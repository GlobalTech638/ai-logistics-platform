const API = window.LOGISTICS_API_URL || "http://localhost:8000";
const ORGANIZATION_ID = window.LOGISTICS_ORGANIZATION_ID || "";
const USER_ID = window.LOGISTICS_USER_ID || "dashboard-user";
const USER_ROLE = window.LOGISTICS_USER_ROLE || "viewer";
const CAN_EXECUTE = ["admin", "operations_manager", "fleet_manager"].includes(USER_ROLE);

let vehicles = [];
let routePlansByShipment = new Map();

const headers = () => ({
  "Content-Type": "application/json",
  "X-Organization-Id": ORGANIZATION_ID,
  "X-User-Id": USER_ID,
  "X-User-Role": USER_ROLE,
});

const money = (value, currency = "KES") =>
  `${currency} ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function renderSummary(data) {
  document.querySelector("#metrics").innerHTML = `
    <div class="metric"><p class="eyebrow">FLEET</p><div class="metric-value">${data.fleet.total}</div><small>${data.fleet.active} active</small></div>
    <div class="metric"><p class="eyebrow">ACTIVE SHIPMENTS</p><div class="metric-value">${data.shipments.active}</div><small>${data.shipments.delivered} delivered</small></div>
    <div class="metric"><p class="eyebrow">OPEN AI ALERTS</p><div class="metric-value">${data.alerts.open}</div><small>${data.alerts.critical} critical · ${data.alerts.high} high</small></div>`;

  document.querySelector("#insight-title").textContent =
    data.alerts.critical > 0 ? "Critical attention required" : "Operations currently stable";
  document.querySelector("#insight-text").textContent =
    `${data.fleet.active} vehicles are active across ${data.shipments.active} active shipments. The AI queue contains ${data.alerts.open} unresolved alerts.`;
  document.querySelector("#insight-action").textContent =
    data.alerts.critical > 0 ? "Recommended action: investigate critical alerts first." : "Recommended action: monitor operations and review high-priority alerts.";
}

function recommendationCard(shipment, recommendation) {
  const impact = recommendation.expected_impact || "Operational impact not quantified yet.";
  const fuel = shipment.fuel_cost_impact || { estimated_excess_cost: 0, currency: "KES" };
  const reassign = recommendation.recommendation_type === "reassign_vehicle";
  const reroute = recommendation.recommendation_type === "reroute_shipment";
  const vehicleOptions = vehicles.filter((vehicle) => vehicle.active).map((vehicle) =>
    `<option value="${escapeHtml(vehicle.id)}">${escapeHtml(vehicle.registration_number)} · ${escapeHtml(vehicle.make)} ${escapeHtml(vehicle.model)}</option>`
  ).join("");
  const routeOptions = (routePlansByShipment.get(shipment.shipment_id) || []).filter((plan) => plan.status === "planned").map((plan) =>
    `<option value="${escapeHtml(plan.id)}">${escapeHtml(plan.corridor)} · sequence ${escapeHtml(plan.route_sequence)}</option>`
  ).join("");
  const executionControls = !CAN_EXECUTE
    ? `<small class="permission-note">Viewer/analyst access: execution controls are disabled.</small>`
    : reroute
      ? `<select class="route-plan-select" aria-label="Route plan"><option value="">Select route plan</option>${routeOptions}</select><button class="action-button" data-action="accept">Accept recommendation</button>`
      : `${reassign ? `<select class="vehicle-select" aria-label="Replacement vehicle"><option value="">Select replacement vehicle</option>${vehicleOptions}</select>` : ""}<button class="action-button" data-action="accept">Accept recommendation</button>`;

  return `
    <article class="recommendation" data-shipment-id="${escapeHtml(shipment.shipment_id)}" data-recommendation-type="${escapeHtml(recommendation.recommendation_type)}">
      <div class="recommendation-top">
        <div>
          <span class="priority priority-${escapeHtml(recommendation.priority)}">${escapeHtml(recommendation.priority)}</span>
          <h3>${escapeHtml(recommendation.title)}</h3>
          <p class="route">${escapeHtml(shipment.shipment_reference)} · ${escapeHtml(shipment.route.origin)} → ${escapeHtml(shipment.route.destination)}</p>
        </div>
        <strong class="score">${Math.round(Number(recommendation.score || 0))}</strong>
      </div>
      <p class="rationale">${escapeHtml(recommendation.rationale)}</p>
      <div class="impact"><span>Expected impact</span><strong>${escapeHtml(impact)}</strong></div>
      ${fuel.estimated_excess_cost > 0 ? `<div class="fuel-impact">Estimated excess fuel: <strong>${money(fuel.estimated_excess_cost, fuel.currency)}</strong></div>` : ""}
      <div class="recommendation-actions">${executionControls}</div>
      <div class="card-status" aria-live="polite"></div>
    </article>`;
}

function renderRecommendations(data) {
  const items = data.shipments.flatMap((shipment) =>
    shipment.recommendations.map((recommendation) => ({ shipment, recommendation }))
  );
  const container = document.querySelector("#recommendations");
  if (!items.length) {
    container.innerHTML = `<div class="empty">No active recommendations. Operations are currently within the configured thresholds.</div>`;
    return;
  }
  container.innerHTML = items.map(({ shipment, recommendation }) => recommendationCard(shipment, recommendation)).join("");
  container.querySelectorAll("button[data-action='accept']").forEach((button) => button.addEventListener("click", handleAccept));
}

async function handleAccept(event) {
  const card = event.currentTarget.closest(".recommendation");
  const shipmentId = card.dataset.shipmentId;
  const recommendationType = card.dataset.recommendationType;
  const status = card.querySelector(".card-status");
  const vehicleSelect = card.querySelector(".vehicle-select");
  const routePlanSelect = card.querySelector(".route-plan-select");
  const button = event.currentTarget;

  if (["reassign_vehicle", "reroute_shipment"].includes(recommendationType)) {
    const selected = vehicleSelect?.value || routePlanSelect?.value;
    if (!selected) {
      status.textContent = recommendationType === "reassign_vehicle"
        ? "Select a replacement vehicle before accepting this executable recommendation."
        : "Select a route plan before accepting this executable recommendation.";
      return;
    }
  }

  button.disabled = true;
  status.textContent = "Recording operator decision…";

  try {
    const createResponse = await fetch(`${API}/api/v1/recommendations/${ORGANIZATION_ID}/shipments/${shipmentId}/actions`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        recommendation_type: recommendationType,
        priority: card.querySelector(".priority").textContent,
        recommendation_score: Number(card.querySelector(".score").textContent),
        title: card.querySelector("h3").textContent,
        rationale: card.querySelector(".rationale").textContent,
        expected_impact: card.querySelector(".impact strong").textContent,
      }),
    });
    if (!createResponse.ok) throw new Error(`Could not create action (${createResponse.status})`);
    const action = await createResponse.json();

    const acceptedResponse = await fetch(`${API}/api/v1/recommendations/actions/${action.id}/status`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify({ status: "accepted" }),
    });
    if (!acceptedResponse.ok) throw new Error(`Could not accept action (${acceptedResponse.status})`);

    if (recommendationType === "reassign_vehicle") {
      await executeAction(action.id, { status: "in_progress", vehicle_id: vehicleSelect.value });
      status.textContent = "Accepted and executed. Vehicle reassignment recorded.";
    } else if (recommendationType === "reroute_shipment") {
      await executeAction(action.id, { status: "in_progress", route_plan_id: routePlanSelect.value });
      status.textContent = "Accepted and executed. Route plan activated.";
    } else {
      status.textContent = "Accepted. Execution is tracked in the decision log.";
    }

    await loadActions();
  } catch (error) {
    status.textContent = error.message;
    button.disabled = false;
  }
}

async function executeAction(actionId, payload) {
  const response = await fetch(`${API}/api/v1/recommendations/actions/${actionId}/status`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Execution failed (${response.status})`);
  }
  return response.json();
}

