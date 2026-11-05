import os
from concurrent.futures import ThreadPoolExecutor
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
def test_concurrent_reassignment_with_distinct_keys_executes_once():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Recommendation concurrency {suffix}",),
            )
            organization_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, capacity_tonnes, active
                ) VALUES
                    (%s, %s, 'Test', 'Original', 20, 20, TRUE),
                    (%s, %s, 'Test', 'Replacement', 20, 20, TRUE)
                RETURNING id
                """,
                (organization_id, f"ORIG-{suffix}", organization_id, f"NEW-{suffix}"),
            )
            original_vehicle_id, replacement_vehicle_id = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination, weight_tonnes
                ) VALUES (%s, %s, 'Nairobi', 'Mombasa', 5)
                RETURNING id
                """,
                (organization_id, f"SHIP-{suffix}"),
            )
            shipment_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO trips (
                    organization_id, vehicle_id, shipment_id, origin, destination,
                    distance_km, planned_duration_minutes, actual_duration_minutes, load_tonnes
                ) VALUES (%s, %s, %s, 'Nairobi', 'Mombasa', 480, 480, 480, 5)
                """,
                (organization_id, original_vehicle_id, shipment_id),
            )

            cur.execute(
                """
                INSERT INTO recommendation_actions (
                    organization_id, shipment_id, recommendation_type, status, acted_by
                ) VALUES (%s, %s, 'reassign_vehicle', 'accepted', %s)
                RETURNING id
                """,
                (organization_id, shipment_id, f"operator-{suffix}"),
            )
            action_id = cur.fetchone()[0]

    token = issue_access_token(
        f"concurrency-operator-{suffix}", str(organization_id), "operations_manager"
    )
    url = f"/api/v1/recommendations/actions/{action_id}/status"

    def execute(key: str):
        with TestClient(app) as client:
            return client.patch(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": key,
                },
                json={
                    "status": "in_progress",
                    "vehicle_id": str(replacement_vehicle_id),
                    "expected_vehicle_id": str(original_vehicle_id),
                },
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(execute, [f"request-a-{suffix}", f"request-b-{suffix}"]))

    assert sorted(response.status_code for response in responses) == [200, 409], [
        (response.status_code, response.text) for response in responses
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status FROM recommendation_actions
                WHERE id = %s AND organization_id = %s
                """,
                (action_id, organization_id),
            )
            assert cur.fetchone()[0] == "in_progress"

            cur.execute(
                """
                SELECT vehicle_id FROM trips
                WHERE organization_id = %s AND shipment_id = %s AND completed_at IS NULL
                """,
                (organization_id, shipment_id),
            )
            assert cur.fetchone()[0] == replacement_vehicle_id

            cur.execute(
                """
                SELECT count(*) FROM recommendation_action_events
                WHERE action_id = %s AND organization_id = %s
                """,
                (action_id, organization_id),
            )
            assert cur.fetchone()[0] == 1

            cur.execute(
                """
                SELECT count(*) FROM recommendation_action_idempotency
                WHERE action_id = %s AND organization_id = %s
                """,
                (action_id, organization_id),
            )
            assert cur.fetchone()[0] == 1
