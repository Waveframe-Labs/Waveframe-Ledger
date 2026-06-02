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
    PUBLICATION_RECEIPT_V1,
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
    semantic_commit_bundle: dict[str, Any] | None = None,
    compiled_authority_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return authority_bundle.v1 from published governance artifacts."""
    authority = copy.deepcopy(authority_contract)
    manifest = copy.deepcopy(publication_manifest)
    preview = copy.deepcopy(governance_impact_preview)
    diff = copy.deepcopy(authority_diff_impact) if authority_diff_impact is not None else None
    packets = copy.deepcopy(governance_review_packets) if governance_review_packets is not None else []
    semantic_commit = copy.deepcopy(semantic_commit_bundle) if semantic_commit_bundle is not None else None
    compiled_contract = copy.deepcopy(compiled_authority_contract) if compiled_authority_contract is not None else None

    authority_ref = _authority_ref(authority)
    contract_hash = _contract_hash(authority)
    semantic_commit_hash = _semantic_commit_hash(semantic_commit)
    compiled_contract_hash = _compiled_contract_hash(compiled_contract)
    publication_id = _publication_id(manifest, authority_ref, contract_hash)
    immutable_inputs = _immutable_inputs(authority, manifest, preview, diff, packets, semantic_commit, compiled_contract)
    semantic_artifacts = _semantic_artifacts(preview, diff, semantic_commit, compiled_contract)
    review_packets = _review_packets(packets)

    return {
        "schema_version": AUTHORITY_BUNDLE_V1,
        "publication_id": publication_id,
        "authority_ref": authority_ref,
        "contract_hash": contract_hash,
        "semantic_commit_hash": semantic_commit_hash,
        "compiled_contract_hash": compiled_contract_hash,
        "authority_contract": authority,
        "semantic_commit_bundle": semantic_commit,
        "compiled_authority_contract": compiled_contract,
        "publication_manifest": manifest,
        "governance_impact_preview": preview,
        "authority_diff_impact": diff,
        "governance_review_packets": packets,
        "semantic_artifacts": semantic_artifacts,
        "review_packets": review_packets,
        "lineage": _lineage(authority, manifest),
        "provenance": _provenance(manifest),
        "schema_compatibility": _schema_compatibility(authority, manifest, preview, diff, packets, semantic_commit, compiled_contract),
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


def build_publication_receipt(
    *,
    authority_bundle: dict[str, Any],
    published_at: str,
    readiness_confirmations: dict[str, bool] | None = None,
    publication_notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return publication_receipt.v1 evidence for an exported authority bundle."""
    bundle = copy.deepcopy(authority_bundle)
    confirmations = copy.deepcopy(readiness_confirmations) if readiness_confirmations is not None else {}
    notes = copy.deepcopy(publication_notes) if publication_notes is not None else []
    manifest = bundle.get("publication_manifest") if isinstance(bundle.get("publication_manifest"), dict) else {}
    semantic_artifacts = bundle.get("semantic_artifacts") if isinstance(bundle.get("semantic_artifacts"), list) else []
    immutable_inputs = bundle.get("immutable_inputs") if isinstance(bundle.get("immutable_inputs"), dict) else {}
    schema_compatibility = bundle.get("schema_compatibility") if isinstance(bundle.get("schema_compatibility"), dict) else {}

    receipt = {
        "schema_version": PUBLICATION_RECEIPT_V1,
        "receipt_id": _receipt_id(bundle, published_at),
        "publication_id": bundle.get("publication_id"),
        "authority_ref": bundle.get("authority_ref"),
        "published_at": published_at,
        "published_by": (bundle.get("provenance") or {}).get("published_by") or manifest.get("published_by"),
        "bundle_hash": _artifact_hash(bundle),
        "contract_hash": bundle.get("contract_hash"),
        "manifest_hash": immutable_inputs.get("manifest_hash") or _artifact_hash(manifest),
        "semantic_artifact_hashes": _semantic_artifact_hashes(semantic_artifacts, immutable_inputs),
        "review_packet_hashes": list(immutable_inputs.get("review_packet_hashes") or []),
        "semantic_commit_hash": bundle.get("semantic_commit_hash") or immutable_inputs.get("semantic_commit_hash"),
        "compiled_contract_hash": bundle.get("compiled_contract_hash") or immutable_inputs.get("compiled_contract_hash"),
        "lineage_continuity": _lineage_continuity(bundle),
        "compatibility_posture": _compatibility_posture(schema_compatibility),
        "readiness_confirmations": _readiness_confirmations(confirmations),
        "publication_notes": _publication_notes(notes),
        "semantic_compatibility_warnings": _semantic_compatibility_warnings(bundle),
        "immutable_inputs": {
            "authority_hash": immutable_inputs.get("authority_hash"),
            "manifest_hash": immutable_inputs.get("manifest_hash"),
            "preview_hash": immutable_inputs.get("preview_hash"),
            "diff_hash": immutable_inputs.get("diff_hash"),
            "semantic_commit_hash": immutable_inputs.get("semantic_commit_hash"),
            "compiled_contract_hash": immutable_inputs.get("compiled_contract_hash"),
            "bundle_hash": _artifact_hash(bundle),
        },
        "non_goals": [
            "does_not_deploy_authority",
            "does_not_approve_authority",
            "does_not_reject_publication",
            "does_not_call_guard",
            "does_not_call_cloud",
            "does_not_evaluate_admissibility",
        ],
    }
    receipt["receipt_hash"] = _artifact_hash(receipt)
    return receipt


