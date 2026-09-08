from __future__ import annotations

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"active"},
    "active": {"superseded"},
    "superseded": set(),
}


def validate_transition(current_status: str, target_status: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise ValueError(
            f"Invalid route plan transition: {current_status} -> {target_status}"
        )
