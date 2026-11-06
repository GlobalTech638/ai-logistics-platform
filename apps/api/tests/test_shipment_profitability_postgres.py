import os
from datetime import datetime, timezone
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
def test_shipment_revenue_idempotency_and_currency_safe_profitability():
    suffix = uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Profitability {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, capacity_tonnes, odometer_km, active
                ) VALUES (%s, %s, 'Test', 'Truck', 20, 20, 500, TRUE)
                RETURNING id
                """,
                (organization_id, f"PROFIT-{suffix}"),
            )
            vehicle_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination,
                    weight_tonnes, status
                ) VALUES (%s, %s, 'Nairobi', 'Mombasa', 8, 'delivered')
                RETURNING id
                """,
                (organization_id, f"PROFIT-LOAD-{suffix}"),
            )
            shipment_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO trips (
                    organization_id, vehicle_id, shipment_id, origin, destination,
                    distance_km, planned_duration_minutes, actual_duration_minutes,
                    load_tonnes, completed_at, started_at, started_by,
                    start_odometer_km, end_odometer_km, actual_distance_km, completed_by
                ) VALUES (
                    %s, %s, %s, 'Nairobi', 'Mombasa', 500, 600, 540,
                    8, %s, %s, 'operator', 0, 500, 500, 'operator'
                ) RETURNING id
                """,
                (organization_id, vehicle_id, shipment_id, now, now),
            )
            trip_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO fuel_transactions (
                    organization_id, vehicle_id, trip_id, transaction_time,
                    litres, price_per_litre, odometer_km, currency, country_code
                ) VALUES
                    (%s, %s, %s, %s, 20, 100, 250, 'KES', 'KE'),
                    (%s, %s, %s, %s, 2, 50, 300, 'USD', 'US')
                """,
                (
                    organization_id, vehicle_id, trip_id, now,
                    organization_id, vehicle_id, trip_id, now,
                ),
            )

    token = issue_access_token(
        f"profitability-operator-{suffix}", str(organization_id), "operations_manager"
    )
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/operations/{organization_id}/shipments/{shipment_id}/charges"
    first_payload = {
        "charge_type": "transport",
        "description": "Line-haul delivery charge",
        "amount": 1000,
        "currency": "KES",
        "occurred_at": now.isoformat(),
    }
    second_payload = {
        "charge_type": "handling",
        "description": "Warehouse handling",
        "amount": 250,
        "currency": "KES",
        "occurred_at": now.isoformat(),
    }
    usd_payload = {
        "charge_type": "other",
        "description": "Cross-border documentation",
        "amount": 300,
        "currency": "USD",
        "occurred_at": now.isoformat(),
    }
    with TestClient(app) as client:
        missing_key = client.post(url, json=first_payload, headers=headers)
        first = client.post(
            url, json=first_payload,
            headers={**headers, "Idempotency-Key": f"revenue-{suffix}"},
        )
        replay = client.post(
            url, json=first_payload,
            headers={**headers, "Idempotency-Key": f"revenue-{suffix}"},
        )
        conflict = client.post(
            url, json={**first_payload, "amount": 1100},
            headers={**headers, "Idempotency-Key": f"revenue-{suffix}"},
        )
        second = client.post(
            url, json=second_payload,
            headers={**headers, "Idempotency-Key": f"handling-{suffix}"},
        )
        usd_charge = client.post(
            url, json=usd_payload,
            headers={**headers, "Idempotency-Key": f"usd-charge-{suffix}"},
        )
        profitability = client.get(
            f"/api/v1/operations/{organization_id}/profitability?days=30",
            headers=headers,
        )

    assert missing_key.status_code == 428, missing_key.text
    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert conflict.status_code == 409, conflict.text
    assert second.status_code == 200, second.text
    assert usd_charge.status_code == 200, usd_charge.text
    assert profitability.status_code == 200, profitability.text
    data = profitability.json()
    assert data["period_days"] == 30
    assert data["currency_totals"] == [
        {"currency": "KES", "revenue": 1250, "fuel_cost": 2000, "fuel_contribution": -750},
        {"currency": "USD", "revenue": 300, "fuel_cost": 100, "fuel_contribution": 200},
    ]
    assert len(data["shipments"]) == 2
    shipment = next(item for item in data["shipments"] if item["currency"] == "KES")
    assert shipment["shipment_id"] == str(shipment_id)
    assert shipment["currency"] == "KES"
    assert shipment["revenue_amount"] == 1250
    assert shipment["fuel_amount"] == 2000
    assert shipment["fuel_contribution"] == -750
    assert shipment["fuel_contribution_margin_percent"] == -60
    assert "maintenance and overhead are not allocated" in data["cost_scope"]
