"""Registry health posture projections."""

from __future__ import annotations

from typing import Any

from governance_ledger.local_registry.projections.lineage import build_authority_lineage_projection

REGISTRY_HEALTH_PROJECTION_V1 = "registry_health_projection.v1"


def build_registry_health_projection(
    *,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build registry, authority, and lineage health posture."""
    lineage = build_authority_lineage_projection(entries=entries)
    authority_health = [_authority_health(entry) for entry in entries]
    lineage_posture = _lineage_posture(lineage)
    registry_states = {item["posture"] for item in authority_health}
    if lineage_posture != "healthy":
        registry_states.add(lineage_posture)
    return {
        "schema_version": REGISTRY_HEALTH_PROJECTION_V1,
        "registry_posture": _aggregate_registry_posture(registry_states),
        "authority_posture": authority_health,
        "lineage_posture": {
            "authority_family": lineage.get("authority_family"),
            "posture": lineage_posture,
            "drift_count": len(lineage.get("drift_indicators", [])),
        },
    }


def _authority_health(entry: dict[str, Any]) -> dict[str, Any]:
    states = []
    if (entry.get("diagnostic_summary") or {}).get("warning_count", 0) > 0:
        states.append("warnings_present")
    if not (entry.get("latest_receipt_hash") or (entry.get("publication_receipt") or {}).get("receipt_hash")):
        states.append("replay_posture_incomplete")
    if entry.get("status") == "superseded":
        states.append("supersession_pending")
    if entry.get("status") == "revoked":
        states.append("continuity_drift_detected")
    return {
        "authority_ref": entry["authority_ref"],
        "authority_version": entry.get("authority_version") or _version_from_ref(entry["authority_ref"]),
        "posture": _priority_posture(states),
        "signals": states,
    }


def _lineage_posture(lineage: dict[str, Any]) -> str:
    if any(item.get("drift_type") == "continuity_posture_changed" for item in lineage.get("drift_indicators", [])):
        return "continuity_drift_detected"
    if lineage.get("drift_indicators"):
        return "warnings_present"
    return "healthy"


def _aggregate_registry_posture(states: set[str]) -> str:
    return _priority_posture(list(states))


def _priority_posture(states: list[str]) -> str:
    for posture in (
        "continuity_drift_detected",
        "replay_posture_incomplete",
        "supersession_pending",
        "review_stale",
        "warnings_present",
    ):
        if posture in states:
            return posture
    return "healthy"


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
