from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection
from app.services.alert_engine import build_alerts
from app.services.vehicle_health import calculate_vehicle_health

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet-intelligence"])


@router.get("/{organization_id}/intelligence")
def fleet_intelligence(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[dict]:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH fuel_metrics AS (
                    SELECT
                        v.id AS vehicle_id,
                        COALESCE(SUM(ft.litres), 0) AS actual_fuel_litres,
                        COALESCE(
                            SUM((t.distance_km / 100.0) * v.expected_litres_per_100km),
                            0
                        ) AS expected_fuel_litres
                    FROM vehicles v
                    LEFT JOIN fuel_transactions ft
                        ON ft.vehicle_id = v.id
                        AND ft.organization_id = v.organization_id
                    LEFT JOIN trips t
                        ON t.id = ft.trip_id
                        AND t.vehicle_id = v.id
                        AND t.organization_id = v.organization_id
                    WHERE v.organization_id = %s
                    GROUP BY v.id
                ),
                maintenance_metrics AS (
                    SELECT vehicle_id, COUNT(*) AS maintenance_events
                    FROM maintenance_events
                    WHERE organization_id = %s
                    GROUP BY vehicle_id
                ),
                trip_metrics AS (
                    SELECT
                        vehicle_id,
                        COUNT(*) AS trips,
                        COUNT(*) FILTER (WHERE completed_at IS NULL) AS active_trips
                    FROM trips
                    WHERE organization_id = %s
                    GROUP BY vehicle_id
                )
                SELECT
                    v.id,
                    v.registration_number,
                    v.odometer_km,
                    COALESCE(fm.actual_fuel_litres, 0),
                    COALESCE(fm.expected_fuel_litres, 0),
                    COALESCE(mm.maintenance_events, 0),
                    COALESCE(tm.trips, 0),
                    COALESCE(tm.active_trips, 0)
                FROM vehicles v
                LEFT JOIN fuel_metrics fm ON fm.vehicle_id = v.id
                LEFT JOIN maintenance_metrics mm ON mm.vehicle_id = v.id
                LEFT JOIN trip_metrics tm ON tm.vehicle_id = v.id
                WHERE v.organization_id = %s
                ORDER BY v.registration_number
                """,
                (organization_id, organization_id, organization_id, organization_id),
            )
            rows = cursor.fetchall()

    result = []
    for (
        vehicle_id,
        registration_number,
        odometer,
        actual_fuel_litres,
        expected_fuel_litres,
        maintenance_events,
        trips,
        active_trips,
    ) in rows:
        expected = float(expected_fuel_litres or 0)
        actual = float(actual_fuel_litres or 0)
        fuel_variance_pct = 0.0 if expected <= 0 else max(0.0, ((actual - expected) / expected) * 100)
        fuel_score = min(100.0, fuel_variance_pct * 2)

        # This is an operational baseline until service intervals are modeled explicitly.
        maintenance_score = min(100.0, float(maintenance_events) * 15)
        utilization_score = min(100.0, (float(active_trips) * 20) + (float(trips) * 2))

        health = calculate_vehicle_health(
            registration_number,
            fuel_score,
            maintenance_score,
            utilization_score,
        )
        alerts = build_alerts(
            registration_number,
            fuel_score,
            maintenance_score,
            utilization_score,
        )
        result.append(
            {
                "vehicle_id": registration_number,
                "odometer_km": float(odometer or 0),
                "health": {
                    "score": health.health_score,
                    "status": health.status,
                    "priority": health.priority,
                },
                "signals": {
                    "fuel": round(fuel_score, 1),
                    "maintenance": round(maintenance_score, 1),
                    "utilization": round(utilization_score, 1),
                },
                "alerts": [a.__dict__ for a in alerts],
            }
        )
    return result


@router.post("/rank-cost-risk")
def rank_cost_risk_compat() -> dict:
    return {"message": "Use GET /api/v1/fleet/{organization_id}/intelligence for tenant-scoped fleet intelligence."}
