import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.security import issue_access_token
from app.db.database import get_connection
from app.main import app


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL API integration tests",
)
def test_trip_start_and_completion_are_idempotent_and_release_vehicle():
    suffix = uuid4().hex[:10]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Trip lifecycle {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, capacity_tonnes, odometer_km, active
                ) VALUES (%s, %s, 'Test', 'Truck', 20, 12, 1000, TRUE)
                RETURNING id
                """,
                (organization_id, f"TRIP-{suffix}"),
            )
            vehicle_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination,
                    weight_tonnes, status
                ) VALUES (%s, %s, 'Nairobi', 'Mombasa', 8, 'pending')
                RETURNING id
                """,
                (organization_id, f"TRIP-LOAD-{suffix}"),
            )
            shipment_id = cur.fetchone()[0]

    token = issue_access_token(
        f"trip-operator-{suffix}", str(organization_id), "operations_manager"
    )
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/operations/{organization_id}"
    with TestClient(app) as client:
        assignment = client.post(
            f"{base}/shipments/{shipment_id}/assign-vehicle",
            json={"vehicle_id": str(vehicle_id)},
            headers={**headers, "Idempotency-Key": f"assign-{suffix}"},
        )
        start_url = f"{base}/shipments/{shipment_id}/start-trip"
        start_payload = {
            "planned_distance_km": 485,
            "planned_duration_minutes": 420,
            "start_odometer_km": 1000,
        }
        missing_start_key = client.post(start_url, json=start_payload, headers=headers)
        started = client.post(
            start_url,
            json=start_payload,
            headers={**headers, "Idempotency-Key": f"start-{suffix}"},
        )
        start_replay = client.post(
            start_url,
            json=start_payload,
            headers={**headers, "Idempotency-Key": f"start-{suffix}"},
        )
        complete_url = (
            f"{base}/shipments/{shipment_id}/trips/{started.json()['trip_id']}/complete"
        )
        complete_payload = {"end_odometer_km": 1150}
        missing_complete_key = client.post(
            complete_url, json=complete_payload, headers=headers
        )
        completed = client.post(
            complete_url,
            json=complete_payload,
            headers={**headers, "Idempotency-Key": f"complete-{suffix}"},
        )
        complete_replay = client.post(
            complete_url,
            json=complete_payload,
            headers={**headers, "Idempotency-Key": f"complete-{suffix}"},
        )
        candidates_after_completion = client.get(
            f"{base}/shipments/{shipment_id}/dispatch-candidates",
            headers=headers,
        )
        timeline = client.get(
            f"{base}/shipments/{shipment_id}/timeline",
            headers=headers,
        )

    assert assignment.status_code == 200, assignment.text
    assert missing_start_key.status_code == 428, missing_start_key.text
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"
    assert start_replay.status_code == 200, start_replay.text
    assert start_replay.json() == started.json()
    assert missing_complete_key.status_code == 428, missing_complete_key.text
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["actual_distance_km"] == 150
    assert completed.json()["actual_duration_minutes"] >= 1
    assert complete_replay.status_code == 200, complete_replay.text
    assert complete_replay.json() == completed.json()
    assert candidates_after_completion.status_code == 200, candidates_after_completion.text
    assert [item["vehicle_id"] for item in candidates_after_completion.json()["candidates"]] == [str(vehicle_id)]
    assert timeline.status_code == 200, timeline.text
    assert [event["event_type"] for event in timeline.json()["events"]] == [
        "vehicle_assigned", "trip_started", "trip_completed"
    ]
    assert timeline.json()["status"] == "delivered"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status FROM shipments
                WHERE organization_id = %s AND id = %s
                """,
                (organization_id, shipment_id),
            )
            assert cur.fetchone()[0] == "delivered"
            cur.execute(
                """
                SELECT completed_at, actual_distance_km, actual_duration_minutes,
                       start_odometer_km, end_odometer_km, completed_by
                FROM trips
                WHERE organization_id = %s AND shipment_id = %s
                """,
                (organization_id, shipment_id),
            )
            trip = cur.fetchone()
            assert trip[0] is not None
            assert float(trip[1]) == 150
            assert trip[2] >= 1
            assert float(trip[3]) == 1000
            assert float(trip[4]) == 1150
            assert trip[5] == f"trip-operator-{suffix}"
            cur.execute(
                """
                SELECT odometer_km FROM vehicles
                WHERE organization_id = %s AND id = %s
                """,
                (organization_id, vehicle_id),
            )
            assert float(cur.fetchone()[0]) == 1150
            cur.execute(
                """
                SELECT released_at, released_by, release_reason
                FROM shipment_vehicle_assignments
                WHERE organization_id = %s AND shipment_id = %s
                """,
                (organization_id, shipment_id),
            )
            release = cur.fetchone()
            assert release[0] is not None
            assert release[1] == f"trip-operator-{suffix}"
            assert release[2] == "trip_completed"
            cur.execute(
                """
                SELECT event_type FROM trip_events
                WHERE organization_id = %s AND trip_id = %s
                ORDER BY created_at, event_type
                """,
                (organization_id, started.json()["trip_id"]),
            )
            assert {row[0] for row in cur.fetchall()} == {"started", "completed"}
