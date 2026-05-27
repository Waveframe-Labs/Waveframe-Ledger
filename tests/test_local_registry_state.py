from __future__ import annotations

from governance_ledger.local_registry import (
    MemoryRegistryAdapter,
    build_active_authority_projection,
    build_authority_drift_indicators,
    build_authority_lifecycle_event,
    build_authority_lineage_projection,
    build_authority_operational_summary,
    build_authority_registry_entry,
    build_authority_workspace_projection,
    build_diagnostic_rollup,
    build_governance_activity_projection,
    build_registry_health_projection,
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
    drafted = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="drafted",
        timestamp="2026-05-26T18:00:00Z",
    )
    reviewed = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="reviewed",
        timestamp="2026-05-26T18:05:00Z",
        previous_event_id=drafted["event_id"],
    )
    exported = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="exported",
        timestamp="2026-05-26T18:10:00Z",
        previous_event_id=reviewed["event_id"],
        artifact_hashes={"bundle_hash": "sha256:bundle", "receipt_hash": "sha256:receipt"},
    )
    adapter.append_lifecycle_event("transfer-policy@3.5.6", drafted)
    adapter.append_lifecycle_event("transfer-policy@3.5.6", reviewed)
    adapter.append_lifecycle_event("transfer-policy@3.5.6", exported)
    registered = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="registered",
        timestamp="2026-05-26T18:11:00Z",
        previous_event_id=exported["event_id"],
        artifact_hashes={"bundle_hash": "sha256:bundle", "receipt_hash": "sha256:receipt"},
    )
    events = adapter.append_lifecycle_event("transfer-policy@3.5.6", registered)

    assert [event["event_type"] for event in events] == ["drafted", "reviewed", "exported", "registered"]
    assert events[-1]["previous_event_id"] == exported["event_id"]
    assert events[-1]["caused_by_event_id"] == exported["event_id"]


def test_invalid_lifecycle_transition_fails():
    registered = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="registered",
        timestamp="2026-05-26T18:11:00Z",
    )
    drafted = build_authority_lifecycle_event(
        authority_ref="transfer-policy@3.5.6",
        event_type="drafted",
        timestamp="2026-05-26T18:12:00Z",
        previous_event_id=registered["event_id"],
    )

    try:
        append_lifecycle_event([registered], drafted)
    except ValueError as exc:
        assert "registered -> drafted" in str(exc)
    else:
        raise AssertionError("registered -> drafted transition should fail")


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


def test_drift_detection_compares_previous_registry_state():
    previous = _registry_entry(
        "transfer-policy@3.4.5",
        approval_count=1,
        escalation_threshold="amount > 250,000",
        continuity_posture="resume revalidation",
    )
    current = _registry_entry(
        "transfer-policy@3.4.6",
        approval_count=2,
        escalation_threshold="amount > 100,000",
        continuity_posture="resume revalidation and revocation invalidation",
    )

    drift = build_authority_drift_indicators(previous, current)

    assert {
        (item["drift_type"], item["severity"], item["from"], item["to"])
        for item in drift
    } == {
        ("continuity_posture_changed", "warning", "resume revalidation", "resume revalidation and revocation invalidation"),
        ("escalation_threshold_changed", "info", "amount > 250,000", "amount > 100,000"),
        ("approval_requirement_changed", "warning", 1, 2),
    }


def test_authority_lineage_projection_builds_chain_and_drift():
    previous = _registry_entry(
        "transfer-policy@3.4.5",
        approval_count=1,
        status="superseded",
        superseded_by="transfer-policy@3.4.6",
    )
    current = _registry_entry(
        "transfer-policy@3.4.6",
        approval_count=2,
        status="revoked",
        latest_receipt_hash="sha256:receipt",
    )

    lineage = build_authority_lineage_projection(entries=[current, previous])

    assert lineage["schema_version"] == "authority_lineage_projection.v1"
    assert [node["authority_ref"] for node in lineage["nodes"]] == [
        "transfer-policy@3.4.5",
        "transfer-policy@3.4.6",
    ]
    assert {
        (edge["from"], edge["to"], edge["relationship"])
        for edge in lineage["edges"]
    } == {
        ("transfer-policy@3.4.5", "transfer-policy@3.4.6", "version_successor"),
        ("transfer-policy@3.4.5", "transfer-policy@3.4.6", "superseded_by"),
    }
    assert any(item["drift_type"] == "approval_requirement_changed" for item in lineage["drift_indicators"])


def test_authority_operational_summary_renders_governance_object_view():
    entry = _registry_entry(
        "transfer-policy@3.4.5",
        approval_count=1,
        status="registered",
        latest_receipt_hash="sha256:receipt",
    )
    workspace_projection = {
        "operational_change": "Executions above $300,000 require treasury governance review.",
        "continuity_posture": "Resumed workflows invalidate after authority revocation.",
        "replay_posture": "Replay evidence binds to transfer-policy@3.4.5 lineage.",
    }

    summary = build_authority_operational_summary(
        authority={
            "schema_version": "authority_contract.v1",
            "protected_resource": "Corporate Treasury Transfer System",
            "governed_actions": ["transfer funds"],
        },
        bundle={"schema_version": "authority_bundle.v1", "authority_ref": "transfer-policy@3.4.5"},
        workspace_projection=workspace_projection,
        registry_entry=entry,
        lineage_entries=[entry],
    )

    assert summary["schema_version"] == "authority_operational_summary.v1"
    assert summary["governance_meaning"] == [
        "Executions above $300,000 require treasury governance review.",
        "Resumed workflows invalidate after authority revocation.",
        "Replay evidence binds to transfer-policy@3.4.5 lineage.",
    ]
    assert summary["replay_readiness"]["receipt_present"] is True
    assert summary["relationship_graph"]["nodes"][0]["authority_ref"] == "transfer-policy@3.4.5"


