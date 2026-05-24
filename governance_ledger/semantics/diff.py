"""Deterministic semantic impact diffs for authority contracts."""

from __future__ import annotations

import copy
from typing import Any

from governance_ledger.schema_versions import AUTHORITY_DIFF_IMPACT_V1


def build_authority_diff_impact(
    old_authority_contract: dict[str, Any],
    new_authority_contract: dict[str, Any],
) -> dict[str, Any]:
    """Return authority_diff_impact.v1 for two authority contracts."""
    old_contract = copy.deepcopy(old_authority_contract)
    new_contract = copy.deepcopy(new_authority_contract)
    changed_rules = [
        *_threshold_changes(_thresholds(old_contract), _thresholds(new_contract)),
        *_role_changes(_required_roles(old_contract), _required_roles(new_contract)),
        *_artifact_changes(_artifact_requirements(old_contract), _artifact_requirements(new_contract)),
        *_lifecycle_changes(_lifecycle_transitions(old_contract), _lifecycle_transitions(new_contract)),
        *_continuity_changes(_continuity_requirements(old_contract), _continuity_requirements(new_contract)),
    ]
    changed_rules = sorted(changed_rules, key=_rule_sort_key)

    return {
        "schema_version": AUTHORITY_DIFF_IMPACT_V1,
        "old_authority_ref": _authority_ref(old_contract),
        "new_authority_ref": _authority_ref(new_contract),
        "old_contract_hash": old_contract.get("contract_hash"),
        "new_contract_hash": new_contract.get("contract_hash"),
        "changed_governance_rules": changed_rules,
        "operational_implications": _unique(
            implication
            for change in changed_rules
            for implication in change.get("operational_impact", [])
        ),
        "lifecycle_continuity_implications": _unique(
            implication
            for change in changed_rules
            for implication in change.get("continuity_implications", [])
        ),
        "escalation_impact": _unique(
            implication
            for change in changed_rules
            for implication in change.get("escalation_impact", [])
        ),
        "replay_continuity_implications": _unique(
            implication
            for change in changed_rules
            for implication in change.get("replay_continuity_implications", [])
        ),
        "deterministic_guarantees": [
            "Derived only from structured authority contract fields.",
            "Does not invoke Guard, replay, simulation, runtime evaluation, or admissibility execution.",
            "Stable for identical old and new authority inputs.",
        ],
    }


def format_authority_diff_impact(diff: dict[str, Any]) -> str:
    """Format an authority diff impact artifact for CLI display."""
    return "\n".join(
        [
            "[Authority Diff Impact]",
            "",
            f"Old Authority: {diff['old_authority_ref']}",
            f"New Authority: {diff['new_authority_ref']}",
            "",
            "Changed Governance Rules:",
            *_indented(
                f"{item['change_type']}: {item['summary']}"
                for item in diff.get("changed_governance_rules", [])
            ),
            "",
            "Operational Implications:",
            *_indented(diff.get("operational_implications", [])),
            "",
            "Lifecycle Continuity Implications:",
            *_indented(diff.get("lifecycle_continuity_implications", [])),
            "",
            "Escalation Impact:",
            *_indented(diff.get("escalation_impact", [])),
            "",
            "Replay Continuity Implications:",
            *_indented(diff.get("replay_continuity_implications", [])),
        ]
    )


