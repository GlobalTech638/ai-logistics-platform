from dataclasses import dataclass


@dataclass(frozen=True)
class FuelAnalysis:
    actual_litres_per_100km: float
    variance_percent: float
    fuel_cost: float
    estimated_excess_cost: float
    risk: str
    recommendation: str


def analyze_fuel(
    distance_km: float,
    fuel_litres: float,
    fuel_price_per_litre: float,
    expected_litres_per_100km: float,
) -> FuelAnalysis:
    actual = (fuel_litres / distance_km) * 100
    variance = ((actual - expected_litres_per_100km) / expected_litres_per_100km) * 100
    fuel_cost = fuel_litres * fuel_price_per_litre

    expected_litres = distance_km * expected_litres_per_100km / 100
    excess_litres = max(fuel_litres - expected_litres, 0)
    excess_cost = excess_litres * fuel_price_per_litre

    if variance >= 25:
        risk = "high"
        recommendation = "Investigate fuel usage, vehicle condition, driver behavior and route conditions."
    elif variance >= 10:
        risk = "medium"
        recommendation = "Monitor fuel consumption and investigate recurring inefficiency."
    else:
        risk = "low"
        recommendation = "Fuel consumption is within the expected operating range."

    return FuelAnalysis(
        actual_litres_per_100km=round(actual, 2),
        variance_percent=round(variance, 2),
        fuel_cost=round(fuel_cost, 2),
        estimated_excess_cost=round(excess_cost, 2),
        risk=risk,
        recommendation=recommendation,
    )
