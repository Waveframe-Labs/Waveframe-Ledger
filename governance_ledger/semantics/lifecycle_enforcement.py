"""Lifecycle enforcement consequence projections from semantic authority diffs."""

from __future__ import annotations

from typing import Any


SEMANTIC_LIFECYCLE_ENFORCEMENT_PROJECTION_V1 = "semantic_lifecycle_enforcement_projection.v1"


def build_semantic_lifecycle_enforcement_projection(
    semantic_authority_diff: dict[str, Any],
) -> dict[str, Any]:
    """Project semantic changes into read-only lifecycle and admissibility consequences."""
    changes = list(semantic_authority_diff.get("semantic_changes") or [])
    consequence_chain = [_consequence_for_change(change) for change in changes]
    lifecycle_invalidations = _lifecycle_invalidations(consequence_chain)
    replay_projection = _replay_continuity_projection(semantic_authority_diff, consequence_chain)
    admissibility_projection = _execution_admissibility_projection(consequence_chain)
    guard_projection = _guard_policy_projection(semantic_authority_diff, consequence_chain)

    return {
        "schema_version": SEMANTIC_LIFECYCLE_ENFORCEMENT_PROJECTION_V1,
        "source_diff_schema_version": semantic_authority_diff.get("schema_version"),
        "previous_authority_ref": semantic_authority_diff.get("previous_authority_ref"),
        "current_authority_ref": semantic_authority_diff.get("current_authority_ref"),
        "generated_from_change_count": len(changes),
        "lifecycle_invalidation_model": lifecycle_invalidations,
        "replay_continuity_projection": replay_projection,
        "authority_supersession_consequences": _authority_supersession_consequences(consequence_chain),
        "drift_detection_surfaces": _drift_detection_surfaces(consequence_chain),
        "execution_admissibility_projection": admissibility_projection,
        "what_becomes_unsafe_now": _unsafe_now(consequence_chain, replay_projection, guard_projection),
        "guard_policy_projection": guard_projection,
        "consequence_chain": consequence_chain,
        "deterministic_guarantees": [
            "Derived only from semantic_authority_diff.v1.",
            "Does not invoke Guard, Cloud, simulation, runtime evaluation, or admissibility execution.",
            "Same semantic diff input produces the same lifecycle enforcement projection.",
        ],
        "non_goals": [
            "does_not_execute_guard",
            "does_not_block_runtime_execution",
            "does_not_mutate_registry_state",
            "does_not_determine_runtime_admissibility",
        ],
    }


def _consequence_for_change(change: dict[str, Any]) -> dict[str, Any]:
    change_class = change.get("change_class") or "semantic_change"
    path = change.get("semantic_path") or "semantic.unknown"
    operational = _first(change.get("operational_impact")) or f"{path} changed."
    continuity = _continuity_impact(change)
    admissibility = _admissibility_projection(change)
    unsafe = _unsafe_observations(change)
    return {
        "schema_version": "semantic_lifecycle_consequence.v1",
        "semantic_change": {
            "change_class": change_class,
            "semantic_path": path,
            "severity": change.get("severity") or "informational",
        },
        "operational_consequence": operational,
        "continuity_impact": continuity,
        "execution_admissibility_projection": admissibility,
        "unsafe_observations": unsafe,
        "guard_enforcement_implications": list(change.get("guard_enforcement_implications") or []),
        "replay_compatibility_warnings": list(change.get("replay_compatibility_warnings") or []),
    }


def _continuity_impact(change: dict[str, Any]) -> str:
    change_class = change.get("change_class")
    path = str(change.get("semantic_path") or "")
    before = change.get("before")
    after = change.get("after")
    if change_class == "continuity_change":
        return "revalidation_required"
    if change_class == "replay_change":
        before_set = set(_list(before))
        after_set = set(_list(after))
        if before_set - after_set:
            return "replay_continuity_degraded"
        return "replay_continuity_expanded"
    if change_class == "capability_removed":
        return "prior_execution_lineage_required"
    if change_class == "approval_weakened":
        return "approval_evidence_may_be_stale"
    if change_class == "delegation_change":
        return "delegated_authority_boundary_changed"
    if path.startswith("execution.") or change_class in {"scope_expansion", "relaxed_control"}:
        return "execution_boundary_review_required"
    if change_class in {"approval_strengthened", "identity_change"}:
        return "authority_evidence_revalidation_required"
    return "none"


