from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleHealthSignals:
    fuel_score: float
    maintenance_score: float
    utilization_score: float


def calculate_vehicle_health_signals(
    *,
    actual_fuel_litres: float,
    expected_fuel_litres: float,
    maintenance_events: int,
    trips: int,
    active_trips: int,
) -> VehicleHealthSignals:
    if actual_fuel_litres < 0 or expected_fuel_litres < 0:
        raise ValueError("Fuel litres cannot be negative")
    if maintenance_events < 0 or trips < 0 or active_trips < 0:
        raise ValueError("Operational counts cannot be negative")

    fuel_variance_pct = (
        0.0
        if expected_fuel_litres <= 0
        else max(0.0, ((actual_fuel_litres - expected_fuel_litres) / expected_fuel_litres) * 100)
    )
    fuel_score = min(100.0, fuel_variance_pct * 2)

    # Maintenance events are a transparent baseline until service intervals,
    # severity and time-since-service are modeled in the operational schema.
    maintenance_score = min(100.0, float(maintenance_events) * 15)
    utilization_score = min(100.0, (float(active_trips) * 20) + (float(trips) * 2))

    return VehicleHealthSignals(
        fuel_score=fuel_score,
        maintenance_score=maintenance_score,
        utilization_score=utilization_score,
    )
