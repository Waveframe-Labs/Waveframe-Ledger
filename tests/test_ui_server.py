from __future__ import annotations

from governance_ledger.semantics.publication import build_publication_receipt
from governance_ledger.ui_server import build_publication_receipt_response, compose_authority_publication


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
        }
    )

    authority = result["authority_contract"]
    preview = result["governance_impact_preview"]
    packet = result["governance_review_packet"]
    bundle = result["authority_bundle"]
    registry_projection = result["authority_registry_projection"]
    release_narrative = result["authority_release_narrative"]

    assert authority["schema_version"] == "authority_contract.v1"
    assert authority["protected_resource"] == "Corporate Treasury Transfer System"
    assert authority["approval_requirements"]["thresholds"][0]["value"] == 250000
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
    assert [diagnostic["code"] for diagnostic in result["diagnostics"]] == ["GQ004", "GQ005"]
    assert {diagnostic["blocks_publication"] for diagnostic in result["diagnostics"]} == {False}


def test_ui_server_emits_guidance_diagnostic_for_default_mutation_target():
    result = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "approver_role": "treasury-governance",
        }
    )

    diagnostics = result["diagnostics"]

    assert {diagnostic["code"] for diagnostic in diagnostics} == {"GQ004", "GQ005", "default_mutation_target"}
    assert _diagnostic(diagnostics, "default_mutation_target")["title"] == "Derived Mutation Target"
    assert {diagnostic["blocks_publication"] for diagnostic in diagnostics} == {False}


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
