"""Review report convenience API."""

from __future__ import annotations

from typing import Any

from governance_authoring.extract import extract_constraints
from governance_authoring.review import build_review_report


def review_constraints(text: str) -> dict[str, Any]:
    """Extract policy text and return the human-reviewable detection report."""
    policy = extract_constraints(text)
    return build_review_report(text, policy)
