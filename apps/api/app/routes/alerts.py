from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

_ALLOWED_TRANSITIONS = {
    "open": {"acknowledged", "resolved"},
    "acknowledged": {"in_progress", "resolved"},
    "in_progress": {"resolved"},
    "resolved": set(),
}


@router.patch("/{alert_id}/status")
def update_alert_status(
    alert_id: UUID,
    status: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    if status not in _ALLOWED_TRANSITIONS:
        raise HTTPException(status_code=400, detail="Invalid alert status")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM alerts WHERE id = %s AND organization_id = %s",
                (alert_id, tenant.organization_id),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Alert not found")

            current_status = row[0]
            if status not in _ALLOWED_TRANSITIONS[current_status]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot transition alert from {current_status} to {status}",
                )

            cursor.execute(
                """
                UPDATE alerts
                SET status = %s
                WHERE id = %s AND organization_id = %s
                RETURNING id, status, created_at
                """,
                (status, alert_id, tenant.organization_id),
            )
            updated = cursor.fetchone()
            columns = [item.name for item in cursor.description]
            return dict(zip(columns, updated))
