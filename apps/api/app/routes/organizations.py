from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context
from app.db.database import get_connection

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    country_code: str = Field(min_length=2, max_length=2)
    default_currency: str = Field(min_length=3, max_length=3)


@router.post("")
def create_organization(payload: OrganizationCreate) -> dict:
    country = payload.country_code.upper()
    currency = payload.default_currency.upper()
    query = """
        INSERT INTO organizations (name, country_code, default_currency)
        VALUES (%s, %s, %s)
        RETURNING id, name, country_code, default_currency, created_at
    """
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (payload.name.strip(), country, currency))
            row = cursor.fetchone()
            columns = [item.name for item in cursor.description]
            return dict(zip(columns, row))


@router.get("/{organization_id}/vehicles")
def organization_vehicles(
    organization_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[dict]:
    if organization_id != tenant.organization_id:
        raise HTTPException(status_code=403, detail="Organization access denied")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, vehicle_id, registration_number, vehicle_type,
                       capacity_tonnes, odometer_km, status
                FROM vehicles
                WHERE organization_id = %s
                ORDER BY vehicle_id
                """,
                (organization_id,),
            )
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
