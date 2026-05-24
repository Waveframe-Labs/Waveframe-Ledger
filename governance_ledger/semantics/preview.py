"""Deterministic governance impact preview derivation.

This module derives semantic operator-facing meaning from structured authority
contracts. It must not invoke Guard, replay, or runtime admissibility checks.
"""

from __future__ import annotations

import copy
from typing import Any


def build_governance_impact_preview(authority_contract: dict[str, Any]) -> dict[str, Any]:
    """Return governance_impact_preview.v1 for an authority contract."""
    contract = copy.deepcopy(authority_contract)
    contract_id = _required_string(contract, "contract_id")
    contract_version = _required_string(contract, "contract_version")
    authority_ref = f"{contract_id}@{contract_version}"
    scope = _scope(contract)
    thresholds = _thresholds(contract)
    required_roles = _required_roles(contract)
    artifact_requirements = _artifact_requirements(contract)
    lifecycle_transitions = _lifecycle_transitions(contract)
    continuity_requirements = _continuity_requirements(contract)

    enforcement_behavior = _enforcement_behavior(thresholds, required_roles, artifact_requirements)
    operational_consequences = _operational_consequences(thresholds, artifact_requirements)
    lifecycle_implications = _lifecycle_implications(lifecycle_transitions, continuity_requirements)

    return {
        "schema_version": "governance_impact_preview.v1",
        "authority_ref": authority_ref,
        "contract_id": contract_id,
        "contract_version": contract_version,
        "contract_hash": contract.get("contract_hash"),
        "governance_summary": f"{scope} are governed by {authority_ref}.",
        "enforcement_behavior": enforcement_behavior,
        "operational_consequences": operational_consequences,
        "lifecycle_implications": lifecycle_implications,
        "example_governed_outcomes": _example_governed_outcomes(
            thresholds,
            required_roles,
            artifact_requirements,
            continuity_requirements,
        ),
    }


def format_governance_impact_preview(preview: dict[str, Any]) -> str:
    """Format a governance impact preview for CLI display."""
    lines = [
        "[Governance Impact Preview]",
        "",
        "Governance Summary:",
        f"  {preview['governance_summary']}",
        "",
        "Enforcement Behavior:",
        *_indented(preview.get("enforcement_behavior", [])),
        "",
        "Operational Consequences:",
        *_indented(preview.get("operational_consequences", [])),
        "",
        "Lifecycle Implications:",
        *_indented(preview.get("lifecycle_implications", [])),
        "",
        "Example Governed Outcomes:",
        *_indented(
            f"{item['outcome']}: {item['description']}"
            for item in preview.get("example_governed_outcomes", [])
        ),
    ]
    return "\n".join(lines)


def _required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Authority contract missing required field: {field}")
    return value


def _scope(contract: dict[str, Any]) -> str:
    scope = contract.get("scope")
    if isinstance(scope, dict):
        for field in ("description", "domain", "name"):
            value = scope.get(field)
            if isinstance(value, str) and value:
                return value
    for field in ("governed_domain", "domain", "description"):
        value = contract.get(field)
        if isinstance(value, str) and value:
            return value
    actions = contract.get("governed_actions")
    if isinstance(actions, list) and actions and all(isinstance(item, str) for item in actions):
        return ", ".join(sorted(actions))
    return _contract_label(contract["contract_id"])


def _thresholds(contract: dict[str, Any]) -> list[dict[str, Any]]:
    approval_requirements = contract.get("approval_requirements")
    thresholds = []
    if isinstance(approval_requirements, dict):
        thresholds.extend(item for item in approval_requirements.get("thresholds", []) if isinstance(item, dict))
        for requirement in approval_requirements.get("required", []):
            if not isinstance(requirement, dict) or not isinstance(requirement.get("condition"), dict):
                continue
            condition = requirement["condition"]
            thresholds.append(
                {
                    "field": condition.get("field"),
                    "operator": condition.get("operator"),
                    "value": condition.get("value"),
                    "requires_role": requirement.get("role"),
                }
            )
    return sorted(
        thresholds,
        key=lambda item: (
            str(item.get("field", "")),
            str(item.get("operator", "")),
            _sort_value(item.get("value")),
            str(item.get("requires_role", "")),
        ),
    )


def _required_roles(contract: dict[str, Any]) -> list[str]:
    roles: set[str] = set()
    authority_requirements = contract.get("authority_requirements")
    if isinstance(authority_requirements, dict):
        for role in authority_requirements.get("required_roles", []):
            if isinstance(role, str) and role:
                roles.add(role)
    approval_requirements = contract.get("approval_requirements")
    if isinstance(approval_requirements, dict):
        for requirement in approval_requirements.get("required", []):
            if isinstance(requirement, dict) and isinstance(requirement.get("role"), str):
                roles.add(requirement["role"])
    return sorted(roles)


def _artifact_requirements(contract: dict[str, Any]) -> list[str]:
    artifacts = contract.get("artifact_requirements")
    if not isinstance(artifacts, dict):
        return []
    required = artifacts.get("required", [])
    if not isinstance(required, list):
        return []
    return sorted(item for item in required if isinstance(item, str) and item)


