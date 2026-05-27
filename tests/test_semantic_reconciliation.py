from __future__ import annotations

import json
from pathlib import Path

from governance_ledger.semantics.extraction import extract_governance_semantics
from governance_ledger.semantics.reconciliation import (
    build_governance_semantic_reconciliation,
    build_semantic_interpretation_decision,
    build_semantic_reconciliation_projection,
)

ROOT = Path(__file__).resolve().parents[1]


def test_unresolved_ambiguity_does_not_become_normalized_meaning():
    extraction = extract_governance_semantics("Large financial transfers require executive review.")
    extraction["ambiguities"].append(
        {
            "ambiguity_type": "undefined_threshold",
            "text": "Large financial transfers",
            "summary": "Large is not a deterministic threshold.",
            "requires_operator_resolution": True,
        }
    )

    reconciliation = build_governance_semantic_reconciliation(semantic_extraction=extraction)

    assert reconciliation["schema_version"] == "governance_semantic_reconciliation.v1"
    assert reconciliation["interpretation_completeness_posture"] == "operator_required"
    assert reconciliation["unresolved_ambiguities"]
    assert reconciliation["final_normalized_semantic_meaning"] == {}


def test_operator_decision_records_interpretation_provenance_and_normalizes_meaning():
    extraction = extract_governance_semantics("Large financial transfers require executive review.")
    extraction["ambiguities"] = [
        {
            "ambiguity_id": "ambiguity-large-transfer",
            "ambiguity_type": "undefined_threshold",
            "text": "Large financial transfers",
            "summary": "Large is not a deterministic threshold.",
            "requires_operator_resolution": True,
        }
    ]
    decision = build_semantic_interpretation_decision(
        decision_type="threshold_definition",
        ambiguity_id="ambiguity-large-transfer",
        resolved_value=250000,
        rationale="Treasury policy baseline",
    )

    reconciliation = build_governance_semantic_reconciliation(
        semantic_extraction=extraction,
        interpretation_decisions=[decision],
    )

    assert reconciliation["interpretation_completeness_posture"] == "complete"
    assert reconciliation["unresolved_ambiguities"] == []
    assert reconciliation["operator_interpretation_decisions"] == [decision]
    assert reconciliation["final_normalized_semantic_meaning"]["escalation_threshold"] == 250000
    assert reconciliation["normalization_decisions"] == ["threshold normalized from operator interpretation"]


def test_semantic_reconciliation_projection_surfaces_completeness_posture():
    extraction = extract_governance_semantics("Large financial transfers require executive review.")
    extraction["ambiguities"].append(
        {
            "ambiguity_type": "undefined_threshold",
            "summary": "Large is not a deterministic threshold.",
            "requires_operator_resolution": True,
        }
    )
    reconciliation = build_governance_semantic_reconciliation(semantic_extraction=extraction)

    projection = build_semantic_reconciliation_projection(reconciliation)

    assert projection["schema_version"] == "semantic_reconciliation_projection.v1"
    assert projection["interpretation_completeness_posture"] == "operator_required"
    assert projection["unresolved_ambiguities"]


def test_semantic_reconciliation_schemas_are_canonical():
    for name, const in {
        "governance_semantic_reconciliation.v1.json": "governance_semantic_reconciliation.v1",
        "semantic_conflict.v1.json": "semantic_conflict.v1",
        "semantic_ambiguity.v1.json": "semantic_ambiguity.v1",
        "semantic_interpretation_decision.v1.json": "semantic_interpretation_decision.v1",
        "semantic_reconciliation_projection.v1.json": "semantic_reconciliation_projection.v1",
    }.items():
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert schema["properties"]["schema_version"]["const"] == const
