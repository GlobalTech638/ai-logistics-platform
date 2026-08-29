from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.eta import predict_eta

router = APIRouter(prefix="/api/v1/eta", tags=["eta"])


class ETARequest(BaseModel):
    planned_duration_minutes: int = Field(gt=0)
    corridor_average_delay_percent: float = Field(ge=0)
    current_delay_minutes: int = Field(default=0, ge=0)


@router.post("/predict")
def predict(request: ETARequest) -> dict:
    return predict_eta(**request.model_dump()).__dict__