def _lifecycle_transitions(contract: dict[str, Any]) -> list[dict[str, str]]:
    stages = contract.get("stage_requirements")
    if not isinstance(stages, dict):
        return []
    transitions = stages.get("allowed_transitions", [])
    if not isinstance(transitions, list):
        return []
    return sorted(
        (
            {"from": item["from"], "to": item["to"]}
            for item in transitions
            if isinstance(item, dict)
            and isinstance(item.get("from"), str)
            and isinstance(item.get("to"), str)
        ),
        key=lambda item: (item["from"], item["to"]),
    )


def _continuity_requirements(contract: dict[str, Any]) -> dict[str, Any]:
    for field in ("continuity_requirements", "continuity", "execution_continuity"):
        value = contract.get(field)
        if isinstance(value, dict):
            return value
    return {}


def _enforcement_behavior(
    thresholds: list[dict[str, Any]],
    required_roles: list[str],
    artifact_requirements: list[str],
) -> list[str]:
    behavior = [_threshold_sentence(threshold) for threshold in thresholds]
    for role in required_roles:
        if not any(item.endswith(f"require {role} review.") for item in behavior):
            behavior.append(f"Executions require {role} authority evidence.")
    for artifact in artifact_requirements:
        behavior.append(f"Executions require {artifact} evidence artifacts.")
    return behavior or ["Executions follow the published authority contract requirements."]


def _operational_consequences(
    thresholds: list[dict[str, Any]],
    artifact_requirements: list[str],
) -> list[str]:
    consequences = [
        "Blocked executions generate immutable replay and evidence artifacts.",
    ]
    if thresholds:
        consequences.append("Executions crossing approval thresholds require explicit approval evidence before completion.")
    if artifact_requirements:
        consequences.append("Missing required artifacts prevent governed completion until evidence is attached.")
    return consequences


def _lifecycle_implications(
    lifecycle_transitions: list[dict[str, str]],
    continuity_requirements: dict[str, Any],
) -> list[str]:
    implications = []
    if lifecycle_transitions:
        transitions = ", ".join(f"{item['from']} -> {item['to']}" for item in lifecycle_transitions)
        implications.append(f"Execution lifecycle movement is limited to: {transitions}.")
    if _truthy(continuity_requirements, "revoked_authority_invalidates_resume", "invalidate_on_revocation"):
        implications.append("Revoked authorities invalidate resumed execution continuity.")
    if _truthy(continuity_requirements, "resume_requires_current_authority", "resume_requires_authority_hash"):
        implications.append("Resumed executions must remain bound to the current authority identity.")
    return implications or ["Lifecycle continuity follows the authority contract without additional stage constraints."]


def _example_governed_outcomes(
    thresholds: list[dict[str, Any]],
    required_roles: list[str],
    artifact_requirements: list[str],
    continuity_requirements: dict[str, Any],
) -> list[dict[str, str]]:
    examples = [
        {
            "outcome": "allowed_execution",
            "description": "Execution proceeds when applicable authority, approval, and evidence requirements are satisfied.",
        },
        {
            "outcome": "blocked_execution",
            "description": "Execution is blocked when required authority evidence is missing.",
        },
    ]
    if thresholds or required_roles:
        role = thresholds[0].get("requires_role") if thresholds else required_roles[0]
        examples.append(
            {
                "outcome": "escalation",
                "description": f"Execution escalates for {_review_phrase(role)} when threshold conditions apply.",
            }
        )
    if artifact_requirements or _truthy(continuity_requirements, "resume_requires_current_authority", "resume_requires_authority_hash"):
        examples.append(
            {
                "outcome": "continuity_drift",
                "description": "Execution continuity drifts when resumed state no longer matches authority or evidence requirements.",
            }
        )
    return examples


def _threshold_sentence(threshold: dict[str, Any]) -> str:
    field = threshold.get("field") or "value"
    operator = threshold.get("operator") or "matches"
    value = _format_value(field, threshold.get("value"))
    role = threshold.get("requires_role") or "authorized"
    return f"Executions with {field} {operator} {value} require {_review_phrase(role)}."


def _format_value(field: Any, value: Any) -> str:
    if field == "amount" and isinstance(value, (int, float)):
        return f"${value:,.0f}"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _review_phrase(role: Any) -> str:
    text = str(role)
    if text.endswith("review"):
        return text
    return f"{text} review"


def _contract_label(contract_id: str) -> str:
    words = [word for word in contract_id.replace("_", "-").split("-") if word]
    if not words:
        return "Governance operations"
    return " ".join(word.capitalize() for word in words)


def _sort_value(value: Any) -> tuple[str, str]:
    if isinstance(value, (int, float)):
        return ("number", f"{value:020.6f}")
    return (type(value).__name__, str(value))


def _truthy(payload: dict[str, Any], *fields: str) -> bool:
    return any(payload.get(field) is True for field in fields)


def _indented(lines: Any) -> list[str]:
    materialized = list(lines)
    if not materialized:
        return ["  none"]
    return [f"  {line}" for line in materialized]
