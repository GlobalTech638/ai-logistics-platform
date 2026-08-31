from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.load_matching import rank_load_matches

router = APIRouter(prefix="/api/v1/optimization", tags=["optimization"])


class Vehicle(BaseModel):
    vehicle_id: str
    capacity_tonnes: float = Field(gt=0)
    destination: str
    available_from: str
    position_distance_km: float = Field(default=0, ge=0)


class Shipment(BaseModel):
    shipment_id: str
    weight_tonnes: float = Field(gt=0)
    origin: str
    pickup_date: str


class LoadMatchRequest(BaseModel):
    vehicles: list[Vehicle]
    shipments: list[Shipment]


@router.post("/load-matches")
def load_matches(request: LoadMatchRequest) -> list[dict]:
    return [
        item.__dict__
        for item in rank_load_matches(
            [item.model_dump() for item in request.vehicles],
            [item.model_dump() for item in request.shipments],
        )
    ]
