from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context, require_current_role
from app.db.database import get_connection

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


class VehicleCreate(BaseModel):
    registration_number: str = Field(min_length=1, max_length=100)
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    fuel_type: str = Field(default="diesel", min_length=1, max_length=30)
    expected_litres_per_100km: float = Field(default=20, gt=0)
    capacity_tonnes: float | None = Field(default=None, gt=0)
    odometer_km: float = Field(default=0, ge=0)
    active: bool = True


class ShipmentCreate(BaseModel):
    shipment_reference: str = Field(min_length=1, max_length=100)
    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    weight_tonnes: float = Field(gt=0)
    pickup_at: str | None = None
    delivery_at: str | None = None
    status: str = Field(default="pending", min_length=1, max_length=30)


def require_org(organization_id: UUID, tenant: TenantContext) -> None:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")


@router.post("/{organization_id}/vehicles")
def create_vehicle(
    organization_id: UUID,
    payload: VehicleCreate,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_current_role(
                cursor, tenant, {"admin", "operations_manager", "fleet_manager"},
                "Role is not authorized to create operational records",
            )
            cursor.execute(
                """
                INSERT INTO vehicles (
                    organization_id, registration_number, make, model, fuel_type,
                    expected_litres_per_100km, capacity_tonnes, odometer_km, active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, organization_id, registration_number, make, model,
                          fuel_type, expected_litres_per_100km, capacity_tonnes,
                          odometer_km, active, created_at
                """,
                (
                    organization_id, payload.registration_number.strip(),
                    payload.make.strip(), payload.model.strip(), payload.fuel_type.strip(),
                    payload.expected_litres_per_100km, payload.capacity_tonnes,
                    payload.odometer_km, payload.active,
                ),
            )
            row = cursor.fetchone()
            columns = [item.name for item in cursor.description]
            return dict(zip(columns, row))


@router.post("/{organization_id}/shipments")
def create_shipment(
    organization_id: UUID,
    payload: ShipmentCreate,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_current_role(
                cursor, tenant, {"admin", "operations_manager", "fleet_manager"},
                "Role is not authorized to create operational records",
            )
            cursor.execute(
                """
                INSERT INTO shipments (
                    organization_id, shipment_reference, origin, destination,
                    weight_tonnes, pickup_at, delivery_at, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, organization_id, shipment_reference, origin,
                          destination, weight_tonnes, pickup_at, delivery_at,
                          status, created_at
                """,
                (
                    organization_id, payload.shipment_reference.strip(),
                    payload.origin.strip(), payload.destination.strip(),
                    payload.weight_tonnes, payload.pickup_at, payload.delivery_at,
                    payload.status.strip(),
                ),
            )
            row = cursor.fetchone()
            columns = [item.name for item in cursor.description]
            return dict(zip(columns, row))


@router.get("/{organization_id}/alerts")
def open_alerts(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[dict]:
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, vehicle_id, shipment_id, alert_type, severity, score,
                       message, recommended_action, created_at
                FROM alerts
                WHERE organization_id = %s AND status = 'open'
                ORDER BY created_at DESC
                """,
                (organization_id,),
            )
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


@router.get("/{organization_id}/dispatch-queue")
def dispatch_queue(
    organization_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    """List pending shipments and classify dispatch readiness without mutating state."""
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH pending_shipments AS (
                    SELECT s.id, s.shipment_reference, s.origin, s.destination,
                           s.weight_tonnes, s.pickup_at, s.created_at,
                           EXISTS (
                               SELECT 1 FROM trips t
                               WHERE t.organization_id = s.organization_id
                                 AND t.shipment_id = s.id
                                 AND t.completed_at IS NULL
                           ) AS assigned,
                           (
                               SELECT COUNT(*)
                               FROM vehicles v
                               WHERE v.organization_id = s.organization_id
                                 AND v.active IS TRUE
                                 AND v.capacity_tonnes >= s.weight_tonnes
                                 AND NOT EXISTS (
                                     SELECT 1 FROM trips busy
                                     WHERE busy.organization_id = v.organization_id
                                       AND busy.vehicle_id = v.id
                                       AND busy.completed_at IS NULL
                                 )
                           ) AS eligible_vehicle_count
                    FROM shipments s
                    WHERE s.organization_id = %s
                      AND s.status = 'pending'
                )
                SELECT id, shipment_reference, origin, destination, weight_tonnes,
                       pickup_at, created_at, assigned, eligible_vehicle_count,
                       COUNT(*) OVER() AS total_count
                FROM pending_shipments
                ORDER BY created_at ASC, id ASC
                LIMIT %s OFFSET %s
                """,
                (organization_id, limit, offset),
            )
            rows = cursor.fetchall()

    shipments = []
    total_count = rows[0][9] if rows else 0
    for row in rows:
        (
            shipment_id, reference, origin, destination, weight, pickup_at,
            created_at, assigned, eligible_count, _total,
        ) = row
        dispatch_state = (
            "assigned" if assigned else "ready" if eligible_count > 0 else "blocked"
        )
        shipments.append({
            "shipment_id": str(shipment_id),
            "shipment_reference": reference,
            "origin": origin,
            "destination": destination,
            "weight_tonnes": float(weight),
            "pickup_at": pickup_at.isoformat() if pickup_at else None,
            "created_at": created_at.isoformat(),
            "dispatch_state": dispatch_state,
            "eligible_vehicle_count": int(eligible_count),
        })

    return {
        "organization_id": str(organization_id),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "summary": {
            "ready": sum(item["dispatch_state"] == "ready" for item in shipments),
            "blocked": sum(item["dispatch_state"] == "blocked" for item in shipments),
            "assigned": sum(item["dispatch_state"] == "assigned" for item in shipments),
        },
        "shipments": shipments,
    }


@router.get("/{organization_id}/shipments/{shipment_id}/dispatch-candidates")
def dispatch_candidates(
    organization_id: UUID,
    shipment_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Return explainable, currently available vehicle candidates for a shipment."""
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT weight_tonnes, shipment_reference
                FROM shipments
                WHERE id = %s AND organization_id = %s
                """,
                (shipment_id, organization_id),
            )
            shipment = cursor.fetchone()
            if shipment is None:
                raise HTTPException(status_code=404, detail="Shipment not found")

            shipment_weight, shipment_reference = shipment
            cursor.execute(
                """
                WITH fuel_by_trip AS (
                    SELECT
                        f.trip_id,
                        SUM(f.litres) AS actual_litres
                    FROM fuel_transactions f
                    WHERE f.organization_id = %s
                      AND f.trip_id IS NOT NULL
                    GROUP BY f.trip_id
                ),
                fuel_metrics AS (
                    SELECT
                        t.vehicle_id,
                        SUM(fbt.actual_litres) AS actual_litres,
                        SUM((t.distance_km / 100.0) * v.expected_litres_per_100km)
                            AS expected_litres
                    FROM trips t
                    JOIN vehicles v
                      ON v.id = t.vehicle_id
                     AND v.organization_id = t.organization_id
                    JOIN fuel_by_trip fbt ON fbt.trip_id = t.id
                    WHERE t.organization_id = %s
                    GROUP BY t.vehicle_id
                ),
                maintenance_metrics AS (
                    SELECT
                        vehicle_id,
                        COUNT(*) AS maintenance_events
                    FROM maintenance_events
                    WHERE organization_id = %s
                      AND completed_at >= now() - INTERVAL '365 days'
                    GROUP BY vehicle_id
                )
                SELECT
                    v.id,
                    v.registration_number,
                    v.make,
                    v.model,
                    v.capacity_tonnes,
                    v.expected_litres_per_100km,
                    COALESCE(fm.actual_litres, 0) AS actual_litres,
                    COALESCE(fm.expected_litres, 0) AS expected_litres,
                    COALESCE(mm.maintenance_events, 0) AS maintenance_events,
                    CASE
                        WHEN COALESCE(fm.expected_litres, 0) > 0
                        THEN GREATEST(
                            0,
                            (fm.actual_litres / fm.expected_litres) - 1
                        )
                        ELSE 0
                    END AS fuel_variance_ratio
                FROM vehicles v
                LEFT JOIN fuel_metrics fm
                  ON fm.vehicle_id = v.id
                LEFT JOIN maintenance_metrics mm
                  ON mm.vehicle_id = v.id
                WHERE v.organization_id = %s
                  AND v.active IS TRUE
                  AND v.capacity_tonnes >= %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM trips active_trip
                      WHERE active_trip.organization_id = v.organization_id
                        AND active_trip.vehicle_id = v.id
                        AND active_trip.completed_at IS NULL
                  )
                ORDER BY v.registration_number
                """,
                (
                    organization_id,
                    organization_id,
                    organization_id,
                    organization_id,
                    shipment_weight,
                ),
            )
            rows = cursor.fetchall()

    candidates = []
    for row in rows:
        (
            vehicle_id, registration_number, make, model, capacity_tonnes,
            expected_litres_per_100km, actual_litres, expected_litres,
            maintenance_events, fuel_variance_ratio,
        ) = row
        fuel_penalty = min(float(fuel_variance_ratio or 0) * 20, 30)
        maintenance_penalty = min(int(maintenance_events) * 2, 20)
        capacity_utilization = float(shipment_weight) / float(capacity_tonnes)
        capacity_fit_penalty = min(max(0.0, 1.0 - capacity_utilization) * 15, 15)
        score = round(max(0, 100 - fuel_penalty - maintenance_penalty - capacity_fit_penalty), 1)
        candidates.append({
            "vehicle_id": str(vehicle_id),
            "registration_number": registration_number,
            "make": make,
            "model": model,
            "capacity_tonnes": float(capacity_tonnes),
            "shipment_weight_tonnes": float(shipment_weight),
            "score": score,
            "score_breakdown": {
                "fuel_variance_penalty": round(fuel_penalty, 1),
                "maintenance_history_penalty": round(maintenance_penalty, 1),
                "capacity_fit_penalty": round(capacity_fit_penalty, 1),
            },
            "historical_metrics": {
                "actual_fuel_litres": float(actual_litres or 0),
                "expected_fuel_litres": float(expected_litres or 0),
                "maintenance_events_last_365_days": int(maintenance_events),
                "capacity_utilization": round(capacity_utilization, 3),
            },
        })

    candidates.sort(key=lambda item: (-item["score"], item["registration_number"]))
    return {
        "organization_id": str(organization_id),
        "shipment_id": str(shipment_id),
        "shipment_reference": shipment_reference,
        "eligible_vehicle_count": len(candidates),
        "candidates": candidates,
        "scoring_policy": {
            "fuel_variance_weight": 20,
            "fuel_variance_penalty_cap": 30,
            "maintenance_event_penalty": 2,
            "maintenance_penalty_cap": 20,
            "capacity_fit_weight": 15,
            "capacity_fit_penalty_cap": 15,
            "maintenance_lookback_days": 365,
            "note": "Fuel variance uses fuel linked to completed or active trips; maintenance is a rolling 365-day count. Capacity fit rewards right-sized vehicles. Scores rank eligible vehicles and do not guarantee future performance.",
        },
    }
