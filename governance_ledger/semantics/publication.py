"""Deterministic publishable authority bundle derivation."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from governance_ledger.schema_versions import (
    AUTHORITY_BUNDLE_V1,
    AUTHORITY_DIFF_IMPACT_V1,
    GOVERNANCE_IMPACT_PREVIEW_V1,
    GOVERNANCE_REVIEW_PACKET_V1,
    PUBLICATION_MANIFEST_V1,
)

NON_GOALS = [
    "does_not_deploy_authority",
    "does_not_approve_authority",
    "does_not_change_execution_outcome",
    "does_not_mutate_evidence",
    "does_not_alter_replay",
    "does_not_bypass_guard",
    "does_not_call_cloud",
]


def build_authority_bundle(
    *,
    authority_contract: dict[str, Any],
    publication_manifest: dict[str, Any],
    governance_impact_preview: dict[str, Any],
    authority_diff_impact: dict[str, Any] | None = None,
    governance_review_packets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return authority_bundle.v1 from published governance artifacts."""
    authority = copy.deepcopy(authority_contract)
    manifest = copy.deepcopy(publication_manifest)
    preview = copy.deepcopy(governance_impact_preview)
    diff = copy.deepcopy(authority_diff_impact) if authority_diff_impact is not None else None
    packets = copy.deepcopy(governance_review_packets) if governance_review_packets is not None else []

    authority_ref = _authority_ref(authority)
    contract_hash = _contract_hash(authority)
    publication_id = _publication_id(manifest, authority_ref, contract_hash)
    immutable_inputs = _immutable_inputs(authority, manifest, preview, diff, packets)
    semantic_artifacts = _semantic_artifacts(preview, diff)
    review_packets = _review_packets(packets)

    return {
        "schema_version": AUTHORITY_BUNDLE_V1,
        "publication_id": publication_id,
        "authority_ref": authority_ref,
        "contract_hash": contract_hash,
        "authority_contract": authority,
        "publication_manifest": manifest,
        "governance_impact_preview": preview,
        "authority_diff_impact": diff,
        "governance_review_packets": packets,
        "semantic_artifacts": semantic_artifacts,
        "review_packets": review_packets,
        "lineage": _lineage(authority, manifest),
        "provenance": _provenance(manifest),
        "schema_compatibility": _schema_compatibility(authority, manifest, preview, diff, packets),
        "publication_meaning": _publication_meaning(authority_ref, preview, diff, review_packets),
        "operational_implications": _operational_implications(preview, diff, packets),
        "continuity_implications": _continuity_implications(preview, diff, packets),
        "immutable_inputs": immutable_inputs,
        "non_goals": list(NON_GOALS),
    }


def format_authority_bundle(bundle: dict[str, Any]) -> str:
    """Format an authority bundle for CLI display."""
    return "\n".join(
        [
            "[Authority Bundle]",
            "",
            f"Publication: {bundle['publication_id']}",
            f"Authority: {bundle['authority_ref']}",
            f"Contract hash: {bundle['contract_hash']}",
            "",
            "Publication Meaning:",
            f"  {bundle['publication_meaning']}",
            "",
            "Operational Implications:",
            *_indented(bundle.get("operational_implications", [])),
            "",
            "Continuity Implications:",
            *_indented(bundle.get("continuity_implications", [])),
        ]
    )


def _authority_ref(authority: dict[str, Any]) -> str:
    contract_id = authority.get("contract_id")
    contract_version = authority.get("contract_version")
    if not isinstance(contract_id, str) or not contract_id:
        raise ValueError("Authority contract missing required field: contract_id")
    if not isinstance(contract_version, str) or not contract_version:
        raise ValueError("Authority contract missing required field: contract_version")
    return f"{contract_id}@{contract_version}"


def _contract_hash(authority: dict[str, Any]) -> str:
    contract_hash = authority.get("contract_hash")
    if isinstance(contract_hash, str) and contract_hash:
        return contract_hash if contract_hash.startswith("sha256:") else f"sha256:{contract_hash}"
    return _artifact_hash(authority)


def _publication_id(manifest: dict[str, Any], authority_ref: str, contract_hash: str) -> str:
    value = manifest.get("publication_id")
    if isinstance(value, str) and value:
        return value
    digest = hashlib.sha256(f"{authority_ref}:{contract_hash}".encode("utf-8")).hexdigest()
    return f"pub_semantic_{digest[:12]}"


def _immutable_inputs(
    authority: dict[str, Any],
    manifest: dict[str, Any],
    preview: dict[str, Any],
    diff: dict[str, Any] | None,
    packets: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "authority_hash": _contract_hash(authority),
        "manifest_hash": _artifact_hash(manifest),
        "preview_hash": _artifact_hash(preview),
        "diff_hash": _artifact_hash(diff) if diff is not None else None,
        "review_packet_hashes": [_artifact_hash(packet) for packet in packets],
    }


