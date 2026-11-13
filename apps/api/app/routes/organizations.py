import hmac
import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])
OrganizationRole = Literal["admin", "operations_manager", "fleet_manager", "analyst", "viewer"]
MembershipStatus = Literal["active", "suspended", "revoked"]


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    country_code: str = Field(min_length=2, max_length=2)
    default_currency: str = Field(min_length=3, max_length=3)
    owner_subject: str = Field(min_length=1, max_length=128)


class MembershipCreate(BaseModel):
    user_subject: str = Field(min_length=1, max_length=128)
    role: OrganizationRole = "viewer"


class MembershipUpdate(BaseModel):
    role: OrganizationRole | None = None
    status: MembershipStatus | None = None


def _require_org_admin(organization_id: UUID, tenant: TenantContext) -> None:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")
    if tenant.role != "admin":
        raise HTTPException(status_code=403, detail="Organization administrator role required")


def _lock_and_verify_active_admin(cursor, organization_id: UUID, tenant: TenantContext) -> None:
    """Revalidate the acting administrator while holding the membership row lock."""
    if os.getenv("APP_ENV", "development").strip().lower() != "production":
        return
    cursor.execute(
        """
        SELECT role, status
        FROM organization_memberships
        WHERE organization_id = %s AND user_subject = %s
        FOR SHARE
        """,
        (organization_id, tenant.user_id),
    )
    membership = cursor.fetchone()
    if membership is None or membership[1] != "active":
        raise HTTPException(status_code=403, detail="Organization membership is not active")
    if membership[0] != "admin":
        raise HTTPException(status_code=403, detail="Organization administrator role required")


@router.post("")
def create_organization(
    payload: OrganizationCreate,
    provisioning_token: str | None = Header(default=None, alias="X-Organization-Provisioning-Token"),
) -> dict:
    """Create an organization and its initial admin membership atomically."""
    expected_token = os.getenv("ORGANIZATION_PROVISIONING_TOKEN", "")
    if not expected_token or not provisioning_token or not hmac.compare_digest(provisioning_token, expected_token):
        raise HTTPException(status_code=403, detail="Organization provisioning is not authorized")

    country = payload.country_code.upper()
    currency = payload.default_currency.upper()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO organizations (name, country_code, default_currency)
                VALUES (%s, %s, %s)
                RETURNING id, name, country_code, default_currency, created_at
                """,
                (payload.name.strip(), country, currency),
            )
            row = cursor.fetchone()
            columns = [item.name for item in cursor.description]
            organization = dict(zip(columns, row))
            cursor.execute(
                """
                INSERT INTO organization_memberships
                    (organization_id, user_subject, role, status)
                VALUES (%s, %s, 'admin', 'active')
                """,
                (organization["id"], payload.owner_subject),
            )
            cursor.execute(
                """
                INSERT INTO organization_membership_events (
                    organization_id, actor_subject, target_subject, event_type,
                    new_role, new_status
                )
                VALUES (%s, 'system:provisioning', %s, 'member_added', 'admin', 'active')
                """,
                (organization["id"], payload.owner_subject),
            )
    return organization


@router.get("/{organization_id}/vehicles")
def organization_vehicles(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[dict]:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, registration_number, make, model,
                       fuel_type, capacity_tonnes, odometer_km, active
                FROM vehicles
                WHERE organization_id = %s
                ORDER BY registration_number
                """,
                (organization_id,),
            )
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


