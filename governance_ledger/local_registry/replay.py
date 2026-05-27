"""Deterministic governance chronology replay."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

GOVERNANCE_REPLAY_STATE_V1 = "governance_replay_state.v1"
GOVERNANCE_REPLAY_DIFF_V1 = "governance_replay_diff.v1"


def replay_governance_chronology(
    events: list[dict[str, Any]],
    replay_cutoff: str | None = None,
) -> dict[str, Any]:
    """Replay append-only governance chronology into governance_replay_state.v1."""
    included = [
        _normalize_event(event)
        for event in deepcopy(events)
        if replay_cutoff is None or str(event.get("timestamp") or "") <= replay_cutoff
    ]
    included.sort(key=lambda item: (item["timestamp"], item["event_id"]))
    state = _empty_state(replay_cutoff or (included[-1]["timestamp"] if included else None), included)
    authorities: dict[str, dict[str, Any]] = {}
    projection_freshness: dict[tuple[str, str], dict[str, Any]] = {}
    continuity_state: dict[str, dict[str, Any]] = {}
    replay_posture: dict[str, dict[str, Any]] = {}

    for event in included:
        schema = event["schema_version"]
        if schema == "authority_lifecycle_event.v1":
            _apply_lifecycle_event(event, authorities, replay_posture)
        elif schema == "governance_event.v1":
            _apply_governance_event(event, authorities, replay_posture)
        elif schema == "projection_generation_event.v1":
            projection_freshness[_projection_key(event)] = _projection_freshness(event)
        elif schema == "projection_invalidation_event.v1":
            projection_freshness[_projection_key(event)] = _projection_invalidation(event)
        elif schema == "continuity_transition_event.v1":
            continuity_state[event["authority_ref"]] = _continuity_state(event)

    _fill_default_replay_posture(authorities, replay_posture)
    state["active_authorities"] = _active_authorities(authorities)
    state["lineage_state"] = _lineage_state(authorities)
    state["continuity_state"] = _sorted_values(continuity_state)
    state["replay_posture"] = _sorted_values(replay_posture)
    state["projection_freshness"] = sorted(
        projection_freshness.values(),
        key=lambda item: (item["authority_ref"], item["projection_name"]),
    )
    state["governance_health"] = _governance_health(authorities, replay_posture, continuity_state)
    state["operational_summaries"] = _operational_summaries(authorities, replay_posture, continuity_state)
    return state


def diff_governance_replay_states(
    from_state: dict[str, Any],
    to_state: dict[str, Any],
) -> dict[str, Any]:
    """Compare two governance_replay_state.v1 objects."""
    return {
        "schema_version": GOVERNANCE_REPLAY_DIFF_V1,
        "from_cutoff": from_state.get("replay_cutoff"),
        "to_cutoff": to_state.get("replay_cutoff"),
        "active_authority_changes": _diff_lists(
            from_state.get("active_authorities") or [],
            to_state.get("active_authorities") or [],
            _authority_ref,
        ),
        "continuity_changes": _diff_lists(
            from_state.get("continuity_state") or [],
            to_state.get("continuity_state") or [],
            _authority_ref,
        ),
        "replay_posture_changes": _diff_lists(
            from_state.get("replay_posture") or [],
            to_state.get("replay_posture") or [],
            _authority_ref,
        ),
        "projection_freshness_changes": _diff_lists(
            from_state.get("projection_freshness") or [],
            to_state.get("projection_freshness") or [],
            lambda item: f"{item['authority_ref']}::{item['projection_name']}",
        ),
        "governance_health_changes": _diff_single(
            "governance_health",
            from_state.get("governance_health") or {},
            to_state.get("governance_health") or {},
        ),
        "operational_summary_changes": _diff_lists(
            from_state.get("operational_summaries") or [],
            to_state.get("operational_summaries") or [],
            _authority_ref,
        ),
    }


def diff_governance_chronology_replay(
    events: list[dict[str, Any]],
    *,
    from_cutoff: str | None,
    to_cutoff: str | None,
) -> dict[str, Any]:
    """Replay chronology at two cutoffs and compare the resulting governance states."""
    return diff_governance_replay_states(
        replay_governance_chronology(events, replay_cutoff=from_cutoff),
        replay_governance_chronology(events, replay_cutoff=to_cutoff),
    )


def _empty_state(replay_cutoff: str | None, included: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": GOVERNANCE_REPLAY_STATE_V1,
        "replayed_at": replay_cutoff,
        "replay_cutoff": replay_cutoff,
        "source_event_ids": [event["event_id"] for event in included],
        "active_authorities": [],
        "lineage_state": [],
        "continuity_state": [],
        "replay_posture": [],
        "projection_freshness": [],
        "governance_health": {"posture": "healthy", "signals": []},
        "operational_summaries": [],
    }


def _diff_lists(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
    key_fn: Any,
) -> list[dict[str, Any]]:
    previous_by_key = {key_fn(item): item for item in previous}
    current_by_key = {key_fn(item): item for item in current}
    changes = []
    for key in sorted(set(previous_by_key) | set(current_by_key)):
        before = previous_by_key.get(key)
        after = current_by_key.get(key)
        if before == after:
            continue
        changes.append(
            {
                "change_type": "added" if before is None else "removed" if after is None else "changed",
                "ref": key,
                "from": before,
                "to": after,
            }
        )
    return changes


def _diff_single(ref: str, previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    if previous == current:
        return []
    return [{"change_type": "changed", "ref": ref, "from": previous, "to": current}]


def _authority_ref(item: dict[str, Any]) -> str:
    return item["authority_ref"]


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(event)
    schema = normalized.get("schema_version")
    if schema == "authority_lifecycle_event.v1":
        normalized.setdefault("event_category", "lifecycle")
        normalized.setdefault("severity", _lifecycle_severity(normalized.get("event_type")))
        normalized.setdefault("immutability_posture", "append_only")
        normalized.setdefault("caused_by_event_id", normalized.get("previous_event_id"))
    return normalized


def _apply_lifecycle_event(
    event: dict[str, Any],
    authorities: dict[str, dict[str, Any]],
    replay_posture: dict[str, dict[str, Any]],
) -> None:
    authority = _authority(authorities, event)
    event_type = event["event_type"]
    authority["status"] = event_type
    authority["active"] = event_type == "registered"
    if event_type in {"superseded", "revoked"}:
        authority["active"] = False
    if event_type == "superseded":
        authority["superseded_by"] = _superseded_by(event)
    authority["lifecycle_event_ids"].append(event["event_id"])
    receipt_hash = (event.get("artifact_hashes") or {}).get("receipt_hash")
    if receipt_hash:
        replay_posture[event["authority_ref"]] = _replay_posture(event, receipt_hash)


def _apply_governance_event(
    event: dict[str, Any],
    authorities: dict[str, dict[str, Any]],
    replay_posture: dict[str, dict[str, Any]],
) -> None:
    if event.get("event_category") != "lifecycle":
        return
    authority = _authority(authorities, event)
    event_type = event["event_type"]
    authority["status"] = event_type
    authority["active"] = event_type == "registered"
    if event_type in {"authority_superseded", "superseded", "authority_revoked", "revoked"}:
        authority["active"] = False
    authority["lifecycle_event_ids"].append(event["event_id"])
    details = event.get("details") or {}
    if details.get("receipt_hash"):
        replay_posture[event["authority_ref"]] = _replay_posture(event, details["receipt_hash"])


def _authority(authorities: dict[str, dict[str, Any]], event: dict[str, Any]) -> dict[str, Any]:
    authority_ref = event["authority_ref"]
    if authority_ref not in authorities:
        authorities[authority_ref] = {
            "authority_ref": authority_ref,
            "authority_version": event.get("authority_version") or _version_from_ref(authority_ref),
            "authority_family": _authority_family(authority_ref),
            "status": "unknown",
            "active": False,
            "superseded_by": None,
            "lifecycle_event_ids": [],
        }
    return authorities[authority_ref]


def _projection_key(event: dict[str, Any]) -> tuple[str, str]:
    return (event["authority_ref"], event["projection_name"])


def _projection_freshness(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority_ref": event["authority_ref"],
        "authority_version": event.get("authority_version") or _version_from_ref(event["authority_ref"]),
        "projection_name": event["projection_name"],
        "generated_at": event.get("generated_at") or event["timestamp"],
        "source_event_ids": list(event.get("source_event_ids") or []),
        "freshness_posture": event.get("freshness_posture") or "fresh",
    }


def _projection_invalidation(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority_ref": event["authority_ref"],
        "authority_version": event.get("authority_version") or _version_from_ref(event["authority_ref"]),
        "projection_name": event["projection_name"],
        "generated_at": event["timestamp"],
        "source_event_ids": [event["invalidated_by_event_id"]],
        "freshness_posture": "invalidated",
    }


def _continuity_state(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority_ref": event["authority_ref"],
        "authority_version": event.get("authority_version") or _version_from_ref(event["authority_ref"]),
        "continuity_posture": event.get("to"),
        "transition_type": event["transition_type"],
        "source_event_id": event["event_id"],
    }


def _replay_posture(event: dict[str, Any], receipt_hash: str) -> dict[str, Any]:
    return {
        "authority_ref": event["authority_ref"],
        "authority_version": event.get("authority_version") or _version_from_ref(event["authority_ref"]),
        "receipt_present": True,
        "receipt_hash": receipt_hash,
        "posture": "complete",
    }


def _fill_default_replay_posture(
    authorities: dict[str, dict[str, Any]],
    replay_posture: dict[str, dict[str, Any]],
) -> None:
    for authority in authorities.values():
        replay_posture.setdefault(
            authority["authority_ref"],
            {
                "authority_ref": authority["authority_ref"],
                "authority_version": authority["authority_version"],
                "receipt_present": False,
                "receipt_hash": None,
                "posture": "incomplete",
            },
        )


def _active_authorities(authorities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    active = []
    for authority in authorities.values():
        if not authority["active"]:
            continue
        active.append(
            {
                "authority_ref": authority["authority_ref"],
                "authority_version": authority["authority_version"],
                "authority_family": authority["authority_family"],
                "activated_by_event_id": authority["lifecycle_event_ids"][-1],
            }
        )
    return sorted(active, key=lambda item: item["authority_ref"])


def _lineage_state(authorities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "authority_ref": authority["authority_ref"],
                "authority_version": authority["authority_version"],
                "authority_family": authority["authority_family"],
                "status": authority["status"],
                "active": authority["active"],
                "superseded_by": authority["superseded_by"],
                "lifecycle_event_ids": authority["lifecycle_event_ids"],
            }
            for authority in authorities.values()
        ],
        key=lambda item: item["authority_ref"],
    )


def _governance_health(
    authorities: dict[str, dict[str, Any]],
    replay_posture: dict[str, dict[str, Any]],
    continuity_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    signals = []
    active_by_family: dict[str, list[str]] = {}
    for authority in authorities.values():
        if authority["active"]:
            active_by_family.setdefault(authority["authority_family"], []).append(authority["authority_ref"])
    for family, refs in sorted(active_by_family.items()):
        if len(refs) > 1:
            signals.append(
                {
                    "signal_type": "multiple_active_authorities",
                    "severity": "authority_conflict",
                    "authority_family": family,
                    "authority_refs": refs,
                }
            )
    if any(item["posture"] == "incomplete" for item in replay_posture.values()):
        signals.append({"signal_type": "replay_degraded", "severity": "replay_risk"})
    if any(str(item.get("continuity_posture")) == "continuity_risk" for item in continuity_state.values()):
        signals.append({"signal_type": "continuity_risk", "severity": "continuity_risk"})
    posture = "healthy"
    if any(item["severity"] == "authority_conflict" for item in signals):
        posture = "authority_conflict"
    elif any(item["severity"] == "continuity_risk" for item in signals):
        posture = "continuity_risk"
    elif any(item["severity"] == "replay_risk" for item in signals):
        posture = "replay_degraded"
    return {"posture": posture, "signals": signals}


def _operational_summaries(
    authorities: dict[str, dict[str, Any]],
    replay_posture: dict[str, dict[str, Any]],
    continuity_state: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries = []
    for authority in authorities.values():
        replay = replay_posture.get(authority["authority_ref"], {})
        continuity = continuity_state.get(authority["authority_ref"], {})
        summaries.append(
            {
                "authority_ref": authority["authority_ref"],
                "authority_version": authority["authority_version"],
                "status": authority["status"],
                "active": authority["active"],
                "continuity_posture": continuity.get("continuity_posture", "unknown"),
                "replay_posture": replay.get("posture", "incomplete"),
            }
        )
    return sorted(summaries, key=lambda item: item["authority_ref"])


def _sorted_values(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items.values(), key=lambda item: item["authority_ref"])


def _lifecycle_severity(event_type: str | None) -> str:
    if event_type == "revoked":
        return "critical"
    if event_type == "superseded":
        return "continuity_risk"
    return "info"


def _superseded_by(event: dict[str, Any]) -> str | None:
    notes = event.get("notes") or {}
    return notes.get("superseded_by") or event.get("superseded_by")


def _authority_family(authority_ref: str) -> str:
    return authority_ref.split("@", 1)[0]


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
