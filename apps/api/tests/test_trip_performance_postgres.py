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
def test_trip_performance_uses_measured_distance_and_keeps_currency_costs_separate():
    suffix = uuid4().hex[:10]
    completed_at = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Trip performance {suffix}",),
            )
            organization_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, capacity_tonnes, odometer_km, active
                ) VALUES (%s, %s, 'Test', 'Truck', 20, 15, 1200, TRUE)
                RETURNING id
                """,
                (organization_id, f"PERF-{suffix}"),
            )
            vehicle_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination,
                    weight_tonnes, status
                ) VALUES (%s, %s, 'Nairobi', 'Mombasa', 10, 'delivered')
                RETURNING id
                """,
                (organization_id, f"PERF-LOAD-{suffix}"),
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
                    %s, %s, %s, 'Nairobi', 'Mombasa',
                    110, 300, 240, 10, %s, %s, 'operator',
                    1200, 1300, 100, 'operator'
                ) RETURNING id
                """,
                (organization_id, vehicle_id, shipment_id, completed_at, completed_at),
            )
            trip_id = cur.fetchone()[0]

    token = issue_access_token(
        f"performance-operator-{suffix}", str(organization_id), "operations_manager"
    )
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        fuel_url = f"/api/v1/operations/{organization_id}/fuel-transactions"
        kes_payload = {
            "vehicle_id": str(vehicle_id), "trip_id": str(trip_id),
            "transaction_time": completed_at.isoformat(), "litres": 100,
            "price_per_litre": 150, "odometer_km": 1250,
            "currency": "KES", "country_code": "KE",
        }
        usd_payload = {
            "vehicle_id": str(vehicle_id), "trip_id": str(trip_id),
            "transaction_time": completed_at.isoformat(), "litres": 20,
            "price_per_litre": 2, "odometer_km": 1260,
            "currency": "USD", "country_code": "US",
        }
        missing_key = client.post(fuel_url, json=kes_payload, headers=headers)
        kes = client.post(
            fuel_url, json=kes_payload,
            headers={**headers, "Idempotency-Key": f"fuel-kes-{suffix}"},
        )
        kes_replay = client.post(
            fuel_url, json=kes_payload,
            headers={**headers, "Idempotency-Key": f"fuel-kes-{suffix}"},
        )
        conflicting = client.post(
            fuel_url, json={**kes_payload, "litres": 101},
            headers={**headers, "Idempotency-Key": f"fuel-kes-{suffix}"},
        )
        usd = client.post(
            fuel_url, json=usd_payload,
            headers={**headers, "Idempotency-Key": f"fuel-usd-{suffix}"},
        )
        response = client.get(
            f"/api/v1/operations/{organization_id}/trip-performance?days=30",
            headers=headers,
        )
        timeline = client.get(
            f"/api/v1/operations/{organization_id}/shipments/{shipment_id}/timeline",
            headers=headers,
        )

    assert missing_key.status_code == 428, missing_key.text
    assert kes.status_code == 200, kes.text
    assert kes_replay.status_code == 200, kes_replay.text
    assert kes_replay.json() == kes.json()
    assert conflicting.status_code == 409, conflicting.text
    assert usd.status_code == 200, usd.text
    assert timeline.status_code == 200, timeline.text
    assert [event["event_type"] for event in timeline.json()["events"]].count("fuel_recorded") == 2

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"]["completed_trip_count"] == 1
    assert data["summary"]["actual_distance_km"] == 100
    assert data["summary"]["fuel_litres"] == 120
    assert data["summary"]["expected_fuel_litres"] == 20
    assert data["summary"]["fuel_costs_by_currency"] == [
        {"currency": "KES", "amount": 15000},
        {"currency": "USD", "amount": 40},
    ]
    trip = data["trips"][0]
    assert trip["trip_id"] == str(trip_id)
    assert trip["actual_litres_per_100km"] == 120
    assert trip["fuel_variance_percent"] == 500
    assert trip["fuel_costs"] == [
        {"currency": "KES", "amount": 15000},
        {"currency": "USD", "amount": 40},
    ]
