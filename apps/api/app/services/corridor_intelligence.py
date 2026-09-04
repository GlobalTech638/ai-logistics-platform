from dataclasses import dataclass


@dataclass(frozen=True)
class CorridorRisk:
    corridor: str
    risk_score: float
    risk_level: str
    primary_factors: list[str]
    recommended_action: str


def assess_corridor_risk(
    corridor: str,
    delay_rate_pct: float,
    border_wait_hours: float = 0.0,
    incident_rate_pct: float = 0.0,
) -> CorridorRisk:
    """Score corridor risk from observed performance and optional external signals."""
    if min(delay_rate_pct, border_wait_hours, incident_rate_pct) < 0:
        raise ValueError("Risk inputs cannot be negative")

    delay_component = min(70.0, delay_rate_pct * 2.0)
    border_component = min(20.0, border_wait_hours * 2.5)
    incident_component = min(20.0, incident_rate_pct * 2.0)
    score = min(100.0, delay_component + border_component + incident_component)

    factors = []
    if delay_rate_pct >= 20:
        factors.append("elevated delivery delays")
    elif delay_rate_pct >= 10:
        factors.append("rising delivery delays")
    if border_wait_hours >= 6:
        factors.append("long border processing times")
    if incident_rate_pct >= 10:
        factors.append("high incident frequency")

    if score >= 70:
        level = "critical"
        action = "Review alternative routing, dispatch buffers, and border documentation readiness."
    elif score >= 45:
        level = "high"
        action = "Increase ETA buffers and monitor corridor conditions before dispatch."
    elif score >= 25:
        level = "medium"
        action = "Monitor corridor performance and flag deteriorating conditions."
    else:
        level = "low"
        action = "Continue normal monitoring."

    return CorridorRisk(
        corridor=corridor,
        risk_score=round(score, 1),
        risk_level=level,
        primary_factors=factors or ["no dominant risk factor"],
        recommended_action=action,
    )
