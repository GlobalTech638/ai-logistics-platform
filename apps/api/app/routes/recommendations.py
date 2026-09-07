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
                WITH shipment_fuel AS (
                    SELECT
                        t.shipment_id,
                        SUM(f.litres) AS actual_litres,
                        SUM(
                            (t.distance_km / 100.0) * v.expected_litres_per_100km
                        ) AS expected_litres,
                        AVG(f.price_per_litre) AS avg_price_per_litre,
                        MIN(f.currency) AS currency
                    FROM trips t
                    JOIN vehicles v ON v.id = t.vehicle_id
                        AND v.organization_id = t.organization_id
                    JOIN fuel_transactions f ON f.trip_id = t.id
                        AND f.organization_id = t.organization_id
                    WHERE t.organization_id = %s
                    GROUP BY t.shipment_id
                )
                SELECT
                    s.id,
                    s.shipment_reference,
                    s.origin,
                    s.destination,
                    s.status,
                    COALESCE(MAX(a.score), 0) AS alert_score,
                    COALESCE(MAX(CASE WHEN a.alert_type = 'route_risk' THEN a.score ELSE 0 END), 0) AS corridor_score,
                    COALESCE(MAX(CASE WHEN a.alert_type = 'maintenance_risk' THEN a.score ELSE 0 END), 0) AS vehicle_alert_score,
                    GREATEST(
                        0,
                        COALESCE(sf.actual_litres, 0) - COALESCE(sf.expected_litres, 0)
                    ) * COALESCE(sf.avg_price_per_litre, 0) AS estimated_excess_fuel_cost,
                    COALESCE(sf.currency, o.default_currency) AS fuel_currency
                FROM shipments s
                JOIN organizations o ON o.id = s.organization_id
                LEFT JOIN alerts a
                    ON a.shipment_id = s.id
                    AND a.organization_id = s.organization_id
                    AND a.status <> 'resolved'
                LEFT JOIN shipment_fuel sf ON sf.shipment_id = s.id
                WHERE s.organization_id = %s
                    AND s.status IN ('pending', 'in_transit')
                GROUP BY
                    s.id, s.shipment_reference, s.origin, s.destination, s.status,
                    o.default_currency, sf.actual_litres, sf.expected_litres,
                    sf.avg_price_per_litre, sf.currency, s.created_at
                ORDER BY alert_score DESC, s.created_at ASC
                LIMIT 50
                """,
                (organization_id, organization_id),
            )
            rows = cursor.fetchall()

    results = []
    for row in rows:
        (
            shipment_id,
            reference,
            origin,
            destination,
            status,
            alert_score,
            corridor_score,
            vehicle_alert_score,
            estimated_excess_fuel_cost,
            fuel_currency,
        ) = row
        shipment_score = float(alert_score or 0)
        vehicle_health = max(0.0, 100.0 - float(vehicle_alert_score or 0))
        fuel_cost = float(estimated_excess_fuel_cost or 0)
        items = build_recommendations(
            str(shipment_id),
            shipment_score,
            "critical" if shipment_score >= 70 else "high" if shipment_score >= 45 else "medium" if shipment_score >= 25 else "low",
            corridor_risk_score=float(corridor_score or 0),
            vehicle_health_score=vehicle_health,
            estimated_excess_fuel_cost=fuel_cost,
            currency=str(fuel_currency or "KES"),
        )
        results.append(
            {
                "shipment_id": str(shipment_id),
                "shipment_reference": reference,
                "route": {"origin": origin, "destination": destination},
                "status": status,
                "fuel_cost_impact": {
                    "estimated_excess_cost": fuel_cost,
                    "currency": str(fuel_currency or "KES"),
                },
                "recommendations": [item.__dict__ for item in items],
            }
        )

    return {"organization_id": str(organization_id), "shipments": results}
