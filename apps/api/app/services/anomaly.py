from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalyResult:
    vehicle_id: str
    baseline_litres_per_100km: float
    current_litres_per_100km: float
    deviation_percent: float
    anomaly_score: float
    severity: str
    possible_causes: list[str]
    recommended_action: str


def detect_fuel_anomaly(
    vehicle_id: str,
    historical_litres_per_100km: list[float],
    current_litres_per_100km: float,
) -> AnomalyResult:
    if not historical_litres_per_100km:
        raise ValueError("historical_litres_per_100km cannot be empty")
    if any(value <= 0 for value in historical_litres_per_100km) or current_litres_per_100km <= 0:
        raise ValueError("fuel-efficiency values must be greater than zero")

    baseline = sum(historical_litres_per_100km) / len(historical_litres_per_100km)
    deviation = ((current_litres_per_100km - baseline) / baseline) * 100
    score = min(100.0, max(0.0, abs(deviation) * 2.5))

    if deviation >= 25:
        severity = "critical"
        causes = ["fuel leakage", "vehicle fault", "fuel theft", "severe route conditions"]
        action = "Inspect the vehicle and fuel records before the next dispatch."
    elif deviation >= 15:
        severity = "high"
        causes = ["maintenance issue", "driving behavior", "route conditions"]
        action = "Schedule an inspection and compare the trip with route and driver history."
    elif deviation >= 8:
        severity = "medium"
        causes = ["traffic", "load variation", "driving behavior"]
        action = "Monitor the next trips and collect supporting operational data."
    else:
        severity = "low"
        causes = []
        action = "No immediate intervention; continue monitoring the baseline."

    return AnomalyResult(
        vehicle_id=vehicle_id,
        baseline_litres_per_100km=round(baseline, 2),
        current_litres_per_100km=round(current_litres_per_100km, 2),
        deviation_percent=round(deviation, 2),
        anomaly_score=round(score, 1),
        severity=severity,
        possible_causes=causes,
        recommended_action=action,
    )
