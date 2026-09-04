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
POLICY_TRANSLATION_REVIEW_V1 = "policy_translation_review.v1"
POLICY_TRANSLATION_RUN_EVIDENCE_V1 = "policy_translation_run_evidence.v1"

_CATALOG_ID = "waveframe.coding-agent.repository-change"
_CATALOG_VERSION = "1.0.0"
_ENFORCEMENT_POINT = "waveframe.guard.repository-change.v1"
_TRUSTED_CATALOG_REGISTRY = {
    (_CATALOG_ID, _CATALOG_VERSION): "builtin_repository_change",
}
_CLAUSE_COVERAGE_STATUSES = {
    "fully_represented",
    "partially_represented",
    "entirely_unsupported",
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
    "pull_request_approval_not_supported",
    "other",
}
_KNOWN_FAIL_CLOSED_CAPABILITIES = [
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
]
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
    """Return the aggregate currently enforceable catalog without customer selection."""
    return _build_repository_capability_catalog()


def resolve_policy_translation_capability_catalog(
    catalog_ref: dict[str, Any],
) -> dict[str, Any]:
    """Resolve only immutable catalogs registered in this Ledger installation."""
    _object(catalog_ref, "capability catalog reference")
    _exact(
        catalog_ref,
        {"catalog_id", "catalog_version", "catalog_hash"},
        "capability catalog reference",
    )
    key = (catalog_ref["catalog_id"], catalog_ref["catalog_version"])
    if _TRUSTED_CATALOG_REGISTRY.get(key) != "builtin_repository_change":
        raise ValueError("capability catalog is not registered by this Ledger installation")
    catalog = _build_repository_capability_catalog()
    expected = {
        "catalog_id": catalog["catalog_id"],
        "catalog_version": catalog["catalog_version"],
        "catalog_hash": catalog["catalog_hash"],
    }
    if catalog_ref != expected:
        raise ValueError("registered capability catalog hash is unavailable")
    return catalog


def _build_repository_capability_catalog() -> dict[str, Any]:
    """Return the immutable capabilities implemented by Ledger and Guard v0.16.1.

    The catalog is intentionally the intersection of the repository-change compiler
    and Guard's trusted repository-change fact boundary.  Representable Constraint IR
    features without a released lowering are not advertised.
    """
    pack = get_builtin_domain_pack(
        REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION
    )
    reachable_facts = {
        fact_id
        for spec in _CONTROL_SPECS.values()
        for fact_id in spec["required_runtime_facts"]
    }
    facts = []
    for fact in pack["runtime_fact_schema"]["facts"]:
        if fact["fact_id"] not in reachable_facts:
            continue
        item = copy.deepcopy(fact)
        item["comparison_operators"] = [
            operator
            for operator in item["comparison_operators"]
            if operator in {"==", "starts_with"}
        ]
        facts.append(item)
    controls = [
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
    ]
    catalog: dict[str, Any] = {
        "schema_version": POLICY_TRANSLATION_CAPABILITY_CATALOG_V1,
        "catalog_id": _CATALOG_ID,
        "catalog_version": _CATALOG_VERSION,
        "domain_pack": _pack_ref(pack),
        "actor_kinds": ["autonomous_agent"],
        "actions": ["modify"],
        "facts": facts,
        "operators": ["==", "starts_with"],
        "effects": ["allow", "deny", "require"],
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
                    item["fact_id"] for item in facts
                ],
            }
        ],
        "control_types": controls,
        "known_fail_closed_capabilities": copy.deepcopy(_KNOWN_FAIL_CLOSED_CAPABILITIES),
    }
    catalog["catalog_hash"] = artifact_hash(catalog, "catalog_hash")
    validate_policy_translation_capability_catalog(catalog)
    return catalog


def validate_policy_translation_capability_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Validate that every advertised capability is reachable by a released control."""
    _object(catalog, "capability catalog")
    _exact(
        catalog,
        {
            "schema_version", "catalog_id", "catalog_version", "domain_pack",
            "actor_kinds", "actions", "facts", "operators", "effects",
            "binding_types", "enforcement_points", "control_types",
            "known_fail_closed_capabilities", "catalog_hash",
        },
        "capability catalog",
    )
    pack = get_builtin_domain_pack(REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION)
    controls = catalog["control_types"]
    if not isinstance(controls, list) or not controls:
        raise ValueError("capability catalog must contain reachable controls")
    expected_controls = []
    for name, spec in _CONTROL_SPECS.items():
        expected_controls.append(
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
        )
    if controls != expected_controls:
        raise ValueError("capability catalog controls do not match released lowerings")
    fact_ids = sorted({fact for control in controls for fact in control["required_runtime_facts"]})
    expected_facts = []
    for fact in pack["runtime_fact_schema"]["facts"]:
        if fact["fact_id"] in fact_ids:
            item = copy.deepcopy(fact)
            item["comparison_operators"] = [
                operator for operator in item["comparison_operators"]
                if operator in {"==", "starts_with"}
            ]
            expected_facts.append(item)
    advertised_fact_ids = [item.get("fact_id") for item in catalog["facts"]] if isinstance(catalog["facts"], list) else []
    if catalog["facts"] != expected_facts or sorted(advertised_fact_ids) != fact_ids:
        raise ValueError("capability catalog advertises unreachable or unavailable runtime facts")
    derived_operators = sorted({control["operator"] for control in controls})
    derived_effects = sorted({effect for control in controls for effect in control["effects"]})
    derived_bindings = sorted({binding for control in controls for binding in control["binding_types"]})
    if catalog["operators"] != derived_operators:
        raise ValueError("capability catalog operators are inconsistent with reachable controls")
    if catalog["effects"] != derived_effects:
        raise ValueError("capability catalog effects are inconsistent with reachable controls")
    if catalog["binding_types"] != derived_bindings:
        raise ValueError("capability catalog binding types are inconsistent with reachable controls")
    if catalog["actor_kinds"] != ["autonomous_agent"] or catalog["actions"] != sorted({c["action"] for c in controls}):
        raise ValueError("capability catalog actor kinds or actions are inconsistent")
    point = catalog["enforcement_points"]
    if point != [{"enforcement_point_id": _ENFORCEMENT_POINT, "actions": ["modify"], "runtime_fact_ids": [item["fact_id"] for item in expected_facts]}]:
        raise ValueError("capability catalog enforcement points are inconsistent with reachable controls")
    if catalog["schema_version"] != POLICY_TRANSLATION_CAPABILITY_CATALOG_V1 or catalog["catalog_id"] != _CATALOG_ID or catalog["catalog_version"] != _CATALOG_VERSION or catalog["domain_pack"] != _pack_ref(pack):
        raise ValueError("capability catalog identity or domain pack is unavailable")
    if catalog["known_fail_closed_capabilities"] != _KNOWN_FAIL_CLOSED_CAPABILITIES:
        raise ValueError("capability catalog fail-closed scope is inconsistent")
    if catalog["catalog_hash"] != artifact_hash(catalog, "catalog_hash"):
        raise ValueError("capability catalog hash is invalid")
    return copy.deepcopy(catalog)


def create_policy_translation_run(
    *, source_policy_ref: str, source_revision: str, source_snapshot_hash: str,
    provider_class: str, provider_identifier: str | None, translation_template_version: str,
    translation_template_hash: str, request_configuration_id: str,
    request_configuration_hash: str, request_hash: str, response_hash: str,
    created_at: str, completed_at: str, sequence_number: int,
    previous_run_hash: str | None, explanation_hash: str | None = None,
) -> dict[str, Any]:
    """Create one hash-chained run against Ledger's aggregate trusted catalog."""
    catalog = get_policy_translation_capability_catalog()
    capability_catalog = {
        key: catalog[key] for key in ("catalog_id", "catalog_version", "catalog_hash")
    }
    core: dict[str, Any] = {
        "sequence_number": sequence_number,
        "source_policy_ref": source_policy_ref,
        "source_revision": source_revision,
        "source_snapshot_hash": source_snapshot_hash,
        "capability_catalog": copy.deepcopy(capability_catalog),
        "provider_class": provider_class,
        "provider_identifier": provider_identifier,
        "translation_template_version": translation_template_version,
        "translation_template_hash": translation_template_hash,
        "request_configuration_id": request_configuration_id,
        "request_configuration_hash": request_configuration_hash,
        "request_hash": request_hash,
        "response_hash": response_hash,
        "explanation_hash": explanation_hash,
        "created_at": created_at,
        "completed_at": completed_at,
        "previous_run_hash": previous_run_hash,
    }
    result = {"run_id": "translation-run-" + canonical_sha256(core).removeprefix("sha256:"), **core}
    result["run_hash"] = artifact_hash(result, "run_hash")
    _validate_run_descriptor_intrinsic(result)
    return result