def _threshold_changes(
    old_thresholds: list[dict[str, Any]],
    new_thresholds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    old_by_key = {_threshold_key(item): item for item in old_thresholds}
    new_by_key = {_threshold_key(item): item for item in new_thresholds}
    changes = []

    for key in old_by_key.keys() & new_by_key.keys():
        old = old_by_key[key]
        new = new_by_key[key]
        if old.get("value") == new.get("value"):
            continue
        direction = _threshold_direction(old, new)
        changes.append(
            _change(
                "ESCALATION_THRESHOLD_CHANGED",
                rule_ref=_threshold_rule_ref(new),
                before=old,
                after=new,
                summary=(
                    f"{new.get('field')} {new.get('operator')} threshold changed "
                    f"from {_format_value(new.get('field'), old.get('value'))} "
                    f"to {_format_value(new.get('field'), new.get('value'))} "
                    f"for {_review_phrase(new.get('requires_role'))}."
                ),
                operational_impact=[_threshold_operational_impact(direction)],
                continuity_implications=["Resumed workflows may require continuity revalidation."],
                escalation_impact=[_threshold_escalation_impact(direction)],
                replay_continuity_implications=[
                    "Replay bundles spanning this authority change must bind execution state to the exact authority hash."
                ],
            )
        )

    for key in new_by_key.keys() - old_by_key.keys():
        new = new_by_key[key]
        changes.append(
            _change(
                "ESCALATION_THRESHOLD_ADDED",
                rule_ref=_threshold_rule_ref(new),
                before=None,
                after=new,
                summary=(
                    f"New escalation threshold added: {new.get('field')} {new.get('operator')} "
                    f"{_format_value(new.get('field'), new.get('value'))} requires "
                    f"{_review_phrase(new.get('requires_role'))}."
                ),
                operational_impact=["Additional executions may require escalation review."],
                continuity_implications=["In-flight workflows may require continuity revalidation against the new threshold."],
                escalation_impact=["Escalation review coverage expands."],
                replay_continuity_implications=[
                    "Replay bundles created before this threshold must preserve their original authority hash."
                ],
            )
        )

    for key in old_by_key.keys() - new_by_key.keys():
        old = old_by_key[key]
        changes.append(
            _change(
                "ESCALATION_THRESHOLD_REMOVED",
                rule_ref=_threshold_rule_ref(old),
                before=old,
                after=None,
                summary=(
                    f"Escalation threshold removed: {old.get('field')} {old.get('operator')} "
                    f"{_format_value(old.get('field'), old.get('value'))} for "
                    f"{_review_phrase(old.get('requires_role'))}."
                ),
                operational_impact=["Fewer executions may require escalation review."],
                continuity_implications=["In-flight workflows may need revalidation before relying on relaxed escalation requirements."],
                escalation_impact=["Escalation review coverage narrows."],
                replay_continuity_implications=[
                    "Replay bundles created under the removed threshold must preserve their original authority hash."
                ],
            )
        )

    return changes


def _role_changes(old_roles: list[str], new_roles: list[str]) -> list[dict[str, Any]]:
    changes = []
    for role in sorted(set(new_roles) - set(old_roles)):
        changes.append(
            _change(
                "AUTHORITY_ROLE_ADDED",
                rule_ref=f"authority_role:{role}",
                before=None,
                after=role,
                summary=f"{role} authority evidence is now required.",
                operational_impact=["Executions may require additional authority evidence before completion."],
                continuity_implications=["Resumed workflows may require continuity revalidation for authority role coverage."],
                replay_continuity_implications=[
                    "Replay verification must use the authority version that matches the required role set."
                ],
            )
        )
    for role in sorted(set(old_roles) - set(new_roles)):
        changes.append(
            _change(
                "AUTHORITY_ROLE_REMOVED",
                rule_ref=f"authority_role:{role}",
                before=role,
                after=None,
                summary=f"{role} authority evidence is no longer required.",
                operational_impact=["Executions may require less authority evidence before completion."],
                continuity_implications=["In-flight workflows may need revalidation before relying on relaxed authority requirements."],
                replay_continuity_implications=[
                    "Replay verification must preserve the authority version active at execution time."
                ],
            )
        )
    return changes


def _artifact_changes(old_artifacts: list[str], new_artifacts: list[str]) -> list[dict[str, Any]]:
    changes = []
    for artifact in sorted(set(new_artifacts) - set(old_artifacts)):
        changes.append(
            _change(
                "EVIDENCE_ARTIFACT_REQUIRED",
                rule_ref=f"artifact:{artifact}",
                before=None,
                after=artifact,
                summary=f"{artifact} evidence artifacts are now required.",
                operational_impact=["Executions missing newly required evidence artifacts may be blocked from governed completion."],
                continuity_implications=["Resumed workflows may need evidence continuity revalidation."],
                replay_continuity_implications=[
                    "Replay continuity must include the evidence artifact set required by the authority version."
                ],
            )
        )
    for artifact in sorted(set(old_artifacts) - set(new_artifacts)):
        changes.append(
            _change(
                "EVIDENCE_ARTIFACT_REMOVED",
                rule_ref=f"artifact:{artifact}",
                before=artifact,
                after=None,
                summary=f"{artifact} evidence artifacts are no longer required.",
                operational_impact=["Executions may require fewer evidence artifacts before governed completion."],
                continuity_implications=["In-flight workflows may need revalidation before relying on relaxed evidence requirements."],
                replay_continuity_implications=[
                    "Replay bundles created under the prior evidence requirement must retain their original artifact evidence."
                ],
            )
        )
    return changes


def _lifecycle_changes(
    old_transitions: list[dict[str, str]],
    new_transitions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    changes = []
    old_keys = {_transition_key(item) for item in old_transitions}
    new_keys = {_transition_key(item) for item in new_transitions}
    for key in sorted(new_keys - old_keys):
        changes.append(
            _change(
                "LIFECYCLE_TRANSITION_ADDED",
                rule_ref=f"lifecycle:{key[0]}->{key[1]}",
                before=None,
                after={"from": key[0], "to": key[1]},
                summary=f"Lifecycle transition {key[0]} -> {key[1]} is now allowed.",
                operational_impact=["Operators may move governed workflows through an additional lifecycle transition."],
                continuity_implications=["Resumed workflows may require lifecycle continuity revalidation."],
                replay_continuity_implications=[
                    "Replay traces must preserve the lifecycle graph active when the transition occurred."
                ],
            )
        )
    for key in sorted(old_keys - new_keys):
        changes.append(
            _change(
                "LIFECYCLE_TRANSITION_REMOVED",
                rule_ref=f"lifecycle:{key[0]}->{key[1]}",
                before={"from": key[0], "to": key[1]},
                after=None,
                summary=f"Lifecycle transition {key[0]} -> {key[1]} is no longer allowed.",
                operational_impact=["Operators may be blocked from moving governed workflows through a previously allowed transition."],
                continuity_implications=["Resumed workflows on the removed transition path require continuity revalidation."],
                replay_continuity_implications=[
                    "Replay traces spanning this lifecycle change must bind to the exact authority version."
                ],
            )
        )
    return changes


def _continuity_changes(
    old_continuity: dict[str, Any],
    new_continuity: dict[str, Any],
) -> list[dict[str, Any]]:
    changes = []
    for key in sorted(old_continuity.keys() | new_continuity.keys()):
        old_value = old_continuity.get(key)
        new_value = new_continuity.get(key)
        if old_value == new_value:
            continue
        changes.append(
            _change(
                "CONTINUITY_REQUIREMENT_CHANGED",
                rule_ref=f"continuity:{key}",
                before=old_value,
                after=new_value,
                summary=f"Continuity requirement {key} changed from {old_value} to {new_value}.",
                operational_impact=["Continuity handling for resumed workflows has changed."],
                continuity_implications=["Resumed workflows may require continuity revalidation."],
                replay_continuity_implications=[
                    "Replay bundles must bind continuity checks to the authority version that governed execution."
                ],
            )
        )
    return changes


def _change(
    change_type: str,
    *,
    rule_ref: str,
    before: Any,
    after: Any,
    summary: str,
    operational_impact: list[str],
    continuity_implications: list[str],
    escalation_impact: list[str] | None = None,
    replay_continuity_implications: list[str],
) -> dict[str, Any]:
    return {
        "change_type": change_type,
        "rule_ref": rule_ref,
        "before": before,
        "after": after,
        "summary": summary,
        "operational_impact": operational_impact,
        "continuity_implications": continuity_implications,
        "escalation_impact": escalation_impact or [],
        "replay_continuity_implications": replay_continuity_implications,
    }


def _authority_ref(contract: dict[str, Any]) -> str:
    contract_id = contract.get("contract_id")
    contract_version = contract.get("contract_version")
    if not isinstance(contract_id, str) or not contract_id:
        raise ValueError("Authority contract missing required field: contract_id")
    if not isinstance(contract_version, str) or not contract_version:
        raise ValueError("Authority contract missing required field: contract_version")
    return f"{contract_id}@{contract_version}"


def _thresholds(contract: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = contract.get("approval_requirements")
    thresholds = []
    if not isinstance(requirements, dict):
        return thresholds
    thresholds.extend(copy.deepcopy(item) for item in requirements.get("thresholds", []) if isinstance(item, dict))
    for requirement in requirements.get("required", []):
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
    return sorted(thresholds, key=lambda item: (_threshold_key(item), _sort_value(item.get("value"))))


def _required_roles(contract: dict[str, Any]) -> list[str]:
    roles = set()
    authority_requirements = contract.get("authority_requirements")
    if isinstance(authority_requirements, dict):
        roles.update(role for role in authority_requirements.get("required_roles", []) if isinstance(role, str))
    approval_requirements = contract.get("approval_requirements")
    if isinstance(approval_requirements, dict):
        roles.update(
            requirement["role"]
            for requirement in approval_requirements.get("required", [])
            if isinstance(requirement, dict) and isinstance(requirement.get("role"), str)
        )
    return sorted(roles)


def _artifact_requirements(contract: dict[str, Any]) -> list[str]:
    artifacts = contract.get("artifact_requirements")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("required"), list):
        return []
    return sorted(item for item in artifacts["required"] if isinstance(item, str))


def _lifecycle_transitions(contract: dict[str, Any]) -> list[dict[str, str]]:
    stages = contract.get("stage_requirements")
    if not isinstance(stages, dict) or not isinstance(stages.get("allowed_transitions"), list):
        return []
    transitions = [
        {
            "from": item["from"],
            "to": item["to"],
        }
        for item in stages["allowed_transitions"]
        if isinstance(item, dict) and isinstance(item.get("from"), str) and isinstance(item.get("to"), str)
    ]
    return sorted(transitions, key=lambda item: (item["from"], item["to"]))


def _continuity_requirements(contract: dict[str, Any]) -> dict[str, Any]:
    for field in ("continuity_requirements", "continuity", "execution_continuity"):
        value = contract.get(field)
        if isinstance(value, dict):
            return copy.deepcopy(value)
    return {}


def _threshold_key(threshold: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(threshold.get("field", "")),
        str(threshold.get("operator", "")),
        str(threshold.get("requires_role", "")),
    )


def _threshold_rule_ref(threshold: dict[str, Any]) -> str:
    field, operator, role = _threshold_key(threshold)
    return f"threshold:{field}:{operator}:{role}"


def _transition_key(transition: dict[str, str]) -> tuple[str, str]:
    return (transition["from"], transition["to"])


def _threshold_direction(old: dict[str, Any], new: dict[str, Any]) -> str:
    old_value = old.get("value")
    new_value = new.get("value")
    operator = new.get("operator")
    if not isinstance(old_value, (int, float)) or not isinstance(new_value, (int, float)):
        return "changed"
    if operator in {">", ">="}:
        if new_value < old_value:
            return "more_escalation"
        if new_value > old_value:
            return "less_escalation"
    if operator in {"<", "<="}:
        if new_value > old_value:
            return "more_escalation"
        if new_value < old_value:
            return "less_escalation"
    return "changed"


def _threshold_operational_impact(direction: str) -> str:
    if direction == "more_escalation":
        return "More executions are expected to enter escalation review."
    if direction == "less_escalation":
        return "Fewer executions are expected to enter escalation review."
    return "Escalation routing may change for executions matching this threshold."


def _threshold_escalation_impact(direction: str) -> str:
    if direction == "more_escalation":
        return "Escalation review coverage expands."
    if direction == "less_escalation":
        return "Escalation review coverage narrows."
    return "Escalation review routing changes."


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


def _sort_value(value: Any) -> tuple[str, str]:
    if isinstance(value, (int, float)):
        return ("number", f"{value:020.6f}")
    return (type(value).__name__, str(value))


def _rule_sort_key(change: dict[str, Any]) -> tuple[str, str]:
    return (change["change_type"], change["rule_ref"])


def _unique(items: Any) -> list[str]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _indented(lines: Any) -> list[str]:
    materialized = list(lines)
    if not materialized:
        return ["  none"]
    return [f"  {line}" for line in materialized]
