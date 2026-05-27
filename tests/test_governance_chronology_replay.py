from __future__ import annotations

from copy import deepcopy

from governance_ledger.local_registry import replay_governance_chronology


def test_same_events_and_cutoff_produce_same_governance_replay_state():
    events = [
        _lifecycle("event-1", "transfer-policy@1.0.0", "drafted", "2026-05-27T00:00:00Z"),
        _lifecycle("event-2", "transfer-policy@1.0.0", "registered", "2026-05-27T00:01:00Z"),
    ]

    first = replay_governance_chronology(events, replay_cutoff="2026-05-27T00:01:00Z")
    second = replay_governance_chronology(events, replay_cutoff="2026-05-27T00:01:00Z")

    assert first == second
    assert first["schema_version"] == "governance_replay_state.v1"


def test_governance_chronology_replay_cutoff_excludes_later_events():
    events = [
        _lifecycle("event-1", "transfer-policy@1.0.0", "registered", "2026-05-27T00:01:00Z"),
        _lifecycle("event-2", "transfer-policy@1.0.0", "revoked", "2026-05-27T00:02:00Z"),
    ]

    state = replay_governance_chronology(events, replay_cutoff="2026-05-27T00:01:00Z")

    assert state["source_event_ids"] == ["event-1"]
    assert state["active_authorities"][0]["authority_ref"] == "transfer-policy@1.0.0"
    assert state["lineage_state"][0]["status"] == "registered"


def test_registered_authority_becomes_active():
    state = replay_governance_chronology(
        [_lifecycle("event-1", "transfer-policy@1.0.0", "registered", "2026-05-27T00:01:00Z")]
    )

    assert state["active_authorities"] == [
        {
            "authority_ref": "transfer-policy@1.0.0",
            "authority_version": "1.0.0",
            "authority_family": "transfer-policy",
            "activated_by_event_id": "event-1",
        }
    ]


def test_superseded_authority_is_no_longer_active():
    events = [
        _lifecycle("event-1", "transfer-policy@1.0.0", "registered", "2026-05-27T00:01:00Z"),
        _lifecycle("event-2", "transfer-policy@1.0.0", "superseded", "2026-05-27T00:02:00Z"),
    ]

    state = replay_governance_chronology(events)

    assert state["active_authorities"] == []
    assert state["lineage_state"][0]["active"] is False
    assert state["lineage_state"][0]["status"] == "superseded"


def test_revoked_authority_is_no_longer_active():
    events = [
        _lifecycle("event-1", "transfer-policy@1.0.0", "registered", "2026-05-27T00:01:00Z"),
        _lifecycle("event-2", "transfer-policy@1.0.0", "revoked", "2026-05-27T00:02:00Z"),
    ]

    state = replay_governance_chronology(events)

    assert state["active_authorities"] == []
    assert state["lineage_state"][0]["active"] is False
    assert state["lineage_state"][0]["status"] == "revoked"


def test_projection_generation_sets_freshness_fresh():
    state = replay_governance_chronology(
        [
            _projection_generated(
                "event-1",
                "transfer-policy@1.0.0",
                "governance_continuity_projection.v1",
                "2026-05-27T00:01:00Z",
            )
        ]
    )

    assert state["projection_freshness"] == [
        {
            "authority_ref": "transfer-policy@1.0.0",
            "authority_version": "1.0.0",
            "projection_name": "governance_continuity_projection.v1",
            "generated_at": "2026-05-27T00:01:00Z",
            "source_event_ids": ["source-1"],
            "freshness_posture": "fresh",
        }
    ]


def test_projection_invalidation_sets_freshness_invalidated():
    events = [
        _projection_generated(
            "event-1",
            "transfer-policy@1.0.0",
            "authority_operational_summary.v1",
            "2026-05-27T00:01:00Z",
        ),
        _projection_invalidated(
            "event-2",
            "transfer-policy@1.0.0",
            "authority_operational_summary.v1",
            "event-1",
            "2026-05-27T00:02:00Z",
        ),
    ]

    state = replay_governance_chronology(events)

    assert state["projection_freshness"][0]["freshness_posture"] == "invalidated"
    assert state["projection_freshness"][0]["source_event_ids"] == ["event-1"]


