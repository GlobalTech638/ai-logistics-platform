from uuid import UUID

import pytest
from fastapi import HTTPException

from app.auth import security
from app.auth.tenant import get_tenant_context


def test_signed_bearer_token_produces_tenant_claims():
    organization_id = "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21"
    token = security.issue_access_token("operator-7", organization_id, "operations_manager")

    claims = security.get_access_claims(f"Bearer {token}")
    tenant = get_tenant_context(claims)

    assert tenant.organization_id == UUID(organization_id)
    assert tenant.user_id == "operator-7"
    assert tenant.role == "operations_manager"


def test_tampered_token_is_rejected():
    token = security.issue_access_token(
        "operator-7", "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21", "viewer"
    )
    payload, signature = token.rsplit(".", 1)
    tampered = payload.replace(":viewer:", ":admin:") + "." + signature

    with pytest.raises(HTTPException) as error:
        security.get_access_claims(f"Bearer {tampered}")

    assert error.value.status_code == 401


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(security, "TOKEN_TTL_MINUTES", -1)
    token = security.issue_access_token(
        "operator-7", "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21", "viewer"
    )

    with pytest.raises(HTTPException) as error:
        security.get_access_claims(f"Bearer {token}")

    assert error.value.status_code == 401
    assert "expired" in error.value.detail.lower()


def test_unsupported_role_cannot_be_issued():
    with pytest.raises(ValueError, match="Unsupported organization role"):
        security.issue_access_token(
            "operator-7", "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21", "superuser"
        )


def test_invalid_organization_claim_is_rejected():
    claims = security.AccessClaims(
        user_id="operator-7",
        organization_id="not-a-uuid",
        role="viewer",
        expires_at=security.datetime.now(security.timezone.utc),
    )

    with pytest.raises(HTTPException) as error:
        get_tenant_context(claims)

    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "user_id,organization_id",
    [
        ("operator:admin", "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21"),
        ("operator-7", "org:admin"),
        ("operator-7", ""),
        ("", "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21"),
    ],
)
def test_token_issuance_rejects_empty_or_delimiter_bearing_identity(user_id, organization_id):
    with pytest.raises(ValueError):
        security.issue_access_token(user_id, organization_id, "viewer")


def test_token_issuance_rejects_overlong_user_id():
    with pytest.raises(ValueError, match="128 characters"):
        security.issue_access_token(
            "u" * 129, "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21", "viewer"
        )
