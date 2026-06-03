from __future__ import annotations

from governance_ledger.semantics.publication import build_publication_receipt
from governance_ledger.semantics.diffing import build_semantic_authority_diff
from governance_ledger.semantics.lifecycle_enforcement import build_semantic_lifecycle_enforcement_projection
from governance_ledger.ui_server import build_publication_receipt_response, build_ui_diagnostics, compose_authority_publication


def test_ui_server_composes_artifacts_from_authoring_fields():
    result = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "contract_id": "treasury-policy",
            "contract_version": "2.1.0",
            "governance_category": "Financial",
            "approver_role": "treasury-governance",
            "approval_count": "2",
            "escalation_threshold": "250000",
            "validity_days": "30",
            "mutation_targets": "bank_api.transfer_funds",
            "continuity_revalidation": True,
            "revocation_invalidates_resume": True,
            "execution_context_semantics": {
                "schema_version": "execution_context_semantics.v1",
                "execution_context": "queued_async",
                "execution_boundary": "external_worker",
                "requires_replay_evidence": True,
                "requires_state_snapshot": True,
                "requires_temporal_validation": True,
                "resume_behavior": "revalidate_on_resume",
                "continuity_risk_profile": "medium",
                "runtime_enforced_by": "Guard/Cloud",
            },
        }
    )

    authority = result["authority_contract"]
    preview = result["governance_impact_preview"]
    packet = result["governance_review_packet"]
    bundle = result["authority_bundle"]
    registry_projection = result["authority_registry_projection"]
    release_narrative = result["authority_release_narrative"]
    workspace_projection = result["authority_workspace_projection"]
    operational_summary = result["authority_operational_summary"]

    assert authority["schema_version"] == "authority_contract.v1"
    assert authority["protected_resource"] == "Corporate Treasury Transfer System"
    assert authority["approval_requirements"]["thresholds"][0]["value"] == 250000
    assert authority["temporal_semantics"] == {
        "schema_version": "temporal_authority_semantics.v1",
        "validity_window": "P30D",
        "timestamp_source": "unspecified",
        "expiration_basis": "unspecified",
        "runtime_enforced_by": "Guard/Cloud",
    }
    assert authority["state_snapshot_semantics"] == {
        "schema_version": "state_posture_snapshot_semantics.v1",
        "snapshot_required": True,
        "snapshot_hash_algorithm": "sha256",
        "snapshot_subject": "active_governance_state",
        "resume_comparison": "snapshot_hash_must_match_active_state_hash",
        "drift_result": "continuity_drift_detected",
        "runtime_enforced_by": "Guard/Cloud",
    }
    assert authority["execution_context_semantics"]["execution_context"] == "queued_async"
    assert authority["governance_actor"] == {
        "schema_version": "governance_actor.v1",
        "actor_id": "treasury-governance",
        "actor_type": "human_role",
        "authority_scope": ["transfer_funds_approval"],
        "delegation_allowed": False,
        "attestation_required": False,
        "identity_continuity_required": True,
    }
    assert authority["approval_chain_semantics"]["required_approval_count"] == 2
    assert authority["identity_continuity_semantics"]["runtime_enforced_by"] == "Guard/Cloud"
    assert preview["execution_context"]["replay_posture"] == "Replay-backed continuity required"
    assert preview["schema_version"] == "governance_impact_preview.v1"
    assert packet["schema_version"] == "governance_review_packet.v1"
    assert bundle["schema_version"] == "authority_bundle.v1"
    assert bundle["authority_ref"] == "treasury-policy@2.1.0"
    assert registry_projection == {
        "schema_version": "authority_registry_projection.v1",
        "authority_ref": "treasury-policy@2.1.0",
        "governed_resource": "Corporate Treasury Transfer System",
        "governed_action": "transfer funds",
        "continuity_posture": "resume revalidation and revocation invalidation",
        "escalation_threshold": "amount > 250,000",
        "semantic_integrity_posture": "compatible",
    }
    assert release_narrative["schema_version"] == "authority_release_narrative.v1"
    assert release_narrative["authority_ref"] == "treasury-policy@2.1.0"
    assert "Corporate Treasury Transfer System" in release_narrative["headline"]
    assert workspace_projection["schema_version"] == "authority_workspace_projection.v1"
    assert workspace_projection["authority_ref"] == "treasury-policy@2.1.0"
    assert workspace_projection["operational_change"] == release_narrative["operational_change"]
    assert workspace_projection["continuity_posture"] == release_narrative["continuity_summary"]
    assert workspace_projection["lifecycle_effect"] == release_narrative["lifecycle_summary"]
    assert workspace_projection["diagnostics_summary"] == {"findings": 4, "warnings": 2, "info": 2}
    assert operational_summary["schema_version"] == "authority_operational_summary.v1"
    assert operational_summary["authority_ref"] == "treasury-policy@2.1.0"
    assert operational_summary["governance_meaning"] == [
        workspace_projection["operational_change"],
        workspace_projection["continuity_posture"],
        workspace_projection["replay_posture"],
    ]
    assert [diagnostic["code"] for diagnostic in result["diagnostics"]] == [
        "GQ004",
        "GQ005",
        "temporal_source_ambiguity",
        "attestation_requirement_gap",
    ]
    assert {diagnostic["blocks_publication"] for diagnostic in result["diagnostics"]} == {False}


