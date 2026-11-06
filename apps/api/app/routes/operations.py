import hashlib
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
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




class DispatchAssignmentCreate(BaseModel):
    vehicle_id: UUID


class DispatchAssignmentRelease(BaseModel):
    reason: str = Field(default="operator_cancelled", min_length=1, max_length=500)


class TripStart(BaseModel):
    planned_distance_km: float = Field(gt=0)
    planned_duration_minutes: int = Field(gt=0)
    start_odometer_km: float = Field(ge=0)


class TripComplete(BaseModel):
    end_odometer_km: float = Field(ge=0)


class ShipmentChargeCreate(BaseModel):
    charge_type: str = Field(pattern=r"^(transport|handling|fuel_surcharge|waiting_time|other)$")
    description: str = Field(min_length=1, max_length=500)
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    occurred_at: datetime | None = None


class FuelTransactionCreate(BaseModel):
    vehicle_id: UUID
    trip_id: UUID
    transaction_time: datetime
    litres: float = Field(gt=0)
    price_per_litre: float = Field(ge=0)
    odometer_km: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    country_code: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")


class ShipmentCreate(BaseModel):
    shipment_reference: str = Field(min_length=1, max_length=100)
    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    weight_tonnes: float = Field(gt=0)
    pickup_at: str | None = None
    delivery_at: str | None = None
    status: str = Field(default="pending", min_length=1, max_length=30)


