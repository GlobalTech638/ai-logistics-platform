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


def test_production_oidc_verifies_signature_issuer_audience_and_tenant_claims(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    class SigningKey:
        key = public_key

    class FakeJWKClient:
        def __init__(self, url):
            assert url == "https://identity.example.com/.well-known/jwks.json"

        def get_signing_key_from_jwt(self, token):
            return SigningKey()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://identity.example.com/.well-known/jwks.json")
    monkeypatch.setenv("OIDC_ISSUER", "https://identity.example.com/")
    monkeypatch.setenv("OIDC_AUDIENCE", "logistics-api")
    monkeypatch.setattr(security.jwt, "PyJWKClient", FakeJWKClient)

    now = int(security.datetime.now(security.timezone.utc).timestamp())
    token = security.jwt.encode(
        {
            "sub": "oidc-user-17",
            "organization_id": "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21",
            "organization_role": "operations_manager",
            "iss": "https://identity.example.com/",
            "aud": "logistics-api",
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
    )

    claims = security.get_access_claims(f"Bearer {token}")
    tenant = get_tenant_context(claims)

    assert tenant.user_id == "oidc-user-17"
    assert tenant.organization_id == UUID("a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21")
    assert tenant.role == "operations_manager"


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"aud": "another-service"},
        {"iss": "https://attacker.example.com/"},
        {"organization_role": "superuser"},
        {"organization_id": ""},
        {"sub": ""},
    ],
)
def test_production_oidc_rejects_invalid_identity_claims(monkeypatch, claim_overrides):
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    class SigningKey:
        key = public_key

    class FakeJWKClient:
        def __init__(self, url):
            pass

        def get_signing_key_from_jwt(self, token):
            return SigningKey()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://identity.example.com/jwks")
    monkeypatch.setenv("OIDC_ISSUER", "https://identity.example.com/")
    monkeypatch.setenv("OIDC_AUDIENCE", "logistics-api")
    monkeypatch.setattr(security.jwt, "PyJWKClient", FakeJWKClient)

    now = int(security.datetime.now(security.timezone.utc).timestamp())
    payload = {
        "sub": "oidc-user-17",
        "organization_id": "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21",
        "organization_role": "viewer",
        "iss": "https://identity.example.com/",
        "aud": "logistics-api",
        "iat": now,
        "exp": now + 300,
    }
    payload.update(claim_overrides)
    token = security.jwt.encode(payload, private_key, algorithm="RS256")

    with pytest.raises(HTTPException) as error:
        security.get_access_claims(f"Bearer {token}")

    assert error.value.status_code == 401


def test_production_rejects_local_development_tokens(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    token = security.issue_access_token(
        "operator-7", "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21", "viewer"
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://identity.example.com/jwks")
    monkeypatch.setenv("OIDC_ISSUER", "https://identity.example.com/")
    monkeypatch.setenv("OIDC_AUDIENCE", "logistics-api")

    with pytest.raises(HTTPException) as error:
        security.get_access_claims(f"Bearer {token}")

    assert error.value.status_code == 401


def test_production_disables_local_token_issuance(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="disabled in production"):
        security.issue_access_token(
            "operator-7", "a8d0b7be-7e6c-4d29-83d7-63ad0d0b0c21", "viewer"
        )


def test_production_requires_complete_oidc_configuration(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)

    with pytest.raises(RuntimeError, match="OIDC_JWKS_URL"):
        security._production_oidc_config()


def test_production_rejects_non_https_or_hostless_oidc_endpoints(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OIDC_JWKS_URL", "http://identity.example.com/jwks")
    monkeypatch.setenv("OIDC_ISSUER", "https://identity.example.com/")
    monkeypatch.setenv("OIDC_AUDIENCE", "logistics-api")

    with pytest.raises(RuntimeError, match="valid HTTPS URLs"):
        security._production_oidc_config()

    monkeypatch.setenv("OIDC_JWKS_URL", "https:///jwks")
    with pytest.raises(RuntimeError, match="valid HTTPS URLs"):
        security._production_oidc_config()
