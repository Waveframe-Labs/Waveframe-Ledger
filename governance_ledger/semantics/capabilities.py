"""Action-level governance capability semantics."""

from __future__ import annotations

import re
from typing import Any


def build_governance_capabilities(
    *,
    candidate_authority: dict[str, Any],
    candidate_rules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic action-level capability semantics from extracted authority meaning."""
    rules = candidate_rules or []
    capabilities = []
    governed_action = str(candidate_authority.get("governed_action") or "governed execution")
    primary_action = _slug(governed_action)
    capabilities.append(
        _capability(
            capability_id=primary_action,
            action=governed_action,
            action_type="governed_action",
            requirements=_primary_requirements(candidate_authority, rules),
            continuity_semantics=_continuity_semantics(candidate_authority),
            evidence_requirements=_evidence_requirements(rules),
            execution_constraints=_execution_constraints(candidate_authority),
            identity_requirements=_identity_requirements(candidate_authority),
        )
    )

    if candidate_authority.get("approver_role") or candidate_authority.get("approval_count"):
        capabilities.append(
            _capability(
                capability_id=f"approve_{primary_action}",
                action=f"approve {governed_action}",
                action_type="approval_action",
                requirements=_approval_requirements(candidate_authority),
                continuity_semantics={},
                evidence_requirements=_approval_evidence_requirements(rules),
                execution_constraints={},
                identity_requirements=_identity_requirements(candidate_authority),
            )
        )

    if candidate_authority.get("continuity_revalidation") or candidate_authority.get("state_snapshot_semantics"):
        capabilities.append(
            _capability(
                capability_id=f"resume_{primary_action}",
                action=f"resume {governed_action}",
                action_type="resume_action",
                requirements=[
                    _requirement(
                        requirement_type="continuity_revalidation",
                        summary="Resumed execution requires current governance posture validation.",
                        fields={"resume_requires_revalidation": True},
                    )
                ],
                continuity_semantics=_continuity_semantics(candidate_authority),
                evidence_requirements=_replay_evidence_requirements(rules),
                execution_constraints=_execution_constraints(candidate_authority),
                identity_requirements=_identity_requirements(candidate_authority),
            )
        )

    delegation_posture = (
        (candidate_authority.get("approval_chain_semantics") or {}).get("delegation_posture")
        or (candidate_authority.get("authority_role_binding") or {}).get("delegation_posture")
    )
    if delegation_posture and delegation_posture != "not_allowed":
        capabilities.append(
            _capability(
                capability_id="delegate_authority",
                action="delegate authority",
                action_type="delegation_action",
                requirements=[
                    _requirement(
                        requirement_type="delegation_boundary",
                        summary="Delegated authority requires explicit delegation boundary semantics.",
                        fields={"delegation_posture": delegation_posture},
                    )
                ],
                continuity_semantics={},
                evidence_requirements=[
                    _evidence_requirement(
                        evidence_type="attested_delegation_evidence",
                        summary="Delegation must retain attested evidence when authority is delegated.",
                    )
                ],
                execution_constraints={},
                identity_requirements=_identity_requirements(candidate_authority),
            )
        )

    return capabilities


def _capability(
    *,
    capability_id: str,
    action: str,
    action_type: str,
    requirements: list[dict[str, Any]],
    continuity_semantics: dict[str, Any],
    evidence_requirements: list[dict[str, Any]],
    execution_constraints: dict[str, Any],
    identity_requirements: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "governance_capability.v1",
        "capability_id": capability_id,
        "action": action,
        "action_type": action_type,
        "requirements": requirements,
        "continuity_semantics": continuity_semantics,
        "evidence_requirements": evidence_requirements,
        "execution_constraints": execution_constraints,
        "identity_requirements": identity_requirements,
        "non_goals": [
            "does not determine admissibility",
            "does not execute the action",
            "does not bypass Guard",
        ],
    }


def _primary_requirements(candidate: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requirements = []
    threshold = candidate.get("escalation_threshold")
    role = candidate.get("approver_role")
    count = candidate.get("approval_count")
    if threshold:
        requirements.append(
            _requirement(
                requirement_type="escalation_threshold",
                summary=f"Executions above ${int(threshold):,} require escalation review.",
                fields={"threshold": threshold, "operator": "greater_than"},
            )
        )
    if role or count:
        requirements.append(
            _requirement(
                requirement_type="approval_requirement",
                summary="Execution requires approval before completion.",
                fields={"approver_role": role, "approval_count": count},
            )
        )
    for rule in rules:
        if rule.get("rule_type") == "required_evidence":
            requirements.append(
                _requirement(
                    requirement_type="evidence_requirement",
                    summary=rule.get("summary") or "Execution requires evidence.",
                    fields=rule.get("fields") or {},
                )
            )
    return requirements


def _approval_requirements(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    approval = candidate.get("approval_chain_semantics") or {}
    role = candidate.get("approver_role")
    count = candidate.get("approval_count")
    requirements = [
        _requirement(
            requirement_type="approval_responsibility",
            summary="Approval action is bound to the responsible governance role.",
            fields={"approver_role": role, "approval_count": count},
        )
    ]
    if approval.get("self_approval_prohibited"):
        requirements.append(
            _requirement(
                requirement_type="independence_constraint",
                summary="Originator and approver must be independent actors.",
                fields={"self_approval_prohibited": True},
            )
        )
    return requirements


def _continuity_semantics(candidate: dict[str, Any]) -> dict[str, Any]:
    snapshot = candidate.get("state_snapshot_semantics") or {}
    if not (candidate.get("continuity_revalidation") or candidate.get("revocation_invalidates_resume") or snapshot):
        return {}
    return {
        "schema_version": "capability_continuity_semantics.v1",
        "revalidation_required": bool(candidate.get("continuity_revalidation")),
        "revocation_invalidates_resume": bool(candidate.get("revocation_invalidates_resume")),
        "state_snapshot_semantics": snapshot,
    }


def _evidence_requirements(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for rule in rules:
        if rule.get("rule_type") != "required_evidence":
            continue
        evidence_type = (rule.get("fields") or {}).get("evidence_term") or "governance_evidence"
        evidence.append(_evidence_requirement(evidence_type=evidence_type, summary=rule.get("summary") or "Evidence is required."))
    return evidence


def _approval_evidence_requirements(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = _evidence_requirements(rules)
    if not any(item["evidence_type"] == "approval_evidence" for item in evidence):
        evidence.append(
            _evidence_requirement(
                evidence_type="approval_evidence",
                summary="Approval action should retain approval evidence.",
            )
        )
    return evidence


def _replay_evidence_requirements(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = _evidence_requirements(rules)
    if not any(item["evidence_type"] == "replay" for item in evidence):
        evidence.append(
            _evidence_requirement(
                evidence_type="replay_evidence",
                summary="Resume action requires replay evidence binding.",
            )
        )
    return evidence


def _execution_constraints(candidate: dict[str, Any]) -> dict[str, Any]:
    execution = candidate.get("execution_context_semantics") or {}
    temporal = candidate.get("temporal_semantics") or {}
    if not (execution or temporal):
        return {}
    return {
        "schema_version": "capability_execution_constraint.v1",
        "execution_context_semantics": execution,
        "temporal_semantics": temporal,
        "runtime_enforced_by": "Guard/Cloud",
    }


def _identity_requirements(candidate: dict[str, Any]) -> dict[str, Any]:
    actor = candidate.get("governance_actor") or {}
    binding = candidate.get("authority_role_binding") or {}
    approval = candidate.get("approval_chain_semantics") or {}
    identity = candidate.get("identity_continuity_semantics") or {}
    if not (actor or binding or approval or identity):
        return {}
    return {
        "schema_version": "capability_identity_requirement.v1",
        "governance_actor": actor,
        "authority_role_binding": binding,
        "approval_chain_semantics": approval,
        "identity_continuity_semantics": identity,
    }


def _requirement(*, requirement_type: str, summary: str, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "capability_requirement.v1",
        "requirement_type": requirement_type,
        "summary": summary,
        "fields": fields,
    }


def _evidence_requirement(*, evidence_type: str, summary: str) -> dict[str, Any]:
    return {
        "schema_version": "capability_evidence_requirement.v1",
        "evidence_type": evidence_type,
        "summary": summary,
    }


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return text or "governed_execution"
