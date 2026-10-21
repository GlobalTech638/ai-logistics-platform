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
def test_route_plan_api_enforces_tenant_roles_and_lifecycle():
    organization_ids = []
    shipment_ids = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            for name in ("API integration A", "API integration B"):
                cur.execute(
                    """
                    INSERT INTO organizations (name, country_code, default_currency)
                    VALUES (%s, 'KE', 'KES') RETURNING id
                    """,
                    (name,),
                )
                organization_ids.append(cur.fetchone()[0])

            for org_id, reference in zip(organization_ids, ("API-INT-A", "API-INT-B")):
                cur.execute(
                    """
                    INSERT INTO shipments
                        (organization_id, shipment_reference, origin, destination, weight_tonnes)
                    VALUES (%s, %s, 'Nairobi', 'Mombasa', 2) RETURNING id
                    """,
                    (org_id, reference),
                )
                shipment_ids.append(cur.fetchone()[0])

    org_a, org_b = organization_ids
    shipment_a, shipment_b = shipment_ids
    operator_token = issue_access_token("operator-a", str(org_a), "operations_manager")
    viewer_token = issue_access_token("viewer-a", str(org_a), "viewer")
    client = TestClient(app)

    headers = {"Authorization": f"Bearer {operator_token}"}
    create_url = f"/api/v1/route-plans/{org_a}/shipments/{shipment_a}"

    created = client.post(create_url, json={"corridor": "Nairobi-Mombasa"}, headers=headers)
    assert created.status_code == 200, created.text
    plan_id = UUID(created.json()["id"])
    assert created.json()["status"] == "planned"

    # A signed token cannot be used to cross into another organization's data.
    cross_tenant = client.post(
        f"/api/v1/route-plans/{org_b}/shipments/{shipment_b}",
        json={"corridor": "Unauthorized"},
        headers=headers,
    )
    assert cross_tenant.status_code == 403

    # Read-only role must not create or transition route plans.
    forbidden_create = client.post(
        create_url, json={"corridor": "Viewer route"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert forbidden_create.status_code == 403

    activate = client.patch(
        f"/api/v1/route-plans/{org_a}/plans/{plan_id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert activate.status_code == 200, activate.text
    assert activate.json()["status"] == "active"

    illegal_transition = client.patch(
        f"/api/v1/route-plans/{org_a}/plans/{plan_id}/status",
        json={"status": "planned"},
        headers=headers,
    )
    assert illegal_transition.status_code == 409

    supersede = client.patch(
        f"/api/v1/route-plans/{org_a}/plans/{plan_id}/status",
        json={"status": "superseded", "reroute_reason": "Integration test"},
        headers=headers,
    )
    assert supersede.status_code == 200, supersede.text
    assert supersede.json()["status"] == "superseded"

    immutable = client.patch(
        f"/api/v1/route-plans/{org_a}/plans/{plan_id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert immutable.status_code == 409
