/* Qafila SPA — vanilla JS, no build step.
   State lives in one object; every render is a full re-render of its view.
   At this size that is simpler and less buggy than a diffing layer. */

const state = {
  token: localStorage.getItem("qafila_token") || null,
  role: localStorage.getItem("qafila_role") || null,
  view: "dash",
  tasks: [],
  runs: [],
  shipments: [],
  agents: [],
  metrics: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ---------- api ---------- */

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;

  const res = await fetch(path, { ...options, headers });
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { detail: text }; }

  if (!res.ok) {
    const detail = body && body.detail ? body.detail : `HTTP ${res.status}`;
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return body;
}

/* ---------- helpers ---------- */

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function pill(status) {
  return `<span class="pill ${esc(status)}">${esc(status.replace(/_/g, " "))}</span>`;
}

function money(n) {
  return `$${Number(n || 0).toFixed(4)}`;
}

function show(view) {
  state.view = view;
  $$(".view").forEach((el) => el.classList.add("hidden"));
  const target = $(`#view-${view}`);
  if (target) target.classList.remove("hidden");
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
}

/* ---------- auth ---------- */

function setSession(token, role) {
  state.token = token;
  state.role = role;
  localStorage.setItem("qafila_token", token);
  localStorage.setItem("qafila_role", role);
  $("#logout").classList.remove("hidden");
  $("#who").textContent = role ? `role: ${role}` : "";
  $("#view-auth").classList.add("hidden");
  show("dash");
  loadAll();
}

function clearSession() {
  state.token = null;
  state.role = null;
  localStorage.removeItem("qafila_token");
  localStorage.removeItem("qafila_role");
  $("#logout").classList.add("hidden");
  $("#who").textContent = "";
  $$(".view").forEach((el) => el.classList.add("hidden"));
  $("#view-auth").classList.remove("hidden");
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  $("#auth-error").textContent = "";
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const body = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: form.email.value.trim(),
        password: form.password.value,
      }),
    });
    setSession(body.access_token, body.role);
  } catch (err) {
    $("#auth-error").textContent = err.message;
  } finally {
    button.disabled = false;
  }
});

$("#logout").addEventListener("click", clearSession);

/* ---------- data loading ---------- */

async function loadAll() {
  try {
    const [metrics, tasks, runs, shipments, agents] = await Promise.all([
      api("/api/metrics"),
      api("/api/tasks?limit=50"),
      api("/api/runs?limit=25"),
      api("/api/shipments?limit=50"),
      api("/api/agents"),
    ]);
    state.metrics = metrics;
    state.tasks = tasks;
    state.runs = runs;
    state.shipments = shipments;
    state.agents = agents;
    renderAll();
  } catch (err) {
    if (err.status === 401) { clearSession(); return; }
    console.error(err);
  }
}

function renderAll() {
  renderStats();
  renderTasks();
  renderRuns();
  renderShipments();
  renderAgents();
}

/* ---------- render: stats ---------- */

function renderStats() {
  const m = state.metrics;
  if (!m) return;
  const queued = m.tasks_by_status.queued || 0;
  const failed = m.tasks_by_status.failed || 0;
  const succeeded = m.tasks_by_status.succeeded || 0;

  const cards = [
    { k: "Queued", v: queued, cls: queued > 0 ? "warn" : "" },
    { k: "Succeeded", v: succeeded, cls: "" },
    { k: "Failed", v: failed, cls: failed > 0 ? "bad" : "" },
    { k: "Runs", v: m.runs_total, cls: "" },
    { k: "Tokens", v: m.tokens_used.toLocaleString(), cls: "" },
    { k: "Spend", v: money(m.cost_usd), cls: "" },
  ];

  $("#stats").innerHTML = cards
    .map((c) => `<div class="stat"><div class="k">${c.k}</div><div class="v ${c.cls}">${esc(c.v)}</div></div>`)
    .join("");
}

/* ---------- render: tasks ---------- */

function renderTasks() {
  const body = $("#task-table tbody");
  if (!state.tasks.length) {
    body.innerHTML = `<tr><td colspan="5" class="muted">No tasks yet. Create one from a shipment below.</td></tr>`;
    return;
  }
  const shipmentRef = Object.fromEntries(state.shipments.map((s) => [s.id, s.reference]));
  body.innerHTML = state.tasks
    .map((t) => `
      <tr>
        <td>${esc(t.title)}</td>
        <td class="mono">${esc(t.kind)}</td>
        <td class="mono">${t.priority}</td>
        <td>${pill(t.status)}</td>
        <td class="mono">${esc(shipmentRef[t.shipment_id] || "—")}</td>
      </tr>`)
    .join("");
}

/* ---------- render: runs ---------- */

function renderRuns() {
  const body = $("#run-table tbody");
  if (!state.runs.length) {
    body.innerHTML = `<tr><td colspan="6" class="muted">No runs yet — dispatch the queue.</td></tr>`;
    return;
  }
  const agentName = Object.fromEntries(state.agents.map((a) => [a.id, a.name]));
  body.innerHTML = state.runs
    .map((r) => `
      <tr>
        <td>${esc(agentName[r.agent_id] || "—")}</td>
        <td>${pill(r.status)}</td>
        <td class="mono">${r.steps.length}</td>
        <td class="mono">${r.tokens_used}</td>
        <td class="mono">${money(r.cost_usd)}</td>
        <td><button class="btn tiny ghost" data-run="${esc(r.id)}">Trace</button></td>
      </tr>`)
    .join("");

  body.querySelectorAll("[data-run]").forEach((btn) => {
    btn.addEventListener("click", () => openTrace(btn.dataset.run));
  });
}

