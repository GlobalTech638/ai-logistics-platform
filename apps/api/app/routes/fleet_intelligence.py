from fastapi import APIRouter

from app.schemas.fleet_intelligence import (
    FleetRankingRequest,
    FleetRankingResponse,
    FleetVehicleRisk,
)
from app.services.fleet_intelligence import rank_vehicle_cost_risk

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet-intelligence"])


@router.post("/rank-cost-risk", response_model=FleetRankingResponse)
def rank_cost_risk(request: FleetRankingRequest) -> FleetRankingResponse:
    records = [vehicle.model_dump() for vehicle in request.vehicles]
    results = rank_vehicle_cost_risk(records)
    vehicles = [FleetVehicleRisk(**result.__dict__) for result in results]

    return FleetRankingResponse(
        vehicle_count=len(vehicles),
        total_estimated_excess_cost=round(
            sum(vehicle.estimated_excess_cost for vehicle in vehicles), 2
        ),
        critical_vehicle_count=sum(vehicle.risk == "critical" for vehicle in vehicles),
        high_risk_vehicle_count=sum(vehicle.risk == "high" for vehicle in vehicles),
        vehicles=vehicles,
    )
