from dataclasses import dataclass


@dataclass(frozen=True)
class CostImpact:
    currency: str
    excess_fuel_litres: float
    estimated_excess_cost: float
    confidence: float


def calculate_fuel_cost_impact(
    actual_litres: float,
    expected_litres: float,
    fuel_price_per_litre: float,
    currency: str = "KES",
) -> CostImpact:
    if actual_litres < 0 or expected_litres < 0 or fuel_price_per_litre < 0:
        raise ValueError("Cost inputs cannot be negative")
    excess = max(0.0, actual_litres - expected_litres)
    cost = excess * fuel_price_per_litre
    confidence = 0.95 if expected_litres > 0 else 0.0
    return CostImpact(
        currency=currency.upper(),
        excess_fuel_litres=round(excess, 2),
        estimated_excess_cost=round(cost, 2),
        confidence=confidence,
    )