def test_ui_server_semantic_diff_artifact_is_ledger_generated():
    previous = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "contract_id": "treasury-policy",
            "contract_version": "2.1.0",
            "approver_role": "treasury-governance",
            "approval_count": "1",
        }
    )
    current = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "contract_id": "treasury-policy",
            "contract_version": "2.2.0",
            "approver_role": "treasury-governance",
            "approval_count": "2",
        }
    )

    diff = build_semantic_authority_diff(previous["authority_contract"], current["authority_contract"])

    assert diff["schema_version"] == "semantic_authority_diff.v1"
    assert diff["previous_authority_ref"] == "treasury-policy@2.1.0"
    assert diff["current_authority_ref"] == "treasury-policy@2.2.0"
    assert "Human approval requirements increased." in diff["operational_impact_narratives"]
    assert diff["guard_compatibility_projection"]["schema_version"] == "guard_compatibility_projection.v1"


def test_ui_server_lifecycle_enforcement_projection_is_diff_derived():
    previous = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "contract_id": "treasury-policy",
            "contract_version": "2.1.0",
            "approver_role": "treasury-governance",
            "approval_count": "1",
        }
    )
    current = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "contract_id": "treasury-policy",
            "contract_version": "2.2.0",
            "approver_role": "treasury-governance",
            "approval_count": "2",
            "continuity_revalidation": True,
        }
    )

    diff = build_semantic_authority_diff(previous["authority_contract"], current["authority_contract"])
    projection = build_semantic_lifecycle_enforcement_projection(diff)

    assert projection["schema_version"] == "semantic_lifecycle_enforcement_projection.v1"
    assert projection["source_diff_schema_version"] == "semantic_authority_diff.v1"
    assert projection["execution_admissibility_projection"]["schema_version"] == "execution_admissibility_projection.v1"
    assert "does_not_execute_guard" in projection["non_goals"]


def test_ui_server_emits_guidance_diagnostic_for_default_mutation_target():
    result = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "approver_role": "treasury-governance",
        }
    )

    diagnostics = result["diagnostics"]

    assert {diagnostic["code"] for diagnostic in diagnostics} == {
        "GQ004",
        "GQ005",
        "default_mutation_target",
        "temporal_source_ambiguity",
        "attestation_requirement_gap",
    }
    assert _diagnostic(diagnostics, "default_mutation_target")["title"] == "Derived Mutation Target"
    assert _diagnostic(diagnostics, "temporal_source_ambiguity")["title"] == "Temporal Source Ambiguity"
    assert _diagnostic(diagnostics, "attestation_requirement_gap")["title"] == "Attestation Requirement Gap"
    assert {diagnostic["blocks_publication"] for diagnostic in diagnostics} == {False}


def test_ui_server_emits_snapshot_gap_when_continuity_lacks_snapshot_expectation():
    result = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "approver_role": "treasury-governance",
        }
    )
    authority = dict(result["authority_contract"])
    authority.pop("state_snapshot_semantics")

    diagnostics = build_ui_diagnostics(authority, {"mutation_targets": "bank_api.transfer_funds"}, result["authority_bundle"])

    assert _diagnostic(diagnostics, "snapshot_continuity_gap")["title"] == "Snapshot Continuity Gap"
    assert _diagnostic(diagnostics, "snapshot_continuity_gap")["blocks_publication"] is False