def _authority_ref(authority: dict[str, Any]) -> str:
    contract_id = authority.get("contract_id")
    contract_version = authority.get("contract_version")
    if not isinstance(contract_id, str) or not contract_id:
        raise ValueError("Authority contract missing required field: contract_id")
    if not isinstance(contract_version, str) or not contract_version:
        raise ValueError("Authority contract missing required field: contract_version")
    return f"{contract_id}@{contract_version}"


def _receipt_id(bundle: dict[str, Any], published_at: str) -> str:
    digest = hashlib.sha256(
        f"{bundle.get('publication_id')}:{bundle.get('authority_ref')}:{published_at}".encode("utf-8")
    ).hexdigest()
    return f"receipt_{digest[:12]}"


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
    semantic_commit: dict[str, Any] | None,
    compiled_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "authority_hash": _contract_hash(authority),
        "manifest_hash": _artifact_hash(manifest),
        "preview_hash": _artifact_hash(preview),
        "diff_hash": _artifact_hash(diff) if diff is not None else None,
        "review_packet_hashes": [_artifact_hash(packet) for packet in packets],
        "semantic_commit_hash": _semantic_commit_hash(semantic_commit),
        "compiled_contract_hash": _compiled_contract_hash(compiled_contract),
    }


def _semantic_artifacts(
    preview: dict[str, Any],
    diff: dict[str, Any] | None,
    semantic_commit: dict[str, Any] | None,
    compiled_contract: dict[str, Any] | None,
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
    if semantic_commit is not None:
        artifacts.append(
            {
                "artifact_type": "semantic_commit_bundle.v1",
                "artifact_hash": _semantic_commit_hash(semantic_commit),
            }
        )
    if compiled_contract is not None:
        artifacts.append(
            {
                "artifact_type": "compiled_authority_contract.v1",
                "artifact_hash": _compiled_contract_hash(compiled_contract),
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
    semantic_commit: dict[str, Any] | None,
    compiled_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    artifacts = {
        "authority_contract": authority.get("schema_version") or "authority_contract.v1",
        "publication_manifest": manifest.get("schema_version") or PUBLICATION_MANIFEST_V1,
        "governance_impact_preview": preview.get("schema_version"),
        "authority_diff_impact": diff.get("schema_version") if diff is not None else None,
        "governance_review_packets": [packet.get("schema_version") for packet in packets],
        "semantic_commit_bundle": semantic_commit.get("schema_version") if semantic_commit is not None else None,
        "compiled_authority_contract": compiled_contract.get("schema_version") if compiled_contract is not None else None,
    }
    expected = {
        "publication_manifest": PUBLICATION_MANIFEST_V1,
        "governance_impact_preview": GOVERNANCE_IMPACT_PREVIEW_V1,
        "authority_diff_impact": AUTHORITY_DIFF_IMPACT_V1 if diff is not None else None,
        "governance_review_packets": [GOVERNANCE_REVIEW_PACKET_V1 for _ in packets],
        "semantic_commit_bundle": "semantic_commit_bundle.v1" if semantic_commit is not None else None,
        "compiled_authority_contract": "compiled_authority_contract.v1" if compiled_contract is not None else None,
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
        and artifacts["semantic_commit_bundle"] == expected["semantic_commit_bundle"]
        and artifacts["compiled_authority_contract"] == expected["compiled_authority_contract"]
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


def _semantic_artifact_hashes(
    semantic_artifacts: list[Any],
    immutable_inputs: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for artifact in semantic_artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_type = artifact.get("artifact_type")
        artifact_hash = artifact.get("artifact_hash")
        if isinstance(artifact_type, str) and artifact_type and isinstance(artifact_hash, str):
            result[artifact_type] = artifact_hash
    if "governance_impact_preview.v1" not in result and immutable_inputs.get("preview_hash"):
        result["governance_impact_preview.v1"] = immutable_inputs["preview_hash"]
    if immutable_inputs.get("diff_hash"):
        result.setdefault("authority_diff_impact.v1", immutable_inputs["diff_hash"])
    if immutable_inputs.get("semantic_commit_hash"):
        result.setdefault("semantic_commit_bundle.v1", immutable_inputs["semantic_commit_hash"])
    if immutable_inputs.get("compiled_contract_hash"):
        result.setdefault("compiled_authority_contract.v1", immutable_inputs["compiled_contract_hash"])
    return result


def _lineage_continuity(bundle: dict[str, Any]) -> dict[str, Any]:
    lineage = bundle.get("lineage") if isinstance(bundle.get("lineage"), dict) else {}
    return {
        "source_hash_present": bool(lineage.get("source_hash")),
        "compilation_report_hash_present": bool(lineage.get("compilation_report_hash")),
        "lineage_complete": bool(lineage.get("source_hash") and lineage.get("compilation_report_hash")),
    }


def _compatibility_posture(schema_compatibility: dict[str, Any]) -> dict[str, Any]:
    return {
        "compatible": bool(schema_compatibility.get("compatible")),
        "compatibility_mode": schema_compatibility.get("compatibility_mode"),
        "artifacts": copy.deepcopy(schema_compatibility.get("artifacts") or {}),
        "expected": copy.deepcopy(schema_compatibility.get("expected") or {}),
    }


def _readiness_confirmations(confirmations: dict[str, bool]) -> dict[str, bool]:
    keys = [
        "semantic_diagnostics_reviewed",
        "lineage_validated",
        "continuity_posture_reviewed",
        "replay_implications_reviewed",
        "lifecycle_implications_acknowledged",
    ]
    return {key: bool(confirmations.get(key)) for key in keys}


def _publication_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        note_type = note.get("note_type")
        text = note.get("text")
        created_at = note.get("created_at")
        if not isinstance(note_type, str) or not isinstance(text, str) or not text.strip():
            continue
        result.append(
            {
                "note_type": note_type,
                "text": text.strip(),
                "created_at": created_at if isinstance(created_at, str) and created_at else None,
            }
        )
    return result


def _semantic_compatibility_warnings(bundle: dict[str, Any]) -> list[str]:
    diff = bundle.get("authority_diff_impact")
    if not isinstance(diff, dict):
        return []
    warnings = []
    for change in diff.get("changed_governance_rules", []):
        if not isinstance(change, dict):
            continue
        change_type = change.get("change_type")
        escalation_impact = " ".join(_strings(change.get("escalation_impact"))).lower()
        continuity_impact = " ".join(_strings(change.get("continuity_implications"))).lower()
        if change_type == "ESCALATION_THRESHOLD_CHANGED" and "expands" in escalation_impact:
            warnings.append("This authority lowers escalation thresholds relative to prior lineage.")
        if change_type == "ESCALATION_THRESHOLD_CHANGED" and "narrows" in escalation_impact:
            warnings.append("This authority raises escalation thresholds relative to prior lineage.")
        if change_type == "CONTINUITY_REQUIREMENT_CHANGED" or "continuity" in continuity_impact:
            warnings.append("This authority changes continuity semantics for resumed execution.")
    return _unique(warnings)


def _artifact_hash(artifact: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(artifact).encode("utf-8")).hexdigest()


def _semantic_commit_hash(semantic_commit: dict[str, Any] | None) -> str | None:
    if semantic_commit is None:
        return None
    value = semantic_commit.get("semantic_commit_hash") or semantic_commit.get("bundle_hash")
    if isinstance(value, str) and value:
        return value if value.startswith("sha256:") else f"sha256:{value}"
    return _artifact_hash(semantic_commit)


def _compiled_contract_hash(compiled_contract: dict[str, Any] | None) -> str | None:
    if compiled_contract is None:
        return None
    value = compiled_contract.get("contract_hash") or compiled_contract.get("compiled_contract_hash")
    if isinstance(value, str) and value:
        return value if value.startswith("sha256:") else f"sha256:{value}"
    return _artifact_hash(compiled_contract)


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
