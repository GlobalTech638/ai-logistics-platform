from dataclasses import dataclass


@dataclass(frozen=True)
class DispatchRecommendation:
    vehicle_id: str
    shipment_id: str
    dispatch_score: float
    vehicle_health_score: float
    route_risk_score: float
    load_utilization_percent: float
    estimated_deadhead_km: float
    rationale: list[str]
    recommended_action: str


def optimize_dispatch(
    vehicle: dict,
    shipment: dict,
    vehicle_health_score: float,
    route_risk_score: float,
) -> DispatchRecommendation | None:
    if vehicle["capacity_tonnes"] <= 0 or shipment["weight_tonnes"] <= 0:
        raise ValueError("capacity and shipment weight must be greater than zero")
    if shipment["weight_tonnes"] > vehicle["capacity_tonnes"]:
        return None
    if vehicle.get("destination") != shipment.get("origin"):
        return None
    if vehicle.get("available_from") != shipment.get("pickup_date"):
        return None

    utilization = shipment["weight_tonnes"] / vehicle["capacity_tonnes"] * 100
    deadhead = max(float(vehicle.get("position_distance_km", 0)), 0)

    utilization_score = min(utilization, 100)
    deadhead_score = max(0, 100 - deadhead / 5)
    health_component = max(0, min(vehicle_health_score, 100))
    route_component = max(0, min(100 - route_risk_score, 100))

    score = (
        utilization_score * 0.30
        + deadhead_score * 0.20
        + health_component * 0.25
        + route_component * 0.25
    )

    rationale = [
        f"{utilization:.1f}% load utilization",
        f"{deadhead:.0f} km estimated deadhead",
        f"vehicle health score {health_component:.1f}",
        f"route performance score {route_component:.1f}",
    ]

    if health_component < 40:
        action = "Do not dispatch this vehicle without operational review despite the route match."
    elif score >= 75:
        action = "Recommended dispatch: strong combined fit across utilization, health, deadhead, and route risk."
    elif score >= 55:
        action = "Conditional dispatch: review the main risk signal before assignment."
    else:
        action = "Lower-priority dispatch: consider another compatible vehicle first."

    return DispatchRecommendation(
        vehicle_id=vehicle["vehicle_id"],
        shipment_id=shipment["shipment_id"],
        dispatch_score=round(score, 1),
        vehicle_health_score=round(health_component, 1),
        route_risk_score=round(route_risk_score, 1),
        load_utilization_percent=round(utilization, 1),
        estimated_deadhead_km=round(deadhead, 1),
        rationale=rationale,
        recommended_action=action,
    )
