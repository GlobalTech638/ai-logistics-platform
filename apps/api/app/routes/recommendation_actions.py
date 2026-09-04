from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])

_ALLOWED_TRANSITIONS = {
    "proposed": {"accepted", "rejected"},
    "accepted": {"in_progress", "rejected"},
    "in_progress": {"completed"},
    "completed": set(),
    "rejected": set(),
}


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


@router.post("/{organization_id}/shipments/{shipment_id}/actions")
def record_recommendation_action(
    organization_id: UUID,
    shipment_id: UUID,
    action: RecommendationAction,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

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
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'proposed', %s, %s)
                RETURNING id, organization_id, shipment_id,
                          recommendation_type, priority, recommendation_score,
                          title, rationale, expected_impact, status,
                          notes, acted_by, created_at, updated_at
                """,
                (
                    organization_id,
                    shipment_id,
                    action.recommendation_type,
                    action.priority,
                    action.recommendation_score,
                    action.title,
                    action.rationale,
                    action.expected_impact,
                    action.notes,
                    tenant.user_id,
                ),
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
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status
                FROM recommendation_actions
                WHERE id = %s AND organization_id = %s
                """,
                (action_id, tenant.organization_id),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Recommendation action not found")

            current_status = row[0]
            if payload.status not in _ALLOWED_TRANSITIONS[current_status]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot transition recommendation action from {current_status} to {payload.status}",
                )

            completed_at_sql = "completed_at = now()," if payload.status == "completed" else ""
            cursor.execute(
                f"""
                UPDATE recommendation_actions
                SET status = %s,
                    notes = COALESCE(%s, notes),
                    acted_by = %s,
                    updated_at = now(),
                    {completed_at_sql}
                WHERE id = %s AND organization_id = %s
                RETURNING id, shipment_id, recommendation_type,
                          priority, recommendation_score, title, rationale,
                          expected_impact, status, notes, acted_by,
                          created_at, updated_at, completed_at
                """,
                (
                    payload.status,
                    payload.notes,
                    tenant.user_id,
                    action_id,
                    tenant.organization_id,
                ),
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
                SELECT id, shipment_id, recommendation_type,
                       priority, recommendation_score, title, rationale,
                       expected_impact, status, notes, acted_by,
                       created_at, updated_at, completed_at
                FROM recommendation_actions
                WHERE organization_id = %s
                ORDER BY created_at DESC
                LIMIT 100
                """,
                (organization_id,),
            )
            rows = cursor.fetchall()
            columns = [item.name for item in cursor.description]

    return {
        "organization_id": str(organization_id),
        "actions": [dict(zip(columns, row)) for row in rows],
    }
