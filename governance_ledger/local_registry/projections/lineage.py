"""Lineage projections for local registry state."""

from __future__ import annotations

from typing import Any

from governance_ledger.local_registry.projections.registry import build_authority_drift_indicators
from governance_ledger.local_registry.projections.timeline import build_timeline_projection

AUTHORITY_LINEAGE_PROJECTION_V1 = "authority_lineage_projection.v1"


def build_authority_lineage_projection(
    *,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic authority lineage projection across registry entries."""
    ordered = sorted(entries, key=_lineage_sort_key)
    nodes = [_lineage_node(entry) for entry in ordered]
    edges = _lineage_edges(ordered)
    drift_indicators: list[dict[str, Any]] = []
    for previous, current in zip(ordered, ordered[1:]):
        drift_indicators.extend(build_authority_drift_indicators(previous, current))
    return {
        "schema_version": AUTHORITY_LINEAGE_PROJECTION_V1,
        "authority_family": _authority_family(ordered[0]["authority_ref"]) if ordered else None,
        "nodes": nodes,
        "edges": edges,
        "drift_indicators": drift_indicators,
        "timeline": [
            build_timeline_projection(
                authority_ref=entry["authority_ref"],
                lifecycle_events=entry.get("lifecycle_events") or entry.get("lifecycle_timeline") or [],
            )
            for entry in ordered
        ],
    }


def _lineage_node(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority_ref": entry["authority_ref"],
        "authority_version": entry.get("authority_version") or _version_from_ref(entry["authority_ref"]),
        "status": entry.get("status"),
        "continuity_posture": entry.get("continuity_posture"),
        "replay_readiness": entry.get("replay_readiness"),
        "latest_receipt_hash": entry.get("latest_receipt_hash")
        or (entry.get("publication_receipt") or {}).get("receipt_hash"),
        "supersedes": entry.get("supersedes"),
        "superseded_by": entry.get("superseded_by"),
    }


def _lineage_edges(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = {entry["authority_ref"] for entry in entries}
    edges = []
    for previous, current in zip(entries, entries[1:]):
        edges.append(
            {
                "from": previous["authority_ref"],
                "to": current["authority_ref"],
                "relationship": "version_successor",
            }
        )
    for entry in entries:
        if entry.get("superseded_by") in refs:
            edges.append(
                {
                    "from": entry["authority_ref"],
                    "to": entry["superseded_by"],
                    "relationship": "superseded_by",
                }
            )
    return _dedupe_edges(edges)


def _dedupe_edges(edges: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for edge in edges:
        key = (edge["from"], edge["to"], edge["relationship"])
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result


def _lineage_sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    return (_authority_family(entry["authority_ref"]), entry.get("authority_version") or _version_from_ref(entry["authority_ref"]))


def _authority_family(authority_ref: str) -> str:
    return authority_ref.split("@", 1)[0]


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
