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
def test_dispatch_candidates_exclude_unavailable_and_ineligible_vehicles():
    suffix = uuid4().hex[:12]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, 'KE', 'KES') RETURNING id
                """,
                (f"Dispatch candidates {suffix}",),
            )
            organization_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model,
                    expected_litres_per_100km, capacity_tonnes, active
                ) VALUES
                    (%s, %s, 'Test', 'Available', 20, 12, TRUE),
                    (%s, %s, 'Test', 'Busy', 20, 15, TRUE),
                    (%s, %s, 'Test', 'Inactive', 20, 15, FALSE),
                    (%s, %s, 'Test', 'Undersized', 20, 4, TRUE)
                RETURNING id
                """,
                (
                    organization_id, f"AVAILABLE-{suffix}",
                    organization_id, f"BUSY-{suffix}",
                    organization_id, f"INACTIVE-{suffix}",
                    organization_id, f"SMALL-{suffix}",
                ),
            )
            available_id, busy_id, inactive_id, undersized_id = [
                row[0] for row in cur.fetchall()
            ]

            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination, weight_tonnes
                ) VALUES (%s, %s, 'Nairobi', 'Mombasa', 8)
                RETURNING id
                """,
                (organization_id, f"DISPATCH-{suffix}"),
            )
            shipment_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination, weight_tonnes
                ) VALUES (%s, %s, 'Nairobi', 'Kisumu', 3)
                RETURNING id
                """,
                (organization_id, f"BUSY-LOAD-{suffix}"),
            )
            busy_shipment_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO trips (
                    organization_id, vehicle_id, shipment_id, origin, destination,
                    distance_km, planned_duration_minutes, actual_duration_minutes, load_tonnes
                ) VALUES (%s, %s, %s, 'Nairobi', 'Kisumu', 350, 350, 350, 3)
                """,
                (organization_id, busy_id, busy_shipment_id),
            )

    token = issue_access_token(
        f"dispatch-operator-{suffix}", str(organization_id), "operations_manager"
    )
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/operations/{organization_id}/shipments/{shipment_id}/dispatch-candidates",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["eligible_vehicle_count"] == 1
    assert [item["vehicle_id"] for item in result["candidates"]] == [str(available_id)]
    assert result["candidates"][0]["capacity_tonnes"] == 12
    assert result["candidates"][0]["shipment_weight_tonnes"] == 8

    # The candidate endpoint is advisory; it must not create a trip or mutate
    # the shipment while an operator is evaluating options.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM trips
                WHERE organization_id = %s AND shipment_id = %s
                """,
                (organization_id, shipment_id),
            )
            assert cur.fetchone()[0] == 0
