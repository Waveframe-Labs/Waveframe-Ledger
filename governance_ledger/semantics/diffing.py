"""Operational semantic diffs between interpreted authority meanings."""

from __future__ import annotations

import copy
from typing import Any


SEMANTIC_AUTHORITY_DIFF_V1 = "semantic_authority_diff.v1"


def build_semantic_authority_diff(
    previous_authority: dict[str, Any],
    current_authority: dict[str, Any],
) -> dict[str, Any]:
    """Compare governance meaning, not source text or document structure."""
    previous = copy.deepcopy(previous_authority)
    current = copy.deepcopy(current_authority)
    changes = [
        *_capability_changes(previous, current),
        *_approval_changes(previous, current),
        *_ai_autonomy_changes(previous, current),
        *_continuity_changes(previous, current),
        *_replay_changes(previous, current),
        *_escalation_changes(previous, current),
        *_execution_boundary_changes(previous, current),
        *_identity_changes(previous, current),
        *_delegation_changes(previous, current),
        *_validity_window_changes(previous, current),
        *_scope_changes(previous, current),
    ]
    changes = sorted(changes, key=lambda item: (item["change_class"], item["semantic_path"], str(item["before"]), str(item["after"])))

    return {
        "schema_version": SEMANTIC_AUTHORITY_DIFF_V1,
        "previous_authority_ref": _authority_ref(previous),
        "current_authority_ref": _authority_ref(current),
        "semantic_changes": changes,
        "operational_impact_narratives": _unique(
            narrative
            for change in changes
            for narrative in change.get("operational_impact", [])
        ),
        "guard_compatibility_projection": _guard_compatibility_projection(changes),
        "replay_compatibility_warnings": _unique(
            warning
            for change in changes
            for warning in change.get("replay_compatibility_warnings", [])
        ),
        "deterministic_guarantees": [
            "Diffs interpreted authority meaning, not raw policy text.",
            "Does not invoke Guard, Cloud, simulation, runtime evaluation, or admissibility execution.",
            "Stable for identical previous and current authority inputs.",
        ],
    }


def _capability_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_capabilities = _capabilities_by_id(previous)
    current_capabilities = _capabilities_by_id(current)
    changes = []
    for capability_id in sorted(set(current_capabilities) - set(previous_capabilities)):
        capability = current_capabilities[capability_id]
        changes.append(
            _change(
                change_class="capability_added",
                semantic_path=f"capabilities.{capability_id}",
                before=None,
                after=capability,
                severity=_capability_severity(capability),
                operational_impact=[f"Capability {capability_id} is now governed by this authority."],
                guard_obligations=_guard_obligations_for_capability(capability),
                replay_warnings=["Replay review must bind executions to the authority version where this capability exists."],
            )
        )
    for capability_id in sorted(set(previous_capabilities) - set(current_capabilities)):
        capability = previous_capabilities[capability_id]
        changes.append(
            _change(
                change_class="capability_removed",
                semantic_path=f"capabilities.{capability_id}",
                before=capability,
                after=None,
                severity="high-impact",
                operational_impact=[f"Capability {capability_id} is no longer governed by this authority."],
                replay_warnings=["Replay review must preserve prior authority lineage for executions using the removed capability."],
            )
        )
    return changes


def _approval_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    previous_count = _approval_count(previous)
    current_count = _approval_count(current)
    if previous_count != current_count:
        strengthened = _number(current_count) > _number(previous_count)
        changes.append(
            _change(
                change_class="approval_strengthened" if strengthened else "approval_weakened",
                semantic_path="approval.required_count",
                before=previous_count,
                after=current_count,
                severity="moderate" if strengthened else "high-impact",
                operational_impact=[
                    "Human approval requirements increased." if strengthened else "Human approval requirements decreased.",
                    "Execution autonomy reduced." if strengthened else "Execution autonomy expanded.",
                ],
                guard_obligations=["Verify required approval count before admissibility."] if strengthened else [],
            )
        )

    previous_roles = set(_approval_roles(previous))
    current_roles = set(_approval_roles(current))
    if previous_roles != current_roles:
        changes.append(
            _change(
                change_class="identity_change",
                semantic_path="approval.required_roles",
                before=sorted(previous_roles),
                after=sorted(current_roles),
                severity="moderate",
                operational_impact=["Approval responsibility changed across authority roles."],
                guard_obligations=["Verify approval evidence against the active authority role set."],
            )
        )

    for field, summary in (
        ("independence_required", "Approval independence boundary changed."),
        ("self_approval_prohibited", "Self-approval boundary changed."),
        ("attestation_required", "Actor attestation requirement changed."),
    ):
        previous_value = _approval_semantics(previous).get(field)
        current_value = _approval_semantics(current).get(field)
        if previous_value == current_value:
            continue
        strengthened = bool(current_value) and not bool(previous_value)
        changes.append(
            _change(
                change_class="approval_strengthened" if strengthened else "approval_weakened",
                semantic_path=f"approval.{field}",
                before=previous_value,
                after=current_value,
                severity="moderate" if strengthened else "high-impact",
                operational_impact=[summary],
                guard_obligations=[f"Verify {field} before admissibility."] if strengthened else [],
            )
        )
    return changes


