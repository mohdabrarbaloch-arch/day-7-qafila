# Usage

## Signing in

Open the app, switch to the **Register** tab and create an account, or use the demo account (`demo@qafila.pk` / `demo12345`).

## Agents

Agents are the workers. Four kinds are available:

| Kind | What it does | Example input |
|---|---|---|
| `dispatch` | Picks the cheapest available vehicle that fits the weight | `{"weight_kg": 120, "origin": "Karachi", "destination": "Lahore"}` |
| `route` | Computes distance, ETA and cost, with optional stopover | `{"origin": "Karachi", "destination": "Lahore", "stopover": "Hyderabad", "speed_kmh": 60}` |
| `inventory` | Flags SKUs below a reorder point, suggests order qty | `{"sku": "SKU-1002", "reorder_point": 10}` |
| `demand` | Moving-average forecast from demand history | `{"sku": "SKU-1001", "window": 7}` |

Create agents from the **Agents** tab. You can pause/run them and delete them.

## Tasks

1. Go to **Tasks**.
2. Pick an agent, give the task a title, and paste the input as JSON.
3. Click **Queue task**.
4. Click **▶ Run queue** — queued tasks execute oldest-first and their outputs appear inline.

A failed task (e.g. dispatch with no fitting vehicle) shows its status as `failed` with the reason in the error field.

## Shipments

1. Go to **Shipments** → **New shipment**.
2. Enter origin, destination and weight.
3. The dispatch agent assigns the cheapest fitting vehicle automatically, sets the ETA and cost, and marks the vehicle `on_route`.
4. Click **Advance →** to move it through `assigned → in_transit → delivered`. On delivery the vehicle returns to `available`.

If no vehicle fits the weight, the shipment stays `created` and an event explains why — add a bigger vehicle to the fleet and create the shipment again.

## Fleet

Add bikes, vans and trucks with capacity and cost-per-km. The dispatch agent uses these to make assignments. You can update a vehicle's status/location via the API (`PATCH /api/fleet/{id}`).

## Dashboard

The dashboard shows live counts (shipments, agents, tasks, fleet) and the 10 most recent audit events.
