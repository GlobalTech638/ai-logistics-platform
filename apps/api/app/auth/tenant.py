import os
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException

from app.auth.security import AccessClaims, get_access_claims
from app.db.database import get_connection


@dataclass(frozen=True)
class TenantContext:
    organization_id: UUID
    user_id: str
    role: str


def get_tenant_context(claims: AccessClaims = Depends(get_access_claims)) -> TenantContext:
    """Resolve tenant and authorization from verified identity plus active membership.

    In production, the identity provider establishes who the caller is and which
    organization context was requested. The database remains authoritative for
    current membership status and role, so stale JWT role claims cannot preserve
    privileges after an administrator changes or revokes membership.
    Client-supplied identity and role headers are never trusted.
    """
    try:
        organization_id = UUID(claims.organization_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid organization claim") from exc

    role = claims.role
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT role, status
                        FROM organization_memberships
                        WHERE organization_id = %s AND user_subject = %s
                        """,
                        (organization_id, claims.user_id),
                    )
                    membership = cursor.fetchone()
        except Exception as exc:
            # Authorization must fail closed when the membership authority is unavailable.
            raise HTTPException(
                status_code=503,
                detail="Organization authorization is temporarily unavailable",
            ) from exc

        if membership is None:
            raise HTTPException(status_code=403, detail="Organization membership is not active")
        role, status = membership
        if status != "active":
            raise HTTPException(status_code=403, detail="Organization membership is not active")

    return TenantContext(
        organization_id=organization_id,
        user_id=claims.user_id,
        role=role,
    )


def require_current_role(cursor, tenant: TenantContext, allowed_roles: set[str], detail: str) -> None:
    """Enforce an allowed role and lock its current membership for the transaction.

    Production membership changes take a conflicting row lock, so revocation or
    downgrade cannot race with a privileged write after this check.
    """
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        cursor.execute(
            """
            SELECT role, status
            FROM organization_memberships
            WHERE organization_id = %s AND user_subject = %s
            FOR SHARE
            """,
            (tenant.organization_id, tenant.user_id),
        )
        membership = cursor.fetchone()
        if membership is None or membership[1] != "active":
            raise HTTPException(status_code=403, detail="Organization membership is not active")
        current_role = membership[0]
    else:
        current_role = tenant.role

    if current_role not in allowed_roles:
        raise HTTPException(status_code=403, detail=detail)
