"""Runtime-facing execution projections from compiled authority contracts."""

from __future__ import annotations

import copy
from typing import Any


EXECUTION_REQUIREMENT_PROJECTION_V1 = "execution_requirement_projection.v1"
EXECUTION_ADMISSIBILITY_PROJECTION_V1 = "execution_admissibility_projection.v1"
RUNTIME_CONSEQUENCE_PROJECTION_V1 = "runtime_consequence_projection.v1"
GUARD_ENFORCEMENT_PROJECTION_V1 = "guard_enforcement_projection.v1"
AUTHORITY_EXECUTION_PROJECTION_V1 = "authority_execution_projection.v1"

_NON_GOALS = [
    "does_not_call_guard",
    "does_not_call_cloud",
    "does_not_execute_policy",
    "does_not_evaluate_runtime_admissibility",
    "does_not_block_execution",
]


def build_authority_execution_projection(
    compiled_authority_contract: dict[str, Any],
) -> dict[str, Any]:
    """Build the full read-only execution projection family from a compiled contract."""
    _require_compiled_contract(compiled_authority_contract)
    requirements = build_execution_requirement_projection(compiled_authority_contract)
    admissibility = build_execution_admissibility_projection(compiled_authority_contract)
    consequences = build_runtime_consequence_projection(compiled_authority_contract)
    guard = build_guard_enforcement_projection(compiled_authority_contract)
    return {
        "schema_version": AUTHORITY_EXECUTION_PROJECTION_V1,
        "authority_ref": compiled_authority_contract.get("authority_ref"),
        "compiled_contract_hash": compiled_authority_contract.get("contract_hash"),
        "execution_requirement_projection": requirements,
        "execution_admissibility_projection": admissibility,
        "runtime_consequence_projection": consequences,
        "guard_enforcement_projection": guard,
        "deterministic_guarantees": [
            "Derived only from compiled_authority_contract.v1.",
            "Does not invoke Guard, Cloud, simulation, runtime evaluation, or admissibility execution.",
            "Same compiled authority contract input produces the same authority execution projection.",
        ],
        "non_goals": list(_NON_GOALS),
    }


def build_execution_requirement_projection(
    compiled_authority_contract: dict[str, Any],
) -> dict[str, Any]:
    """Project deterministic runtime requirements from compiled_authority_contract.v1."""
    _require_compiled_contract(compiled_authority_contract)
    approval = compiled_authority_contract.get("approval_requirements") or {}
    continuity = compiled_authority_contract.get("continuity_requirements") or {}
    replay = compiled_authority_contract.get("replay_obligations") or []
    delegation = compiled_authority_contract.get("delegation_requirements") or {}
    execution = compiled_authority_contract.get("execution_admissibility_semantics") or {}
    constraints = _capability_constraints(compiled_authority_contract)
    return {
        "schema_version": EXECUTION_REQUIREMENT_PROJECTION_V1,
        "authority_ref": compiled_authority_contract.get("authority_ref"),
        "compiled_contract_hash": compiled_authority_contract.get("contract_hash"),
        "required_approvals": _int_or_zero(approval.get("minimum_approvals")),
        "independent_approval_required": bool(approval.get("independent")),
        "required_roles": _string_list(approval.get("required_roles")),
        "self_approval_prohibited": bool(approval.get("self_approval_prohibited")),
        "attestation_required": bool(approval.get("attestation_required")),
        "human_in_loop_required": bool(approval.get("human_in_loop_required")),
        "replay_evidence_required": _requires_replay_evidence(replay, execution),
        "continuity_snapshot_required": bool(continuity.get("state_snapshot_required")),
        "resume_validation_required": bool(
            continuity.get("revalidation_required")
            or continuity.get("revocation_invalidates_resume")
            or continuity.get("state_snapshot_required")
        ),
        "delegation_expiry": delegation.get("validity_window"),
        "delegation_evidence_required": bool(delegation.get("attested_delegation_evidence_required")),
        "temporal_validation_required": bool((execution.get("temporal_validation") or {}).get("validity_window")),
        "capability_requirements": constraints,
        "runtime_enforced_by": "Guard/Cloud",
        "non_goals": list(_NON_GOALS),
    }


