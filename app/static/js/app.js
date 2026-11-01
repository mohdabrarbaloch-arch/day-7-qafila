/* Qafila SPA — vanilla JS, no build step. */
"use strict";

const API = "/api";
let token = localStorage.getItem("qafila_token") || null;
let currentUser = null;

const $ = (id) => document.getElementById(id);

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add("hidden"), 3200);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) {
    logout();
    throw new Error("Session expired — please sign in again");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

/* ---------- Auth ---------- */
function showAuth() {
  $("auth-view").classList.remove("hidden");
  $("app-view").classList.add("hidden");
}
function showApp() {
  $("auth-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  $("user-name").textContent = currentUser ? currentUser.name : "";
  switchView("dashboard");
  refreshAll();
}

function logout() {
  token = null;
  currentUser = null;
  localStorage.removeItem("qafila_token");
  showAuth();
}

/* ---------- Views ---------- */
function switchView(name) {
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-" + name).classList.remove("hidden");
  if (name === "dashboard") loadDashboard();
  if (name === "agents") loadAgents();
  if (name === "tasks") loadTasks();
  if (name === "shipments") loadShipments();
  if (name === "fleet") loadFleet();
}

async function refreshAll() {
  loadDashboard();
}

/* ---------- Dashboard ---------- */
async function loadDashboard() {
  try {
    const d = await api("/dashboard");
    const grid = $("stat-grid");
    const stats = [
      { n: d.shipments_total, l: "Total shipments", c: "" },
      { n: d.shipments_in_transit, l: "In transit", c: "accent" },
      { n: d.shipments_delivered, l: "Delivered", c: "green" },
      { n: d.agents_total, l: "Agents", c: "" },
      { n: d.agents_running, l: "Agents running", c: "accent" },
      { n: d.tasks_queued, l: "Tasks queued", c: "amber" },
      { n: d.tasks_done, l: "Tasks done", c: "green" },
      { n: d.fleet_available, l: "Fleet available", c: "green" },
      { n: d.fleet_on_route, l: "Fleet on route", c: "accent" },
    ];
    grid.innerHTML = stats
      .map((s) => `<div class="stat-card ${s.c}"><div class="num">${s.n}</div><div class="lbl">${s.l}</div></div>`)
      .join("");
    const list = $("event-list");
    if (!d.recent_events.length) {
      list.innerHTML = "<li>No activity yet — create a shipment or queue a task.</li>";
    } else {
      list.innerHTML = d.recent_events
        .map((e) => `<li><span class="time">${esc(new Date(e.created_at).toLocaleTimeString())}</span><span>${esc(e.message)}</span></li>`)
        .join("");
    }
  } catch (err) {
    toast(err.message);
  }
}

/* ---------- Agents ---------- */
async function loadAgents() {
  try {
    const agents = await api("/agents");
    const list = $("agent-list");
    if (!agents.length) {
      list.innerHTML = `<div class="panel">No agents yet. Create your first one — a dispatcher is a good start.</div>`;
      return;
    }
    list.innerHTML = agents
      .map(
        (a) => `
      <div class="card">
        <div class="row"><h4>${esc(a.name)}</h4><span class="badge ${a.status}">${a.status}</span></div>
        <div class="sub">${esc(a.kind)} agent</div>
        <div class="sub">${esc(a.description)}</div>
        <div class="row"><span class="k">Created</span><span>${esc(new Date(a.created_at).toLocaleDateString())}</span></div>
        <div class="row">
          <button class="btn btn-ghost" onclick="toggleAgent(${a.id}, '${a.status === "running" ? "paused" : "running"}')">${a.status === "running" ? "Pause" : "Run"}</button>
          <button class="btn btn-danger" onclick="deleteAgent(${a.id})">Delete</button>
        </div>
      </div>`
      )
      .join("");
  } catch (err) {
    toast(err.message);
  }
}

async function toggleAgent(id, status) {
  try {
    await api(`/agents/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    loadAgents();
  } catch (err) {
    toast(err.message);
  }
}

async function deleteAgent(id) {
  if (!confirm("Delete this agent and its tasks?")) return;
  try {
    await api(`/agents/${id}`, { method: "DELETE" });
    loadAgents();
  } catch (err) {
    toast(err.message);
  }
}

/* ---------- Tasks ---------- */
async function loadTasks() {
  try {
    const [tasks, agents] = await Promise.all([api("/tasks"), api("/agents")]);
    const sel = $("task-agent");
    sel.innerHTML = agents.map((a) => `<option value="${a.id}">${esc(a.name)} (${a.kind})</option>`).join("");
    const list = $("task-list");
    if (!tasks.length) {
      list.innerHTML = `<div class="panel">No tasks yet. Queue one below, then hit "Run queue".</div>`;
      return;
    }
    list.innerHTML = tasks
      .map(
        (t) => `
      <div class="task-item">
        <div class="grow">
          <div class="title">${esc(t.title)}</div>
          <div class="meta">Task #${t.id} · agent #${t.agent_id} · ${esc(new Date(t.created_at).toLocaleString())}</div>
        </div>
        <span class="badge ${t.status}">${t.status}</span>
        ${t.output_data && Object.keys(t.output_data).length ? `<pre>${esc(JSON.stringify(t.output_data, null, 1))}</pre>` : ""}
        ${t.error ? `<pre>${esc(t.error)}</pre>` : ""}
      </div>`
      )
      .join("");
  } catch (err) {
    toast(err.message);
  }
}

/* ---------- Shipments ---------- */
async function loadShipments() {
  try {
    const shipments = await api("/shipments");
    const list = $("shipment-list");
    if (!shipments.length) {
      list.innerHTML = `<div class="panel">No shipments yet. Create one and the dispatch agent will assign a vehicle automatically.</div>`;
      return;
    }
    list.innerHTML = shipments
      .map(
        (s) => `
      <div class="card">
        <div class="row"><h4>${esc(s.tracking_code)}</h4><span class="badge ${s.status}">${s.status}</span></div>
        <div class="sub">${esc(s.origin)} → ${esc(s.destination)}</div>
        <div class="row"><span class="k">Weight</span><span>${s.weight_kg} kg</span></div>
        <div class="row"><span class="k">ETA</span><span>${s.eta_hours} h</span></div>
        <div class="row"><span class="k">Cost</span><span>PKR ${s.cost.toLocaleString()}</span></div>
        ${s.status !== "delivered" ? `<button class="btn btn-ghost" onclick="advanceShipment(${s.id})">Advance →</button>` : ""}
      </div>`
      )
      .join("");
  } catch (err) {
    toast(err.message);
  }
}

async function advanceShipment(id) {
  try {
    await api(`/shipments/${id}/advance`, { method: "POST" });
    loadShipments();
    loadDashboard();
  } catch (err) {
    toast(err.message);
  }
}

/* ---------- Fleet ---------- */
async function loadFleet() {
  try {
    const vehicles = await api("/fleet");
    const list = $("vehicle-list");
    if (!vehicles.length) {
      list.innerHTML = `<div class="panel">No vehicles yet. Add a van or truck so the dispatch agent has something to assign.</div>`;
      return;
    }
    list.innerHTML = vehicles
      .map(
        (v) => `
      <div class="card">
        <div class="row"><h4>${esc(v.name)}</h4><span class="badge ${v.status}">${v.status}</span></div>
        <div class="sub">${esc(v.vehicle_type)} · ${v.capacity_kg} kg capacity</div>
        <div class="row"><span class="k">Cost / km</span><span>PKR ${v.cost_per_km}</span></div>
        <div class="row"><span class="k">Location</span><span>${esc(v.location || "—")}</span></div>
      </div>`
      )
      .join("");
  } catch (err) {
    toast(err.message);
  }
}

/* ---------- Event wiring ---------- */
document.addEventListener("DOMContentLoaded", () => {
  // Tabs
  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
      $("login-form").classList.toggle("hidden", t.dataset.tab !== "login");
      $("register-form").classList.toggle("hidden", t.dataset.tab !== "register");
      $("auth-error").classList.add("hidden");
    })
  );

  // Login
  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: $("login-email").value, password: $("login-password").value }),
      });
      token = data.access_token;
      currentUser = data.user;
      localStorage.setItem("qafila_token", token);
      showApp();
    } catch (err) {
      $("auth-error").textContent = err.message;
      $("auth-error").classList.remove("hidden");
    }
  });

  // Register
  $("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await api("/auth/register", {
        method: "POST",
        body: JSON.stringify({ name: $("reg-name").value, email: $("reg-email").value, password: $("reg-password").value }),
      });
      token = data.access_token;
      currentUser = data.user;
      localStorage.setItem("qafila_token", token);
      showApp();
    } catch (err) {
      $("auth-error").textContent = err.message;
      $("auth-error").classList.remove("hidden");
    }
  });

  // Nav
  document.querySelectorAll(".nav-btn").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  $("logout-btn").addEventListener("click", logout);

  // Agent form
  $("new-agent-btn").addEventListener("click", () => $("agent-form-wrap").classList.toggle("hidden"));
  $("agent-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/agents", {
        method: "POST",
        body: JSON.stringify({ name: $("agent-name").value, kind: $("agent-kind").value, description: $("agent-desc").value }),
      });
      $("agent-form-wrap").classList.add("hidden");
      $("agent-form").reset();
      loadAgents();
      toast("Agent created");
    } catch (err) {
      toast(err.message);
    }
  });

  // Task form
  $("run-queue-btn").addEventListener("click", async () => {
    try {
      const r = await api("/tasks/run", { method: "POST" });
      toast(`Queue run: ${r.ran} task(s) executed`);
      loadTasks();
      loadDashboard();
    } catch (err) {
      toast(err.message);
    }
  });
  $("task-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    let input = {};
    try {
      input = JSON.parse($("task-input").value || "{}");
    } catch {
      toast("Input must be valid JSON");
      return;
    }
    try {
      await api("/tasks", {
        method: "POST",
        body: JSON.stringify({ agent_id: Number($("task-agent").value), title: $("task-title").value, input_data: input }),
      });
      $("task-form").reset();
      loadTasks();
      toast("Task queued");
    } catch (err) {
      toast(err.message);
    }
  });

  // Shipment form
  $("new-shipment-btn").addEventListener("click", () => $("shipment-form-wrap").classList.toggle("hidden"));
  $("shipment-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const s = await api("/shipments", {
        method: "POST",
        body: JSON.stringify({
          origin: $("ship-origin").value,
          destination: $("ship-destination").value,
          weight_kg: Number($("ship-weight").value),
        }),
      });
      $("shipment-form-wrap").classList.add("hidden");
      $("shipment-form").reset();
      loadShipments();
      loadDashboard();
      toast(`Shipment ${s.tracking_code} created — assigned ${s.vehicle_id ? "vehicle #" + s.vehicle_id : "pending"}`);
    } catch (err) {
      toast(err.message);
    }
  });

  // Vehicle form
  $("new-vehicle-btn").addEventListener("click", () => $("vehicle-form-wrap").classList.toggle("hidden"));
  $("vehicle-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/fleet", {
        method: "POST",
        body: JSON.stringify({
          name: $("veh-name").value,
          vehicle_type: $("veh-type").value,
          capacity_kg: Number($("veh-capacity").value),
          cost_per_km: Number($("veh-cost").value),
        }),
      });
      $("vehicle-form-wrap").classList.add("hidden");
      $("vehicle-form").reset();
      loadFleet();
      toast("Vehicle added");
    } catch (err) {
      toast(err.message);
    }
  });

  // Boot
  if (token) {
    api("/auth/me")
      .then((u) => {
        currentUser = u;
        showApp();
      })
      .catch(() => showAuth());
  } else {
    showAuth();
  }
});
