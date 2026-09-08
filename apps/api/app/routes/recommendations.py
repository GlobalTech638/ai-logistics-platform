from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection
from app.services.recommendation_engine import build_recommendations
from app.services.vehicle_health import calculate_vehicle_health
from app.services.vehicle_health_signals import calculate_vehicle_health_signals

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
                ),
                vehicle_fuel AS (
                    SELECT
                        v.id AS vehicle_id,
                        COALESCE(SUM(f.litres), 0) AS actual_litres,
                        COALESCE(
                            SUM((t.distance_km / 100.0) * v.expected_litres_per_100km),
                            0
                        ) AS expected_litres
                    FROM vehicles v
                    LEFT JOIN fuel_transactions f
                        ON f.vehicle_id = v.id
                        AND f.organization_id = v.organization_id
                    LEFT JOIN trips t
                        ON t.id = f.trip_id
                        AND t.vehicle_id = v.id
                        AND t.organization_id = v.organization_id
                    WHERE v.organization_id = %s
                    GROUP BY v.id
                ),
                vehicle_maintenance AS (
                    SELECT vehicle_id, COUNT(*) AS maintenance_events
                    FROM maintenance_events
                    WHERE organization_id = %s
                    GROUP BY vehicle_id
                ),
                vehicle_trips AS (
                    SELECT
                        vehicle_id,
                        COUNT(*) AS trips,
                        COUNT(*) FILTER (WHERE completed_at IS NULL) AS active_trips
                    FROM trips
                    WHERE organization_id = %s
                    GROUP BY vehicle_id
                ),
                vehicle_metrics AS (
                    SELECT
                        v.id AS vehicle_id,
                        COALESCE(vf.actual_litres, 0) AS actual_litres,
                        COALESCE(vf.expected_litres, 0) AS expected_litres,
                        COALESCE(vm.maintenance_events, 0) AS maintenance_events,
                        COALESCE(vt.trips, 0) AS trips,
                        COALESCE(vt.active_trips, 0) AS active_trips
                    FROM vehicles v
                    LEFT JOIN vehicle_fuel vf ON vf.vehicle_id = v.id
                    LEFT JOIN vehicle_maintenance vm ON vm.vehicle_id = v.id
                    LEFT JOIN vehicle_trips vt ON vt.vehicle_id = v.id
                    WHERE v.organization_id = %s
                ),
                shipment_vehicle AS (
                    SELECT DISTINCT ON (t.shipment_id)
                        t.shipment_id,
                        t.vehicle_id
                    FROM trips t
                    WHERE t.organization_id = %s
                        AND t.shipment_id IS NOT NULL
                    ORDER BY
                        t.shipment_id,
                        (t.completed_at IS NULL) DESC,
                        t.completed_at DESC NULLS LAST,
                        t.id DESC
                )
                SELECT
                    s.id,
                    s.shipment_reference,
                    s.origin,
                    s.destination,
                    s.status,
                    COALESCE(MAX(a.score), 0) AS alert_score,
                    COALESCE(MAX(CASE WHEN a.alert_type = 'route_risk' THEN a.score ELSE 0 END), 0) AS corridor_score,
                    GREATEST(
                        0,
                        COALESCE(sf.actual_litres, 0) - COALESCE(sf.expected_litres, 0)
                    ) * COALESCE(sf.avg_price_per_litre, 0) AS estimated_excess_fuel_cost,
                    COALESCE(sf.currency, o.default_currency) AS fuel_currency,
                    COALESCE(vm.actual_litres, 0) AS vehicle_actual_litres,
                    COALESCE(vm.expected_litres, 0) AS vehicle_expected_litres,
                    COALESCE(vm.maintenance_events, 0) AS vehicle_maintenance_events,
                    COALESCE(vm.trips, 0) AS vehicle_trips,
                    COALESCE(vm.active_trips, 0) AS vehicle_active_trips
                FROM shipments s
                JOIN organizations o ON o.id = s.organization_id
                LEFT JOIN alerts a
                    ON a.shipment_id = s.id
                    AND a.organization_id = s.organization_id
                    AND a.status <> 'resolved'
                LEFT JOIN shipment_fuel sf ON sf.shipment_id = s.id
                LEFT JOIN shipment_vehicle sv ON sv.shipment_id = s.id
                LEFT JOIN vehicle_metrics vm ON vm.vehicle_id = sv.vehicle_id
                WHERE s.organization_id = %s
                    AND s.status IN ('pending', 'in_transit')
                GROUP BY
                    s.id, s.shipment_reference, s.origin, s.destination, s.status,
                    o.default_currency, sf.actual_litres, sf.expected_litres,
                    sf.avg_price_per_litre, sf.currency,
                    vm.actual_litres, vm.expected_litres, vm.maintenance_events,
                    vm.trips, vm.active_trips, s.created_at
                ORDER BY alert_score DESC, s.created_at ASC
                LIMIT 50
                """,
                (
                    organization_id,
                    organization_id,
                    organization_id,
                    organization_id,
                    organization_id,
                    organization_id,
                    organization_id,
                ),
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
            estimated_excess_fuel_cost,
            fuel_currency,
            vehicle_actual_litres,
            vehicle_expected_litres,
            vehicle_maintenance_events,
            vehicle_trips,
            vehicle_active_trips,
        ) = row
        shipment_score = float(alert_score or 0)
        corridor_risk = float(corridor_score or 0)
        health_signals = calculate_vehicle_health_signals(
            actual_fuel_litres=float(vehicle_actual_litres or 0),
            expected_fuel_litres=float(vehicle_expected_litres or 0),
            maintenance_events=int(vehicle_maintenance_events or 0),
            trips=int(vehicle_trips or 0),
            active_trips=int(vehicle_active_trips or 0),
        )
        vehicle_health = calculate_vehicle_health(
            str(shipment_id),
            fuel_anomaly_score=health_signals.fuel_score,
            maintenance_risk_score=health_signals.maintenance_score,
            corridor_risk_score=corridor_risk,
        ).health_score
        fuel_cost = float(estimated_excess_fuel_cost or 0)
        items = build_recommendations(
            str(shipment_id),
            shipment_score,
            "critical" if shipment_score >= 70 else "high" if shipment_score >= 45 else "medium" if shipment_score >= 25 else "low",
            corridor_risk_score=corridor_risk,
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
                "vehicle_health": {
                    "score": vehicle_health,
                    "signals": {
                        "fuel": round(health_signals.fuel_score, 1),
                        "maintenance": round(health_signals.maintenance_score, 1),
                        "utilization": round(health_signals.utilization_score, 1),
                    },
                },
                "fuel_cost_impact": {
                    "estimated_excess_cost": fuel_cost,
                    "currency": str(fuel_currency or "KES"),
                },
                "recommendations": [item.__dict__ for item in items],
            }
        )

    return {"organization_id": str(organization_id), "shipments": results}