async function loadRoutePlans(shipmentId) {
  try {
    const response = await fetch(`${API}/api/v1/route-plans/${ORGANIZATION_ID}/shipments/${shipmentId}`, { headers: headers() });
    if (!response.ok) throw new Error(`Route plans request failed: ${response.status}`);
    const data = await response.json();
    routePlansByShipment.set(shipmentId, data.route_plans || []);
  } catch (error) {
    routePlansByShipment.set(shipmentId, []);
    console.warn(`Could not load route plans for ${shipmentId}:`, error);
  }
}

async function loadActions() {
  const container = document.querySelector("#actions");
  try {
    const response = await fetch(`${API}/api/v1/recommendations/${ORGANIZATION_ID}/actions`, { headers: headers() });
    if (!response.ok) throw new Error(`Actions request failed: ${response.status}`);
    const data = await response.json();
    document.querySelector("#action-count").textContent = data.actions.length;
    if (!data.actions.length) {
      container.innerHTML = `<div class="empty">No operator decisions recorded yet.</div>`;
      return;
    }
    container.innerHTML = data.actions.map((action) => {
      const executable = CAN_EXECUTE && action.status === "accepted" && ["reassign_vehicle", "reroute_shipment"].includes(action.recommendation_type);
      const control = executable
        ? action.recommendation_type === "reassign_vehicle"
          ? `<select class="log-vehicle-select" data-action-id="${escapeHtml(action.id)}" aria-label="Replacement vehicle"><option value="">Select vehicle</option>${vehicles.filter((vehicle) => vehicle.active).map((vehicle) => `<option value="${escapeHtml(vehicle.id)}">${escapeHtml(vehicle.registration_number)}</option>`).join("")}</select><button class="action-button log-execute" data-action-id="${escapeHtml(action.id)}">Execute</button>`
          : `<select class="log-route-select" data-action-id="${escapeHtml(action.id)}" data-shipment-id="${escapeHtml(action.shipment_id || "")}" aria-label="Route plan"><option value="">Select route plan</option>${(routePlansByShipment.get(action.shipment_id) || []).filter((plan) => plan.status === "planned").map((plan) => `<option value="${escapeHtml(plan.id)}">${escapeHtml(plan.corridor)} · ${escapeHtml(plan.route_sequence)}</option>`).join("")}</select><button class="action-button log-execute" data-action-id="${escapeHtml(action.id)}">Execute</button>`
        : "";
      return `<div class="action-row"><div><strong>${escapeHtml(action.title || action.recommendation_type)}</strong><small>${escapeHtml(action.recommendation_type)} · ${escapeHtml(action.shipment_id || "No shipment")}</small></div><div class="action-row-controls">${control}<span class="action-status status-${escapeHtml(action.status)}">${escapeHtml(action.status.replaceAll("_", " "))}</span></div></div>`;
    }).join("");
    container.querySelectorAll(".log-execute").forEach((button) => button.addEventListener("click", handleLogExecute));
  } catch (error) {
    container.innerHTML = `<div class="empty">Decision log unavailable: ${escapeHtml(error.message)}</div>`;
  }
}

