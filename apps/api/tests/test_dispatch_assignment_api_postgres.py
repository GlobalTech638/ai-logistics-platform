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
def test_dispatch_assignment_is_idempotent_and_reserves_vehicle():
    suffix = uuid4().hex[:10]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Dispatch API {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, capacity_tonnes, active
                ) VALUES
                    (%s, %s, 'Test', 'Truck', 20, 10, TRUE),
                    (%s, %s, 'Test', 'Truck', 20, 10, TRUE)
                RETURNING id
                """,
                (
                    organization_id, f"DISPATCH-A-{suffix}",
                    organization_id, f"DISPATCH-B-{suffix}",
                ),
            )
            first_vehicle_id, second_vehicle_id = [row[0] for row in cur.fetchall()]
            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination,
                    weight_tonnes, status
                ) VALUES
                    (%s, %s, 'Nairobi', 'Mombasa', 4, 'pending'),
                    (%s, %s, 'Nairobi', 'Kisumu', 5, 'pending')
                RETURNING id
                """,
                (
                    organization_id, f"LOAD-A-{suffix}",
                    organization_id, f"LOAD-B-{suffix}",
                ),
            )
            first_shipment_id, second_shipment_id = [row[0] for row in cur.fetchall()]

    token = issue_access_token(
        f"dispatch-api-operator-{suffix}", str(organization_id), "operations_manager"
    )
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": f"dispatch-{suffix}"}
    base = f"/api/v1/operations/{organization_id}"
    with TestClient(app) as client:
        missing_key = client.post(
            f"{base}/shipments/{first_shipment_id}/assign-vehicle",
            json={"vehicle_id": str(first_vehicle_id)},
            headers={"Authorization": headers["Authorization"]},
        )
        first = client.post(
            f"{base}/shipments/{first_shipment_id}/assign-vehicle",
            json={"vehicle_id": str(first_vehicle_id)},
            headers=headers,
        )
        replay = client.post(
            f"{base}/shipments/{first_shipment_id}/assign-vehicle",
            json={"vehicle_id": str(first_vehicle_id)},
            headers=headers,
        )
        conflicting_key = client.post(
            f"{base}/shipments/{first_shipment_id}/assign-vehicle",
            json={"vehicle_id": str(second_vehicle_id)},
            headers=headers,
        )
        vehicle_reserved = client.post(
            f"{base}/shipments/{second_shipment_id}/assign-vehicle",
            json={"vehicle_id": str(first_vehicle_id)},
            headers={**headers, "Idempotency-Key": f"other-{suffix}"},
        )
        queue = client.get(f"{base}/dispatch-queue", headers=headers)
        candidates = client.get(
            f"{base}/shipments/{second_shipment_id}/dispatch-candidates",
            headers=headers,
        )

    assert missing_key.status_code == 428, missing_key.text
    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert conflicting_key.status_code == 409, conflicting_key.text
    assert vehicle_reserved.status_code == 409, vehicle_reserved.text
    assert queue.status_code == 200, queue.text
    queue_states = {item["shipment_reference"]: item["dispatch_state"] for item in queue.json()["shipments"]}
    assert queue_states == {
        f"LOAD-A-{suffix}": "assigned",
        f"LOAD-B-{suffix}": "ready",
    }
    assert candidates.status_code == 200, candidates.text
    assert [item["vehicle_id"] for item in candidates.json()["candidates"]] == [str(second_vehicle_id)]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM shipment_vehicle_assignments
                WHERE organization_id = %s AND shipment_id = %s AND released_at IS NULL
                """,
                (organization_id, first_shipment_id),
            )
            assert cur.fetchone()[0] == 1
            cur.execute(
                "SELECT COUNT(*) FROM trips WHERE organization_id = %s AND shipment_id = %s",
                (organization_id, first_shipment_id),
            )
            assert cur.fetchone()[0] == 0
