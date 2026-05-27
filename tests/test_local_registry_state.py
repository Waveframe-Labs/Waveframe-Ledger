from __future__ import annotations

from governance_ledger.local_registry import (
    MemoryRegistryAdapter,
    build_authority_lifecycle_event,
    build_authority_registry_entry,
    build_authority_workspace_projection,
    build_diagnostic_rollup,
)
from governance_ledger.local_registry.models import append_lifecycle_event


def test_lifecycle_event_append_preserves_old_events():
    drafted = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="drafted",
        timestamp="2026-05-26T18:00:00Z",
        artifact_hashes={"bundle_hash": "sha256:draft"},
    )
    reviewed = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="reviewed",
        timestamp="2026-05-26T18:05:00Z",
        previous_event_id=drafted["event_id"],
        artifact_hashes={"bundle_hash": "sha256:review"},
    )

    events = append_lifecycle_event([drafted], reviewed)

    assert events[0] == drafted
    assert events[1] == reviewed
    assert events[1]["previous_event_id"] == drafted["event_id"]


def test_registry_entry_references_lifecycle_event_ids():
    events = [
        build_authority_lifecycle_event(
            authority_ref="transfer-policy@3.5.6",
            event_type="drafted",
            timestamp="2026-05-26T18:00:00Z",
        ),
        build_authority_lifecycle_event(
            authority_ref="transfer-policy@3.5.6",
            event_type="reviewed",
            timestamp="2026-05-26T18:05:00Z",
        ),
    ]
    rollup = build_diagnostic_rollup(
        authority_ref="transfer-policy@3.5.6",
        diagnostics=[_diagnostic("GQ004", "approval", "info")],
    )

    entry = build_authority_registry_entry(
        authority_ref="transfer-policy@3.5.6",
        status="reviewed",
        protected_resource="Corporate Treasury Transfer System",
        governed_action="transfer funds",
        continuity_posture="resume revalidation",
        replay_readiness="receipt pending",
        diagnostic_summary=rollup,
        lifecycle_events=events,
        created_at="2026-05-26T18:00:00Z",
        updated_at="2026-05-26T18:05:00Z",
    )

    assert entry["schema_version"] == "authority_registry_entry.v1"
    assert entry["lifecycle_event_ids"] == [event["event_id"] for event in events]
    assert entry["diagnostic_summary"] == rollup


def test_exported_event_does_not_equal_registered_event():
    exported = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="exported",
        timestamp="2026-05-26T18:10:00Z",
        artifact_hashes={"bundle_hash": "sha256:bundle", "receipt_hash": "sha256:receipt"},
    )
    registered = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="registered",
        timestamp="2026-05-26T18:11:00Z",
        previous_event_id=exported["event_id"],
        artifact_hashes={"bundle_hash": "sha256:bundle", "receipt_hash": "sha256:receipt"},
    )

    assert exported["event_type"] == "exported"
    assert registered["event_type"] == "registered"
    assert exported["event_id"] != registered["event_id"]


def test_registering_authority_creates_registered_lifecycle_event():
    adapter = MemoryRegistryAdapter()
    exported = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="exported",
        timestamp="2026-05-26T18:10:00Z",
        artifact_hashes={"bundle_hash": "sha256:bundle", "receipt_hash": "sha256:receipt"},
    )
    adapter.append_lifecycle_event("transfer-policy@3.5.6", exported)
    registered = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="registered",
        timestamp="2026-05-26T18:11:00Z",
        previous_event_id=exported["event_id"],
        artifact_hashes={"bundle_hash": "sha256:bundle", "receipt_hash": "sha256:receipt"},
    )
    events = adapter.append_lifecycle_event("transfer-policy@3.5.6", registered)

    assert [event["event_type"] for event in events] == ["exported", "registered"]
    assert events[-1]["previous_event_id"] == exported["event_id"]


def test_revoked_authority_keeps_prior_lineage():
    registered = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="registered",
        timestamp="2026-05-26T18:11:00Z",
    )
    revoked = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="revoked",
        timestamp="2026-05-26T19:00:00Z",
        previous_event_id=registered["event_id"],
        notes={"reason": "superseded operational posture"},
    )

    events = append_lifecycle_event([registered], revoked)

    assert events[0]["event_type"] == "registered"
    assert events[1]["event_type"] == "revoked"
    assert events[1]["previous_event_id"] == registered["event_id"]


def test_diagnostic_rollup_matches_diagnostics():
    rollup = build_diagnostic_rollup(
        authority_ref="transfer-policy@3.5.6",
        diagnostics=[
            _diagnostic("GQ004", "approval", "info"),
            _diagnostic("GQ005", "lifecycle", "warning"),
            _diagnostic("GQ999", "replay", "error"),
        ],
    )

    assert rollup == {
        "schema_version": "diagnostic_rollup.v1",
        "authority_ref": "transfer-policy@3.5.6",
        "authority_version": "3.5.6",
        "finding_count": 3,
        "warning_count": 1,
        "info_count": 1,
        "domains": ["approval", "lifecycle", "replay"],
        "highest_severity": "error",
        "diagnostic_ids": ["GQ004", "GQ005", "GQ999"],
    }


def test_registry_projection_is_deterministic():
    kwargs = {
        "authority": {"schema_version": "authority_contract.v1"},
        "preview": {"schema_version": "governance_impact_preview.v1"},
        "bundle": {"schema_version": "authority_bundle.v1", "authority_ref": "transfer-policy@3.5.6"},
        "diagnostics": [_diagnostic("GQ004", "approval", "info")],
        "publication_meaning": "transfer-policy@3.5.6 governs transfer funds.",
        "publication_summary": "Publishing creates a replayable governance record.",
        "operational_change": "Transfers above threshold require review.",
        "continuity_posture": "Resumed workflows require revalidation.",
        "lifecycle_effect": "Revoked authorities invalidate resumed execution.",
        "timeline": [{"event": "drafted", "detail": "Draft captured."}],
    }

    first = build_authority_workspace_projection(**kwargs)
    second = build_authority_workspace_projection(**kwargs)

    assert first == second
    assert first["schema_version"] == "authority_workspace_projection.v1"
    assert first["diagnostic_rollup"]["diagnostic_ids"] == ["GQ004"]


def _diagnostic(code: str, domain: str, severity: str) -> dict:
    return {
        "code": code,
        "domain": domain,
        "severity": severity,
    }