def build_execution_admissibility_projection(
    compiled_authority_contract: dict[str, Any],
) -> dict[str, Any]:
    """Describe what runtime evidence would be required without evaluating it."""
    requirements = build_execution_requirement_projection(compiled_authority_contract)
    required_conditions: list[str] = []
    if requirements["replay_evidence_required"]:
        required_conditions.append("replay_evidence")
    if requirements["continuity_snapshot_required"]:
        required_conditions.append("continuity_snapshot")
    if requirements["resume_validation_required"]:
        required_conditions.append("continuity_validation")
    if requirements["required_approvals"]:
        required_conditions.append("approval_evidence")
    if requirements["independent_approval_required"]:
        required_conditions.append("independent_approval")
    if requirements["attestation_required"]:
        required_conditions.append("attested_acknowledgment")
    if requirements["delegation_evidence_required"]:
        required_conditions.append("delegation_evidence")
    if requirements["temporal_validation_required"]:
        required_conditions.append("temporal_validation")
    required_conditions.append("active_authority_lineage")
    return {
        "schema_version": EXECUTION_ADMISSIBILITY_PROJECTION_V1,
        "authority_ref": requirements["authority_ref"],
        "compiled_contract_hash": requirements["compiled_contract_hash"],
        "projection_posture": "requirements_projected" if required_conditions else "no_requirements_projected",
        "required_runtime_conditions": _unique(required_conditions),
        "operator_summary": _operator_summary(required_conditions),
        "runtime_enforced_by": "Guard/Cloud",
        "non_goals": list(_NON_GOALS),
    }


def build_runtime_consequence_projection(
    compiled_authority_contract: dict[str, Any],
) -> dict[str, Any]:
    """Project runtime consequences implied by compiled requirements."""
    requirements = build_execution_requirement_projection(compiled_authority_contract)
    consequences: list[dict[str, Any]] = []
    if requirements["resume_validation_required"]:
        consequences.append(_consequence("resumed_workflows_require_revalidation", "Resumed workflows require current authority and continuity validation."))
    if requirements["continuity_snapshot_required"]:
        consequences.append(_consequence("continuity_snapshot_required", "Runtime evidence must include a governance state snapshot for resume comparison."))
    if requirements["independent_approval_required"]:
        consequences.append(_consequence("prior_approval_evidence_may_be_stale", "Approval evidence must prove independent approval boundaries before execution can rely on it."))
    if requirements["replay_evidence_required"]:
        consequences.append(_consequence("replay_evidence_required", "Execution evidence must bind to replay obligations and authority lineage."))
    if requirements["delegation_expiry"]:
        consequences.append(_consequence("delegated_authority_expiry_enforced", f"Delegated authority expires at {requirements['delegation_expiry']} and requires renewal evidence."))
    if requirements["attestation_required"]:
        consequences.append(_consequence("attested_acknowledgment_required", "Actor or reviewer attestation is required before runtime authority can rely on approval posture."))
    return {
        "schema_version": RUNTIME_CONSEQUENCE_PROJECTION_V1,
        "authority_ref": requirements["authority_ref"],
        "compiled_contract_hash": requirements["compiled_contract_hash"],
        "runtime_consequences": consequences,
        "what_runtime_would_require": [item["summary"] for item in consequences],
        "runtime_enforced_by": "Guard/Cloud",
        "non_goals": list(_NON_GOALS),
    }


