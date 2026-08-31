const API = window.LOGISTICS_API_URL || "http://localhost:8000";
const ORGANIZATION_ID = window.LOGISTICS_ORGANIZATION_ID || "";

const money = (value) => `KES ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

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

async function loadDashboard() {
  if (!ORGANIZATION_ID) {
    document.querySelector("#insight-title").textContent = "Organization not configured";
    document.querySelector("#insight-text").textContent = "Set LOGISTICS_ORGANIZATION_ID to connect this Control Tower to an organization.";
    document.querySelector("#insight-action").textContent = "Development configuration required.";
    return;
  }

  try {
    const response = await fetch(`${API}/api/v1/control-tower/${ORGANIZATION_ID}/overview`, {
      headers: {
        "X-Organization-Id": ORGANIZATION_ID,
        "X-User-Id": window.LOGISTICS_USER_ID || "dashboard-user",
        "X-User-Role": window.LOGISTICS_USER_ROLE || "viewer",
      },
    });
    if (!response.ok) throw new Error(`API request failed: ${response.status}`);
    renderSummary(await response.json());
  } catch (error) {
    document.querySelector("#insight-title").textContent = "Control Tower unavailable";
    document.querySelector("#insight-text").textContent = "The dashboard could not retrieve live operational data from the API.";
    document.querySelector("#insight-action").textContent = "Check the API, database, organization ID, and tenant credentials.";
  }
}

loadDashboard();
