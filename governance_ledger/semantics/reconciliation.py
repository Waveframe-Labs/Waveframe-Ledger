"""Semantic reconciliation artifacts for interpreted governance meaning."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_semantic_interpretation_decision(
    *,
    decision_type: str,
    resolved_value: Any,
    rationale: str,
    ambiguity_id: str | None = None,
    operator: str = "local-ledger-ui",
) -> dict[str, Any]:
    return {
        "schema_version": "semantic_interpretation_decision.v1",
        "decision_id": "decision-" + hashlib.sha256(
            json.dumps(
                {"decision_type": decision_type, "resolved_value": resolved_value, "rationale": rationale},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:12],
        "decision_type": decision_type,
        "ambiguity_id": ambiguity_id,
        "resolved_value": resolved_value,
        "rationale": rationale,
        "operator": operator,
        "decision_posture": "operator_reviewed",
    }


def build_governance_semantic_reconciliation(
    *,
    semantic_extraction: dict[str, Any],
    interpretation_decisions: list[dict[str, Any]] | None = None,
    rejected_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record how extracted governance meaning became normalized authority meaning."""
    decisions = interpretation_decisions or []
    ambiguities = [
        _semantic_ambiguity(item, index)
        for index, item in enumerate(semantic_extraction.get("ambiguities", []), start=1)
    ]
    resolved_ids = {decision.get("ambiguity_id") for decision in decisions if decision.get("ambiguity_id")}
    unresolved = [
        ambiguity
        for ambiguity in ambiguities
        if ambiguity["requires_operator_resolution"] and ambiguity["ambiguity_id"] not in resolved_ids
    ]
    normalized = dict(semantic_extraction.get("candidate_authority") or {})
    normalization_decisions = []
    for decision in decisions:
        if decision.get("decision_type") == "threshold_definition":
            normalized["escalation_threshold"] = decision.get("resolved_value")
            normalized["escalation_semantics"] = f"Executions above ${int(decision['resolved_value']):,} require escalation review."
            normalization_decisions.append("threshold normalized from operator interpretation")
        if decision.get("decision_type") == "timestamp_source_definition":
            temporal = dict(normalized.get("temporal_semantics") or {})
            temporal.setdefault("schema_version", "temporal_authority_semantics.v1")
            temporal["timestamp_source"] = str(decision.get("resolved_value") or "unspecified")
            temporal["expiration_basis"] = _expiration_basis_for_source(temporal["timestamp_source"])
            temporal["runtime_enforced_by"] = "Guard/Cloud"
            normalized["temporal_semantics"] = temporal
            normalization_decisions.append("timestamp source normalized from operator interpretation")
        if decision.get("decision_type") == "state_snapshot_subject_definition":
            snapshot = dict(normalized.get("state_snapshot_semantics") or {})
            snapshot.setdefault("schema_version", "state_posture_snapshot_semantics.v1")
            snapshot["snapshot_required"] = True
            snapshot["snapshot_hash_algorithm"] = "sha256"
            snapshot["snapshot_subject"] = str(decision.get("resolved_value") or "unspecified")
            snapshot["resume_comparison"] = "snapshot_hash_must_match_active_state_hash"
            snapshot["drift_result"] = "continuity_drift_detected"
            snapshot["runtime_enforced_by"] = "Guard/Cloud"
            normalized["state_snapshot_semantics"] = snapshot
            normalization_decisions.append("state snapshot subject normalized from operator interpretation")
    return {
        "schema_version": "governance_semantic_reconciliation.v1",
        "source_id": semantic_extraction["source_id"],
        "source_hash": semantic_extraction["source_hash"],
        "extraction_id": f"extraction-{semantic_extraction['source_hash'].removeprefix('sha256:')[:12]}",
        "what_was_inferred": semantic_extraction.get("candidate_rules", []),
        "ambiguities": ambiguities,
        "operator_interpretation_decisions": decisions,
        "normalization_decisions": normalization_decisions,
        "rejected_candidates": rejected_candidates or [],
        "semantic_conflicts": _semantic_conflicts(semantic_extraction, decisions),
        "unresolved_ambiguities": unresolved,
        "final_normalized_semantic_meaning": normalized if not unresolved else {},
        "interpretation_completeness_posture": "complete" if not unresolved else "operator_required",
        "non_goals": [
            "does not approve authority",
            "does not determine admissibility",
            "does not hide unresolved ambiguity",
        ],
    }


def build_semantic_reconciliation_projection(reconciliation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "semantic_reconciliation_projection.v1",
        "source_id": reconciliation["source_id"],
        "unresolved_ambiguities": reconciliation["unresolved_ambiguities"],
        "operator_reviewed_interpretations": reconciliation["operator_interpretation_decisions"],
        "conflicting_extracted_semantics": reconciliation["semantic_conflicts"],
        "normalization_decisions": reconciliation["normalization_decisions"],
        "interpretation_completeness_posture": reconciliation["interpretation_completeness_posture"],
    }


def _semantic_ambiguity(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "schema_version": "semantic_ambiguity.v1",
        "ambiguity_id": item.get("ambiguity_id") or f"ambiguity-{index:03d}",
        "ambiguity_type": item.get("ambiguity_type") or item.get("type") or "semantic_ambiguity",
        "text": item.get("text") or item.get("summary") or "",
        "summary": item.get("summary") or item.get("text") or "",
        "requires_operator_resolution": bool(item.get("requires_operator_resolution", True)),
    }


def _semantic_conflicts(extraction: dict[str, Any], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts = []
    candidate = extraction.get("candidate_authority") or {}
    for decision in decisions:
        if decision.get("decision_type") != "threshold_definition":
            continue
        extracted = candidate.get("escalation_threshold")
        resolved = decision.get("resolved_value")
        if extracted not in (None, "", resolved):
            conflicts.append(
                {
                    "schema_version": "semantic_conflict.v1",
                    "conflict_id": f"conflict-{len(conflicts) + 1:03d}",
                    "conflict_type": "threshold_conflict",
                    "extracted_value": extracted,
                    "resolved_value": resolved,
                    "requires_operator_resolution": True,
                    "summary": "Extracted threshold differs from operator interpretation decision.",
                }
            )
    return conflicts


def _expiration_basis_for_source(timestamp_source: str) -> str:
    return {
        "execution_payload": "signed_execution_time",
        "signed_oracle": "signed_oracle_time",
        "block_timestamp": "block_timestamp",
        "cloud_attested_time": "cloud_attested_time",
    }.get(timestamp_source, "unspecified")
