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
  const commandHeaders = (key) => Object.assign({}, headers(), { "Idempotency-Key": key });
  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");


  async function loadTimeline(event) {
    const row = event.currentTarget.closest("[data-shipment-id]");
    const panel = document.querySelector("#timeline-panel");
    const list = document.querySelector("#shipment-timeline");
    const title = document.querySelector("#timeline-title");
    if (!row || !panel || !list) return;
    panel.hidden = false;
    list.innerHTML = '<div class="empty">Loading shipment history…</div>';
    title.textContent = "Shipment timeline";
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    try {
      const response = await fetch(
        api + "/api/v1/operations/" + organizationId + "/shipments/" +
        encodeURIComponent(row.dataset.shipmentId) + "/timeline",
        { headers: headers() }
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Timeline request failed");
      title.textContent = data.shipment_reference + " · " + data.status.replaceAll("_", " ");
      list.innerHTML = data.events.length ? data.events.map((item) =>
        '<article class="timeline-event">' +
          '<span class="timeline-marker" aria-hidden="true"></span>' +
          '<div><strong>' + escapeHtml(item.event_type.replaceAll("_", " ")) + '</strong>' +
          '<small>' + escapeHtml(new Date(item.occurred_at).toLocaleString()) +
          (item.actor_id ? " · " + escapeHtml(item.actor_id) : " · historical record") + '</small>' +
          '<small>' + escapeHtml(Object.entries(item.details || {}).filter(([key]) => key !== "legacy_event")
            .map(([key, value]) => key.replaceAll("_", " ") + ": " + value).join(" · ")) + '</small></div>' +
        '</article>'
      ).join("") : '<div class="empty">No shipment events have been recorded.</div>';
    } catch (error) {
      list.innerHTML = '<div class="empty">Shipment history unavailable: ' + escapeHtml(error.message) + '</div>';
    }
  }

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
        let actions;
        if (item.dispatch_state === "ready" && canExecute) {
          actions = '<button class="action-button dispatch-candidates" type="button">Find vehicle</button>' +
            '<select class="dispatch-select" disabled aria-label="Eligible vehicle"><option value="">Load candidates</option></select>' +
            '<button class="action-button dispatch-submit" type="button" disabled>Assign</button>';
        } else if (item.dispatch_state === "assigned" && canExecute && item.assignment_id) {
          actions = '<div class="trip-start-fields">' +
            '<small>Reserved: ' + escapeHtml(item.assigned_registration_number || "vehicle") + '</small>' +
            '<input class="trip-distance" type="number" min="0.1" step="0.1" placeholder="Planned km" aria-label="Planned distance in kilometres">' +
            '<input class="trip-duration" type="number" min="1" step="1" placeholder="Planned minutes" aria-label="Planned duration in minutes">' +
            '<input class="trip-start-odometer" type="number" min="0" step="0.1" value="' + escapeHtml(item.assigned_vehicle_odometer_km ?? "") + '" aria-label="Start odometer kilometres">' +
            '<button class="action-button trip-start" type="button">Start trip</button></div>';
        } else {
          actions = '<small>' + (item.dispatch_state === "assigned" ? "Vehicle reserved" : item.dispatch_state === "blocked" ? "No eligible vehicle" : "Read-only access") + '</small>';
        }
        return '<article class="dispatch-row" data-shipment-id="' + escapeHtml(item.shipment_id) + '">' +
          '<div class="dispatch-main"><strong>' + escapeHtml(item.shipment_reference) + '</strong>' +
          '<small>' + escapeHtml(item.origin) + ' → ' + escapeHtml(item.destination) + ' · ' + item.weight_tonnes + ' t</small></div>' +
          '<span class="dispatch-state state-' + escapeHtml(item.dispatch_state) + '">' + escapeHtml(item.dispatch_state) + '</span>' +
          '<div class="dispatch-actions">' + actions + '<button class="action-button shipment-timeline" type="button">Timeline</button></div>' +
          '<small class="dispatch-feedback" aria-live="polite"></small></article>';
      }).join("") : '<div class="empty">No pending shipments.</div>';
      list.querySelectorAll(".dispatch-candidates").forEach((button) => button.addEventListener("click", findCandidates));
      list.querySelectorAll(".dispatch-submit").forEach((button) => button.addEventListener("click", assignVehicle));
      list.querySelectorAll(".trip-start").forEach((button) => button.addEventListener("click", startTrip));
      list.querySelectorAll(".shipment-timeline").forEach((button) => button.addEventListener("click", loadTimeline));
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
        headers: commandHeaders(crypto.randomUUID()),
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

  async function startTrip(event) {
    const row = event.currentTarget.closest(".dispatch-row");
    const feedback = row.querySelector(".dispatch-feedback");
    const distance = Number(row.querySelector(".trip-distance").value);
    const duration = Number(row.querySelector(".trip-duration").value);
    const odometer = Number(row.querySelector(".trip-start-odometer").value);
    if (!(distance > 0) || !(duration > 0) || !(odometer >= 0)) {
      feedback.textContent = "Enter a positive planned distance, planned duration, and valid start odometer.";
      return;
    }
    event.currentTarget.disabled = true;
    feedback.textContent = "Starting trip…";
    try {
      const response = await fetch(api + "/api/v1/operations/" + organizationId + "/shipments/" + row.dataset.shipmentId + "/start-trip", {
        method: "POST",
        headers: commandHeaders(crypto.randomUUID()),
        body: JSON.stringify({
          planned_distance_km: distance,
          planned_duration_minutes: Math.round(duration),
          start_odometer_km: odometer
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Trip start failed");
      feedback.textContent = "Trip started at " + data.started_at + ".";
      await loadQueue();
      await loadActiveTrips();
    } catch (error) {
      feedback.textContent = error.message;
      event.currentTarget.disabled = false;
    }
  }

  async function loadActiveTrips() {
    const list = document.querySelector("#active-trips");
    if (!list) return;
    if (!organizationId) {
      list.innerHTML = '<div class="empty">Configure an organization to load active trips.</div>';
      return;
    }
    try {
      const response = await fetch(api + "/api/v1/operations/" + organizationId + "/active-trips", { headers: headers() });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Active trip lookup failed");
      list.innerHTML = data.trips.length ? data.trips.map((trip) =>
        '<article class="dispatch-row active-trip-row" data-trip-id="' + escapeHtml(trip.trip_id) + '" data-shipment-id="' + escapeHtml(trip.shipment_id) + '">' +
          '<div class="dispatch-main"><strong>' + escapeHtml(trip.shipment_reference) + '</strong>' +
          '<small>' + escapeHtml(trip.registration_number) + ' · ' + escapeHtml(trip.origin) + ' → ' + escapeHtml(trip.destination) + '</small>' +
          '<small>Started ' + escapeHtml(trip.started_at) + ' · start odometer ' + escapeHtml(trip.start_odometer_km) + ' km</small></div>' +
          '<span class="dispatch-state state-in_progress">in transit</span>' +
          '<div class="dispatch-actions">' +
            (canExecute
              ? '<input class="trip-end-odometer" type="number" min="0" step="0.1" value="' + escapeHtml(trip.current_odometer_km) + '" aria-label="End odometer kilometres">' +
                '<button class="action-button trip-complete" type="button">Complete trip</button>' +
                '<button class="action-button shipment-timeline" type="button">Timeline</button>'
              : '<small>Read-only access</small>') +
          '</div><small class="dispatch-feedback" aria-live="polite"></small></article>'
      ).join("") : '<div class="empty">No trips are currently in transit.</div>';
      list.querySelectorAll(".trip-complete").forEach((button) => button.addEventListener("click", completeTrip));
      list.querySelectorAll(".shipment-timeline").forEach((button) => button.addEventListener("click", loadTimeline));
    } catch (error) {
      list.innerHTML = '<div class="empty">Active trips unavailable: ' + escapeHtml(error.message) + '</div>';
    }
  }

  async function completeTrip(event) {
    const row = event.currentTarget.closest(".active-trip-row");
    const feedback = row.querySelector(".dispatch-feedback");
    const endOdometer = Number(row.querySelector(".trip-end-odometer").value);
    if (!(endOdometer >= 0)) { feedback.textContent = "Enter a valid end odometer."; return; }
    event.currentTarget.disabled = true;
    feedback.textContent = "Recording measured completion…";
    try {
      const response = await fetch(api + "/api/v1/operations/" + organizationId + "/shipments/" + row.dataset.shipmentId + "/trips/" + row.dataset.tripId + "/complete", {
        method: "POST",
        headers: commandHeaders(crypto.randomUUID()),
        body: JSON.stringify({ end_odometer_km: endOdometer })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Trip completion failed");
      feedback.textContent = "Delivered · " + data.actual_distance_km + " km · " + data.actual_duration_minutes + " min.";
      await loadQueue();
      await loadActiveTrips();
    } catch (error) {
      feedback.textContent = error.message;
      event.currentTarget.disabled = false;
    }
  }

  document.querySelector("#timeline-close")?.addEventListener("click", () => {
    document.querySelector("#timeline-panel").hidden = true;
  });
  document.querySelector("#dispatch-refresh")?.addEventListener("click", loadQueue);
  document.querySelector("#trips-refresh")?.addEventListener("click", loadActiveTrips);
  loadQueue();
  loadActiveTrips();
})();
