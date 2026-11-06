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
def test_reassignment_rejects_vehicle_already_on_another_active_trip():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Vehicle conflict {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, capacity_tonnes, active
                ) VALUES
                    (%s, %s, 'Test', 'Source', 20, 20, TRUE),
                    (%s, %s, 'Test', 'Already assigned', 20, 20, TRUE)
                RETURNING id
                """,
                (
                    organization_id, f"SOURCE-{suffix}",
                    organization_id, f"TAKEN-{suffix}",
                ),
            )
            source_vehicle_id, occupied_vehicle_id = [row[0] for row in cur.fetchall()]

            shipment_ids = []
            for label in ("TARGET", "OCCUPIED"):
                cur.execute(
                    """
                    INSERT INTO shipments (
                        organization_id, shipment_reference, origin, destination, weight_tonnes
                    ) VALUES (%s, %s, 'Nairobi', 'Mombasa', 5)
                    RETURNING id
                    """,
                    (organization_id, f"{label}-{suffix}"),
                )
                shipment_ids.append(cur.fetchone()[0])
            target_shipment_id, occupied_shipment_id = shipment_ids

            cur.execute(
                """
                INSERT INTO trips (
                    organization_id, vehicle_id, shipment_id, origin, destination,
                    distance_km, planned_duration_minutes, actual_duration_minutes, load_tonnes
                ) VALUES
                    (%s, %s, %s, 'Nairobi', 'Mombasa', 480, 480, 480, 5),
                    (%s, %s, %s, 'Nairobi', 'Mombasa', 480, 480, 480, 5)
                """,
                (
                    organization_id, source_vehicle_id, target_shipment_id,
                    organization_id, occupied_vehicle_id, occupied_shipment_id,
                ),
            )
            cur.execute(
                """
                INSERT INTO recommendation_actions (
                    organization_id, shipment_id, recommendation_type, status, acted_by
                ) VALUES (%s, %s, 'reassign_vehicle', 'accepted', %s)
                RETURNING id
                """,
                (organization_id, target_shipment_id, f"operator-{suffix}"),
            )
            action_id = cur.fetchone()[0]

    token = issue_access_token(
        f"vehicle-conflict-{suffix}", str(organization_id), "operations_manager"
    )
    with TestClient(app) as client:
        response = client.patch(
            f"/api/v1/recommendations/actions/{action_id}/status",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"vehicle-conflict-{suffix}",
            },
            json={
                "status": "in_progress",
                "vehicle_id": str(occupied_vehicle_id),
                "expected_vehicle_id": str(source_vehicle_id),
            },
        )

    assert response.status_code == 409, response.text
    assert "already has an unfinished trip" in response.json()["detail"]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT vehicle_id FROM trips
                WHERE organization_id = %s AND shipment_id = %s AND completed_at IS NULL
                """,
                (organization_id, target_shipment_id),
            )
            assert cur.fetchone()[0] == source_vehicle_id

            cur.execute(
                """
                SELECT status FROM recommendation_actions
                WHERE id = %s AND organization_id = %s
                """,
                (action_id, organization_id),
            )
            assert cur.fetchone()[0] == "accepted"

            cur.execute(
                """
                SELECT count(*) FROM recommendation_action_events
                WHERE action_id = %s AND organization_id = %s
                """,
                (action_id, organization_id),
            )
            assert cur.fetchone()[0] == 0
