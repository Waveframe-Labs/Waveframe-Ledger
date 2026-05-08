"""Deterministic lifecycle transitions for governance review artifacts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from governance_authoring.provenance import _utc_now

VALID_REVIEW_STATUSES = {
    "pending",
    "reviewed",
    "approved",
    "rejected",
    "compiled",
    "deployed",
}

ALLOWED_REVIEW_TRANSITIONS = {
    "pending": {"reviewed", "rejected"},
    "reviewed": {"approved", "rejected"},
    "approved": {"compiled"},
    "compiled": {"deployed"},
    "rejected": set(),
    "deployed": set(),
}


def transition_review_status(
    review: dict[str, Any],
    new_status: str,
    *,
    actor: str | None = None,
    timestamp: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Return a copied review artifact with an appended lifecycle transition."""
    current_status = review.get("review_status")
    _validate_status(current_status, "current")
    _validate_status(new_status, "new")
    _validate_transition(current_status, new_status)

    updated_review = deepcopy(review)
    updated_review["review_status"] = new_status
    updated_review.setdefault("lifecycle", []).append(
        {
            "from_status": current_status,
            "to_status": new_status,
            "actor": actor,
            "timestamp": timestamp or _utc_now(),
            "note": note,
        }
    )

    return updated_review


def _validate_status(status: Any, label: str) -> None:
    if status not in VALID_REVIEW_STATUSES:
        raise ValueError(f"Invalid {label} review status: {status!r}")


def _validate_transition(current_status: str, new_status: str) -> None:
    allowed_statuses = ALLOWED_REVIEW_TRANSITIONS[current_status]
    if new_status not in allowed_statuses:
        raise ValueError(
            f"Invalid review status transition: {current_status!r} -> {new_status!r}"
        )
