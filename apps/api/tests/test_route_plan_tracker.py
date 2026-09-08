import pytest

from app.services.route_plan_tracker import validate_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [("planned", "active"), ("active", "superseded")],
)
def test_valid_route_plan_transitions(current: str, target: str) -> None:
    validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("planned", "superseded"),
        ("active", "planned"),
        ("superseded", "active"),
        ("superseded", "planned"),
    ],
)
def test_invalid_route_plan_transitions(current: str, target: str) -> None:
    with pytest.raises(ValueError):
        validate_transition(current, target)
