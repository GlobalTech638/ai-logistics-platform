import pytest

from app.services.vehicle_health_signals import calculate_vehicle_health_signals


def test_vehicle_health_signals_calculate_fuel_variance():
    result = calculate_vehicle_health_signals(
        actual_fuel_litres=120,
        expected_fuel_litres=100,
        maintenance_events=2,
        trips=5,
        active_trips=1,
    )

    assert result.fuel_score == 40.0
    assert result.maintenance_score == 30.0
    assert result.utilization_score == 30.0


def test_vehicle_health_signals_cap_operational_scores():
    result = calculate_vehicle_health_signals(
        actual_fuel_litres=500,
        expected_fuel_litres=100,
        maintenance_events=20,
        trips=100,
        active_trips=10,
    )

    assert result.fuel_score == 100.0
    assert result.maintenance_score == 100.0
    assert result.utilization_score == 100.0


def test_vehicle_health_signals_allow_missing_fuel_baseline():
    result = calculate_vehicle_health_signals(
        actual_fuel_litres=50,
        expected_fuel_litres=0,
        maintenance_events=0,
        trips=0,
        active_trips=0,
    )

    assert result.fuel_score == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"actual_fuel_litres": -1, "expected_fuel_litres": 10, "maintenance_events": 0, "trips": 0, "active_trips": 0},
        {"actual_fuel_litres": 10, "expected_fuel_litres": -1, "maintenance_events": 0, "trips": 0, "active_trips": 0},
        {"actual_fuel_litres": 10, "expected_fuel_litres": 10, "maintenance_events": -1, "trips": 0, "active_trips": 0},
        {"actual_fuel_litres": 10, "expected_fuel_litres": 10, "maintenance_events": 0, "trips": -1, "active_trips": 0},
        {"actual_fuel_litres": 10, "expected_fuel_litres": 10, "maintenance_events": 0, "trips": 0, "active_trips": -1},
    ],
)
def test_vehicle_health_signals_reject_negative_inputs(kwargs):
    with pytest.raises(ValueError):
        calculate_vehicle_health_signals(**kwargs)
