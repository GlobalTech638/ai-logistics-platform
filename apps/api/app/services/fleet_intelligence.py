from dataclasses import dataclass

from app.domain.fuel import analyze_fuel


@dataclass(frozen=True)
class VehicleFuelSnapshot:
    vehicle_id: str
    actual_litres_per_100km: float
    expected_litres_per_100km: float
    variance_percent: float
    estimated_excess_cost: float
    risk: str


def rank_vehicle_cost_risk(records: list[dict]) -> list[VehicleFuelSnapshot]:
    snapshots = []
    for record in records:
        result = analyze_fuel(**record)
        snapshots.append(
            VehicleFuelSnapshot(
                vehicle_id=result.vehicle_id,
                actual_litres_per_100km=result.actual_litres_per_100km,
                expected_litres_per_100km=result.expected_litres_per_100km,
                variance_percent=result.variance_percent,
                estimated_excess_cost=result.estimated_excess_cost,
                risk=result.risk,
            )
        )

    return sorted(
        snapshots,
        key=lambda item: item.estimated_excess_cost,
        reverse=True,
    )
