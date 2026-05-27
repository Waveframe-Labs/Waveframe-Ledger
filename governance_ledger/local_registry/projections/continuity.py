"""Governance continuity projections for local registry state."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from governance_ledger.local_registry.projections.registry import build_authority_drift_indicators

GOVERNANCE_CONTINUITY_PROJECTION_V1 = "governance_continuity_projection.v1"


def build_governance_continuity_projection(
    *,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build deterministic governance continuity posture across authority families."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(_authority_family(entry["authority_ref"]), []).append(entry)
    families = []
    for family, family_entries in sorted(grouped.items()):
        ordered = sorted(family_entries, key=_lineage_sort_key)
        observations = _continuity_observations(ordered)
        replay_matrix = [_replay_matrix_row(entry) for entry in ordered]
        fragmentation = _lineage_fragmentation(ordered)
        active_authority = _active_authority(ordered)
        families.append(
            {
                "authority_family": family,
                "continuity_posture": _continuity_posture(observations, fragmentation),
                "active_authority": active_authority["authority_ref"] if active_authority else None,
                "superseded_authorities": sum(1 for entry in ordered if entry.get("status") == "superseded"),
                "continuity_warnings": [
                    item["summary"]
                    for item in observations
                    if item["severity"] in {"warning", "critical", "continuity_risk", "replay_risk", "authority_conflict"}
                ],
                "replay_compatibility": _replay_compatibility(replay_matrix),
                "fragmentation": fragmentation,
                "replay_continuity_matrix": replay_matrix,
                "continuity_observations": observations,
            }
        )
    return {
        "schema_version": GOVERNANCE_CONTINUITY_PROJECTION_V1,
        "authority_families": families,
    }


def _continuity_observations(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    observations.extend(_fragmentation_observations(entries))
    observations.extend(_replay_observations(entries))
    observations.extend(_drift_observations(entries))
    observations.extend(_churn_observations(entries))
    observations.sort(key=lambda item: (item["severity"], item["continuity_observation_type"], item["authority_ref"]))
    return observations


def _fragmentation_observations(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fragmentation = _lineage_fragmentation(entries)
    if not fragmentation["fragmentation_detected"]:
        return []
    return [
        _observation(
            observation_type=fragmentation["fragmentation_type"],
            severity="authority_conflict",
            summary=fragmentation["summary"],
            authority_ref=_authority_family(entries[0]["authority_ref"]) if entries else "unknown",
        )
    ]


def _replay_observations(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations = []
    for entry in entries:
        if not _receipt_hash(entry):
            observations.append(
                _observation(
                    observation_type="replay_continuity_degraded",
                    severity="replay_risk",
                    summary=f"{entry['authority_ref']} has no publication receipt for replay continuity binding.",
                    authority_ref=entry["authority_ref"],
                )
            )
        if entry.get("semantic_hash_alignment") == "mismatch":
            observations.append(
                _observation(
                    observation_type="semantic_hash_incompatibility",
                    severity="replay_risk",
                    summary=f"{entry['authority_ref']} has incompatible semantic hash posture.",
                    authority_ref=entry["authority_ref"],
                )
            )
    return observations


def _drift_observations(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations = []
    for previous, current in zip(entries, entries[1:]):
        for drift in build_authority_drift_indicators(previous, current):
            if drift["drift_type"] == "continuity_posture_changed":
                observations.append(
                    _observation(
                        observation_type="continuity_posture_changed",
                        severity="continuity_risk",
                        summary=f"Continuity posture changed between {previous['authority_ref']} and {current['authority_ref']}.",
                        authority_ref=current["authority_ref"],
                    )
                )
            elif drift["drift_type"] in {"approval_requirement_changed", "escalation_threshold_changed"}:
                observations.append(
                    _observation(
                        observation_type=drift["drift_type"],
                        severity="warning",
                        summary=f"{drift['field']} changed between {previous['authority_ref']} and {current['authority_ref']}.",
                        authority_ref=current["authority_ref"],
                    )
                )
    return observations


def _churn_observations(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations = []
    supersession_events = [
        event
        for entry in entries
        for event in entry.get("lifecycle_events") or entry.get("lifecycle_timeline") or []
        if (event.get("event_type") or event.get("event")) == "superseded"
    ]
    if _events_within_window(supersession_events, threshold=5, window=timedelta(hours=48)):
        observations.append(
            _observation(
                observation_type="governance_churn",
                severity="warning",
                summary="Authority lineage recorded 5 or more supersessions within 48 hours.",
                authority_ref=_authority_family(entries[0]["authority_ref"]),
            )
        )
    approval_changes = 0
    threshold_changes = 0
    for previous, current in zip(entries, entries[1:]):
        drift_types = {item["drift_type"] for item in build_authority_drift_indicators(previous, current)}
        if "approval_requirement_changed" in drift_types:
            approval_changes += 1
        if "escalation_threshold_changed" in drift_types:
            threshold_changes += 1
    if approval_changes >= 3:
        observations.append(
            _observation(
                observation_type="governance_churn",
                severity="warning",
                summary=f"Approval requirements changed {approval_changes} times across this authority lineage.",
                authority_ref=_authority_family(entries[0]["authority_ref"]),
            )
        )
    if threshold_changes >= 3:
        observations.append(
            _observation(
                observation_type="governance_churn",
                severity="warning",
                summary=f"Escalation thresholds changed {threshold_changes} times across this authority lineage.",
                authority_ref=_authority_family(entries[0]["authority_ref"]),
            )
        )
    return observations


def _lineage_fragmentation(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        return _fragmentation(False, "none", "No authority lineage is present.")
    refs = {entry["authority_ref"] for entry in entries}
    active = [entry for entry in entries if entry.get("status") == "registered" and not entry.get("superseded_by")]
    if len(active) > 1:
        return _fragmentation(True, "multiple_active_authorities", "Multiple registered authorities are active in one lineage.")
    latest = entries[-1]
    if latest.get("status") == "revoked":
        return _fragmentation(True, "revoked_active_authority", "The latest authority posture is revoked with no active successor.")
    for entry in entries:
        if entry.get("supersedes") and entry["supersedes"] not in refs:
            return _fragmentation(True, "orphaned_version", f"{entry['authority_ref']} supersedes an authority not present in local lineage.")
        if entry.get("superseded_by") and entry["superseded_by"] not in refs:
            return _fragmentation(True, "broken_supersession_chain", f"{entry['authority_ref']} points to a missing superseding authority.")
        if not _has_continuity_semantics(entry):
            return _fragmentation(True, "missing_continuity_semantics", f"{entry['authority_ref']} has no explicit continuity semantics.")
    return _fragmentation(False, "none", "Lineage continuity is coherent.")


def _replay_matrix_row(entry: dict[str, Any]) -> dict[str, Any]:
    receipt_hash = _receipt_hash(entry)
    requires_revalidation = "revalidation" in str(entry.get("continuity_posture", "")).lower()
    return {
        "authority_ref": entry["authority_ref"],
        "authority_version": entry.get("authority_version") or _version_from_ref(entry["authority_ref"]),
        "replay_compatible": bool(receipt_hash),
        "requires_revalidation": requires_revalidation,
        "continuity_preserved": bool(receipt_hash) and _has_continuity_semantics(entry),
        "receipt_hash": receipt_hash,
        "replay_readiness": entry.get("replay_readiness"),
    }


def _active_authority(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    active = [entry for entry in entries if entry.get("status") == "registered" and not entry.get("superseded_by")]
    if active:
        return sorted(active, key=_lineage_sort_key)[-1]
    available = [entry for entry in entries if entry.get("status") not in {"revoked", "superseded"}]
    if available:
        return sorted(available, key=_lineage_sort_key)[-1]
    return None


def _continuity_posture(observations: list[dict[str, Any]], fragmentation: dict[str, Any]) -> str:
    severities = {item["severity"] for item in observations}
    if fragmentation["fragmentation_detected"]:
        return "fragmented"
    if "authority_conflict" in severities:
        return "ambiguous"
    if "continuity_risk" in severities:
        return "continuity_at_risk"
    if "replay_risk" in severities:
        return "replay_degraded"
    if "warning" in severities:
        return "unstable"
    return "stable"


def _replay_compatibility(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "unknown"
    compatible = [row["replay_compatible"] for row in rows]
    if all(compatible):
        return "complete"
    if any(compatible):
        return "degraded"
    return "incomplete"


def _fragmentation(detected: bool, fragmentation_type: str, summary: str) -> dict[str, Any]:
    return {
        "fragmentation_detected": detected,
        "fragmentation_type": fragmentation_type,
        "summary": summary,
    }


def _observation(
    *,
    observation_type: str,
    severity: str,
    summary: str,
    authority_ref: str,
) -> dict[str, Any]:
    return {
        "schema_version": "governance_continuity_observation.v1",
        "continuity_observation_type": observation_type,
        "severity": severity,
        "summary": summary,
        "authority_ref": authority_ref,
    }


def _events_within_window(events: list[dict[str, Any]], *, threshold: int, window: timedelta) -> bool:
    timestamps = sorted(_parse_timestamp(event.get("timestamp")) for event in events)
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    if len(timestamps) < threshold:
        return False
    for index, timestamp in enumerate(timestamps):
        if index + threshold > len(timestamps):
            break
        if timestamps[index + threshold - 1] - timestamp <= window:
            return True
    return False


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _receipt_hash(entry: dict[str, Any]) -> str | None:
    return entry.get("latest_receipt_hash") or (entry.get("publication_receipt") or {}).get("receipt_hash")


def _has_continuity_semantics(entry: dict[str, Any]) -> bool:
    value = str(entry.get("continuity_posture") or "").strip().lower()
    return bool(value and value not in {"unknown", "none", "not specified", "missing"})


def _lineage_sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    authority_ref = entry["authority_ref"]
    return (_authority_family(authority_ref), entry.get("authority_version") or _version_from_ref(authority_ref))


def _authority_family(authority_ref: str) -> str:
    return authority_ref.split("@", 1)[0]


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
