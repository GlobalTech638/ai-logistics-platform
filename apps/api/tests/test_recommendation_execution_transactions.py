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
                VALUES (%s, %s, 'reassign_vehicle', 'proposed', 'integration-operator')
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

    # The action must be explicitly accepted before operational execution.
    accepted = client.patch(url, json={"status": "accepted"}, headers=headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"

    # A rejected execution must leave the action and trip unchanged.
    missing_key = client.patch(
        url,
        json={"status": "in_progress", "vehicle_id": str(inactive_vehicle_id)},
        headers=headers,
    )
    assert missing_key.status_code == 428, missing_key.text

    failed = client.patch(
        url,
        json={
            "status": "in_progress",
            "vehicle_id": str(inactive_vehicle_id),
            "expected_vehicle_id": str(old_vehicle_id),
        },
        headers={**headers, "Idempotency-Key": "reassign-failure-001"},
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
            assert cur.fetchone()[0] == 1

    # A valid execution commits the trip reassignment, action state, and audit event together.
    idempotency_headers = {**headers, "Idempotency-Key": "reassign-integration-001"}
    request_body = {
        "status": "in_progress",
        "vehicle_id": str(replacement_vehicle_id),
        "expected_vehicle_id": str(old_vehicle_id),
    }
    succeeded = client.patch(url, json=request_body, headers=idempotency_headers)
    assert succeeded.status_code == 200, succeeded.text
    assert succeeded.json()["status"] == "in_progress"

    # Retrying the exact request returns the stored response without a second transition.
    replayed = client.patch(url, json=request_body, headers=idempotency_headers)
    assert replayed.status_code == 200, replayed.text
    assert replayed.json() == succeeded.json()

    # A key cannot be reused for a different payload.
    conflicting_replay = client.patch(
        url,
        json={
            "status": "in_progress",
            "vehicle_id": str(old_vehicle_id),
            "expected_vehicle_id": str(old_vehicle_id),
        },
        headers=idempotency_headers,
    )
    assert conflicting_replay.status_code == 409

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT vehicle_id FROM trips WHERE id = %s", (trip_id,))
            assert cur.fetchone()[0] == replacement_vehicle_id
            cur.execute("SELECT status FROM recommendation_actions WHERE id = %s", (action_id,))
            assert cur.fetchone()[0] == "in_progress"
            cur.execute(
                "SELECT count(*) FROM recommendation_action_events WHERE action_id = %s",
                (action_id,),
            )
            assert cur.fetchone()[0] == 2
            cur.execute(
                "SELECT count(*) FROM recommendation_action_idempotency WHERE action_id = %s",
                (action_id,),
            )
            assert cur.fetchone()[0] == 1
            cur.execute(
                """
                SELECT from_status, to_status, actor_id, event_type, details
                FROM recommendation_action_events
                WHERE action_id = %s
                ORDER BY created_at DESC, id DESC
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

    history = client.get(
        f"/api/v1/recommendations/actions/{action_id}/events",
        headers=headers,
    )
    assert history.status_code == 200, history.text
    assert history.json()["action_id"] == str(action_id)
    assert [event["to_status"] for event in history.json()["events"]] == [
        "accepted",
        "in_progress",
    ]
    assert history.json()["events"][0]["from_status"] == "proposed"
    assert history.json()["events"][0]["actor_id"] == "integration-operator"

    # Completion closes the operational loop and records a terminal audit event.
    completed = client.patch(
        url,
        json={"status": "completed", "notes": "Replacement vehicle completed dispatch"},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None

    completed_history = client.get(
        f"/api/v1/recommendations/actions/{action_id}/events",
        headers=headers,
    )
    assert completed_history.status_code == 200, completed_history.text
    assert [event["to_status"] for event in completed_history.json()["events"]] == [
        "accepted",
        "in_progress",
        "completed",
    ]

    # A completed action is terminal; it cannot be reopened.
    reopened = client.patch(
        url,
        json={"status": "in_progress"},
        headers={**headers, "Idempotency-Key": "reopen-completed-action-001"},
    )
    assert reopened.status_code == 409

    # The operator queue must expose the current assignment as a stale-write precondition.
    action_queue = client.get(
        f"/api/v1/recommendations/{organization_id}/actions",
        headers=headers,
    )
    assert action_queue.status_code == 200, action_queue.text
    queued_action = next(
        item for item in action_queue.json()["actions"] if item["id"] == str(action_id)
    )
    assert queued_action["expected_vehicle_id"] == str(replacement_vehicle_id)

    # A different action based on the old assignment must not overwrite a newer change.
    with get_connection() as conn:
        with conn.cursor() as cur:
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
            stale_action_id = cur.fetchone()[0]

    stale_execution = client.patch(
        f"/api/v1/recommendations/actions/{stale_action_id}/status",
        json={
            "status": "in_progress",
            "vehicle_id": str(old_vehicle_id),
            "expected_vehicle_id": str(old_vehicle_id),
        },
        headers={**headers, "Idempotency-Key": "reassign-stale-001"},
    )
    assert stale_execution.status_code == 409, stale_execution.text

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT vehicle_id FROM trips WHERE id = %s", (trip_id,))
            assert cur.fetchone()[0] == replacement_vehicle_id
            cur.execute(
                "SELECT status FROM recommendation_actions WHERE id = %s",
                (stale_action_id,),
            )
            assert cur.fetchone()[0] == "accepted"
            cur.execute(
                "SELECT count(*) FROM recommendation_action_events WHERE action_id = %s",
                (stale_action_id,),
            )
            assert cur.fetchone()[0] == 0