def create_policy_translation_run_evidence(
    run: dict[str, Any], *, request_bytes: bytes, response_bytes: bytes,
    provider_explanation: str | None = None,
) -> dict[str, Any]:
    """Create optional, private raw evidence that may be deleted independently."""
    if not isinstance(request_bytes, bytes) or not isinstance(response_bytes, bytes):
        raise ValueError("run evidence requires exact request and response bytes")
    _validate_run_descriptor_intrinsic(run)
    if provider_explanation is not None and (
        not isinstance(provider_explanation, str)
        or not provider_explanation.strip()
        or len(provider_explanation) > 4096
    ):
        raise ValueError("provider explanation must be null or bounded non-empty text")
    result = {
        "schema_version": POLICY_TRANSLATION_RUN_EVIDENCE_V1,
        "run_id": run.get("run_id"),
        "run_hash": run.get("run_hash"),
        "request_bytes_base64": base64.b64encode(request_bytes).decode("ascii"),
        "response_bytes_base64": base64.b64encode(response_bytes).decode("ascii"),
        "request_hash": bytes_sha256(request_bytes),
        "response_hash": bytes_sha256(response_bytes),
        "provider_explanation": provider_explanation,
        "explanation_hash": (
            bytes_sha256(provider_explanation.encode("utf-8"))
            if provider_explanation is not None
            else None
        ),
        "trust_posture": "private_untrusted_retention_evidence",
    }
    result["evidence_hash"] = artifact_hash(result, "evidence_hash")
    validate_policy_translation_run_evidence(run, result)
    return result


