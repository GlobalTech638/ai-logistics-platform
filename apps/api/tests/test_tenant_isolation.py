from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.security import issue_access_token
from app.main import app
from app.routes import organizations, recommendation_actions

client = TestClient(app)
TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"


def bearer(user_id: str = "operator-a", organization_id: str = TENANT_A, role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, organization_id, role)}"}


def test_tenant_cannot_list_another_organizations_vehicles(monkeypatch):
    def should_not_connect():
        raise AssertionError("cross-tenant request must be rejected before database access")

    monkeypatch.setattr(organizations, "get_connection", should_not_connect)
    headers = {
        **bearer(),
        "X-Organization-ID": TENANT_B,
        "X-User-ID": "attacker",
        "X-User-Role": "admin",
    }

    response = client.get(f"/api/v1/organizations/{TENANT_B}/vehicles", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization access denied"


def test_tenant_cannot_list_another_organizations_recommendation_actions(monkeypatch):
    def should_not_connect():
        raise AssertionError("cross-tenant request must be rejected before database access")

    monkeypatch.setattr(recommendation_actions, "get_connection", should_not_connect)
    headers = {**bearer(), "X-Organization-ID": TENANT_B, "X-User-Role": "admin"}

    response = client.get(f"/api/v1/recommendations/{TENANT_B}/actions", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization access denied"


def test_viewer_cannot_execute_recommendation_action(monkeypatch):
    def should_not_connect():
        raise AssertionError("role-denied request must be rejected before database access")

    monkeypatch.setattr(recommendation_actions, "get_connection", should_not_connect)
    response = client.patch(
        "/api/v1/recommendations/actions/33333333-3333-4333-8333-333333333333/status",
        headers=bearer(role="viewer"),
        json={"status": "accepted"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Role is not authorized to execute recommendations"


def test_invalid_token_cannot_be_overridden_by_identity_headers():
    response = client.get(
        f"/api/v1/organizations/{TENANT_A}/vehicles",
        headers={
            "Authorization": "Bearer invalid",
            "X-Organization-ID": TENANT_A,
            "X-User-ID": "operator-a",
            "X-User-Role": "admin",
        },
    )

    assert response.status_code == 401
