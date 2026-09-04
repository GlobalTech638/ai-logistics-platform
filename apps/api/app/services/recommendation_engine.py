from dataclasses import dataclass


@dataclass(frozen=True)
class Recommendation:
    recommendation_type: str
    priority: str
    score: float
    title: str
    rationale: str
    actions: list[str]
    expected_impact: str


def _priority(score: float) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def build_recommendations(
    shipment_id: str,
    shipment_risk_score: float,
    shipment_risk_level: str,
    corridor_risk_score: float = 0.0,
    vehicle_health_score: float = 100.0,
    estimated_excess_fuel_cost: float = 0.0,
    currency: str = "KES",
) -> list[Recommendation]:
    """Generate deterministic, explainable operational recommendations.

    This is intentionally rule-based: recommendations must be auditable before
    introducing an ML/LLM decision layer.
    """
    inputs = [
        shipment_risk_score,
        corridor_risk_score,
        vehicle_health_score,
        estimated_excess_fuel_cost,
    ]
    if any(value < 0 for value in inputs):
        raise ValueError("Recommendation inputs cannot be negative")
    if shipment_risk_score > 100 or corridor_risk_score > 100 or vehicle_health_score > 100:
        raise ValueError("Risk and health scores must be between 0 and 100")

    recommendations: list[Recommendation] = []

    if shipment_risk_score >= 70 and corridor_risk_score >= 45:
        score = min(100.0, max(shipment_risk_score, corridor_risk_score) + 10.0)
        recommendations.append(
            Recommendation(
                "reroute_shipment",
                _priority(score),
                round(score, 1),
                "Review alternate routing",
                f"Shipment {shipment_id} has critical execution risk and elevated corridor risk.",
                [
                    "Compare alternate corridors and current border conditions.",
                    "Recalculate ETA with realistic corridor buffers.",
                    "Confirm customer impact before dispatching the revised route.",
                ],
                "Reduce exposure to corridor-driven delay and missed delivery windows.",
            )
        )

    if shipment_risk_score >= 45 and vehicle_health_score < 60:
        score = min(100.0, shipment_risk_score + (60.0 - vehicle_health_score) * 0.5)
        recommendations.append(
            Recommendation(
                "reassign_vehicle",
                _priority(score),
                round(score, 1),
                "Review vehicle assignment",
                f"Shipment {shipment_id} is exposed to execution risk while its assigned vehicle health is below 60.",
                [
                    "Inspect the vehicle before departure.",
                    "Check whether a healthy replacement vehicle is available.",
                    "Only dispatch after the reassignment or maintenance decision is recorded.",
                ],
                "Reduce breakdown and service-disruption risk on the shipment.",
            )
        )

    if estimated_excess_fuel_cost > 0:
        score = min(100.0, 25.0 + estimated_excess_fuel_cost / 1000.0 * 25.0)
        recommendations.append(
            Recommendation(
                "investigate_fuel_cost",
                _priority(score),
                round(score, 1),
                "Investigate excess fuel cost",
                f"Observed fuel consumption is above the expected baseline, with an estimated excess cost of {currency.upper()} {estimated_excess_fuel_cost:,.2f}.",
                [
                    "Review fuel transactions against trip distance and odometer readings.",
                    "Check for route, idling, maintenance, or fuel-control anomalies.",
                    "Record the investigation outcome for future model calibration.",
                ],
                "Identify avoidable operating cost and improve fuel-efficiency controls.",
            )
        )

    if not recommendations and shipment_risk_score >= 25:
        recommendations.append(
            Recommendation(
                "monitor_shipment",
                _priority(shipment_risk_score),
                round(shipment_risk_score, 1),
                "Increase shipment monitoring",
                f"Shipment {shipment_id} has {shipment_risk_level} execution risk without a stronger intervention signal.",
                [
                    "Monitor the next dispatch milestone.",
                    "Refresh ETA and corridor conditions when new data arrives.",
                ],
                "Limit escalation while maintaining visibility on a deteriorating shipment.",
            )
        )

    return sorted(recommendations, key=lambda item: item.score, reverse=True)