def test_ui_server_emits_execution_context_diagnostics():
    result = compose_authority_publication(
        {
            "protected_system": "Deployment Workflow",
            "governed_action": "deferred execution",
            "approver_role": "release-governance",
            "continuity_revalidation": False,
            "revocation_invalidates_resume": False,
            "execution_context_semantics": {
                "schema_version": "execution_context_semantics.v1",
                "execution_context": "resumed_workflow",
                "execution_boundary": "external_worker",
                "requires_replay_evidence": True,
                "requires_state_snapshot": True,
                "requires_temporal_validation": False,
                "resume_behavior": "revalidate_on_resume",
                "continuity_risk_profile": "medium",
                "runtime_enforced_by": "Guard/Cloud",
            },
        }
    )

    diagnostics = result["diagnostics"]

    assert _diagnostic(diagnostics, "resume_validation_gap")["title"] == "Resume Validation Gap"
    assert "execution_context_ambiguity" not in {diagnostic["code"] for diagnostic in diagnostics}


def test_ui_server_emits_execution_context_ambiguity_for_deferred_text_without_context():
    result = compose_authority_publication(
        {
            "protected_system": "Deployment Workflow",
            "governed_action": "deferred execution",
            "approver_role": "release-governance",
        }
    )

    assert _diagnostic(result["diagnostics"], "execution_context_ambiguity")["title"] == "Execution Context Ambiguity"


def test_ui_server_emits_identity_responsibility_diagnostics():
    result = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "approver_role": "treasury-governance",
            "approval_chain_semantics": {
                "schema_version": "approval_chain_semantics.v1",
                "required_approval_count": 2,
                "required_roles": ["treasury-governance"],
                "independence_required": True,
                "self_approval_prohibited": True,
                "independent_actor_refs": [],
                "delegation_posture": "ambiguous",
                "attestation_required": True,
                "human_in_loop_required": True,
                "ai_recommendation_posture": "not_present",
            },
            "governance_actor": {
                "schema_version": "governance_actor.v1",
                "actor_id": "treasury-governance",
                "actor_type": "human_role",
                "authority_scope": ["transfer_funds_approval"],
                "delegation_allowed": False,
                "attestation_required": True,
                "identity_continuity_required": True,
            },
        }
    )

    diagnostics = result["diagnostics"]

    assert _diagnostic(diagnostics, "approval_independence_ambiguity")["title"] == "Approval Independence Ambiguity"
    assert _diagnostic(diagnostics, "delegation_ambiguity")["title"] == "Delegation Ambiguity"


def test_ui_server_receipt_builder_supports_publication_notes():
    result = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "approver_role": "treasury-governance",
        }
    )

    receipt = build_publication_receipt(
        authority_bundle=result["authority_bundle"],
        published_at="2026-05-25T18:00:00Z",
        readiness_confirmations={
            "semantic_diagnostics_reviewed": True,
            "lineage_validated": True,
            "continuity_posture_reviewed": True,
            "replay_implications_reviewed": True,
            "lifecycle_implications_acknowledged": True,
        },
        publication_notes=[
            {
                "note_type": "governance_revision_context",
                "text": "Initial local publication receipt.",
                "created_at": "2026-05-25T17:59:00Z",
            }
        ],
    )

    assert receipt["schema_version"] == "publication_receipt.v1"
    assert receipt["publication_notes"][0]["text"] == "Initial local publication receipt."
    assert receipt["readiness_confirmations"]["lineage_validated"] is True

    response = build_publication_receipt_response(receipt)

    assert response["status"] == "exported"
    assert response["publication_receipt"] == receipt
    assert response["receipt_hash"] == receipt["receipt_hash"]
    assert response["bundle_hash"] == receipt["bundle_hash"]


def _diagnostic(diagnostics: list[dict], code: str) -> dict:
    for diagnostic in diagnostics:
        if diagnostic["code"] == code:
            return diagnostic
    raise AssertionError(f"Missing diagnostic {code}: {diagnostics}")
