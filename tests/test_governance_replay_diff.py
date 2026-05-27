from __future__ import annotations

import json
from pathlib import Path

from governance_ledger.local_registry import (
    diff_governance_chronology_replay,
    diff_governance_replay_states,
    replay_governance_chronology,
)
from tests.test_governance_chronology_replay import (
    _continuity_transition,
    _lifecycle,
    _projection_generated,
    _projection_invalidated,
)

ROOT = Path(__file__).resolve().parents[1]


def test_governance_replay_diff_compares_cutoff_states():
    events = [
        _lifecycle(
            "event-1",
            "transfer-policy@3.4.5",
            "registered",
            "2026-05-27T00:01:00Z",
            artifact_hashes={"receipt_hash": "sha256:old"},
        ),
        _continuity_transition(
            "event-2",
            "transfer-policy@3.4.5",
            "stable",
            "continuity_risk",
            "2026-05-27T00:02:00Z",
        ),
        _projection_generated(
            "event-3",
            "transfer-policy@3.4.5",
            "governance_continuity_projection.v1",
            "2026-05-27T00:03:00Z",
        ),
        _projection_invalidated(
            "event-4",
            "transfer-policy@3.4.5",
            "governance_continuity_projection.v1",
            "event-3",
            "2026-05-27T00:04:00Z",
        ),
    ]

    diff = diff_governance_chronology_replay(
        events,
        from_cutoff="2026-05-27T00:01:00Z",
        to_cutoff="2026-05-27T00:04:00Z",
    )

    assert diff["schema_version"] == "governance_replay_diff.v1"
    assert diff["from_cutoff"] == "2026-05-27T00:01:00Z"
    assert diff["to_cutoff"] == "2026-05-27T00:04:00Z"
    assert diff["continuity_changes"][0]["ref"] == "transfer-policy@3.4.5"
    assert diff["projection_freshness_changes"][0]["to"]["freshness_posture"] == "invalidated"
    assert diff["governance_health_changes"][0]["to"]["posture"] == "continuity_risk"
    assert diff["operational_summary_changes"][0]["to"]["continuity_posture"] == "continuity_risk"


def test_governance_replay_diff_detects_active_authority_removal_after_supersession():
    events = [
        _lifecycle("event-1", "transfer-policy@3.4.5", "registered", "2026-05-27T00:01:00Z"),
        _lifecycle("event-2", "transfer-policy@3.4.5", "superseded", "2026-05-27T00:02:00Z"),
    ]

    diff = diff_governance_chronology_replay(
        events,
        from_cutoff="2026-05-27T00:01:00Z",
        to_cutoff="2026-05-27T00:02:00Z",
    )

    assert diff["active_authority_changes"] == [
        {
            "change_type": "removed",
            "ref": "transfer-policy@3.4.5",
            "from": {
                "authority_ref": "transfer-policy@3.4.5",
                "authority_version": "3.4.5",
                "authority_family": "transfer-policy",
                "activated_by_event_id": "event-1",
            },
            "to": None,
        }
    ]


def test_governance_replay_diff_detects_replay_posture_change():
    events = [
        _lifecycle("event-1", "transfer-policy@3.4.5", "registered", "2026-05-27T00:01:00Z"),
        _lifecycle(
            "event-2",
            "transfer-policy@3.4.5",
            "registered",
            "2026-05-27T00:02:00Z",
            artifact_hashes={"receipt_hash": "sha256:receipt"},
        ),
    ]

    diff = diff_governance_chronology_replay(
        events,
        from_cutoff="2026-05-27T00:01:00Z",
        to_cutoff="2026-05-27T00:02:00Z",
    )

    assert diff["replay_posture_changes"][0]["from"]["posture"] == "incomplete"
    assert diff["replay_posture_changes"][0]["to"]["posture"] == "complete"


def test_diff_governance_replay_states_is_deterministic():
    events = [
        _lifecycle("event-2", "transfer-policy@3.4.5", "registered", "2026-05-27T00:01:00Z"),
        _lifecycle("event-1", "transfer-policy@3.4.4", "registered", "2026-05-27T00:00:00Z"),
    ]
    first = replay_governance_chronology(events, replay_cutoff="2026-05-27T00:00:00Z")
    second = replay_governance_chronology(events, replay_cutoff="2026-05-27T00:01:00Z")

    assert diff_governance_replay_states(first, second) == diff_governance_replay_states(first, second)


def test_event_ordering_semantics_doc_and_schema_are_present():
    doc = (ROOT / "EVENT_ORDERING_SEMANTICS.md").read_text(encoding="utf-8")
    schema = json.loads((ROOT / "schemas" / "governance_replay_diff.v1.json").read_text(encoding="utf-8"))

    assert "sort_key = (timestamp, event_id)" in doc
    assert "governance_chronology_checkpoint.v1" in doc
    assert schema["properties"]["schema_version"]["const"] == "governance_replay_diff.v1"
    for field in (
        "active_authority_changes",
        "continuity_changes",
        "replay_posture_changes",
        "projection_freshness_changes",
        "governance_health_changes",
        "operational_summary_changes",
    ):
        assert field in schema["required"]
