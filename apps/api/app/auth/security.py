import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClientError, PyJWTError

TOKEN_TTL_MINUTES = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "60"))
_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET", "development-only-change-me")
_ALLOWED_ROLES = {"admin", "operations_manager", "fleet_manager", "analyst", "viewer"}
PRODUCTION_ALGORITHMS = ["RS256"]
OIDC_LEEWAY_SECONDS = 30


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    organization_id: str
    role: str
    expires_at: datetime


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def _production_oidc_config() -> tuple[str, str, str]:
    jwks_url = os.getenv("OIDC_JWKS_URL", "").strip()
    issuer = os.getenv("OIDC_ISSUER", "").strip()
    audience = os.getenv("OIDC_AUDIENCE", "").strip()
    if not jwks_url or not issuer or not audience:
        raise RuntimeError(
            "Production requires OIDC_JWKS_URL, OIDC_ISSUER, and OIDC_AUDIENCE"
        )
    if urlparse(jwks_url).scheme != "https" or urlparse(issuer).scheme != "https":
        raise RuntimeError("Production OIDC JWKS URL and issuer must use HTTPS")
    return jwks_url, issuer, audience


if TOKEN_TTL_MINUTES < 1:
    raise RuntimeError("ACCESS_TOKEN_TTL_MINUTES must be at least 1")
if _is_production():
    _production_oidc_config()


def _sign(payload: str) -> str:
    return hmac.new(_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_access_token(user_id: str, organization_id: str, role: str) -> str:
    """Issue a development token for trusted local/test callers only.

    Production identity must come from the configured OIDC identity provider.
    This helper is deliberately disabled in production.
    """
    if _is_production():
        raise RuntimeError("Local access-token issuance is disabled in production")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required")
    if len(user_id) > 128 or ":" in user_id:
        raise ValueError("user_id must be at most 128 characters and cannot contain ':'")
    if not isinstance(organization_id, str) or not organization_id.strip() or ":" in organization_id:
        raise ValueError("organization_id is required and cannot contain ':'")
    if role not in _ALLOWED_ROLES:
        raise ValueError("Unsupported organization role")
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
    payload = f"{user_id}:{organization_id}:{role}:{int(expires.timestamp())}"
    return f"{payload}.{_sign(payload)}"


def _decode_oidc_claims(token: str) -> AccessClaims:
    jwks_url, issuer, audience = _production_oidc_config()
    try:
        signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=PRODUCTION_ALGORITHMS,
            issuer=issuer,
            audience=audience,
            leeway=OIDC_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except (PyJWTError, PyJWKClientError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid identity-provider token") from exc

    user_id = payload.get("sub")
    organization_id = payload.get("organization_id")
    role = payload.get("organization_role")
    if (
        not isinstance(user_id, str)
        or not user_id.strip()
        or len(user_id) > 128
        or not isinstance(organization_id, str)
        or not organization_id.strip()
        or not isinstance(role, str)
        or role not in _ALLOWED_ROLES
    ):
        raise HTTPException(status_code=401, detail="Invalid identity-provider claims")

    try:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(status_code=401, detail="Invalid identity-provider expiry") from exc

    return AccessClaims(user_id, organization_id, role, expires_at)


def get_access_claims(authorization: str = Header(...)) -> AccessClaims:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")

    if _is_production():
        return _decode_oidc_claims(token)

    try:
        payload, signature = token.rsplit(".", 1)
        user_id, organization_id, role, expiry = payload.split(":", 3)
        expected = _sign(payload)
        expires_at = datetime.fromtimestamp(int(expiry), tz=timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    if not secrets.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid access token")
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Access token expired")
    if (
        not user_id.strip()
        or len(user_id) > 128
        or ":" in user_id
        or not organization_id.strip()
        or ":" in organization_id
        or role not in _ALLOWED_ROLES
    ):
        raise HTTPException(status_code=401, detail="Invalid access token claims")

    return AccessClaims(user_id, organization_id, role, expires_at)
