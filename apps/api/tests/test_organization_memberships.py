from contextlib import contextmanager
from uuid import UUID

from fastapi.testclient import TestClient

from app import main
from app.auth.tenant import TenantContext, get_tenant_context
from app.routes import organizations


client = TestClient(main.app)
ORG_ID = UUID("11111111-1111-4111-8111-111111111111")


def _tenant(role="admin"):
    return TenantContext(organization_id=ORG_ID, user_id="admin-subject", role=role)


def test_non_admin_cannot_add_organization_members(monkeypatch):
    main.app.dependency_overrides[get_tenant_context] = lambda: _tenant("operations_manager")
    try:
        def should_not_connect():
            raise AssertionError("non-admin membership changes must be rejected before database access")

        monkeypatch.setattr(organizations, "get_connection", should_not_connect)
        response = client.post(
            f"/api/v1/organizations/{ORG_ID}/members",
            json={"user_subject": "new-user", "role": "viewer"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Organization administrator role required"
    finally:
        main.app.dependency_overrides.pop(get_tenant_context, None)


def test_admin_cannot_manage_memberships_in_another_tenant(monkeypatch):
    main.app.dependency_overrides[get_tenant_context] = lambda: _tenant("admin")
    other_org = "22222222-2222-4222-8222-222222222222"
    try:
        def should_not_connect():
            raise AssertionError("cross-tenant membership changes must be rejected before database access")

        monkeypatch.setattr(organizations, "get_connection", should_not_connect)
        response = client.post(
            f"/api/v1/organizations/{other_org}/members",
            json={"user_subject": "attacker", "role": "admin"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Organization access denied"
    finally:
        main.app.dependency_overrides.pop(get_tenant_context, None)


def test_last_active_admin_cannot_be_demoted_or_suspended(monkeypatch):
    main.app.dependency_overrides[get_tenant_context] = lambda: _tenant("admin")

    class Cursor:
        def __init__(self):
            self.query = ""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            self.query = query

        def fetchone(self):
            normalized_query = " ".join(self.query.split())
            if "SELECT id FROM organizations" in normalized_query:
                return (ORG_ID,)
            if "SELECT role, status FROM organization_memberships" in normalized_query:
                return ("admin", "active")
            if "SELECT count(*)" in normalized_query:
                return (1,)
            raise AssertionError(f"Unexpected query: {self.query}")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_connection():
        yield Connection()

    try:
        monkeypatch.setattr(organizations, "get_connection", fake_connection)
        response = client.patch(
            f"/api/v1/organizations/{ORG_ID}/members/admin-subject",
            json={"role": "viewer"},
        )
        assert response.status_code == 409
        assert "last active" in response.json()["detail"]
    finally:
        main.app.dependency_overrides.pop(get_tenant_context, None)


def test_membership_update_requires_at_least_one_field(monkeypatch):
    main.app.dependency_overrides[get_tenant_context] = lambda: _tenant("admin")
    try:
        def should_not_connect():
            raise AssertionError("empty membership update must not access the database")

        monkeypatch.setattr(organizations, "get_connection", should_not_connect)
        response = client.patch(
            f"/api/v1/organizations/{ORG_ID}/members/member-1",
            json={},
        )
        assert response.status_code == 422
    finally:
        main.app.dependency_overrides.pop(get_tenant_context, None)


@pytest.mark.parametrize(
    "membership,expected_status",
    [
        (None, 403),
        (("viewer", "active"), 403),
        (("admin", "suspended"), 403),
        (("admin", "revoked"), 403),
    ],
)
def test_production_membership_admin_actions_lock_and_revalidate_actor(
    monkeypatch, membership, expected_status
):
    from fastapi import HTTPException

    monkeypatch.setenv("APP_ENV", "production")
    statements = []

    class Cursor:
        def execute(self, query, params):
            statements.append((" ".join(query.split()), params))

        def fetchone(self):
            return membership

    tenant = _tenant("admin")
    with pytest.raises(HTTPException) as error:
        organizations._lock_and_verify_active_admin(Cursor(), ORG_ID, tenant)

    assert error.value.status_code == expected_status
    assert statements == [
        (
            "SELECT role, status FROM organization_memberships "
            "WHERE organization_id = %s AND user_subject = %s FOR SHARE",
            (ORG_ID, tenant.user_id),
        )
    ]


def test_production_membership_admin_lock_accepts_active_admin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    class Cursor:
        def execute(self, query, params):
            assert "FOR SHARE" in query
            assert params == (ORG_ID, "admin-subject")

        def fetchone(self):
            return ("admin", "active")

    organizations._lock_and_verify_active_admin(Cursor(), ORG_ID, _tenant("admin"))
