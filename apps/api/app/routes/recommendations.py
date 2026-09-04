from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection
from app.services.recommendation_engine import build_recommendations

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get("/{organization_id}")
def recommendations(
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
                    s.id,
                    s.shipment_reference,
                    s.origin,
                    s.destination,
                    s.status,
                    COALESCE(MAX(a.score), 0) AS alert_score,
                    COALESCE(MAX(CASE WHEN a.alert_type = 'route_risk' THEN a.score ELSE 0 END), 0) AS corridor_score,
                    COALESCE(MAX(CASE WHEN a.alert_type = 'maintenance_risk' THEN a.score ELSE 0 END), 0) AS vehicle_alert_score,
                    COALESCE(MAX(CASE WHEN a.alert_type = 'fuel_anomaly' THEN a.score ELSE 0 END), 0) AS fuel_alert_score
                FROM shipments s
                LEFT JOIN alerts a
                    ON a.shipment_id = s.id
                    AND a.organization_id = s.organization_id
                    AND a.status <> 'resolved'
                WHERE s.organization_id = %s
                    AND s.status IN ('pending', 'in_transit')
                GROUP BY s.id, s.shipment_reference, s.origin, s.destination, s.status
                ORDER BY alert_score DESC, s.created_at ASC
                LIMIT 50
                """,
                (organization_id,),
            )
            rows = cursor.fetchall()

    results = []
    for row in rows:
        shipment_id, reference, origin, destination, status, alert_score, corridor_score, vehicle_alert_score, fuel_alert_score = row
        shipment_score = float(alert_score or 0)
        vehicle_health = max(0.0, 100.0 - float(vehicle_alert_score or 0))
        fuel_cost = float(fuel_alert_score or 0)
        items = build_recommendations(
            str(shipment_id),
            shipment_score,
            "critical" if shipment_score >= 70 else "high" if shipment_score >= 45 else "medium" if shipment_score >= 25 else "low",
            corridor_risk_score=float(corridor_score or 0),
            vehicle_health_score=vehicle_health,
            estimated_excess_fuel_cost=fuel_cost,
        )
        results.append(
            {
                "shipment_id": str(shipment_id),
                "shipment_reference": reference,
                "route": {"origin": origin, "destination": destination},
                "status": status,
                "recommendations": [item.__dict__ for item in items],
            }
        )

    return {"organization_id": str(organization_id), "shipments": results}
