"""Untrusted, model-agnostic policy translation proposal boundary.

This module deliberately contains no provider client, credential lookup, filesystem
access, or network access.  Provider output is retained only as hash-bound authoring
evidence.  Human-confirmed meaning is replayed through the released v2 domain-policy
publication path.
"""

from __future__ import annotations

import base64
import binascii
import copy
import re
from datetime import datetime
from typing import Any

from governance_ledger.constraint_ir import artifact_hash, validate_format_value
from governance_ledger.domain_packs import (
    REPOSITORY_CHANGES_PACK_ID,
    REPOSITORY_CHANGES_PACK_VERSION,
    REPOSITORY_PATH_FORMAT_ID,
    get_builtin_domain_pack,
)
from governance_ledger.domain_policy import (
    apply_policy_mapping_decision,
    finalize_domain_policy_authority,
    interpret_policy_with_domain_pack,
)
from governance_ledger.publication_provenance import bytes_sha256, canonical_sha256


POLICY_TRANSLATION_PROPOSAL_V1 = "policy_translation_proposal.v1"
POLICY_TRANSLATION_CAPABILITY_CATALOG_V1 = "policy_translation_capability_catalog.v1"
POLICY_TRANSLATION_CONFIRMATION_V1 = "policy_translation_confirmation.v1"
POLICY_TRANSLATION_APPROVAL_V1 = "policy_translation_approval.v1"

_CATALOG_ID = "waveframe.coding-agent.repository-change"
_CATALOG_VERSION = "1.0.0"
_ENFORCEMENT_POINT = "waveframe.guard.repository-change.v1"
_STATUSES = {
    "enforceable_fully_bound",
    "needs_concrete_answer",
    "integration_dependent",
    "unsupported",
    "informational",
}
_LIMITATIONS = {
    None,
    "unavailable_action",
    "unavailable_actor_kind",
    "unavailable_runtime_fact",
    "unavailable_enforcement_point",
    "unavailable_binding_type",
    "cross_repository_adapter_required",
    "other",
}
_CONTROL_SPECS = {
    "acting_role": {
        "mapping_control_id": "acting-role",
        "resource_kind": "repository_change",
        "fact_id": "actor.role",
        "operator": "==",
        "effect": "require",
        "binding_types": {"repository_role"},
        "required_runtime_facts": [
            "actor.role",
            "actor.subject_kind",
            "proposal.action",
            "proposal.resource.kind",
        ],
    },
    "exact_path_access": {
        "mapping_control_id": "exact-path-access",
        "resource_kind": "repository_path",
        "fact_id": "proposal.resource.path",
        "operator": "==",
        "effects": {"allow", "deny"},
        "binding_types": {"repository_exact_path"},
        "required_runtime_facts": [
            "actor.subject_kind",
            "proposal.action",
            "proposal.resource.kind",
            "proposal.resource.path",
        ],
    },
    "prefix_path_access": {
        "mapping_control_id": "prefix-path-access",
        "resource_kind": "repository_path",
        "fact_id": "proposal.resource.path",
        "operator": "starts_with",
        "effects": {"allow", "deny"},
        "binding_types": {"repository_path_prefix"},
        "required_runtime_facts": [
            "actor.subject_kind",
            "proposal.action",
            "proposal.resource.kind",
            "proposal.resource.path",
        ],
    },
}
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")


def get_policy_translation_capability_catalog() -> dict[str, Any]:
    """Return the immutable capabilities implemented by Ledger and Guard v0.16.1.

    The catalog is intentionally the intersection of the repository-change compiler
    and Guard's trusted repository-change fact boundary.  Representable Constraint IR
    features without a released lowering are not advertised.
    """
    pack = get_builtin_domain_pack(
        REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION
    )
    catalog: dict[str, Any] = {
        "schema_version": POLICY_TRANSLATION_CAPABILITY_CATALOG_V1,
        "catalog_id": _CATALOG_ID,
        "catalog_version": _CATALOG_VERSION,
        "domain_pack": _pack_ref(pack),
        "actor_kinds": ["autonomous_agent"],
        "actions": ["modify"],
        "facts": copy.deepcopy(pack["runtime_fact_schema"]["facts"]),
        "operators": ["!=", "==", "starts_with"],
        "binding_types": [
            "repository_exact_path",
            "repository_path_prefix",
            "repository_role",
        ],
        "enforcement_points": [
            {
                "enforcement_point_id": _ENFORCEMENT_POINT,
                "actions": ["modify"],
                "runtime_fact_ids": [
                    item["fact_id"] for item in pack["runtime_fact_schema"]["facts"]
                ],
            }
        ],
        "control_types": [
            {
                "control_type": name,
                "mapping_control_id": spec["mapping_control_id"],
                "action": "modify",
                "resource_kind": spec["resource_kind"],
                "fact_id": spec["fact_id"],
                "operator": spec["operator"],
                "effects": sorted(spec.get("effects", {spec.get("effect")})),
                "binding_types": sorted(spec["binding_types"]),
                "required_runtime_facts": spec["required_runtime_facts"],
            }
            for name, spec in _CONTROL_SPECS.items()
        ],
        "known_fail_closed_capabilities": [
            "human_actor",
            "service_actor",
            "branch_scope",
            "push",
            "open_pull_request",
            "approve_pull_request",
            "merge_pull_request",
            "changed_file_count",
            "reviewer_identity_or_team",
            "approval_count_or_threshold",
            "requester_approver_separation_of_duties",
            "environment",
            "evidence_requirement",
            "external_scanner_findings",
            "iac_plan",
            "cloud_provisioning",
            "financial_system",
        ],
    }
    catalog["catalog_hash"] = artifact_hash(catalog, "catalog_hash")
    return catalog


