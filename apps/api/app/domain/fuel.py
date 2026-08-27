from dataclasses import dataclass


@dataclass(frozen=True)
class FuelAnalysis:
    vehicle_id: str
    actual_litres_per_100km: float
    expected_litres_per_100km: float
    variance_percent: float
    fuel_cost: float
    estimated_excess_cost: float
    risk: str
    recommendation: str


def analyze_fuel(
    vehicle_id: str,
    distance_km: float,
    fuel_litres: float,
    fuel_price_per_litre: float,
    expected_litres_per_100km: float,
) -> FuelAnalysis:
    if distance_km <= 0 or fuel_litres <= 0:
        raise ValueError("distance_km and fuel_litres must be greater than zero")
    if expected_litres_per_100km <= 0:
        raise ValueError("expected_litres_per_100km must be greater than zero")
    if fuel_price_per_litre < 0:
        raise ValueError("fuel_price_per_litre cannot be negative")

    actual = (fuel_litres / distance_km) * 100
    variance = ((actual - expected_litres_per_100km) / expected_litres_per_100km) * 100
    fuel_cost = fuel_litres * fuel_price_per_litre

    expected_litres = (distance_km / 100) * expected_litres_per_100km
    excess_litres = max(fuel_litres - expected_litres, 0)
    excess_cost = excess_litres * fuel_price_per_litre

    if variance >= 30:
        risk = "critical"
        recommendation = "Investigate fuel transactions, vehicle condition, route conditions, and driver behavior immediately."
    elif variance >= 15:
        risk = "high"
        recommendation = "Investigate fuel usage and schedule a vehicle inspection."
    elif variance >= 8:
        risk = "medium"
        recommendation = "Monitor fuel efficiency and compare against similar vehicles and routes."
    else:
        risk = "low"
        recommendation = "No immediate intervention; continue monitoring fuel efficiency."

    return FuelAnalysis(
        vehicle_id=vehicle_id,
        actual_litres_per_100km=round(actual, 2),
        expected_litres_per_100km=round(expected_litres_per_100km, 2),
        variance_percent=round(variance, 2),
        fuel_cost=round(fuel_cost, 2),
        estimated_excess_cost=round(excess_cost, 2),
        risk=risk,
        recommendation=recommendation,
    )
