from datetime import datetime, timezone

from fastapi import APIRouter

from app.analytics.corridors import summarize_corridors
from app.schemas.trips import TripRecord

router = APIRouter(prefix="/api/v1/analytics", tags=["corridors"])

SAMPLE_TRIPS = [
    TripRecord(vehicle_id="KE-KDA-431A", origin="Nairobi", destination="Mombasa", distance_km=485, planned_duration_minutes=420, actual_duration_minutes=575, load_tonnes=18, completed_at=datetime.now(timezone.utc), country_code="KE"),
    TripRecord(vehicle_id="KE-KDB-982P", origin="Nairobi", destination="Mombasa", distance_km=485, planned_duration_minutes=420, actual_duration_minutes=510, load_tonnes=21, completed_at=datetime.now(timezone.utc), country_code="KE"),
    TripRecord(vehicle_id="UG-UAX-204K", origin="Kampala", destination="Mombasa", distance_km=1170, planned_duration_minutes=1200, actual_duration_minutes=1450, load_tonnes=16, completed_at=datetime.now(timezone.utc), country_code="UG"),
    TripRecord(vehicle_id="TZ-T-482B", origin="Dar es Salaam", destination="Arusha", distance_km=640, planned_duration_minutes=600, actual_duration_minutes=620, load_tonnes=12, completed_at=datetime.now(timezone.utc), country_code="TZ"),
]


@router.get("/corridors")
def corridor_intelligence() -> list[dict]:
    return [item.__dict__ for item in summarize_corridors(SAMPLE_TRIPS)]