def create_policy_translation_proposal(
    source_bytes: bytes,
    *,
    source_policy_id: str,
    source_revision: str,
    authority_id: str,
    authority_version: str,
    clauses: list[dict[str, Any]],
    organizational_bindings: list[dict[str, Any]],
    provider_class: str,
    provider_identifier: str | None,
    translation_template_version: str,
    translation_template_hash: str,
    request_configuration_id: str,
    request_configuration_hash: str,
    created_at: str,
    candidate_response_bytes: bytes,
) -> dict[str, Any]:
    """Canonicalize untrusted authoring input without interpreting or approving it."""
    if not isinstance(source_bytes, bytes) or not source_bytes:
        raise ValueError("source_bytes must be non-empty exact bytes")
    draft = interpret_policy_with_domain_pack(
        source_bytes,
        domain_pack_id=REPOSITORY_CHANGES_PACK_ID,
        domain_pack_version=REPOSITORY_CHANGES_PACK_VERSION,
        source_policy_id=source_policy_id,
        source_revision=source_revision,
        authority_id=authority_id,
        authority_version=authority_version,
    )
    if not isinstance(candidate_response_bytes, bytes):
        raise ValueError("candidate_response_bytes must be exact bytes")
    normalized_clauses: list[dict[str, Any]] = []
    for index, item in enumerate(clauses):
        if not isinstance(item, dict):
            raise ValueError(f"clauses[{index}] must be an object")
        _exact(
            item,
            {
                "start_byte",
                "end_byte",
                "status",
                "candidate_control",
                "unresolved_binding_ids",
                "limitation_code",
                "provider_explanation",
            },
            f"clauses[{index}]",
        )
        start, end = item["start_byte"], item["end_byte"]
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise ValueError(f"clauses[{index}] span must use integers")
        piece = source_bytes[start:end] if 0 <= start < end <= len(source_bytes) else b""
        statement_hash = bytes_sha256(piece)
        clause_core = {
            "source_snapshot_hash": draft["source_policy"]["snapshot_hash"],
            "source_policy_ref": draft["source_policy"]["source_policy_ref"],
            "index": index,
            "start_byte": start,
            "end_byte": end,
            "clause_hash": statement_hash,
        }
        candidate = copy.deepcopy(item["candidate_control"])
        if isinstance(candidate, dict) and "candidate_control_id" not in candidate:
            candidate["candidate_control_id"] = "candidate-control-" + canonical_sha256(candidate).removeprefix("sha256:")
        normalized_clauses.append(
            {
                "clause_id": "policy-clause-" + canonical_sha256(clause_core).removeprefix("sha256:"),
                "index": index,
                "start_byte": start,
                "end_byte": end,
                "clause_bytes_base64": base64.b64encode(piece).decode("ascii"),
                "clause_hash": statement_hash,
                "status": item["status"],
                "candidate_control": candidate,
                "unresolved_binding_ids": copy.deepcopy(item["unresolved_binding_ids"]),
                "limitation_code": item["limitation_code"],
                "provider_explanation": item["provider_explanation"],
            }
        )
    catalog = get_policy_translation_capability_catalog()
    proposal: dict[str, Any] = {
        "schema_version": POLICY_TRANSLATION_PROPOSAL_V1,
        "source_policy": copy.deepcopy(draft["source_policy"]),
        "authority": copy.deepcopy(draft["authority"]),
        "capability_catalog": {
            "catalog_id": catalog["catalog_id"],
            "catalog_version": catalog["catalog_version"],
            "catalog_hash": catalog["catalog_hash"],
        },
        "clauses": normalized_clauses,
        "organizational_bindings": copy.deepcopy(organizational_bindings),
        "provider_evidence": {
            "provider_class": provider_class,
            "provider_identifier": provider_identifier,
            "translation_template_version": translation_template_version,
            "translation_template_hash": translation_template_hash,
            "request_configuration_id": request_configuration_id,
            "request_configuration_hash": request_configuration_hash,
            "created_at": created_at,
            "candidate_response_base64": base64.b64encode(candidate_response_bytes).decode("ascii"),
            "candidate_response_hash": bytes_sha256(candidate_response_bytes),
            "trust_posture": "untrusted_authoring_evidence",
        },
    }
    proposal_hash = canonical_sha256(proposal)
    proposal["proposal_id"] = "policy-translation-proposal-" + proposal_hash.removeprefix("sha256:")
    proposal["proposal_hash"] = proposal_hash
    validate_policy_translation_proposal(proposal)
    return proposal