def record_shipment_event(cursor, organization_id, shipment_id, event_type, actor_id, details):
    cursor.execute(
        """
        INSERT INTO shipment_events (
            organization_id, shipment_id, event_type, actor_id, details
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (organization_id, shipment_id, event_type, actor_id, Jsonb(details)),
    )


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
            result = dict(zip(columns, row))
            record_shipment_event(
                cursor, organization_id, result["id"], "shipment_created",
                tenant.user_id,
                {"shipment_reference": result["shipment_reference"],
                 "origin": result["origin"], "destination": result["destination"],
                 "weight_tonnes": payload.weight_tonnes},
            )
            return result


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




@router.post("/{organization_id}/shipments/{shipment_id}/assign-vehicle")
def assign_shipment_vehicle(
    organization_id: UUID,
    shipment_id: UUID,
    payload: DispatchAssignmentCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> dict:
    """Reserve an eligible vehicle for a shipment without inventing trip telemetry."""
    require_org(organization_id, tenant)
    if idempotency_key is None:
        raise HTTPException(
            status_code=428,
            detail="Idempotency-Key is required for dispatch assignment",
        )

    request_hash = hashlib.sha256(
        json.dumps(
            payload.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_current_role(
                cursor, tenant, {"admin", "operations_manager", "fleet_manager"},
                "Role is not authorized to assign vehicles",
            )
            cursor.execute(
                """
                SELECT id, weight_tonnes, shipment_reference, status
                FROM shipments
                WHERE id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (shipment_id, organization_id),
            )
            shipment = cursor.fetchone()
            if shipment is None:
                raise HTTPException(status_code=404, detail="Shipment not found")

            cursor.execute(
                """
                SELECT request_hash, response_body
                FROM dispatch_assignment_idempotency
                WHERE organization_id = %s AND shipment_id = %s AND idempotency_key = %s
                """,
                (organization_id, shipment_id, idempotency_key),
            )
            cached = cursor.fetchone()
            if cached:
                cached_hash, cached_response = cached
                if cached_hash != request_hash:
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency-Key was already used with a different request",
                    )
                return cached_response

            _, shipment_weight, shipment_reference, shipment_status = shipment
            if shipment_status != "pending":
                raise HTTPException(
                    status_code=409,
                    detail="Only pending shipments can receive a dispatch assignment",
                )

            cursor.execute(
                """
                SELECT id FROM shipment_vehicle_assignments
                WHERE organization_id = %s AND shipment_id = %s AND released_at IS NULL
                FOR UPDATE
                """,
                (organization_id, shipment_id),
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="Shipment already has an active vehicle assignment",
                )

            cursor.execute(
                """
                SELECT id, registration_number, capacity_tonnes, active
                FROM vehicles
                WHERE id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (payload.vehicle_id, organization_id),
            )
            vehicle = cursor.fetchone()
            if vehicle is None:
                raise HTTPException(status_code=404, detail="Vehicle not found")
            vehicle_id, registration_number, capacity_tonnes, active = vehicle
            if not active:
                raise HTTPException(status_code=409, detail="Vehicle is inactive")
            if capacity_tonnes is None or capacity_tonnes < shipment_weight:
                raise HTTPException(
                    status_code=409,
                    detail="Vehicle capacity is insufficient for this shipment",
                )

            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM trips
                    WHERE organization_id = %s AND vehicle_id = %s AND completed_at IS NULL
                ) OR EXISTS (
                    SELECT 1 FROM shipment_vehicle_assignments
                    WHERE organization_id = %s AND vehicle_id = %s AND released_at IS NULL
                )
                """,
                (organization_id, vehicle_id, organization_id, vehicle_id),
            )
            if cursor.fetchone()[0]:
                raise HTTPException(
                    status_code=409,
                    detail="Vehicle already has an active trip or dispatch assignment",
                )

            try:
                cursor.execute(
                    """
                    INSERT INTO shipment_vehicle_assignments (
                        organization_id, shipment_id, vehicle_id, assigned_by
                    ) VALUES (%s, %s, %s, %s)
                    RETURNING id, assigned_at
                    """,
                    (organization_id, shipment_id, vehicle_id, tenant.user_id),
                )
            except UniqueViolation as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Shipment or vehicle was assigned by another dispatch request",
                ) from exc

            assignment_id, assigned_at = cursor.fetchone()
            record_shipment_event(
                cursor, organization_id, shipment_id, "vehicle_assigned",
                tenant.user_id,
                {"assignment_id": str(assignment_id), "vehicle_id": str(vehicle_id),
                 "registration_number": registration_number},
            )
            cursor.execute(
                """
                INSERT INTO dispatch_assignment_events (
                    organization_id, assignment_id, shipment_id, vehicle_id,
                    event_type, actor_id, details
                ) VALUES (%s, %s, %s, %s, 'assigned', %s, %s)
                """,
                (
                    organization_id, assignment_id, shipment_id, vehicle_id,
                    tenant.user_id, Jsonb({"registration_number": registration_number}),
                ),
            )
            response_body = {
                "organization_id": str(organization_id),
                "shipment_id": str(shipment_id),
                "shipment_reference": shipment_reference,
                "assignment_id": str(assignment_id),
                "vehicle_id": str(vehicle_id),
                "registration_number": registration_number,
                "assigned_by": tenant.user_id,
                "assigned_at": assigned_at.isoformat(),
                "status": "assigned",
            }
            cursor.execute(
                """
                INSERT INTO dispatch_assignment_idempotency (
                    organization_id, shipment_id, idempotency_key,
                    request_hash, response_body
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    organization_id, shipment_id, idempotency_key,
                    request_hash, Jsonb(response_body),
                ),
            )

    return response_body




@router.post("/{organization_id}/shipments/{shipment_id}/assignments/{assignment_id}/release")
def release_shipment_assignment(
    organization_id: UUID,
    shipment_id: UUID,
    assignment_id: UUID,
    payload: DispatchAssignmentRelease,
    tenant: TenantContext = Depends(get_tenant_context),
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> dict:
    """Release a reservation while preserving immutable assignment history."""
    require_org(organization_id, tenant)
    if idempotency_key is None:
        raise HTTPException(status_code=428, detail="Idempotency-Key is required for release")

    request_hash = hashlib.sha256(
        json.dumps(
            {"operation": "release", "assignment_id": str(assignment_id),
             **payload.model_dump()},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_current_role(
                cursor, tenant, {"admin", "operations_manager", "fleet_manager"},
                "Role is not authorized to release dispatch assignments",
            )
            cursor.execute(
                "SELECT id FROM shipments WHERE id = %s AND organization_id = %s FOR UPDATE",
                (shipment_id, organization_id),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Shipment not found")

            cursor.execute(
                """
                SELECT request_hash, response_body
                FROM dispatch_assignment_idempotency
                WHERE organization_id = %s AND shipment_id = %s AND idempotency_key = %s
                """,
                (organization_id, shipment_id, idempotency_key),
            )
            cached = cursor.fetchone()
            if cached:
                if cached[0] != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key conflicts with another dispatch command")
                return cached[1]

            cursor.execute(
                """
                SELECT id, vehicle_id, released_at
                FROM shipment_vehicle_assignments
                WHERE id = %s AND organization_id = %s AND shipment_id = %s
                FOR UPDATE
                """,
                (assignment_id, organization_id, shipment_id),
            )
            assignment = cursor.fetchone()
            if assignment is None:
                raise HTTPException(status_code=404, detail="Assignment not found")
            if assignment[2] is not None:
                raise HTTPException(status_code=409, detail="Assignment has already been released")

            cursor.execute(
                """
                UPDATE shipment_vehicle_assignments
                SET released_at = now(), released_by = %s, release_reason = %s
                WHERE id = %s
                RETURNING released_at
                """,
                (tenant.user_id, payload.reason.strip(), assignment_id),
            )
            released_at = cursor.fetchone()[0]
            record_shipment_event(
                cursor, organization_id, shipment_id, "assignment_released",
                tenant.user_id,
                {"assignment_id": str(assignment_id), "vehicle_id": str(assignment[1]),
                 "reason": payload.reason.strip()},
            )
            cursor.execute(
                """
                INSERT INTO dispatch_assignment_events (
                    organization_id, assignment_id, shipment_id, vehicle_id,
                    event_type, actor_id, details
                ) VALUES (%s, %s, %s, %s, 'released', %s, %s)
                """,
                (
                    organization_id, assignment_id, shipment_id, assignment[1],
                    tenant.user_id, Jsonb({"reason": payload.reason.strip()}),
                ),
            )
            response_body = {
                "organization_id": str(organization_id),
                "shipment_id": str(shipment_id),
                "assignment_id": str(assignment_id),
                "vehicle_id": str(assignment[1]),
                "released_by": tenant.user_id,
                "released_at": released_at.isoformat(),
                "reason": payload.reason.strip(),
                "status": "released",
            }
            cursor.execute(
                """
                INSERT INTO dispatch_assignment_idempotency (
                    organization_id, shipment_id, idempotency_key,
                    request_hash, response_body
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (organization_id, shipment_id, idempotency_key, request_hash, Jsonb(response_body)),
            )
    return response_body




@router.post("/{organization_id}/shipments/{shipment_id}/start-trip")
def start_shipment_trip(
    organization_id: UUID,
    shipment_id: UUID,
    payload: TripStart,
    tenant: TenantContext = Depends(get_tenant_context),
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> dict:
    """Start a real trip from an active dispatch reservation."""
    require_org(organization_id, tenant)
    if idempotency_key is None:
        raise HTTPException(status_code=428, detail="Idempotency-Key is required to start a trip")
    request_hash = hashlib.sha256(
        json.dumps(
            {"operation": "start_trip", **payload.model_dump()},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_current_role(
                cursor, tenant, {"admin", "operations_manager", "fleet_manager"},
                "Role is not authorized to start trips",
            )
            cursor.execute(
                """
                SELECT id, origin, destination, weight_tonnes, status
                FROM shipments
                WHERE id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (shipment_id, organization_id),
            )
            shipment = cursor.fetchone()
            if shipment is None:
                raise HTTPException(status_code=404, detail="Shipment not found")

            cursor.execute(
                """
                SELECT request_hash, response_body
                FROM trip_command_idempotency
                WHERE organization_id = %s AND shipment_id = %s AND idempotency_key = %s
                """,
                (organization_id, shipment_id, idempotency_key),
            )
            cached = cursor.fetchone()
            if cached:
                if cached[0] != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key conflicts with another trip command")
                return cached[1]

            _, origin, destination, load_tonnes, shipment_status = shipment
            if shipment_status != "pending":
                raise HTTPException(status_code=409, detail="Only pending shipments can start a trip")

            cursor.execute(
                """
                SELECT id, vehicle_id
                FROM shipment_vehicle_assignments
                WHERE organization_id = %s AND shipment_id = %s AND released_at IS NULL
                FOR UPDATE
                """,
                (organization_id, shipment_id),
            )
            assignment = cursor.fetchone()
            if assignment is None:
                raise HTTPException(status_code=409, detail="Shipment has no active vehicle reservation")
            assignment_id, vehicle_id = assignment

            cursor.execute(
                """
                SELECT odometer_km, active, capacity_tonnes
                FROM vehicles
                WHERE id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (vehicle_id, organization_id),
            )
            vehicle = cursor.fetchone()
            if vehicle is None:
                raise HTTPException(status_code=404, detail="Reserved vehicle not found")
            current_odometer, active, capacity = vehicle
            if not active:
                raise HTTPException(status_code=409, detail="Reserved vehicle is inactive")
            if capacity is None or capacity < load_tonnes:
                raise HTTPException(status_code=409, detail="Reserved vehicle no longer meets shipment capacity")
            if payload.start_odometer_km < current_odometer:
                raise HTTPException(status_code=409, detail="Start odometer cannot be below the vehicle's recorded odometer")

            cursor.execute(
                """
                SELECT id FROM trips
                WHERE organization_id = %s AND vehicle_id = %s AND completed_at IS NULL
                FOR UPDATE
                """,
                (organization_id, vehicle_id),
            )
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="Vehicle already has an unfinished trip")

            cursor.execute(
                """
                INSERT INTO trips (
                    organization_id, vehicle_id, shipment_id, origin, destination,
                    distance_km, planned_duration_minutes, actual_duration_minutes,
                    load_tonnes, started_at, started_by, start_odometer_km
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, now(), %s, %s)
                RETURNING id, started_at
                """,
                (
                    organization_id, vehicle_id, shipment_id, origin, destination,
                    payload.planned_distance_km, payload.planned_duration_minutes,
                    load_tonnes, tenant.user_id, payload.start_odometer_km,
                ),
            )
            trip_id, started_at = cursor.fetchone()
            record_shipment_event(
                cursor, organization_id, shipment_id, "trip_started",
                tenant.user_id,
                {"trip_id": str(trip_id), "vehicle_id": str(vehicle_id),
                 "start_odometer_km": payload.start_odometer_km},
            )
            cursor.execute(
                "UPDATE shipments SET status = 'in_transit' WHERE id = %s AND organization_id = %s",
                (shipment_id, organization_id),
            )
            cursor.execute(
                """
                INSERT INTO trip_events (
                    organization_id, trip_id, shipment_id, vehicle_id,
                    event_type, actor_id, details
                ) VALUES (%s, %s, %s, %s, 'started', %s, %s)
                """,
                (
                    organization_id, trip_id, shipment_id, vehicle_id,
                    tenant.user_id,
                    Jsonb({
                        "assignment_id": str(assignment_id),
                        "start_odometer_km": payload.start_odometer_km,
                        "planned_distance_km": payload.planned_distance_km,
                        "planned_duration_minutes": payload.planned_duration_minutes,
                    }),
                ),
            )
            response_body = {
                "organization_id": str(organization_id),
                "shipment_id": str(shipment_id),
                "assignment_id": str(assignment_id),
                "trip_id": str(trip_id),
                "vehicle_id": str(vehicle_id),
                "status": "in_progress",
                "started_by": tenant.user_id,
                "started_at": started_at.isoformat(),
                "start_odometer_km": payload.start_odometer_km,
            }
            cursor.execute(
                """
                INSERT INTO trip_command_idempotency (
                    organization_id, shipment_id, idempotency_key, request_hash, response_body
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (organization_id, shipment_id, idempotency_key, request_hash, Jsonb(response_body)),
            )
    return response_body


@router.post("/{organization_id}/shipments/{shipment_id}/trips/{trip_id}/complete")
def complete_shipment_trip(
    organization_id: UUID,
    shipment_id: UUID,
    trip_id: UUID,
    payload: TripComplete,
    tenant: TenantContext = Depends(get_tenant_context),
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> dict:
    """Complete a trip using measured odometer distance and elapsed time."""
    require_org(organization_id, tenant)
    if idempotency_key is None:
        raise HTTPException(status_code=428, detail="Idempotency-Key is required to complete a trip")
    request_hash = hashlib.sha256(
        json.dumps(
            {"operation": "complete_trip", "trip_id": str(trip_id), **payload.model_dump()},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_current_role(
                cursor, tenant, {"admin", "operations_manager", "fleet_manager"},
                "Role is not authorized to complete trips",
            )
            cursor.execute(
                """
                SELECT id, status
                FROM shipments
                WHERE id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (shipment_id, organization_id),
            )
            shipment = cursor.fetchone()
            if shipment is None:
                raise HTTPException(status_code=404, detail="Shipment not found")

            cursor.execute(
                """
                SELECT request_hash, response_body
                FROM trip_command_idempotency
                WHERE organization_id = %s AND shipment_id = %s AND idempotency_key = %s
                """,
                (organization_id, shipment_id, idempotency_key),
            )
            cached = cursor.fetchone()
            if cached:
                if cached[0] != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key conflicts with another trip command")
                return cached[1]

            if shipment[1] != "in_transit":
                raise HTTPException(status_code=409, detail="Shipment is not in transit")

            cursor.execute(
                """
                SELECT vehicle_id, started_at, start_odometer_km, completed_at
                FROM trips
                WHERE id = %s AND organization_id = %s AND shipment_id = %s
                FOR UPDATE
                """,
                (trip_id, organization_id, shipment_id),
            )
            trip = cursor.fetchone()
            if trip is None:
                raise HTTPException(status_code=404, detail="Trip not found")
            vehicle_id, started_at, start_odometer, completed_at = trip
            if completed_at is not None:
                raise HTTPException(status_code=409, detail="Trip has already been completed")
            if start_odometer is None:
                raise HTTPException(status_code=409, detail="Trip is missing its start odometer reading")
            if payload.end_odometer_km <= start_odometer:
                raise HTTPException(status_code=422, detail="End odometer must be greater than start odometer")

            cursor.execute(
                "SELECT odometer_km FROM vehicles WHERE id = %s AND organization_id = %s FOR UPDATE",
                (vehicle_id, organization_id),
            )
            vehicle = cursor.fetchone()
            if vehicle is None:
                raise HTTPException(status_code=404, detail="Trip vehicle not found")
            if payload.end_odometer_km < vehicle[0]:
                raise HTTPException(status_code=409, detail="End odometer cannot be below the vehicle's recorded odometer")

            cursor.execute(
                """
                UPDATE trips
                SET completed_at = now(),
                    completed_by = %s,
                    end_odometer_km = %s,
                    actual_distance_km = %s - start_odometer_km,
                    actual_duration_minutes = GREATEST(
                        1, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) / 60)::integer
                    )
                WHERE id = %s AND organization_id = %s
                RETURNING completed_at, actual_distance_km, actual_duration_minutes
                """,
                (tenant.user_id, payload.end_odometer_km, payload.end_odometer_km, trip_id, organization_id),
            )
            completed_at, actual_distance, actual_duration = cursor.fetchone()
            cursor.execute(
                "UPDATE vehicles SET odometer_km = %s WHERE id = %s AND organization_id = %s",
                (payload.end_odometer_km, vehicle_id, organization_id),
            )
            cursor.execute(
                "UPDATE shipments SET status = 'delivered' WHERE id = %s AND organization_id = %s",
                (shipment_id, organization_id),
            )

            cursor.execute(
                """
                UPDATE shipment_vehicle_assignments
                SET released_at = now(), released_by = %s, release_reason = 'trip_completed'
                WHERE organization_id = %s AND shipment_id = %s
                  AND vehicle_id = %s AND released_at IS NULL
                RETURNING id
                """,
                (tenant.user_id, organization_id, shipment_id, vehicle_id),
            )
            released_assignment = cursor.fetchone()
            if released_assignment:
                cursor.execute(
                    """
                    INSERT INTO dispatch_assignment_events (
                        organization_id, assignment_id, shipment_id, vehicle_id,
                        event_type, actor_id, details
                    ) VALUES (%s, %s, %s, %s, 'released', %s, %s)
                    """,
                    (
                        organization_id, released_assignment[0], shipment_id, vehicle_id,
                        tenant.user_id, Jsonb({"reason": "trip_completed", "trip_id": str(trip_id)}),
                    ),
                )

            record_shipment_event(
                cursor, organization_id, shipment_id, "trip_completed",
                tenant.user_id,
                {"trip_id": str(trip_id), "vehicle_id": str(vehicle_id),
                 "actual_distance_km": float(actual_distance),
                 "actual_duration_minutes": actual_duration,
                 "end_odometer_km": payload.end_odometer_km},
            )
            cursor.execute(
                """
                INSERT INTO trip_events (
                    organization_id, trip_id, shipment_id, vehicle_id,
                    event_type, actor_id, details
                ) VALUES (%s, %s, %s, %s, 'completed', %s, %s)
                """,
                (
                    organization_id, trip_id, shipment_id, vehicle_id,
                    tenant.user_id,
                    Jsonb({
                        "end_odometer_km": payload.end_odometer_km,
                        "actual_distance_km": float(actual_distance),
                        "actual_duration_minutes": actual_duration,
                    }),
                ),
            )
            response_body = {
                "organization_id": str(organization_id),
                "shipment_id": str(shipment_id),
                "trip_id": str(trip_id),
                "vehicle_id": str(vehicle_id),
                "status": "completed",
                "completed_by": tenant.user_id,
                "completed_at": completed_at.isoformat(),
                "actual_distance_km": float(actual_distance),
                "actual_duration_minutes": actual_duration,
                "end_odometer_km": payload.end_odometer_km,
            }
            cursor.execute(
                """
                INSERT INTO trip_command_idempotency (
                    organization_id, shipment_id, idempotency_key, request_hash, response_body
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (organization_id, shipment_id, idempotency_key, request_hash, Jsonb(response_body)),
            )
    return response_body












@router.post("/{organization_id}/fuel-transactions")
def create_fuel_transaction(
    organization_id: UUID,
    payload: FuelTransactionCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> dict:
    """Record a trip-linked fuel purchase with idempotent, tenant-safe writes."""
    require_org(organization_id, tenant)
    if idempotency_key is None:
        raise HTTPException(status_code=428, detail="Idempotency-Key is required to record fuel")
    if payload.transaction_time.tzinfo is None:
        raise HTTPException(status_code=422, detail="transaction_time must include a timezone")

    request_hash = hashlib.sha256(
        json.dumps(
            {"operation": "create_fuel_transaction", **payload.model_dump(mode="json")},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_current_role(
                cursor, tenant, {"admin", "operations_manager", "fleet_manager"},
                "Role is not authorized to record fuel transactions",
            )
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                (str(organization_id), idempotency_key),
            )
            cursor.execute(
                """
                SELECT request_hash, response_body
                FROM fuel_transaction_idempotency
                WHERE organization_id = %s AND idempotency_key = %s
                """,
                (organization_id, idempotency_key),
            )
            cached = cursor.fetchone()
            if cached:
                if cached[0] != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key conflicts with another fuel transaction")
                return cached[1]

            cursor.execute(
                """
                SELECT id, vehicle_id, shipment_id, completed_at,
                       start_odometer_km, end_odometer_km
                FROM trips
                WHERE id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (payload.trip_id, organization_id),
            )
            trip = cursor.fetchone()
            if trip is None:
                raise HTTPException(status_code=404, detail="Trip not found")
            _, trip_vehicle_id, shipment_id, completed_at, start_odometer, end_odometer = trip
            if trip_vehicle_id != payload.vehicle_id:
                raise HTTPException(status_code=409, detail="Fuel transaction vehicle does not match the trip")
            if start_odometer is not None and payload.odometer_km < start_odometer:
                raise HTTPException(status_code=409, detail="Fuel odometer cannot be below the trip start odometer")
            if end_odometer is not None and payload.odometer_km > end_odometer:
                raise HTTPException(status_code=409, detail="Fuel odometer cannot exceed the trip end odometer")

            cursor.execute(
                """
                SELECT odometer_km
                FROM vehicles
                WHERE id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (payload.vehicle_id, organization_id),
            )
            vehicle = cursor.fetchone()
            if vehicle is None:
                raise HTTPException(status_code=404, detail="Vehicle not found")
            if completed_at is None and payload.odometer_km < vehicle[0]:
                raise HTTPException(status_code=409, detail="Fuel odometer cannot move an active vehicle backwards")

            cursor.execute(
                """
                INSERT INTO fuel_transactions (
                    organization_id, vehicle_id, trip_id, transaction_time,
                    litres, price_per_litre, odometer_km, currency, country_code
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    organization_id, payload.vehicle_id, payload.trip_id,
                    payload.transaction_time, payload.litres, payload.price_per_litre,
                    payload.odometer_km, payload.currency, payload.country_code,
                ),
            )
            transaction_id, created_at = cursor.fetchone()
            if completed_at is None:
                cursor.execute(
                    """
                    UPDATE vehicles SET odometer_km = GREATEST(odometer_km, %s)
                    WHERE id = %s AND organization_id = %s
                    """,
                    (payload.odometer_km, payload.vehicle_id, organization_id),
                )

            response_body = {
                "organization_id": str(organization_id),
                "fuel_transaction_id": str(transaction_id),
                "trip_id": str(payload.trip_id),
                "vehicle_id": str(payload.vehicle_id),
                "shipment_id": str(shipment_id) if shipment_id else None,
                "transaction_time": payload.transaction_time.isoformat(),
                "litres": payload.litres,
                "price_per_litre": payload.price_per_litre,
                "odometer_km": payload.odometer_km,
                "currency": payload.currency,
                "country_code": payload.country_code,
                "created_at": created_at.isoformat(),
            }
            cursor.execute(
                """
                INSERT INTO fuel_transaction_idempotency (
                    organization_id, idempotency_key, request_hash, response_body
                ) VALUES (%s, %s, %s, %s)
                """,
                (organization_id, idempotency_key, request_hash, Jsonb(response_body)),
            )
            if shipment_id:
                record_shipment_event(
                    cursor, organization_id, shipment_id, "fuel_recorded",
                    tenant.user_id,
                    {"fuel_transaction_id": str(transaction_id),
                     "trip_id": str(payload.trip_id), "litres": payload.litres,
                     "currency": payload.currency, "odometer_km": payload.odometer_km},
                )

    return response_body

@router.get("/{organization_id}/trip-performance")
def trip_performance(
    organization_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Measure completed trip efficiency without combining unlike currencies."""
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH selected_trips AS (
                    SELECT t.id, t.shipment_id, s.shipment_reference,
                           t.vehicle_id, v.registration_number,
                           t.origin, t.destination, t.completed_at,
                           t.actual_distance_km, t.actual_duration_minutes,
                           v.expected_litres_per_100km
                    FROM trips t
                    JOIN vehicles v
                      ON v.id = t.vehicle_id AND v.organization_id = t.organization_id
                    LEFT JOIN shipments s
                      ON s.id = t.shipment_id AND s.organization_id = t.organization_id
                    WHERE t.organization_id = %s
                      AND t.completed_at >= now() - (%s * INTERVAL '1 day')
                      AND t.actual_distance_km IS NOT NULL
                    ORDER BY t.completed_at DESC, t.id
                    LIMIT %s
                )
                SELECT t.id, t.shipment_id, t.shipment_reference,
                       t.vehicle_id, t.registration_number,
                       t.origin, t.destination, t.completed_at,
                       t.actual_distance_km, t.actual_duration_minutes,
                       t.expected_litres_per_100km,
                       COALESCE(SUM(fuel.litres), 0) AS fuel_litres,
                       fuel.currency,
                       SUM(fuel.fuel_cost) AS fuel_cost
                FROM selected_trips t
                LEFT JOIN LATERAL (
                    SELECT ft.currency,
                           SUM(ft.litres) AS litres,
                           SUM(ft.litres * ft.price_per_litre) AS fuel_cost
                    FROM fuel_transactions ft
                    WHERE ft.organization_id = %s
                      AND ft.trip_id = t.id
                      AND ft.vehicle_id = t.vehicle_id
                    GROUP BY ft.currency
                ) fuel ON TRUE
                GROUP BY t.id, t.shipment_id, t.shipment_reference,
                         t.vehicle_id, t.registration_number, t.origin,
                         t.destination, t.completed_at, t.actual_distance_km,
                         t.actual_duration_minutes, t.expected_litres_per_100km,
                         fuel.currency
                ORDER BY t.completed_at DESC, t.id, fuel.currency
                """,
                (organization_id, days, limit, organization_id),
            )
            rows = cursor.fetchall()

    trip_map = {}
    cost_by_currency = {}
    for row in rows:
        trip_id = str(row[0])
        if trip_id not in trip_map:
            distance = float(row[8])
            duration = int(row[9]) if row[9] is not None else None
            expected_rate = float(row[10])
            fuel_litres = float(row[11])
            expected_litres = distance * expected_rate / 100
            trip_map[trip_id] = {
                "trip_id": trip_id,
                "shipment_id": str(row[1]) if row[1] else None,
                "shipment_reference": row[2],
                "vehicle_id": str(row[3]),
                "registration_number": row[4],
                "origin": row[5],
                "destination": row[6],
                "completed_at": row[7].isoformat(),
                "actual_distance_km": distance,
                "actual_duration_minutes": duration,
                "fuel_litres": fuel_litres,
                "expected_fuel_litres": round(expected_litres, 3),
                "actual_litres_per_100km": round(fuel_litres / distance * 100, 2)
                    if fuel_litres > 0 and distance > 0 else None,
                "fuel_variance_percent": round(
                    (fuel_litres - expected_litres) / expected_litres * 100, 2
                ) if fuel_litres > 0 and expected_litres > 0 else None,
                "fuel_data_available": fuel_litres > 0,
                "fuel_costs": [],
            }
        else:
            trip = trip_map[trip_id]
            trip["fuel_litres"] += float(row[11])
            trip["fuel_data_available"] = trip["fuel_litres"] > 0
            trip["actual_litres_per_100km"] = round(
                trip["fuel_litres"] / trip["actual_distance_km"] * 100, 2
            ) if trip["fuel_data_available"] else None
            trip["fuel_variance_percent"] = round(
                (trip["fuel_litres"] - trip["expected_fuel_litres"])
                / trip["expected_fuel_litres"] * 100, 2
            ) if trip["fuel_data_available"] and trip["expected_fuel_litres"] > 0 else None
        if row[12] is not None:
            amount = float(row[13] or 0)
            trip_map[trip_id]["fuel_costs"].append({
                "currency": row[12].strip(),
                "amount": round(amount, 2),
            })
            cost_by_currency[row[12].strip()] = (
                cost_by_currency.get(row[12].strip(), 0.0) + amount
            )

    trips = list(trip_map.values())
    summary = {
        "completed_trip_count": len(trips),
        "actual_distance_km": round(sum(t["actual_distance_km"] for t in trips), 2),
        "fuel_litres": round(sum(t["fuel_litres"] for t in trips), 2),
        "expected_fuel_litres": round(sum(t["expected_fuel_litres"] for t in trips), 2),
        "average_duration_minutes": round(
            sum(t["actual_duration_minutes"] or 0 for t in trips)
            / len(trips), 2
        ) if trips else 0,
        "fuel_costs_by_currency": [
            {"currency": currency, "amount": round(amount, 2)}
            for currency, amount in sorted(cost_by_currency.items())
        ],
        "trips_without_fuel_data": sum(1 for t in trips if not t["fuel_data_available"]),
    }
    return {
        "organization_id": str(organization_id),
        "period_days": days,
        "returned_count": len(trips),
        "summary": summary,
        "trips": trips,
    }

@router.get("/{organization_id}/shipments/recent")
def recent_shipments(
    organization_id: UUID,
    limit: int = Query(default=25, ge=1, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    """List recent shipment activity, including delivered shipments."""
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.shipment_reference, s.origin, s.destination,
                       s.weight_tonnes, s.status, s.created_at,
                       COALESCE(MAX(e.occurred_at), s.created_at) AS last_event_at,
                       COUNT(e.id) AS event_count,
                       COUNT(*) OVER() AS total_count
                FROM shipments s
                LEFT JOIN shipment_events e
                  ON e.organization_id = s.organization_id
                 AND e.shipment_id = s.id
                WHERE s.organization_id = %s
                GROUP BY s.id
                ORDER BY last_event_at DESC, s.created_at DESC, s.id
                LIMIT %s
                """,
                (organization_id, limit),
            )
            rows = cursor.fetchall()
    return {
        "organization_id": str(organization_id),
        "total_count": int(rows[0][9]) if rows else 0,
        "returned_count": len(rows),
        "shipments": [
            {
                "shipment_id": str(row[0]),
                "shipment_reference": row[1],
                "origin": row[2],
                "destination": row[3],
                "weight_tonnes": float(row[4]),
                "status": row[5],
                "created_at": row[6].isoformat(),
                "last_event_at": row[7].isoformat(),
                "event_count": int(row[8]),
            }
            for row in rows
        ],
    }

@router.get("/{organization_id}/shipments/{shipment_id}/timeline")
def shipment_timeline(
    organization_id: UUID,
    shipment_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Return immutable shipment milestones in chronological order."""
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT shipment_reference, origin, destination, status, created_at
                FROM shipments
                WHERE organization_id = %s AND id = %s
                """,
                (organization_id, shipment_id),
            )
            shipment = cursor.fetchone()
            if shipment is None:
                raise HTTPException(status_code=404, detail="Shipment not found")
            cursor.execute(
                """
                SELECT id, event_type, actor_id, details, occurred_at
                FROM shipment_events
                WHERE organization_id = %s AND shipment_id = %s
                ORDER BY occurred_at ASC, id ASC
                """,
                (organization_id, shipment_id),
            )
            rows = cursor.fetchall()

    reference, origin, destination, status, created_at = shipment
    events = [
        {"event_id": str(row[0]), "event_type": row[1], "actor_id": row[2],
         "details": row[3], "occurred_at": row[4].isoformat()}
        for row in rows
    ]
    if not any(event["event_type"] == "shipment_created" for event in events):
        events.insert(0, {
            "event_id": None, "event_type": "shipment_created", "actor_id": None,
            "details": {"shipment_reference": reference, "origin": origin,
                        "destination": destination, "legacy_event": True},
            "occurred_at": created_at.isoformat(),
        })
    return {
        "organization_id": str(organization_id), "shipment_id": str(shipment_id),
        "shipment_reference": reference, "status": status,
        "total_events": len(events), "events": events,
    }

@router.get("/{organization_id}/active-trips")
def list_active_trips(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    """List current trips with live odometer context for completion."""
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT t.id, t.shipment_id, s.shipment_reference, t.vehicle_id,
                       v.registration_number, t.origin, t.destination,
                       t.started_at, t.started_by, t.start_odometer_km,
                       v.odometer_km, o.default_currency, o.country_code
                FROM trips t
                JOIN organizations o ON o.id = t.organization_id
                JOIN shipments s
                  ON s.id = t.shipment_id AND s.organization_id = t.organization_id
                JOIN vehicles v
                  ON v.id = t.vehicle_id AND v.organization_id = t.organization_id
                WHERE t.organization_id = %s AND t.completed_at IS NULL
                ORDER BY t.started_at ASC, t.id ASC
                """,
                (organization_id,),
            )
            rows = cursor.fetchall()
    return {
        "organization_id": str(organization_id),
        "total_count": len(rows),
        "trips": [
            {
                "trip_id": str(row[0]),
                "shipment_id": str(row[1]),
                "shipment_reference": row[2],
                "vehicle_id": str(row[3]),
                "registration_number": row[4],
                "origin": row[5],
                "destination": row[6],
                "started_at": row[7].isoformat(),
                "started_by": row[8],
                "start_odometer_km": float(row[9]) if row[9] is not None else None,
                "current_odometer_km": float(row[10]),
                "default_currency": row[11].strip(),
                "country_code": row[12].strip(),
            }
            for row in rows
        ],
    }


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
                    SELECT s.id,
                           EXISTS (
                               SELECT 1 FROM trips t
                               WHERE t.organization_id = s.organization_id
                                 AND t.shipment_id = s.id
                                 AND t.completed_at IS NULL
                           ) OR EXISTS (
                               SELECT 1 FROM shipment_vehicle_assignments a
                               WHERE a.organization_id = s.organization_id
                                 AND a.shipment_id = s.id
                                 AND a.released_at IS NULL
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
                                 AND NOT EXISTS (
                                     SELECT 1 FROM shipment_vehicle_assignments reserved
                                     WHERE reserved.organization_id = v.organization_id
                                       AND reserved.vehicle_id = v.id
                                       AND reserved.released_at IS NULL
                                 )
                           ) AS eligible_vehicle_count
                    FROM shipments s
                    WHERE s.organization_id = %s AND s.status = 'pending'
                )
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE assigned),
                       COUNT(*) FILTER (WHERE NOT assigned AND eligible_vehicle_count > 0),
                       COUNT(*) FILTER (WHERE NOT assigned AND eligible_vehicle_count = 0)
                FROM pending_shipments
                """,
                (organization_id,),
            )
            total_count, total_assigned, total_ready, total_blocked = cursor.fetchone()

            cursor.execute(
                """
                WITH pending_shipments AS (
                    SELECT s.id, s.shipment_reference, s.origin, s.destination,
                           s.weight_tonnes, s.pickup_at, s.created_at,
                           assignment.id AS assignment_id,
                           assignment.vehicle_id AS assigned_vehicle_id,
                           assigned_vehicle.registration_number AS assigned_registration_number,
                           assigned_vehicle.odometer_km AS assigned_vehicle_odometer_km,
                           EXISTS (
                               SELECT 1 FROM trips t
                               WHERE t.organization_id = s.organization_id
                                 AND t.shipment_id = s.id
                                 AND t.completed_at IS NULL
                           ) OR EXISTS (
                               SELECT 1 FROM shipment_vehicle_assignments a
                               WHERE a.organization_id = s.organization_id
                                 AND a.shipment_id = s.id
                                 AND a.released_at IS NULL
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
                                 AND NOT EXISTS (
                                     SELECT 1 FROM shipment_vehicle_assignments reserved
                                     WHERE reserved.organization_id = v.organization_id
                                       AND reserved.vehicle_id = v.id
                                       AND reserved.released_at IS NULL
                                 )
                           ) AS eligible_vehicle_count
                    FROM shipments s
                    LEFT JOIN LATERAL (
                        SELECT a.id, a.vehicle_id
                        FROM shipment_vehicle_assignments a
                        WHERE a.organization_id = s.organization_id
                          AND a.shipment_id = s.id AND a.released_at IS NULL
                        ORDER BY a.assigned_at DESC
                        LIMIT 1
                    ) assignment ON TRUE
                    LEFT JOIN vehicles assigned_vehicle
                      ON assigned_vehicle.id = assignment.vehicle_id
                     AND assigned_vehicle.organization_id = s.organization_id
                    WHERE s.organization_id = %s AND s.status = 'pending'
                )
                SELECT id, shipment_reference, origin, destination, weight_tonnes,
                       pickup_at, created_at, assigned, eligible_vehicle_count,
                       assignment_id, assigned_vehicle_id, assigned_registration_number,
                       assigned_vehicle_odometer_km
                FROM pending_shipments
                ORDER BY created_at ASC, id ASC
                LIMIT %s OFFSET %s
                """,
                (organization_id, limit, offset),
            )
            rows = cursor.fetchall()

    shipments = []
    for row in rows:
        (
            shipment_id, reference, origin, destination, weight, pickup_at,
            created_at, assigned, eligible_count, assignment_id,
            assigned_vehicle_id, assigned_registration_number, assigned_vehicle_odometer_km,
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
            "assignment_id": str(assignment_id) if assignment_id else None,
            "assigned_vehicle_id": str(assigned_vehicle_id) if assigned_vehicle_id else None,
            "assigned_registration_number": assigned_registration_number,
            "assigned_vehicle_odometer_km": float(assigned_vehicle_odometer_km) if assigned_vehicle_odometer_km is not None else None,
        })

    return {
        "organization_id": str(organization_id),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "summary": {
            "ready": total_ready,
            "blocked": total_blocked,
            "assigned": total_assigned,
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
                  AND NOT EXISTS (
                      SELECT 1
                      FROM shipment_vehicle_assignments reserved
                      WHERE reserved.organization_id = v.organization_id
                        AND reserved.vehicle_id = v.id
                        AND reserved.released_at IS NULL
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


@router.post("/{organization_id}/shipments/{shipment_id}/charges")
def create_shipment_charge(
    organization_id: UUID,
    shipment_id: UUID,
    payload: ShipmentChargeCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> dict:
    """Record an immutable customer charge against one shipment."""
    require_org(organization_id, tenant)
    if idempotency_key is None:
        raise HTTPException(status_code=428, detail="Idempotency-Key is required to record shipment revenue")
    if payload.occurred_at is not None and (
        payload.occurred_at.tzinfo is None or payload.occurred_at.utcoffset() is None
    ):
        raise HTTPException(status_code=422, detail="occurred_at must include a timezone")
    occurred_at = payload.occurred_at or datetime.now().astimezone()
    request_hash = hashlib.sha256(json.dumps(
        {"operation": "create_shipment_charge", "shipment_id": str(shipment_id),
         **payload.model_dump(mode="json")},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_current_role(
                cursor, tenant, {"admin", "operations_manager", "fleet_manager"},
                "Role is not authorized to record shipment charges",
            )
            cursor.execute(
                "SELECT id FROM shipments WHERE id = %s AND organization_id = %s FOR UPDATE",
                (shipment_id, organization_id),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Shipment not found")
            cursor.execute(
                """
                SELECT request_hash, response_body
                FROM shipment_charge_idempotency
                WHERE organization_id = %s AND shipment_id = %s AND idempotency_key = %s
                """,
                (organization_id, shipment_id, idempotency_key),
            )
            cached = cursor.fetchone()
            if cached:
                if cached[0] != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key conflicts with another shipment charge")
                return cached[1]

            cursor.execute(
                """
                INSERT INTO shipment_charges (
                    organization_id, shipment_id, charge_type, description,
                    amount, currency, occurred_at, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    organization_id, shipment_id, payload.charge_type,
                    payload.description.strip(), payload.amount, payload.currency,
                    occurred_at, tenant.user_id,
                ),
            )
            charge_id, created_at = cursor.fetchone()
            record_shipment_event(
                cursor, organization_id, shipment_id, "revenue_charge_recorded",
                tenant.user_id,
                {"charge_id": str(charge_id), "charge_type": payload.charge_type,
                 "amount": payload.amount, "currency": payload.currency},
            )
            result = {
                "charge_id": str(charge_id), "organization_id": str(organization_id),
                "shipment_id": str(shipment_id), "charge_type": payload.charge_type,
                "description": payload.description.strip(), "amount": payload.amount,
                "currency": payload.currency, "occurred_at": occurred_at.isoformat(),
                "created_by": tenant.user_id, "created_at": created_at.isoformat(),
            }
            cursor.execute(
                """
                INSERT INTO shipment_charge_idempotency (
                    organization_id, shipment_id, idempotency_key, request_hash, response_body
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (organization_id, shipment_id, idempotency_key, request_hash, Jsonb(result)),
            )
    return result


@router.get("/{organization_id}/profitability")
def shipment_profitability(
    organization_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Report shipment revenue and direct fuel contribution, grouped by currency."""
    require_org(organization_id, tenant)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH revenue AS (
                    SELECT c.shipment_id, c.currency,
                           SUM(c.amount) AS revenue_amount
                    FROM shipment_charges c
                    WHERE c.organization_id = %s
                      AND c.occurred_at >= now() - (%s * INTERVAL '1 day')
                    GROUP BY c.shipment_id, c.currency
                ),
                fuel AS (
                    SELECT t.shipment_id, f.currency,
                           SUM(f.litres * f.price_per_litre) AS fuel_amount
                    FROM trips t
                    JOIN fuel_transactions f
                      ON f.trip_id = t.id
                     AND f.organization_id = t.organization_id
                     AND f.vehicle_id = t.vehicle_id
                    WHERE t.organization_id = %s
                      AND f.transaction_time >= now() - (%s * INTERVAL '1 day')
                      AND t.shipment_id IS NOT NULL
                    GROUP BY t.shipment_id, f.currency
                ),
                combined AS (
                    SELECT COALESCE(r.shipment_id, f.shipment_id) AS shipment_id,
                           COALESCE(r.currency, f.currency) AS currency,
                           COALESCE(r.revenue_amount, 0) AS revenue_amount,
                           COALESCE(f.fuel_amount, 0) AS fuel_amount
                    FROM revenue r
                    FULL OUTER JOIN fuel f
                      ON f.shipment_id = r.shipment_id AND f.currency = r.currency
                )
                SELECT s.id AS shipment_id, s.shipment_reference, s.origin, s.destination,
                       s.status, c.currency, c.revenue_amount, c.fuel_amount,
                       c.revenue_amount - c.fuel_amount AS fuel_contribution,
                       CASE WHEN c.revenue_amount > 0
                            THEN ROUND(((c.revenue_amount - c.fuel_amount)
                                       / c.revenue_amount) * 100, 2)
                            ELSE NULL END AS fuel_contribution_margin_percent
                FROM combined c
                JOIN shipments s
                  ON s.id = c.shipment_id AND s.organization_id = %s
                ORDER BY (c.revenue_amount - c.fuel_amount) ASC,
                         s.shipment_reference, c.currency
                LIMIT %s
                """,
                (organization_id, days, organization_id, days, organization_id, limit),
            )
            columns = [item.name for item in cursor.description]
            shipments = [dict(zip(columns, row)) for row in cursor.fetchall()]

            cursor.execute(
                """
                WITH revenue AS (
                    SELECT currency, SUM(amount) AS amount
                    FROM shipment_charges
                    WHERE organization_id = %s
                      AND occurred_at >= now() - (%s * INTERVAL '1 day')
                    GROUP BY currency
                ),
                fuel AS (
                    SELECT f.currency, SUM(f.litres * f.price_per_litre) AS amount
                    FROM fuel_transactions f
                    WHERE f.organization_id = %s
                      AND f.transaction_time >= now() - (%s * INTERVAL '1 day')
                    GROUP BY f.currency
                ),
                currencies AS (
                    SELECT currency FROM revenue UNION SELECT currency FROM fuel
                )
                SELECT c.currency, COALESCE(r.amount, 0) AS revenue,
                       COALESCE(f.amount, 0) AS fuel_cost,
                       COALESCE(r.amount, 0) - COALESCE(f.amount, 0) AS fuel_contribution
                FROM currencies c
                LEFT JOIN revenue r USING (currency)
                LEFT JOIN fuel f USING (currency)
                ORDER BY c.currency
                """,
                (organization_id, days, organization_id, days),
            )
            totals = [
                {"currency": row[0], "revenue": float(row[1]),
                 "fuel_cost": float(row[2]), "fuel_contribution": float(row[3])}
                for row in cursor.fetchall()
            ]

    for item in shipments:
        for key in ("revenue_amount", "fuel_amount", "fuel_contribution"):
            item[key] = float(item[key])
        if item["fuel_contribution_margin_percent"] is not None:
            item["fuel_contribution_margin_percent"] = float(item["fuel_contribution_margin_percent"])
    return {
        "organization_id": str(organization_id), "period_days": days,
        "currency_totals": totals, "shipments": shipments,
        "cost_scope": "Direct recorded fuel only; maintenance and overhead are not allocated.",
    }

