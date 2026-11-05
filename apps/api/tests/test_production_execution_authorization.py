from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.auth.tenant import TenantContext
from app.routes import recommendation_actions


@pytest.mark.parametrize(
    "membership",
    [
        None,
        ("viewer", "active"),
        ("admin", "suspended"),
        ("admin", "revoked"),
    ],
)
def test_production_execution_rechecks_membership_under_shared_lock(monkeypatch, membership):
    organization_id = UUID("a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21")
    tenant = TenantContext(
        organization_id=organization_id,
        user_id="oidc-user-17",
        role="admin",
    )
    queries = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            queries.append((" ".join(query.split()), params))

        def fetchone(self):
            return membership

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

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(recommendation_actions, "get_connection", fake_connection)

    with pytest.raises(HTTPException) as error:
        recommendation_actions.update_recommendation_action_status(
            action_id=uuid4(),
            payload=recommendation_actions.RecommendationActionStatus(status="in_progress"),
            tenant=tenant,
            idempotency_key="membership-lock-regression",
        )

    assert error.value.status_code == 403
    assert queries == [
        (
            "SELECT role, status FROM organization_memberships "
            "WHERE organization_id = %s AND user_subject = %s FOR SHARE",
            (organization_id, "oidc-user-17"),
        )
    ]