def validate_policy_translation_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate structure, source coverage, capability bounds, and hashes.

    A successful result says nothing about semantic correctness.  It only proves that
    the untrusted proposal is complete, internally bound, and confined to the catalog.
    """
    _object(proposal, "proposal")
    _exact(
        proposal,
        {
            "schema_version",
            "proposal_id",
            "proposal_hash",
            "source_policy",
            "authority",
            "capability_catalog",
            "clauses",
            "organizational_bindings",
            "provider_evidence",
        },
        "proposal",
    )
    if proposal["schema_version"] != POLICY_TRANSLATION_PROPOSAL_V1:
        raise ValueError(f"proposal must be {POLICY_TRANSLATION_PROPOSAL_V1}")
    expected_hash = canonical_sha256(
        {key: value for key, value in proposal.items() if key not in {"proposal_id", "proposal_hash"}}
    )
    if proposal["proposal_hash"] != expected_hash:
        raise ValueError("proposal canonical hash is invalid")
    if proposal["proposal_id"] != "policy-translation-proposal-" + expected_hash.removeprefix("sha256:"):
        raise ValueError("proposal identity is invalid")

    source = proposal["source_policy"]
    _exact(
        source,
        {
            "source_policy_id",
            "source_revision",
            "source_policy_ref",
            "content_encoding",
            "source_bytes_base64",
            "snapshot_hash",
        },
        "source_policy",
    )
    if source["content_encoding"] != "base64":
        raise ValueError("source policy content encoding must be base64")
    exact = _decode_base64(source["source_bytes_base64"], "source bytes")
    if not exact or bytes_sha256(exact) != source["snapshot_hash"]:
        raise ValueError("source snapshot hash does not match exact source bytes")
    _identity(source["source_policy_id"], "source_policy_id")
    _nonempty(source["source_revision"], "source_revision")
    if source["source_policy_ref"] != f"{source['source_policy_id']}@{source['source_revision']}":
        raise ValueError("source policy identity and revision are inconsistent")

    authority = proposal["authority"]
    _exact(authority, {"authority_id", "authority_version", "authority_ref"}, "authority")
    _identity(authority["authority_id"], "authority_id")
    if authority["authority_ref"] != f"{authority['authority_id']}@{authority['authority_version']}":
        raise ValueError("authority identity and version are inconsistent")

    catalog = get_policy_translation_capability_catalog()
    expected_ref = {
        "catalog_id": catalog["catalog_id"],
        "catalog_version": catalog["catalog_version"],
        "catalog_hash": catalog["catalog_hash"],
    }
    if proposal["capability_catalog"] != expected_ref:
        raise ValueError("proposal capability-catalog identity, version, or hash is unavailable")
    _validate_provider_evidence(proposal["provider_evidence"])

    # Re-run the released source partitioner.  This makes omission, duplication,
    # overlap, reordering, and cross-source span substitution impossible.
    draft = interpret_policy_with_domain_pack(
        exact,
        domain_pack_id=REPOSITORY_CHANGES_PACK_ID,
        domain_pack_version=REPOSITORY_CHANGES_PACK_VERSION,
        source_policy_id=source["source_policy_id"],
        source_revision=source["source_revision"],
        authority_id=authority["authority_id"],
        authority_version=authority["authority_version"],
    )
    if draft["source_policy"] != source or draft["authority"] != authority:
        raise ValueError("proposal source or authority cannot be reconstructed")
    clauses = proposal["clauses"]
    if not isinstance(clauses, list) or not clauses:
        raise ValueError("proposal clauses must be a non-empty complete partition")
    expected_statements = draft["source_statements"]
    if len(clauses) != len(expected_statements):
        raise ValueError("proposal omits or duplicates a source clause")

    bindings = _binding_index(proposal["organizational_bindings"])
    used_bindings: set[str] = set()
    status_counts = {status: 0 for status in sorted(_STATUSES)}
    for index, (clause, statement) in enumerate(zip(clauses, expected_statements)):
        _validate_clause(
            clause,
            index=index,
            statement=statement,
            source=source,
            exact_source=exact,
            bindings=bindings,
            used_bindings=used_bindings,
        )
        status_counts[clause["status"]] += 1
    if used_bindings != set(bindings):
        raise ValueError("organizational bindings must each be referenced by exactly one candidate control")
    return {
        "schema_version": POLICY_TRANSLATION_PROPOSAL_V1,
        "valid": True,
        "semantic_validity": "not_established",
        "trust_posture": "untrusted_authoring_input",
        "proposal_id": proposal["proposal_id"],
        "proposal_hash": proposal["proposal_hash"],
        "source_snapshot_hash": source["snapshot_hash"],
        "clause_count": len(clauses),
        "status_counts": status_counts,
        "unresolved_binding_count": len(bindings),
    }


def inspect_policy_translation_proposal(
    proposal: dict[str, Any],
    confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect exact coverage and unresolved human work without changing state."""
    validation = validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation or _empty_confirmation(proposal))
    resolutions = {item["binding_id"] for item in state["binding_resolutions"]}
    decisions = {item["clause_id"]: item for item in state["clause_decisions"]}
    unresolved_bindings = [
        {
            "binding_id": item["binding_id"],
            "binding_type": item["binding_type"],
            "symbol": item["symbol"],
            "question": item["question"],
        }
        for item in proposal["organizational_bindings"]
        if item["binding_id"] not in resolutions
    ]
    unresolved_clauses = [
        {
            "clause_id": item["clause_id"],
            "status": item["status"],
            "unresolved_binding_ids": [
                binding for binding in item["unresolved_binding_ids"] if binding not in resolutions
            ],
        }
        for item in proposal["clauses"]
        if item["clause_id"] not in decisions
    ]
    return {
        "schema_version": "policy_translation_inspection.v1",
        "proposal_validation": validation,
        "coverage": copy.deepcopy(state["coverage"]),
        "unresolved_bindings": unresolved_bindings,
        "unresolved_clauses": unresolved_clauses,
        "publication_ready": state["coverage"]["unresolved_clause_count"] == 0
        and state["coverage"]["enforced_clause_count"] > 0,
    }


def apply_policy_translation_binding(
    proposal: dict[str, Any],
    confirmation: dict[str, Any] | None,
    *,
    binding_id: str,
    value: str,
    confirmed_by: str,
    confirmed_at: str,
) -> dict[str, Any]:
    """Apply one human-supplied value through its declared bounded binding type."""
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation or _empty_confirmation(proposal))
    bindings = _binding_index(proposal["organizational_bindings"])
    if binding_id not in bindings:
        raise ValueError("unknown organizational binding")
    if any(item["binding_id"] == binding_id for item in state["binding_resolutions"]):
        raise ValueError("organizational binding is already resolved")
    binding = bindings[binding_id]
    _validate_binding_value(binding["binding_type"], value)
    record = {
        "binding_id": binding_id,
        "binding_type": binding["binding_type"],
        "value": value,
        "confirmed_by": _nonempty(confirmed_by, "confirmed_by"),
        "confirmed_at": _utc(confirmed_at, "confirmed_at"),
    }
    record["resolution_hash"] = artifact_hash(record, "resolution_hash")
    result = copy.deepcopy(state)
    result["binding_resolutions"].append(record)
    return _finalize_confirmation(proposal, result)


