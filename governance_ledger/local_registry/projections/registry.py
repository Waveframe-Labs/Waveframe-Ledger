"""Registry projections and drift detection."""

from __future__ import annotations

from typing import Any


DRIFT_FIELDS = {
    "status": "lifecycle_posture_changed",
    "continuity_posture": "continuity_posture_changed",
    "escalation_threshold": "escalation_threshold_changed",
    "approval_requirement": "approval_requirement_changed",
}

GOVERNANCE_DRIFT_SEVERITIES = {
    "info",
    "warning",
    "critical",
    "continuity_risk",
    "replay_risk",
    "authority_conflict",
}


def build_authority_drift_indicators(
    previous_entry: dict[str, Any] | None,
    current_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare registry entries and return deterministic governance drift indicators."""
    if previous_entry is None:
        return []
    indicators: list[dict[str, Any]] = []
    for field, drift_type in DRIFT_FIELDS.items():
        previous = _field_value(previous_entry, field)
        current = _field_value(current_entry, field)
        if previous != current:
            indicators.append(
                {
                    "schema_version": "authority_drift_indicator.v1",
                    "authority_ref": current_entry["authority_ref"],
                    "previous_authority_ref": previous_entry["authority_ref"],
                    "drift_type": drift_type,
                    "severity": _drift_severity(drift_type),
                    "field": field,
                    "from": previous,
                    "to": current,
                }
            )
    return indicators


def _field_value(entry: dict[str, Any], field: str) -> Any:
    if field == "approval_requirement":
        return (
            entry.get("approval_requirement")
            or entry.get("approval_count")
            or (entry.get("authority_contract") or {}).get("authority_requirements", {}).get("approval_count")
            or (entry.get("artifacts") or {})
            .get("authority_contract", {})
            .get("authority_requirements", {})
            .get("approval_count")
        )
    return entry.get(field)


def _drift_severity(drift_type: str) -> str:
    if drift_type == "continuity_posture_changed":
        return "continuity_risk"
    if drift_type == "lifecycle_posture_changed":
        return "authority_conflict"
    if drift_type in {"approval_requirement_changed", "escalation_threshold_changed"}:
        return "warning"
    return "info"
