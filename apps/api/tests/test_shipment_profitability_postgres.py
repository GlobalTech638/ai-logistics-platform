import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation
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
                    (%s, %s, %s, %s, 2, 50, 300, 'USD', 'US'),
                    (%s, %s, NULL, %s, 10, 100, 350, 'KES', 'KE')
                """,
                (
                    organization_id, vehicle_id, trip_id, now,
                    organization_id, vehicle_id, trip_id, now,
                    organization_id, vehicle_id, now,
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
    operating_cost_payload = {
        "cost_type": "driver_allowance",
        "description": "Driver overnight allowance",
        "amount": 300,
        "currency": "KES",
        "trip_id": str(trip_id),
        "occurred_at": now.isoformat(),
    }
    usd_cost_payload = {
        "cost_type": "border_fee",
        "description": "Border processing",
        "amount": 50,
        "currency": "USD",
        "trip_id": str(trip_id),
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
        cost_url = f"/api/v1/operations/{organization_id}/shipments/{shipment_id}/operating-costs"
        missing_cost_key = client.post(cost_url, json=operating_cost_payload, headers=headers)
        cost = client.post(
            cost_url, json=operating_cost_payload,
            headers={**headers, "Idempotency-Key": f"driver-cost-{suffix}"},
        )
        cost_replay = client.post(
            cost_url, json=operating_cost_payload,
            headers={**headers, "Idempotency-Key": f"driver-cost-{suffix}"},
        )
        invalid_trip_cost = client.post(
            cost_url, json={**operating_cost_payload, "trip_id": str(uuid4())},
            headers={**headers, "Idempotency-Key": f"bad-trip-cost-{suffix}"},
        )
        usd_cost = client.post(
            cost_url, json=usd_cost_payload,
            headers={**headers, "Idempotency-Key": f"usd-cost-{suffix}"},
        )
        profitability = client.get(
            f"/api/v1/operations/{organization_id}/profitability?days=30",
            headers=headers,
        )
        timeline = client.get(
            f"/api/v1/operations/{organization_id}/shipments/{shipment_id}/timeline",
            headers=headers,
        )

    assert missing_key.status_code == 428, missing_key.text
    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert conflict.status_code == 409, conflict.text
    assert second.status_code == 200, second.text
    assert usd_charge.status_code == 200, usd_charge.text
    assert missing_cost_key.status_code == 428, missing_cost_key.text
    assert cost.status_code == 200, cost.text
    assert cost_replay.status_code == 200, cost_replay.text
    assert cost_replay.json() == cost.json()
    assert invalid_trip_cost.status_code == 422, invalid_trip_cost.text
    assert usd_cost.status_code == 200, usd_cost.text
    assert profitability.status_code == 200, profitability.text
    assert timeline.status_code == 200, timeline.text
    assert [event["event_type"] for event in timeline.json()["events"]].count("revenue_charge_recorded") == 3
    assert [event["event_type"] for event in timeline.json()["events"]].count("operating_cost_recorded") == 2
    data = profitability.json()
    assert data["period_days"] == 30
    assert data["currency_totals"] == [
        {"currency": "KES", "revenue": 1250, "fuel_cost": 2000, "operating_cost": 300, "net_contribution": -1050},
        {"currency": "USD", "revenue": 300, "fuel_cost": 100, "operating_cost": 50, "net_contribution": 150},
    ]
    assert len(data["shipments"]) == 2
    shipment = next(item for item in data["shipments"] if item["currency"] == "KES")
    assert shipment["shipment_id"] == str(shipment_id)
    assert shipment["currency"] == "KES"
    assert shipment["revenue_amount"] == 1250
    assert shipment["fuel_amount"] == 2000
    assert shipment["operating_cost_amount"] == 300
    assert shipment["fuel_contribution"] == -750
    assert shipment["net_contribution"] == -1050
    assert shipment["net_contribution_margin_percent"] == -84
    assert "unallocated costs remain excluded" in data["cost_scope"]
    with pytest.raises(CheckViolation):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE shipment_charges SET amount = 999 WHERE id = %s",
                    (first.json()["charge_id"],),
                )
    with pytest.raises(CheckViolation):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM shipment_charges WHERE id = %s",
                    (first.json()["charge_id"],),
                )
    with pytest.raises(CheckViolation):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE shipment_charge_idempotency
                    SET response_body = '{}'::jsonb
                    WHERE organization_id = %s AND shipment_id = %s
                      AND idempotency_key = %s
                    """,
                    (organization_id, shipment_id, f"revenue-{suffix}"),
                )
    with pytest.raises(CheckViolation):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE shipment_operating_costs SET amount = 1 WHERE id = %s",
                    (cost.json()["cost_id"],),
                )
    with pytest.raises(CheckViolation):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM shipment_operating_costs WHERE id = %s",
                    (cost.json()["cost_id"],),
                )
    with pytest.raises(CheckViolation):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE shipment_operating_cost_idempotency
                    SET response_body = '{}'::jsonb
                    WHERE organization_id = %s AND shipment_id = %s
                      AND idempotency_key = %s
                    """,
                    (organization_id, shipment_id, f"driver-cost-{suffix}"),
                )
