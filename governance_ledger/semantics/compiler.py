"""Compile committed governance semantics into deterministic authority contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

SEMANTIC_COMMIT_BUNDLE_SCHEMA_VERSION = "semantic_commit_bundle.v1"
COMPILED_AUTHORITY_CONTRACT_SCHEMA_VERSION = "compiled_authority_contract.v1"

_NON_GOALS = [
    "does_not_interpret_raw_policy_text",
    "does_not_compile_provisional_extraction",
    "does_not_resolve_ambiguities",
    "does_not_call_guard",
    "does_not_determine_runtime_admissibility",
]


def build_semantic_commit_bundle(
    reconciliation: dict[str, Any],
    *,
    committed_by: str = "governance-ledger",
    committed_at: str | None = None,
) -> dict[str, Any]:
    """Freeze completed semantic reconciliation as compiler input."""
    _require_complete_reconciliation(reconciliation)
    committed_semantics = copy.deepcopy(reconciliation.get("final_normalized_semantic_meaning") or {})
    if not committed_semantics:
        raise ValueError("Semantic commit bundle requires final normalized semantic meaning.")
    _reject_raw_policy_text(committed_semantics)
    semantic_hash = _hash_payload(committed_semantics)
    decisions = copy.deepcopy(reconciliation.get("operator_interpretation_decisions") or [])
    payload = {
        "schema_version": SEMANTIC_COMMIT_BUNDLE_SCHEMA_VERSION,
        "source_id": reconciliation.get("source_id"),
        "source_hash": reconciliation.get("source_hash"),
        "extraction_id": reconciliation.get("extraction_id"),
        "semantic_commit_id": f"semantic-commit-{semantic_hash.removeprefix('sha256:')[:12]}",
        "semantic_commit_hash": semantic_hash,
        "committed_at": committed_at or _stable_time(semantic_hash),
        "committed_by": committed_by,
        "committed_capabilities": copy.deepcopy(committed_semantics.get("capabilities") or []),
        "resolved_interpretations": decisions,
        "approved_constraints": _approved_constraints(committed_semantics),
        "lifecycle_posture": _lifecycle_posture(committed_semantics),
        "continuity_posture": _continuity_posture(committed_semantics),
        "identity_bindings": _identity_bindings(committed_semantics),
        "execution_admissibility_semantics": _execution_admissibility_semantics(committed_semantics),
        "replay_obligations": _replay_obligations(committed_semantics),
        "committed_semantic_meaning": committed_semantics,
        "non_goals": list(_NON_GOALS),
    }
    payload["bundle_hash"] = _hash_payload(payload)
    return payload


def compile_semantic_commit_bundle(commit_bundle: dict[str, Any]) -> dict[str, Any]:
    """Compile semantic_commit_bundle.v1 into compiled_authority_contract.v1."""
    if commit_bundle.get("schema_version") != SEMANTIC_COMMIT_BUNDLE_SCHEMA_VERSION:
        raise ValueError("Compiler input must be semantic_commit_bundle.v1.")
    _reject_raw_policy_text(commit_bundle)
    committed = copy.deepcopy(commit_bundle.get("committed_semantic_meaning") or {})
    if not committed:
        raise ValueError("Compiler input requires committed semantic meaning.")
    _reject_raw_policy_text(committed)

    contract_id = str(committed.get("contract_id") or _slug(committed.get("protected_system") or "authority")).strip()
    contract_version = str(committed.get("contract_version") or "0.1.0").strip()
    authority_ref = f"{contract_id}@{contract_version}"
    compiled_capabilities = [
        _compile_capability(capability, committed)
        for capability in (commit_bundle.get("committed_capabilities") or committed.get("capabilities") or [])
    ]
    if not compiled_capabilities:
        compiled_capabilities = [_compile_capability(_fallback_capability(committed), committed)]

    compiled = {
        "schema_version": COMPILED_AUTHORITY_CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "contract_version": contract_version,
        "authority_ref": authority_ref,
        "compiled_from": {
            "schema_version": SEMANTIC_COMMIT_BUNDLE_SCHEMA_VERSION,
            "semantic_commit_id": commit_bundle.get("semantic_commit_id"),
            "semantic_commit_hash": commit_bundle.get("semantic_commit_hash"),
            "source_hash": commit_bundle.get("source_hash"),
            "resolved_interpretation_count": len(commit_bundle.get("resolved_interpretations") or []),
        },
        "governed_targets": _string_list(committed.get("governed_targets") or committed.get("governed_action_targets") or [committed.get("protected_system")]),
        "governed_operations": _string_list(committed.get("governed_operations") or [committed.get("governed_action")]),
        "mutation_classes": _string_list(committed.get("mutation_classes")),
        "capability_scope": compiled_capabilities,
        "approval_requirements": _compile_approval_requirements(committed),
        "continuity_requirements": _compile_continuity_requirements(committed),
        "replay_obligations": _compile_replay_obligations(committed, compiled_capabilities),
        "lifecycle_requirements": _compile_lifecycle_requirements(committed),
        "escalation_requirements": _compile_escalation_requirements(committed),
        "delegation_requirements": _compile_delegation_requirements(committed),
        "identity_bindings": _compile_identity_bindings(committed),
        "execution_admissibility_semantics": _compile_execution_admissibility_semantics(committed),
        "determinism": {
            "input_schema": SEMANTIC_COMMIT_BUNDLE_SCHEMA_VERSION,
            "output_schema": COMPILED_AUTHORITY_CONTRACT_SCHEMA_VERSION,
            "same_input_same_output": True,
            "runtime_enforced_by": "Guard/Cloud",
        },
        "non_goals": list(_NON_GOALS),
    }
    compiled["contract_hash"] = _hash_payload(compiled)
    return compiled


def format_compiled_authority_contract(contract: dict[str, Any]) -> str:
    return "\n".join(
        [
            "[Compiled Authority Contract]",
            "",
            f"Authority: {contract.get('authority_ref', 'unknown')}",
            f"Capabilities: {len(contract.get('capability_scope') or [])}",
            f"Contract hash: {contract.get('contract_hash', 'unavailable')}",
        ]
    )


def _require_complete_reconciliation(reconciliation: dict[str, Any]) -> None:
    if reconciliation.get("schema_version") != "governance_semantic_reconciliation.v1":
        raise ValueError("Semantic commit requires governance_semantic_reconciliation.v1.")
    if reconciliation.get("interpretation_completeness_posture") != "complete":
        raise ValueError("Semantic commit requires complete interpretation reconciliation.")
    if reconciliation.get("unresolved_ambiguities"):
        raise ValueError("Semantic commit cannot include unresolved ambiguities.")
    if reconciliation.get("semantic_conflicts"):
        raise ValueError("Semantic commit cannot include semantic conflicts.")


def _reject_raw_policy_text(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"source_text", "canonical_text", "raw_policy_text", "policy_text", "governance_source"}:
                raise ValueError("Compiler input must not contain raw policy text or governance source artifacts.")
            _reject_raw_policy_text(item)
    elif isinstance(value, list):
        for item in value:
            _reject_raw_policy_text(item)


def _approved_constraints(committed: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval": _compile_approval_requirements(committed),
        "escalation": _compile_escalation_requirements(committed),
        "continuity": _compile_continuity_requirements(committed),
        "execution": _compile_execution_admissibility_semantics(committed),
    }


def _lifecycle_posture(committed: dict[str, Any]) -> dict[str, Any]:
    return {
        "revocation_invalidates_resume": bool(committed.get("revocation_invalidates_resume")),
        "supersession_requires_revalidation": bool(committed.get("continuity_revalidation")),
    }


def _continuity_posture(committed: dict[str, Any]) -> dict[str, Any]:
    return _compile_continuity_requirements(committed)


def _identity_bindings(committed: dict[str, Any]) -> dict[str, Any]:
    return _compile_identity_bindings(committed)


def _execution_admissibility_semantics(committed: dict[str, Any]) -> dict[str, Any]:
    return _compile_execution_admissibility_semantics(committed)


def _replay_obligations(committed: dict[str, Any]) -> list[dict[str, Any]]:
    return _compile_replay_obligations(committed, committed.get("capabilities") or [])


def _compile_capability(capability: dict[str, Any], committed: dict[str, Any]) -> dict[str, Any]:
    return {
        "capability_id": capability.get("capability_id") or _slug(capability.get("action") or "governed_execution"),
        "action": capability.get("action") or committed.get("governed_action") or "governed execution",
        "action_type": capability.get("action_type") or "governed_action",
        "approval_requirements": _compile_approval_requirements(committed, capability),
        "escalation_requirements": _compile_escalation_requirements(committed, capability),
        "continuity_requirements": _compile_continuity_requirements(committed, capability),
        "replay_obligations": _compile_replay_obligations(committed, [capability]),
        "identity_requirements": _compile_identity_bindings(committed, capability),
        "execution_constraints": _compile_execution_constraints(committed, capability),
        "admissibility_constraints": _compile_admissibility_constraints(committed, capability),
    }


def _fallback_capability(committed: dict[str, Any]) -> dict[str, Any]:
    action = committed.get("governed_action") or "governed execution"
    return {
        "capability_id": _slug(action),
        "action": action,
        "action_type": "governed_action",
        "requirements": [],
        "continuity_semantics": {},
        "evidence_requirements": [],
        "execution_constraints": {},
        "identity_requirements": {},
    }


def _compile_approval_requirements(committed: dict[str, Any], capability: dict[str, Any] | None = None) -> dict[str, Any]:
    approval = committed.get("approval_chain_semantics") or {}
    identity = (capability or {}).get("identity_requirements") or {}
    capability_approval = identity.get("approval_chain_semantics") if isinstance(identity, dict) else {}
    effective = capability_approval or approval
    roles = _string_list(effective.get("required_roles") or committed.get("approver_roles") or [committed.get("approver_role")])
    count = effective.get("required_approval_count") or committed.get("approval_count")
    return {
        "minimum_approvals": _int_or_none(count),
        "independent": bool(effective.get("independence_required")),
        "required_roles": roles,
        "self_approval_prohibited": bool(effective.get("self_approval_prohibited")),
        "attestation_required": bool(effective.get("attestation_required")),
        "human_in_loop_required": bool(effective.get("human_in_loop_required")),
    }


def _compile_continuity_requirements(committed: dict[str, Any], capability: dict[str, Any] | None = None) -> dict[str, Any]:
    capability_continuity = (capability or {}).get("continuity_semantics") or {}
    snapshot = capability_continuity.get("state_snapshot_semantics") or committed.get("state_snapshot_semantics") or {}
    identity = committed.get("identity_continuity_semantics") or {}
    return {
        "revalidation_required": bool(capability_continuity.get("revalidation_required", committed.get("continuity_revalidation"))),
        "revocation_invalidates_resume": bool(capability_continuity.get("revocation_invalidates_resume", committed.get("revocation_invalidates_resume"))),
        "state_snapshot_required": bool(snapshot.get("snapshot_required")),
        "snapshot_hash_algorithm": snapshot.get("snapshot_hash_algorithm") or ("sha256" if snapshot else None),
        "snapshot_subject": snapshot.get("snapshot_subject"),
        "resume_comparison": snapshot.get("resume_comparison"),
        "drift_result": snapshot.get("drift_result"),
        "identity_continuity_required": bool(identity.get("identity_continuity_required")),
    }


def _compile_replay_obligations(committed: dict[str, Any], capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    obligations: dict[str, dict[str, Any]] = {}
    execution = committed.get("execution_context_semantics") or {}
    if execution.get("requires_replay_evidence"):
        obligations["replay_evidence"] = {
            "obligation_type": "replay_evidence",
            "required": True,
            "binding": "authority_lineage",
        }
    for capability in capabilities:
        for evidence in capability.get("evidence_requirements") or []:
            evidence_type = evidence.get("evidence_type") or "governance_evidence"
            obligations[evidence_type] = {
                "obligation_type": evidence_type,
                "required": True,
                "binding": "capability_execution",
            }
    if committed.get("state_snapshot_semantics"):
        obligations["state_snapshot_evidence"] = {
            "obligation_type": "state_snapshot_evidence",
            "required": True,
            "binding": "active_governance_state",
        }
    return [obligations[key] for key in sorted(obligations)]


def _compile_lifecycle_requirements(committed: dict[str, Any]) -> dict[str, Any]:
    return {
        "revoked_authority_effect": "invalidate_resumed_execution" if committed.get("revocation_invalidates_resume") else "review_required",
        "supersession_effect": "revalidate_resumed_execution" if committed.get("continuity_revalidation") else "preserve_prior_execution_lineage",
        "runtime_enforced_by": "Guard/Cloud",
    }


def _compile_escalation_requirements(committed: dict[str, Any], capability: dict[str, Any] | None = None) -> dict[str, Any]:
    threshold = committed.get("escalation_threshold")
    for requirement in (capability or {}).get("requirements") or []:
        if requirement.get("requirement_type") == "escalation_threshold":
            threshold = (requirement.get("fields") or {}).get("threshold", threshold)
    return {
        "threshold": {
            "field": "amount",
            "operator": "greater_than",
            "value": _int_or_none(threshold),
        }
        if threshold not in (None, "")
        else None,
        "review_role": committed.get("approver_role") or "escalation_review",
        "escalation_semantics": committed.get("escalation_semantics") or "",
    }


def _compile_delegation_requirements(committed: dict[str, Any]) -> dict[str, Any]:
    approval = committed.get("approval_chain_semantics") or {}
    role = committed.get("authority_role_binding") or {}
    emergency = committed.get("emergency_delegation_semantics") or {}
    posture = emergency.get("delegation_posture") or approval.get("delegation_posture") or role.get("delegation_posture") or "not_allowed"
    return {
        "delegation_posture": posture,
        "delegation_allowed": posture not in {"not_allowed", "ambiguous"},
        "validity_window": emergency.get("validity_window"),
        "renewal_requirement": emergency.get("renewal_requirement"),
        "attested_delegation_evidence_required": posture not in {"not_allowed", "ambiguous"},
    }


def _compile_identity_bindings(committed: dict[str, Any], capability: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = (capability or {}).get("identity_requirements") or {}
    actor = identity.get("governance_actor") or committed.get("governance_actor") or {}
    binding = identity.get("authority_role_binding") or committed.get("authority_role_binding") or {}
    approval = identity.get("approval_chain_semantics") or committed.get("approval_chain_semantics") or {}
    continuity = identity.get("identity_continuity_semantics") or committed.get("identity_continuity_semantics") or {}
    return {
        "governance_actor": actor,
        "authority_role_binding": binding,
        "approval_chain_semantics": approval,
        "identity_continuity_semantics": continuity,
    }


def _compile_execution_admissibility_semantics(committed: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_context": committed.get("execution_context_semantics") or {},
        "temporal_validation": committed.get("temporal_semantics") or {},
        "runtime_enforced_by": "Guard/Cloud",
        "ledger_boundary": "models deterministic runtime representation only",
    }


def _compile_execution_constraints(committed: dict[str, Any], capability: dict[str, Any]) -> dict[str, Any]:
    constraints = capability.get("execution_constraints") or {}
    return {
        "execution_context_semantics": constraints.get("execution_context_semantics") or committed.get("execution_context_semantics") or {},
        "temporal_semantics": constraints.get("temporal_semantics") or committed.get("temporal_semantics") or {},
        "runtime_enforced_by": "Guard/Cloud",
    }


def _compile_admissibility_constraints(committed: dict[str, Any], capability: dict[str, Any]) -> list[dict[str, Any]]:
    constraints = []
    approval = _compile_approval_requirements(committed, capability)
    if approval["minimum_approvals"] or approval["required_roles"]:
        constraints.append({"constraint_type": "approval_requirements", "fields": approval})
    escalation = _compile_escalation_requirements(committed, capability)
    if escalation.get("threshold"):
        constraints.append({"constraint_type": "escalation_threshold", "fields": escalation})
    continuity = _compile_continuity_requirements(committed, capability)
    if any(value for value in continuity.values()):
        constraints.append({"constraint_type": "continuity_requirements", "fields": continuity})
    return constraints


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = re.split(r"[,;]", value)
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    return sorted({str(item).strip() for item in values if str(item or "").strip()})


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _hash_payload(payload: Any) -> str:
    canonical = json.dumps(
        _without_hashes(payload),
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _without_hashes(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_hashes(item)
            for key, item in value.items()
            if key not in {"contract_hash", "bundle_hash"}
        }
    if isinstance(value, list):
        return [_without_hashes(item) for item in value]
    return value


def _stable_time(value_hash: str) -> str:
    seconds = int(value_hash.removeprefix("sha256:")[:8], 16) % (365 * 24 * 60 * 60)
    day = seconds // 86400 + 1
    hour = seconds % 86400 // 3600
    minute = seconds % 3600 // 60
    second = seconds % 60
    month = min(12, (day - 1) // 31 + 1)
    month_day = ((day - 1) % 28) + 1
    return f"2026-{month:02d}-{month_day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "authority"