def build_guard_enforcement_projection(
    compiled_authority_contract: dict[str, Any],
) -> dict[str, Any]:
    """Return the exact Guard-consumable subset of compiled authority data."""
    requirements = build_execution_requirement_projection(compiled_authority_contract)
    compiled = compiled_authority_contract
    return {
        "schema_version": GUARD_ENFORCEMENT_PROJECTION_V1,
        "authority_ref": compiled.get("authority_ref"),
        "compiled_contract_hash": compiled.get("contract_hash"),
        "admissibility_requirements": {
            "required_approvals": requirements["required_approvals"],
            "independent_approval_required": requirements["independent_approval_required"],
            "required_roles": requirements["required_roles"],
            "self_approval_prohibited": requirements["self_approval_prohibited"],
            "attestation_required": requirements["attestation_required"],
            "human_in_loop_required": requirements["human_in_loop_required"],
        },
        "replay_obligations": copy.deepcopy(compiled.get("replay_obligations") or []),
        "approval_constraints": copy.deepcopy(compiled.get("approval_requirements") or {}),
        "continuity_rules": copy.deepcopy(compiled.get("continuity_requirements") or {}),
        "execution_constraints": {
            "execution_admissibility_semantics": copy.deepcopy(compiled.get("execution_admissibility_semantics") or {}),
            "capability_constraints": [
                {
                    "capability_id": capability.get("capability_id"),
                    "action": capability.get("action"),
                    "admissibility_constraints": copy.deepcopy(capability.get("admissibility_constraints") or []),
                    "execution_constraints": copy.deepcopy(capability.get("execution_constraints") or {}),
                }
                for capability in compiled.get("capability_scope") or []
            ],
        },
        "excluded_from_guard_consumption": [
            "reconciliation_history",
            "extraction_provenance",
            "semantic_ambiguity",
            "ui_state",
            "registry_state",
        ],
        "non_goals": list(_NON_GOALS),
    }


def _require_compiled_contract(compiled: dict[str, Any]) -> None:
    if compiled.get("schema_version") != "compiled_authority_contract.v1":
        raise ValueError("Execution projections require compiled_authority_contract.v1.")


def _capability_constraints(compiled: dict[str, Any]) -> list[dict[str, Any]]:
    constraints = []
    for capability in compiled.get("capability_scope") or []:
        constraints.append(
            {
                "capability_id": capability.get("capability_id"),
                "action": capability.get("action"),
                "admissibility_constraints": copy.deepcopy(capability.get("admissibility_constraints") or []),
                "replay_obligations": copy.deepcopy(capability.get("replay_obligations") or []),
                "continuity_requirements": copy.deepcopy(capability.get("continuity_requirements") or {}),
            }
        )
    return constraints


def _requires_replay_evidence(replay: list[dict[str, Any]], execution: dict[str, Any]) -> bool:
    if any(item.get("required") for item in replay if isinstance(item, dict)):
        return True
    context = execution.get("execution_context") if isinstance(execution.get("execution_context"), dict) else {}
    return bool(context.get("requires_replay_evidence"))


def _operator_summary(required_conditions: list[str]) -> list[str]:
    labels = {
        "replay_evidence": "Execution would require replay evidence.",
        "continuity_snapshot": "Execution would require a continuity snapshot.",
        "continuity_validation": "Execution would require continuity validation.",
        "approval_evidence": "Execution would require approval evidence.",
        "independent_approval": "Execution would require independent approval.",
        "attested_acknowledgment": "Execution would require attested acknowledgment.",
        "delegation_evidence": "Execution would require delegation evidence.",
        "temporal_validation": "Execution would require temporal validation.",
        "active_authority_lineage": "Execution would require active authority lineage.",
    }
    return [labels[item] for item in _unique(required_conditions)]


def _consequence(consequence_type: str, summary: str, severity: str = "warning") -> dict[str, Any]:
    return {
        "consequence_type": consequence_type,
        "severity": severity,
        "summary": summary,
    }


def _int_or_zero(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "")]
    return [str(value)]


def _unique(items: list[Any]) -> list[Any]:
    result = []
    seen = set()
    for item in items:
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