def validate_policy_translation_run_evidence(run: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate optional raw evidence against a run descriptor without making it authority."""
    _object(evidence, "run evidence")
    _validate_run_descriptor_intrinsic(run)
    _exact(evidence, {"schema_version", "run_id", "run_hash", "request_bytes_base64", "response_bytes_base64", "request_hash", "response_hash", "provider_explanation", "explanation_hash", "trust_posture", "evidence_hash"}, "run evidence")
    if evidence["schema_version"] != POLICY_TRANSLATION_RUN_EVIDENCE_V1:
        raise ValueError(f"run evidence must be {POLICY_TRANSLATION_RUN_EVIDENCE_V1}")
    if evidence["run_id"] != run.get("run_id") or evidence["run_hash"] != run.get("run_hash"):
        raise ValueError("run evidence is substituted across translation runs")
    request = _decode_base64(evidence["request_bytes_base64"], "run request bytes")
    response = _decode_base64(evidence["response_bytes_base64"], "run response bytes")
    if bytes_sha256(request) != evidence["request_hash"] or evidence["request_hash"] != run.get("request_hash"):
        raise ValueError("run request evidence hash is invalid")
    if bytes_sha256(response) != evidence["response_hash"] or evidence["response_hash"] != run.get("response_hash"):
        raise ValueError("run response evidence hash is invalid")
    explanation = evidence["provider_explanation"]
    if explanation is None:
        expected_explanation_hash = None
    else:
        if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 4096:
            raise ValueError("provider explanation must be null or bounded non-empty text")
        expected_explanation_hash = bytes_sha256(explanation.encode("utf-8"))
    if evidence["explanation_hash"] != expected_explanation_hash or run.get("explanation_hash") != expected_explanation_hash:
        raise ValueError("run provider-explanation hash is invalid")
    if evidence["trust_posture"] != "private_untrusted_retention_evidence":
        raise ValueError("raw run evidence must remain private and untrusted")
    if evidence["evidence_hash"] != artifact_hash(evidence, "evidence_hash"):
        raise ValueError("run evidence hash is invalid")
    return copy.deepcopy(evidence)


def create_policy_translation_proposal(
    source_bytes: bytes,
    *,
    source_policy_id: str,
    source_revision: str,
    authority_id: str,
    authority_version: str,
    clauses: list[dict[str, Any]],
    organizational_bindings: list[dict[str, Any]],
    translation_runs: list[dict[str, Any]],
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
    normalized_clauses: list[dict[str, Any]] = []
    for index, item in enumerate(clauses):
        if not isinstance(item, dict):
            raise ValueError(f"clauses[{index}] must be an object")
        _exact(
            item,
            {
                "start_byte",
                "end_byte",
                "coverage_status",
                "candidate_controls",
                "unresolved_binding_ids",
                "limitation_code",
                "residual_unsupported_spans",
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
        candidates = copy.deepcopy(item["candidate_controls"])
        if not isinstance(candidates, list):
            raise ValueError(f"clauses[{index}].candidate_controls must be an array")
        for candidate in candidates:
            if isinstance(candidate, dict) and "candidate_control_id" not in candidate:
                candidate["candidate_control_id"] = "candidate-control-" + canonical_sha256(candidate).removeprefix("sha256:")
        residual_spans = []
        if not isinstance(item["residual_unsupported_spans"], list):
            raise ValueError(f"clauses[{index}].residual_unsupported_spans must be an array")
        for residual_index, residual in enumerate(item["residual_unsupported_spans"]):
            _object(residual, f"clauses[{index}].residual_unsupported_spans[{residual_index}]")
            _exact(residual, {"start_byte", "end_byte"}, f"clauses[{index}].residual_unsupported_spans[{residual_index}]")
            residual_start, residual_end = residual["start_byte"], residual["end_byte"]
            residual_bytes = source_bytes[residual_start:residual_end] if isinstance(residual_start, int) and isinstance(residual_end, int) and 0 <= residual_start < residual_end <= len(source_bytes) else b""
            residual_core = {
                "clause_hash": statement_hash,
                "index": residual_index,
                "start_byte": residual_start,
                "end_byte": residual_end,
                "residual_hash": bytes_sha256(residual_bytes),
            }
            residual_spans.append(
                {
                    "residual_id": "policy-residual-" + canonical_sha256(residual_core).removeprefix("sha256:"),
                    "index": residual_index,
                    "start_byte": residual_start,
                    "end_byte": residual_end,
                    "residual_bytes_base64": base64.b64encode(residual_bytes).decode("ascii"),
                    "residual_hash": bytes_sha256(residual_bytes),
                }
            )
        normalized_clauses.append(
            {
                "clause_id": "policy-clause-" + canonical_sha256(clause_core).removeprefix("sha256:"),
                "index": index,
                "start_byte": start,
                "end_byte": end,
                "clause_bytes_base64": base64.b64encode(piece).decode("ascii"),
                "clause_hash": statement_hash,
                "coverage_status": item["coverage_status"],
                "candidate_controls": candidates,
                "unresolved_binding_ids": copy.deepcopy(item["unresolved_binding_ids"]),
                "limitation_code": item["limitation_code"],
                "residual_unsupported_spans": residual_spans,
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
        "translation_runs": copy.deepcopy(translation_runs),
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
            "translation_runs",
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

    catalog = resolve_policy_translation_capability_catalog(proposal["capability_catalog"])
    expected_ref = {
        key: catalog[key] for key in ("catalog_id", "catalog_version", "catalog_hash")
    }
    _validate_translation_runs(proposal["translation_runs"], source, expected_ref)

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

    bindings = _binding_index(proposal["organizational_bindings"], catalog)
    used_bindings: set[str] = set()
    status_counts = {status: 0 for status in sorted(_CLAUSE_COVERAGE_STATUSES)}
    for index, (clause, statement) in enumerate(zip(clauses, expected_statements)):
        if (
            statement["classification"] == "direct"
            and isinstance(clause, dict)
            and clause.get("coverage_status") != "fully_represented"
        ):
            raise ValueError("deterministically recognized source clause cannot be downgraded")
        _validate_clause(
            clause,
            index=index,
            statement=statement,
            source=source,
            exact_source=exact,
            bindings=bindings,
            used_bindings=used_bindings,
            catalog=catalog,
        )
        if statement["classification"] == "direct":
            actual = [
                _control_semantics(control, {})
                for control in clause["candidate_controls"]
            ]
            expected = _direct_statement_semantics(draft, statement["statement_id"])
            if actual != expected:
                raise ValueError("candidate controls do not completely match deterministic executable semantics")
        status_counts[clause["coverage_status"]] += 1
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
    decisions = {
        item["clause_id"]: item for item in state["clause_coverage_decisions"]
    }
    confirmed_controls = {
        item["candidate_control_id"] for item in state["control_confirmations"]
    }
    unresolved_bindings = [
        {
            "binding_id": item["binding_id"],
            "binding_type": item["binding_type"],
            "symbol": item["symbol"],
            "question": _render_binding_question(item["binding_type"]),
        }
        for item in proposal["organizational_bindings"]
        if item["binding_id"] not in resolutions
    ]
    unresolved_clauses = [
        {
            "clause_id": item["clause_id"],
            "coverage_status": item["coverage_status"],
            "unconfirmed_control_ids": [
                control["candidate_control_id"]
                for control in item["candidate_controls"]
                if control["candidate_control_id"] not in confirmed_controls
            ],
            "unresolved_binding_ids": [
                binding for binding in item["unresolved_binding_ids"] if binding not in resolutions
            ],
        }
        for item in proposal["clauses"]
        if item["clause_id"] not in decisions
    ]
    return {
        "view_type": "policy_translation_inspection",
        "proposal_validation": validation,
        "coverage": copy.deepcopy(state["coverage"]),
        "unresolved_bindings": unresolved_bindings,
        "unresolved_clauses": unresolved_clauses,
        "publication_ready": state["coverage"]["unresolved_clause_count"] == 0
        and state["coverage"]["unresolved_control_count"] == 0
        and state["coverage"]["confirmed_control_count"] > 0,
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
    catalog = resolve_policy_translation_capability_catalog(proposal["capability_catalog"])
    bindings = _binding_index(proposal["organizational_bindings"], catalog)
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


def apply_policy_translation_control_confirmation(
    proposal: dict[str, Any],
    confirmation: dict[str, Any] | None,
    *,
    clause_id: str,
    candidate_control_id: str,
    confirmed_by: str,
    confirmed_at: str,
) -> dict[str, Any]:
    """Individually confirm one validated candidate control."""
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation or _empty_confirmation(proposal))
    clause = next(
        (item for item in proposal["clauses"] if item["clause_id"] == clause_id),
        None,
    )
    if clause is None:
        raise ValueError("unknown proposal clause")
    control = next(
        (
            item
            for item in clause["candidate_controls"]
            if item["candidate_control_id"] == candidate_control_id
        ),
        None,
    )
    if control is None:
        raise ValueError("candidate control does not belong to the selected clause")
    if any(
        item["candidate_control_id"] == candidate_control_id
        for item in state["control_confirmations"]
    ):
        raise ValueError("candidate control is already human-confirmed")
    resolved = {item["binding_id"] for item in state["binding_resolutions"]}
    required = set(clause["unresolved_binding_ids"])
    if control["value"]["kind"] == "organizational_binding":
        required = {control["value"]["binding_id"]}
    else:
        required = set()
    if required - resolved:
        raise ValueError("candidate control requires a concrete organizational answer")
    record = {
        "clause_id": clause_id,
        "candidate_control_id": candidate_control_id,
        "confirmed_by": _nonempty(confirmed_by, "control confirmed_by"),
        "confirmed_at": _utc(confirmed_at, "control confirmed_at"),
    }
    record["confirmation_hash"] = artifact_hash(record, "confirmation_hash")
    result = copy.deepcopy(state)
    result["control_confirmations"].append(record)
    return _finalize_confirmation(proposal, result)


def apply_policy_translation_disposition(
    proposal: dict[str, Any],
    confirmation: dict[str, Any] | None,
    *,
    clause_id: str,
    coverage_status: str,
    confirmed_by: str,
    confirmed_at: str,
    reason_code: str,
    human_reason: str | None = None,
    acknowledge_unrepresented: bool = False,
) -> dict[str, Any]:
    """Human-confirm semantic coverage for one complete visible source clause."""
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation or _empty_confirmation(proposal))
    clauses = {item["clause_id"]: item for item in proposal["clauses"]}
    clause = clauses.get(clause_id)
    if clause is None:
        raise ValueError("unknown proposal clause")
    if any(item["clause_id"] == clause_id for item in state["clause_coverage_decisions"]):
        raise ValueError("proposal clause already has a human coverage decision")
    if coverage_status not in _CLAUSE_COVERAGE_STATUSES:
        raise ValueError("clause coverage decision is unknown")
    if coverage_status != clause["coverage_status"]:
        raise ValueError("human coverage decision must explicitly confirm the reviewed proposal coverage")
    if clause_id in _direct_clause_ids(proposal) and coverage_status != "fully_represented":
        raise ValueError("deterministically recognized source clause cannot be downgraded")
    resolved = {item["binding_id"] for item in state["binding_resolutions"]}
    missing = set(clause["unresolved_binding_ids"]) - resolved
    if missing:
        raise ValueError("all candidate-control bindings require concrete human answers")
    confirmed = {item["candidate_control_id"] for item in state["control_confirmations"]}
    unconfirmed = {
        item["candidate_control_id"] for item in clause["candidate_controls"]
    } - confirmed
    if unconfirmed:
        raise ValueError("every candidate control requires individual human confirmation")
    if coverage_status == "fully_represented":
        if acknowledge_unrepresented or reason_code != "human-confirmed-complete" or human_reason is not None:
            raise ValueError("fully represented clauses use the deterministic complete-coverage decision")
    elif coverage_status == "partially_represented":
        if not acknowledge_unrepresented or reason_code != "human-confirmed-partial":
            raise ValueError("partial representation requires explicit residual-meaning acknowledgement")
    elif coverage_status == "entirely_unsupported":
        if not acknowledge_unrepresented or reason_code not in {"outside-domain", "not-enforceable", "deferred", "other"}:
            raise ValueError("entirely unsupported meaning requires explicit bounded acknowledgement")
    elif acknowledge_unrepresented or reason_code not in {"context-only", "descriptive", "non-policy", "other"}:
        raise ValueError("informational coverage decision is inconsistent")
    if reason_code == "other" and (not isinstance(human_reason, str) or not human_reason.strip()):
        raise ValueError("reason_code other requires a human_reason")
    if human_reason is not None and (not isinstance(human_reason, str) or not human_reason.strip() or len(human_reason) > 1024):
        raise ValueError("human_reason must be null or 1 to 1024 non-whitespace characters")
    decision = {
        "clause_id": clause_id,
        "coverage_status": coverage_status,
        "reason_code": reason_code,
        "human_reason": human_reason,
        "acknowledged_unrepresented": acknowledge_unrepresented,
        "confirmed_by": _nonempty(confirmed_by, "confirmed_by"),
        "confirmed_at": _utc(confirmed_at, "confirmed_at"),
    }
    decision["decision_hash"] = artifact_hash(decision, "decision_hash")
    result = copy.deepcopy(state)
    result["clause_coverage_decisions"].append(decision)
    return _finalize_confirmation(proposal, result)


def render_policy_translation_review(
    proposal: dict[str, Any], confirmation: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Render deterministic operational meaning solely from validated controls."""
    review = _build_policy_translation_review(proposal, confirmation)
    validate_policy_translation_review(proposal, confirmation, review)
    return review


def _build_policy_translation_review(
    proposal: dict[str, Any], confirmation: dict[str, Any] | None = None
) -> dict[str, Any]:
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation or _empty_confirmation(proposal))
    resolutions = {item["binding_id"]: item["value"] for item in state["binding_resolutions"]}
    decisions = {
        item["clause_id"]: item for item in state["clause_coverage_decisions"]
    }
    confirmed_controls = {
        item["candidate_control_id"] for item in state["control_confirmations"]
    }
    catalog = resolve_policy_translation_capability_catalog(proposal["capability_catalog"])
    bindings = _binding_index(proposal["organizational_bindings"], catalog)
    exact = _decode_base64(proposal["source_policy"]["source_bytes_base64"], "source bytes")
    rows = []
    for clause in proposal["clauses"]:
        decision = decisions.get(clause["clause_id"])
        control_rows = []
        for control in clause["candidate_controls"]:
            remaining = []
            questions = []
            if control["value"]["kind"] == "organizational_binding":
                binding_id = control["value"]["binding_id"]
                if binding_id not in resolutions:
                    remaining.append(binding_id)
                    questions.append(
                        _render_binding_question(bindings[binding_id]["binding_type"])
                    )
            control_rows.append(
                {
                    "candidate_control_id": control["candidate_control_id"],
                    "human_confirmed": control["candidate_control_id"] in confirmed_controls,
                    "operational_explanation": _render_control(control, resolutions),
                    "remaining_unresolved_bindings": remaining,
                    "questions": questions,
                    "technical_details": {
                        "control_type": control["control_type"],
                        "fact_id": control["fact_id"],
                        "operator": control["operator"],
                        "effect": control["effect"],
                        "enforcement_point": control["enforcement_point"],
                    },
                }
            )
        rows.append(
            {
                "clause_id": clause["clause_id"],
                "source_text": exact[clause["start_byte"] : clause["end_byte"]].decode("utf-8"),
                "proposed_coverage_status": clause["coverage_status"],
                "human_coverage_status": decision["coverage_status"] if decision else None,
                "controls": control_rows,
                "residual_explanation": _render_residual(clause),
            }
        )
    review = {
        "schema_version": POLICY_TRANSLATION_REVIEW_V1,
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


def validate_policy_translation_review(
    proposal: dict[str, Any], confirmation: dict[str, Any] | None,
    review: dict[str, Any],
) -> dict[str, Any]:
    """Validate the strict, approval-bound deterministic review artifact."""
    _object(review, "policy translation review")
    _exact(
        review,
        {
            "schema_version", "proposal_id", "proposal_hash", "source_policy_ref",
            "source_snapshot_hash", "authority_ref", "capability_catalog",
            "coverage", "clauses", "provider_explanations_used", "review_hash",
        },
        "policy translation review",
    )
    if review["schema_version"] != POLICY_TRANSLATION_REVIEW_V1:
        raise ValueError(f"policy translation review must be {POLICY_TRANSLATION_REVIEW_V1}")
    expected = _build_policy_translation_review(proposal, confirmation)
    if review != expected:
        raise ValueError("policy translation review is not the deterministic rendering")
    if review["review_hash"] != artifact_hash(review, "review_hash"):
        raise ValueError("policy translation review hash is invalid")
    return copy.deepcopy(review)


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
        raise ValueError("publication approval requires a coverage decision for every source clause")
    if coverage["unresolved_control_count"]:
        raise ValueError("publication approval requires individual confirmation of every candidate control")
    if coverage["confirmed_control_count"] == 0:
        raise ValueError("publication approval requires at least one confirmed control")
    if coverage["unrepresented_clause_count"] != len(coverage["acknowledged_unrepresented_clause_ids"]):
        raise ValueError("partial coverage requires acknowledgement of every unrepresented clause or residual")
    approval_time = _utc_datetime(approved_at, "approved_at")
    if any(
        _utc_datetime(run["completed_at"], "translation run completed_at") > approval_time
        for run in proposal["translation_runs"]
    ):
        raise ValueError("every translation run must complete no later than proposal approval")
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
    decisions = {
        item["clause_id"]: item for item in state["clause_coverage_decisions"]
    }
    for clause, statement in zip(proposal["clauses"], draft["source_statements"]):
        decision = decisions[clause["clause_id"]]
        controls = clause["candidate_controls"]
        if statement["classification"] == "direct":
            if decision["coverage_status"] != "fully_represented":
                raise ValueError("a deterministically compiled source clause cannot silently become unenforced")
            expected = [_control_semantics(control, resolutions) for control in controls]
            actual = _direct_statement_semantics(draft, statement["statement_id"])
            if expected != actual:
                raise ValueError("candidate controls contradict deterministic executable constraints")
            continue
        if decision["coverage_status"] == "partially_represented":
            raise ValueError(
                "released authority_bundle.v2 cannot represent enforced and residual unsupported meaning within one pending source statement"
            )
        if len(controls) > 1:
            raise ValueError(
                "released authority_bundle.v2 cannot reconstruct multiple human-mapped controls for one pending source statement"
            )
        kwargs: dict[str, Any] = {
            "statement_id": statement["statement_id"],
            "disposition": (
                "enforced"
                if decision["coverage_status"] in {"fully_represented", "partially_represented"}
                else "unsupported"
                if decision["coverage_status"] == "entirely_unsupported"
                else "informational"
            ),
            "mapper_identity": decision["confirmed_by"],
            "mapped_at": decision["confirmed_at"],
        }
        if controls:
            control_id, selections = _control_selections(controls[0], resolutions)
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
    catalog: dict[str, Any],
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
            "coverage_status",
            "candidate_controls",
            "unresolved_binding_ids",
            "limitation_code",
            "residual_unsupported_spans",
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
    status = clause["coverage_status"]
    if status not in _CLAUSE_COVERAGE_STATUSES:
        raise ValueError("proposal clause coverage status is unknown")
    if clause["limitation_code"] not in _LIMITATIONS:
        raise ValueError("proposal clause limitation code is unknown")
    unresolved = clause["unresolved_binding_ids"]
    if not isinstance(unresolved, list) or unresolved != sorted(set(unresolved)):
        raise ValueError("unresolved_binding_ids must be a sorted unique array")
    residuals = clause["residual_unsupported_spans"]
    _validate_residual_spans(
        residuals,
        clause=clause,
        exact_source=exact_source,
    )
    controls = clause["candidate_controls"]
    if not isinstance(controls, list):
        raise ValueError("candidate_controls must be an ordered array")
    referenced: list[str] = []
    seen_control_ids: set[str] = set()
    seen_semantics: set[str] = set()
    contradiction_keys: dict[str, str] = {}
    for control in controls:
        control_bindings = _validate_candidate_control(
            control,
            exact_source=exact_source,
            clause_start=clause["start_byte"],
            clause_end=clause["end_byte"],
            bindings=bindings,
            catalog=catalog,
        )
        control_id = control["candidate_control_id"]
        value_semantics = (
            {
                "kind": "source_literal",
                "canonical_value": control["value"]["canonical_value"],
            }
            if control["value"]["kind"] == "source_literal"
            else {
                "kind": "organizational_binding",
                "binding_id": control["value"]["binding_id"],
            }
        )
        executable_semantics = {
            key: control[key]
            for key in (
                "control_type", "actor_kind", "action", "resource_kind", "fact_id",
                "operator", "effect", "enforcement_point", "required_runtime_facts",
            )
        }
        executable_semantics["value"] = value_semantics
        semantic_hash = canonical_sha256(executable_semantics)
        if control_id in seen_control_ids or semantic_hash in seen_semantics:
            raise ValueError("candidate controls contain a duplicate control")
        seen_control_ids.add(control_id)
        seen_semantics.add(semantic_hash)
        contradiction_key = canonical_sha256(
            {
                key: value
                for key, value in executable_semantics.items()
                if key != "effect"
            }
        )
        prior_effect = contradiction_keys.get(contradiction_key)
        if prior_effect is not None and prior_effect != control["effect"]:
            raise ValueError("candidate controls contain contradictory effects")
        contradiction_keys[contradiction_key] = control["effect"]
        referenced.extend(control_bindings)
    if unresolved != sorted(referenced):
        raise ValueError("candidate controls unresolved bindings are inconsistent")
    overlap = used_bindings & set(referenced)
    if overlap or len(referenced) != len(set(referenced)):
        raise ValueError("an organizational binding cannot be guessed or reused across candidate controls")
    used_bindings.update(referenced)
    if status == "fully_represented":
        if not controls or residuals or clause["limitation_code"] is not None:
            raise ValueError("fully represented clauses require controls and no residual unsupported meaning")
    elif status == "partially_represented":
        if not controls or not residuals or clause["limitation_code"] is None:
            raise ValueError("partially represented clauses require controls and explicit residual unsupported meaning")
    elif status == "entirely_unsupported":
        if controls or unresolved or not residuals or clause["limitation_code"] is None:
            raise ValueError("entirely unsupported clauses require exact residual meaning and no controls")
    elif controls or unresolved or residuals or clause["limitation_code"] is not None:
        raise ValueError("informational clauses cannot claim controls or unsupported residual meaning")


def _validate_residual_spans(
    residuals: Any, *, clause: dict[str, Any], exact_source: bytes
) -> None:
    if not isinstance(residuals, list):
        raise ValueError("residual_unsupported_spans must be an ordered array")
    previous_end: int | None = None
    for index, residual in enumerate(residuals):
        label = f"residual_unsupported_spans[{index}]"
        _object(residual, label)
        _exact(
            residual,
            {
                "residual_id", "index", "start_byte", "end_byte",
                "residual_bytes_base64", "residual_hash",
            },
            label,
        )
        start, end = residual["start_byte"], residual["end_byte"]
        if residual["index"] != index or not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise ValueError("residual unsupported spans must use ordered integer positions")
        if not (clause["start_byte"] <= start < end <= clause["end_byte"]):
            raise ValueError("residual unsupported span must be contained by its clause")
        if previous_end is not None and start < previous_end:
            raise ValueError("residual unsupported spans overlap or are reordered")
        piece = exact_source[start:end]
        if _decode_base64(residual["residual_bytes_base64"], f"{label} bytes") != piece or residual["residual_hash"] != bytes_sha256(piece):
            raise ValueError("residual unsupported span does not reproduce exact source bytes")
        core = {
            "clause_hash": clause["clause_hash"],
            "index": index,
            "start_byte": start,
            "end_byte": end,
            "residual_hash": residual["residual_hash"],
        }
        if residual["residual_id"] != "policy-residual-" + canonical_sha256(core).removeprefix("sha256:"):
            raise ValueError("residual unsupported span identity is invalid")
        previous_end = end


def _validate_candidate_control(
    control: dict[str, Any], *, exact_source: bytes, clause_start: int,
    clause_end: int, bindings: dict[str, dict[str, Any]], catalog: dict[str, Any]
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
    control_catalog = {
        item["control_type"]: item for item in catalog["control_types"]
    }
    if control_type not in control_catalog:
        raise ValueError("candidate control uses an unknown or invented control capability")
    advertised = control_catalog[control_type]
    spec = _CONTROL_SPECS.get(control_type)
    if spec is None:
        raise ValueError("registered catalog control has no installed compiler lowering")
    if control["actor_kind"] not in catalog["actor_kinds"]:
        raise ValueError("candidate control uses an unknown actor capability")
    if control["action"] not in catalog["actions"] or control["action"] != advertised["action"]:
        raise ValueError("candidate control uses an unknown action capability")
    if control["resource_kind"] != advertised["resource_kind"]:
        raise ValueError("candidate control uses an unavailable resource capability")
    if control["fact_id"] != advertised["fact_id"] or control["fact_id"] not in {item["fact_id"] for item in catalog["facts"]}:
        raise ValueError("candidate control uses an unknown or unavailable runtime fact")
    if control["operator"] != advertised["operator"] or control["operator"] not in catalog["operators"]:
        raise ValueError("candidate control uses an unknown or type-invalid operator")
    if control["effect"] not in advertised["effects"] or control["effect"] not in catalog["effects"]:
        raise ValueError("candidate control effect is incompatible with its executable control")
    points = {item["enforcement_point_id"] for item in catalog["enforcement_points"]}
    if control["enforcement_point"] not in points:
        raise ValueError("candidate control uses an unknown enforcement point")
    if control["required_runtime_facts"] != advertised["required_runtime_facts"]:
        raise ValueError("candidate control requires unknown, unavailable, or omitted runtime facts")
    value = control["value"]
    _object(value, "candidate control value")
    kind = value.get("kind")
    if kind == "source_literal":
        _exact(value, {"kind", "value", "canonical_value", "start_byte", "end_byte", "literal_hash"}, "candidate control source literal")
        literal = _nonempty(value["value"], "candidate control source literal")
        canonical_value = _nonempty(value["canonical_value"], "candidate control canonical source value")
        start, end = value["start_byte"], value["end_byte"]
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise ValueError("candidate control source literal span must use integers")
        if not (clause_start <= start < end <= clause_end):
            raise ValueError("candidate control source literal span must be contained by its clause")
        try:
            encoded = literal.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("candidate control source literal must be UTF-8") from exc
        exact_literal = exact_source[start:end]
        if exact_literal != encoded:
            raise ValueError("candidate control path or identity is guessed rather than present in its exact source span")
        if value["literal_hash"] != bytes_sha256(exact_literal):
            raise ValueError("candidate control source literal hash is invalid")
        _validate_literal_boundaries(exact_source, start, end)
        expected_canonical = _canonical_source_literal(control_type, literal)
        if canonical_value != expected_canonical:
            raise ValueError("candidate control source literal canonical value is not deterministically derived")
        _validate_control_value(control_type, canonical_value)
        return []
    if kind == "organizational_binding":
        _exact(value, {"kind", "binding_id"}, "candidate control organizational binding")
        binding_id = _nonempty(value["binding_id"], "candidate control binding_id")
        binding = bindings.get(binding_id)
        if binding is None:
            raise ValueError("candidate control references an unknown organizational binding")
        if binding["binding_type"] not in spec["binding_types"] or binding["binding_type"] not in advertised["binding_types"]:
            raise ValueError("candidate control organizational binding has an invalid type")
        return [binding_id]
    raise ValueError("candidate control value must be an exact source literal or unresolved organizational binding")


def _binding_index(
    value: Any, catalog: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
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
        advertised_binding_types = set(
            (catalog or get_policy_translation_capability_catalog())["binding_types"]
        )
        if binding["binding_type"] not in advertised_binding_types:
            raise ValueError("unknown organizational binding type")
        _nonempty(binding["symbol"], f"{label}.symbol")
        _nonempty(binding["question"], f"{label}.question")
        if binding["status"] != "unresolved":
            raise ValueError("provider output cannot present an organizational symbol as resolved")
        result[binding_id] = binding
    return result


def _validate_translation_runs(
    runs: Any, source: dict[str, Any], catalog_ref: dict[str, str]
) -> None:
    if not isinstance(runs, list) or not runs:
        raise ValueError("translation_runs must be a non-empty ordered collection")
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    previous: str | None = None
    previous_completed: datetime | None = None
    for index, run in enumerate(runs):
        _validate_run_descriptor_intrinsic(run)
        if run["sequence_number"] != index:
            raise ValueError("translation runs are missing, reordered, or duplicated")
        if run["previous_run_hash"] != previous:
            raise ValueError("translation run ordering chain is invalid")
        if run["source_policy_ref"] != source["source_policy_ref"] or run["source_revision"] != source["source_revision"] or run["source_snapshot_hash"] != source["snapshot_hash"]:
            raise ValueError("translation run is substituted across source bytes or revision")
        if run["capability_catalog"] != catalog_ref:
            raise ValueError("translation run is substituted across capability catalogs")
        created = _utc_datetime(run["created_at"], "translation run created_at")
        completed = _utc_datetime(run["completed_at"], "translation run completed_at")
        if previous_completed is not None and created < previous_completed:
            raise ValueError("a subsequent translation run cannot begin before the preceding run completes")
        if run["run_id"] in seen_ids or run["run_hash"] in seen_hashes:
            raise ValueError("translation runs are duplicated")
        seen_ids.add(run["run_id"])
        seen_hashes.add(run["run_hash"])
        previous = run["run_hash"]
        previous_completed = completed


def _validate_run_descriptor_intrinsic(run: Any) -> None:
    _object(run, "translation run")
    fields = {
        "run_id", "run_hash", "sequence_number", "source_policy_ref",
        "source_revision", "source_snapshot_hash", "capability_catalog",
        "provider_class", "provider_identifier", "translation_template_version",
        "translation_template_hash", "request_configuration_id",
        "request_configuration_hash", "request_hash", "response_hash",
        "explanation_hash", "created_at", "completed_at", "previous_run_hash",
    }
    _exact(run, fields, "translation run")
    sequence = run["sequence_number"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("translation run sequence_number must be a non-negative integer")
    if sequence == 0 and run["previous_run_hash"] is not None:
        raise ValueError("the first translation run cannot name a previous run")
    if sequence > 0:
        _sha256(run["previous_run_hash"], "previous_run_hash")
    _nonempty(run["source_policy_ref"], "translation run source_policy_ref")
    _nonempty(run["source_revision"], "translation run source_revision")
    _sha256(run["source_snapshot_hash"], "translation run source_snapshot_hash")
    _object(run["capability_catalog"], "translation run capability catalog")
    _exact(run["capability_catalog"], {"catalog_id", "catalog_version", "catalog_hash"}, "translation run capability catalog")
    _nonempty(run["capability_catalog"]["catalog_id"], "translation run catalog_id")
    _nonempty(run["capability_catalog"]["catalog_version"], "translation run catalog_version")
    _sha256(run["capability_catalog"]["catalog_hash"], "translation run catalog_hash")
    resolve_policy_translation_capability_catalog(run["capability_catalog"])
    if run["provider_class"] not in {"hosted_model", "local_model", "guided_deterministic", "other"}:
        raise ValueError("translation run provider class is unknown")
    if run["provider_class"] in {"hosted_model", "local_model"}:
        _nonempty(run["provider_identifier"], "model/deployment identifier")
    elif run["provider_identifier"] is not None:
        _nonempty(run["provider_identifier"], "provider identifier")
    for field in ("translation_template_version", "request_configuration_id"):
        _nonempty(run[field], field)
    for field in ("translation_template_hash", "request_configuration_hash", "request_hash", "response_hash"):
        _sha256(run[field], field)
    if run["explanation_hash"] is not None:
        _sha256(run["explanation_hash"], "explanation_hash")
    created = _utc_datetime(run["created_at"], "translation run created_at")
    completed = _utc_datetime(run["completed_at"], "translation run completed_at")
    if completed < created:
        raise ValueError("translation run completion precedes creation")
    core = {key: value for key, value in run.items() if key not in {"run_id", "run_hash"}}
    expected_id = "translation-run-" + canonical_sha256(core).removeprefix("sha256:")
    if run["run_id"] != expected_id or run["run_hash"] != artifact_hash(run, "run_hash"):
        raise ValueError("translation run identity or hash is invalid")


def _validate_literal_boundaries(source: bytes, start: int, end: int) -> None:
    """Require a complete UTF-8 policy token while allowing quote/backtick boundaries."""
    try:
        before = source[:start].decode("utf-8")
        after = source[end:].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("candidate control source literal span must align to UTF-8 boundaries") from exc
    if before and (before[-1].isalnum() or before[-1] in "_./-"):
        raise ValueError("candidate control source literal begins inside a larger token")
    if after and (after[0].isalnum() or after[0] in "_/-"):
        raise ValueError("candidate control source literal ends inside a larger token")
    # A dot followed by a token character is an extension/suffix, not sentence punctuation.
    if after.startswith(".") and len(after) > 1 and (after[1].isalnum() or after[1] in "_/-"):
        raise ValueError("candidate control source literal ends inside a larger dotted token")


def _empty_confirmation(proposal: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema_version": POLICY_TRANSLATION_CONFIRMATION_V1,
        "proposal_id": proposal["proposal_id"],
        "proposal_hash": proposal["proposal_hash"],
        "source_snapshot_hash": proposal["source_policy"]["snapshot_hash"],
        "authority_ref": proposal["authority"]["authority_ref"],
        "binding_resolutions": [],
        "control_confirmations": [],
        "clause_coverage_decisions": [],
        "coverage": _coverage(proposal, [], []),
    }
    result["confirmation_hash"] = artifact_hash(result, "confirmation_hash")
    return result


def _finalize_confirmation(proposal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(state)
    result["coverage"] = _coverage(
        proposal,
        result["control_confirmations"],
        result["clause_coverage_decisions"],
    )
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
            "control_confirmations",
            "clause_coverage_decisions",
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
    catalog = resolve_policy_translation_capability_catalog(proposal["capability_catalog"])
    catalog_ref = {key: catalog[key] for key in ("catalog_id", "catalog_version", "catalog_hash")}
    _validate_translation_runs(proposal["translation_runs"], proposal["source_policy"], catalog_ref)
    final_run_completed = _utc_datetime(
        proposal["translation_runs"][-1]["completed_at"],
        "translation run completed_at",
    )
    bindings = _binding_index(proposal["organizational_bindings"], catalog)
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
        if _utc_datetime(record["confirmed_at"], "binding confirmed_at") < final_run_completed:
            raise ValueError("human confirmation cannot precede the final translation run")
        if record["resolution_hash"] != artifact_hash(record, "resolution_hash"):
            raise ValueError("binding resolution hash is invalid")
    clauses = {item["clause_id"]: item for item in proposal["clauses"]}
    controls = {
        control["candidate_control_id"]: (clause, control)
        for clause in proposal["clauses"]
        for control in clause["candidate_controls"]
    }
    seen_controls: set[str] = set()
    for record in state["control_confirmations"]:
        _exact(record, {"clause_id", "candidate_control_id", "confirmed_by", "confirmed_at", "confirmation_hash"}, "control confirmation")
        control_id = record["candidate_control_id"]
        if control_id in seen_controls or control_id not in controls:
            raise ValueError("control confirmation is duplicated or unknown")
        seen_controls.add(control_id)
        clause, control = controls[control_id]
        if record["clause_id"] != clause["clause_id"]:
            raise ValueError("control confirmation is substituted across clauses")
        if control["value"]["kind"] == "organizational_binding" and control["value"]["binding_id"] not in seen_bindings:
            raise ValueError("control confirmation precedes its required organizational answer")
        _nonempty(record["confirmed_by"], "control confirmed_by")
        confirmed_at = _utc_datetime(record["confirmed_at"], "control confirmed_at")
        if confirmed_at < final_run_completed:
            raise ValueError("human confirmation cannot precede the final translation run")
        if record["confirmation_hash"] != artifact_hash(record, "confirmation_hash"):
            raise ValueError("control confirmation hash is invalid")
    direct_clause_ids = _direct_clause_ids(proposal)
    seen_clauses: set[str] = set()
    resolved = {item["binding_id"] for item in state["binding_resolutions"]}
    for decision in state["clause_coverage_decisions"]:
        _exact(decision, {"clause_id", "coverage_status", "reason_code", "human_reason", "acknowledged_unrepresented", "confirmed_by", "confirmed_at", "decision_hash"}, "clause coverage decision")
        clause_id = decision["clause_id"]
        if clause_id in seen_clauses or clause_id not in clauses:
            raise ValueError("clause decision is duplicated or unknown")
        seen_clauses.add(clause_id)
        clause = clauses[clause_id]
        status = decision["coverage_status"]
        if status != clause["coverage_status"]:
            raise ValueError("clause coverage decision does not match the reviewed proposal")
        if clause_id in direct_clause_ids and status != "fully_represented":
            raise ValueError("deterministically recognized source clause cannot be downgraded")
        if set(clause["unresolved_binding_ids"]) - resolved:
            raise ValueError("clause coverage decision has unresolved organizational meaning")
        if any(control["candidate_control_id"] not in seen_controls for control in clause["candidate_controls"]):
            raise ValueError("clause coverage decision requires every control's individual confirmation")
        if status == "fully_represented":
            if decision["reason_code"] != "human-confirmed-complete" or decision["human_reason"] is not None or decision["acknowledged_unrepresented"]:
                raise ValueError("fully represented clause decision is inconsistent")
        elif status == "partially_represented":
            if decision["reason_code"] != "human-confirmed-partial" or not decision["acknowledged_unrepresented"]:
                raise ValueError("partially represented clause lacks residual acknowledgement")
        elif status == "entirely_unsupported":
            if decision["reason_code"] not in {"outside-domain", "not-enforceable", "deferred", "other"} or not decision["acknowledged_unrepresented"]:
                raise ValueError("entirely unsupported clause decision is inconsistent")
        elif status == "informational":
            if decision["reason_code"] not in {"context-only", "descriptive", "non-policy", "other"} or decision["acknowledged_unrepresented"]:
                raise ValueError("informational clause decision is inconsistent")
        else:
            raise ValueError("clause coverage decision is invalid")
        if decision["reason_code"] == "other" and (not isinstance(decision["human_reason"], str) or not decision["human_reason"].strip()):
            raise ValueError("reason_code other requires a human_reason")
        _nonempty(decision["confirmed_by"], "clause confirmed_by")
        confirmed_at = _utc_datetime(decision["confirmed_at"], "clause confirmed_at")
        if confirmed_at < final_run_completed:
            raise ValueError("human confirmation cannot precede the final translation run")
        if decision["decision_hash"] != artifact_hash(decision, "decision_hash"):
            raise ValueError("clause decision hash is invalid")
    expected_coverage = _coverage(
        proposal,
        state["control_confirmations"],
        state["clause_coverage_decisions"],
    )
    if state["coverage"] != expected_coverage:
        raise ValueError("confirmation coverage counts are inconsistent")
    if state["confirmation_hash"] != artifact_hash(state, "confirmation_hash"):
        raise ValueError("confirmation hash is invalid")
    return copy.deepcopy(state)


def _coverage(
    proposal: dict[str, Any],
    control_confirmations: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_by_clause = {item["clause_id"]: item for item in decisions}
    status_ids = {
        status: sorted(
            clause_id
            for clause_id, decision in decision_by_clause.items()
            if decision["coverage_status"] == status
        )
        for status in sorted(_CLAUSE_COVERAGE_STATUSES)
    }
    enforced = sorted(status_ids["fully_represented"] + status_ids["partially_represented"])
    # A partially represented clause truthfully appears in both sets: it has at least
    # one enforced mapping and explicitly acknowledged meaning that remains unenforced.
    unenforced = sorted(
        status_ids["partially_represented"]
        + status_ids["entirely_unsupported"]
        + status_ids["informational"]
    )
    unrepresented = sorted(status_ids["partially_represented"] + status_ids["entirely_unsupported"])
    acknowledged = sorted(
        item["clause_id"] for item in decisions if item["acknowledged_unrepresented"]
    )
    control_ids = sorted(
        control["candidate_control_id"]
        for clause in proposal["clauses"]
        for control in clause["candidate_controls"]
    )
    confirmed_control_ids = sorted(item["candidate_control_id"] for item in control_confirmations)
    total = len(proposal["clauses"])
    return {
        "total_clause_count": total,
        "enforced_clause_count": len(enforced),
        "unenforced_clause_count": len(unenforced),
        "unresolved_clause_count": total - len(decisions),
        "fully_represented_clause_count": len(status_ids["fully_represented"]),
        "partially_represented_clause_count": len(status_ids["partially_represented"]),
        "entirely_unsupported_clause_count": len(status_ids["entirely_unsupported"]),
        "informational_clause_count": len(status_ids["informational"]),
        "unrepresented_clause_count": len(unrepresented),
        "enforced_clause_ids": enforced,
        "unenforced_clause_ids": unenforced,
        "acknowledged_unrepresented_clause_ids": acknowledged,
        "total_control_count": len(control_ids),
        "confirmed_control_count": len(confirmed_control_ids),
        "unresolved_control_count": len(control_ids) - len(confirmed_control_ids),
        "confirmed_control_ids": confirmed_control_ids,
        "unresolved_control_ids": sorted(set(control_ids) - set(confirmed_control_ids)),
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
    if any(
        _utc_datetime(run["completed_at"], "translation run completed_at") > approval_time
        for run in proposal["translation_runs"]
    ):
        raise ValueError("every translation run must complete no later than proposal approval")
    confirmations = [
        *state["binding_resolutions"],
        *state["control_confirmations"],
        *state["clause_coverage_decisions"],
    ]
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
    selected = value["canonical_value"] if value["kind"] == "source_literal" else resolutions[value["binding_id"]]
    spec = _CONTROL_SPECS[control["control_type"]]
    if control["control_type"] == "acting_role":
        return spec["mapping_control_id"], {"role": selected}
    return spec["mapping_control_id"], {"effect": control["effect"], "path": selected}


def _control_semantics(control: dict[str, Any], resolutions: dict[str, str]) -> dict[str, Any]:
    control_id, selections = _control_selections(control, resolutions)
    if control_id == "acting-role":
        return {"control_id": control_id, "role": selections["role"]}
    return {"control_id": control_id, "effect": selections["effect"], "path": selections["path"]}


def _direct_statement_semantics(draft: dict[str, Any], statement_id: str) -> list[dict[str, Any]]:
    mapping = next(item for item in draft["source_to_constraint_mappings"] if item["statement_id"] == statement_id)
    constraints = {
        item["constraint_id"]: item for item in draft["constraint_ir"]["constraints"]
    }
    return [
        _direct_constraint_semantics(constraints[constraint_id])
        for constraint_id in mapping["constraint_ids"]
    ]


def _direct_constraint_semantics(constraint: dict[str, Any]) -> dict[str, Any]:
    if constraint["acting_role"]:
        return {"control_id": "acting-role", "role": constraint["acting_role"]["value"]}
    match = constraint["resource"]["match"]
    return {
        "control_id": "exact-path-access" if match == "exact" else "prefix-path-access",
        "effect": constraint["effect"],
        "path": constraint["resource"]["value"],
    }


def _direct_clause_ids(proposal: dict[str, Any]) -> set[str]:
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
    return {
        clause["clause_id"]
        for clause, statement in zip(proposal["clauses"], draft["source_statements"])
        if statement["classification"] == "direct"
    }


def _render_control(control: dict[str, Any], resolutions: dict[str, str]) -> str:
    value = control["value"]
    selected = value.get("canonical_value") if value["kind"] == "source_literal" else resolutions.get(value["binding_id"])
    if control["control_type"] == "acting_role":
        if selected is None:
            return "A repository role must be confirmed before automated agents may modify this repository."
        return f"Automated agents must use repository role {selected!r} to modify this repository."
    if control["control_type"] == "prefix_path_access":
        if selected is None:
            if control["effect"] == "deny":
                return "Automated agents are blocked from modifying files under the repository path prefix you confirm."
            return "Automated agents may modify files under the repository path prefix you confirm."
        if control["effect"] == "deny":
            return f"Automated agents are blocked from modifying files under {selected}."
        return f"Automated agents may modify files under {selected}."
    if selected is None:
        consequence = "are blocked from modifying" if control["effect"] == "deny" else "may modify"
        return f"Automated agents {consequence} the exact repository path you confirm."
    if control["effect"] == "deny":
        return f"Automated agents are blocked from modifying {selected}."
    return f"Automated agents may modify {selected}."


def _render_binding_question(binding_type: str) -> str:
    questions = {
        "repository_role": "Which repository role should this policy require?",
        "repository_exact_path": "Which exact repository path should this policy apply to?",
        "repository_path_prefix": "Which repository path prefix should this policy apply to?",
    }
    try:
        return questions[binding_type]
    except KeyError as exc:
        raise ValueError(
            "registered binding type has no deterministic customer question"
        ) from exc


def _render_residual(clause: dict[str, Any]) -> str | None:
    if clause["coverage_status"] == "informational":
        return "This clause is informational and does not create an enforcement rule."
    if not clause["residual_unsupported_spans"]:
        return None
    if clause["limitation_code"] == "pull_request_approval_not_supported":
        return "Waveframe cannot enforce this part yet because pull-request approvals are not currently supported."
    return "Waveframe cannot enforce the explicitly identified remaining part of this clause yet."


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


def _canonical_source_literal(control_type: str, literal: str) -> str:
    if control_type != "acting_role":
        return literal
    normalized = literal.strip().lower()
    pack = get_builtin_domain_pack(REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION)
    for canonical, synonyms in pack["synonyms"].items():
        if canonical in pack["role_kinds"] and normalized in {canonical, *synonyms}:
            return canonical
    return literal


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
