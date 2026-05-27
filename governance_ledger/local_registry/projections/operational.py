"""Operational authority summary projection."""

from __future__ import annotations

from typing import Any

from governance_ledger.local_registry.projections.lineage import build_authority_lineage_projection

AUTHORITY_OPERATIONAL_SUMMARY_V1 = "authority_operational_summary.v1"


def build_authority_operational_summary(
    *,
    authority: dict[str, Any],
    bundle: dict[str, Any],
    workspace_projection: dict[str, Any],
    registry_entry: dict[str, Any] | None = None,
    lineage_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the canonical detail-view projection for an authority."""
    authority_ref = bundle["authority_ref"]
    lineage_projection = build_authority_lineage_projection(entries=lineage_entries or ([registry_entry] if registry_entry else []))
    drift = [
        item
        for item in lineage_projection.get("drift_indicators", [])
        if item.get("authority_ref") == authority_ref or item.get("previous_authority_ref") == authority_ref
    ]
    return {
        "schema_version": AUTHORITY_OPERATIONAL_SUMMARY_V1,
        "authority_ref": authority_ref,
        "authority_version": _version_from_ref(authority_ref),
        "protected_resource": authority.get("protected_resource") or registry_entry_value(registry_entry, "protected_resource"),
        "governed_action": (authority.get("governed_actions") or [registry_entry_value(registry_entry, "governed_action")])[0],
        "lifecycle": {
            "status": registry_entry_value(registry_entry, "status") or workspace_projection.get("lifecycle_posture"),
            "events": registry_entry_value(registry_entry, "lifecycle_events") or [],
        },
        "drift_summary": drift,
        "replay_readiness": _replay_readiness(registry_entry, workspace_projection),
        "governance_meaning": [
            workspace_projection["operational_change"],
            workspace_projection["continuity_posture"],
            workspace_projection["replay_posture"],
        ],
        "relationship_graph": {
            "nodes": lineage_projection.get("nodes", []),
            "edges": lineage_projection.get("edges", []),
        },
    }


def registry_entry_value(entry: dict[str, Any] | None, field: str) -> Any:
    if not entry:
        return None
    if field == "protected_resource":
        return entry.get("protected_resource") or entry.get("governed_resource")
    return entry.get(field)


def _replay_readiness(
    registry_entry: dict[str, Any] | None,
    workspace_projection: dict[str, Any],
) -> dict[str, Any]:
    receipt = (registry_entry or {}).get("publication_receipt") or {}
    immutable_inputs = (registry_entry or {}).get("immutable_inputs") or {}
    lineage = (registry_entry or {}).get("lineage") or {}
    manifest_hash = immutable_inputs.get("manifest_hash") or receipt.get("manifest_hash")
    semantic_hashes = [
        immutable_inputs.get("preview_hash"),
        immutable_inputs.get("review_packet_hashes"),
        immutable_inputs.get("diff_hash"),
    ]
    return {
        "receipt_present": bool(receipt.get("receipt_hash") or (registry_entry or {}).get("latest_receipt_hash")),
        "semantic_hashes_aligned": any(bool(item) for item in semantic_hashes),
        "lineage_complete": bool(lineage),
        "manifest_aligned": bool(manifest_hash),
        "summary": workspace_projection["replay_posture"],
    }


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