def _admissibility_projection(change: dict[str, Any]) -> str:
    change_class = change.get("change_class")
    path = str(change.get("semantic_path") or "")
    before = change.get("before")
    after = change.get("after")
    if change_class == "continuity_change":
        return "resumed_workflows_require_revalidation"
    if change_class == "approval_weakened":
        return "prior_approval_evidence_should_not_be_reused_without_review"
    if change_class == "approval_strengthened":
        return "existing_approval_evidence_may_be_insufficient"
    if change_class == "replay_change" and set(_list(before)) - set(_list(after)):
        return "replay_evidence_obligations_removed"
    if change_class == "capability_removed":
        return "removed_capability_no_longer_projected_admissible"
    if change_class == "delegation_change":
        return "delegation_evidence_requires_boundary_review"
    if path == "ai.autonomy_posture" and change_class == "relaxed_control":
        return "ai_autonomy_scope_widened_requires_authority_review"
    if path.startswith("execution.") or change_class == "scope_expansion":
        return "execution_boundary_expanded"
    if change_class == "identity_change":
        return "identity_continuity_requires_revalidation"
    return "no_admissibility_change_projected"


def _unsafe_observations(change: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    change_class = change.get("change_class")
    path = str(change.get("semantic_path") or "")
    before = change.get("before")
    after = change.get("after")
    if change_class == "continuity_change":
        observations.append(_unsafe("resumed_workflow_no_longer_admissible", "Existing resumed workflows should not continue without governance revalidation."))
    if change_class == "approval_weakened":
        observations.append(_unsafe("independent_approval_requirements_weakened", "Prior approval posture should be reviewed because approval controls were weakened."))
    if change_class == "approval_strengthened":
        observations.append(_unsafe("approval_evidence_stale", "Existing approval evidence may be insufficient under the new authority meaning."))
    if change_class == "replay_change" and set(_list(before)) - set(_list(after)):
        observations.append(_unsafe("evidence_obligations_removed", "Replay evidence obligations were removed; relying on reduced evidence may weaken continuity review."))
    if change_class == "delegation_change":
        observations.append(_unsafe("delegated_authority_boundary_changed", "Delegated authority evidence should be reviewed against the new delegation boundary."))
    if path == "ai.autonomy_posture" and change_class == "relaxed_control":
        observations.append(_unsafe("ai_autonomy_scope_widened", "AI autonomy expanded; human authority boundaries should be revalidated before relying on prior posture."))
    if path.startswith("execution.") or change_class == "scope_expansion":
        observations.append(_unsafe("execution_boundary_expanded", "The execution boundary or governed scope expanded; prior continuity assumptions may not cover the new surface."))
    if change_class == "identity_change":
        observations.append(_unsafe("identity_continuity_broken", "Identity continuity evidence should be revalidated against the changed authority role set."))
    if change_class == "capability_removed":
        observations.append(_unsafe("removed_capability_reliance", "Executions relying on the removed capability require prior-version lineage review."))
    return observations


def _lifecycle_invalidations(consequence_chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    invalidations = []
    for consequence in consequence_chain:
        for observation in consequence["unsafe_observations"]:
            invalidations.append(
                {
                    "schema_version": "lifecycle_invalidation_observation.v1",
                    "invalidation_type": observation["unsafe_type"],
                    "severity": observation["severity"],
                    "summary": observation["summary"],
                    "source_change_paths": [consequence["semantic_change"]["semantic_path"]],
                }
            )
    return _dedupe_dicts(invalidations, ("invalidation_type", "summary"))


def _replay_continuity_projection(
    semantic_authority_diff: dict[str, Any],
    consequence_chain: list[dict[str, Any]],
) -> dict[str, Any]:
    warnings = list(semantic_authority_diff.get("replay_compatibility_warnings") or [])
    observations = [
        consequence["continuity_impact"]
        for consequence in consequence_chain
        if consequence["continuity_impact"] in {
            "revalidation_required",
            "replay_continuity_degraded",
            "prior_execution_lineage_required",
            "approval_evidence_may_be_stale",
            "authority_evidence_revalidation_required",
        }
    ]
    if any(item == "replay_continuity_degraded" for item in observations):
        posture = "invalidated"
    elif any(item in {"revalidation_required", "prior_execution_lineage_required"} for item in observations):
        posture = "revalidation_required"
    elif warnings:
        posture = "review_required"
    else:
        posture = "stable"
    return {
        "schema_version": "replay_continuity_projection.v1",
        "posture": posture,
        "existing_workflows_need_revalidation": posture in {"invalidated", "revalidation_required"},
        "observations": _unique([*observations, *warnings]),
    }


def _authority_supersession_consequences(consequence_chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for consequence in consequence_chain:
        impact = consequence["continuity_impact"]
        if impact in {"revalidation_required", "prior_execution_lineage_required", "execution_boundary_review_required"}:
            values.append(
                {
                    "schema_version": "authority_supersession_consequence.v1",
                    "consequence_type": impact,
                    "summary": consequence["operational_consequence"],
                    "source_change_path": consequence["semantic_change"]["semantic_path"],
                }
            )
    return _dedupe_dicts(values, ("consequence_type", "source_change_path"))


def _drift_detection_surfaces(consequence_chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    surfaces = []
    for consequence in consequence_chain:
        change = consequence["semantic_change"]
        if consequence["continuity_impact"] == "none" and change["change_class"] not in {"scope_expansion", "relaxed_control"}:
            continue
        surfaces.append(
            {
                "schema_version": "semantic_drift_surface.v1",
                "drift_surface": _drift_surface(change["semantic_path"], change["change_class"]),
                "severity": _governance_severity(change["severity"]),
                "summary": consequence["operational_consequence"],
                "source_change_path": change["semantic_path"],
            }
        )
    return _dedupe_dicts(surfaces, ("drift_surface", "source_change_path"))


def _execution_admissibility_projection(consequence_chain: list[dict[str, Any]]) -> dict[str, Any]:
    observations = _unique(
        consequence["execution_admissibility_projection"]
        for consequence in consequence_chain
        if consequence["execution_admissibility_projection"] != "no_admissibility_change_projected"
    )
    if any(item in observations for item in ("replay_evidence_obligations_removed", "ai_autonomy_scope_widened_requires_authority_review")):
        posture = "potentially_weakened"
    elif observations:
        posture = "changed"
    else:
        posture = "unchanged"
    return {
        "schema_version": "execution_admissibility_projection.v1",
        "projection_posture": posture,
        "admissibility_observations": observations,
        "runtime_enforced_by": "Guard/Cloud",
        "non_goals": [
            "does_not_determine_runtime_admissibility",
            "does_not_execute_guard",
            "does_not_block_execution",
        ],
    }


def _guard_policy_projection(
    semantic_authority_diff: dict[str, Any],
    consequence_chain: list[dict[str, Any]],
) -> dict[str, Any]:
    source = semantic_authority_diff.get("guard_compatibility_projection") or {}
    obligations = _unique(source.get("new_enforcement_obligations") or [])
    projected_changes = _unique(
        consequence["execution_admissibility_projection"]
        for consequence in consequence_chain
        if consequence["execution_admissibility_projection"] != "no_admissibility_change_projected"
    )
    return {
        "schema_version": "guard_policy_projection_change.v1",
        "projection_posture": "changed" if obligations or projected_changes else "unchanged",
        "enforcement_changes": obligations,
        "admissibility_projection_changes": projected_changes,
        "non_goals": [
            "does_not_invoke_guard",
            "does_not_compile_runtime_policy",
            "does_not_evaluate_execution",
        ],
    }


def _unsafe_now(
    consequence_chain: list[dict[str, Any]],
    replay_projection: dict[str, Any],
    guard_projection: dict[str, Any],
) -> list[dict[str, Any]]:
    observations = [
        observation
        for consequence in consequence_chain
        for observation in consequence["unsafe_observations"]
    ]
    if replay_projection["posture"] == "invalidated":
        observations.append(_unsafe("replay_continuity_invalidated", "Replay continuity is invalidated until evidence obligations are reviewed."))
    if guard_projection["projection_posture"] == "changed":
        observations.append(_unsafe("guard_policy_projection_changed", "Guard-facing enforcement projection changed; runtime policy consumers require review before relying on prior assumptions.", "warning"))
    return _dedupe_dicts(observations, ("unsafe_type", "summary"))


def _unsafe(unsafe_type: str, summary: str, severity: str = "continuity_risk") -> dict[str, Any]:
    return {
        "schema_version": "unsafe_governance_observation.v1",
        "unsafe_type": unsafe_type,
        "severity": severity,
        "summary": summary,
    }


def _drift_surface(path: str, change_class: str) -> str:
    if path.startswith("continuity."):
        return "continuity_semantics"
    if path.startswith("replay."):
        return "replay_obligations"
    if path.startswith("approval."):
        return "approval_evidence"
    if path.startswith("identity."):
        return "identity_continuity"
    if path.startswith("execution."):
        return "execution_boundary"
    if path.startswith("ai."):
        return "ai_autonomy"
    if change_class == "delegation_change":
        return "delegated_authority"
    if change_class.startswith("scope"):
        return "governed_scope"
    return "semantic_meaning"


def _governance_severity(severity: str) -> str:
    if severity == "breaking-governance-change":
        return "authority_conflict"
    if severity == "high-impact":
        return "continuity_risk"
    if severity == "moderate":
        return "warning"
    return "info"


def _first(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return next((item for item in items if isinstance(item, str) and item), "")


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, set):
        return sorted(value)
    return [value]


def _unique(items: list[Any]) -> list[Any]:
    result = []
    seen = set()
    for item in items:
        key = repr(item)
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_dicts(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in items:
        key = tuple(item.get(part) for part in keys)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
