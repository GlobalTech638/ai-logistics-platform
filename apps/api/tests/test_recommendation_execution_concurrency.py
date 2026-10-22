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
def test_concurrent_identical_reassignment_retries_commit_once():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES')
                RETURNING id
                """,
                (f"Concurrent idempotency {suffix}",),
            )
            organization_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO shipments
                    (organization_id, shipment_reference, origin, destination, weight_tonnes)
                VALUES (%s, %s, 'Nairobi', 'Mombasa', 2)
                RETURNING id
                """,
                (organization_id, f"CONCURRENT-{suffix}"),
            )
            shipment_id = cur.fetchone()[0]

            vehicle_ids = []
            for registration in (f"OLD-{suffix}", f"NEW-{suffix}"):
                cur.execute(
                    """
                    INSERT INTO vehicles (
                        organization_id, registration_number, make, model,
                        expected_litres_per_100km, capacity_tonnes, active
                    )
                    VALUES (%s, %s, 'TestMake', 'TestModel', 20, 10, TRUE)
                    RETURNING id
                    """,
                    (organization_id, registration),
                )
                vehicle_ids.append(cur.fetchone()[0])
            old_vehicle_id, replacement_vehicle_id = vehicle_ids

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
                VALUES (%s, %s, 'reassign_vehicle', 'accepted', 'concurrency-operator')
                RETURNING id
                """,
                (organization_id, shipment_id),
            )
            action_id = cur.fetchone()[0]

    token = issue_access_token(
        "concurrency-operator", str(organization_id), "operations_manager"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"concurrent-reassign-{suffix}",
    }
    body = {
        "status": "in_progress",
        "vehicle_id": str(replacement_vehicle_id),
        "expected_vehicle_id": str(old_vehicle_id),
    }
    url = f"/api/v1/recommendations/actions/{action_id}/status"

    def submit_request():
        with TestClient(app) as client:
            return client.patch(url, json=body, headers=headers)

    # Two independent HTTP clients simulate simultaneous duplicate delivery.
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit_request(), range(2)))

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT vehicle_id FROM trips WHERE id = %s", (trip_id,))
            assert cur.fetchone()[0] == replacement_vehicle_id

            cur.execute(
                "SELECT status FROM recommendation_actions WHERE id = %s",
                (action_id,),
            )
            assert cur.fetchone()[0] == "in_progress"

            cur.execute(
                "SELECT count(*) FROM recommendation_action_events WHERE action_id = %s",
                (action_id,),
            )
            assert cur.fetchone()[0] == 1

            cur.execute(
                "SELECT count(*) FROM recommendation_action_idempotency WHERE action_id = %s",
                (action_id,),
            )
            assert cur.fetchone()[0] == 1
