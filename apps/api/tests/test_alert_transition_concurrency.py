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
def test_concurrent_alert_acknowledgements_allow_only_one_transition():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Alert lock integration {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO alerts (
                    organization_id, alert_type, severity, message, status
                )
                VALUES (%s, 'integration_test', 'low', 'Concurrent transition test', 'open')
                RETURNING id
                """,
                (organization_id,),
            )
            alert_id = cur.fetchone()[0]

    token = issue_access_token(
        f"alert-operator-{suffix}", str(organization_id), "operations_manager"
    )
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/alerts/{alert_id}/status"

    def acknowledge():
        with TestClient(app) as client:
            return client.patch(url, params={"status": "acknowledged"}, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: acknowledge(), range(2)))

    assert sorted(response.status_code for response in responses) == [200, 409]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM alerts WHERE id = %s", (alert_id,))
            assert cur.fetchone()[0] == "acknowledged"
