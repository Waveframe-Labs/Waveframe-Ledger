"""Provider-free normative publication for approved policy translations.

This additive v3 path preserves the released v2 implementation unchanged.  It binds
clause-to-many-control meaning and acknowledged residual spans in a public commitment;
private translation-run evidence is neither embedded nor required for verification.
"""

from __future__ import annotations

import copy
from typing import Any

from governance_ledger.constraint_ir import (
    artifact_hash,
    validate_constraint_ir,
    validate_runtime_fact_compatibility,
)
from governance_ledger.domain_packs import (
    REPOSITORY_CHANGES_PACK_ID,
    REPOSITORY_CHANGES_PACK_VERSION,
    get_builtin_domain_pack,
    mapping_control_index,
)
from governance_ledger.domain_policy import (
    _build_ir,
    _compile_domain_contract_v2,
    _constraint_from_control,
    _finalize_constraint,
    _lower_constraint,
    _pack_ref,
    _validate_compiled_authority_contract_v2,
    interpret_policy_with_domain_pack,
)
from governance_ledger.policy_translation import (
    _control_selections,
    _decode_base64,
    _direct_statement_semantics,
    _render_control,
    _render_residual,
    _utc,
    _utc_datetime,
    _validate_approval,
    _validate_binding_value,
    _validate_candidate_control,
    _validate_confirmation,
    _validate_residual_spans,
    resolve_policy_translation_capability_catalog,
    validate_policy_translation_proposal,
)
from governance_ledger.publication_provenance import bytes_sha256, canonical_sha256
from governance_ledger.semantics.compiler import build_semantic_commit_bundle
from governance_ledger.semantics.preview import build_governance_impact_preview


POLICY_TRANSLATION_COMMITMENT_V1 = "policy_translation_commitment.v1"
AUTHORITY_BUNDLE_V3 = "authority_bundle.v3"
PUBLICATION_RECEIPT_V3 = "publication_receipt.v3"

READY_TO_ENFORCE = "Ready to enforce"
NEEDS_AN_ANSWER = "Needs an answer"
NEEDS_A_CONNECTION = "Needs a connection"
PARTIALLY_ENFORCEABLE = "Partially enforceable"
NOT_CURRENTLY_ENFORCEABLE = "Not currently enforceable"
INFORMATIONAL = "Informational"

_CUSTOMER_STATES = {
    READY_TO_ENFORCE,
    NEEDS_AN_ANSWER,
    NEEDS_A_CONNECTION,
    PARTIALLY_ENFORCEABLE,
    NOT_CURRENTLY_ENFORCEABLE,
    INFORMATIONAL,
}
_CONNECTION_LIMITATIONS = {
    "unavailable_action",
    "unavailable_actor_kind",
    "unavailable_runtime_fact",
    "unavailable_enforcement_point",
    "unavailable_binding_type",
    "cross_repository_adapter_required",
    "pull_request_approval_not_supported",
}
_PUBLIC_LIMITATIONS = _CONNECTION_LIMITATIONS | {"other", None}


