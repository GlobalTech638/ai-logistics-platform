from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


class RecommendationAction(BaseModel):
    recommendation_type: str = Field(min_length=1, max_length=100)
    status: str = Field(pattern="^(accepted|rejected|completed)$")
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
                    status, notes, acted_by
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, organization_id, shipment_id,
                          recommendation_type, status, notes, acted_by, created_at
                """,
                (
                    organization_id,
                    shipment_id,
                    action.recommendation_type,
                    action.status,
                    action.notes,
                    tenant.user_id,
                ),
            )
            row = cursor.fetchone()
            columns = [item.name for item in cursor.description]

    return dict(zip(columns, row))


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
                       status, notes, acted_by, created_at
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
