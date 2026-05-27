"""Workspace projections over local registry state."""

from __future__ import annotations

from typing import Any

from governance_ledger.local_registry.projections.diagnostics import build_diagnostic_rollup_projection

AUTHORITY_WORKSPACE_PROJECTION_V1 = "authority_workspace_projection.v1"


def build_authority_workspace_projection(
    *,
    authority: dict[str, Any],
    preview: dict[str, Any],
    bundle: dict[str, Any],
    diagnostics: list[dict[str, Any]],
    publication_meaning: str,
    publication_summary: str,
    operational_change: str,
    continuity_posture: str,
    lifecycle_effect: str,
    registry_entry: dict[str, Any] | None = None,
    publication_receipt: dict[str, Any] | None = None,
    timeline: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the canonical UI-facing projection for one authority workspace."""
    authority_ref = bundle["authority_ref"]
    status = registry_entry.get("status") if registry_entry else "draft"
    receipt_hash = publication_receipt.get("receipt_hash") if publication_receipt else None
    rollup = build_diagnostic_rollup_projection(authority_ref=authority_ref, diagnostics=diagnostics)
    return {
        "schema_version": AUTHORITY_WORKSPACE_PROJECTION_V1,
        "authority_ref": authority_ref,
        "authority_version": _version_from_ref(authority_ref),
        "lifecycle_posture": status,
        "review_state": "impact_reviewed" if preview else "impact_pending",
        "export_state": "exported" if publication_receipt else "not_exported",
        "registration_state": "registered" if registry_entry else "not_registered",
        "operational_change": operational_change,
        "continuity_posture": continuity_posture,
        "lifecycle_effect": lifecycle_effect,
        "publication_meaning": publication_meaning,
        "publication_summary": publication_summary,
        "registry_posture": _registry_posture(registry_entry, publication_receipt),
        "replay_posture": _replay_posture(receipt_hash),
        "diagnostic_rollup": rollup,
        "timeline": timeline or [],
        "semantic_sources": {
            "authority": authority["schema_version"],
            "preview": preview["schema_version"],
            "bundle": bundle["schema_version"],
        },
    }


def _registry_posture(
    registry_entry: dict[str, Any] | None,
    publication_receipt: dict[str, Any] | None,
) -> str:
    if registry_entry:
        return "Authority registered locally. Registry lifecycle now has a registered authority event."
    if publication_receipt:
        return "Bundle exported. Authority is not registered locally yet."
    return "Bundle ready to export. Authority not registered locally."


def _replay_posture(receipt_hash: str | None) -> str:
    if receipt_hash:
        return f"Replay review can bind to publication receipt {receipt_hash}."
    return "Export will create publication receipt evidence that future replay can bind against."


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