def _ai_autonomy_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_posture = _ai_posture(previous)
    current_posture = _ai_posture(current)
    if previous_posture == current_posture:
        return []
    previous_rank = _ai_autonomy_rank(previous_posture)
    current_rank = _ai_autonomy_rank(current_posture)
    expanded = current_rank > previous_rank
    return [
        _change(
            change_class="relaxed_control" if expanded else "tightened_control",
            semantic_path="ai.autonomy_posture",
            before=previous_posture,
            after=current_posture,
            severity="breaking-governance-change" if expanded else "high-impact",
            operational_impact=[
                "AI execution autonomy expanded." if expanded else "AI execution autonomy reduced.",
                "Human approval boundary relaxed." if expanded else "Human approval boundary strengthened.",
            ],
            guard_obligations=["Verify AI execution authorization boundary before admissibility."] if expanded else [],
            replay_warnings=["Replay review must distinguish advisory AI recommendations from executable AI actions."],
        )
    ]


def _continuity_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for field, summary in (
        ("continuity_revalidation", "Continuity revalidation posture changed."),
        ("revocation_invalidates_resume", "Revocation invalidation posture changed."),
    ):
        previous_value = bool(previous.get(field))
        current_value = bool(current.get(field))
        if previous_value == current_value:
            continue
        strengthened = current_value and not previous_value
        changes.append(
            _change(
                change_class="continuity_change",
                semantic_path=f"continuity.{field}",
                before=previous_value,
                after=current_value,
                severity="high-impact",
                operational_impact=[
                    summary,
                    "Continuity controls expanded for resumed workflows." if strengthened else "Continuity controls relaxed for resumed workflows.",
                ],
                guard_obligations=["Verify continuity posture before resumed execution."] if strengthened else [],
                replay_warnings=["Replay continuity must bind resumed execution to the authority version active at continuation."],
            )
        )

    previous_snapshot = _snapshot_semantics(previous)
    current_snapshot = _snapshot_semantics(current)
    if previous_snapshot != current_snapshot:
        changes.append(
            _change(
                change_class="continuity_change",
                semantic_path="continuity.state_snapshot_semantics",
                before=previous_snapshot,
                after=current_snapshot,
                severity="high-impact",
                operational_impact=["State snapshot continuity semantics changed."],
                guard_obligations=["Compare governance snapshot hash against active governance posture."] if current_snapshot.get("snapshot_required") else [],
                replay_warnings=["Replay evidence must preserve state snapshot semantics for the authority version under review."],
            )
        )
    return changes


def _replay_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_obligations = set(_replay_obligations(previous))
    current_obligations = set(_replay_obligations(current))
    if previous_obligations == current_obligations:
        return []
    added = sorted(current_obligations - previous_obligations)
    removed = sorted(previous_obligations - current_obligations)
    return [
        _change(
            change_class="replay_change",
            semantic_path="replay.obligations",
            before=sorted(previous_obligations),
            after=sorted(current_obligations),
            severity="high-impact" if removed else "moderate",
            operational_impact=[
                "Replay continuity obligations changed.",
                "Replay evidence requirements expanded." if added and not removed else "Replay evidence requirements relaxed." if removed else "Replay evidence requirements changed.",
            ],
            guard_obligations=[f"Validate {item} evidence before admissibility." for item in added],
            replay_warnings=["Replay compatibility depends on the authority version that produced the evidence obligation set."],
        )
    ]


def _escalation_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_threshold = previous.get("escalation_threshold")
    current_threshold = current.get("escalation_threshold")
    if previous_threshold == current_threshold:
        return []
    lowered = _number(current_threshold) < _number(previous_threshold)
    return [
        _change(
            change_class="tightened_control" if lowered else "relaxed_control",
            semantic_path="escalation.threshold",
            before=previous_threshold,
            after=current_threshold,
            severity="moderate" if lowered else "high-impact",
            operational_impact=[
                "Escalation review coverage expanded." if lowered else "Escalation review coverage narrowed."
            ],
            guard_obligations=["Evaluate escalation threshold before admissibility."] if current_threshold is not None else [],
        )
    ]


