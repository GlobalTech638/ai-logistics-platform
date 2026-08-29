from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceRisk:
    vehicle_id: str
    risk_score: float
    severity: str
    signals: list[str]
    recommended_action: str


def assess_maintenance_risk(
    vehicle_id: str,
    kilometers_since_service: float,
    service_interval_km: float,
    recent_anomaly_count: int = 0,
    recent_trip_delay_percent: float = 0.0,
) -> MaintenanceRisk:
    if kilometers_since_service < 0 or service_interval_km <= 0:
        raise ValueError("invalid service interval values")
    if recent_anomaly_count < 0 or recent_trip_delay_percent < 0:
        raise ValueError("risk signals cannot be negative")

    service_ratio = kilometers_since_service / service_interval_km
    score = min(100.0, service_ratio * 70 + min(recent_anomaly_count, 5) * 5 + min(recent_trip_delay_percent, 30) * 0.5)

    signals = []
    if service_ratio >= 1:
        signals.append("service interval reached")
    elif service_ratio >= 0.8:
        signals.append("service interval approaching")
    if recent_anomaly_count >= 2:
        signals.append("repeated operational anomalies")
    if recent_trip_delay_percent >= 15:
        signals.append("recent trip delays")

    if score >= 80:
        severity = "critical"
        action = "Schedule maintenance inspection before the next long-haul dispatch."
    elif score >= 55:
        severity = "high"
        action = "Schedule maintenance soon and inspect recurring operational signals."
    elif score >= 30:
        severity = "medium"
        action = "Monitor the vehicle and plan the next service window."
    else:
        severity = "low"
        action = "Continue normal preventive-maintenance monitoring."

    return MaintenanceRisk(
        vehicle_id=vehicle_id,
        risk_score=round(score, 1),
        severity=severity,
        signals=signals,
        recommended_action=action,
    )
