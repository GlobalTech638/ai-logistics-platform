from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection
from app.services.corridor_intelligence import assess_corridor_risk

router = APIRouter(prefix="/api/v1/corridors", tags=["corridor-intelligence"])


@router.get("/{organization_id}/risk")
def corridor_risk(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[dict]:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT origin, destination, COUNT(*) AS trip_count,
                       AVG(planned_duration_minutes) AS avg_planned_minutes,
                       AVG(actual_duration_minutes) AS avg_actual_minutes,
                       AVG(CASE WHEN actual_duration_minutes > planned_duration_minutes THEN 1.0 ELSE 0.0 END) * 100 AS delay_rate_pct,
                       AVG(GREATEST(actual_duration_minutes - planned_duration_minutes, 0)) AS avg_delay_minutes
                FROM trips
                WHERE organization_id = %s AND completed_at IS NOT NULL
                GROUP BY origin, destination
                ORDER BY delay_rate_pct DESC, trip_count DESC, origin, destination
                """,
                (organization_id,),
            )
            rows = cursor.fetchall()

    result = []
    for origin, destination, trip_count, avg_planned, avg_actual, delay_rate, avg_delay in rows:
        corridor = f"{origin} → {destination}"
        risk = assess_corridor_risk(corridor, float(delay_rate or 0))
        result.append({
            "corridor": corridor,
            "origin": origin,
            "destination": destination,
            "trip_count": int(trip_count),
            "average_planned_duration_minutes": round(float(avg_planned or 0), 1),
            "average_actual_duration_minutes": round(float(avg_actual or 0), 1),
            "delay_rate_pct": round(float(delay_rate or 0), 1),
            "average_delay_minutes": round(float(avg_delay or 0), 1),
            "risk_score": risk.risk_score,
            "risk_level": risk.risk_level,
            "primary_factors": risk.primary_factors,
            "recommended_action": risk.recommended_action,
        })
    return result
