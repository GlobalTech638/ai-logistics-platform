(() => {
  const api = window.LOGISTICS_API_URL || "http://localhost:8000";
  const organizationId = window.LOGISTICS_ORGANIZATION_ID || "";
  const role = window.LOGISTICS_USER_ROLE || "viewer";
  const canExecute = ["admin", "operations_manager", "fleet_manager"].includes(role);
  const headers = () => ({
    "Content-Type": "application/json",
    "Authorization": "Bearer " + (window.LOGISTICS_ACCESS_TOKEN || ""),
    "X-Organization-Id": organizationId,
    "X-User-Id": window.LOGISTICS_USER_ID || "dashboard-user",
    "X-User-Role": role
  });
  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  async function loadQueue() {
    const list = document.querySelector("#dispatch-queue");
    const summary = document.querySelector("#dispatch-summary");
    if (!list || !summary) return;
    if (!organizationId) {
      list.innerHTML = '<div class="empty">Configure an organization to load dispatch work.</div>';
      return;
    }
    try {
      const response = await fetch(api + "/api/v1/operations/" + organizationId + "/dispatch-queue", { headers: headers() });
      if (!response.ok) throw new Error("Queue request failed (" + response.status + ")");
      const data = await response.json();
      summary.innerHTML = [
        ["ready", data.summary.ready], ["assigned", data.summary.assigned],
        ["blocked", data.summary.blocked], ["pending", data.total_count]
      ].map(([label, count]) => '<span><strong>' + count + '</strong> ' + label + '</span>').join("");
      list.innerHTML = data.shipments.length ? data.shipments.map((item) => {
        const actions = item.dispatch_state === "ready" && canExecute
          ? '<button class="action-button dispatch-candidates" type="button">Find vehicle</button><select class="dispatch-select" disabled aria-label="Eligible vehicle"><option value="">Load candidates</option></select><button class="action-button dispatch-submit" type="button" disabled>Assign</button>'
          : '<small>' + (item.dispatch_state === "assigned" ? "Vehicle reserved" : item.dispatch_state === "blocked" ? "No eligible vehicle" : "Read-only access") + '</small>';
        return '<article class="dispatch-row" data-shipment-id="' + escapeHtml(item.shipment_id) + '">' +
          '<div class="dispatch-main"><strong>' + escapeHtml(item.shipment_reference) + '</strong>' +
          '<small>' + escapeHtml(item.origin) + ' → ' + escapeHtml(item.destination) + ' · ' + item.weight_tonnes + ' t</small></div>' +
          '<span class="dispatch-state state-' + escapeHtml(item.dispatch_state) + '">' + escapeHtml(item.dispatch_state) + '</span>' +
          '<div class="dispatch-actions">' + actions + '</div><small class="dispatch-feedback" aria-live="polite"></small></article>';
      }).join("") : '<div class="empty">No pending shipments.</div>';
      list.querySelectorAll(".dispatch-candidates").forEach((button) => button.addEventListener("click", findCandidates));
      list.querySelectorAll(".dispatch-submit").forEach((button) => button.addEventListener("click", assignVehicle));
    } catch (error) {
      summary.textContent = "";
      list.innerHTML = '<div class="empty">Dispatch queue unavailable: ' + escapeHtml(error.message) + '</div>';
    }
  }

  async function findCandidates(event) {
    const row = event.currentTarget.closest(".dispatch-row");
    const select = row.querySelector(".dispatch-select");
    const feedback = row.querySelector(".dispatch-feedback");
    event.currentTarget.disabled = true;
    feedback.textContent = "Ranking available vehicles…";
    try {
      const response = await fetch(api + "/api/v1/operations/" + organizationId + "/shipments/" + row.dataset.shipmentId + "/dispatch-candidates", { headers: headers() });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Candidate lookup failed");
      select.innerHTML = data.candidates.length
        ? '<option value="">Select vehicle</option>' + data.candidates.map((vehicle) =>
            '<option value="' + escapeHtml(vehicle.vehicle_id) + '">' + escapeHtml(vehicle.registration_number) + ' · score ' + vehicle.score + '</option>'
          ).join("")
        : '<option value="">No eligible vehicles</option>';
      select.disabled = !data.candidates.length;
      row.querySelector(".dispatch-submit").disabled = !data.candidates.length;
      feedback.textContent = data.eligible_vehicle_count + " eligible vehicles.";
    } catch (error) {
      feedback.textContent = error.message;
      event.currentTarget.disabled = false;
    }
  }

  async function assignVehicle(event) {
    const row = event.currentTarget.closest(".dispatch-row");
    const select = row.querySelector(".dispatch-select");
    const feedback = row.querySelector(".dispatch-feedback");
    if (!select.value) { feedback.textContent = "Select a vehicle first."; return; }
    event.currentTarget.disabled = true;
    try {
      const response = await fetch(api + "/api/v1/operations/" + organizationId + "/shipments/" + row.dataset.shipmentId + "/assign-vehicle", {
        method: "POST",
        headers: Object.assign({}, headers(), { "Idempotency-Key": crypto.randomUUID() }),
        body: JSON.stringify({ vehicle_id: select.value })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Assignment failed");
      feedback.textContent = "Assigned " + data.registration_number + ".";
      await loadQueue();
    } catch (error) {
      feedback.textContent = error.message;
      event.currentTarget.disabled = false;
    }
  }

  document.querySelector("#dispatch-refresh")?.addEventListener("click", loadQueue);
  loadQueue();
})();
