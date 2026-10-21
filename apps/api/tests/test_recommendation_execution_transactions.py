import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.security import issue_access_token
from app.db.database import get_connection
from app.main import app


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL API integration tests",
)
def test_reassignment_failure_rolls_back_action_and_success_commits_both():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES ('Execution transaction test', 'KE', 'KES')
                RETURNING id
                """
            )
            organization_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO shipments
                    (organization_id, shipment_reference, origin, destination, weight_tonnes)
                VALUES (%s, 'TX-ROLLBACK-001', 'Nairobi', 'Mombasa', 2)
                RETURNING id
                """,
                (organization_id,),
            )
            shipment_id = cur.fetchone()[0]

            vehicle_ids = []
            for registration, active in (
                ("TX-OLD-001", True),
                ("TX-INACTIVE-001", False),
                ("TX-NEW-001", True),
            ):
                cur.execute(
                    """
                    INSERT INTO vehicles (
                        organization_id, registration_number, make, model,
                        expected_litres_per_100km, capacity_tonnes, active
                    )
                    VALUES (%s, %s, 'TestMake', 'TestModel', 20, 10, %s)
                    RETURNING id
                    """,
                    (organization_id, registration, active),
                )
                vehicle_ids.append(cur.fetchone()[0])

            old_vehicle_id, inactive_vehicle_id, replacement_vehicle_id = vehicle_ids

            cur.execute(
                """
                INSERT INTO trips (
                    organization_id, vehicle_id, shipment_id, origin, destination,
                    distance_km, planned_duration_minutes, actual_duration_minutes, load_tonnes
                )
                VALUES (%s, %s, %s, 'Nairobi', 'Mombasa', 480, 480, 500, 2)
                RETURNING id
                """,
                (organization_id, old_vehicle_id, shipment_id),
            )
            trip_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO recommendation_actions (
                    organization_id, shipment_id, recommendation_type, status, acted_by
                )
                VALUES (%s, %s, 'reassign_vehicle', 'accepted', 'integration-operator')
                RETURNING id
                """,
                (organization_id, shipment_id),
            )
            action_id = cur.fetchone()[0]

    token = issue_access_token(
        "integration-operator", str(organization_id), "operations_manager"
    )
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    url = f"/api/v1/recommendations/actions/{action_id}/status"

    # A rejected execution must leave both the action and trip unchanged.
    failed = client.patch(
        url,
        json={"status": "in_progress", "vehicle_id": str(inactive_vehicle_id)},
        headers=headers,
    )
    assert failed.status_code == 409, failed.text

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM recommendation_actions WHERE id = %s",
                (action_id,),
            )
            assert cur.fetchone()[0] == "accepted"
            cur.execute("SELECT vehicle_id FROM trips WHERE id = %s", (trip_id,))
            assert cur.fetchone()[0] == old_vehicle_id
            cur.execute(
                "SELECT count(*) FROM recommendation_action_events WHERE action_id = %s",
                (action_id,),
            )
            assert cur.fetchone()[0] == 0

    # A valid execution commits the trip reassignment, action state, and audit event together.
    succeeded = client.patch(
        url,
        json={"status": "in_progress", "vehicle_id": str(replacement_vehicle_id)},
        headers=headers,
    )
    assert succeeded.status_code == 200, succeeded.text
    assert succeeded.json()["status"] == "in_progress"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT vehicle_id FROM trips WHERE id = %s", (trip_id,))
            assert cur.fetchone()[0] == replacement_vehicle_id
            cur.execute("SELECT status FROM recommendation_actions WHERE id = %s", (action_id,))
            assert cur.fetchone()[0] == "in_progress"
            cur.execute(
                """
                SELECT from_status, to_status, actor_id, event_type, details
                FROM recommendation_action_events
                WHERE action_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (action_id,),
            )
            event = cur.fetchone()
            assert event is not None
            assert event[0:4] == (
                "accepted",
                "in_progress",
                "integration-operator",
                "operational_execution",
            )
            assert event[4]["vehicle_id"] == str(replacement_vehicle_id)
