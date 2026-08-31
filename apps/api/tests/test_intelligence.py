from app.services.alert_engine import build_alerts
from app.services.dispatch_optimizer import optimize_dispatch
from app.services.load_matching import rank_load_matches
from app.services.vehicle_health import calculate_vehicle_health


def test_vehicle_health_combines_risk_signals():
    result = calculate_vehicle_health("TRUCK-01", 80, 60, 40)
    assert result.health_score == 30.0
    assert result.status == "critical"
    assert result.priority == "immediate"


def test_load_matching_rejects_over_capacity():
    matches = rank_load_matches(
        [{"vehicle_id": "V1", "capacity_tonnes": 10, "destination": "Nairobi", "available_from": "2026-09-01"}],
        [{"shipment_id": "S1", "weight_tonnes": 12, "origin": "Nairobi", "pickup_date": "2026-09-01"}],
    )
    assert matches == []


def test_dispatch_rejects_route_mismatch():
    result = optimize_dispatch(
        {"vehicle_id": "V1", "capacity_tonnes": 20, "destination": "Nairobi", "available_from": "2026-09-01", "position_distance_km": 10},
        {"shipment_id": "S1", "weight_tonnes": 10, "origin": "Mombasa", "pickup_date": "2026-09-01"},
        90,
        20,
    )
    assert result is None


def test_alert_engine_prioritizes_critical_signals():
    alerts = build_alerts("V1", 85, 65, 25)
    assert [alert.alert_type for alert in alerts] == ["fuel_anomaly", "maintenance_risk"]
    assert alerts[0].severity == "critical"
    assert alerts[1].severity == "high"
