from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


class VehicleCreate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=100)
    registration_number: str | None = None
    vehicle_type: str | None = None
    capacity_tonnes: float = Field(gt=0)
    odometer_km: float = Field(default=0, ge=0)


class ShipmentCreate(BaseModel):
    shipment_id: str = Field(min_length=1, max_length=100)
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    weight_tonnes: float = Field(gt=0)
    pickup_at: str | None = None
    delivery_at: str | None = None


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
            cursor.execute(
                """
                INSERT INTO vehicles
                    (organization_id, vehicle_id, registration_number, vehicle_type, capacity_tonnes, odometer_km)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, vehicle_id, registration_number, vehicle_type, capacity_tonnes, odometer_km, status
                """,
                (organization_id, payload.vehicle_id.strip(), payload.registration_number, payload.vehicle_type,
                 payload.capacity_tonnes, payload.odometer_km),
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
            cursor.execute(
                """
                INSERT INTO shipments
                    (organization_id, shipment_id, origin, destination, weight_tonnes, pickup_at, delivery_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, shipment_id, origin, destination, weight_tonnes, pickup_at, delivery_at, status
                """,
                (organization_id, payload.shipment_id.strip(), payload.origin.strip(), payload.destination.strip(),
                 payload.weight_tonnes, payload.pickup_at, payload.delivery_at),
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
