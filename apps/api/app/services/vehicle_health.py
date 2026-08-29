from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleHealth:
    vehicle_id: str
    health_score: float
    status: str
    priority: str
    key_signals: list[str]
    recommended_action: str


def calculate_vehicle_health(
    vehicle_id: str,
    fuel_anomaly_score: float = 0.0,
    maintenance_risk_score: float = 0.0,
    corridor_risk_score: float = 0.0,
) -> VehicleHealth:
    scores = [fuel_anomaly_score, maintenance_risk_score, corridor_risk_score]
    if any(score < 0 or score > 100 for score in scores):
        raise ValueError("risk scores must be between 0 and 100")

    # Higher risk produces a lower health score.
    risk_score = (fuel_anomaly_score * 0.40) + (maintenance_risk_score * 0.35) + (corridor_risk_score * 0.25)
    health = round(100 - risk_score, 1)

    signals = []
    if fuel_anomaly_score >= 55:
        signals.append("abnormal fuel behavior")
    if maintenance_risk_score >= 55:
        signals.append("maintenance risk")
    if corridor_risk_score >= 55:
        signals.append("route performance risk")

    if health < 40:
        status, priority = "critical", "immediate"
        action = "Hold non-essential dispatch and investigate the vehicle before its next long-haul trip."
    elif health < 60:
        status, priority = "at_risk", "high"
        action = "Schedule an operational review and address the highest-risk signal."
    elif health < 80:
        status, priority = "watch", "medium"
        action = "Monitor the next trips and schedule preventive checks where appropriate."
    else:
        status, priority = "healthy", "low"
        action = "Continue normal operations and preventive monitoring."

    return VehicleHealth(
        vehicle_id=vehicle_id,
        health_score=health,
        status=status,
        priority=priority,
        key_signals=signals,
        recommended_action=action,
    )