async function handleLogExecute(event) {
  const button = event.currentTarget;
  const actionId = button.dataset.actionId;
  const row = button.closest(".action-row");
  const routeSelect = row.querySelector(".log-route-select");
  const vehicleSelect = row.querySelector(".log-vehicle-select");
  const payload = { status: "in_progress" };
  if (routeSelect) payload.route_plan_id = routeSelect.value;
  if (vehicleSelect) payload.vehicle_id = vehicleSelect.value;
  if (!payload.route_plan_id && !payload.vehicle_id) return;
  button.disabled = true;
  try {
    await executeAction(actionId, payload);
    await loadActions();
  } catch (error) {
    button.disabled = false;
    window.alert(error.message);
  }
}

async function loadDashboard() {
  if (!ORGANIZATION_ID) {
    document.querySelector("#insight-title").textContent = "Organization not configured";
    document.querySelector("#insight-text").textContent = "Set LOGISTICS_ORGANIZATION_ID to connect this Control Tower to an organization.";
    document.querySelector("#insight-action").textContent = "Development configuration required.";
    return;
  }

  try {
    const [overviewResponse, recommendationsResponse, vehiclesResponse] = await Promise.all([
      fetch(`${API}/api/v1/control-tower/${ORGANIZATION_ID}/overview`, { headers: headers() }),
      fetch(`${API}/api/v1/recommendations/${ORGANIZATION_ID}`, { headers: headers() }),
      fetch(`${API}/api/v1/organizations/${ORGANIZATION_ID}/vehicles`, { headers: headers() }),
    ]);
    if (!overviewResponse.ok) throw new Error(`Overview request failed: ${overviewResponse.status}`);
    if (!recommendationsResponse.ok) throw new Error(`Recommendations request failed: ${recommendationsResponse.status}`);
    if (!vehiclesResponse.ok) throw new Error(`Vehicles request failed: ${vehiclesResponse.status}`);

    vehicles = await vehiclesResponse.json();
    const recommendations = await recommendationsResponse.json();
    const rerouteShipmentIds = recommendations.shipments
      .filter((shipment) => shipment.recommendations.some((item) => item.recommendation_type === "reroute_shipment"))
      .map((shipment) => shipment.shipment_id);
    await Promise.all(rerouteShipmentIds.map(loadRoutePlans));

    renderSummary(await overviewResponse.json());
    renderRecommendations(recommendations);
    await loadActions();
  } catch (error) {
    document.querySelector("#insight-title").textContent = "Control Tower unavailable";
    document.querySelector("#insight-text").textContent = "The dashboard could not retrieve live operational data from the API.";
    document.querySelector("#insight-action").textContent = error.message;
    document.querySelector("#recommendations").innerHTML = `<div class="empty">Live recommendation queue unavailable.</div>`;
  }
}

loadDashboard();
