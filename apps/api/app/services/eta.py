from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class ETAResult:
    planned_arrival_minutes: int
    predicted_arrival_minutes: int
    predicted_delay_minutes: int
    delay_probability_percent: float
    confidence_percent: float
    risk: str
    recommendation: str


def predict_eta(
    planned_duration_minutes: int,
    corridor_average_delay_percent: float,
    current_delay_minutes: int = 0,
) -> ETAResult:
    if planned_duration_minutes <= 0:
        raise ValueError("planned_duration_minutes must be greater than zero")
    if corridor_average_delay_percent < 0 or current_delay_minutes < 0:
        raise ValueError("delay values cannot be negative")

    corridor_delay = planned_duration_minutes * (corridor_average_delay_percent / 100)
    predicted_delay = ceil(max(corridor_delay, current_delay_minutes))
    probability = min(95.0, max(5.0, 20.0 + corridor_average_delay_percent * 2.0))
    confidence = min(92.0, max(55.0, 88.0 - corridor_average_delay_percent * 0.7))

    if probability >= 70:
        risk = "high"
        recommendation = "Notify the customer early and review the delivery window or alternate route."
    elif probability >= 40:
        risk = "medium"
        recommendation = "Monitor the trip closely and prepare a contingency delivery window."
    else:
        risk = "low"
        recommendation = "Continue monitoring; no immediate intervention is required."

    return ETAResult(
        planned_arrival_minutes=planned_duration_minutes,
        predicted_arrival_minutes=planned_duration_minutes + predicted_delay,
        predicted_delay_minutes=predicted_delay,
        delay_probability_percent=round(probability, 1),
        confidence_percent=round(confidence, 1),
        risk=risk,
        recommendation=recommendation,
    )
