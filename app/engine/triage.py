"""Exception triage: turn a free-text incident into a severity and an action.

Rule-based on purpose. A dispatcher needs to know *why* a shipment was
escalated, and a keyword table is something they can read and argue with.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass


class Severity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Action(str, enum.Enum):
    auto_resolve = "auto_resolve"
    notify_customer = "notify_customer"
    reassign_carrier = "reassign_carrier"
    escalate_human = "escalate_human"


# (pattern, severity, action, label). First match wins, so order matters:
# the most severe patterns are listed first.
RULES: tuple[tuple[str, Severity, Action, str], ...] = (
    (
        r"\b(accident|collision|crash|fire|theft|stolen|hijack)\b",
        Severity.critical,
        Action.escalate_human,
        "safety_or_loss",
    ),
    (
        r"\b(perishable|spoiled|spoilt|cold chain|temperature|melted)\b",
        Severity.critical,
        Action.escalate_human,
        "cold_chain_breach",
    ),
    (
        r"\b(customs|clearance|detained|seized|paperwork)\b",
        Severity.high,
        Action.escalate_human,
        "customs_hold",
    ),
    (
        r"\b(breakdown|engine|tyre|tire|puncture|mechanical)\b",
        Severity.high,
        Action.reassign_carrier,
        "vehicle_breakdown",
    ),
    (
        r"\b(flood|rain|storm|landslide|road closed|blocked)\b",
        Severity.high,
        Action.notify_customer,
        "weather_or_road",
    ),
    (
        r"\b(delayed|late|delay|traffic|congestion)\b",
        Severity.medium,
        Action.notify_customer,
        "delay",
    ),
    (
        r"\b(address|wrong location|not found|unreachable|no answer)\b",
        Severity.medium,
        Action.notify_customer,
        "address_issue",
    ),
    (
        r"\b(damaged|dent|broken|crushed|leak)\b",
        Severity.high,
        Action.escalate_human,
        "cargo_damage",
    ),
)

# Escalation floor by shipment value band (PKR). A delay on a 2M shipment is
# not the same event as a delay on a 5k one.
VALUE_ESCALATION_PKR = 500_000.0

_SEVERITY_ORDER = [Severity.low, Severity.medium, Severity.high, Severity.critical]


@dataclass(frozen=True)
class Triage:
    severity: Severity
    action: Action
    labels: list[str]
    reason: str

    def as_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "action": self.action.value,
            "labels": self.labels,
            "reason": self.reason,
        }


def _max_severity(a: Severity, b: Severity) -> Severity:
    return a if _SEVERITY_ORDER.index(a) >= _SEVERITY_ORDER.index(b) else b


def triage(description: str, declared_value_pkr: float = 0.0) -> Triage:
    """Classify an incident report.

    Unmatched text is not silently dropped — it becomes a low-severity
    'unclassified' triage that a human still sees.
    """
    text = (description or "").lower()
    labels: list[str] = []
    severity = Severity.low
    action = Action.auto_resolve
    matched_any = False

    for pattern, rule_severity, rule_action, label in RULES:
        if re.search(pattern, text):
            matched_any = True
            labels.append(label)
            if _SEVERITY_ORDER.index(rule_severity) > _SEVERITY_ORDER.index(severity):
                severity = rule_severity
                action = rule_action

    if not matched_any:
        labels.append("unclassified")
        severity = Severity.low
        action = Action.notify_customer

    # High-value cargo raises the floor: money changes the response, not the
    # words in the report.
    if declared_value_pkr >= VALUE_ESCALATION_PKR and severity in {Severity.low, Severity.medium}:
        severity = Severity.high
        action = Action.escalate_human
        labels.append("high_value")

    if severity is Severity.critical:
        action = Action.escalate_human

    reason = f"Matched {', '.join(labels)}; severity {severity.value} " f"-> {action.value}" + (
        f" (declared value {declared_value_pkr:,.0f} PKR)" if declared_value_pkr else ""
    )
    return Triage(severity=severity, action=action, labels=labels, reason=reason)
