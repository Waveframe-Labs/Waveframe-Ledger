from __future__ import annotations

import json
from pathlib import Path

from governance_ledger.semantics.extraction import build_governance_source, extract_governance_semantics

ROOT = Path(__file__).resolve().parents[1]


POLICY_TEXT = (
    "Corporate Treasury Transfer System transfers above $250,000 require approval by treasury governance. "
    "Approval is valid for 30 days. Resumed workflows must revalidate if authority posture changes, "
    "and revoked authorities invalidate resumed execution. Approval evidence and decision trace are required for replay."
)


def test_governance_source_v1_captures_policy_text_and_stable_hash():
    first = build_governance_source(POLICY_TEXT)
    second = build_governance_source(POLICY_TEXT)

    assert first == second
    assert first["schema_version"] == "governance_source.v1"
    assert first["source_type"] == "policy_text"
    assert first["source_hash"].startswith("sha256:")
    assert first["human_review_required"] is True
    assert first["extraction_mode"] == "deterministic_rules"


def test_semantic_extraction_is_deterministic_and_requires_review():
    first = extract_governance_semantics(POLICY_TEXT)
    second = extract_governance_semantics(POLICY_TEXT)

    assert first == second
    assert first["schema_version"] == "governance_semantic_extraction.v1"
    assert first["extraction_method"] == "deterministic_pattern_pass"
    assert first["confidence_posture"] == "requires_human_review"
    assert "requires operator confirmation before publication" in first["non_goals"]


def test_semantic_extraction_extracts_candidate_authority_anchors():
    extraction = extract_governance_semantics(POLICY_TEXT)
    candidate = extraction["candidate_authority"]

    assert candidate["protected_system"] == "Corporate Treasury Transfer System"
    assert candidate["governed_action"] == "transfer funds"
    assert candidate["approver_role"] == "treasury-governance"
    assert candidate["approval_count"] == 1
    assert candidate["escalation_threshold"] == 250000
    assert candidate["escalation_semantics"] == "Executions above $250,000 require treasury-governance review."
    assert candidate["validity_days"] == 30
    assert candidate["temporal_semantics"]["validity_window"] == "P30D"
    assert candidate["temporal_semantics"]["timestamp_source"] == "unspecified"
    assert candidate["temporal_semantics"]["runtime_enforced_by"] == "Guard/Cloud"
    assert candidate["continuity_revalidation"] is True
    assert candidate["revocation_invalidates_resume"] is True
    assert candidate["state_snapshot_semantics"]["snapshot_required"] is True
    assert candidate["state_snapshot_semantics"]["runtime_enforced_by"] == "Guard/Cloud"
    assert {rule["rule_type"] for rule in extraction["candidate_rules"]} >= {
        "approval_requirement",
        "escalation_threshold",
        "continuity_semantics",
        "required_evidence",
        "temporal_authority_semantics",
        "state_posture_snapshot_semantics",
    }


def test_semantic_extraction_emits_timestamp_source_ambiguity_when_missing():
    extraction = extract_governance_semantics(
        "Payment Workflow action: transfer funds. Approval is valid for 30 days."
    )

    candidate = extraction["candidate_authority"]
    ambiguity_types = {item["ambiguity_type"] for item in extraction["ambiguities"]}

    assert candidate["temporal_semantics"]["validity_window"] == "P30D"
    assert candidate["temporal_semantics"]["timestamp_source"] == "unspecified"
    assert "timestamp_source_unspecified" in ambiguity_types


def test_semantic_extraction_captures_timestamp_sources():
    signed = extract_governance_semantics(
        "Payment Workflow action: transfer funds. Approval is valid for 30 days using signed execution timestamp."
    )
    oracle = extract_governance_semantics(
        "Payment Workflow action: transfer funds. Approval is valid for 30 days using signed oracle time."
    )
    block = extract_governance_semantics(
        "Payment Workflow action: transfer funds. Approval is valid for 30 days using block timestamp."
    )
    cloud = extract_governance_semantics(
        "Payment Workflow action: transfer funds. Approval is valid for 30 days using Cloud-attested time."
    )

    assert signed["candidate_authority"]["temporal_semantics"]["timestamp_source"] == "execution_payload"
    assert oracle["candidate_authority"]["temporal_semantics"]["timestamp_source"] == "signed_oracle"
    assert block["candidate_authority"]["temporal_semantics"]["timestamp_source"] == "block_timestamp"
    assert cloud["candidate_authority"]["temporal_semantics"]["timestamp_source"] == "cloud_attested_time"


def test_semantic_extraction_continuity_revalidation_implies_snapshot_semantics():
    extraction = extract_governance_semantics(
        "Payment Workflow must revalidate on resume and compare current policy version before resuming."
    )
    candidate = extraction["candidate_authority"]

    assert candidate["state_snapshot_semantics"] == {
        "schema_version": "state_posture_snapshot_semantics.v1",
        "snapshot_required": True,
        "snapshot_hash_algorithm": "sha256",
        "snapshot_subject": "current_policy_version",
        "resume_comparison": "snapshot_hash_must_match_active_state_hash",
        "drift_result": "continuity_drift_detected",
        "runtime_enforced_by": "Guard/Cloud",
    }


