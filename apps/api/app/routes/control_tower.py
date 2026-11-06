from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

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
                    COUNT(*) FILTER (WHERE active IS TRUE) AS active
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
                    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                    COUNT(*) FILTER (
                        WHERE status IN ('pending', 'in_transit')
                          AND delivery_at < now()
                    ) AS overdue_deliveries,
                    COUNT(*) FILTER (
                        WHERE status IN ('pending', 'in_transit')
                          AND delivery_at >= now()
                          AND delivery_at <= now() + INTERVAL '2 hours'
                    ) AS due_soon,
                    COUNT(*) FILTER (
                        WHERE status = 'pending' AND pickup_at < now()
                    ) AS missed_pickups
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
        "shipments": {
            "active": shipments[0],
            "delivered": shipments[1],
            "overdue_deliveries": shipments[2],
            "due_soon": shipments[3],
            "missed_pickups": shipments[4],
        },
        "alerts": {
            "open": alerts[0],
            "critical": alerts[1],
            "high": alerts[2],
            "medium": alerts[3],
        },
    }


@router.get("/{organization_id}/shipment-exceptions")
def shipment_exceptions(
    organization_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Surface pending pickups and shipments at or near their delivery SLA."""
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.shipment_reference, s.origin, s.destination,
                       s.status, s.pickup_at, s.delivery_at,
                       CASE
                           WHEN s.status = 'pending' AND s.pickup_at < now()
                               THEN 'missed_pickup'
                           WHEN s.delivery_at < now()
                               THEN 'overdue_delivery'
                           ELSE 'delivery_due_soon'
                       END AS exception_type,
                       CASE
                           WHEN s.status = 'pending' AND s.pickup_at < now()
                               THEN FLOOR(EXTRACT(EPOCH FROM (s.pickup_at - now())) / 60)::integer
                           ELSE FLOOR(EXTRACT(EPOCH FROM (s.delivery_at - now())) / 60)::integer
                       END AS minutes_to_due,
                       latest.occurred_at AS last_event_at,
                       COUNT(*) OVER() AS total_count
                FROM shipments s
                LEFT JOIN LATERAL (
                    SELECT occurred_at
                    FROM shipment_events e
                    WHERE e.organization_id = s.organization_id
                      AND e.shipment_id = s.id
                    ORDER BY occurred_at DESC, id DESC
                    LIMIT 1
                ) latest ON TRUE
                WHERE s.organization_id = %s
                  AND s.status IN ('pending', 'in_transit')
                  AND (
                      (s.status = 'pending' AND s.pickup_at < now())
                      OR s.delivery_at <= now() + INTERVAL '2 hours'
                  )
                ORDER BY
                    CASE
                        WHEN s.status = 'pending' AND s.pickup_at < now() THEN 0
                        WHEN s.delivery_at < now() THEN 1
                        ELSE 2
                    END,
                    COALESCE(
                        CASE WHEN s.status = 'pending' AND s.pickup_at < now()
                             THEN s.pickup_at ELSE s.delivery_at END,
                        s.created_at
                    ) ASC
                LIMIT %s
                """,
                (organization_id, limit),
            )
            rows = cursor.fetchall()

    return {
        "organization_id": str(organization_id),
        "total_count": int(rows[0][10]) if rows else 0,
        "returned_count": len(rows),
        "exceptions": [
            {
                "shipment_id": str(row[0]),
                "shipment_reference": row[1],
                "origin": row[2],
                "destination": row[3],
                "status": row[4],
                "pickup_at": row[5].isoformat() if row[5] else None,
                "delivery_at": row[6].isoformat() if row[6] else None,
                "exception_type": row[7],
                "minutes_to_due": row[8],
                "last_event_at": row[9].isoformat() if row[9] else None,
            }
            for row in rows
        ],
    }
