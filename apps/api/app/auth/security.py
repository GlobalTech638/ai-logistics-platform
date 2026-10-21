import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

TOKEN_TTL_MINUTES = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "60"))
_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET", "development-only-change-me")
_ALLOWED_ROLES = {"admin", "operations_manager", "fleet_manager", "analyst", "viewer"}


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    organization_id: str
    role: str
    expires_at: datetime


def _sign(payload: str) -> str:
    return hmac.new(_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_access_token(user_id: str, organization_id: str, role: str) -> str:
    """Issue a short-lived signed token for trusted server-side callers.

    Do not expose this helper as an unauthenticated public endpoint. Production
    deployments must set ACCESS_TOKEN_SECRET to a strong, randomly generated value.
    """
    if not user_id.strip():
        raise ValueError("user_id is required")
    if role not in _ALLOWED_ROLES:
        raise ValueError("Unsupported organization role")
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
    payload = f"{user_id}:{organization_id}:{role}:{int(expires.timestamp())}"
    return f"{payload}.{_sign(payload)}"


def get_access_claims(authorization: str = Header(...)) -> AccessClaims:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = authorization.removeprefix("Bearer ")
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
    if not user_id.strip() or role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=401, detail="Invalid access token claims")

    return AccessClaims(user_id, organization_id, role, expires_at)
