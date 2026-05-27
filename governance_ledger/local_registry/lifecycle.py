"""Lifecycle transition validation for local registry events."""

from __future__ import annotations

ALLOWED_TRANSITIONS = {
    None: {"drafted"},
    "drafted": {"reviewed", "revoked"},
    "reviewed": {"exported", "revoked"},
    "exported": {"registered", "revoked"},
    "registered": {"superseded", "revoked"},
    "superseded": {"revoked"},
    "revoked": set(),
}


def validate_lifecycle_transition(previous_event_type: str | None, next_event_type: str) -> None:
    """Validate local authority lifecycle event ordering."""
    allowed = ALLOWED_TRANSITIONS.get(previous_event_type, set())
    if next_event_type not in allowed:
        previous = previous_event_type or "start"
        raise ValueError(f"invalid lifecycle transition: {previous} -> {next_event_type}")
