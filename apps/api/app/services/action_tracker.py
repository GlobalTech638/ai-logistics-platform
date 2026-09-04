from datetime import datetime, timezone


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"accepted", "rejected"},
    "accepted": {"in_progress", "rejected"},
    "in_progress": {"completed"},
    "completed": set(),
    "rejected": set(),
}


def validate_transition(current_status: str, target_status: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current_status)
    if allowed is None:
        raise ValueError(f"Unknown recommendation action status: {current_status}")
    if target_status not in allowed:
        raise ValueError(
            f"Cannot transition recommendation action from {current_status} to {target_status}"
        )


def completed_at_for_status(status: str) -> datetime | None:
    if status == "completed":
        return datetime.now(timezone.utc)
    return None
