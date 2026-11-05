from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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
