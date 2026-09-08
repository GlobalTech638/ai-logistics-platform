from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection
from app.services.route_plan_tracker import validate_transition

router = APIRouter(prefix="/api/v1/route-plans", tags=["route-plans"])
ACTION_ROLES = {"admin", "operations_manager", "fleet_manager"}


class RoutePlanCreate(BaseModel):
    corridor: str = Field(min_length=1, max_length=200)
    route_sequence: int = Field(default=1, ge=1)


class RoutePlanStatus(BaseModel):
    status: str = Field(pattern="^(planned|active|superseded)$")
    reroute_reason: str | None = Field(default=None, max_length=2000)


def _require_action_role(tenant: TenantContext) -> None:
    if tenant.role not in ACTION_ROLES:
        raise HTTPException(status_code=403, detail="Role is not authorized to manage route plans")


def _serialize_route_plan(cursor, row) -> dict:
    columns = [item.name for item in cursor.description]
    return dict(zip(columns, row))


@router.post("/{organization_id}/shipments/{shipment_id}")
def create_route_plan(
    organization_id: UUID,
    shipment_id: UUID,
    plan: RoutePlanCreate,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")
    _require_action_role(tenant)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM shipments WHERE id = %s AND organization_id = %s",
                (shipment_id, organization_id),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Shipment not found")

            cursor.execute(
                """
                INSERT INTO shipment_route_plans (
                    organization_id, shipment_id, corridor, route_sequence,
                    status, selected_by
                ) VALUES (%s, %s, %s, %s, 'planned', %s)
                RETURNING id, organization_id, shipment_id, corridor,
                          route_sequence, status, reroute_reason, selected_by,
                          created_at, updated_at
                """,
                (
                    organization_id,
                    shipment_id,
                    plan.corridor,
                    plan.route_sequence,
                    tenant.user_id,
                ),
            )
            row = cursor.fetchone()
            return _serialize_route_plan(cursor, row)


@router.get("/{organization_id}/shipments/{shipment_id}")
def list_route_plans(
    organization_id: UUID,
    shipment_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, shipment_id, corridor, route_sequence, status,
                       reroute_reason, selected_by, created_at, updated_at
                FROM shipment_route_plans
                WHERE organization_id = %s AND shipment_id = %s
                ORDER BY route_sequence, created_at
                """,
                (organization_id, shipment_id),
            )
            rows = cursor.fetchall()
            columns = [item.name for item in cursor.description]

    return {
        "organization_id": str(organization_id),
        "shipment_id": str(shipment_id),
        "route_plans": [dict(zip(columns, row)) for row in rows],
    }


@router.patch("/{organization_id}/plans/{plan_id}/status")
def update_route_plan_status(
    organization_id: UUID,
    plan_id: UUID,
    payload: RoutePlanStatus,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")
    _require_action_role(tenant)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, shipment_id, status
                FROM shipment_route_plans
                WHERE id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (plan_id, organization_id),
            )
            plan_row = cursor.fetchone()
            if not plan_row:
                raise HTTPException(status_code=404, detail="Route plan not found")

            _, shipment_id, current_status = plan_row
            if current_status == "superseded":
                raise HTTPException(status_code=409, detail="Superseded route plans are immutable")
            if payload.status == current_status:
                raise HTTPException(status_code=409, detail=f"Route plan is already {current_status}")

            try:
                validate_transition(current_status, payload.status)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            if payload.status == "active":
                cursor.execute(
                    """
                    UPDATE shipment_route_plans
                    SET status = 'superseded', updated_at = now()
                    WHERE organization_id = %s AND shipment_id = %s
                      AND status = 'active' AND id <> %s
                    """,
                    (organization_id, shipment_id, plan_id),
                )

            cursor.execute(
                """
                UPDATE shipment_route_plans
                SET status = %s,
                    reroute_reason = COALESCE(%s, reroute_reason),
                    selected_by = %s,
                    updated_at = now()
                WHERE id = %s AND organization_id = %s
                RETURNING id, organization_id, shipment_id, corridor,
                          route_sequence, status, reroute_reason, selected_by,
                          created_at, updated_at
                """,
                (
                    payload.status,
                    payload.reroute_reason,
                    tenant.user_id,
                    plan_id,
                    organization_id,
                ),
            )
            row = cursor.fetchone()
            return _serialize_route_plan(cursor, row)
