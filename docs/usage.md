# Usage

This is the part that matters. Anyone can show a dashboard; the question is
whether the numbers on it survive being checked.

## The cost model

Freight cost is:

```
cost = BASE_FEE + (PER_KM_PER_KG × distance × weight × tier) × (1 + fuel)
```

| Constant | Value |
|---|---|
| `BASE_FEE` | 250 PKR |
| `PER_KM_PER_KG` | 0.018 |
| `fuel` | 11% |

The weight tier steps down as shipments get heavier, because the marginal cost
of the 500th kilogram is lower than the 5th:

| Weight | Multiplier |
|---|---|
| ≤ 50 kg | 1.00 |
| ≤ 500 kg | 0.92 |
| ≤ 5,000 kg | 0.84 |
| > 5,000 kg | 0.78 |

### Worked example

A 320 kg shipment over 1,240 km:

```
0.018 × 1240        = 22.32
22.32 × 320         = 7142.40
7142.40 × 0.92      = 6571.008     (320 kg falls in the 0.92 tier)
6571.008 × 1.11     = 7293.81888   (11% fuel)
7293.81888 + 250    = 7543.81888
                    → 7543.82 PKR
```

That is exactly what `routing.freight_cost(320, 1240)` returns, and
`tests/test_routing.py::test_freight_cost_matches_hand_calculation` asserts it.
If you change a constant, that test fails — which is the point.

## Transit time

```
transit_hours = distance / average_speed + 3 hours handling
```

Average speed depends on the distance band:

| Distance | Speed |
|---|---|
| ≤ 50 km | 22 km/h |
| ≤ 300 km | 45 km/h |
| ≤ 1,000 km | 58 km/h |
| > 1,000 km | 52 km/h |

City runs average 22 km/h because they are stop-start. Long hauls average
faster on motorways, then drop slightly past 1,000 km where driver rest periods
start to matter. These are modelling choices, not measurements — stated so you
can disagree with them.

The same 1,240 km shipment: `1240 / 52 + 3 = 26.8 hours`.

## At-risk detection

`slack_hours = deadline_hours - transit_hours`

Negative slack means the shipment physically cannot make its deadline. The
dispatcher agent sets the shipment to `delayed` and records a `flag_at_risk`
step with the arithmetic in it.

A 1,240 km shipment with a 30-hour deadline has 3.2 hours of slack — tight but
possible. With a 20-hour deadline it has −6.8 hours, and the agent flags it
before anyone has to notice manually.

## Route ranking

Each candidate route is scored as:

```
score = (freight_cost + toll) × (1 + risk × 0.4)
```

Lower is better. The `0.4` prices a 0.1 risk step at 4% of freight — a judgement
call, but a stated one. A longer motorway detour can beat a shorter direct road
when the risk gap is wide enough, and there is a test for exactly that case.

The ranking is returned with every component visible, so a dispatcher can see
*why* the motorway won rather than just being told it did.

## Triage rules

Incidents are classified by keyword, most severe rule first:

| Pattern | Severity | Action |
|---|---|---|
| accident, collision, crash, fire, theft, stolen, hijack | critical | escalate_human |
| perishable, spoiled, cold chain, temperature, melted | critical | escalate_human |
| customs, clearance, detained, seized, paperwork | high | escalate_human |
| breakdown, engine, tyre, puncture, mechanical | high | reassign_carrier |
| flood, rain, storm, landslide, road closed, blocked | high | notify_customer |
| delayed, late, delay, traffic, congestion | medium | notify_customer |
| address, wrong location, not found, unreachable | medium | notify_customer |
| damaged, dent, broken, crushed, leak | high | escalate_human |

Two behaviours worth knowing:

**The worst match wins.** "Delayed because of a tyre puncture" matches both the
delay rule and the breakdown rule. Breakdown is more severe, so the result is
`high` / `reassign_carrier`. The delay is a symptom; the puncture is the cause.

**Unmatched text is not dropped.** Anything that matches nothing becomes
`low` / `notify_customer` with an `unclassified` label. A human still sees it.
Silently discarding an incident report is how you lose a shipment and a customer
in the same afternoon.

**High value raises the floor.** A declared value of 500,000 PKR or more lifts
`low` and `medium` to `high` / `escalate_human`. It never downgrades a critical.

## Reading a run trace

Every run stores its steps. A route optimisation looks like this:

```json
[
  {"step": "load_candidates", "detail": {"count": 2}},
  {"step": "rank_routes",     "detail": {"ranking": ["direct", "motorway"]}},
  {"step": "select_route",    "detail": {"chosen": "direct", "score": 8298.2}}
]
```

Check the score by hand: freight for 320 kg over 1,240 km is 7,543.82, risk is
0.25, so `7543.82 × (1 + 0.25 × 0.4) = 7543.82 × 1.1 = 8298.2`. It matches.

That is the whole product claim. If a number in a trace does not reconcile, it
is a bug, and you can prove it.

## The task DAG

A task with `depends_on_id` will not run until its parent is `succeeded`.

```
Dispatch QFL-1001  (priority 1)
        │
        └──> Optimise route QFL-1001  (priority 2, depends on the above)
```

First dispatch: the parent runs, the child is skipped with
`"Dependency is queued, not succeeded."` Second dispatch: the child runs.

Note the distinction between `running` and `failed`. A parent that is still
going might succeed, so the child waits. A parent that failed will never
succeed, so the child is blocked permanently and the operator needs to know.
Both cases produce a different `skipped` reason.

## Agent capacity

Each agent has `max_concurrency`. At dispatch, an agent at capacity is skipped,
not queued silently. The skip reason names the agent and its load:

```
All 'dispatcher' agents are at capacity: Tarmeem (3/3).
```

Capacity is re-checked within a single dispatch batch, so two tasks in one
request cannot both claim the last slot.

## Roles

| Role | Can do |
|---|---|
| `viewer` | Read tasks, runs, shipments, agents, metrics |
| `operator` | Everything above, plus create shipments and tasks, dispatch |
| `admin` | Everything above, plus create/toggle agents, read the audit log |

Self-registration always yields `viewer`. See
[setup.md](setup.md#creating-a-real-admin) for how to promote someone.

## Known limitations

Stated here rather than discovered in production:

- **Rate limiting is per-process.** Two uvicorn workers allow twice the
  configured rate. Move to Redis before scaling out.
- **Dispatch is synchronous.** A slow handler blocks the request. The `Run`
  model is already shaped for a worker queue, so the fix is transport, not
  schema.
- **No Content-Security-Policy.** The SPA uses inline event handlers; adding a
  CSP means refactoring `app.js` first.
- **No refresh tokens or account lockout.** A stolen token is valid for 24
  hours.
- **Token counts are estimates.** `TOKENS_PER_STEP = 180` is a stand-in for
  prompt+completion size, not billed usage. The cost dashboard sums real
  numbers, but those numbers are modelled.
