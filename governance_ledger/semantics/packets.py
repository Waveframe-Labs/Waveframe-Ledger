"""Deterministic governance review packet derivation."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from governance_ledger.schema_versions import GOVERNANCE_REVIEW_PACKET_V1

NON_GOALS = [
    "does_not_change_execution_outcome",
    "does_not_mutate_evidence",
    "does_not_alter_replay",
    "does_not_bypass_guard",
]


def build_governance_review_packet(
    *,
    authority_contract: dict[str, Any],
    governance_impact_preview: dict[str, Any],
    authority_diff_impact: dict[str, Any] | None = None,
    execution_evidence: dict[str, Any] | None = None,
    review_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return governance_review_packet.v1 from semantic governance inputs."""
    authority = copy.deepcopy(authority_contract)
    preview = copy.deepcopy(governance_impact_preview)
    diff = copy.deepcopy(authority_diff_impact) if authority_diff_impact is not None else None
    evidence = copy.deepcopy(execution_evidence) if execution_evidence is not None else {}
    metadata = copy.deepcopy(review_metadata) if review_metadata is not None else {}

    authority_ref = _authority_ref(authority)
    immutable_inputs = {
        "authority_hash": authority.get("contract_hash") or _artifact_hash(authority),
        "preview_hash": _artifact_hash(preview),
        "diff_hash": _artifact_hash(diff) if diff is not None else None,
    }
    packet_body = {
        "schema_version": GOVERNANCE_REVIEW_PACKET_V1,
        "authority_ref": authority_ref,
        "operational_state": _operational_state(evidence, metadata),
        "consequence_summary": _consequence_summary(preview, diff),
        "protected_resource": _protected_resource(authority, evidence),
        "governed_action": _governed_action(authority, evidence),
        "continuity_signals": _continuity_signals(preview, diff, evidence),
        "timeline": _timeline(evidence, metadata),
        "immutable_inputs": immutable_inputs,
        "review_context": {
            "disposition": metadata.get("disposition"),
            "annotations": _annotations(metadata),
        },
        "non_goals": list(NON_GOALS),
    }
    return {
        "schema_version": packet_body["schema_version"],
        "packet_id": _packet_id(packet_body),
        "authority_ref": packet_body["authority_ref"],
        "operational_state": packet_body["operational_state"],
        "consequence_summary": packet_body["consequence_summary"],
        "protected_resource": packet_body["protected_resource"],
        "governed_action": packet_body["governed_action"],
        "continuity_signals": packet_body["continuity_signals"],
        "timeline": packet_body["timeline"],
        "immutable_inputs": packet_body["immutable_inputs"],
        "review_context": packet_body["review_context"],
        "non_goals": packet_body["non_goals"],
    }


def format_governance_review_packet(packet: dict[str, Any]) -> str:
    """Format a governance review packet for CLI display."""
    return "\n".join(
        [
            "[Governance Review Packet]",
            "",
            f"Packet: {packet['packet_id']}",
            f"Authority: {packet['authority_ref']}",
            f"Operational State: {packet['operational_state']}",
            "",
            "Consequence Summary:",
            f"  {packet['consequence_summary']}",
            "",
            "Protected Resource:",
            f"  {packet['protected_resource']}",
            "",
            "Governed Action:",
            f"  {packet['governed_action']}",
            "",
            "Continuity Signals:",
            *_indented(packet.get("continuity_signals", [])),
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


def _operational_state(evidence: dict[str, Any], metadata: dict[str, Any]) -> str:
    for source in (metadata, evidence):
        for field in ("operational_state", "state", "status", "decision"):
            value = source.get(field)
            if isinstance(value, str) and value:
                return value
    return "review_ready"


def _consequence_summary(preview: dict[str, Any], diff: dict[str, Any] | None) -> str:
    consequences = []
    for field in ("operational_consequences", "enforcement_behavior"):
        consequences.extend(_string_items(preview.get(field)))
    if diff is not None:
        consequences.extend(_string_items(diff.get("operational_implications")))
        consequences.extend(_string_items(diff.get("escalation_impact")))
    if not consequences:
        return "No semantic consequences were derived from the supplied governance inputs."
    return " ".join(_unique(consequences))


def _protected_resource(authority: dict[str, Any], evidence: dict[str, Any]) -> str:
    for source in (evidence, authority):
        for field in ("protected_resource", "resource", "target"):
            value = source.get(field)
            if isinstance(value, str) and value:
                return value
    scope = authority.get("scope")
    if isinstance(scope, dict):
        for field in ("resource", "description", "domain", "name"):
            value = scope.get(field)
            if isinstance(value, str) and value:
                return value
    return "unspecified"


def _governed_action(authority: dict[str, Any], evidence: dict[str, Any]) -> str:
    for source in (evidence, authority):
        for field in ("governed_action", "action"):
            value = source.get(field)
            if isinstance(value, str) and value:
                return value
    actions = authority.get("governed_actions")
    if isinstance(actions, list):
        action_items = sorted(item for item in actions if isinstance(item, str) and item)
        if action_items:
            return action_items[0]
    return "unspecified"


def _continuity_signals(
    preview: dict[str, Any],
    diff: dict[str, Any] | None,
    evidence: dict[str, Any],
) -> list[str]:
    signals = []
    signals.extend(_string_items(preview.get("lifecycle_implications")))
    if diff is not None:
        signals.extend(_string_items(diff.get("lifecycle_continuity_implications")))
        signals.extend(_string_items(diff.get("replay_continuity_implications")))
    signals.extend(_string_items(evidence.get("continuity_signals")))
    return _unique(signals)


def _timeline(evidence: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    entries.extend(_timeline_entries("execution_evidence", evidence.get("timeline")))
    entries.extend(_timeline_entries("review_metadata", metadata.get("timeline")))
    if isinstance(evidence.get("observed_at"), str):
        entries.append(
            {
                "source": "execution_evidence",
                "event": "evidence_observed",
                "timestamp": evidence["observed_at"],
                "detail": evidence.get("evidence_id"),
            }
        )
    if isinstance(metadata.get("reviewed_at"), str):
        entries.append(
            {
                "source": "review_metadata",
                "event": "review_recorded",
                "timestamp": metadata["reviewed_at"],
                "detail": metadata.get("reviewed_by"),
            }
        )
    return sorted(entries, key=lambda item: _canonical_json(item))


def _timeline_entries(source: str, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = []
    for item in value:
        if isinstance(item, str):
            entries.append({"source": source, "event": item, "timestamp": None, "detail": None})
        elif isinstance(item, dict):
            entries.append(
                {
                    "source": source,
                    "event": item.get("event"),
                    "timestamp": item.get("timestamp"),
                    "detail": item.get("detail"),
                }
            )
    return entries


def _annotations(metadata: dict[str, Any]) -> list[Any]:
    annotations = metadata.get("annotations")
    if not isinstance(annotations, list):
        return []
    return sorted(copy.deepcopy(annotations), key=_canonical_json)


def _artifact_hash(artifact: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(artifact).encode("utf-8")).hexdigest()


def _packet_id(packet_body: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(packet_body).encode("utf-8")).hexdigest()
    return f"grp_{digest[:24]}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _string_items(value: Any) -> list[str]:
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
