from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Organization(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    country_code: str = Field(min_length=2, max_length=2)
    default_currency: str = Field(min_length=3, max_length=3)


class Vehicle(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    registration_number: str
    make: str
    model: str
    fuel_type: str = "diesel"
    expected_litres_per_100km: Decimal = Field(gt=0)
    active: bool = True


class FuelTransaction(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    vehicle_id: UUID
    transaction_time: datetime
    litres: Decimal = Field(gt=0)
    price_per_litre: Decimal = Field(ge=0)
    odometer_km: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    country_code: str = Field(min_length=2, max_length=2)