def apply_policy_translation_disposition(
    proposal: dict[str, Any],
    confirmation: dict[str, Any] | None,
    *,
    clause_id: str,
    disposition: str,
    confirmed_by: str,
    confirmed_at: str,
    reason_code: str,
    human_reason: str | None = None,
    acknowledge_unenforced: bool = False,
) -> dict[str, Any]:
    """Human-confirm exactly one enforceable or explicitly unenforced clause."""
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation or _empty_confirmation(proposal))
    clauses = {item["clause_id"]: item for item in proposal["clauses"]}
    clause = clauses.get(clause_id)
    if clause is None:
        raise ValueError("unknown proposal clause")
    if any(item["clause_id"] == clause_id for item in state["clause_decisions"]):
        raise ValueError("proposal clause already has a human disposition")
    if disposition not in {"enforced", "unsupported", "informational"}:
        raise ValueError("disposition must be enforced, unsupported, or informational")
    resolved = {item["binding_id"] for item in state["binding_resolutions"]}
    if disposition == "enforced":
        if clause["candidate_control"] is None:
            raise ValueError("an enforced disposition requires a validated candidate control")
        missing = set(clause["unresolved_binding_ids"]) - resolved
        if missing:
            raise ValueError("all candidate-control bindings require concrete human answers")
        if acknowledge_unenforced:
            raise ValueError("enforced clauses do not use unenforced acknowledgement")
        if reason_code != "human-confirmed-control" or human_reason is not None:
            raise ValueError("enforced clauses use only the deterministic human-confirmed-control reason")
    else:
        if not acknowledge_unenforced:
            raise ValueError("every unenforced clause requires explicit approver acknowledgement")
        allowed = (
            {"outside-domain", "not-enforceable", "deferred", "other"}
            if disposition == "unsupported"
            else {"context-only", "descriptive", "non-policy", "other"}
        )
        if reason_code not in allowed:
            raise ValueError("unenforced clause reason_code is outside the bounded disposition catalog")
        if reason_code == "other" and (not isinstance(human_reason, str) or not human_reason.strip()):
            raise ValueError("reason_code other requires a human_reason")
    if human_reason is not None and (not isinstance(human_reason, str) or not human_reason.strip() or len(human_reason) > 1024):
        raise ValueError("human_reason must be null or 1 to 1024 non-whitespace characters")
    decision = {
        "clause_id": clause_id,
        "disposition": disposition,
        "reason_code": reason_code,
        "human_reason": human_reason,
        "acknowledged_unenforced": acknowledge_unenforced,
        "confirmed_by": _nonempty(confirmed_by, "confirmed_by"),
        "confirmed_at": _utc(confirmed_at, "confirmed_at"),
    }
    decision["decision_hash"] = artifact_hash(decision, "decision_hash")
    result = copy.deepcopy(state)
    result["clause_decisions"].append(decision)
    return _finalize_confirmation(proposal, result)


