"""Governance activity feed projections."""

from __future__ import annotations

from typing import Any

from governance_ledger.local_registry.projections.lineage import build_authority_lineage_projection

GOVERNANCE_ACTIVITY_PROJECTION_V1 = "governance_activity_projection.v1"


def build_governance_activity_projection(
    *,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the canonical operational activity feed for a registry."""
    lineage = build_authority_lineage_projection(entries=entries)
    activities = _event_activities(entries) + _drift_activities(lineage.get("drift_indicators", []))
    activities.sort(key=lambda item: (item.get("timestamp") or "", item["activity_type"], item["authority_ref"]), reverse=True)
    return {
        "schema_version": GOVERNANCE_ACTIVITY_PROJECTION_V1,
        "activity": activities,
    }


def _event_activities(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    activities = []
    for entry in entries:
        for event in entry.get("lifecycle_events") or entry.get("lifecycle_timeline") or []:
            event_type = event.get("event_type") or event.get("event")
            activities.append(
                {
                    "schema_version": "governance_activity_event.v1",
                    "activity_type": f"authority_{event_type}",
                    "authority_ref": entry["authority_ref"],
                    "authority_version": entry.get("authority_version") or _version_from_ref(entry["authority_ref"]),
                    "timestamp": event.get("timestamp"),
                    "severity": _event_severity(event_type),
                    "summary": _event_summary(event_type, entry),
                    "continuity_impact": _continuity_impact(event_type, entry),
                    "caused_by_event_id": event.get("caused_by_event_id") or event.get("previous_event_id"),
                    "event_id": event.get("event_id"),
                }
            )
    return activities


def _drift_activities(drift_indicators: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": "governance_activity_event.v1",
            "activity_type": item["drift_type"],
            "authority_ref": item["authority_ref"],
            "authority_version": _version_from_ref(item["authority_ref"]),
            "timestamp": None,
            "severity": item["severity"],
            "summary": _drift_summary(item),
            "continuity_impact": "review_required" if item["drift_type"] == "continuity_posture_changed" else "none",
            "caused_by_event_id": None,
            "drift_type": item["drift_type"],
        }
        for item in drift_indicators
    ]


def _event_summary(event_type: str | None, entry: dict[str, Any]) -> str:
    label = {
        "drafted": "drafted",
        "reviewed": "reviewed",
        "exported": "exported",
        "registered": "registered",
        "superseded": "superseded",
        "revoked": "revoked",
    }.get(event_type or "", "updated")
    return f"{entry['authority_ref']} authority {label}."


def _drift_summary(item: dict[str, Any]) -> str:
    if item["drift_type"] == "continuity_posture_changed":
        return f"Continuity posture changed from {item['from']} to {item['to']}."
    if item["drift_type"] == "approval_requirement_changed":
        return f"Approval requirement changed from {item['from']} to {item['to']}."
    if item["drift_type"] == "escalation_threshold_changed":
        return f"Escalation threshold changed from {item['from']} to {item['to']}."
    return f"{item['field']} changed from {item['from']} to {item['to']}."


def _event_severity(event_type: str | None) -> str:
    if event_type == "revoked":
        return "critical"
    if event_type in {"revoked", "superseded"}:
        return "continuity_risk"
    return "info"


def _continuity_impact(event_type: str | None, entry: dict[str, Any]) -> str:
    if event_type in {"revoked", "superseded"} and "revalidation" in str(entry.get("continuity_posture", "")):
        return "continuity_revalidation_required"
    return "none"


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
