import os
from datetime import datetime, timedelta, timezone
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
def test_control_tower_surfaces_missed_pickups_overdue_and_due_soon_shipments():
    suffix = uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"SLA exceptions {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            fixtures = [
                (f"MISSED-{suffix}", "pending", now - timedelta(hours=1), None),
                (f"OVERDUE-{suffix}", "in_transit", None, now - timedelta(minutes=30)),
                (f"DUE-{suffix}", "pending", None, now + timedelta(minutes=90)),
                (f"SAFE-{suffix}", "pending", None, now + timedelta(days=1)),
            ]
            for reference, status, pickup_at, delivery_at in fixtures:
                cur.execute(
                    """
                    INSERT INTO shipments (
                        organization_id, shipment_reference, origin, destination,
                        weight_tonnes, pickup_at, delivery_at, status
                    ) VALUES (%s, %s, 'Nairobi', 'Mombasa', 4, %s, %s, %s)
                    """,
                    (organization_id, reference, pickup_at, delivery_at, status),
                )

    token = issue_access_token(
        f"sla-operator-{suffix}", str(organization_id), "operations_manager"
    )
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        exceptions = client.get(
            f"/api/v1/control-tower/{organization_id}/shipment-exceptions",
            headers=headers,
        )
        overview = client.get(
            f"/api/v1/control-tower/{organization_id}/overview",
            headers=headers,
        )

    assert exceptions.status_code == 200, exceptions.text
    by_reference = {
        item["shipment_reference"]: item
        for item in exceptions.json()["exceptions"]
    }
    assert by_reference[f"MISSED-{suffix}"]["exception_type"] == "missed_pickup"
    assert by_reference[f"OVERDUE-{suffix}"]["exception_type"] == "overdue_delivery"
    assert by_reference[f"DUE-{suffix}"]["exception_type"] == "delivery_due_soon"
    assert f"SAFE-{suffix}" not in by_reference

    assert overview.status_code == 200, overview.text
    assert overview.json()["shipments"]["overdue_deliveries"] == 1
    assert overview.json()["shipments"]["due_soon"] == 1
    assert overview.json()["shipments"]["missed_pickups"] == 1