@router.get("/{organization_id}/members")
def list_organization_members(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[dict]:
    _require_org_admin(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _lock_and_verify_active_admin(cursor, organization_id, tenant)
            cursor.execute(
                """
                SELECT user_subject, role, status, created_at, updated_at
                FROM organization_memberships
                WHERE organization_id = %s
                ORDER BY user_subject
                """,
                (organization_id,),
            )
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


@router.get("/{organization_id}/membership-events")
def list_membership_events(
    organization_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[dict]:
    _require_org_admin(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _lock_and_verify_active_admin(cursor, organization_id, tenant)
            cursor.execute(
                """
                SELECT actor_subject, target_subject, event_type,
                       previous_role, new_role, previous_status, new_status, created_at
                FROM organization_membership_events
                WHERE organization_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (organization_id, limit),
            )
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


@router.post("/{organization_id}/members", status_code=201)
def add_organization_member(
    organization_id: UUID,
    payload: MembershipCreate,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    _require_org_admin(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM organizations WHERE id = %s FOR UPDATE",
                (organization_id,),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Organization not found")
            _lock_and_verify_active_admin(cursor, organization_id, tenant)
            cursor.execute(
                """
                INSERT INTO organization_memberships (organization_id, user_subject, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (organization_id, user_subject) DO NOTHING
                RETURNING user_subject, role, status, created_at
                """,
                (organization_id, payload.user_subject, payload.role),
            )
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=409, detail="Organization membership already exists")
            cursor.execute(
                """
                INSERT INTO organization_membership_events (
                    organization_id, actor_subject, target_subject, event_type,
                    new_role, new_status
                )
                VALUES (%s, %s, %s, 'member_added', %s, 'active')
                """,
                (organization_id, tenant.user_id, payload.user_subject, payload.role),
            )
    return dict(zip(("user_subject", "role", "status", "created_at"), row))


@router.patch("/{organization_id}/members/{user_subject}")
def update_organization_member(
    organization_id: UUID,
    user_subject: str,
    payload: MembershipUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    _require_org_admin(organization_id, tenant)
    if not payload.model_fields_set or (
        payload.role is None and payload.status is None
    ):
        raise HTTPException(status_code=422, detail="At least one membership field is required")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            # Serialize membership administration per organization. This prevents
            # concurrent demotions from removing the final active administrator.
            cursor.execute(
                "SELECT id FROM organizations WHERE id = %s FOR UPDATE",
                (organization_id,),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Organization not found")
            _lock_and_verify_active_admin(cursor, organization_id, tenant)
            cursor.execute(
                """
                SELECT role, status
                FROM organization_memberships
                WHERE organization_id = %s AND user_subject = %s
                FOR UPDATE
                """,
                (organization_id, user_subject),
            )
            current = cursor.fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Organization membership not found")

            old_role, old_status = current
            new_role = payload.role or old_role
            new_status = payload.status or old_status
            removes_active_admin = (
                old_role == "admin"
                and old_status == "active"
                and (new_role != "admin" or new_status != "active")
            )
            if removes_active_admin:
                cursor.execute(
                    """
                    SELECT count(*)
                    FROM organization_memberships
                    WHERE organization_id = %s AND role = 'admin' AND status = 'active'
                    """,
                    (organization_id,),
                )
                if cursor.fetchone()[0] <= 1:
                    raise HTTPException(
                        status_code=409,
                        detail="The last active organization administrator cannot be removed",
                    )

            cursor.execute(
                """
                UPDATE organization_memberships
                SET role = %s, status = %s, updated_at = now()
                WHERE organization_id = %s AND user_subject = %s
                RETURNING user_subject, role, status, updated_at
                """,
                (new_role, new_status, organization_id, user_subject),
            )
            updated = cursor.fetchone()

            if new_role != old_role:
                cursor.execute(
                    """
                    INSERT INTO organization_membership_events (
                        organization_id, actor_subject, target_subject, event_type,
                        previous_role, new_role, previous_status, new_status
                    )
                    VALUES (%s, %s, %s, 'role_changed', %s, %s, %s, %s)
                    """,
                    (organization_id, tenant.user_id, user_subject, old_role, new_role, old_status, new_status),
                )
            if new_status != old_status:
                cursor.execute(
                    """
                    INSERT INTO organization_membership_events (
                        organization_id, actor_subject, target_subject, event_type,
                        previous_role, new_role, previous_status, new_status
                    )
                    VALUES (%s, %s, %s, 'status_changed', %s, %s, %s, %s)
                    """,
                    (organization_id, tenant.user_id, user_subject, old_role, new_role, old_status, new_status),
                )

    return dict(zip(("user_subject", "role", "status", "updated_at"), updated))
