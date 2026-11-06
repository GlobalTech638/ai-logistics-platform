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
def test_vehicle_and_shipment_creation_use_canonical_schema():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Operations create {suffix}",),
            )
            organization_id = cur.fetchone()[0]

    token = issue_access_token(
        f"operations-manager-{suffix}", str(organization_id), "operations_manager"
    )
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        vehicle = client.post(
            f"/api/v1/operations/{organization_id}/vehicles",
            headers=headers,
            json={
                "registration_number": f"KAA-{suffix}",
                "make": "Test Motors",
                "model": "Cargo 12T",
                "fuel_type": "diesel",
                "expected_litres_per_100km": 24,
                "capacity_tonnes": 12,
                "odometer_km": 15000,
                "active": True,
            },
        )
        shipment = client.post(
            f"/api/v1/operations/{organization_id}/shipments",
            headers=headers,
            json={
                "shipment_reference": f"LOAD-{suffix}",
                "origin": "Nairobi",
                "destination": "Mombasa",
                "weight_tonnes": 8,
                "status": "pending",
            },
        )
        timeline = client.get(
            f"/api/v1/operations/{organization_id}/shipments/{shipment.json()['id']}/timeline",
            headers=headers,
        )

    assert vehicle.status_code == 200, vehicle.text
    assert vehicle.json()["registration_number"] == f"KAA-{suffix}"
    assert vehicle.json()["make"] == "Test Motors"
    assert vehicle.json()["active"] is True

    assert shipment.status_code == 200, shipment.text
    assert shipment.json()["shipment_reference"] == f"LOAD-{suffix}"
    assert shipment.json()["origin"] == "Nairobi"
    assert shipment.json()["status"] == "pending"
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["total_events"] == 1
    assert timeline.json()["events"][0]["event_type"] == "shipment_created"
    assert timeline.json()["events"][0]["actor_id"] == f"operations-manager-{suffix}"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM vehicles
                WHERE organization_id = %s AND registration_number = %s
                """,
                (organization_id, f"KAA-{suffix}"),
            )
            assert cur.fetchone()[0] == 1
            cur.execute(
                """
                SELECT count(*) FROM shipments
                WHERE organization_id = %s AND shipment_reference = %s
                """,
                (organization_id, f"LOAD-{suffix}"),
            )
            assert cur.fetchone()[0] == 1