def test_semantic_extraction_revoked_authority_continuity_emits_snapshot_comparison():
    extraction = extract_governance_semantics(
        "Revoked authority invalidates paused workflows and resumed execution requires current governance state."
    )
    candidate = extraction["candidate_authority"]

    assert candidate["revocation_invalidates_resume"] is True
    assert candidate["state_snapshot_semantics"]["snapshot_subject"] == "active_governance_state"
    assert candidate["state_snapshot_semantics"]["resume_comparison"] == "snapshot_hash_must_match_active_state_hash"
    assert candidate["state_snapshot_semantics"]["drift_result"] == "continuity_drift_detected"
    assert candidate["state_snapshot_semantics"]["runtime_enforced_by"] == "Guard/Cloud"


def test_semantic_extraction_policy_change_language_emits_continuity_snapshot_expectation():
    extraction = extract_governance_semantics(
        "If policy changes before execution, resumed workflows require current governance state."
    )
    candidate = extraction["candidate_authority"]

    assert candidate["continuity_revalidation"] is True
    assert candidate["state_snapshot_semantics"]["snapshot_required"] is True
    assert candidate["state_snapshot_semantics"]["snapshot_subject"] == "active_governance_state"


def test_semantic_extraction_expires_after_approval_records_temporal_trigger():
    extraction = extract_governance_semantics(
        "Payment Workflow approval expires after approval using block timestamp."
    )
    temporal = extraction["candidate_authority"]["temporal_semantics"]

    assert temporal["expiration_trigger"] == "approval_completion"
    assert temporal["timestamp_source"] == "block_timestamp"
    assert temporal["runtime_enforced_by"] == "Guard/Cloud"


def test_semantic_extraction_normalizes_execution_context_semantics():
    extraction = extract_governance_semantics(
        "Queued deployment may resume later after approval and requires replay evidence."
    )
    execution_context = extraction["candidate_authority"]["execution_context_semantics"]

    assert execution_context == {
        "schema_version": "execution_context_semantics.v1",
        "execution_context": "queued_async",
        "execution_boundary": "external_worker",
        "requires_replay_evidence": True,
        "requires_state_snapshot": True,
        "requires_temporal_validation": True,
        "resume_behavior": "revalidate_on_resume",
        "continuity_risk_profile": "medium",
        "runtime_enforced_by": "Guard/Cloud",
    }
    assert "execution_context_semantics" in {rule["rule_type"] for rule in extraction["candidate_rules"]}


def test_semantic_extraction_emits_execution_context_ambiguity_for_vague_deferred_execution():
    extraction = extract_governance_semantics("Approval controls deferred execution after governance review.")

    assert "execution_context_semantics" not in {
        rule["rule_type"] for rule in extraction["candidate_rules"]
    }
    assert "execution_context_ambiguity" in {
        ambiguity["ambiguity_type"] for ambiguity in extraction["ambiguities"]
    }


def test_semantic_extraction_keeps_missing_fields_explicit():
    extraction = extract_governance_semantics("This policy requires appropriate approval for sensitive actions.")

    missing_fields = {item["field"] for item in extraction["missing_information"]}
    assert "protected_system" in missing_fields
    assert "escalation_threshold" in missing_fields
    assert extraction["ambiguities"]


def test_semantic_extraction_schemas_are_canonical():
    source_schema = json.loads((ROOT / "schemas" / "governance_source.v1.json").read_text(encoding="utf-8"))
    extraction_schema = json.loads((ROOT / "schemas" / "governance_semantic_extraction.v1.json").read_text(encoding="utf-8"))
    temporal_schema = json.loads((ROOT / "schemas" / "temporal_authority_semantics.v1.json").read_text(encoding="utf-8"))
    snapshot_schema = json.loads((ROOT / "schemas" / "state_posture_snapshot_semantics.v1.json").read_text(encoding="utf-8"))
    execution_context_schema = json.loads((ROOT / "schemas" / "execution_context_semantics.v1.json").read_text(encoding="utf-8"))

    assert source_schema["properties"]["schema_version"]["const"] == "governance_source.v1"
    assert "source_text" in source_schema["required"]
    assert extraction_schema["properties"]["schema_version"]["const"] == "governance_semantic_extraction.v1"
    assert "candidate_authority" in extraction_schema["required"]
    assert temporal_schema["properties"]["schema_version"]["const"] == "temporal_authority_semantics.v1"
    assert temporal_schema["properties"]["runtime_enforced_by"]["const"] == "Guard/Cloud"
    assert snapshot_schema["properties"]["schema_version"]["const"] == "state_posture_snapshot_semantics.v1"
    assert snapshot_schema["properties"]["runtime_enforced_by"]["const"] == "Guard/Cloud"
    assert execution_context_schema["properties"]["schema_version"]["const"] == "execution_context_semantics.v1"
    assert execution_context_schema["properties"]["runtime_enforced_by"]["const"] == "Guard/Cloud"