def test_governance_activity_projection_emits_lifecycle_and_drift_activity():
    previous = _registry_entry(
        "transfer-policy@3.4.5",
        approval_count=1,
        status="superseded",
        continuity_posture="resume revalidation",
        superseded_by="transfer-policy@3.4.6",
    )
    current = _registry_entry(
        "transfer-policy@3.4.6",
        approval_count=2,
        status="registered",
        continuity_posture="resume revalidation and revocation invalidation",
        latest_receipt_hash="sha256:receipt",
    )

    projection = build_governance_activity_projection(entries=[previous, current])

    assert projection["schema_version"] == "governance_activity_projection.v1"
    assert any(item["activity_type"] == "authority_registered" for item in projection["activity"])
    assert any(item["activity_type"] == "continuity_posture_changed" for item in projection["activity"])
    continuity = next(item for item in projection["activity"] if item["activity_type"] == "continuity_posture_changed")
    assert continuity["severity"] == "warning"
    assert continuity["continuity_impact"] == "review_required"


def test_registry_health_projection_reports_replay_and_continuity_posture():
    previous = _registry_entry(
        "transfer-policy@3.4.5",
        approval_count=1,
        status="superseded",
        continuity_posture="resume revalidation",
        superseded_by="transfer-policy@3.4.6",
    )
    current = _registry_entry(
        "transfer-policy@3.4.6",
        approval_count=2,
        status="registered",
        continuity_posture="resume revalidation and revocation invalidation",
        latest_receipt_hash="sha256:receipt",
    )

    projection = build_registry_health_projection(entries=[previous, current])

    assert projection["schema_version"] == "registry_health_projection.v1"
    assert projection["registry_posture"] == "continuity_drift_detected"
    assert projection["lineage_posture"]["posture"] == "continuity_drift_detected"
    assert {item["posture"] for item in projection["authority_posture"]} == {
        "replay_posture_incomplete",
        "healthy",
    }


def test_active_authority_projection_resolves_current_registered_version():
    older = _registry_entry(
        "transfer-policy@3.4.5",
        approval_count=1,
        status="superseded",
        superseded_by="transfer-policy@3.4.6",
    )
    current = _registry_entry(
        "transfer-policy@3.4.6",
        approval_count=2,
        status="registered",
        latest_receipt_hash="sha256:receipt",
    )

    projection = build_active_authority_projection(entries=[older, current])

    assert projection == {
        "schema_version": "active_authority_projection.v1",
        "active_authorities": [
            {
                "authority_family": "transfer-policy",
                "active_authority_ref": "transfer-policy@3.4.6",
                "active_authority_version": "3.4.6",
                "status": "registered",
                "reason": "latest registered authority without supersession",
            }
        ],
    }


def _diagnostic(code: str, domain: str, severity: str) -> dict:
    return {
        "code": code,
        "domain": domain,
        "severity": severity,
    }


def _registry_entry(
    authority_ref: str,
    *,
    approval_count: int,
    status: str = "registered",
    escalation_threshold: str = "amount > 250,000",
    continuity_posture: str = "resume revalidation",
    superseded_by: str | None = None,
    latest_receipt_hash: str | None = None,
) -> dict:
    return {
        "schema_version": "authority_registry_entry.v1",
        "authority_ref": authority_ref,
        "authority_version": authority_ref.rsplit("@", 1)[1],
        "status": status,
        "protected_resource": "Corporate Treasury Transfer System",
        "governed_action": "transfer funds",
        "continuity_posture": continuity_posture,
        "replay_readiness": "receipt available" if latest_receipt_hash else "receipt pending",
        "diagnostic_summary": {},
        "latest_bundle_hash": "sha256:bundle",
        "latest_receipt_hash": latest_receipt_hash,
        "lifecycle_event_ids": [],
        "supersedes": None,
        "superseded_by": superseded_by,
        "created_at": "2026-05-26T18:00:00Z",
        "updated_at": "2026-05-26T18:00:00Z",
        "escalation_threshold": escalation_threshold,
        "approval_requirement": approval_count,
        "lifecycle_events": [
            {
                "schema_version": "authority_lifecycle_event.v1",
                "event_id": f"event-{authority_ref}",
                "authority_ref": authority_ref,
                "authority_version": authority_ref.rsplit("@", 1)[1],
                "event_type": status,
                "timestamp": "2026-05-26T18:00:00Z",
                "actor": "local-ledger-ui",
                "source": "governance-ledger",
                "artifact_hashes": {"bundle_hash": "sha256:bundle"},
                "notes": {"detail": "Lifecycle event recorded."},
                "previous_event_id": None,
            }
        ],
    }
