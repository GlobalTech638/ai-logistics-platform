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
def test_reassignment_rolls_back_when_audit_event_insert_fails():
    suffix = uuid4().hex[:12]
    action_id = uuid4()
    function_name = f"fail_recommendation_audit_{suffix}"
    trigger_name = f"fail_recommendation_audit_trigger_{suffix}"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Recommendation rollback {suffix}",),
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
            vehicle_ids = [row[0] for row in cur.fetchall()]
            original_vehicle_id, replacement_vehicle_id = vehicle_ids

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
                    id, organization_id, shipment_id, recommendation_type, status, acted_by
                ) VALUES (%s, %s, %s, 'reassign_vehicle', 'accepted', %s)
                """,
                (action_id, organization_id, shipment_id, f"operator-{suffix}"),
            )

            cur.execute(
                f"""
                CREATE FUNCTION {function_name}() RETURNS trigger AS $$
                BEGIN
                    IF NEW.action_id = '{action_id}'::uuid THEN
                        RAISE EXCEPTION 'forced audit persistence failure';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
                """
            )
            cur.execute(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE INSERT ON recommendation_action_events
                FOR EACH ROW EXECUTE FUNCTION {function_name}()
                """
            )

    token = issue_access_token(
        f"rollback-operator-{suffix}", str(organization_id), "operations_manager"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"rollback-{suffix}",
    }
    url = f"/api/v1/recommendations/actions/{action_id}/status"

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.patch(
                url,
                headers=headers,
                json={
                    "status": "in_progress",
                    "vehicle_id": str(replacement_vehicle_id),
                    "expected_vehicle_id": str(original_vehicle_id),
                },
            )

        assert response.status_code == 500

        with get_connection() as conn:
            with conn.cursor() as cur:
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
                    SELECT vehicle_id FROM trips
                    WHERE organization_id = %s AND shipment_id = %s AND completed_at IS NULL
                    """,
                    (organization_id, shipment_id),
                )
                assert cur.fetchone()[0] == original_vehicle_id

                cur.execute(
                    """
                    SELECT count(*) FROM recommendation_action_events
                    WHERE action_id = %s AND organization_id = %s
                    """,
                    (action_id, organization_id),
                )
                assert cur.fetchone()[0] == 0

                cur.execute(
                    """
                    SELECT count(*) FROM recommendation_action_idempotency
                    WHERE action_id = %s AND organization_id = %s
                    """,
                    (action_id, organization_id),
                )
                assert cur.fetchone()[0] == 0
    finally:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DROP TRIGGER IF EXISTS {trigger_name} ON recommendation_action_events"
                )
                cur.execute(f"DROP FUNCTION IF EXISTS {function_name}()")
