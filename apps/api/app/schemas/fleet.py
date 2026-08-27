from pydantic import BaseModel, Field


class FuelAnalysisRequest(BaseModel):
    vehicle_id: str = Field(min_length=1)
    distance_km: float = Field(gt=0)
    fuel_litres: float = Field(gt=0)
    fuel_price_per_litre: float = Field(ge=0)
    expected_litres_per_100km: float = Field(gt=0)


class FuelAnalysisResponse(BaseModel):
    vehicle_id: str
    actual_litres_per_100km: float
    expected_litres_per_100km: float
    variance_percent: float
    fuel_cost: float
    estimated_excess_cost: float
    risk: str
    recommendation: str
