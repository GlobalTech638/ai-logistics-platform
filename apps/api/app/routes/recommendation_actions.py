from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection
from app.services.action_tracker import completed_at_for_status, validate_transition

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])
ACTION_ROLES = {"admin", "operations_manager", "fleet_manager"}


class RecommendationAction(BaseModel):
    recommendation_type: str = Field(min_length=1, max_length=100)
    priority: str = Field(default="medium", pattern="^(critical|high|medium|low)$")
    recommendation_score: float = Field(default=0, ge=0, le=100)
    title: str | None = Field(default=None, max_length=500)
    rationale: str | None = Field(default=None, max_length=2000)
    expected_impact: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)


class RecommendationActionStatus(BaseModel):
    status: str = Field(pattern="^(accepted|in_progress|completed|rejected)$")
    notes: str | None = Field(default=None, max_length=2000)
    vehicle_id: UUID | None = None


def _require_action_role(tenant: TenantContext) -> None:
    if tenant.role not in ACTION_ROLES:
        raise HTTPException(status_code=403, detail="Role is not authorized to execute recommendations")


def _execute_reassignment(cursor, organization_id: UUID, shipment_id: UUID, vehicle_id: UUID | None) -> str:
    if vehicle_id is None:
        raise HTTPException(status_code=422, detail="vehicle_id is required to start a reassign_vehicle action")

    cursor.execute(
        """
        SELECT s.weight_tonnes, v.capacity_tonnes, v.active
        FROM shipments s CROSS JOIN vehicles v
        WHERE s.id = %s AND s.organization_id = %s
          AND v.id = %s AND v.organization_id = %s
        """,
        (shipment_id, organization_id, vehicle_id, organization_id),
    )
    assignment = cursor.fetchone()
    if not assignment:
        raise HTTPException(status_code=404, detail="Shipment or replacement vehicle not found")

    weight_tonnes, capacity_tonnes, active = assignment
    if not active:
        raise HTTPException(status_code=409, detail="Replacement vehicle is inactive")
    if capacity_tonnes is not None and capacity_tonnes < weight_tonnes:
        raise HTTPException(status_code=409, detail="Replacement vehicle capacity is below shipment weight")

    cursor.execute(
        """
        SELECT id, vehicle_id FROM trips
        WHERE organization_id = %s AND shipment_id = %s AND completed_at IS NULL
        ORDER BY id DESC LIMIT 1 FOR UPDATE
        """,
        (organization_id, shipment_id),
    )
    trip = cursor.fetchone()
    if not trip:
        raise HTTPException(status_code=409, detail="No active trip assignment found for shipment")

    trip_id, previous_vehicle_id = trip
    if previous_vehicle_id == vehicle_id:
        return f"Trip {trip_id} already assigned to vehicle {vehicle_id}"

    cursor.execute(
        "UPDATE trips SET vehicle_id = %s WHERE id = %s AND organization_id = %s",
        (vehicle_id, trip_id, organization_id),
    )
    return f"Trip {trip_id} reassigned from vehicle {previous_vehicle_id} to {vehicle_id}"


@router.post("/{organization_id}/shipments/{shipment_id}/actions")
def record_recommendation_action(
    organization_id: UUID,
    shipment_id: UUID,
    action: RecommendationAction,
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
                INSERT INTO recommendation_actions (
                    organization_id, shipment_id, recommendation_type,
                    priority, recommendation_score, title, rationale,
                    expected_impact, status, notes, acted_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'proposed', %s, %s)
                RETURNING id, organization_id, shipment_id, recommendation_type,
                          priority, recommendation_score, title, rationale,
                          expected_impact, status, notes, acted_by, created_at, updated_at
                """,
                (organization_id, shipment_id, action.recommendation_type,
                 action.priority, action.recommendation_score, action.title,
                 action.rationale, action.expected_impact, action.notes, tenant.user_id),
            )
            row = cursor.fetchone()
            columns = [item.name for item in cursor.description]

    return dict(zip(columns, row))


@router.patch("/actions/{action_id}/status")
def update_recommendation_action_status(
    action_id: UUID,
    payload: RecommendationActionStatus,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    _require_action_role(tenant)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, shipment_id, recommendation_type, notes
                FROM recommendation_actions
                WHERE id = %s AND organization_id = %s FOR UPDATE
                """,
                (action_id, tenant.organization_id),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Recommendation action not found")

            current_status, shipment_id, recommendation_type, current_notes = row
            try:
                validate_transition(current_status, payload.status)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            execution_note = None
            if payload.status == "in_progress" and recommendation_type == "reassign_vehicle":
                if shipment_id is None:
                    raise HTTPException(status_code=409, detail="Reassignment action has no shipment")
                execution_note = _execute_reassignment(
                    cursor, tenant.organization_id, shipment_id, payload.vehicle_id
                )

            notes = payload.notes if payload.notes is not None else current_notes
            if execution_note:
                notes = f"{notes}\nExecution: {execution_note}" if notes else f"Execution: {execution_note}"

            completed_at = completed_at_for_status(payload.status)
            cursor.execute(
                """
                UPDATE recommendation_actions
                SET status = %s, notes = %s, acted_by = %s,
                    updated_at = now(), completed_at = COALESCE(%s, completed_at)
                WHERE id = %s AND organization_id = %s
                RETURNING id, shipment_id, recommendation_type, priority,
                          recommendation_score, title, rationale, expected_impact,
                          status, notes, acted_by, created_at, updated_at, completed_at
                """,
                (payload.status, notes, tenant.user_id, completed_at,
                 action_id, tenant.organization_id),
            )
            updated = cursor.fetchone()
            columns = [item.name for item in cursor.description]

    return dict(zip(columns, updated))


@router.get("/{organization_id}/actions")
def list_recommendation_actions(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, shipment_id, recommendation_type, priority,
                       recommendation_score, title, rationale, expected_impact,
                       status, notes, acted_by, created_at, updated_at, completed_at
                FROM recommendation_actions
                WHERE organization_id = %s
                ORDER BY created_at DESC LIMIT 100
                """,
                (organization_id,),
            )
            rows = cursor.fetchall()
            columns = [item.name for item in cursor.description]

    return {"organization_id": str(organization_id), "actions": [dict(zip(columns, row)) for row in rows]}
