from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AlertDecision:
    alert_type: str
    severity: str
    score: float
    message: str
    recommended_action: str


def build_alerts(
    vehicle_id: str,
    fuel_anomaly_score: float,
    maintenance_risk_score: float,
    route_risk_score: float,
) -> list[AlertDecision]:
    signals: list[tuple[str, float, str, str, str]] = [
        (
            "fuel_anomaly",
            fuel_anomaly_score,
            "Abnormal fuel behavior detected.",
            "Review fuel transactions, trip history, and vehicle condition.",
            "fuel",
        ),
        (
            "maintenance_risk",
            maintenance_risk_score,
            "Vehicle maintenance risk is increasing.",
            "Schedule an inspection and review recent maintenance history.",
            "maintenance",
        ),
        (
            "route_risk",
            route_risk_score,
            "Route performance risk is elevated.",
            "Review the corridor, ETA forecast, and alternative routing options.",
            "route",
        ),
    ]

    alerts = []
    for alert_type, score, message, action, _ in signals:
        score = max(0.0, min(100.0, score))
        if score >= 80:
            severity = "critical"
        elif score >= 60:
            severity = "high"
        elif score >= 40:
            severity = "medium"
        else:
            continue

        alerts.append(
            AlertDecision(
                alert_type=alert_type,
                severity=severity,
                score=round(score, 1),
                message=f"{vehicle_id}: {message}",
                recommended_action=action,
            )
        )

    return sorted(alerts, key=lambda alert: alert.score, reverse=True)
