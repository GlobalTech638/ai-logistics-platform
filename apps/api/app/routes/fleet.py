from fastapi import APIRouter

from app.schemas.fleet import FuelAnalysisRequest, FuelAnalysisResponse
from services.fuel.analyzer import analyze_fuel

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet"])


@router.post("/analyze", response_model=FuelAnalysisResponse)
def analyze_fleet_cost(payload: FuelAnalysisRequest) -> FuelAnalysisResponse:
    result = analyze_fuel(
        distance_km=payload.distance_km,
        fuel_litres=payload.fuel_litres,
        fuel_price_per_litre=payload.fuel_price_per_litre,
        expected_litres_per_100km=payload.expected_litres_per_100km,
    )

    return FuelAnalysisResponse(
        vehicle_id=payload.vehicle_id,
        **result.__dict__,
    )
