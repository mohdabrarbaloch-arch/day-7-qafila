"""Task execution: run an agent against a task and record every step.

The executor is synchronous and in-process. That is a deliberate scope choice:
a real deployment would hand this to a worker queue, and the `Run` row is
already shaped for that (status, steps, tokens, cost, error) so swapping the
transport does not change the data model.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import Agent, AgentKind, Run, RunStatus, Shipment, ShipmentStatus, Task, TaskStatus
from . import routing, triage

# Rough per-step token accounting so the cost dashboard has real numbers to
# sum. These are estimates of prompt+completion size, not billed usage.
TOKENS_PER_STEP = 180
USD_PER_1K_TOKENS = 0.002


def _step(name: str, detail: dict) -> dict:
    return {
        "step": name,
        "at": datetime.now(UTC).isoformat(),
        "detail": detail,
    }


def _run_dispatcher(task: Task, shipment: Shipment | None) -> tuple[list[dict], dict]:
    steps = [_step("load_shipment", {"shipment_id": shipment.id if shipment else None})]
    if shipment is None:
        raise ValueError("dispatcher requires a shipment")

    cost = routing.freight_cost(shipment.weight_kg, shipment.distance_km)
    hours = routing.transit_hours(shipment.distance_km)
    slack = routing.slack_hours(shipment.distance_km, shipment.deadline_hours)
    urgency = routing.urgency_score(shipment.distance_km, shipment.deadline_hours)

    steps.append(
        _step(
            "compute_plan",
            {
                "freight_pkr": cost,
                "transit_hours": hours,
                "slack_hours": slack,
                "urgency": urgency,
            },
        )
    )

    if slack < 0:
        steps.append(
            _step(
                "flag_at_risk",
                {"reason": f"Needs {hours}h but deadline is {shipment.deadline_hours}h"},
            )
        )
        shipment.status = ShipmentStatus.delayed
    else:
        shipment.status = ShipmentStatus.in_transit

    steps.append(_step("assign_carrier", {"status": shipment.status.value}))
    return steps, {"freight_pkr": cost, "transit_hours": hours, "urgency": urgency}


def _run_route_optimizer(task: Task, shipment: Shipment | None) -> tuple[list[dict], dict]:
    if shipment is None:
        raise ValueError("route optimizer requires a shipment")

    options = task.payload.get("routes")
    if not options:
        # Default: direct, and a longer toll-road detour. Real enough to rank.
        options = [
            {"name": "direct", "distance_km": shipment.distance_km, "toll_pkr": 0, "risk": 0.25},
            {
                "name": "motorway",
                "distance_km": round(shipment.distance_km * 1.08, 1),
                "toll_pkr": 1_800,
                "risk": 0.08,
            },
        ]

    parsed = [
        routing.RouteOption(
            name=str(o["name"]),
            distance_km=float(o["distance_km"]),
            toll_pkr=float(o.get("toll_pkr", 0)),
            risk=float(o.get("risk", 0)),
        )
        for o in options
    ]

    steps = [_step("load_candidates", {"count": len(parsed)})]
    ranked = routing.rank_routes(shipment.weight_kg, parsed)
    steps.append(_step("rank_routes", {"ranking": [r["name"] for r in ranked]}))
    best = ranked[0]
    steps.append(_step("select_route", {"chosen": best["name"], "score": best["score"]}))
    return steps, {"chosen": best["name"], "ranking": ranked}


def _run_inventory_auditor(task: Task, shipment: Shipment | None) -> tuple[list[dict], dict]:
    items = task.payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("payload.items must be a list")

    steps = [_step("load_manifest", {"line_items": len(items)})]
    shortages = []
    for item in items:
        sku = str(item.get("sku", "?"))
        on_hand = float(item.get("on_hand", 0))
        required = float(item.get("required", 0))
        if on_hand < required:
            shortages.append({"sku": sku, "short_by": round(required - on_hand, 2)})

    steps.append(_step("compare_stock", {"shortages": len(shortages)}))
    if shortages:
        steps.append(_step("raise_shortage", {"items": shortages}))
    else:
        steps.append(_step("confirm_ready", {"items": len(items)}))
    return steps, {"shortages": shortages, "ready": not shortages}


def _run_exception_handler(task: Task, shipment: Shipment | None) -> tuple[list[dict], dict]:
    description = str(task.payload.get("description", ""))
    declared = float(task.payload.get("declared_value_pkr", 0) or 0)

    steps = [_step("read_incident", {"chars": len(description)})]
    result = triage.triage(description, declared)
    steps.append(_step("classify", result.as_dict()))
    steps.append(_step("choose_action", {"action": result.action.value}))

    if shipment is not None and result.severity in {triage.Severity.high, triage.Severity.critical}:
        shipment.status = ShipmentStatus.delayed
        steps.append(_step("mark_shipment", {"status": shipment.status.value}))

    return steps, result.as_dict()


HANDLERS = {
    AgentKind.dispatcher: _run_dispatcher,
    AgentKind.route_optimizer: _run_route_optimizer,
    AgentKind.inventory_auditor: _run_inventory_auditor,
    AgentKind.exception_handler: _run_exception_handler,
}


def execute_task(db: Session, task: Task, agent: Agent) -> Run:
    """Run one task, persist the Run, and move the task to a terminal status."""
    run = Run(task_id=task.id, agent_id=agent.id, status=RunStatus.running, steps=[])
    db.add(run)
    task.status = TaskStatus.running
    task.agent_id = agent.id
    db.flush()

    shipment = db.get(Shipment, task.shipment_id) if task.shipment_id else None
    handler = HANDLERS.get(task.kind)

    try:
        if handler is None:
            raise ValueError(f"No handler registered for kind '{task.kind.value}'")
        steps, output = handler(task, shipment)
        run.steps = steps
        run.tokens_used = len(steps) * TOKENS_PER_STEP
        run.cost_usd = round(run.tokens_used / 1000 * USD_PER_1K_TOKENS, 6)
        run.status = RunStatus.succeeded
        task.status = TaskStatus.succeeded
        task.payload = {**task.payload, "output": output}
    except Exception as exc:  # noqa: BLE001 - the run row is the error boundary
        run.status = RunStatus.failed
        run.error = f"{type(exc).__name__}: {exc}"
        task.status = TaskStatus.failed
        run.tokens_used = len(run.steps) * TOKENS_PER_STEP
        run.cost_usd = round(run.tokens_used / 1000 * USD_PER_1K_TOKENS, 6)
    finally:
        run.finished_at = datetime.now(UTC)
        db.flush()

    return run
