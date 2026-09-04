import pytest

from app.services.action_tracker import completed_at_for_status, validate_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("proposed", "accepted"),
        ("proposed", "rejected"),
        ("accepted", "in_progress"),
        ("accepted", "rejected"),
        ("in_progress", "completed"),
    ],
)
def test_valid_action_transitions(current: str, target: str) -> None:
    validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("proposed", "in_progress"),
        ("proposed", "completed"),
        ("accepted", "completed"),
        ("in_progress", "accepted"),
        ("in_progress", "rejected"),
        ("completed", "accepted"),
        ("rejected", "accepted"),
    ],
)
def test_invalid_action_transitions(current: str, target: str) -> None:
    with pytest.raises(ValueError):
        validate_transition(current, target)


def test_completed_status_gets_timestamp() -> None:
    assert completed_at_for_status("completed") is not None


def test_non_completed_status_has_no_completion_timestamp() -> None:
    assert completed_at_for_status("in_progress") is None
