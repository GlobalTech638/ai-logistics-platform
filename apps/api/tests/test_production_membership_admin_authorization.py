import pytest
from fastapi import HTTPException
from uuid import UUID

from app.auth.tenant import TenantContext
from app.routes.organizations import _lock_and_verify_active_admin


@pytest.mark.parametrize(
    "membership",
    [None, ("admin", "suspended"), ("admin", "revoked"), ("viewer", "active")],
)
def test_production_membership_admin_mutation_rejects_stale_admin_claim(monkeypatch, membership):
    organization_id = UUID("a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21")
    tenant = TenantContext(organization_id, "actor-1", "admin")

    class Cursor:
        query = None
        params = None

        def execute(self, query, params):
            self.query = " ".join(query.split())
            self.params = params

        def fetchone(self):
            return membership

    cursor = Cursor()
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(HTTPException) as error:
        _lock_and_verify_active_admin(cursor, organization_id, tenant)

    assert error.value.status_code == 403
    assert "FOR SHARE" in cursor.query
    assert cursor.params == (organization_id, "actor-1")


def test_production_membership_admin_mutation_accepts_active_admin(monkeypatch):
    organization_id = UUID("a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21")
    tenant = TenantContext(organization_id, "actor-1", "admin")

    class Cursor:
        def execute(self, query, params):
            assert "FOR SHARE" in query
            assert params == (organization_id, "actor-1")

        def fetchone(self):
            return ("admin", "active")

    monkeypatch.setenv("APP_ENV", "production")
    _lock_and_verify_active_admin(Cursor(), organization_id, tenant)
