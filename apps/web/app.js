const API = window.LOGISTICS_API_URL || "http://localhost:8000";

const money = (value) => `KES ${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

function renderSummary(data) {
  document.querySelector("#metrics").innerHTML = `
    <div class="metric"><p class="eyebrow">VEHICLES</p><div class="metric-value">${data.vehicle_count}</div></div>
    <div class="metric"><p class="eyebrow">FUEL SPEND</p><div class="metric-value">${money(data.total_fuel_cost)}</div></div>
    <div class="metric"><p class="eyebrow">EST. EXCESS COST</p><div class="metric-value">${money(data.total_estimated_excess_cost)}</div></div>`;

  document.querySelector("#insight-text").textContent =
    `${data.critical_count} critical and ${data.high_risk_count} high-risk vehicles require attention. Average fuel-efficiency variance is ${data.average_variance_percent}%.`;
  document.querySelector("#insight-action").textContent =
    data.total_estimated_excess_cost > 0 ? "Recommended action: investigate the highest-cost vehicles first." : "No immediate fuel-cost intervention detected.";
}

async function loadDashboard() {
  try {
    const response = await fetch(`${API}/api/v1/analytics/fleet/summary`);
    if (!response.ok) throw new Error("API request failed");
    const data = await response.json();
    renderSummary(data);
  } catch (error) {
    document.querySelector("#insight-title").textContent = "API unavailable";
    document.querySelector("#insight-text").textContent = "Start the FastAPI service to load live fleet intelligence.";
    document.querySelector("#insight-action").textContent = "Expected API: http://localhost:8000";
  }
}

loadDashboard();