def render_policy_translation_review(
    proposal: dict[str, Any], confirmation: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Render deterministic operational meaning solely from validated controls."""
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation or _empty_confirmation(proposal))
    resolutions = {item["binding_id"]: item["value"] for item in state["binding_resolutions"]}
    decisions = {item["clause_id"]: item for item in state["clause_decisions"]}
    exact = _decode_base64(proposal["source_policy"]["source_bytes_base64"], "source bytes")
    rows = []
    for clause in proposal["clauses"]:
        decision = decisions.get(clause["clause_id"])
        control = clause["candidate_control"]
        rows.append(
            {
                "clause_id": clause["clause_id"],
                "source_text": exact[clause["start_byte"] : clause["end_byte"]].decode("utf-8"),
                "proposal_status": clause["status"],
                "human_disposition": decision["disposition"] if decision else None,
                "operational_explanation": _render_control(control, resolutions) if control else _render_noncontrol(clause),
                "remaining_unresolved_bindings": [
                    item for item in clause["unresolved_binding_ids"] if item not in resolutions
                ],
                "enforcement_point": control["enforcement_point"] if control else None,
            }
        )
    review = {
        "schema_version": "policy_translation_review.v1",
        "proposal_id": proposal["proposal_id"],
        "proposal_hash": proposal["proposal_hash"],
        "source_policy_ref": proposal["source_policy"]["source_policy_ref"],
        "source_snapshot_hash": proposal["source_policy"]["snapshot_hash"],
        "authority_ref": proposal["authority"]["authority_ref"],
        "capability_catalog": copy.deepcopy(proposal["capability_catalog"]),
        "coverage": copy.deepcopy(state["coverage"]),
        "clauses": rows,
        "provider_explanations_used": False,
    }
    review["review_hash"] = artifact_hash(review, "review_hash")
    return review


def approve_policy_translation_proposal(
    proposal: dict[str, Any],
    confirmation: dict[str, Any],
    *,
    approved_by: str,
    approved_at: str,
) -> dict[str, Any]:
    """Approve complete human dispositions and bind proposal, review, and coverage."""
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation)
    coverage = state["coverage"]
    if coverage["unresolved_clause_count"]:
        raise ValueError("publication approval requires a human disposition for every source clause")
    if coverage["enforced_clause_count"] == 0:
        raise ValueError("publication approval requires at least one enforced clause")
    if coverage["unenforced_clause_count"] != len(coverage["acknowledged_unenforced_clause_ids"]):
        raise ValueError("partial coverage requires acknowledgement of every unenforced clause")
    review = render_policy_translation_review(proposal, state)
    approval: dict[str, Any] = {
        "schema_version": POLICY_TRANSLATION_APPROVAL_V1,
        "proposal_id": proposal["proposal_id"],
        "proposal_hash": proposal["proposal_hash"],
        "confirmation_hash": state["confirmation_hash"],
        "review_hash": review["review_hash"],
        "source_policy_ref": proposal["source_policy"]["source_policy_ref"],
        "source_snapshot_hash": proposal["source_policy"]["snapshot_hash"],
        "authority_ref": proposal["authority"]["authority_ref"],
        "capability_catalog": copy.deepcopy(proposal["capability_catalog"]),
        "coverage": copy.deepcopy(coverage),
        "approved_by": _nonempty(approved_by, "approved_by"),
        "approved_at": _utc(approved_at, "approved_at"),
    }
    approval_hash = canonical_sha256(approval)
    approval["approval_id"] = "policy-translation-approval-" + approval_hash.removeprefix("sha256:")
    approval["approval_hash"] = approval_hash
    _validate_approval(proposal, state, approval)
    return approval


def finalize_policy_translation_authority(
    proposal: dict[str, Any],
    confirmation: dict[str, Any],
    approval: dict[str, Any],
    *,
    committed_by: str,
    committed_at: str,
    publication_id: str,
    published_by: str,
    published_at: str,
) -> dict[str, Any]:
    """Replay approved meaning from exact bytes and publish via unchanged v2 schemas."""
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation)
    _validate_approval(proposal, state, approval)
    source = proposal["source_policy"]
    authority = proposal["authority"]
    exact = _decode_base64(source["source_bytes_base64"], "source bytes")
    draft = interpret_policy_with_domain_pack(
        exact,
        domain_pack_id=REPOSITORY_CHANGES_PACK_ID,
        domain_pack_version=REPOSITORY_CHANGES_PACK_VERSION,
        source_policy_id=source["source_policy_id"],
        source_revision=source["source_revision"],
        authority_id=authority["authority_id"],
        authority_version=authority["authority_version"],
    )
    resolutions = {item["binding_id"]: item["value"] for item in state["binding_resolutions"]}
    decisions = {item["clause_id"]: item for item in state["clause_decisions"]}
    for clause, statement in zip(proposal["clauses"], draft["source_statements"]):
        decision = decisions[clause["clause_id"]]
        if statement["classification"] == "direct":
            if decision["disposition"] != "enforced":
                raise ValueError("a deterministically compiled source clause cannot silently become unenforced")
            expected = _control_semantics(clause["candidate_control"], resolutions)
            actual = _direct_statement_semantics(draft, statement["statement_id"])
            if expected != actual:
                raise ValueError("candidate control contradicts the deterministic executable constraint")
            continue
        kwargs: dict[str, Any] = {
            "statement_id": statement["statement_id"],
            "disposition": decision["disposition"],
            "mapper_identity": decision["confirmed_by"],
            "mapped_at": decision["confirmed_at"],
        }
        if decision["disposition"] == "enforced":
            control_id, selections = _control_selections(clause["candidate_control"], resolutions)
            kwargs.update(control_id=control_id, selections=selections, reason_code="human-mapped")
        else:
            kwargs.update(reason_code=decision["reason_code"], human_reason=decision["human_reason"])
        draft = apply_policy_mapping_decision(draft, **kwargs)["updated_interpretation"]
    result = finalize_domain_policy_authority(
        draft,
        approval_id=approval["approval_id"],
        approved_by=approval["approved_by"],
        approved_at=approval["approved_at"],
        committed_by=committed_by,
        committed_at=committed_at,
        publication_id=publication_id,
        published_by=published_by,
        published_at=published_at,
    )
    result["policy_translation_approval"] = copy.deepcopy(approval)
    result["policy_translation_coverage"] = copy.deepcopy(state["coverage"])
    result["proposal_evidence_required_by_guard"] = False
    return result


def _validate_clause(
    clause: dict[str, Any],
    *,
    index: int,
    statement: dict[str, Any],
    source: dict[str, Any],
    exact_source: bytes,
    bindings: dict[str, dict[str, Any]],
    used_bindings: set[str],
) -> None:
    label = f"clauses[{index}]"
    _object(clause, label)
    _exact(
        clause,
        {
            "clause_id",
            "index",
            "start_byte",
            "end_byte",
            "clause_bytes_base64",
            "clause_hash",
            "status",
            "candidate_control",
            "unresolved_binding_ids",
            "limitation_code",
            "provider_explanation",
        },
        label,
    )
    if clause["index"] != index:
        raise ValueError("proposal clauses are reordered")
    for field in ("start_byte", "end_byte"):
        if clause[field] != statement[field]:
            raise ValueError("proposal clause spans are missing, duplicated, overlapping, or reordered")
    piece = exact_source[clause["start_byte"] : clause["end_byte"]]
    if not piece or _decode_base64(clause["clause_bytes_base64"], f"{label} bytes") != piece:
        raise ValueError("proposal clause bytes do not reproduce the exact source span")
    if clause["clause_hash"] != bytes_sha256(piece):
        raise ValueError("proposal clause hash is invalid")
    core = {
        "source_snapshot_hash": source["snapshot_hash"],
        "source_policy_ref": source["source_policy_ref"],
        "index": index,
        "start_byte": clause["start_byte"],
        "end_byte": clause["end_byte"],
        "clause_hash": clause["clause_hash"],
    }
    expected_id = "policy-clause-" + canonical_sha256(core).removeprefix("sha256:")
    if clause["clause_id"] != expected_id:
        raise ValueError("proposal clause identity is invalid for this exact source")
    status = clause["status"]
    if status not in _STATUSES:
        raise ValueError("proposal clause status is unknown")
    if clause["limitation_code"] not in _LIMITATIONS:
        raise ValueError("proposal clause limitation code is unknown")
    explanation = clause["provider_explanation"]
    if explanation is not None and (not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 4096):
        raise ValueError("provider explanation must be null or bounded non-empty text")
    unresolved = clause["unresolved_binding_ids"]
    if not isinstance(unresolved, list) or unresolved != sorted(set(unresolved)):
        raise ValueError("unresolved_binding_ids must be a sorted unique array")
    control = clause["candidate_control"]
    if status in {"integration_dependent", "unsupported", "informational"}:
        if control is not None or unresolved:
            raise ValueError(f"{status} clauses cannot claim an executable control or resolved capability")
        if status == "integration_dependent" and clause["limitation_code"] is None:
            raise ValueError("integration-dependent clauses require an explicit limitation code")
    else:
        if not isinstance(control, dict):
            raise ValueError(f"{status} clauses require one candidate control")
        referenced = _validate_candidate_control(control, piece, bindings)
        if unresolved != sorted(referenced):
            raise ValueError("candidate control unresolved bindings are inconsistent")
        if status == "enforceable_fully_bound" and unresolved:
            raise ValueError("fully bound clauses cannot contain unresolved organizational bindings")
        if status == "needs_concrete_answer" and not unresolved:
            raise ValueError("needs-concrete-answer clauses require an unresolved organizational binding")
        if clause["limitation_code"] is not None:
            raise ValueError("catalog-valid candidate controls cannot claim an integration limitation")
        overlap = used_bindings & set(referenced)
        if overlap:
            raise ValueError("an organizational binding cannot be guessed or reused across candidate controls")
        used_bindings.update(referenced)


def _validate_candidate_control(
    control: dict[str, Any], clause_bytes: bytes, bindings: dict[str, dict[str, Any]]
) -> list[str]:
    _exact(
        control,
        {
            "candidate_control_id",
            "control_type",
            "actor_kind",
            "action",
            "resource_kind",
            "fact_id",
            "operator",
            "effect",
            "enforcement_point",
            "value",
            "required_runtime_facts",
        },
        "candidate control",
    )
    core = {key: value for key, value in control.items() if key != "candidate_control_id"}
    if control["candidate_control_id"] != "candidate-control-" + canonical_sha256(core).removeprefix("sha256:"):
        raise ValueError("candidate control identity is not canonical")
    control_type = control["control_type"]
    if control_type not in _CONTROL_SPECS:
        raise ValueError("candidate control uses an unknown or invented control capability")
    spec = _CONTROL_SPECS[control_type]
    if control["actor_kind"] != "autonomous_agent":
        raise ValueError("candidate control uses an unknown actor capability")
    if control["action"] != "modify":
        raise ValueError("candidate control uses an unknown action capability")
    if control["resource_kind"] != spec["resource_kind"]:
        raise ValueError("candidate control uses an unavailable resource capability")
    if control["fact_id"] != spec["fact_id"]:
        raise ValueError("candidate control uses an unknown or unavailable runtime fact")
    if control["operator"] != spec["operator"]:
        raise ValueError("candidate control uses an unknown or type-invalid operator")
    effects = spec.get("effects", {spec.get("effect")})
    if control["effect"] not in effects:
        raise ValueError("candidate control effect is incompatible with its executable control")
    if control["enforcement_point"] != _ENFORCEMENT_POINT:
        raise ValueError("candidate control uses an unknown enforcement point")
    if control["required_runtime_facts"] != spec["required_runtime_facts"]:
        raise ValueError("candidate control requires unknown, unavailable, or omitted runtime facts")
    value = control["value"]
    _object(value, "candidate control value")
    kind = value.get("kind")
    if kind == "source_literal":
        _exact(value, {"kind", "value"}, "candidate control source literal")
        literal = _nonempty(value["value"], "candidate control source literal")
        try:
            encoded = literal.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("candidate control source literal must be UTF-8") from exc
        if encoded not in clause_bytes:
            raise ValueError("candidate control path or identity is guessed rather than present in its exact source span")
        _validate_control_value(control_type, literal)
        return []
    if kind == "organizational_binding":
        _exact(value, {"kind", "binding_id"}, "candidate control organizational binding")
        binding_id = _nonempty(value["binding_id"], "candidate control binding_id")
        binding = bindings.get(binding_id)
        if binding is None:
            raise ValueError("candidate control references an unknown organizational binding")
        if binding["binding_type"] not in spec["binding_types"]:
            raise ValueError("candidate control organizational binding has an invalid type")
        return [binding_id]
    raise ValueError("candidate control value must be an exact source literal or unresolved organizational binding")


def _binding_index(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("organizational_bindings must be an array")
    result: dict[str, dict[str, Any]] = {}
    for index, binding in enumerate(value):
        label = f"organizational_bindings[{index}]"
        _object(binding, label)
        _exact(binding, {"binding_id", "binding_type", "symbol", "question", "status"}, label)
        binding_id = _identity(binding["binding_id"], f"{label}.binding_id")
        if binding_id in result:
            raise ValueError("duplicate organizational binding")
        if binding["binding_type"] not in {item for spec in _CONTROL_SPECS.values() for item in spec["binding_types"]}:
            raise ValueError("unknown organizational binding type")
        _nonempty(binding["symbol"], f"{label}.symbol")
        _nonempty(binding["question"], f"{label}.question")
        if binding["status"] != "unresolved":
            raise ValueError("provider output cannot present an organizational symbol as resolved")
        result[binding_id] = binding
    return result


def _validate_provider_evidence(value: Any) -> None:
    _object(value, "provider_evidence")
    _exact(
        value,
        {
            "provider_class",
            "provider_identifier",
            "translation_template_version",
            "translation_template_hash",
            "request_configuration_id",
            "request_configuration_hash",
            "created_at",
            "candidate_response_base64",
            "candidate_response_hash",
            "trust_posture",
        },
        "provider_evidence",
    )
    if value["provider_class"] not in {"hosted_model", "local_model", "guided_deterministic", "other"}:
        raise ValueError("provider class is unknown")
    if value["provider_identifier"] is not None:
        _nonempty(value["provider_identifier"], "provider_identifier")
    for field in ("translation_template_version", "request_configuration_id"):
        _nonempty(value[field], field)
    for field in ("translation_template_hash", "request_configuration_hash"):
        _sha256(value[field], field)
    _utc(value["created_at"], "provider created_at")
    raw = _decode_base64(value["candidate_response_base64"], "candidate response")
    if bytes_sha256(raw) != value["candidate_response_hash"]:
        raise ValueError("candidate-response hash does not match exact provider output")
    if value["trust_posture"] != "untrusted_authoring_evidence":
        raise ValueError("provider evidence must remain explicitly untrusted")


def _empty_confirmation(proposal: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema_version": POLICY_TRANSLATION_CONFIRMATION_V1,
        "proposal_id": proposal["proposal_id"],
        "proposal_hash": proposal["proposal_hash"],
        "source_snapshot_hash": proposal["source_policy"]["snapshot_hash"],
        "authority_ref": proposal["authority"]["authority_ref"],
        "binding_resolutions": [],
        "clause_decisions": [],
        "coverage": _coverage(proposal, []),
    }
    result["confirmation_hash"] = artifact_hash(result, "confirmation_hash")
    return result


def _finalize_confirmation(proposal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(state)
    result["coverage"] = _coverage(proposal, result["clause_decisions"])
    result["confirmation_hash"] = artifact_hash(result, "confirmation_hash")
    _validate_confirmation(proposal, result)
    return result


def _validate_confirmation(proposal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    _object(state, "confirmation")
    _exact(
        state,
        {
            "schema_version",
            "proposal_id",
            "proposal_hash",
            "source_snapshot_hash",
            "authority_ref",
            "binding_resolutions",
            "clause_decisions",
            "coverage",
            "confirmation_hash",
        },
        "confirmation",
    )
    expected_header = (
        POLICY_TRANSLATION_CONFIRMATION_V1,
        proposal["proposal_id"],
        proposal["proposal_hash"],
        proposal["source_policy"]["snapshot_hash"],
        proposal["authority"]["authority_ref"],
    )
    actual_header = (
        state["schema_version"], state["proposal_id"], state["proposal_hash"],
        state["source_snapshot_hash"], state["authority_ref"],
    )
    if actual_header != expected_header:
        raise ValueError("confirmation is substituted across proposal, source, or authority")
    bindings = _binding_index(proposal["organizational_bindings"])
    seen_bindings: set[str] = set()
    for record in state["binding_resolutions"]:
        _exact(record, {"binding_id", "binding_type", "value", "confirmed_by", "confirmed_at", "resolution_hash"}, "binding resolution")
        binding_id = record["binding_id"]
        if binding_id in seen_bindings or binding_id not in bindings:
            raise ValueError("binding resolution is duplicated or unknown")
        seen_bindings.add(binding_id)
        if record["binding_type"] != bindings[binding_id]["binding_type"]:
            raise ValueError("binding resolution type is inconsistent")
        _validate_binding_value(record["binding_type"], record["value"])
        _nonempty(record["confirmed_by"], "binding confirmed_by")
        _utc(record["confirmed_at"], "binding confirmed_at")
        if record["resolution_hash"] != artifact_hash(record, "resolution_hash"):
            raise ValueError("binding resolution hash is invalid")
    clauses = {item["clause_id"]: item for item in proposal["clauses"]}
    seen_clauses: set[str] = set()
    resolved = {item["binding_id"] for item in state["binding_resolutions"]}
    for decision in state["clause_decisions"]:
        _exact(decision, {"clause_id", "disposition", "reason_code", "human_reason", "acknowledged_unenforced", "confirmed_by", "confirmed_at", "decision_hash"}, "clause decision")
        clause_id = decision["clause_id"]
        if clause_id in seen_clauses or clause_id not in clauses:
            raise ValueError("clause decision is duplicated or unknown")
        seen_clauses.add(clause_id)
        clause = clauses[clause_id]
        if decision["disposition"] == "enforced":
            if clause["candidate_control"] is None or set(clause["unresolved_binding_ids"]) - resolved:
                raise ValueError("enforced clause has unresolved or absent executable meaning")
            if decision["reason_code"] != "human-confirmed-control" or decision["human_reason"] is not None or decision["acknowledged_unenforced"]:
                raise ValueError("enforced clause decision is inconsistent")
        elif decision["disposition"] in {"unsupported", "informational"}:
            if decision["acknowledged_unenforced"] is not True:
                raise ValueError("unenforced clause lacks explicit acknowledgement")
        else:
            raise ValueError("clause decision disposition is invalid")
        _nonempty(decision["confirmed_by"], "clause confirmed_by")
        _utc(decision["confirmed_at"], "clause confirmed_at")
        if decision["decision_hash"] != artifact_hash(decision, "decision_hash"):
            raise ValueError("clause decision hash is invalid")
    expected_coverage = _coverage(proposal, state["clause_decisions"])
    if state["coverage"] != expected_coverage:
        raise ValueError("confirmation coverage counts are inconsistent")
    if state["confirmation_hash"] != artifact_hash(state, "confirmation_hash"):
        raise ValueError("confirmation hash is invalid")
    return copy.deepcopy(state)


def _coverage(proposal: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    enforced = sorted(item["clause_id"] for item in decisions if item["disposition"] == "enforced")
    unenforced = sorted(item["clause_id"] for item in decisions if item["disposition"] != "enforced")
    acknowledged = sorted(item["clause_id"] for item in decisions if item["disposition"] != "enforced" and item["acknowledged_unenforced"])
    total = len(proposal["clauses"])
    return {
        "total_clause_count": total,
        "enforced_clause_count": len(enforced),
        "unenforced_clause_count": len(unenforced),
        "unresolved_clause_count": total - len(decisions),
        "enforced_clause_ids": enforced,
        "unenforced_clause_ids": unenforced,
        "acknowledged_unenforced_clause_ids": acknowledged,
    }


def _validate_approval(proposal: dict[str, Any], state: dict[str, Any], approval: dict[str, Any]) -> None:
    _exact(
        approval,
        {
            "schema_version", "approval_id", "approval_hash", "proposal_id", "proposal_hash",
            "confirmation_hash", "review_hash", "source_policy_ref", "source_snapshot_hash",
            "authority_ref", "capability_catalog", "coverage", "approved_by", "approved_at",
        },
        "policy translation approval",
    )
    review = render_policy_translation_review(proposal, state)
    expected = {
        "schema_version": POLICY_TRANSLATION_APPROVAL_V1,
        "proposal_id": proposal["proposal_id"],
        "proposal_hash": proposal["proposal_hash"],
        "confirmation_hash": state["confirmation_hash"],
        "review_hash": review["review_hash"],
        "source_policy_ref": proposal["source_policy"]["source_policy_ref"],
        "source_snapshot_hash": proposal["source_policy"]["snapshot_hash"],
        "authority_ref": proposal["authority"]["authority_ref"],
        "capability_catalog": proposal["capability_catalog"],
        "coverage": state["coverage"],
        "approved_by": approval["approved_by"],
        "approved_at": approval["approved_at"],
    }
    _nonempty(approval["approved_by"], "approved_by")
    _utc(approval["approved_at"], "approved_at")
    approval_time = _utc_datetime(approval["approved_at"], "approved_at")
    confirmations = [*state["binding_resolutions"], *state["clause_decisions"]]
    if any(
        _utc_datetime(item["confirmed_at"], "confirmed_at") > approval_time
        for item in confirmations
    ):
        raise ValueError("every human confirmation must precede or equal approval")
    expected_hash = canonical_sha256(expected)
    if approval["approval_hash"] != expected_hash or approval["approval_id"] != "policy-translation-approval-" + expected_hash.removeprefix("sha256:"):
        raise ValueError("policy translation approval binding is invalid")
    for field, value in expected.items():
        if approval[field] != value:
            raise ValueError(f"policy translation approval {field} is inconsistent")


def _control_selections(control: dict[str, Any], resolutions: dict[str, str]) -> tuple[str, dict[str, Any]]:
    value = control["value"]
    selected = value["value"] if value["kind"] == "source_literal" else resolutions[value["binding_id"]]
    spec = _CONTROL_SPECS[control["control_type"]]
    if control["control_type"] == "acting_role":
        return spec["mapping_control_id"], {"role": selected}
    return spec["mapping_control_id"], {"effect": control["effect"], "path": selected}


def _control_semantics(control: dict[str, Any], resolutions: dict[str, str]) -> dict[str, Any]:
    control_id, selections = _control_selections(control, resolutions)
    if control_id == "acting-role":
        return {"control_id": control_id, "role": selections["role"]}
    return {"control_id": control_id, "effect": selections["effect"], "path": selections["path"]}


def _direct_statement_semantics(draft: dict[str, Any], statement_id: str) -> dict[str, Any]:
    mapping = next(item for item in draft["source_to_constraint_mappings"] if item["statement_id"] == statement_id)
    constraint_id = mapping["constraint_ids"][0]
    constraint = next(item for item in draft["constraint_ir"]["constraints"] if item["constraint_id"] == constraint_id)
    if constraint["acting_role"]:
        return {"control_id": "acting-role", "role": constraint["acting_role"]["value"]}
    match = constraint["resource"]["match"]
    return {
        "control_id": "exact-path-access" if match == "exact" else "prefix-path-access",
        "effect": constraint["effect"],
        "path": constraint["resource"]["value"],
    }


def _render_control(control: dict[str, Any], resolutions: dict[str, str]) -> str:
    value = control["value"]
    selected = value.get("value") if value["kind"] == "source_literal" else resolutions.get(value["binding_id"])
    rendered = selected if selected is not None else f"UNRESOLVED({value['binding_id']})"
    point = control["enforcement_point"]
    if control["control_type"] == "acting_role":
        return f"Autonomous agent must act as repository role {rendered!r} to modify the repository; enforced at {point}."
    scope = "exact repository path" if control["control_type"] == "exact_path_access" else "repository path prefix"
    consequence = "allowed" if control["effect"] == "allow" else "denied"
    return f"Autonomous-agent modification of {scope} {rendered!r} is {consequence}; enforced at {point}."


def _render_noncontrol(clause: dict[str, Any]) -> str:
    if clause["status"] == "integration_dependent":
        return f"Not enforceable by the current released capability catalog ({clause['limitation_code']})."
    if clause["status"] == "informational":
        return "Informational only; no executable constraint is proposed."
    return "Unsupported by the current released capability catalog; no executable constraint is proposed."


def _validate_binding_value(binding_type: str, value: Any) -> None:
    value = _nonempty(value, "organizational binding value")
    pack = get_builtin_domain_pack(REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION)
    if binding_type == "repository_role":
        if value not in pack["role_kinds"]:
            raise ValueError("repository role binding is outside the released role catalog")
    elif binding_type == "repository_exact_path":
        validate_format_value(REPOSITORY_PATH_FORMAT_ID, value, match_mode="exact", label="repository exact-path binding")
    elif binding_type == "repository_path_prefix":
        validate_format_value(REPOSITORY_PATH_FORMAT_ID, value, match_mode="prefix", label="repository path-prefix binding")
    else:
        raise ValueError("unknown organizational binding type")


def _validate_control_value(control_type: str, value: str) -> None:
    if control_type == "acting_role":
        _validate_binding_value("repository_role", value)
    elif control_type == "exact_path_access":
        _validate_binding_value("repository_exact_path", value)
    else:
        _validate_binding_value("repository_path_prefix", value)


def _pack_ref(pack: dict[str, Any]) -> dict[str, str]:
    return {
        "domain_pack_id": pack["domain_pack_id"],
        "domain_pack_version": pack["domain_pack_version"],
        "domain_pack_hash": pack["canonical_hash"],
    }


def _decode_base64(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be canonical base64")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} must be canonical base64")
    return decoded


def _object(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        raise ValueError(f"{label} is missing required fields: {sorted(missing)}")
    if extra:
        raise ValueError(f"{label} contains unsupported fields: {sorted(extra)}")


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise ValueError(f"{label} must be a portable identity")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
        raise ValueError(f"{label} must be a prefixed SHA-256")
    return value


def _utc(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise ValueError(f"{label} must be canonical UTC")
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be canonical UTC") from exc
    return value


def _utc_datetime(value: Any, label: str) -> datetime:
    return datetime.fromisoformat(_utc(value, label).removesuffix("Z") + "+00:00")
