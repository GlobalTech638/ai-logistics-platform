from dataclasses import dataclass


@dataclass(frozen=True)
class ShipmentRisk:
    shipment_id: str
    risk_score: float
    risk_level: str
    factors: list[str]
    recommended_action: str


def assess_shipment_risk(
    shipment_id: str,
    corridor_risk_score: float = 0.0,
    vehicle_health_score: float = 100.0,
    delay_risk_pct: float = 0.0,
    priority_weight: float = 0.0,
) -> ShipmentRisk:
    """Combine operational signals into a shipment-level execution risk score."""
    inputs = [corridor_risk_score, vehicle_health_score, delay_risk_pct, priority_weight]
    if any(value < 0 for value in inputs):
        raise ValueError("Shipment risk inputs cannot be negative")

    corridor = min(40.0, corridor_risk_score * 0.4)
    vehicle = min(25.0, max(0.0, 100.0 - vehicle_health_score) * 0.25)
    delay = min(30.0, delay_risk_pct * 0.3)
    priority = min(5.0, priority_weight)
    score = round(min(100.0, corridor + vehicle + delay + priority), 1)

    factors: list[str] = []
    if corridor_risk_score >= 45:
        factors.append("corridor risk")
    if vehicle_health_score < 60:
        factors.append("vehicle health")
    if delay_risk_pct >= 20:
        factors.append("delivery delay risk")
    if priority_weight >= 3:
        factors.append("high shipment priority")

    if score >= 70:
        level = "critical"
        action = "Escalate shipment, review vehicle assignment, and consider alternate routing."
    elif score >= 45:
        level = "high"
        action = "Prioritize monitoring and add an operational ETA buffer."
    elif score >= 25:
        level = "medium"
        action = "Monitor shipment closely and reassess before the next dispatch milestone."
    else:
        level = "low"
        action = "Continue normal shipment monitoring."

    return ShipmentRisk(
        shipment_id=shipment_id,
        risk_score=score,
        risk_level=level,
        factors=factors or ["no dominant risk factor"],
        recommended_action=action,
    )