def _execution_boundary_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_execution = _execution_semantics(previous)
    current_execution = _execution_semantics(current)
    changes = []
    for field in ("execution_context", "execution_boundary", "requires_replay_evidence", "requires_state_snapshot", "requires_temporal_validation", "resume_behavior"):
        previous_value = previous_execution.get(field)
        current_value = current_execution.get(field)
        if previous_value == current_value:
            continue
        changes.append(
            _change(
                change_class="scope_expansion" if field == "execution_context" else "continuity_change",
                semantic_path=f"execution.{field}",
                before=previous_value,
                after=current_value,
                severity="moderate",
                operational_impact=[f"Execution context semantic {field} changed."],
                guard_obligations=[f"Evaluate execution context {field} before admissibility."],
            )
        )
    return changes


def _identity_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_identity = _identity_semantics(previous)
    current_identity = _identity_semantics(current)
    changes = []
    for field in ("actor_id", "actor_type", "authority_scope", "attestation_required", "identity_continuity_required"):
        previous_value = previous_identity.get(field)
        current_value = current_identity.get(field)
        if previous_value == current_value:
            continue
        changes.append(
            _change(
                change_class="identity_change",
                semantic_path=f"identity.{field}",
                before=previous_value,
                after=current_value,
                severity="moderate",
                operational_impact=[f"Governance identity semantic {field} changed."],
                guard_obligations=[f"Verify identity semantic {field} before admissibility."],
            )
        )
    return changes


def _delegation_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_posture = _delegation_posture(previous)
    current_posture = _delegation_posture(current)
    if previous_posture == current_posture:
        return []
    expanded = _delegation_rank(current_posture) > _delegation_rank(previous_posture)
    return [
        _change(
            change_class="delegation_change",
            semantic_path="delegation.posture",
            before=previous_posture,
            after=current_posture,
            severity="high-impact" if expanded else "moderate",
            operational_impact=[
                "Delegated authority boundary expanded." if expanded else "Delegated authority boundary tightened."
            ],
            guard_obligations=["Verify delegation evidence and authority boundary before admissibility."] if expanded else [],
            replay_warnings=["Replay lineage must preserve delegation posture active at execution time."],
        )
    ]


def _validity_window_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_window = _validity_window(previous)
    current_window = _validity_window(current)
    if previous_window == current_window:
        return []
    relaxed = _duration_rank(current_window) > _duration_rank(previous_window)
    return [
        _change(
            change_class="relaxed_control" if relaxed else "tightened_control",
            semantic_path="temporal.validity_window",
            before=previous_window,
            after=current_window,
            severity="moderate",
            operational_impact=[
                "Authority validity window expanded." if relaxed else "Authority validity window narrowed."
            ],
            guard_obligations=["Validate authority timestamp and expiration basis before admissibility."],
        )
    ]


def _scope_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for field in ("governed_targets", "governed_operations", "mutation_classes", "mutation_targets"):
        previous_values = set(_list(previous.get(field)))
        current_values = set(_list(current.get(field)))
        if previous_values == current_values:
            continue
        added = sorted(current_values - previous_values)
        removed = sorted(previous_values - current_values)
        changes.append(
            _change(
                change_class="scope_expansion" if added and not removed else "scope_reduction" if removed and not added else "scope_change",
                semantic_path=f"scope.{field}",
                before=sorted(previous_values),
                after=sorted(current_values),
                severity="high-impact" if added else "moderate",
                operational_impact=[
                    f"Governance scope changed for {field}.",
                    f"New governed scope: {', '.join(added)}." if added else "",
                    f"Removed governed scope: {', '.join(removed)}." if removed else "",
                ],
                guard_obligations=[f"Evaluate governed scope {field} before admissibility."] if added else [],
            )
        )
    return changes


def _change(
    *,
    change_class: str,
    semantic_path: str,
    before: Any,
    after: Any,
    severity: str,
    operational_impact: list[str],
    guard_obligations: list[str] | None = None,
    replay_warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "semantic_meaning_change.v1",
        "change_class": change_class,
        "semantic_path": semantic_path,
        "before": before,
        "after": after,
        "severity": severity,
        "operational_impact": [item for item in operational_impact if item],
        "guard_enforcement_implications": guard_obligations or [],
        "replay_compatibility_warnings": replay_warnings or [],
    }


def _guard_compatibility_projection(changes: list[dict[str, Any]]) -> dict[str, Any]:
    obligations = _unique(
        obligation
        for change in changes
        for obligation in change.get("guard_enforcement_implications", [])
    )
    return {
        "schema_version": "guard_compatibility_projection.v1",
        "new_enforcement_obligations": obligations,
        "compatibility_posture": "guard_behavior_changes" if obligations else "no_new_guard_obligations",
        "non_goals": [
            "does not invoke Guard",
            "does not determine admissibility",
            "does not execute enforcement decisions",
        ],
    }