def test_continuity_transition_updates_continuity_posture():
    state = replay_governance_chronology(
        [
            _continuity_transition(
                "event-1",
                "transfer-policy@1.0.0",
                "stable",
                "continuity_risk",
                "2026-05-27T00:01:00Z",
            )
        ]
    )

    assert state["continuity_state"] == [
        {
            "authority_ref": "transfer-policy@1.0.0",
            "authority_version": "1.0.0",
            "continuity_posture": "continuity_risk",
            "transition_type": "continuity_posture_changed",
            "source_event_id": "event-1",
        }
    ]
    assert state["governance_health"]["posture"] == "continuity_risk"


def test_multiple_active_authorities_emit_authority_conflict():
    events = [
        _lifecycle("event-1", "transfer-policy@1.0.0", "registered", "2026-05-27T00:01:00Z"),
        _lifecycle("event-2", "transfer-policy@1.1.0", "registered", "2026-05-27T00:02:00Z"),
    ]

    state = replay_governance_chronology(events)

    assert len(state["active_authorities"]) == 2
    assert state["governance_health"]["posture"] == "authority_conflict"
    assert state["governance_health"]["signals"][0]["signal_type"] == "multiple_active_authorities"


def test_governance_chronology_replay_does_not_mutate_input_events():
    events = [
        _lifecycle(
            "event-1",
            "transfer-policy@1.0.0",
            "registered",
            "2026-05-27T00:01:00Z",
            artifact_hashes={"receipt_hash": "sha256:receipt"},
        )
    ]
    before = deepcopy(events)

    replay_governance_chronology(events)

    assert events == before


def _lifecycle(
    event_id: str,
    authority_ref: str,
    event_type: str,
    timestamp: str,
    artifact_hashes: dict | None = None,
) -> dict:
    return {
        "schema_version": "authority_lifecycle_event.v1",
        "event_id": event_id,
        "authority_ref": authority_ref,
        "authority_version": authority_ref.rsplit("@", 1)[1],
        "event_type": event_type,
        "timestamp": timestamp,
        "actor": "local-ledger-ui",
        "source": "governance-ledger",
        "artifact_hashes": artifact_hashes or {},
        "notes": {},
        "previous_event_id": None,
        "caused_by_event_id": None,
    }


def _projection_generated(event_id: str, authority_ref: str, projection_name: str, timestamp: str) -> dict:
    return {
        "schema_version": "projection_generation_event.v1",
        "event_id": event_id,
        "event_type": "projection_generated",
        "timestamp": timestamp,
        "authority_ref": authority_ref,
        "authority_version": authority_ref.rsplit("@", 1)[1],
        "severity": "info",
        "caused_by_event_id": None,
        "event_category": "projection",
        "immutability_posture": "append_only",
        "projection_name": projection_name,
        "generated_at": timestamp,
        "source_event_ids": ["source-1"],
        "freshness_posture": "fresh",
        "projection_version": "v1",
        "projection_dependencies": ["authority_lifecycle_event.v1"],
    }


def _projection_invalidated(
    event_id: str,
    authority_ref: str,
    projection_name: str,
    invalidated_by_event_id: str,
    timestamp: str,
) -> dict:
    return {
        "schema_version": "projection_invalidation_event.v1",
        "event_id": event_id,
        "event_type": "projection_invalidated",
        "timestamp": timestamp,
        "authority_ref": authority_ref,
        "authority_version": authority_ref.rsplit("@", 1)[1],
        "severity": "warning",
        "caused_by_event_id": invalidated_by_event_id,
        "event_category": "projection",
        "immutability_posture": "append_only",
        "projection_name": projection_name,
        "invalidated_by_event_id": invalidated_by_event_id,
        "reason": "draft_modified",
    }


def _continuity_transition(
    event_id: str,
    authority_ref: str,
    from_posture: str,
    to_posture: str,
    timestamp: str,
) -> dict:
    return {
        "schema_version": "continuity_transition_event.v1",
        "event_id": event_id,
        "event_type": "continuity_transition",
        "timestamp": timestamp,
        "authority_ref": authority_ref,
        "authority_version": authority_ref.rsplit("@", 1)[1],
        "severity": "continuity_risk",
        "caused_by_event_id": None,
        "event_category": "continuity",
        "immutability_posture": "append_only",
        "transition_type": "continuity_posture_changed",
        "from": from_posture,
        "to": to_posture,
    }
