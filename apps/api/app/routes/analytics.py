from fastapi import APIRouter

from app.analytics.fleet import summarize_fleet
from app.analytics.sample_data import SAMPLE_FLEET

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/fleet/summary")
def fleet_summary() -> dict:
    summary = summarize_fleet(SAMPLE_FLEET)
    return summary.__dict__
