from pydantic import BaseModel, Field


class VehicleFuelRecord(BaseModel):
    vehicle_id: str = Field(min_length=1)
    distance_km: float = Field(gt=0)
    fuel_litres: float = Field(gt=0)
    fuel_price_per_litre: float = Field(ge=0)
    expected_litres_per_100km: float = Field(gt=0)


class FleetRankingRequest(BaseModel):
    vehicles: list[VehicleFuelRecord] = Field(min_length=1)


class FleetVehicleRisk(BaseModel):
    vehicle_id: str
    actual_litres_per_100km: float
    expected_litres_per_100km: float
    variance_percent: float
    estimated_excess_cost: float
    risk: str


class FleetRankingResponse(BaseModel):
    vehicle_count: int
    total_estimated_excess_cost: float
    critical_vehicle_count: int
    high_risk_vehicle_count: int
    vehicles: list[FleetVehicleRisk]
