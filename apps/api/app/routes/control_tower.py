from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection

router = APIRouter(prefix="/api/v1/control-tower", tags=["control-tower"])


@router.get("/{organization_id}/overview")
def overview(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'active') AS active
                FROM vehicles
                WHERE organization_id = %s
                """,
                (organization_id,),
            )
            fleet = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('pending', 'in_transit')) AS active,
                    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered
                FROM shipments
                WHERE organization_id = %s
                """,
                (organization_id,),
            )
            shipments = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS open_alerts,
                    COUNT(*) FILTER (WHERE severity = 'critical') AS critical,
                    COUNT(*) FILTER (WHERE severity = 'high') AS high,
                    COUNT(*) FILTER (WHERE severity = 'medium') AS medium
                FROM alerts
                WHERE organization_id = %s AND status <> 'resolved'
                """,
                (organization_id,),
            )
            alerts = cursor.fetchone()

    return {
        "organization_id": str(organization_id),
        "fleet": {"total": fleet[0], "active": fleet[1]},
        "shipments": {"active": shipments[0], "delivered": shipments[1]},
        "alerts": {
            "open": alerts[0],
            "critical": alerts[1],
            "high": alerts[2],
            "medium": alerts[3],
        },
    }
