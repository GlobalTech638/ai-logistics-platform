from datetime import datetime
from pydantic import BaseModel, Field


class TripRecord(BaseModel):
    vehicle_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    distance_km: float = Field(gt=0)
    planned_duration_minutes: int = Field(gt=0)
    actual_duration_minutes: int = Field(gt=0)
    load_tonnes: float = Field(ge=0)
    completed_at: datetime
    country_code: str = Field(min_length=2, max_length=2)


class TripIntelligence(BaseModel):
    vehicle_id: str
    origin: str
    destination: str
    delay_minutes: int
    delay_percent: float
    utilization_tonnes_per_100km: float
    risk: str
    recommendation: str


def analyze_trip(trip: TripRecord) -> TripIntelligence:
    delay = max(trip.actual_duration_minutes - trip.planned_duration_minutes, 0)
    delay_percent = (delay / trip.planned_duration_minutes) * 100
    utilization = (trip.load_tonnes / trip.distance_km) * 100

    if delay_percent >= 30:
        risk = "critical"
        recommendation = "Investigate route conditions, congestion, border delays, and dispatch planning."
    elif delay_percent >= 15:
        risk = "high"
        recommendation = "Review route performance and compare actual travel time with historical trips."
    elif delay_percent >= 8:
        risk = "medium"
        recommendation = "Monitor this corridor for recurring delays."
    else:
        risk = "low"
        recommendation = "Trip completed within expected operational tolerance."

    return TripIntelligence(
        vehicle_id=trip.vehicle_id,
        origin=trip.origin,
        destination=trip.destination,
        delay_minutes=delay,
        delay_percent=round(delay_percent, 2),
        utilization_tonnes_per_100km=round(utilization, 3),
        risk=risk,
        recommendation=recommendation,
    )
