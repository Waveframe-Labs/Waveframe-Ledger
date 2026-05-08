"""Deterministic extraction from policy prose into structured constraints."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from governance_authoring.patterns import (
    ROLE_PATTERNS,
    SEPARATION_PATTERNS,
    THRESHOLD_PATTERNS,
)

DEFAULT_CONTRACT_ID = "finance-policy"
DEFAULT_CONTRACT_VERSION = "0.1.0"


def extract_constraints(text: str) -> dict[str, Any]:
    """Extract v0.1 governance constraints from policy text."""
    policy: dict[str, Any] = {
        "contract_id": DEFAULT_CONTRACT_ID,
        "contract_version": DEFAULT_CONTRACT_VERSION,
        "authority": {"required_roles": []},
        "approvals": {"thresholds": {}},
        "invariants": {},
    }

    normalized_text = _normalize_text(text)

    for pattern in ROLE_PATTERNS:
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            _append_unique(policy["authority"]["required_roles"], _normalize_role(match["role"]))

    if any(re.search(pattern, normalized_text, flags=re.IGNORECASE) for pattern in SEPARATION_PATTERNS):
        policy["invariants"]["separation_of_duties"] = True

    for pattern in THRESHOLD_PATTERNS:
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            # TODO: v0.2 should support operation-specific threshold extraction
            # instead of hardcoded "transfer_funds".
            policy["approvals"]["thresholds"]["transfer_funds"] = _parse_amount(
                match["amount"],
                match.groupdict().get("suffix"),
            )

    return _without_empty_sections(policy)


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def _normalize_role(role: str) -> str:
    return role.strip().lower().replace("-", "_")


def _parse_amount(amount: str, suffix: str | None = None) -> int:
    value = float(amount.replace(",", ""))
    if suffix and suffix.lower() in {"m", "million"}:
        value *= 1_000_000
    return int(value)


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _without_empty_sections(policy: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(policy)

    if not cleaned["authority"]["required_roles"]:
        cleaned.pop("authority")
    if not cleaned["approvals"]["thresholds"]:
        cleaned.pop("approvals")
    if not cleaned["invariants"]:
        cleaned.pop("invariants")

    return cleaned
