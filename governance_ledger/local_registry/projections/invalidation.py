"""Projection invalidation semantics for local registry state."""

from __future__ import annotations

from typing import Any

PROJECTION_INVALIDATION_PLAN_V1 = "projection_invalidation_plan.v1"

INVALIDATION_RULES = {
    "draft_updated": {
        "invalidates": [
            "authority_workspace_projection.v1",
            "authority_operational_summary.v1",
            "governance_continuity_projection.v1",
            "diagnostic_rollup.v1",
        ],
        "persists": ["authority_registry_entry.v1", "authority_lifecycle_event.v1", "publication_receipt.v1"],
    },
    "impact_reviewed": {
        "invalidates": [
            "authority_workspace_projection.v1",
            "authority_operational_summary.v1",
            "governance_activity_projection.v1",
            "governance_timeline_projection.v1",
            "governance_continuity_projection.v1",
        ],
        "persists": ["authority_lifecycle_event.v1"],
    },
    "bundle_exported": {
        "invalidates": [
            "authority_workspace_projection.v1",
            "authority_registry_entry.v1",
            "authority_operational_summary.v1",
            "registry_health_projection.v1",
            "governance_activity_projection.v1",
            "governance_timeline_projection.v1",
            "governance_continuity_projection.v1",
        ],
        "persists": ["authority_lifecycle_event.v1", "publication_receipt.v1"],
    },
    "authority_registered": {
        "invalidates": [
            "authority_registry_entry.v1",
            "active_authority_projection.v1",
            "authority_lineage_projection.v1",
            "registry_health_projection.v1",
            "governance_activity_projection.v1",
            "governance_timeline_projection.v1",
            "governance_continuity_projection.v1",
        ],
        "persists": ["authority_lifecycle_event.v1", "publication_receipt.v1"],
    },
    "lineage_changed": {
        "invalidates": [
            "authority_lineage_projection.v1",
            "active_authority_projection.v1",
            "registry_health_projection.v1",
            "authority_operational_summary.v1",
            "governance_activity_projection.v1",
            "governance_timeline_projection.v1",
            "governance_continuity_projection.v1",
        ],
        "persists": ["authority_lifecycle_event.v1", "publication_receipt.v1"],
    },
    "authority_superseded": {
        "invalidates": [
            "authority_lineage_projection.v1",
            "active_authority_projection.v1",
            "registry_health_projection.v1",
            "authority_operational_summary.v1",
            "governance_activity_projection.v1",
            "governance_timeline_projection.v1",
            "governance_continuity_projection.v1",
        ],
        "persists": ["authority_lifecycle_event.v1", "publication_receipt.v1"],
    },
    "authority_revoked": {
        "invalidates": [
            "authority_lineage_projection.v1",
            "active_authority_projection.v1",
            "registry_health_projection.v1",
            "authority_operational_summary.v1",
            "governance_activity_projection.v1",
            "governance_timeline_projection.v1",
            "governance_continuity_projection.v1",
        ],
        "persists": ["authority_lifecycle_event.v1", "publication_receipt.v1"],
    },
    "diagnostics_stale": {
        "invalidates": [
            "diagnostic_rollup.v1",
            "authority_workspace_projection.v1",
            "authority_operational_summary.v1",
            "registry_health_projection.v1",
            "governance_activity_projection.v1",
            "governance_timeline_projection.v1",
            "governance_continuity_projection.v1",
        ],
        "persists": ["authority_lifecycle_event.v1", "publication_receipt.v1"],
    },
    "replay_posture_invalidated": {
        "invalidates": [
            "authority_operational_summary.v1",
            "registry_health_projection.v1",
            "governance_activity_projection.v1",
            "governance_timeline_projection.v1",
            "governance_continuity_projection.v1",
        ],
        "persists": ["publication_receipt.v1", "authority_lifecycle_event.v1"],
    },
}


def build_projection_invalidation_plan(
    *,
    change_type: str,
    authority_ref: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic projection invalidation plan for a registry change."""
    if change_type not in INVALIDATION_RULES:
        raise ValueError(f"unsupported projection invalidation change_type: {change_type}")
    rule = INVALIDATION_RULES[change_type]
    return {
        "schema_version": PROJECTION_INVALIDATION_PLAN_V1,
        "change_type": change_type,
        "authority_ref": authority_ref,
        "invalidated_projections": sorted(rule["invalidates"]),
        "historically_persisted_artifacts": sorted(rule["persists"]),
        "recompute": True,
    }
