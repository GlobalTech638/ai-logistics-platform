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
                SELECT
                    v.id,
                    v.registration_number,
                    v.odometer_km,
                    v.expected_litres_per_100km,
                    COALESCE(SUM(ft.litres), 0) AS actual_fuel_litres,
                    COALESCE(SUM((t.distance_km / 100.0) * v.expected_litres_per_100km), 0)
                        AS expected_fuel_litres,
                    COUNT(DISTINCT me.id) AS maintenance_events,
                    COUNT(DISTINCT t.id) AS trips,
                    COUNT(DISTINCT CASE WHEN t.completed_at IS NULL THEN t.id END) AS active_trips
                FROM vehicles v
                LEFT JOIN fuel_transactions ft
                    ON ft.vehicle_id = v.id
                    AND ft.organization_id = v.organization_id
                LEFT JOIN trips t
                    ON t.vehicle_id = v.id
                    AND t.organization_id = v.organization_id
                LEFT JOIN maintenance_events me
                    ON me.vehicle_id = v.id
                    AND me.organization_id = v.organization_id
                WHERE v.organization_id = %s
                GROUP BY v.id, v.registration_number, v.odometer_km,
                         v.expected_litres_per_100km
                ORDER BY v.registration_number
                """,
                (organization_id,),
            )
            rows = cursor.fetchall()

    result = []
    for (
        vehicle_id,
        registration_number,
        odometer,
        expected_litres_per_100km,
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
