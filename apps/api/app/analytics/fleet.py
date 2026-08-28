from dataclasses import dataclass

from app.domain.fuel import analyze_fuel


@dataclass(frozen=True)
class FleetSummary:
    vehicle_count: int
    total_fuel_cost: float
    total_estimated_excess_cost: float
    critical_count: int
    high_risk_count: int
    average_variance_percent: float


def summarize_fleet(records: list[dict]) -> FleetSummary:
    if not records:
        return FleetSummary(0, 0.0, 0.0, 0, 0, 0.0)

    results = [analyze_fuel(**record) for record in records]
    return FleetSummary(
        vehicle_count=len(results),
        total_fuel_cost=round(sum(r.fuel_cost for r in results), 2),
        total_estimated_excess_cost=round(sum(r.estimated_excess_cost for r in results), 2),
        critical_count=sum(r.risk == "critical" for r in results),
        high_risk_count=sum(r.risk == "high" for r in results),
        average_variance_percent=round(sum(r.variance_percent for r in results) / len(results), 2),
    )