def _semantic_artifacts(
    preview: dict[str, Any],
    diff: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    artifacts = [
        {
            "artifact_type": GOVERNANCE_IMPACT_PREVIEW_V1,
            "artifact_hash": _artifact_hash(preview),
        }
    ]
    if diff is not None:
        artifacts.append(
            {
                "artifact_type": AUTHORITY_DIFF_IMPACT_V1,
                "artifact_hash": _artifact_hash(diff),
            }
        )
    return artifacts


def _review_packets(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "packet_id": packet.get("packet_id"),
            "packet_hash": _artifact_hash(packet),
            "authority_ref": packet.get("authority_ref"),
            "operational_state": packet.get("operational_state"),
        }
        for packet in packets
    ]


def _lineage(authority: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    authority_lineage = authority.get("lineage") if isinstance(authority.get("lineage"), dict) else {}
    manifest_contract = _manifest_contract_entry(manifest)
    return {
        "authority_lineage": copy.deepcopy(authority_lineage),
        "manifest_contract": copy.deepcopy(manifest_contract),
        "source_hash": authority_lineage.get("source_hash") or manifest_contract.get("source_hash"),
        "compilation_report_hash": (
            authority_lineage.get("compilation_report_hash")
            or manifest_contract.get("compilation_report_hash")
        ),
    }


def _provenance(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "published_at": manifest.get("published_at"),
        "published_by": manifest.get("published_by"),
        "manifest_schema_version": manifest.get("schema_version"),
    }


def _schema_compatibility(
    authority: dict[str, Any],
    manifest: dict[str, Any],
    preview: dict[str, Any],
    diff: dict[str, Any] | None,
    packets: list[dict[str, Any]],
) -> dict[str, Any]:
    artifacts = {
        "authority_contract": authority.get("schema_version") or "authority_contract.v1",
        "publication_manifest": manifest.get("schema_version") or PUBLICATION_MANIFEST_V1,
        "governance_impact_preview": preview.get("schema_version"),
        "authority_diff_impact": diff.get("schema_version") if diff is not None else None,
        "governance_review_packets": [packet.get("schema_version") for packet in packets],
    }
    expected = {
        "publication_manifest": PUBLICATION_MANIFEST_V1,
        "governance_impact_preview": GOVERNANCE_IMPACT_PREVIEW_V1,
        "authority_diff_impact": AUTHORITY_DIFF_IMPACT_V1 if diff is not None else None,
        "governance_review_packets": [GOVERNANCE_REVIEW_PACKET_V1 for _ in packets],
    }
    return {
        "compatibility_mode": "additive_v1",
        "artifacts": artifacts,
        "expected": expected,
        "compatible": _compatible(artifacts, expected),
    }


def _compatible(artifacts: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        artifacts["publication_manifest"] == expected["publication_manifest"]
        and artifacts["governance_impact_preview"] == expected["governance_impact_preview"]
        and artifacts["authority_diff_impact"] == expected["authority_diff_impact"]
        and artifacts["governance_review_packets"] == expected["governance_review_packets"]
    )


def _publication_meaning(
    authority_ref: str,
    preview: dict[str, Any],
    diff: dict[str, Any] | None,
    review_packets: list[dict[str, Any]],
) -> str:
    summary = preview.get("governance_summary")
    if not isinstance(summary, str) or not summary:
        summary = f"{authority_ref} is published as a governance authority."
    clauses = [summary]
    if diff is not None and diff.get("changed_governance_rules"):
        clauses.append("The publication includes semantic impact from authority changes.")
    if review_packets:
        clauses.append("The publication includes review packet context for governed operation.")
    return " ".join(clauses)


def _operational_implications(
    preview: dict[str, Any],
    diff: dict[str, Any] | None,
    packets: list[dict[str, Any]],
) -> list[str]:
    implications = []
    implications.extend(_strings(preview.get("operational_consequences")))
    implications.extend(_strings(preview.get("enforcement_behavior")))
    if diff is not None:
        implications.extend(_strings(diff.get("operational_implications")))
        implications.extend(_strings(diff.get("escalation_impact")))
    for packet in packets:
        summary = packet.get("consequence_summary")
        if isinstance(summary, str) and summary:
            implications.append(summary)
    return _unique(implications)


def _continuity_implications(
    preview: dict[str, Any],
    diff: dict[str, Any] | None,
    packets: list[dict[str, Any]],
) -> list[str]:
    implications = []
    implications.extend(_strings(preview.get("lifecycle_implications")))
    if diff is not None:
        implications.extend(_strings(diff.get("lifecycle_continuity_implications")))
        implications.extend(_strings(diff.get("replay_continuity_implications")))
    for packet in packets:
        implications.extend(_strings(packet.get("continuity_signals")))
    return _unique(implications)


def _manifest_contract_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    contracts = manifest.get("contracts")
    if isinstance(contracts, list) and contracts and isinstance(contracts[0], dict):
        return contracts[0]
    return {}


def _artifact_hash(artifact: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(artifact).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _unique(items: list[str]) -> list[str]:
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