function openTrace(runId) {
  const run = state.runs.find((r) => r.id === runId);
  if (!run) return;
  $("#drawer-title").textContent = `Run trace — ${run.status}`;
  const steps = run.steps.length
    ? run.steps.map((s) => `
        <li>
          <span class="step-name">${esc(s.step)}</span>
          <span class="step-time">${esc(new Date(s.at).toLocaleTimeString())}</span>
          <pre>${esc(JSON.stringify(s.detail, null, 2))}</pre>
        </li>`).join("")
    : `<li class="muted">No steps recorded.</li>`;
  const error = run.error ? `<li><span class="step-name" style="color:var(--danger)">error</span><pre>${esc(run.error)}</pre></li>` : "";
  $("#drawer-steps").innerHTML = steps + error;
  $("#drawer").classList.remove("hidden");
}

$("#drawer-close").addEventListener("click", () => $("#drawer").classList.add("hidden"));
$("#drawer").addEventListener("click", (e) => {
  if (e.target.id === "drawer") $("#drawer").classList.add("hidden");
});

/* ---------- render: shipments ---------- */

function renderShipments() {
  const body = $("#shipment-table tbody");
  if (!state.shipments.length) {
    body.innerHTML = `<tr><td colspan="6" class="muted">No shipments yet.</td></tr>`;
    return;
  }
  body.innerHTML = state.shipments
    .map((s) => `
      <tr>
        <td class="mono">${esc(s.reference)}</td>
        <td>${esc(s.origin_city)} → ${esc(s.destination_city)}</td>
        <td class="mono">${s.weight_kg} kg</td>
        <td class="mono">${s.distance_km} km</td>
        <td>${pill(s.status)}</td>
        <td><button class="btn tiny" data-dispatch-shipment="${esc(s.id)}">Dispatch</button></td>
      </tr>`)
    .join("");

  body.querySelectorAll("[data-dispatch-shipment]").forEach((btn) => {
    btn.addEventListener("click", () => createDispatchTask(btn.dataset.dispatchShipment));
  });
}

async function createDispatchTask(shipmentId) {
  const shipment = state.shipments.find((s) => s.id === shipmentId);
  if (!shipment) return;
  try {
    await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title: `Dispatch ${shipment.reference}`,
        kind: "dispatcher",
        priority: 3,
        shipment_id: shipmentId,
        payload: {},
      }),
    });
    await loadAll();
    show("dash");
  } catch (err) {
    alert(err.message);
  }
}

/* ---------- render: agents ---------- */

function renderAgents() {
  const grid = $("#agent-grid");
  if (!state.agents.length) {
    grid.innerHTML = `<p class="muted">No agents registered.</p>`;
    return;
  }
  const busy = (state.metrics && state.metrics.agents_busy) || {};
  grid.innerHTML = state.agents
    .map((a) => `
      <div class="agent-card">
        <h3>${esc(a.name)} ${a.enabled ? "" : '<span class="pill cancelled">disabled</span>'}</h3>
        <div class="kind">${esc(a.kind)}</div>
        <p>${esc(a.description || "No description.")}</p>
        <div class="agent-meta">
          <span>cap ${a.max_concurrency}</span>
          <span>busy ${busy[a.name] || 0}</span>
        </div>
      </div>`)
    .join("");
}

/* ---------- actions ---------- */

$("#dispatch").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  $("#dispatch-msg").textContent = "Dispatching…";
  try {
    const result = await api("/api/tasks/dispatch?max_tasks=10", { method: "POST" });
    $("#dispatch-msg").textContent = result.message;
    if (result.skipped.length) {
      const reasons = result.skipped.slice(0, 3).map((s) => s.reason).join(" · ");
      $("#dispatch-msg").textContent += ` ${reasons}`;
    }
    await loadAll();
  } catch (err) {
    $("#dispatch-msg").textContent = err.message;
  } finally {
    button.disabled = false;
  }
});

$("#refresh").addEventListener("click", loadAll);

$("#new-shipment-toggle").addEventListener("click", () => {
  $("#shipment-form").classList.toggle("hidden");
});

$("#shipment-cancel").addEventListener("click", () => {
  $("#shipment-form").classList.add("hidden");
  $("#shipment-error").textContent = "";
});

$("#shipment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  $("#shipment-error").textContent = "";
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await api("/api/shipments", {
      method: "POST",
      body: JSON.stringify({
        reference: form.reference.value.trim(),
        origin_city: form.origin_city.value.trim(),
        destination_city: form.destination_city.value.trim(),
        weight_kg: Number(form.weight_kg.value),
        distance_km: Number(form.distance_km.value),
        deadline_hours: Number(form.deadline_hours.value),
      }),
    });
    form.reset();
    form.classList.add("hidden");
    await loadAll();
  } catch (err) {
    $("#shipment-error").textContent = err.message;
  } finally {
    button.disabled = false;
  }
});

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => show(tab.dataset.view));
});

/* ---------- boot ---------- */

if (state.token) {
  $("#logout").classList.remove("hidden");
  $("#who").textContent = state.role ? `role: ${state.role}` : "";
  $("#view-auth").classList.add("hidden");
  show("dash");
  loadAll();
} else {
  clearSession();
}
