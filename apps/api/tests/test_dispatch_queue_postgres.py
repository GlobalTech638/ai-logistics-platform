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
def test_dispatch_queue_classifies_pending_shipments_and_paginates():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Dispatch queue {suffix}",),
            )
            organization_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, capacity_tonnes, active
                ) VALUES
                    (%s, %s, 'Test', 'Ready', 20, 10, TRUE),
                    (%s, %s, 'Test', 'Busy', 20, 15, TRUE)
                RETURNING id
                """,
                (
                    organization_id, f"READY-{suffix}",
                    organization_id, f"BUSY-{suffix}",
                ),
            )
            ready_vehicle_id, busy_vehicle_id = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination,
                    weight_tonnes, status
                ) VALUES
                    (%s, %s, 'Nairobi', 'Mombasa', 5, 'pending'),
                    (%s, %s, 'Nairobi', 'Kisumu', 20, 'pending'),
                    (%s, %s, 'Nairobi', 'Nakuru', 4, 'pending')
                RETURNING id
                """,
                (
                    organization_id, f"READY-LOAD-{suffix}",
                    organization_id, f"BLOCKED-LOAD-{suffix}",
                    organization_id, f"ASSIGNED-LOAD-{suffix}",
                ),
            )
            ready_shipment_id, blocked_shipment_id, assigned_shipment_id = [
                row[0] for row in cur.fetchall()
            ]

            cur.execute(
                """
                INSERT INTO trips (
                    organization_id, vehicle_id, shipment_id, origin, destination,
                    distance_km, planned_duration_minutes, actual_duration_minutes,
                    load_tonnes
                ) VALUES (%s, %s, %s, 'Nairobi', 'Kisumu', 350, 350, 350, 4)
                """,
                (organization_id, busy_vehicle_id, assigned_shipment_id),
            )

    token = issue_access_token(
        f"dispatch-queue-operator-{suffix}",
        str(organization_id),
        "operations_manager",
    )
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/operations/{organization_id}/dispatch-queue",
            headers=headers,
        )
        page = client.get(
            f"/api/v1/operations/{organization_id}/dispatch-queue?limit=1&offset=1",
            headers=headers,
        )
        empty_page = client.get(
            f"/api/v1/operations/{organization_id}/dispatch-queue?limit=1&offset=99",
            headers=headers,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_count"] == 3
    assert payload["summary"] == {"ready": 1, "blocked": 1, "assigned": 1}
    states = {item["shipment_reference"]: item["dispatch_state"] for item in payload["shipments"]}
    assert states == {
        f"READY-LOAD-{suffix}": "ready",
        f"BLOCKED-LOAD-{suffix}": "blocked",
        f"ASSIGNED-LOAD-{suffix}": "assigned",
    }

    assert page.status_code == 200, page.text
    page_payload = page.json()
    assert page_payload["total_count"] == 3
    assert len(page_payload["shipments"]) == 1
    assert page_payload["offset"] == 1

    assert empty_page.status_code == 200, empty_page.text
    empty_payload = empty_page.json()
    assert empty_payload["total_count"] == 3
    assert empty_payload["summary"] == {"ready": 1, "blocked": 1, "assigned": 1}
    assert empty_payload["shipments"] == []
