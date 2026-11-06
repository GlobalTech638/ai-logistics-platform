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
def test_control_tower_overview_uses_persisted_fleet_and_alert_state():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Control Tower overview {suffix}",),
            )
            organization_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, active
                ) VALUES
                    (%s, %s, 'Test', 'Active', 20, TRUE),
                    (%s, %s, 'Test', 'Inactive', 20, FALSE)
                """,
                (organization_id, f"ACTIVE-{suffix}", organization_id, f"INACTIVE-{suffix}"),
            )

            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination,
                    weight_tonnes, status
                ) VALUES
                    (%s, %s, 'Nairobi', 'Mombasa', 5, 'in_transit'),
                    (%s, %s, 'Nairobi', 'Kisumu', 3, 'delivered')
                """,
                (organization_id, f"ACTIVE-SHIP-{suffix}", organization_id, f"DONE-SHIP-{suffix}"),
            )

            cur.execute(
                """
                INSERT INTO alerts (
                    organization_id, alert_type, severity, message, status
                ) VALUES
                    (%s, 'integration', 'critical', 'Critical test alert', 'open'),
                    (%s, 'integration', 'high', 'Resolved test alert', 'resolved')
                """,
                (organization_id, organization_id),
            )

    token = issue_access_token(
        f"control-tower-{suffix}", str(organization_id), "admin"
    )
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/control-tower/{organization_id}/overview",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["fleet"] == {"total": 2, "active": 1}
    assert data["shipments"] == {
        "active": 1,
        "delivered": 1,
        "overdue_deliveries": 0,
        "due_soon": 0,
        "missed_pickups": 0,
    }
    assert data["alerts"] == {"open": 1, "critical": 1, "high": 0, "medium": 0}
