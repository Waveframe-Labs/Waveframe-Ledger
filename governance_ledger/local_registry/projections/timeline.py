"""Timeline projections for local registry state."""

from __future__ import annotations

from typing import Any

from governance_ledger.local_registry.projections.registry import build_authority_drift_indicators

GOVERNANCE_TIMELINE_PROJECTION_V1 = "governance_timeline_projection.v1"


def build_timeline_projection(
    *,
    authority_ref: str,
    lifecycle_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an ordered lifecycle timeline projection for an authority."""
    return {
        "schema_version": "authority_timeline_projection.v1",
        "authority_ref": authority_ref,
        "events": sorted(
            [
                {
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type") or event.get("event"),
                    "timestamp": event.get("timestamp"),
                    "artifact_hashes": event.get("artifact_hashes") or {"bundle_hash": event.get("hash")},
                    "detail": (event.get("notes") or {}).get("detail") or event.get("detail") or "",
                    "previous_event_id": event.get("previous_event_id"),
                }
                for event in lifecycle_events
            ],
            key=lambda item: item.get("timestamp") or "",
        ),
    }


def build_governance_timeline_projection(
    *,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the canonical governance chronology across registry state."""
    ordered = sorted(entries, key=_lineage_sort_key)
    timeline_events = (
        _lifecycle_timeline_events(ordered)
        + _drift_timeline_events(ordered)
        + _replay_timeline_events(ordered)
        + _diagnostic_timeline_events(ordered)
    )
    timeline_events.sort(
        key=lambda item: (
            item.get("timestamp") or "",
            item["timeline_event_type"],
            item["authority_instance_ref"],
        )
    )
    return {
        "schema_version": GOVERNANCE_TIMELINE_PROJECTION_V1,
        "events": timeline_events,
    }


def _lifecycle_timeline_events(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline_events: list[dict[str, Any]] = []
    for entry in entries:
        for event in entry.get("lifecycle_events") or entry.get("lifecycle_timeline") or []:
            event_type = event.get("event_type") or event.get("event")
            timeline_events.append(
                _timeline_event(
                    timeline_event_type=f"authority_{event_type}",
                    entry=entry,
                    timestamp=event.get("timestamp"),
                    severity=_lifecycle_severity(event_type),
                    summary=_lifecycle_summary(event_type, entry),
                    continuity_impact=_continuity_impact(event_type, entry),
                    caused_by_event_id=event.get("caused_by_event_id") or event.get("previous_event_id"),
                    event_id=event.get("event_id"),
                    superseded_by=entry.get("superseded_by") if event_type == "superseded" else None,
                    activation_state=_activation_state(event_type),
                )
            )
    return timeline_events


def _drift_timeline_events(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline_events: list[dict[str, Any]] = []
    for previous, current in zip(entries, entries[1:]):
        for drift in build_authority_drift_indicators(previous, current):
            timeline_events.append(
                _timeline_event(
                    timeline_event_type=drift["drift_type"],
                    entry=current,
                    timestamp=current.get("updated_at"),
                    severity=drift["severity"],
                    summary=_drift_summary(drift),
                    continuity_impact=_drift_continuity_impact(drift),
                    caused_by_event_id=None,
                    drift_type=drift["drift_type"],
                    drift=drift,
                )
            )
    return timeline_events


def _replay_timeline_events(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline_events: list[dict[str, Any]] = []
    for entry in entries:
        receipt_hash = entry.get("latest_receipt_hash") or (entry.get("publication_receipt") or {}).get("receipt_hash")
        if receipt_hash:
            timeline_events.append(
                _timeline_event(
                    timeline_event_type="replay_posture_aligned",
                    entry=entry,
                    timestamp=entry.get("updated_at"),
                    severity="info",
                    summary=f"Replay evidence can bind to {entry['authority_ref']} receipt posture.",
                    continuity_impact="none",
                    caused_by_event_id=None,
                )
            )
        else:
            timeline_events.append(
                _timeline_event(
                    timeline_event_type="replay_posture_incomplete",
                    entry=entry,
                    timestamp=entry.get("updated_at"),
                    severity="replay_risk",
                    summary=f"Replay posture is incomplete for {entry['authority_ref']} because no publication receipt is present.",
                    continuity_impact="none",
                    caused_by_event_id=None,
                )
            )
    return timeline_events


def _diagnostic_timeline_events(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline_events: list[dict[str, Any]] = []
    for entry in entries:
        rollup = entry.get("diagnostic_summary") or {}
        if not rollup.get("finding_count"):
            continue
        timeline_events.append(
            _timeline_event(
                timeline_event_type="diagnostic_rollup_recorded",
                entry=entry,
                timestamp=entry.get("updated_at"),
                severity=_diagnostic_severity(rollup),
                summary=(
                    f"{entry['authority_ref']} has {rollup.get('finding_count', 0)} diagnostic "
                    "finding(s) in the current governance posture."
                ),
                continuity_impact="review_required" if rollup.get("warning_count") else "none",
                caused_by_event_id=None,
                diagnostic_rollup=rollup,
            )
        )
    return timeline_events


def _timeline_event(
    *,
    timeline_event_type: str,
    entry: dict[str, Any],
    timestamp: str | None,
    severity: str,
    summary: str,
    continuity_impact: str,
    caused_by_event_id: str | None,
    event_id: str | None = None,
    superseded_by: str | None = None,
    activation_state: str | None = None,
    drift_type: str | None = None,
    drift: dict[str, Any] | None = None,
    diagnostic_rollup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    authority_ref = entry["authority_ref"]
    event = {
        "schema_version": "governance_timeline_event.v1",
        "timeline_event_type": timeline_event_type,
        "authority_ref": _authority_family(authority_ref),
        "authority_instance_ref": authority_ref,
        "authority_version": entry.get("authority_version") or _version_from_ref(authority_ref),
        "timestamp": timestamp,
        "severity": severity,
        "summary": summary,
        "continuity_impact": continuity_impact,
        "caused_by_event_id": caused_by_event_id,
        "event_id": event_id,
        "superseded_by": superseded_by,
        "activation_state": activation_state,
        "drift_type": drift_type,
        "drift": drift,
        "diagnostic_rollup": diagnostic_rollup,
    }
    required_keys = {
        "schema_version",
        "timeline_event_type",
        "authority_ref",
        "authority_instance_ref",
        "authority_version",
        "timestamp",
        "severity",
        "summary",
        "continuity_impact",
        "caused_by_event_id",
    }
    return {key: value for key, value in event.items() if key in required_keys or value is not None}


def _lifecycle_summary(event_type: str | None, entry: dict[str, Any]) -> str:
    if event_type == "registered":
        return f"{entry['authority_ref']} registered as a local authority lifecycle event."
    if event_type == "exported":
        return f"{entry['authority_ref']} exported as an authority bundle."
    if event_type == "superseded":
        return f"{entry['authority_ref']} superseded by {entry.get('superseded_by') or 'a later authority'}."
    if event_type == "revoked":
        return f"{entry['authority_ref']} revoked and removed from active authority posture."
    label = {
        "drafted": "drafted",
        "reviewed": "reviewed",
    }.get(event_type or "", "updated")
    return f"{entry['authority_ref']} authority {label}."


def _drift_summary(drift: dict[str, Any]) -> str:
    if drift["drift_type"] == "continuity_posture_changed":
        return f"Continuity posture changed from {drift['from']} to {drift['to']}."
    if drift["drift_type"] == "approval_requirement_changed":
        return f"Approval requirements changed from {drift['from']} to {drift['to']}."
    if drift["drift_type"] == "escalation_threshold_changed":
        return f"Escalation threshold changed from {drift['from']} to {drift['to']}."
    if drift["drift_type"] == "lifecycle_posture_changed":
        return f"Lifecycle posture changed from {drift['from']} to {drift['to']}."
    return f"{drift['field']} changed from {drift['from']} to {drift['to']}."


def _lifecycle_severity(event_type: str | None) -> str:
    if event_type == "revoked":
        return "critical"
    if event_type == "superseded":
        return "continuity_risk"
    return "info"


def _diagnostic_severity(rollup: dict[str, Any]) -> str:
    highest = rollup.get("highest_severity")
    if highest == "error":
        return "critical"
    if highest == "warning" or rollup.get("warning_count"):
        return "warning"
    return "info"


def _continuity_impact(event_type: str | None, entry: dict[str, Any]) -> str:
    if event_type in {"revoked", "superseded"}:
        if "revalidation" in str(entry.get("continuity_posture", "")).lower():
            return "revalidation_required"
        return "review_required"
    return "none"


def _drift_continuity_impact(drift: dict[str, Any]) -> str:
    if drift["drift_type"] == "continuity_posture_changed":
        return "revalidation_required"
    return "none"


def _activation_state(event_type: str | None) -> str | None:
    if event_type == "registered":
        return "activated"
    if event_type in {"superseded", "revoked"}:
        return "deactivated"
    return None


def _lineage_sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    authority_ref = entry["authority_ref"]
    return (_authority_family(authority_ref), entry.get("authority_version") or _version_from_ref(authority_ref))


def _authority_family(authority_ref: str) -> str:
    return authority_ref.split("@", 1)[0]


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
