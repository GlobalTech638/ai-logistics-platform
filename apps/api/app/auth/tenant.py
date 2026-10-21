from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException

from app.auth.security import AccessClaims, get_access_claims


@dataclass(frozen=True)
class TenantContext:
    organization_id: UUID
    user_id: str
    role: str


def get_tenant_context(claims: AccessClaims = Depends(get_access_claims)) -> TenantContext:
    """Derive tenant identity and role only from a verified signed bearer token.

    Client-supplied X-Organization-ID, X-User-ID, and X-User-Role headers are
    deliberately not trusted for authorization.
    """
    try:
        organization_id = UUID(claims.organization_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid organization claim") from exc

    return TenantContext(
        organization_id=organization_id,
        user_id=claims.user_id,
        role=claims.role,
    )