def inspect_policy_translation_customer_coverage(
    proposal: dict[str, Any],
    confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a transient customer-language coverage view for all six states."""
    validate_policy_translation_proposal(proposal)
    from governance_ledger.policy_translation import _empty_confirmation

    state = _validate_confirmation(proposal, confirmation or _empty_confirmation(proposal))
    decisions = {item["clause_id"]: item for item in state["clause_coverage_decisions"]}
    confirmed = {item["candidate_control_id"] for item in state["control_confirmations"]}
    resolved = {item["binding_id"] for item in state["binding_resolutions"]}
    clauses = []
    for clause in proposal["clauses"]:
        customer_state = _proposal_customer_state(
            clause,
            decision=decisions.get(clause["clause_id"]),
            confirmed_controls=confirmed,
            resolved_bindings=resolved,
        )
        clauses.append(
            {
                "clause_id": clause["clause_id"],
                "customer_coverage_state": customer_state,
            }
        )
    return {
        "view_type": "policy_translation_customer_coverage",
        "clauses": clauses,
        "coverage": _customer_coverage_totals(clauses, control_count=sum(
            len(item["candidate_controls"]) for item in proposal["clauses"]
        ), residual_count=sum(
            len(item["residual_unsupported_spans"]) for item in proposal["clauses"]
        )),
    }


def build_policy_translation_commitment(
    proposal: dict[str, Any],
    confirmation: dict[str, Any],
    approval: dict[str, Any],
) -> dict[str, Any]:
    """Build the public provider-free commitment reviewed for v3 publication."""
    validate_policy_translation_proposal(proposal)
    state = _validate_confirmation(proposal, confirmation)
    _validate_approval(proposal, state, approval)
    source = proposal["source_policy"]
    resolutions = {item["binding_id"]: item["value"] for item in state["binding_resolutions"]}
    confirmations = {
        item["candidate_control_id"]: item for item in state["control_confirmations"]
    }
    decisions = {item["clause_id"]: item for item in state["clause_coverage_decisions"]}
    pack = get_builtin_domain_pack(
        REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION
    )
    pack_controls = mapping_control_index(pack)
    clauses: list[dict[str, Any]] = []
    for clause in proposal["clauses"]:
        decision = decisions[clause["clause_id"]]
        controls = []
        for candidate in clause["candidate_controls"]:
            mapping_control_id, selections = _control_selections(candidate, resolutions)
            constraint = _finalize_constraint(
                _constraint_from_control(
                    pack_controls[mapping_control_id], selections, pack
                )
            )
            controls.append(
                {
                    "candidate_control": copy.deepcopy(candidate),
                    "resolved_value": (
                        candidate["value"]["canonical_value"]
                        if candidate["value"]["kind"] == "source_literal"
                        else resolutions[candidate["value"]["binding_id"]]
                    ),
                    "constraint_id": constraint["constraint_id"],
                    "human_confirmation": copy.deepcopy(
                        confirmations[candidate["candidate_control_id"]]
                    ),
                    "customer_explanation": _render_control(candidate, resolutions),
                }
            )
        residuals = [
            {
                **copy.deepcopy(residual),
                "acknowledgment": _residual_acknowledgment(
                    clause["clause_id"], residual["residual_id"], decision
                ),
            }
            for residual in clause["residual_unsupported_spans"]
        ]
        clauses.append(
            {
                "clause_id": clause["clause_id"],
                "index": clause["index"],
                "start_byte": clause["start_byte"],
                "end_byte": clause["end_byte"],
                "clause_bytes_base64": clause["clause_bytes_base64"],
                "clause_hash": clause["clause_hash"],
                "customer_coverage_state": _published_customer_state(
                    decision["coverage_status"]
                ),
                "limitation_code": clause["limitation_code"],
                "customer_explanation": _render_residual(clause),
                "controls": controls,
                "residuals": residuals,
                "human_coverage_decision": copy.deepcopy(decision),
            }
        )
    coverage_rows = [
        {
            "clause_id": item["clause_id"],
            "customer_coverage_state": item["customer_coverage_state"],
        }
        for item in clauses
    ]
    commitment: dict[str, Any] = {
        "schema_version": POLICY_TRANSLATION_COMMITMENT_V1,
        "source_policy_ref": source["source_policy_ref"],
        "source_snapshot_hash": source["snapshot_hash"],
        "authority_ref": proposal["authority"]["authority_ref"],
        "capability_catalog": copy.deepcopy(proposal["capability_catalog"]),
        "customer_bindings": copy.deepcopy(state["binding_resolutions"]),
        "clauses": clauses,
        "coverage": _customer_coverage_totals(
            coverage_rows,
            control_count=sum(len(item["controls"]) for item in clauses),
            residual_count=sum(len(item["residuals"]) for item in clauses),
        ),
    }
    commitment["commitment_hash"] = _commitment_hash(commitment)
    commitment["commitment_id"] = "policy-translation-commitment-" + commitment[
        "commitment_hash"
    ].removeprefix("sha256:")
    _validate_policy_translation_commitment(
        source, proposal["authority"], commitment, approval_time=approval["approved_at"]
    )
    return commitment


def validate_policy_translation_commitment(
    source_policy: dict[str, Any],
    authority: dict[str, Any],
    commitment: dict[str, Any],
    *,
    approved_at: str,
) -> dict[str, Any]:
    """Validate a standalone public commitment against its exact source and approval time."""
    constraints = _validate_policy_translation_commitment(
        source_policy,
        authority,
        commitment,
        approval_time=approved_at,
    )
    return {
        "artifact_schema_version": POLICY_TRANSLATION_COMMITMENT_V1,
        "valid": True,
        "confirmed_control_count": len(constraints),
        "coverage": copy.deepcopy(commitment["coverage"]),
    }


def finalize_policy_translation_authority_v3(
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
    """Publish confirmed multi-control and partial meaning as native v3 authority."""
    commitment = build_policy_translation_commitment(proposal, confirmation, approval)
    source = copy.deepcopy(proposal["source_policy"])
    authority_core = copy.deepcopy(proposal["authority"])
    pack = get_builtin_domain_pack(
        REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION
    )
    constraints = _validate_policy_translation_commitment(
        source,
        authority_core,
        commitment,
        approval_time=approval["approved_at"],
    )
    if not constraints:
        raise ValueError("normative publication requires at least one confirmed control")
    constraint_ir = _build_ir(constraints, pack)
    runtime_schema = copy.deepcopy(pack["runtime_fact_schema"])
    compatibility = validate_runtime_fact_compatibility(
        constraint_ir, runtime_schema, domain_pack=pack
    )
    if not compatibility["compatible"]:
        raise ValueError("policy translation is incompatible with available runtime facts")
    compiler_binding = _compiler_binding(pack, commitment)

    from governance_ledger.customer_policy import (
        _compiler_input,
        _normalized_semantic_meaning,
        _require_no_rule_conflicts,
        _validate_cross_artifact_rule_equivalence,
    )

    rules = [_lower_constraint(item) for item in constraints]
    _require_no_rule_conflicts(rules)
    compiler_input = _compiler_input(authority_core, rules)
    normalized = _normalized_semantic_meaning(authority_core, rules, compiler_input)
    normalized["policy_translation_commitment"] = {
        "commitment_id": commitment["commitment_id"],
        "commitment_hash": commitment["commitment_hash"],
        "coverage": copy.deepcopy(commitment["coverage"]),
        "compiler_binding_hash": compiler_binding["compiler_binding_hash"],
    }
    reconciliation = {
        "schema_version": "governance_semantic_reconciliation.v1",
        "source_id": source["source_policy_id"],
        "source_hash": source["snapshot_hash"],
        "extraction_id": commitment["commitment_id"],
        "operator_interpretation_decisions": [
            copy.deepcopy(item["human_coverage_decision"])
            for item in commitment["clauses"]
        ],
        "unresolved_ambiguities": [],
        "semantic_conflicts": [],
        "interpretation_completeness_posture": "complete",
        "final_normalized_semantic_meaning": normalized,
    }
    committed_at = _utc(committed_at, "committed_at")
    semantic = build_semantic_commit_bundle(
        reconciliation,
        committed_by=_nonempty(committed_by, "committed_by"),
        committed_at=committed_at,
    )
    compiled = _compile_domain_contract_v2(
        compiler_input,
        semantic,
        {
            "source_policy": source,
            "draft_hash": commitment["commitment_hash"],
            "interpretation_id": commitment["commitment_id"],
            "authority": authority_core,
        },
    )
    _validate_cross_artifact_rule_equivalence(
        confirmed_rules=rules,
        normalized_meaning=normalized,
        semantic_commit=semantic,
        compiler_input=compiler_input,
        compiled_contract=compiled,
    )
    approval_record = _publication_approval_record(
        commitment,
        constraint_ir,
        semantic,
        approved_by=approval["approved_by"],
        approved_at=approval["approved_at"],
    )
    published_at = _utc(published_at, "published_at")
    publication_id = _identity(publication_id, "publication_id")
    published_by = _nonempty(published_by, "published_by")
    _validate_chronology(commitment, approval_record, semantic, published_at)
    manifest = _publication_manifest(
        source, compiled, publication_id, published_by, published_at
    )
    authority = {
        **authority_core,
        "authority_identity_hash": canonical_sha256(authority_core),
    }
    provenance = _provenance_bindings(
        source,
        commitment,
        constraint_ir,
        runtime_schema,
        pack,
        compiler_binding,
        semantic,
        compiled,
        authority,
        approval_record,
        manifest,
    )
    bundle: dict[str, Any] = {
        "schema_version": AUTHORITY_BUNDLE_V3,
        "provenance_complete": True,
        "source_policy": source,
        "policy_translation_commitment": commitment,
        "constraint_ir": constraint_ir,
        "runtime_fact_schema": runtime_schema,
        "domain_pack": _pack_ref(pack),
        "compiler_binding": compiler_binding,
        "semantic_commit_bundle": semantic,
        "compiled_authority_contract": compiled,
        "authority": authority,
        "approval_record": approval_record,
        "publication_manifest": manifest,
        "provenance_bindings": provenance,
    }
    bundle["bundle_hash"] = artifact_hash(bundle, "bundle_hash")
    receipt = _publication_receipt(bundle, provenance, publication_id, published_by, published_at)
    bundle_validation = validate_authority_bundle_v3(bundle)
    receipt_validation = validate_publication_receipt_v3(bundle, receipt)
    return {
        "result_type": "policy_translation_publication",
        "status": {
            "constraint_ir_valid": True,
            "runtime_fact_compatible": True,
            "provenance_complete": True,
            "publication_ready": True,
        },
        "policy_translation_commitment": commitment,
        "constraint_ir_validation": validate_constraint_ir(constraint_ir, domain_pack=pack),
        "runtime_fact_compatibility": compatibility,
        "approval_record": approval_record,
        "semantic_commit_bundle": semantic,
        "canonical_compiler_input": compiler_input,
        "compiled_authority_contract": compiled,
        "governance_impact_preview": build_governance_impact_preview(compiled),
        "publication_manifest": manifest,
        "authority_bundle": bundle,
        "publication_receipt": receipt,
        "authority_bundle_validation": bundle_validation,
        "publication_receipt_validation": receipt_validation,
        "private_translation_evidence_required": False,
        "canonical_hashes": {
            "source_snapshot_hash": source["snapshot_hash"],
            "policy_translation_commitment_hash": commitment["commitment_hash"],
            "constraint_ir_hash": constraint_ir["ir_hash"],
            "runtime_fact_schema_hash": runtime_schema["schema_hash"],
            "domain_pack_hash": pack["canonical_hash"],
            "compiler_binding_hash": compiler_binding["compiler_binding_hash"],
            "semantic_commit_hash": semantic["semantic_commit_hash"],
            "semantic_commit_bundle_hash": semantic["bundle_hash"],
            "compiled_contract_hash": compiled["contract_hash"],
            "authority_bundle_hash": bundle["bundle_hash"],
            "publication_receipt_hash": receipt["receipt_hash"],
        },
    }


def validate_authority_bundle_v3(bundle: dict[str, Any]) -> dict[str, Any]:
    """Independently reconstruct every public v3 normative binding."""
    _exact(
        bundle,
        {
            "schema_version", "provenance_complete", "source_policy",
            "policy_translation_commitment", "constraint_ir", "runtime_fact_schema",
            "domain_pack", "compiler_binding", "semantic_commit_bundle",
            "compiled_authority_contract", "authority", "approval_record",
            "publication_manifest", "provenance_bindings", "bundle_hash",
        },
        AUTHORITY_BUNDLE_V3,
    )
    if bundle["schema_version"] != AUTHORITY_BUNDLE_V3 or bundle["provenance_complete"] is not True:
        raise ValueError("authority bundle must be provenance-complete authority_bundle.v3")
    if bundle["bundle_hash"] != artifact_hash(bundle, "bundle_hash"):
        raise ValueError("authority_bundle.v3 canonical hash is invalid")
    source = bundle["source_policy"]
    _exact(
        source,
        {
            "source_policy_id", "source_revision", "source_policy_ref",
            "content_encoding", "source_bytes_base64", "snapshot_hash",
        },
        "authority_bundle.v3 source policy",
    )
    if source["content_encoding"] != "base64" or source["source_policy_ref"] != (
        f"{source['source_policy_id']}@{source['source_revision']}"
    ):
        raise ValueError("authority_bundle.v3 source identity is invalid")
    exact = _decode_base64(source["source_bytes_base64"], "authority source bytes")
    if bytes_sha256(exact) != source["snapshot_hash"]:
        raise ValueError("authority_bundle.v3 source snapshot hash is invalid")
    authority = bundle["authority"]
    _exact(
        authority,
        {"authority_id", "authority_version", "authority_ref", "authority_identity_hash"},
        "authority_bundle.v3 authority",
    )
    authority_core = {
        key: authority[key] for key in ("authority_id", "authority_version", "authority_ref")
    }
    if authority["authority_identity_hash"] != canonical_sha256(authority_core):
        raise ValueError("authority_bundle.v3 authority identity hash is invalid")
    commitment = bundle["policy_translation_commitment"]
    constraints = _validate_policy_translation_commitment(
        source,
        authority_core,
        commitment,
        approval_time=bundle["approval_record"]["approved_at"],
    )
    if not constraints:
        raise ValueError("authority_bundle.v3 requires at least one confirmed control")
    pack = get_builtin_domain_pack(
        bundle["domain_pack"]["domain_pack_id"],
        bundle["domain_pack"]["domain_pack_version"],
    )
    if bundle["domain_pack"] != _pack_ref(pack):
        raise ValueError("authority_bundle.v3 domain-pack binding is invalid")
    expected_ir = _build_ir(constraints, pack)
    if bundle["constraint_ir"] != expected_ir:
        raise ValueError("authority_bundle.v3 Constraint IR is not the confirmed control lowering")
    if bundle["runtime_fact_schema"] != pack["runtime_fact_schema"]:
        raise ValueError("authority_bundle.v3 runtime schema is not pack-bound")
    compatibility = validate_runtime_fact_compatibility(
        expected_ir, bundle["runtime_fact_schema"], domain_pack=pack
    )
    if not compatibility["compatible"]:
        raise ValueError("authority_bundle.v3 runtime facts are incompatible")
    expected_compiler_binding = _compiler_binding(pack, commitment)
    if bundle["compiler_binding"] != expected_compiler_binding:
        raise ValueError("authority_bundle.v3 compiler identity binding is invalid")

    from governance_ledger.customer_policy import (
        _compiler_input,
        _normalized_semantic_meaning,
        _require_no_rule_conflicts,
        _validate_cross_artifact_rule_equivalence,
    )

    rules = [_lower_constraint(item) for item in constraints]
    _require_no_rule_conflicts(rules)
    compiler_input = _compiler_input(authority_core, rules)
    normalized = _normalized_semantic_meaning(authority_core, rules, compiler_input)
    normalized["policy_translation_commitment"] = {
        "commitment_id": commitment["commitment_id"],
        "commitment_hash": commitment["commitment_hash"],
        "coverage": copy.deepcopy(commitment["coverage"]),
        "compiler_binding_hash": expected_compiler_binding["compiler_binding_hash"],
    }
    semantic = bundle["semantic_commit_bundle"]
    reconciliation = {
        "schema_version": "governance_semantic_reconciliation.v1",
        "source_id": source["source_policy_id"],
        "source_hash": source["snapshot_hash"],
        "extraction_id": commitment["commitment_id"],
        "operator_interpretation_decisions": [
            copy.deepcopy(item["human_coverage_decision"])
            for item in commitment["clauses"]
        ],
        "unresolved_ambiguities": [],
        "semantic_conflicts": [],
        "interpretation_completeness_posture": "complete",
        "final_normalized_semantic_meaning": normalized,
    }
    expected_semantic = build_semantic_commit_bundle(
        reconciliation,
        committed_by=semantic["committed_by"],
        committed_at=semantic["committed_at"],
    )
    if semantic != expected_semantic:
        raise ValueError("authority_bundle.v3 semantic commitment is not deterministic")
    compiled = bundle["compiled_authority_contract"]
    _validate_compiled_authority_contract_v2(compiled)
    expected_compiled = _compile_domain_contract_v2(
        compiler_input,
        expected_semantic,
        {
            "source_policy": source,
            "draft_hash": commitment["commitment_hash"],
            "interpretation_id": commitment["commitment_id"],
            "authority": authority_core,
        },
    )
    _validate_cross_artifact_rule_equivalence(
        confirmed_rules=rules,
        normalized_meaning=normalized,
        semantic_commit=expected_semantic,
        compiler_input=compiler_input,
        compiled_contract=expected_compiled,
    )
    if compiled != expected_compiled:
        raise ValueError("authority_bundle.v3 compiled contract is not deterministic")
    expected_approval = _publication_approval_record(
        commitment,
        expected_ir,
        expected_semantic,
        approved_by=bundle["approval_record"]["approved_by"],
        approved_at=bundle["approval_record"]["approved_at"],
    )
    if bundle["approval_record"] != expected_approval:
        raise ValueError("authority_bundle.v3 approval binding is invalid")
    manifest = bundle["publication_manifest"]
    expected_manifest = _publication_manifest(
        source,
        compiled,
        manifest["publication_id"],
        manifest["published_by"],
        manifest["published_at"],
    )
    if manifest != expected_manifest:
        raise ValueError("authority_bundle.v3 publication manifest is invalid")
    _validate_chronology(commitment, expected_approval, expected_semantic, manifest["published_at"])
    expected_provenance = _provenance_bindings(
        source,
        commitment,
        expected_ir,
        bundle["runtime_fact_schema"],
        pack,
        expected_compiler_binding,
        expected_semantic,
        compiled,
        authority,
        expected_approval,
        manifest,
    )
    if bundle["provenance_bindings"] != expected_provenance:
        raise ValueError("authority_bundle.v3 provenance bindings are invalid")
    return {
        "schema_version": AUTHORITY_BUNDLE_V3,
        "profile": "policy_translation_provenance_complete_v1",
        "provenance_complete": True,
        "bundle_hash": bundle["bundle_hash"],
        "coverage": copy.deepcopy(commitment["coverage"]),
    }


def validate_publication_receipt_v3(
    bundle: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    """Validate a v3 receipt only against a fully reconstructed v3 bundle."""
    status = validate_authority_bundle_v3(bundle)
    expected = _publication_receipt(
        bundle,
        bundle["provenance_bindings"],
        bundle["publication_manifest"]["publication_id"],
        bundle["publication_manifest"]["published_by"],
        bundle["publication_manifest"]["published_at"],
    )
    if receipt != expected:
        raise ValueError("publication_receipt.v3 is inconsistent with authority_bundle.v3")
    return {
        **status,
        "schema_version": PUBLICATION_RECEIPT_V3,
        "receipt_hash": receipt["receipt_hash"],
    }


def _validate_policy_translation_commitment(
    source: dict[str, Any],
    authority: dict[str, Any],
    commitment: dict[str, Any],
    *,
    approval_time: str,
) -> list[dict[str, Any]]:
    _exact(
        source,
        {
            "source_policy_id", "source_revision", "source_policy_ref",
            "content_encoding", "source_bytes_base64", "snapshot_hash",
        },
        "policy translation commitment source",
    )
    _exact(
        authority,
        {"authority_id", "authority_version", "authority_ref"},
        "policy translation commitment authority",
    )
    if source["content_encoding"] != "base64" or source["source_policy_ref"] != (
        f"{source['source_policy_id']}@{source['source_revision']}"
    ):
        raise ValueError("policy translation commitment source identity is invalid")
    _exact(
        commitment,
        {
            "schema_version", "commitment_id", "commitment_hash", "source_policy_ref",
            "source_snapshot_hash", "authority_ref", "capability_catalog",
            "customer_bindings", "clauses", "coverage",
        },
        POLICY_TRANSLATION_COMMITMENT_V1,
    )
    if commitment["schema_version"] != POLICY_TRANSLATION_COMMITMENT_V1:
        raise ValueError("policy translation commitment schema is invalid")
    expected_hash = _commitment_hash(commitment)
    if commitment["commitment_hash"] != expected_hash or commitment["commitment_id"] != (
        "policy-translation-commitment-" + expected_hash.removeprefix("sha256:")
    ):
        raise ValueError("policy translation commitment identity is invalid")
    if commitment["source_policy_ref"] != source["source_policy_ref"] or commitment[
        "source_snapshot_hash"
    ] != source["snapshot_hash"]:
        raise ValueError("policy translation commitment is substituted across source")
    if commitment["authority_ref"] != authority["authority_ref"]:
        raise ValueError("policy translation commitment is substituted across authority")
    catalog = resolve_policy_translation_capability_catalog(commitment["capability_catalog"])
    exact = _decode_base64(source["source_bytes_base64"], "commitment source bytes")
    if bytes_sha256(exact) != source["snapshot_hash"]:
        raise ValueError("policy translation commitment source snapshot hash is invalid")
    draft = interpret_policy_with_domain_pack(
        exact,
        domain_pack_id=REPOSITORY_CHANGES_PACK_ID,
        domain_pack_version=REPOSITORY_CHANGES_PACK_VERSION,
        source_policy_id=source["source_policy_id"],
        source_revision=source["source_revision"],
        authority_id=authority["authority_id"],
        authority_version=authority["authority_version"],
    )
    bindings: dict[str, dict[str, Any]] = {}
    resolutions: dict[str, str] = {}
    for resolution in commitment["customer_bindings"]:
        _exact(
            resolution,
            {"binding_id", "binding_type", "value", "confirmed_by", "confirmed_at", "resolution_hash"},
            "customer binding",
        )
        if resolution["binding_id"] in bindings:
            raise ValueError("policy translation commitment duplicates a customer binding")
        if resolution["binding_type"] not in catalog["binding_types"]:
            raise ValueError("policy translation commitment uses an unavailable binding type")
        _validate_binding_value(resolution["binding_type"], resolution["value"])
        if resolution["resolution_hash"] != artifact_hash(resolution, "resolution_hash"):
            raise ValueError("policy translation commitment customer binding hash is invalid")
        _not_after(resolution["confirmed_at"], approval_time, "customer binding")
        bindings[resolution["binding_id"]] = {
            "binding_id": resolution["binding_id"],
            "binding_type": resolution["binding_type"],
            "symbol": "public-binding",
            "question": "public-binding",
            "status": "unresolved",
        }
        resolutions[resolution["binding_id"]] = resolution["value"]
    clauses = commitment["clauses"]
    statements = draft["source_statements"]
    if not isinstance(clauses, list) or len(clauses) != len(statements):
        raise ValueError("policy translation commitment omits or duplicates source clauses")
    constraints: list[dict[str, Any]] = []
    used_bindings: set[str] = set()
    coverage_rows = []
    residual_count = 0
    pack = get_builtin_domain_pack(
        REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION
    )
    pack_controls = mapping_control_index(pack)
    for index, (clause, statement) in enumerate(zip(clauses, statements)):
        _exact(
            clause,
            {
                "clause_id", "index", "start_byte", "end_byte", "clause_bytes_base64",
                "clause_hash", "customer_coverage_state", "controls", "residuals",
                "human_coverage_decision", "limitation_code", "customer_explanation",
            },
            f"commitment clause {index}",
        )
        if clause["index"] != index or clause["start_byte"] != statement["start_byte"] or clause[
            "end_byte"
        ] != statement["end_byte"]:
            raise ValueError("policy translation commitment source clauses are reordered or malformed")
        piece = exact[clause["start_byte"] : clause["end_byte"]]
        if (
            _decode_base64(clause["clause_bytes_base64"], "commitment clause bytes") != piece
            or clause["clause_hash"] != bytes_sha256(piece)
            or clause["clause_id"] != _expected_clause_id(source, clause)
        ):
            raise ValueError("policy translation commitment clause source binding is invalid")
        decision = clause["human_coverage_decision"]
        _exact(
            decision,
            {
                "clause_id", "coverage_status", "reason_code", "human_reason",
                "acknowledged_unrepresented", "confirmed_by", "confirmed_at",
                "decision_hash",
            },
            "published clause coverage decision",
        )
        if decision["clause_id"] != clause["clause_id"] or decision["decision_hash"] != artifact_hash(
            decision, "decision_hash"
        ):
            raise ValueError("policy translation commitment clause decision is invalid")
        _not_after(decision["confirmed_at"], approval_time, "clause coverage decision")
        _validate_public_coverage_decision(decision)
        expected_state = _published_customer_state(decision["coverage_status"])
        if clause["customer_coverage_state"] != expected_state:
            raise ValueError("claimed customer coverage disagrees with the clause decision")
        expected_explanation = _render_residual(
            {
                "coverage_status": decision["coverage_status"],
                "residual_unsupported_spans": clause["residuals"],
                "limitation_code": clause["limitation_code"],
            }
        )
        if clause["customer_explanation"] != expected_explanation:
            raise ValueError("published clause explanation is not deterministic")
        controls = clause["controls"]
        residuals = clause["residuals"]
        if not isinstance(controls, list) or not isinstance(residuals, list):
            raise ValueError("commitment controls and residuals must be ordered arrays")
        if clause["limitation_code"] not in _PUBLIC_LIMITATIONS:
            raise ValueError("published clause limitation is invalid")
        if decision["coverage_status"] == "fully_represented" and (
            not controls or residuals or clause["limitation_code"] is not None
        ):
            raise ValueError("ready-to-enforce coverage disagrees with published controls")
        if decision["coverage_status"] == "partially_represented" and (
            not controls or not residuals or clause["limitation_code"] is None
        ):
            raise ValueError("partial coverage requires controls and acknowledged residuals")
        if decision["coverage_status"] == "entirely_unsupported" and (
            controls or not residuals or clause["limitation_code"] is None
        ):
            raise ValueError("unenforceable coverage disagrees with published controls")
        if decision["coverage_status"] == "informational" and (
            controls or residuals or clause["limitation_code"] is not None
        ):
            raise ValueError("informational coverage cannot publish controls or residuals")
        candidate_clause = {
            "clause_hash": clause["clause_hash"],
            "start_byte": clause["start_byte"],
            "end_byte": clause["end_byte"],
        }
        raw_residuals = []
        clause_constraints = []
        for control_record in controls:
            _exact(
                control_record,
                {
                    "candidate_control", "resolved_value", "constraint_id",
                    "human_confirmation", "customer_explanation",
                },
                "published control",
            )
            candidate = control_record["candidate_control"]
            referenced = _validate_candidate_control(
                candidate,
                exact_source=exact,
                clause_start=clause["start_byte"],
                clause_end=clause["end_byte"],
                bindings=bindings,
                catalog=catalog,
            )
            used_bindings.update(referenced)
            resolved_value = (
                candidate["value"]["canonical_value"]
                if candidate["value"]["kind"] == "source_literal"
                else resolutions[candidate["value"]["binding_id"]]
            )
            if control_record["resolved_value"] != resolved_value:
                raise ValueError("published control resolved value is invalid")
            confirmation = control_record["human_confirmation"]
            _exact(
                confirmation,
                {
                    "clause_id", "candidate_control_id", "confirmed_by",
                    "confirmed_at", "confirmation_hash",
                },
                "published control confirmation",
            )
            if confirmation["clause_id"] != clause["clause_id"] or confirmation[
                "candidate_control_id"
            ] != candidate["candidate_control_id"] or confirmation[
                "confirmation_hash"
            ] != artifact_hash(confirmation, "confirmation_hash"):
                raise ValueError("every published control requires its own valid confirmation")
            _not_after(confirmation["confirmed_at"], approval_time, "control confirmation")
            if control_record["customer_explanation"] != _render_control(candidate, resolutions):
                raise ValueError("published customer explanation is not deterministic")
            mapping_control_id, selections = _control_selections(candidate, resolutions)
            constraint = _finalize_constraint(
                _constraint_from_control(pack_controls[mapping_control_id], selections, pack)
            )
            if control_record["constraint_id"] != constraint["constraint_id"]:
                raise ValueError("published control constraint binding is invalid")
            clause_constraints.append(constraint)
        from governance_ledger.customer_policy import _require_no_rule_conflicts

        _require_no_rule_conflicts([_lower_constraint(item) for item in clause_constraints])
        constraints.extend(clause_constraints)
        for residual in residuals:
            _exact(
                residual,
                {
                    "residual_id", "index", "start_byte", "end_byte",
                    "residual_bytes_base64", "residual_hash", "acknowledgment",
                },
                "published residual",
            )
            raw = {key: residual[key] for key in (
                "residual_id", "index", "start_byte", "end_byte",
                "residual_bytes_base64", "residual_hash",
            )}
            raw_residuals.append(raw)
            acknowledgment = residual["acknowledgment"]
            _exact(
                acknowledgment,
                {
                    "clause_id", "residual_id", "acknowledged_by",
                    "acknowledged_at", "clause_decision_hash",
                    "acknowledgment_hash", "acknowledgment_id",
                },
                "published residual acknowledgment",
            )
            expected_ack = _residual_acknowledgment(
                clause["clause_id"], residual["residual_id"], decision
            )
            if acknowledgment != expected_ack:
                raise ValueError("every residual requires explicit human acknowledgment")
            _not_after(acknowledgment["acknowledged_at"], approval_time, "residual acknowledgment")
        _validate_residual_spans(raw_residuals, clause=candidate_clause, exact_source=exact)
        residual_count += len(residuals)
        if statement["classification"] == "direct":
            actual = [
                _control_public_semantics(item["candidate_control"], commitment["customer_bindings"])
                for item in controls
            ]
            if decision["coverage_status"] != "fully_represented" or actual != _direct_statement_semantics(
                draft, statement["statement_id"]
            ):
                raise ValueError("deterministically recognized meaning cannot be omitted or downgraded")
        coverage_rows.append(
            {
                "clause_id": clause["clause_id"],
                "customer_coverage_state": clause["customer_coverage_state"],
            }
        )
    if used_bindings != set(bindings):
        raise ValueError("published customer bindings are missing, unused, or substituted")
    from governance_ledger.customer_policy import _require_no_rule_conflicts

    _require_no_rule_conflicts([_lower_constraint(item) for item in constraints])
    expected_coverage = _customer_coverage_totals(
        coverage_rows,
        control_count=sum(len(item["controls"]) for item in clauses),
        residual_count=residual_count,
    )
    if commitment["coverage"] != expected_coverage or expected_coverage["waiting_clause_count"]:
        raise ValueError("published coverage totals are invalid or unresolved")
    return constraints


def _publication_approval_record(
    commitment: dict[str, Any],
    constraint_ir: dict[str, Any],
    semantic: dict[str, Any],
    *,
    approved_by: str,
    approved_at: str,
) -> dict[str, Any]:
    record = {
        "approved_by": _nonempty(approved_by, "approved_by"),
        "approved_at": _utc(approved_at, "approved_at"),
        "approved_policy_translation_commitment_hash": commitment["commitment_hash"],
        "approved_constraint_ir_hash": constraint_ir["ir_hash"],
        "approved_semantic_commit_hash": semantic["semantic_commit_hash"],
    }
    record["approval_record_hash"] = artifact_hash(record, "approval_record_hash")
    record["approval_id"] = "publication-approval-v3-" + record[
        "approval_record_hash"
    ].removeprefix("sha256:")
    return record


def _compiler_binding(pack: dict[str, Any], commitment: dict[str, Any]) -> dict[str, Any]:
    control_index = {
        item["control_type"]: item for item in commitment_catalog_controls(commitment)
    }
    pack_index = mapping_control_index(pack)
    used = []
    for clause in commitment["clauses"]:
        for record in clause["controls"]:
            candidate = record["candidate_control"]
            mapping_id = control_index[candidate["control_type"]]["mapping_control_id"]
            used.append(
                {
                    "mapping_control_id": mapping_id,
                    "emitter_id": pack_index[mapping_id]["emitter_id"],
                }
            )
    unique_used = sorted(
        {canonical_sha256(item): item for item in used}.values(),
        key=lambda item: item["mapping_control_id"],
    )
    result = {
        "constraint_ir_schema_version": "constraint_ir.v1",
        "domain_pack": _pack_ref(pack),
        "grammar_compiler": copy.deepcopy(pack["grammar_compiler"]),
        "compiler_lowering": copy.deepcopy(pack["compiler_lowering"]),
        "control_emitters": unique_used,
        "compiled_contract_schema_version": "compiled_authority_contract.v2",
    }
    result["compiler_binding_hash"] = artifact_hash(result, "compiler_binding_hash")
    return result


def commitment_catalog_controls(commitment: dict[str, Any]) -> list[dict[str, Any]]:
    return resolve_policy_translation_capability_catalog(
        commitment["capability_catalog"]
    )["control_types"]


def _provenance_bindings(
    source: dict[str, Any],
    commitment: dict[str, Any],
    constraint_ir: dict[str, Any],
    runtime_schema: dict[str, Any],
    pack: dict[str, Any],
    compiler_binding: dict[str, Any],
    semantic: dict[str, Any],
    compiled: dict[str, Any],
    authority: dict[str, Any],
    approval: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    controls = [control for clause in commitment["clauses"] for control in clause["controls"]]
    residuals = [residual for clause in commitment["clauses"] for residual in clause["residuals"]]
    return {
        "source_snapshot_hash": source["snapshot_hash"],
        "source_clauses_hash": canonical_sha256([
            {key: clause[key] for key in (
                "clause_id", "index", "start_byte", "end_byte",
                "clause_bytes_base64", "clause_hash",
            )}
            for clause in commitment["clauses"]
        ]),
        "policy_translation_commitment_hash": commitment["commitment_hash"],
        "confirmed_controls_hash": canonical_sha256(controls),
        "acknowledged_residuals_hash": canonical_sha256(residuals),
        "customer_bindings_hash": canonical_sha256(commitment["customer_bindings"]),
        "coverage_hash": canonical_sha256(commitment["coverage"]),
        "capability_catalog_hash": commitment["capability_catalog"]["catalog_hash"],
        "constraint_ir_hash": constraint_ir["ir_hash"],
        "runtime_fact_schema_hash": runtime_schema["schema_hash"],
        "domain_pack_hash": pack["canonical_hash"],
        "compiler_binding_hash": compiler_binding["compiler_binding_hash"],
        "semantic_commit_id": semantic["semantic_commit_id"],
        "semantic_commit_hash": semantic["semantic_commit_hash"],
        "semantic_commit_bundle_hash": semantic["bundle_hash"],
        "compiled_contract_hash": compiled["contract_hash"],
        "authority_identity_hash": authority["authority_identity_hash"],
        "approval_record_hash": approval["approval_record_hash"],
        "publication_manifest_hash": canonical_sha256(manifest),
    }


def _publication_manifest(
    source: dict[str, Any],
    compiled: dict[str, Any],
    publication_id: str,
    published_by: str,
    published_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "publication_manifest.v1",
        "publication_id": publication_id,
        "published_at": published_at,
        "published_by": published_by,
        "contracts": [
            {
                "contract_id": compiled["contract_id"],
                "contract_version": compiled["contract_version"],
                "contract_hash": compiled["contract_hash"],
                "source_hash": source["snapshot_hash"],
                "path": f"contracts/{compiled['contract_id']}-{compiled['contract_version']}.contract.json",
            }
        ],
        "reviews": [{"path": f"reviews/{source['source_policy_id']}.policy-translation.json"}],
        "snapshots": [{"path": f"snapshots/{source['source_policy_id']}.source.json"}],
    }


def _commitment_hash(commitment: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            key: value
            for key, value in commitment.items()
            if key not in {"commitment_id", "commitment_hash"}
        }
    )


def _publication_receipt(
    bundle: dict[str, Any],
    provenance: dict[str, Any],
    publication_id: str,
    published_by: str,
    published_at: str,
) -> dict[str, Any]:
    compiled = bundle["compiled_authority_contract"]
    receipt: dict[str, Any] = {
        "schema_version": PUBLICATION_RECEIPT_V3,
        "receipt_id": "receipt-v3-" + bundle["bundle_hash"].removeprefix("sha256:"),
        "publication_id": publication_id,
        "authority_ref": bundle["authority"]["authority_ref"],
        "published_at": published_at,
        "published_by": published_by,
        "bundle_hash": bundle["bundle_hash"],
        **copy.deepcopy(provenance),
        "domain_pack": copy.deepcopy(bundle["domain_pack"]),
        "compiled_contract_ref": f"{compiled['contract_id']}@{compiled['contract_version']}",
        "provenance_complete": True,
    }
    receipt["receipt_hash"] = artifact_hash(receipt, "receipt_hash")
    return receipt


def _residual_acknowledgment(
    clause_id: str, residual_id: str, decision: dict[str, Any]
) -> dict[str, Any]:
    if not decision["acknowledged_unrepresented"]:
        raise ValueError("every residual requires explicit human acknowledgment")
    result = {
        "clause_id": clause_id,
        "residual_id": residual_id,
        "acknowledged_by": decision["confirmed_by"],
        "acknowledged_at": decision["confirmed_at"],
        "clause_decision_hash": decision["decision_hash"],
    }
    result["acknowledgment_hash"] = artifact_hash(result, "acknowledgment_hash")
    result["acknowledgment_id"] = "residual-acknowledgment-" + result[
        "acknowledgment_hash"
    ].removeprefix("sha256:")
    return result


def _proposal_customer_state(
    clause: dict[str, Any],
    *,
    decision: dict[str, Any] | None,
    confirmed_controls: set[str],
    resolved_bindings: set[str],
) -> str:
    if decision is not None:
        return _published_customer_state(decision["coverage_status"])
    if clause["limitation_code"] in _CONNECTION_LIMITATIONS:
        return NEEDS_A_CONNECTION
    if set(clause["unresolved_binding_ids"]) - resolved_bindings or any(
        item["candidate_control_id"] not in confirmed_controls
        for item in clause["candidate_controls"]
    ):
        return NEEDS_AN_ANSWER
    return _published_customer_state(clause["coverage_status"])


def _published_customer_state(status: str) -> str:
    states = {
        "fully_represented": READY_TO_ENFORCE,
        "partially_represented": PARTIALLY_ENFORCEABLE,
        "entirely_unsupported": NOT_CURRENTLY_ENFORCEABLE,
        "informational": INFORMATIONAL,
    }
    try:
        return states[status]
    except KeyError as exc:
        raise ValueError("coverage status has no deterministic customer rendering") from exc


def _validate_public_coverage_decision(decision: dict[str, Any]) -> None:
    status = decision["coverage_status"]
    reason = decision["reason_code"]
    human_reason = decision["human_reason"]
    acknowledged = decision["acknowledged_unrepresented"]
    if status == "fully_represented":
        valid = reason == "human-confirmed-complete" and human_reason is None and not acknowledged
    elif status == "partially_represented":
        valid = reason == "human-confirmed-partial" and acknowledged
    elif status == "entirely_unsupported":
        valid = reason in {"outside-domain", "not-enforceable", "deferred", "other"} and acknowledged
    elif status == "informational":
        valid = reason in {"context-only", "descriptive", "non-policy", "other"} and not acknowledged
    else:
        valid = False
    if reason == "other" and not (isinstance(human_reason, str) and human_reason.strip()):
        valid = False
    if not valid:
        raise ValueError("published clause coverage decision is semantically inconsistent")


def _customer_coverage_totals(
    clauses: list[dict[str, Any]], *, control_count: int, residual_count: int
) -> dict[str, Any]:
    counts = {state: 0 for state in _CUSTOMER_STATES}
    for clause in clauses:
        state = clause["customer_coverage_state"]
        if state not in counts:
            raise ValueError("customer coverage state is invalid")
        counts[state] += 1
    return {
        "total_clause_count": len(clauses),
        "full_clause_count": counts[READY_TO_ENFORCE],
        "partial_clause_count": counts[PARTIALLY_ENFORCEABLE],
        "waiting_clause_count": counts[NEEDS_AN_ANSWER] + counts[NEEDS_A_CONNECTION],
        "needs_answer_clause_count": counts[NEEDS_AN_ANSWER],
        "needs_connection_clause_count": counts[NEEDS_A_CONNECTION],
        "unenforced_clause_count": counts[NOT_CURRENTLY_ENFORCEABLE],
        "informational_clause_count": counts[INFORMATIONAL],
        "confirmed_control_count": control_count,
        "acknowledged_residual_count": residual_count,
    }


def _control_public_semantics(
    control: dict[str, Any], bindings: list[dict[str, Any]]
) -> dict[str, Any]:
    resolutions = {item["binding_id"]: item["value"] for item in bindings}
    from governance_ledger.policy_translation import _control_semantics

    return _control_semantics(control, resolutions)


def _expected_clause_id(source: dict[str, Any], clause: dict[str, Any]) -> str:
    core = {
        "source_snapshot_hash": source["snapshot_hash"],
        "source_policy_ref": source["source_policy_ref"],
        "index": clause["index"],
        "start_byte": clause["start_byte"],
        "end_byte": clause["end_byte"],
        "clause_hash": clause["clause_hash"],
    }
    return "policy-clause-" + canonical_sha256(core).removeprefix("sha256:")


def _validate_chronology(
    commitment: dict[str, Any],
    approval: dict[str, Any],
    semantic: dict[str, Any],
    published_at: str,
) -> None:
    approved = _utc_datetime(approval["approved_at"], "approved_at")
    committed = _utc_datetime(semantic["committed_at"], "committed_at")
    published = _utc_datetime(published_at, "published_at")
    if approved > committed:
        raise ValueError("approved_at must be no later than committed_at")
    if committed > published:
        raise ValueError("committed_at must be no later than published_at")
    for binding in commitment["customer_bindings"]:
        _not_after(binding["confirmed_at"], approval["approved_at"], "customer binding")
    for clause in commitment["clauses"]:
        _not_after(
            clause["human_coverage_decision"]["confirmed_at"],
            approval["approved_at"],
            "clause decision",
        )
        for control in clause["controls"]:
            _not_after(
                control["human_confirmation"]["confirmed_at"],
                approval["approved_at"],
                "control confirmation",
            )
        for residual in clause["residuals"]:
            _not_after(
                residual["acknowledgment"]["acknowledged_at"],
                approval["approved_at"],
                "residual acknowledgment",
            )


def _not_after(value: str, boundary: str, label: str) -> None:
    if _utc_datetime(value, f"{label} time") > _utc_datetime(boundary, "approval time"):
        raise ValueError(f"{label} must occur no later than approval")


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _identity(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    if "@" in value or len(value) > 256:
        raise ValueError(f"{label} is invalid")
    return value


def _exact(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields are invalid")
