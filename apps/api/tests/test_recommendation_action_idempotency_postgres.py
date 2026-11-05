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
def test_recommendation_action_idempotency_replays_and_rejects_key_reuse():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Recommendation idempotency {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO recommendation_actions (
                    organization_id, recommendation_type, status, acted_by
                )
                VALUES (%s, 'review_shipment', 'proposed', %s)
                RETURNING id
                """,
                (organization_id, f"test-actor-{suffix}"),
            )
            action_id = cur.fetchone()[0]

    token = issue_access_token(
        f"recommendation-operator-{suffix}", str(organization_id), "operations_manager"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"recommendation-{suffix}",
    }
    url = f"/api/v1/recommendations/actions/{action_id}/status"

    with TestClient(app) as client:
        first = client.patch(url, headers=headers, json={"status": "accepted"})
        replay = client.patch(url, headers=headers, json={"status": "accepted"})
        conflict = client.patch(
            url, headers=headers, json={"status": "rejected", "notes": "different request"}
        )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "Idempotency-Key was already used with a different request"

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
