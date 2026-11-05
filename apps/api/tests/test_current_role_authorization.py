from uuid import UUID

import pytest
from fastapi import HTTPException

from app.auth.tenant import TenantContext, require_current_role


ORG_ID = UUID("a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21")


class MembershipCursor:
    def __init__(self, membership):
        self.membership = membership
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = " ".join(query.split())
        self.params = params

    def fetchone(self):
        return self.membership


@pytest.mark.parametrize(
    "membership",
    [None, ("viewer", "active"), ("admin", "suspended"), ("admin", "revoked")],
)
def test_production_current_role_check_rejects_inactive_or_insufficient_membership(monkeypatch, membership):
    monkeypatch.setenv("APP_ENV", "production")
    tenant = TenantContext(ORG_ID, "actor-1", "admin")
    cursor = MembershipCursor(membership)

    with pytest.raises(HTTPException) as error:
        require_current_role(
            cursor,
            tenant,
            {"admin", "operations_manager", "fleet_manager"},
            "Not authorized",
        )

    assert error.value.status_code == 403
    assert cursor.query.endswith("FOR SHARE")
    assert cursor.params == (ORG_ID, "actor-1")


def test_production_current_role_check_accepts_current_active_operations_manager(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    tenant = TenantContext(ORG_ID, "actor-1", "viewer")
    cursor = MembershipCursor(("operations_manager", "active"))

    require_current_role(
        cursor,
        tenant,
        {"admin", "operations_manager", "fleet_manager"},
        "Not authorized",
    )

    assert cursor.query.endswith("FOR SHARE")


def test_nonproduction_current_role_check_uses_resolved_tenant_role(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    tenant = TenantContext(ORG_ID, "actor-1", "viewer")
    cursor = MembershipCursor(("admin", "active"))

    with pytest.raises(HTTPException) as error:
        require_current_role(cursor, tenant, {"admin"}, "Not authorized")

    assert error.value.status_code == 403
    assert cursor.query is None
