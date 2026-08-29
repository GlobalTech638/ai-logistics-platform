from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass(frozen=True)
class FuelAnomaly:
    vehicle_id: str
    actual_litres_per_100km: float
    baseline_litres_per_100km: float
    z_score: float
    severity: str
    explanation: str


def detect_fuel_anomalies(records: list[dict]) -> list[FuelAnomaly]:
    if len(records) < 2:
        return []

    efficiencies = [
        (item["fuel_litres"] / item["distance_km"]) * 100
        for item in records
        if item["distance_km"] > 0 and item["fuel_litres"] > 0
    ]
    if len(efficiencies) < 2:
        return []

    baseline = mean(efficiencies)
    deviation = pstdev(efficiencies)
    if deviation == 0:
        return []

    results = []
    for item in records:
        actual = (item["fuel_litres"] / item["distance_km"]) * 100
        z_score = (actual - baseline) / deviation
        magnitude = abs(z_score)

        if magnitude >= 3:
            severity = "critical"
        elif magnitude >= 2:
            severity = "high"
        elif magnitude >= 1.5:
            severity = "medium"
        else:
            continue

        direction = "higher" if z_score > 0 else "lower"
        explanation = (
            f"Fuel consumption is {direction} than the fleet baseline; "
            "investigate route conditions, vehicle condition, fuel records, "
            "and operating behavior before taking action."
        )
        results.append(
            FuelAnomaly(
                vehicle_id=item["vehicle_id"],
                actual_litres_per_100km=round(actual, 2),
                baseline_litres_per_100km=round(baseline, 2),
                z_score=round(z_score, 2),
                severity=severity,
                explanation=explanation,
            )
        )

    return sorted(results, key=lambda item: abs(item.z_score), reverse=True)
