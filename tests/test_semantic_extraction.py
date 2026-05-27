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
    assert candidate["validity_days"] == 30
    assert candidate["continuity_revalidation"] is True
    assert candidate["revocation_invalidates_resume"] is True
    assert {rule["rule_type"] for rule in extraction["candidate_rules"]} >= {
        "approval_requirement",
        "escalation_threshold",
        "continuity_semantics",
        "required_evidence",
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

    assert source_schema["properties"]["schema_version"]["const"] == "governance_source.v1"
    assert "source_text" in source_schema["required"]
    assert extraction_schema["properties"]["schema_version"]["const"] == "governance_semantic_extraction.v1"
    assert "candidate_authority" in extraction_schema["required"]