def _authority_ref(authority: dict[str, Any]) -> str:
    authority_id = authority.get("contract_id") or authority.get("authority_id") or authority.get("source_id") or "authority"
    version = authority.get("contract_version") or authority.get("authority_version") or "unversioned"
    return f"{authority_id}@{version}"


def _capabilities_by_id(authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    capabilities = authority.get("capabilities") or []
    return {
        str(item.get("capability_id") or item.get("action")): copy.deepcopy(item)
        for item in capabilities
        if isinstance(item, dict) and (item.get("capability_id") or item.get("action"))
    }


def _approval_semantics(authority: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(authority.get("approval_chain_semantics") or {})


def _approval_count(authority: dict[str, Any]) -> Any:
    approval = _approval_semantics(authority)
    return approval.get("required_approval_count", authority.get("approval_count"))


def _approval_roles(authority: dict[str, Any]) -> list[str]:
    approval = _approval_semantics(authority)
    roles = approval.get("required_roles") or []
    if authority.get("approver_role"):
        roles = [*roles, authority["approver_role"]]
    return sorted(str(item) for item in roles if item)


def _ai_posture(authority: dict[str, Any]) -> str:
    approval = _approval_semantics(authority)
    ai_boundary = authority.get("ai_boundary_semantics") or {}
    return (
        approval.get("ai_recommendation_posture")
        or ai_boundary.get("ai_recommendation_posture")
        or ai_boundary.get("autonomy_posture")
        or "not_present"
    )


def _ai_autonomy_rank(posture: Any) -> int:
    return {
        "not_present": 0,
        "advisory_only": 1,
        "human_acknowledged": 2,
        "incident_auto_execute": 3,
        "auto_execute": 4,
        "independent_authorization": 5,
    }.get(str(posture), 1)


def _snapshot_semantics(authority: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(authority.get("state_snapshot_semantics") or {})


def _replay_obligations(authority: dict[str, Any]) -> list[str]:
    obligations = set(_list(authority.get("replay_requirements")))
    for capability in _capabilities_by_id(authority).values():
        for evidence in capability.get("evidence_requirements") or []:
            if isinstance(evidence, dict) and evidence.get("evidence_type"):
                obligations.add(str(evidence["evidence_type"]))
    return sorted(obligations)


def _execution_semantics(authority: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(authority.get("execution_context_semantics") or {})


def _identity_semantics(authority: dict[str, Any]) -> dict[str, Any]:
    actor = authority.get("governance_actor") or {}
    identity = authority.get("identity_continuity_semantics") or {}
    return {**copy.deepcopy(actor), **copy.deepcopy(identity)}


def _delegation_posture(authority: dict[str, Any]) -> str:
    approval = _approval_semantics(authority)
    binding = authority.get("authority_role_binding") or {}
    emergency = authority.get("emergency_delegation_semantics") or {}
    return approval.get("delegation_posture") or binding.get("delegation_posture") or ("emergency_delegation" if emergency else "not_allowed")


def _delegation_rank(posture: Any) -> int:
    return {
        "not_allowed": 0,
        "ambiguous": 1,
        "allowed_with_boundary": 2,
        "emergency_delegation": 3,
        "allowed": 4,
    }.get(str(posture), 1)


def _validity_window(authority: dict[str, Any]) -> Any:
    temporal = authority.get("temporal_semantics") or {}
    return temporal.get("validity_window") or (f"P{authority['validity_days']}D" if authority.get("validity_days") else None)


def _duration_rank(value: Any) -> int:
    text = str(value or "")
    if text.startswith("PT") and text.endswith("H"):
        return int(text.removeprefix("PT").removesuffix("H")) * 60
    if text.startswith("P") and text.endswith("D"):
        return int(text.removeprefix("P").removesuffix("D")) * 24 * 60
    return 0


def _capability_severity(capability: dict[str, Any]) -> str:
    if capability.get("action_type") in {"delegation_action", "ai_recommendation_action"}:
        return "high-impact"
    return "moderate"


def _guard_obligations_for_capability(capability: dict[str, Any]) -> list[str]:
    obligations = []
    for requirement in capability.get("requirements") or []:
        if isinstance(requirement, dict) and requirement.get("requirement_type"):
            obligations.append(f"Evaluate {requirement['requirement_type']} for {capability.get('capability_id')}.")
    continuity = capability.get("continuity_semantics") or {}
    if continuity.get("revalidation_required"):
        obligations.append("Verify continuity revalidation before resumed execution.")
    if continuity.get("state_snapshot_semantics"):
        obligations.append("Compare governance snapshot hash against active governance posture.")
    for evidence in capability.get("evidence_requirements") or []:
        if isinstance(evidence, dict) and evidence.get("evidence_type"):
            obligations.append(f"Validate {evidence['evidence_type']} evidence before admissibility.")
    return obligations


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _unique(items: Any) -> list[str]:
    result = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
