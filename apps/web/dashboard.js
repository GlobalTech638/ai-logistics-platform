const API = window.LOGISTICS_API_URL || "http://localhost:8000";

const money = (value, currency = "KES") =>
  `${currency} ${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

async function loadControlTower() {
  const [fleetResponse, corridorResponse] = await Promise.all([
    fetch(`${API}/api/v1/analytics/fleet/summary`),
    fetch(`${API}/api/v1/analytics/corridors`),
  ]);

  if (!fleetResponse.ok || !corridorResponse.ok) {
    throw new Error("Unable to load control tower data");
  }

  return {
    fleet: await fleetResponse.json(),
    corridors: await corridorResponse.json(),
  };
}

function render(data) {
  const fleet = data.fleet;
  const topCorridor = data.corridors[0];

  document.querySelector("#metrics").innerHTML += `
    <div class="metric"><p class="eyebrow">AVG VARIANCE</p><div class="metric-value">${fleet.average_variance_percent}%</div></div>`;

  if (topCorridor) {
    document.querySelector("#insight-title").textContent = topCorridor.corridor;
    document.querySelector("#insight-text").textContent =
      `${topCorridor.trip_count} trips show an average delay of ${topCorridor.average_delay_percent}%. ${topCorridor.delayed_trip_count} trips exceeded the monitoring threshold.`;
    document.querySelector("#insight-action").textContent = topCorridor.recommendation;
  }

  document.querySelector("#corridors").innerHTML = data.corridors.map((item) => `
    <div class="vehicle">
      <div><div class="vehicle-id">${item.corridor}</div><small>${item.trip_count} trips · ${item.delayed_trip_count} delayed</small></div>
      <div class="risk">${item.risk}</div>
      <div class="cost">${item.average_delay_percent}% delay</div>
    </div>
  `).join("");
}

loadControlTower().then(render).catch(() => {
  document.querySelector("#insight-title").textContent = "Control tower offline";
  document.querySelector("#insight-text").textContent = "Start the FastAPI service to load fleet and corridor intelligence.";
  document.querySelector("#insight-action").textContent = "API: http://localhost:8000";
});
