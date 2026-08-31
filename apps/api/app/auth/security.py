import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

TOKEN_TTL_MINUTES = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "60"))
_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET", "development-only-change-me")


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    organization_id: str
    role: str
    expires_at: datetime


def issue_access_token(user_id: str, organization_id: str, role: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
    payload = f"{user_id}:{organization_id}:{role}:{int(expires.timestamp())}"
    signature = hashlib.sha256(f"{payload}:{_TOKEN_SECRET}".encode()).hexdigest()
    return f"{payload}.{signature}"


def get_access_claims(authorization: str = Header(...)) -> AccessClaims:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = authorization.removeprefix("Bearer ")
    try:
        payload, signature = token.rsplit(".", 1)
        user_id, organization_id, role, expiry = payload.split(":", 3)
        expected = hashlib.sha256(f"{payload}:{_TOKEN_SECRET}".encode()).hexdigest()
        expires_at = datetime.fromtimestamp(int(expiry), tz=timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    if not secrets.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid access token")
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Access token expired")

    return AccessClaims(user_id, organization_id, role, expires_at)
