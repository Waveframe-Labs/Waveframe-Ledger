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
    field: str | None = None,
    selected_interpretation: Any | None = None,
    rejected_interpretations: list[Any] | None = None,
    operator: str = "local-ledger-ui",
    timestamp: str | None = None,
    justification: str | None = None,
) -> dict[str, Any]:
    selected = resolved_value if selected_interpretation is None else selected_interpretation
    normalized_field = field or _field_for_decision_type(decision_type)
    normalized_justification = justification or rationale
    stable_payload = {
        "decision_type": decision_type,
        "field": normalized_field,
        "selected_interpretation": selected,
        "rejected_interpretations": rejected_interpretations or [],
        "operator": operator,
        "justification": normalized_justification,
    }
    decision_hash = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "semantic_interpretation_decision.v1",
        "decision_id": "decision-" + decision_hash[:12],
        "field": normalized_field,
        "selected_interpretation": selected,
        "rejected_interpretations": rejected_interpretations or [],
        "decision_type": decision_type,
        "ambiguity_id": ambiguity_id,
        "resolved_value": resolved_value,
        "rationale": rationale,
        "operator": operator,
        "timestamp": timestamp or _stable_decision_time(decision_hash),
        "justification": normalized_justification,
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


def build_semantic_stability_projection(
    *,
    previous_extraction: dict[str, Any] | None = None,
    current_extraction: dict[str, Any],
    previous_reconciliation: dict[str, Any] | None = None,
    current_reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare semantic interpretation lineage across extraction or reconciliation runs."""
    observations: list[dict[str, Any]] = []
    previous_signature = _extraction_signature(previous_extraction) if previous_extraction else None
    current_signature = _extraction_signature(current_extraction)
    same_source = bool(previous_extraction and previous_extraction.get("source_hash") == current_extraction.get("source_hash"))
    extraction_method_changed = bool(
        previous_extraction
        and previous_extraction.get("extraction_method") != current_extraction.get("extraction_method")
    )
    semantic_meaning_changed = bool(
        previous_signature
        and current_signature
        and previous_signature["semantic_hash"] != current_signature["semantic_hash"]
    )
    decision_changes = _decision_changes(previous_reconciliation, current_reconciliation)

    if same_source and semantic_meaning_changed:
        observations.append(
            _stability_observation(
                observation_type="same_source_semantic_drift",
                severity="warning",
                summary="The same governance source produced different extracted semantic meaning.",
            )
        )
    if extraction_method_changed:
        observations.append(
            _stability_observation(
                observation_type="extraction_method_changed",
                severity="info",
                summary="Extraction method changed between interpretation runs.",
            )
        )
    for change in decision_changes:
        observations.append(
            _stability_observation(
                observation_type="operator_interpretation_changed",
                severity="warning",
                summary=f"Operator interpretation for {change['field']} changed.",
                details=change,
            )
        )

    return {
        "schema_version": "semantic_stability_projection.v1",
        "source_hash": current_extraction["source_hash"],
        "previous_source_hash": previous_extraction.get("source_hash") if previous_extraction else None,
        "same_source": same_source,
        "previous_extraction_signature": previous_signature,
        "current_extraction_signature": current_signature,
        "extraction_method_changed": extraction_method_changed,
        "semantic_meaning_changed": semantic_meaning_changed,
        "interpretation_decision_changes": decision_changes,
        "stability_observations": observations,
        "stability_posture": _stability_posture(observations),
        "non_goals": [
            "does not approve authority",
            "does not determine admissibility",
            "does not infer operator intent beyond recorded decisions",
        ],
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


def _field_for_decision_type(decision_type: str) -> str:
    return {
        "threshold_definition": "escalation_threshold",
        "timestamp_source_definition": "timestamp_source",
        "state_snapshot_subject_definition": "state_snapshot_subject",
    }.get(decision_type, decision_type)


def _stable_decision_time(decision_hash: str) -> str:
    seconds = int(decision_hash[:8], 16) % (365 * 24 * 60 * 60)
    return f"2026-01-01T00:00:{seconds % 60:02d}Z"


def _extraction_signature(extraction: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extraction:
        return None
    semantic_payload = {
        "candidate_authority": extraction.get("candidate_authority") or {},
        "candidate_rules": extraction.get("candidate_rules") or [],
        "ambiguities": extraction.get("ambiguities") or [],
        "missing_information": extraction.get("missing_information") or [],
        "semantic_provenance": extraction.get("semantic_provenance") or [],
    }
    return {
        "source_hash": extraction.get("source_hash"),
        "extraction_method": extraction.get("extraction_method"),
        "semantic_hash": _hash_payload(semantic_payload),
    }


def _decision_changes(
    previous_reconciliation: dict[str, Any] | None,
    current_reconciliation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    previous = _decisions_by_field(previous_reconciliation)
    current = _decisions_by_field(current_reconciliation)
    changes = []
    for field in sorted(set(previous) | set(current)):
        previous_value = previous.get(field, {}).get("selected_interpretation")
        current_value = current.get(field, {}).get("selected_interpretation")
        if previous_value == current_value:
            continue
        changes.append(
            {
                "field": field,
                "previous_interpretation": previous_value,
                "current_interpretation": current_value,
                "previous_decision_id": previous.get(field, {}).get("decision_id"),
                "current_decision_id": current.get(field, {}).get("decision_id"),
            }
        )
    return changes


def _decisions_by_field(reconciliation: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not reconciliation:
        return {}
    return {
        decision.get("field") or decision.get("decision_type"): decision
        for decision in reconciliation.get("operator_interpretation_decisions", [])
    }


def _stability_observation(
    *,
    observation_type: str,
    severity: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "observation_type": observation_type,
        "severity": severity,
        "summary": summary,
        "details": details or {},
    }


def _stability_posture(observations: list[dict[str, Any]]) -> str:
    if any(item["severity"] == "warning" for item in observations):
        return "semantic_drift_detected"
    if observations:
        return "semantic_stability_review"
    return "stable"


def _hash_payload(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _expiration_basis_for_source(timestamp_source: str) -> str:
    return {
        "execution_payload": "signed_execution_time",
        "signed_oracle": "signed_oracle_time",
        "block_timestamp": "block_timestamp",
        "cloud_attested_time": "cloud_attested_time",
    }.get(timestamp_source, "unspecified")
