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
                SELECT v.id, v.vehicle_id, v.odometer_km,
                       COALESCE(AVG(ft.litres), 0) AS avg_fuel_litres,
                       COUNT(DISTINCT me.id) AS maintenance_events,
                       COUNT(DISTINCT t.id) AS trips
                FROM vehicles v
                LEFT JOIN fuel_transactions ft ON ft.vehicle_id = v.id
                LEFT JOIN maintenance_events me ON me.vehicle_id = v.id
                LEFT JOIN trips t ON t.vehicle_id = v.id
                WHERE v.organization_id = %s
                GROUP BY v.id, v.vehicle_id, v.odometer_km
                ORDER BY v.vehicle_id
                """,
                (organization_id,),
            )
            rows = cursor.fetchall()

    result = []
    for vehicle_id, external_id, odometer, avg_fuel, maintenance_events, trips in rows:
        fuel_score = min(100.0, float(avg_fuel) * 4)
        maintenance_score = min(100.0, float(maintenance_events) * 15)
        utilization_score = 0.0 if trips > 10 else 35.0
        health = calculate_vehicle_health(external_id, fuel_score, maintenance_score, utilization_score)
        alerts = build_alerts(external_id, fuel_score, maintenance_score, utilization_score)
        result.append({
            "vehicle_id": external_id,
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
        })
    return result


@router.post("/rank-cost-risk")
def rank_cost_risk_compat() -> dict:
    return {"message": "Use GET /api/v1/fleet/{organization_id}/intelligence for tenant-scoped fleet intelligence."}
