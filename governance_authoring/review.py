"""Build inspectable review artifacts for extracted governance constraints."""

from __future__ import annotations

import re
from typing import Any

from governance_authoring.extract import _normalize_role, _normalize_text, _parse_amount
from governance_authoring.patterns import (
    ROLE_PATTERNS,
    SEPARATION_PATTERNS,
    THRESHOLD_PATTERNS,
)


def build_review_report(text: str, policy: dict[str, Any]) -> dict[str, Any]:
    """Explain which governance constraints were detected from source text."""
    normalized_text = _normalize_text(text)
    detected_constraints: list[dict[str, Any]] = []

    for pattern in ROLE_PATTERNS:
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            role = _normalize_role(match["role"])
            if role in policy.get("authority", {}).get("required_roles", []):
                _append_unique_constraint(
                    detected_constraints,
                    {
                        "type": "required_role",
                        "value": role,
                        "source_text": match.group(0),
                    },
                )

    for pattern in SEPARATION_PATTERNS:
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            if policy.get("invariants", {}).get("separation_of_duties") is True:
                _append_unique_constraint(
                    detected_constraints,
                    {
                        "type": "separation_of_duties",
                        "value": True,
                        "source_text": match.group(0),
                    },
                )

    for pattern in THRESHOLD_PATTERNS:
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            threshold = _parse_amount(match["amount"], match.groupdict().get("suffix"))
            extracted_threshold = (
                policy.get("approvals", {})
                .get("thresholds", {})
                .get("transfer_funds")
            )
            if threshold == extracted_threshold:
                _append_unique_constraint(
                    detected_constraints,
                    {
                        "type": "approval_threshold",
                        "operation": "transfer_funds",
                        "value": threshold,
                        "source_text": match.groupdict().get("source", match.group(0)),
                    },
                )

    return {"detected_constraints": detected_constraints}


def _append_unique_constraint(
    detected_constraints: list[dict[str, Any]],
    constraint: dict[str, Any],
) -> None:
    if constraint not in detected_constraints:
        detected_constraints.append(constraint)
