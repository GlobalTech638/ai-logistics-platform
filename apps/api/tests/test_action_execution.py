import pytest

from app.services.action_execution import validate_vehicle_reassignment


def test_active_vehicle_with_sufficient_capacity_is_eligible() -> None:
    decision = validate_vehicle_reassignment(8, 12, True)
    assert decision.allowed is True


def test_inactive_vehicle_is_rejected() -> None:
    decision = validate_vehicle_reassignment(8, 12, False)
    assert decision.allowed is False
    assert "inactive" in decision.reason.lower()


def test_vehicle_with_insufficient_capacity_is_rejected() -> None:
    decision = validate_vehicle_reassignment(12, 8, True)
    assert decision.allowed is False
    assert "capacity" in decision.reason.lower()


@pytest.mark.parametrize(
    ("shipment_weight", "vehicle_capacity"),
    [(0, 10), (-1, 10), (10, 0), (10, -1)],
)
def test_invalid_capacity_inputs_raise(shipment_weight: float, vehicle_capacity: float) -> None:
    with pytest.raises(ValueError):
        validate_vehicle_reassignment(shipment_weight, vehicle_capacity, True)
