from __future__ import annotations

from governance_ledger.ui_server import compose_authority_publication


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

    assert authority["schema_version"] == "authority_contract.v1"
    assert authority["protected_resource"] == "Corporate Treasury Transfer System"
    assert authority["approval_requirements"]["thresholds"][0]["value"] == 250000
    assert preview["schema_version"] == "governance_impact_preview.v1"
    assert packet["schema_version"] == "governance_review_packet.v1"
    assert bundle["schema_version"] == "authority_bundle.v1"
    assert bundle["authority_ref"] == "treasury-policy@2.1.0"
    assert result["diagnostics"] == []


def test_ui_server_emits_guidance_diagnostic_for_default_mutation_target():
    result = compose_authority_publication(
        {
            "protected_system": "Corporate Treasury Transfer System",
            "governed_action": "transfer funds",
            "approver_role": "treasury-governance",
        }
    )

    assert result["diagnostics"] == [
        {
            "code": "default_mutation_target",
            "severity": "info",
            "text": "Mutation target was derived from governed action; confirm it matches the operational system.",
        }
    ]
