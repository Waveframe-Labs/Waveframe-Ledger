"""Filesystem-free deterministic domain-pack policy compilation."""

from __future__ import annotations

import base64
import copy
import re
from datetime import datetime
from typing import Any

from governance_ledger.authority_contract import compute_contract_hash
from governance_ledger.constraint_ir import (
    artifact_hash,
    finalize_constraint_ir,
    validate_constraint_ir,
    validate_format_value,
    validate_runtime_fact_compatibility,
)
from governance_ledger.domain_packs import (
    ACTING_ROLE_EMITTER_ID,
    EXACT_PATH_EMITTER_ID,
    PREFIX_PATH_EMITTER_ID,
    REPOSITORY_CHANGES_PACK_ID,
    REPOSITORY_CHANGES_PACK_VERSION,
    REPOSITORY_PATH_FORMAT_ID,
    get_builtin_domain_pack,
    mapping_control_index,
)
from governance_ledger.publication_provenance import bytes_sha256, canonical_sha256
from governance_ledger.semantics.compiler import build_semantic_commit_bundle
from governance_ledger.semantics.preview import build_governance_impact_preview

DOMAIN_POLICY_INTERPRETATION_V1 = "domain_policy_interpretation.v1"
POLICY_MAPPING_DECISION_V1 = "policy_mapping_decision.v1"
POLICY_MAPPING_APPLICATION_V1 = "policy_mapping_application.v1"
DOMAIN_POLICY_FINALIZATION_V1 = "domain_policy_finalization.v1"
AUTHORITY_BUNDLE_V2 = "authority_bundle.v2"
PUBLICATION_RECEIPT_V2 = "publication_receipt.v2"
COMPILED_AUTHORITY_CONTRACT_V2 = "compiled_authority_contract.v2"

_CANONICAL_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_DECIMAL = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d*[1-9])?\Z")
_INFORMATIONAL_REASONS = {"context-only", "descriptive", "non-policy", "other"}
_UNSUPPORTED_REASONS = {"outside-domain", "not-enforceable", "deferred", "other"}
_MULTI_EXACT_ALLOW = re.compile(
    r"Agents may modify ([^\s]+) and ([^\s]+)\.\Z"
)


def interpret_policy_with_domain_pack(
    source_bytes: bytes,
    *,
    domain_pack_id: str,
    domain_pack_version: str,
    source_policy_id: str,
    source_revision: str,
    authority_id: str,
    authority_version: str,
) -> dict[str, Any]:
    """Directly parse matching clauses and leave every unmatched clause pending."""
    pack = get_builtin_domain_pack(domain_pack_id, domain_pack_version)
    if (domain_pack_id, domain_pack_version) != (
        REPOSITORY_CHANGES_PACK_ID,
        REPOSITORY_CHANGES_PACK_VERSION,
    ):
        raise ValueError("the selected pack has no installed deterministic grammar")
    from governance_ledger.customer_policy import _interpret_customer_policy_v0_6_compatibility

    legacy = _interpret_customer_policy_v0_6_compatibility(
        source_bytes,
        source_policy_id=source_policy_id,
        source_revision=source_revision,
        authority_id=authority_id,
        authority_version=authority_version,
    )
    exact = base64.b64decode(legacy["source_policy"]["source_bytes_base64"].encode("ascii"))
    rules = {item["rule_id"]: item for item in legacy["proposed_rules"]}
    control_ids = [item["control_id"] for item in pack["allowed_mapping_controls"]]
    constraints: list[dict[str, Any]] = []
    statements: list[dict[str, Any]] = []
    direct_parses: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    previews: list[dict[str, Any]] = []
    for source_statement in legacy["source_statements"]:
        direct_constraints: list[dict[str, Any]] = []
        if source_statement["classification"] == "enforced":
            try:
                direct_constraints = [
                    _finalize_constraint(_constraint_from_legacy_rule(rules[rule_id], pack))
                    for rule_id in source_statement["proposed_rule_ids"]
                ]
            except ValueError:
                direct_constraints = []
        if not direct_constraints:
            statement_text = exact[
                source_statement["start_byte"] : source_statement["end_byte"]
            ].decode("utf-8").strip()
            multi_match = _MULTI_EXACT_ALLOW.fullmatch(statement_text)
            if multi_match:
                try:
                    values = list(multi_match.groups())
                    for value in values:
                        validate_format_value(
                            REPOSITORY_PATH_FORMAT_ID,
                            value,
                            match_mode="exact",
                            label="repository exact path",
                        )
                    direct_constraints = [
                        _finalize_constraint(
                            _constraint(
                                action="modify",
                                resource={
                                    "kind": "repository_path",
                                    "match": "exact",
                                    "value": value,
                                },
                                effect="allow",
                            )
                        )
                        for value in values
                    ]
                except ValueError:
                    direct_constraints = []
        statement = {
            "statement_id": source_statement["statement_id"],
            "start_byte": source_statement["start_byte"],
            "end_byte": source_statement["end_byte"],
            "statement_bytes_base64": source_statement["statement_bytes_base64"],
            "statement_hash": source_statement["statement_hash"],
            "classification": "direct" if direct_constraints else "pending",
            "available_mapping_control_ids": [] if direct_constraints else control_ids,
            "decision_hash": None,
        }
        # Every partition returned by the compatibility grammar is preserved,
        # including exact whitespace bytes; no unmatched text is inferred.
        if not exact[statement["start_byte"] : statement["end_byte"]]:
            raise ValueError("source statement spans must be non-empty")
        statements.append(statement)
        if direct_constraints:
            constraint_ids = [item["constraint_id"] for item in direct_constraints]
            constraints.extend(direct_constraints)
            direct_parses.append(_direct_parse(statement, constraint_ids, pack))
            mappings.append(_source_mapping(statement, constraint_ids, "direct", None))
            previews.extend(
                {"constraint_id": item["constraint_id"], "preview": _cnl_preview(item)}
                for item in direct_constraints
            )
    ir = _build_ir(constraints, pack) if constraints else None
    draft: dict[str, Any] = {
        "schema_version": DOMAIN_POLICY_INTERPRETATION_V1,
        "source_policy": copy.deepcopy(legacy["source_policy"]),
        "authority": copy.deepcopy(legacy["authority"]),
        "domain_pack": _pack_ref(pack),
        "runtime_fact_schema": copy.deepcopy(pack["runtime_fact_schema"]),
        "source_statements": statements,
        "direct_parses": direct_parses,
        "statement_decisions": [],
        "constraint_ir": ir,
        "canonical_cnl_previews": previews,
        "source_to_constraint_mappings": mappings,
        "status": _draft_status(statements, constraints),
    }
    draft["interpretation_id"] = "domain-interpretation-" + canonical_sha256(draft).removeprefix("sha256:")
    draft["draft_hash"] = artifact_hash(draft, "draft_hash")
    return draft


def inspect_policy_mapping_controls(
    interpretation_draft: dict[str, Any], statement_id: str
) -> dict[str, Any]:
    """Return pack enforcement controls plus fixed non-enforcement dispositions."""
    draft = _reconstruct_domain_draft(interpretation_draft)
    statement = _statement(draft, statement_id)
    if statement["classification"] != "pending":
        raise ValueError("statement decisions are available only for a pending statement")
    pack = _pack_for_draft(draft)
    controls = mapping_control_index(pack)
    return {
        "domain_pack": copy.deepcopy(draft["domain_pack"]),
        "statement": copy.deepcopy(statement),
        "enforcement_controls": [
            controls[item] for item in statement["available_mapping_control_ids"]
        ],
        "disposition_options": [
            {"disposition": "informational", "reason_codes": sorted(_INFORMATIONAL_REASONS)},
            {"disposition": "unsupported", "reason_codes": sorted(_UNSUPPORTED_REASONS)},
        ],
    }


def apply_policy_mapping_decision(
    interpretation_draft: dict[str, Any],
    *,
    statement_id: str,
    disposition: str,
    mapper_identity: str,
    mapped_at: str,
    control_id: str | None = None,
    selections: dict[str, Any] | None = None,
    reason_code: str | None = None,
    human_reason: str | None = None,
) -> dict[str, Any]:
    """Apply one explicit enforced, informational, or unsupported decision."""
    draft = _reconstruct_domain_draft(interpretation_draft)
    statement = _statement(draft, statement_id)
    if statement["classification"] != "pending":
        raise ValueError("the selected statement is not pending")
    pack = _pack_for_draft(draft)
    constraint: dict[str, Any] | None = None
    control: dict[str, Any] | None = None
    validated_selections: dict[str, Any] | None = None
    if disposition == "enforced":
        if reason_code not in {None, "human-mapped"} or human_reason is not None:
            raise ValueError("enforced decisions use only the canonical human-mapped reason")
        if not isinstance(control_id, str) or selections is None:
            raise ValueError("enforced decisions require one pack control and its selections")
        controls = mapping_control_index(pack)
        if control_id not in statement["available_mapping_control_ids"] or control_id not in controls:
            raise ValueError("the selected enforcement control is unavailable")
        control = controls[control_id]
        validated_selections = _validate_selections(control, selections)
        constraint = _finalize_constraint(
            _constraint_from_control(control, validated_selections, pack)
        )
        reason_code = "human-mapped"
    elif disposition in {"informational", "unsupported"}:
        if control_id is not None or selections is not None:
            raise ValueError("non-enforced dispositions cannot select an enforcement control")
        allowed = _INFORMATIONAL_REASONS if disposition == "informational" else _UNSUPPORTED_REASONS
        if reason_code not in allowed:
            raise ValueError(f"{disposition} decision requires a bounded reason_code")
        if reason_code == "other" and (not isinstance(human_reason, str) or not human_reason.strip()):
            raise ValueError("reason_code other requires a human_reason")
        if human_reason is not None and (not isinstance(human_reason, str) or not human_reason.strip() or len(human_reason) > 1024):
            raise ValueError("human_reason must be null or 1 to 1024 non-whitespace characters")
    else:
        raise ValueError("disposition must be enforced, informational, or unsupported")
    decision = _statement_decision(
        draft,
        statement,
        disposition=disposition,
        mapper_identity=mapper_identity,
        mapped_at=mapped_at,
        reason_code=reason_code,
        human_reason=human_reason,
        control=control,
        selections=validated_selections,
        constraint=constraint,
    )
    updated = _apply_canonical_decision(draft, decision, reconstructing=False)
    mapping = next(
        (
            item
            for item in updated["source_to_constraint_mappings"]
            if item["statement_id"] == statement_id
        ),
        None,
    )
    preview = _cnl_preview(constraint) if constraint else None
    validation = None
    compatibility = None
    if updated["constraint_ir"] is not None:
        validation = validate_constraint_ir(updated["constraint_ir"], domain_pack=pack)
        compatibility = validate_runtime_fact_compatibility(
            updated["constraint_ir"], updated["runtime_fact_schema"], domain_pack=pack
        )
    return {
        "schema_version": POLICY_MAPPING_APPLICATION_V1,
        "statement_decision": copy.deepcopy(decision),
        "canonical_cnl_preview": preview,
        "constraint_ir": copy.deepcopy(updated["constraint_ir"]),
        "source_to_constraint_mapping": copy.deepcopy(mapping),
        "validation_result": {
            "constraint_ir": validation,
            "runtime_fact_compatibility": compatibility,
        },
        "updated_interpretation": updated,
    }


def finalize_domain_policy_authority(
    interpretation_draft: dict[str, Any],
    *,
    approval_id: str,
    approved_by: str,
    approved_at: str,
    committed_by: str,
    committed_at: str,
    publication_id: str,
    published_by: str,
    published_at: str,
    runtime_fact_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lower a complete domain interpretation and emit authority_bundle.v2."""
    draft = _reconstruct_domain_draft(interpretation_draft)
    if not draft["status"]["ready_for_finalization"]:
        raise ValueError("every nonempty statement requires a direct parse or explicit human decision")
    pack = _pack_for_draft(draft)
    constraint_ir = draft["constraint_ir"]
    ir_validation = validate_constraint_ir(constraint_ir, domain_pack=pack)
    selected_runtime = copy.deepcopy(runtime_fact_schema or draft["runtime_fact_schema"])
    compatibility = validate_runtime_fact_compatibility(
        constraint_ir, selected_runtime, domain_pack=pack
    )
    if not compatibility["compatible"]:
        raise ValueError(
            "domain policy is not publication-ready: "
            + "; ".join(item["message"] for item in compatibility["diagnostics"])
        )
    approved_at = _utc(approved_at, "approved_at")
    committed_at = _utc(committed_at, "committed_at")
    published_at = _utc(published_at, "published_at")
    approval_time = _utc_datetime(approved_at, "approved_at")
    if any(_utc_datetime(item["mapped_at"], "mapped_at") > approval_time for item in draft["statement_decisions"]):
        raise ValueError("every mapped_at must be less than or equal to approved_at")
    if approval_time > _utc_datetime(committed_at, "committed_at"):
        raise ValueError("approved_at must be less than or equal to committed_at")
    if _utc_datetime(committed_at, "committed_at") > _utc_datetime(published_at, "published_at"):
        raise ValueError("committed_at must be less than or equal to published_at")

    rules = [_lower_constraint(item) for item in constraint_ir["constraints"]]
    from governance_ledger.customer_policy import (
        _compiler_input,
        _normalized_semantic_meaning,
        _require_no_rule_conflicts,
        _validate_cross_artifact_rule_equivalence,
    )
    _require_no_rule_conflicts(rules)
    authority = draft["authority"]
    compiler_input = _compiler_input(authority, rules)
    normalized = _normalized_semantic_meaning(authority, rules, compiler_input)
    reconciliation = {
        "schema_version": "governance_semantic_reconciliation.v1",
        "source_id": draft["source_policy"]["source_policy_id"],
        "source_hash": draft["source_policy"]["snapshot_hash"],
        "extraction_id": draft["interpretation_id"],
        "operator_interpretation_decisions": copy.deepcopy(draft["statement_decisions"]),
        "unresolved_ambiguities": [],
        "semantic_conflicts": [],
        "interpretation_completeness_posture": "complete",
        "final_normalized_semantic_meaning": normalized,
    }
    semantic_commit = build_semantic_commit_bundle(
        reconciliation,
        committed_by=_nonempty(committed_by, "committed_by"),
        committed_at=committed_at,
    )
    compiled = _compile_domain_contract_v2(
        compiler_input,
        semantic_commit,
        {
            "source_policy": draft["source_policy"],
            "draft_hash": draft["draft_hash"],
            "interpretation_id": draft["interpretation_id"],
            "authority": authority,
        },
    )
    _validate_cross_artifact_rule_equivalence(
        confirmed_rules=rules,
        normalized_meaning=normalized,
        semantic_commit=semantic_commit,
        compiler_input=compiler_input,
        compiled_contract=compiled,
    )
    approval_record = {
        "approval_id": _identity(approval_id, "approval_id"),
        "approved_by": _nonempty(approved_by, "approved_by"),
        "approved_at": approved_at,
        "approved_constraint_ir_hash": constraint_ir["ir_hash"],
        "approved_semantic_commit_hash": semantic_commit["semantic_commit_hash"],
    }
    approval_record["approval_record_hash"] = artifact_hash(approval_record, "approval_record_hash")
    publication_id = _identity(publication_id, "publication_id")
    published_by = _nonempty(published_by, "published_by")
    manifest = {
        "schema_version": "publication_manifest.v1",
        "publication_id": publication_id,
        "published_at": published_at,
        "published_by": published_by,
        "contracts": [
            {
                "contract_id": compiled["contract_id"],
                "contract_version": compiled["contract_version"],
                "contract_hash": compiled["contract_hash"],
                "source_hash": draft["source_policy"]["snapshot_hash"],
                "path": f"contracts/{compiled['contract_id']}-{compiled['contract_version']}.contract.json",
            }
        ],
        "reviews": [{"path": f"reviews/{draft['source_policy']['source_policy_id']}.domain-policy.json"}],
        "snapshots": [{"path": f"snapshots/{draft['source_policy']['source_policy_id']}.source.json"}],
    }
    authority_record = {
        **copy.deepcopy(authority),
        "authority_identity_hash": canonical_sha256(authority),
    }
    provenance = {
        "interpretation_id": draft["interpretation_id"],
        "interpretation_hash": draft["draft_hash"],
        "source_snapshot_hash": draft["source_policy"]["snapshot_hash"],
        "source_statements_hash": canonical_sha256(draft["source_statements"]),
        "direct_parses_hash": canonical_sha256(draft["direct_parses"]),
        "statement_decisions_hash": canonical_sha256(draft["statement_decisions"]),
        "source_to_constraint_mappings_hash": canonical_sha256(draft["source_to_constraint_mappings"]),
        "canonical_cnl_previews_hash": canonical_sha256(draft["canonical_cnl_previews"]),
        "constraint_ir_hash": constraint_ir["ir_hash"],
        "runtime_fact_schema_hash": selected_runtime["schema_hash"],
        "domain_pack_hash": pack["canonical_hash"],
        "semantic_commit_id": semantic_commit["semantic_commit_id"],
        "semantic_commit_hash": semantic_commit["semantic_commit_hash"],
        "semantic_commit_bundle_hash": semantic_commit["bundle_hash"],
        "compiled_contract_hash": compiled["contract_hash"],
        "authority_identity_hash": authority_record["authority_identity_hash"],
        "approval_record_hash": approval_record["approval_record_hash"],
        "publication_manifest_hash": canonical_sha256(manifest),
    }
    bundle: dict[str, Any] = {
        "schema_version": AUTHORITY_BUNDLE_V2,
        "provenance_complete": True,
        "source_policy": copy.deepcopy(draft["source_policy"]),
        "source_statements": copy.deepcopy(draft["source_statements"]),
        "direct_parses": copy.deepcopy(draft["direct_parses"]),
        "statement_decisions": copy.deepcopy(draft["statement_decisions"]),
        "source_to_constraint_mappings": copy.deepcopy(draft["source_to_constraint_mappings"]),
        "canonical_cnl_previews": copy.deepcopy(draft["canonical_cnl_previews"]),
        "constraint_ir": copy.deepcopy(constraint_ir),
        "runtime_fact_schema": selected_runtime,
        "domain_pack": copy.deepcopy(draft["domain_pack"]),
        "semantic_commit_bundle": semantic_commit,
        "compiled_authority_contract": compiled,
        "authority": authority_record,
        "approval_record": approval_record,
        "publication_manifest": manifest,
        "provenance_bindings": provenance,
    }
    bundle["bundle_hash"] = artifact_hash(bundle, "bundle_hash")
    receipt: dict[str, Any] = {
        "schema_version": PUBLICATION_RECEIPT_V2,
        "receipt_id": "receipt-v2-" + bundle["bundle_hash"].removeprefix("sha256:"),
        "publication_id": publication_id,
        "authority_ref": authority["authority_ref"],
        "published_at": published_at,
        "published_by": published_by,
        "bundle_hash": bundle["bundle_hash"],
        "source_snapshot_hash": provenance["source_snapshot_hash"],
        "source_statements_hash": provenance["source_statements_hash"],
        "statement_decisions_hash": provenance["statement_decisions_hash"],
        "constraint_ir_hash": provenance["constraint_ir_hash"],
        "runtime_fact_schema_hash": provenance["runtime_fact_schema_hash"],
        "domain_pack": copy.deepcopy(draft["domain_pack"]),
        "semantic_commit_id": provenance["semantic_commit_id"],
        "semantic_commit_hash": provenance["semantic_commit_hash"],
        "semantic_commit_bundle_hash": provenance["semantic_commit_bundle_hash"],
        "compiled_contract_ref": f"{compiled['contract_id']}@{compiled['contract_version']}",
        "compiled_contract_hash": provenance["compiled_contract_hash"],
        "authority_identity_hash": provenance["authority_identity_hash"],
        "approval_record_hash": provenance["approval_record_hash"],
        "publication_manifest_hash": provenance["publication_manifest_hash"],
        "provenance_complete": True,
    }
    receipt["receipt_hash"] = artifact_hash(receipt, "receipt_hash")
    from governance_ledger.publication_provenance import validate_authority_bundle, validate_publication_receipt
    bundle_validation = validate_authority_bundle(bundle)
    receipt_validation = validate_publication_receipt(bundle, receipt)
    return {
        "schema_version": DOMAIN_POLICY_FINALIZATION_V1,
        "status": {"constraint_ir_valid": True, "runtime_fact_compatible": True, "provenance_complete": True, "publication_ready": True},
        "validated_interpretation": draft,
        "constraint_ir_validation": ir_validation,
        "runtime_fact_compatibility": compatibility,
        "approval_record": approval_record,
        "semantic_commit_bundle": semantic_commit,
        "canonical_compiler_input": compiler_input,
        "compiled_authority_contract": compiled,
        "governance_impact_preview": build_governance_impact_preview(compiled),
        "publication_manifest": manifest,
        "authority_bundle": bundle,
        "publication_receipt": receipt,
        "authority_bundle_validation": bundle_validation,
        "publication_receipt_validation": receipt_validation,
        "canonical_hashes": {
            "source_snapshot_hash": provenance["source_snapshot_hash"],
            "interpretation_hash": provenance["interpretation_hash"],
            "constraint_ir_hash": provenance["constraint_ir_hash"],
            "runtime_fact_schema_hash": provenance["runtime_fact_schema_hash"],
            "domain_pack_hash": provenance["domain_pack_hash"],
            "semantic_commit_hash": provenance["semantic_commit_hash"],
            "semantic_commit_bundle_hash": provenance["semantic_commit_bundle_hash"],
            "compiled_contract_hash": provenance["compiled_contract_hash"],
            "authority_bundle_hash": bundle["bundle_hash"],
            "publication_receipt_hash": receipt["receipt_hash"],
        },
    }


def _validate_authority_bundle_v2(bundle: dict[str, Any]) -> dict[str, Any]:
    """Independently reconstruct and validate an authority_bundle.v2 chain."""
    _exact(
        bundle,
        {
            "schema_version", "provenance_complete", "source_policy", "source_statements",
            "direct_parses", "statement_decisions", "source_to_constraint_mappings",
            "canonical_cnl_previews", "constraint_ir", "runtime_fact_schema", "domain_pack",
            "semantic_commit_bundle", "compiled_authority_contract", "authority",
            "approval_record", "publication_manifest", "provenance_bindings", "bundle_hash",
        },
        "authority_bundle.v2",
    )
    if bundle["schema_version"] != AUTHORITY_BUNDLE_V2 or bundle["provenance_complete"] is not True:
        raise ValueError("authority bundle must be provenance-complete authority_bundle.v2")
    if bundle["bundle_hash"] != artifact_hash(bundle, "bundle_hash"):
        raise ValueError("authority_bundle.v2 canonical hash is invalid")
    pack_ref = bundle["domain_pack"]
    pack = get_builtin_domain_pack(pack_ref["domain_pack_id"], pack_ref["domain_pack_version"])
    if pack_ref != _pack_ref(pack):
        raise ValueError("authority_bundle.v2 domain-pack binding is invalid")
    if bundle["runtime_fact_schema"] != pack["runtime_fact_schema"]:
        raise ValueError("authority_bundle.v2 runtime schema is not the pack-bound schema")
    validate_constraint_ir(bundle["constraint_ir"], domain_pack=pack)
    compatibility = validate_runtime_fact_compatibility(
        bundle["constraint_ir"], bundle["runtime_fact_schema"], domain_pack=pack
    )
    if not compatibility["compatible"]:
        raise ValueError("authority_bundle.v2 runtime facts are incompatible")
    source = bundle["source_policy"]
    exact = base64.b64decode(source["source_bytes_base64"].encode("ascii"), validate=True)
    if bytes_sha256(exact) != source["snapshot_hash"]:
        raise ValueError("authority_bundle.v2 source snapshot hash is invalid")
    for statement in bundle["source_statements"]:
        piece = exact[statement["start_byte"] : statement["end_byte"]]
        if not piece or bytes_sha256(piece) != statement["statement_hash"]:
            raise ValueError("authority_bundle.v2 statement span or hash is invalid")
        if base64.b64encode(piece).decode("ascii") != statement["statement_bytes_base64"]:
            raise ValueError("authority_bundle.v2 statement bytes are invalid")
    authority = bundle["authority"]
    _exact(
        authority,
        {"authority_id", "authority_version", "authority_ref", "authority_identity_hash"},
        "authority_bundle.v2 authority",
    )
    authority_core = {key: authority[key] for key in ("authority_id", "authority_version", "authority_ref")}
    if authority["authority_identity_hash"] != canonical_sha256(authority_core):
        raise ValueError("authority_bundle.v2 authority identity hash is invalid")
    provenance = bundle["provenance_bindings"]
    draft = {
        "schema_version": DOMAIN_POLICY_INTERPRETATION_V1,
        "source_policy": copy.deepcopy(source),
        "authority": authority_core,
        "domain_pack": copy.deepcopy(pack_ref),
        "runtime_fact_schema": copy.deepcopy(bundle["runtime_fact_schema"]),
        "source_statements": copy.deepcopy(bundle["source_statements"]),
        "direct_parses": copy.deepcopy(bundle["direct_parses"]),
        "statement_decisions": copy.deepcopy(bundle["statement_decisions"]),
        "constraint_ir": copy.deepcopy(bundle["constraint_ir"]),
        "canonical_cnl_previews": copy.deepcopy(bundle["canonical_cnl_previews"]),
        "source_to_constraint_mappings": copy.deepcopy(bundle["source_to_constraint_mappings"]),
        "status": _draft_status(bundle["source_statements"], bundle["constraint_ir"]["constraints"]),
        "interpretation_id": provenance["interpretation_id"],
        "draft_hash": provenance["interpretation_hash"],
    }
    _reconstruct_domain_draft(draft)
    semantic = bundle["semantic_commit_bundle"]
    compiled = bundle["compiled_authority_contract"]
    approval = bundle["approval_record"]
    manifest = bundle["publication_manifest"]
    _exact(
        approval,
        {"approval_id", "approved_by", "approved_at", "approved_constraint_ir_hash", "approved_semantic_commit_hash", "approval_record_hash"},
        "authority_bundle.v2 approval_record",
    )
    from governance_ledger.customer_policy import (
        _compiler_input,
        _normalized_semantic_meaning,
        _require_no_rule_conflicts,
        _validate_cross_artifact_rule_equivalence,
    )
    rules = [_lower_constraint(item) for item in bundle["constraint_ir"]["constraints"]]
    _require_no_rule_conflicts(rules)
    compiler_input = _compiler_input(authority_core, rules)
    normalized = _normalized_semantic_meaning(authority_core, rules, compiler_input)
    expected_reconciliation = {
        "schema_version": "governance_semantic_reconciliation.v1",
        "source_id": source["source_policy_id"],
        "source_hash": source["snapshot_hash"],
        "extraction_id": draft["interpretation_id"],
        "operator_interpretation_decisions": copy.deepcopy(draft["statement_decisions"]),
        "unresolved_ambiguities": [],
        "semantic_conflicts": [],
        "interpretation_completeness_posture": "complete",
        "final_normalized_semantic_meaning": normalized,
    }
    expected_semantic = build_semantic_commit_bundle(
        expected_reconciliation,
        committed_by=semantic["committed_by"],
        committed_at=semantic["committed_at"],
    )
    if semantic != expected_semantic:
        raise ValueError("semantic commit is not the deterministic result of the bound Constraint IR")
    _validate_compiled_authority_contract_v2(compiled)
    expected_compiled = _compile_domain_contract_v2(
        compiler_input,
        expected_semantic,
        {
            "source_policy": source,
            "draft_hash": draft["draft_hash"],
            "interpretation_id": draft["interpretation_id"],
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
        raise ValueError("compiled contract is not the deterministic lowering of the semantic commit")
    expected_provenance = {
        "interpretation_id": draft["interpretation_id"],
        "interpretation_hash": draft["draft_hash"],
        "source_snapshot_hash": source["snapshot_hash"],
        "source_statements_hash": canonical_sha256(bundle["source_statements"]),
        "direct_parses_hash": canonical_sha256(bundle["direct_parses"]),
        "statement_decisions_hash": canonical_sha256(bundle["statement_decisions"]),
        "source_to_constraint_mappings_hash": canonical_sha256(bundle["source_to_constraint_mappings"]),
        "canonical_cnl_previews_hash": canonical_sha256(bundle["canonical_cnl_previews"]),
        "constraint_ir_hash": bundle["constraint_ir"]["ir_hash"],
        "runtime_fact_schema_hash": bundle["runtime_fact_schema"]["schema_hash"],
        "domain_pack_hash": pack["canonical_hash"],
        "semantic_commit_id": semantic["semantic_commit_id"],
        "semantic_commit_hash": semantic["semantic_commit_hash"],
        "semantic_commit_bundle_hash": semantic["bundle_hash"],
        "compiled_contract_hash": compiled["contract_hash"],
        "authority_identity_hash": authority["authority_identity_hash"],
        "approval_record_hash": approval["approval_record_hash"],
        "publication_manifest_hash": canonical_sha256(manifest),
    }
    if provenance != expected_provenance:
        raise ValueError("authority_bundle.v2 provenance bindings are inconsistent")
    if semantic["source_hash"] != source["snapshot_hash"]:
        raise ValueError("semantic commit does not bind the exact source")
    if compiled["compiled_from"]["semantic_commit_hash"] != semantic["semantic_commit_hash"]:
        raise ValueError("compiled contract does not bind the semantic commit")
    if compiled["authority_ref"] != authority["authority_ref"]:
        raise ValueError("compiled contract authority identity is inconsistent")
    if approval["approval_record_hash"] != artifact_hash(approval, "approval_record_hash"):
        raise ValueError("approval record hash is invalid")
    if approval["approved_constraint_ir_hash"] != bundle["constraint_ir"]["ir_hash"] or approval["approved_semantic_commit_hash"] != semantic["semantic_commit_hash"]:
        raise ValueError("approval record bindings are inconsistent")
    contract_entry = manifest["contracts"][0]
    if contract_entry["contract_hash"] != compiled["contract_hash"] or contract_entry["source_hash"] != source["snapshot_hash"]:
        raise ValueError("publication manifest contract bindings are inconsistent")
    expected_manifest = {
        "schema_version": "publication_manifest.v1",
        "publication_id": manifest["publication_id"],
        "published_at": manifest["published_at"],
        "published_by": manifest["published_by"],
        "contracts": [
            {
                "contract_id": compiled["contract_id"],
                "contract_version": compiled["contract_version"],
                "contract_hash": compiled["contract_hash"],
                "source_hash": source["snapshot_hash"],
                "path": f"contracts/{compiled['contract_id']}-{compiled['contract_version']}.contract.json",
            }
        ],
        "reviews": [{"path": f"reviews/{source['source_policy_id']}.domain-policy.json"}],
        "snapshots": [{"path": f"snapshots/{source['source_policy_id']}.source.json"}],
    }
    if manifest != expected_manifest:
        raise ValueError("publication manifest is not the deterministic v2 manifest")
    if _utc_datetime(approval["approved_at"], "approved_at") > _utc_datetime(semantic["committed_at"], "committed_at"):
        raise ValueError("approval must precede semantic commitment")
    if _utc_datetime(semantic["committed_at"], "committed_at") > _utc_datetime(manifest["published_at"], "published_at"):
        raise ValueError("semantic commitment must precede publication")
    return {"schema_version": AUTHORITY_BUNDLE_V2, "profile": "domain_pack_provenance_complete_v2", "provenance_complete": True, "bundle_hash": bundle["bundle_hash"]}


def _validate_publication_receipt_v2(bundle: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    status = _validate_authority_bundle_v2(bundle)
    expected_fields = {
        "schema_version", "receipt_id", "publication_id", "authority_ref", "published_at",
        "published_by", "bundle_hash", "source_snapshot_hash", "source_statements_hash",
        "statement_decisions_hash", "constraint_ir_hash", "runtime_fact_schema_hash",
        "domain_pack", "semantic_commit_id", "semantic_commit_hash",
        "semantic_commit_bundle_hash", "compiled_contract_ref", "compiled_contract_hash",
        "authority_identity_hash", "approval_record_hash", "publication_manifest_hash",
        "provenance_complete", "receipt_hash",
    }
    _exact(receipt, expected_fields, "publication_receipt.v2")
    if receipt["schema_version"] != PUBLICATION_RECEIPT_V2 or receipt["provenance_complete"] is not True:
        raise ValueError("publication receipt must be provenance-complete publication_receipt.v2")
    if receipt["receipt_hash"] != artifact_hash(receipt, "receipt_hash"):
        raise ValueError("publication_receipt.v2 canonical hash is invalid")
    provenance = bundle["provenance_bindings"]
    compiled = bundle["compiled_authority_contract"]
    manifest = bundle["publication_manifest"]
    expected = {
        "receipt_id": "receipt-v2-" + bundle["bundle_hash"].removeprefix("sha256:"),
        "publication_id": manifest["publication_id"],
        "authority_ref": bundle["authority"]["authority_ref"],
        "published_at": manifest["published_at"],
        "published_by": manifest["published_by"],
        "bundle_hash": bundle["bundle_hash"],
        "source_snapshot_hash": provenance["source_snapshot_hash"],
        "source_statements_hash": provenance["source_statements_hash"],
        "statement_decisions_hash": provenance["statement_decisions_hash"],
        "constraint_ir_hash": provenance["constraint_ir_hash"],
        "runtime_fact_schema_hash": provenance["runtime_fact_schema_hash"],
        "domain_pack": bundle["domain_pack"],
        "semantic_commit_id": provenance["semantic_commit_id"],
        "semantic_commit_hash": provenance["semantic_commit_hash"],
        "semantic_commit_bundle_hash": provenance["semantic_commit_bundle_hash"],
        "compiled_contract_ref": f"{compiled['contract_id']}@{compiled['contract_version']}",
        "compiled_contract_hash": provenance["compiled_contract_hash"],
        "authority_identity_hash": provenance["authority_identity_hash"],
        "approval_record_hash": provenance["approval_record_hash"],
        "publication_manifest_hash": provenance["publication_manifest_hash"],
    }
    for field, value in expected.items():
        if receipt[field] != value:
            raise ValueError(f"publication_receipt.v2 {field} binding is invalid")
    return {**status, "schema_version": PUBLICATION_RECEIPT_V2, "receipt_hash": receipt["receipt_hash"]}


def _constraint_from_legacy_rule(rule: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    if rule["rule_type"] == "required_actor_role":
        if rule["role"] not in pack["role_kinds"]:
            raise ValueError("direct role is outside repository pack vocabulary")
        return _constraint(action="modify", resource={"kind": "repository_change", "match": "any", "value": None}, effect="require", acting_role=rule["role"])
    if rule["rule_type"] == "target":
        return _constraint(action="modify", resource={"kind": "repository_path", "match": rule["match"], "value": rule["value"]}, effect=rule["effect"])
    raise ValueError("the repository pack does not compile this legacy rule category")


def _constraint_from_control(control: dict[str, Any], selections: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    emitter = control["emitter_id"]
    if emitter == ACTING_ROLE_EMITTER_ID:
        return _constraint(action="modify", resource={"kind": "repository_change", "match": "any", "value": None}, effect="require", acting_role=selections["role"])
    if emitter in {EXACT_PATH_EMITTER_ID, PREFIX_PATH_EMITTER_ID}:
        match = "exact" if emitter == EXACT_PATH_EMITTER_ID else "prefix"
        return _constraint(action="modify", resource={"kind": "repository_path", "match": match, "value": selections["path"]}, effect=selections["effect"])
    raise ValueError(f"mapping control requires unavailable emitter: {emitter}")


def _constraint(*, action: str, resource: dict[str, Any], effect: str, acting_role: str | None = None) -> dict[str, Any]:
    facts = {"actor.subject_kind", "proposal.action", "proposal.resource.kind"}
    if resource["value"] is not None:
        facts.add("proposal.resource.path")
    if acting_role:
        facts.add("actor.role")
    return {
        "subject": {"kind": "subject_kind", "value": "agent"},
        "acting_role": {"kind": "role", "value": acting_role} if acting_role else None,
        "action": action,
        "resource": resource,
        "effect": effect,
        "condition": None,
        "obligations": {"approvals": [], "evidence": [], "separation_of_duties": []},
        "exceptions": [],
        "required_runtime_facts": sorted(facts),
    }


def _finalize_constraint(constraint: dict[str, Any]) -> dict[str, Any]:
    core = copy.deepcopy(constraint)
    core.pop("constraint_id", None)
    return {"constraint_id": "constraint-" + canonical_sha256(core).removeprefix("sha256:"), **core}


def _build_ir(constraints: list[dict[str, Any]], pack: dict[str, Any]) -> dict[str, Any]:
    result = finalize_constraint_ir({"schema_version": "constraint_ir.v1", "domain_pack": _pack_ref(pack), "runtime_fact_schema_hash": pack["runtime_fact_schema"]["schema_hash"], "constraints": copy.deepcopy(constraints)})
    validate_constraint_ir(result, domain_pack=pack)
    return result


def _direct_parse(statement: dict[str, Any], constraint_ids: list[str], pack: dict[str, Any]) -> dict[str, Any]:
    core = {"statement_id": statement["statement_id"], "start_byte": statement["start_byte"], "end_byte": statement["end_byte"], "constraint_ids": constraint_ids, "compiler_id": pack["grammar_compiler"]["compiler_id"], "compiler_version": pack["grammar_compiler"]["compiler_version"]}
    return {"parse_id": "direct-parse-" + canonical_sha256(core).removeprefix("sha256:"), **core, "parse_hash": canonical_sha256(core)}


def _statement_decision(draft: dict[str, Any], statement: dict[str, Any], *, disposition: str, mapper_identity: str, mapped_at: str, reason_code: str, human_reason: str | None, control: dict[str, Any] | None, selections: dict[str, Any] | None, constraint: dict[str, Any] | None) -> dict[str, Any]:
    mapper_identity = _nonempty(mapper_identity, "mapper_identity")
    if len(mapper_identity) > 256:
        raise ValueError("mapper_identity must contain at most 256 characters")
    common = {
        "schema_version": POLICY_MAPPING_DECISION_V1,
        "source_document_hash": draft["source_policy"]["snapshot_hash"],
        "statement_id": statement["statement_id"],
        "start_byte": statement["start_byte"],
        "end_byte": statement["end_byte"],
        "domain_pack": copy.deepcopy(draft["domain_pack"]),
        "disposition": disposition,
        "reason_code": reason_code,
        "human_reason": human_reason,
        "mapper_identity": mapper_identity,
        "mapped_at": _utc(mapped_at, "mapped_at"),
    }
    if disposition == "enforced":
        common.update(
            {
                "control_id": control["control_id"],
                "emitter_id": control["emitter_id"],
                "control_selections": copy.deepcopy(selections),
                "selected_subject": copy.deepcopy(constraint["subject"]),
                "selected_role": copy.deepcopy(constraint["acting_role"]),
                "selected_action": constraint["action"],
                "selected_resource": copy.deepcopy(constraint["resource"]),
                "selected_effect": constraint["effect"],
                "selected_typed_conditions": copy.deepcopy(constraint["condition"]),
                "selected_obligations": copy.deepcopy(constraint["obligations"]),
                "selected_exceptions": copy.deepcopy(constraint["exceptions"]),
                "required_runtime_facts": copy.deepcopy(constraint["required_runtime_facts"]),
                "constraint_id": constraint["constraint_id"],
            }
        )
    common["decision_hash"] = artifact_hash(common, "decision_hash")
    return common


def _apply_canonical_decision(draft: dict[str, Any], decision: dict[str, Any], *, reconstructing: bool) -> dict[str, Any]:
    result = copy.deepcopy(draft)
    pack = _pack_for_draft(result)
    statement = _statement(result, decision["statement_id"])
    if statement["classification"] != "pending":
        raise ValueError("statement decision targets a non-pending statement")
    disposition = decision["disposition"]
    control = None
    selections = None
    constraint = None
    if disposition == "enforced":
        controls = mapping_control_index(pack)
        control = controls.get(decision.get("control_id"))
        if control is None or control["control_id"] not in statement["available_mapping_control_ids"]:
            raise ValueError("statement decision selects an unavailable enforcement control")
        selections = _validate_selections(control, decision.get("control_selections"))
        constraint = _finalize_constraint(_constraint_from_control(control, selections, pack))
    elif disposition == "informational":
        if decision.get("reason_code") not in _INFORMATIONAL_REASONS:
            raise ValueError("informational decision reason is invalid")
    elif disposition == "unsupported":
        if decision.get("reason_code") not in _UNSUPPORTED_REASONS:
            raise ValueError("unsupported decision reason is invalid")
    else:
        raise ValueError("statement decision disposition is invalid")
    expected = _statement_decision(
        result,
        statement,
        disposition=disposition,
        mapper_identity=decision["mapper_identity"],
        mapped_at=decision["mapped_at"],
        reason_code=decision["reason_code"],
        human_reason=decision["human_reason"],
        control=control,
        selections=selections,
        constraint=constraint,
    )
    if decision != expected:
        raise ValueError("statement decision is modified or inconsistent")
    result["statement_decisions"].append(copy.deepcopy(decision))
    statement["classification"] = disposition
    statement["available_mapping_control_ids"] = []
    statement["decision_hash"] = decision["decision_hash"]
    constraints = copy.deepcopy(result["constraint_ir"]["constraints"]) if result["constraint_ir"] else []
    if constraint is not None:
        constraints.append(constraint)
        result["source_to_constraint_mappings"].append(_source_mapping(statement, [constraint["constraint_id"]], "human_mapping", decision["decision_hash"]))
        result["canonical_cnl_previews"].append({"constraint_id": constraint["constraint_id"], "preview": _cnl_preview(constraint)})
    result["constraint_ir"] = _build_ir(constraints, pack) if constraints else None
    result["status"] = _draft_status(result["source_statements"], constraints)
    result["draft_hash"] = artifact_hash(result, "draft_hash")
    if not reconstructing and result["constraint_ir"] is not None:
        validate_constraint_ir(result["constraint_ir"], domain_pack=pack)
    return result


def _reconstruct_domain_draft(draft: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(draft, dict) or draft.get("schema_version") != DOMAIN_POLICY_INTERPRETATION_V1:
        raise ValueError(f"interpretation_draft must be {DOMAIN_POLICY_INTERPRETATION_V1}")
    try:
        source = draft["source_policy"]
        exact = base64.b64decode(source["source_bytes_base64"].encode("ascii"), validate=True)
        base = interpret_policy_with_domain_pack(
            exact,
            domain_pack_id=draft["domain_pack"]["domain_pack_id"],
            domain_pack_version=draft["domain_pack"]["domain_pack_version"],
            source_policy_id=source["source_policy_id"],
            source_revision=source["source_revision"],
            authority_id=draft["authority"]["authority_id"],
            authority_version=draft["authority"]["authority_version"],
        )
        for decision in draft["statement_decisions"]:
            base = _apply_canonical_decision(base, decision, reconstructing=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("domain-policy interpretation cannot be reconstructed") from exc
    if base != draft:
        raise ValueError("domain-policy interpretation is modified or inconsistent")
    return base


def _lower_constraint(constraint: dict[str, Any]) -> dict[str, Any]:
    if constraint["exceptions"] or any(constraint["obligations"].values()) or constraint["condition"] is not None:
        raise ValueError("repository-changes lowering received an unsupported Constraint IR concept")
    if constraint["acting_role"] is not None:
        rule = {"rule_type": "required_actor_role", "role": constraint["acting_role"]["value"]}
    elif constraint["resource"]["kind"] == "repository_path":
        rule = {"rule_type": "target", "effect": constraint["effect"], "match": constraint["resource"]["match"], "value": constraint["resource"]["value"]}
    else:
        raise ValueError("Constraint IR concept is not supported by repository lowering")
    rule["rule_id"] = "rule-" + canonical_sha256(rule).removeprefix("sha256:")
    return rule


def _compile_domain_contract_v2(
    compiler_input: dict[str, Any],
    semantic_commit: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    """Project the installed compiler result into the new strict v2 identity."""
    from governance_ledger.customer_policy import _compile

    compiled = _compile(compiler_input, semantic_commit, draft)
    compiled["schema_version"] = COMPILED_AUTHORITY_CONTRACT_V2
    # compiled_authority_contract.v2 requires the complete target surface even
    # when an acting-role-only policy has no path rules.  The legacy compiler
    # omits empty sections, so normalize only this required v2 representation.
    compiled.setdefault("target_requirements", {"allow": [], "deny": []})
    compiled["contract_hash"] = "sha256:" + compute_contract_hash(compiled)
    _validate_compiled_authority_contract_v2(compiled)
    return compiled


def _validate_compiled_authority_contract_v2(contract: dict[str, Any]) -> dict[str, Any]:
    """Independently validate the exact compiled surface supported by v2 publication."""
    _exact(
        contract,
        {
            "schema_version", "contract_id", "contract_version", "authority_ref",
            "compiled_from", "authority_requirements", "approval_requirements",
            "artifact_requirements", "stage_requirements", "invariants",
            "target_requirements", "lineage", "contract_hash",
        },
        COMPILED_AUTHORITY_CONTRACT_V2,
    )
    if contract["schema_version"] != COMPILED_AUTHORITY_CONTRACT_V2:
        raise ValueError(f"compiled contract must be {COMPILED_AUTHORITY_CONTRACT_V2}")
    _identity(contract["contract_id"], "compiled contract contract_id")
    if not isinstance(contract["contract_version"], str) or not re.fullmatch(
        r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)",
        contract["contract_version"],
    ):
        raise ValueError("compiled contract contract_version must be canonical semver")
    _nonempty(contract["authority_ref"], "compiled contract authority_ref")

    authority = contract["authority_requirements"]
    if not isinstance(authority, dict) or set(authority) - {"required_roles"}:
        raise ValueError("compiled contract authority_requirements is invalid")
    if "required_roles" in authority:
        roles = authority["required_roles"]
        if (
            not isinstance(roles, list)
            or not roles
            or roles != sorted(set(roles))
            or any(not isinstance(role, str) or not role for role in roles)
        ):
            raise ValueError("compiled contract required_roles must be sorted unique strings")
    for field in (
        "approval_requirements", "artifact_requirements", "stage_requirements", "invariants"
    ):
        if contract[field] != {}:
            raise ValueError(
                f"{COMPILED_AUTHORITY_CONTRACT_V2} does not support {field} yet"
            )

    targets = contract["target_requirements"]
    _exact(targets, {"allow", "deny"}, "compiled contract target_requirements")
    target_effects: dict[str, str] = {}
    for effect in ("allow", "deny"):
        rules = targets[effect]
        if not isinstance(rules, list):
            raise ValueError(f"compiled contract target_requirements.{effect} must be an array")
        seen: set[str] = set()
        for index, rule in enumerate(rules):
            label = f"compiled contract target_requirements.{effect}[{index}]"
            _exact(rule, {"match", "value"}, label)
            if rule["match"] not in {"exact", "prefix"}:
                raise ValueError(f"{label}.match is unsupported")
            validate_format_value(
                REPOSITORY_PATH_FORMAT_ID,
                rule["value"],
                match_mode=rule["match"],
                label=f"{label}.value",
            )
            signature = canonical_sha256(rule)
            if signature in seen:
                raise ValueError(f"{label} duplicates another target rule")
            prior_effect = target_effects.get(signature)
            if prior_effect is not None and prior_effect != effect:
                raise ValueError(f"{label} contradicts a {prior_effect} target rule")
            seen.add(signature)
            target_effects[signature] = effect

    lineage = contract["lineage"]
    _exact(
        lineage,
        {"schema_version", "source_hash", "compilation_report_hash", "review_id"},
        "compiled contract lineage",
    )
    if lineage["schema_version"] != "governance_authority_lineage.v1":
        raise ValueError("compiled contract lineage schema is unsupported")
    for field in ("source_hash", "compilation_report_hash"):
        if not isinstance(lineage[field], str) or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", lineage[field]
        ):
            raise ValueError(f"compiled contract lineage {field} is invalid")
    _nonempty(lineage["review_id"], "compiled contract lineage review_id")

    compiled_from = contract["compiled_from"]
    _exact(
        compiled_from,
        {"schema_version", "semantic_commit_id", "semantic_commit_hash", "source_hash", "resolved_interpretation_count"},
        "compiled contract compiled_from",
    )
    if compiled_from["schema_version"] != "semantic_commit_bundle.v1":
        raise ValueError("compiled contract compiled_from schema is unsupported")
    _nonempty(compiled_from["semantic_commit_id"], "compiled contract semantic_commit_id")
    for field in ("semantic_commit_hash", "source_hash"):
        if not isinstance(compiled_from[field], str) or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", compiled_from[field]
        ):
            raise ValueError(f"compiled contract compiled_from {field} is invalid")
    count = compiled_from["resolved_interpretation_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("compiled contract resolved_interpretation_count is invalid")
    if contract["contract_hash"] != "sha256:" + compute_contract_hash(contract):
        raise ValueError("compiled_authority_contract.v2 contract_hash is invalid")
    return {
        "schema_version": COMPILED_AUTHORITY_CONTRACT_V2,
        "contract_hash": contract["contract_hash"],
        "valid": True,
    }


def _validate_selections(control: dict[str, Any], selections: Any) -> dict[str, Any]:
    if not isinstance(selections, dict):
        raise ValueError("mapping selections must be an object")
    schema = control["selection_schema"]
    _exact(selections, set(schema), "mapping selections")
    result = copy.deepcopy(selections)
    for name, field in schema.items():
        value = result[name]
        value_type = field["type"]
        if value_type == "enum" and value not in field["enum_values"]:
            raise ValueError(f"mapping selection {name} is outside the control enum")
        if value_type == "string" and (not isinstance(value, str) or not value):
            raise ValueError(f"mapping selection {name} must be a non-empty string")
        if value_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"mapping selection {name} must be an integer")
        if value_type == "boolean" and not isinstance(value, bool):
            raise ValueError(f"mapping selection {name} must be Boolean")
        if value_type == "decimal" and (not isinstance(value, str) or not _DECIMAL.fullmatch(value)):
            raise ValueError(f"mapping selection {name} must be a canonical decimal string")
        if value_type == "timestamp":
            _utc(value, f"mapping selection {name}")
        if value_type == "string_set" and (
            not isinstance(value, list)
            or value != sorted(set(value))
            or any(not isinstance(item, str) or not item for item in value)
        ):
            raise ValueError(f"mapping selection {name} must be a sorted unique string array")
        if field["format_id"] is not None:
            validate_format_value(field["format_id"], value, label=f"mapping selection {name}")
    return result


def _source_mapping(statement: dict[str, Any], constraint_ids: list[str], mode: str, decision_hash: str | None) -> dict[str, Any]:
    core = {"statement_id": statement["statement_id"], "start_byte": statement["start_byte"], "end_byte": statement["end_byte"], "constraint_ids": constraint_ids, "mode": mode, "statement_decision_hash": decision_hash}
    return {"mapping_id": "constraint-mapping-" + canonical_sha256(core).removeprefix("sha256:"), **core}


def _cnl_preview(constraint: dict[str, Any]) -> str:
    subject = constraint["subject"]["value"]
    resource = constraint["resource"]
    resource_text = f"{resource['kind']}:{resource['match']}"
    if resource["value"] is not None:
        resource_text += f' "{resource["value"]}"'
    if constraint["acting_role"]:
        return f"REQUIRE {subject} ACTING AS {constraint['acting_role']['value']} TO {constraint['action']} {resource_text}."
    return f"{constraint['effect'].upper()} {subject} TO {constraint['action']} {resource_text}."


def _draft_status(statements: list[dict[str, Any]], constraints: list[dict[str, Any]]) -> dict[str, Any]:
    pending = sum(item["classification"] == "pending" for item in statements)
    return {"statement_classification_complete": pending == 0, "pending_statement_count": pending, "enforceable_constraint_count": len(constraints), "ready_for_finalization": pending == 0 and bool(constraints), "publication_ready": False}


def _pack_ref(pack: dict[str, Any]) -> dict[str, str]:
    return {"domain_pack_id": pack["domain_pack_id"], "domain_pack_version": pack["domain_pack_version"], "domain_pack_hash": pack["canonical_hash"]}


def _pack_for_draft(draft: dict[str, Any]) -> dict[str, Any]:
    ref = draft["domain_pack"]
    pack = get_builtin_domain_pack(ref["domain_pack_id"], ref["domain_pack_version"])
    if ref != _pack_ref(pack) or draft["runtime_fact_schema"] != pack["runtime_fact_schema"]:
        raise ValueError("domain-policy interpretation has a tampered pack/runtime binding")
    return pack


def _statement(draft: dict[str, Any], statement_id: str) -> dict[str, Any]:
    matches = [item for item in draft["source_statements"] if item["statement_id"] == statement_id]
    if len(matches) != 1:
        raise ValueError("statement_id does not identify one source statement")
    return matches[0]


def _utc(value: Any, label: str) -> str:
    _utc_datetime(value, label)
    return value


def _utc_datetime(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not _CANONICAL_UTC.fullmatch(value):
        raise ValueError(f"{label} must be canonical UTC (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be canonical UTC (YYYY-MM-DDTHH:MM:SSZ)") from exc


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}", value) or "@" in value:
        raise ValueError(f"{label} must be a portable identity without @")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _exact(value: Any, expected: set[str], label: str) -> None:
    actual = set(value) if isinstance(value, dict) else set()
    if not isinstance(value, dict) or actual != expected:
        raise ValueError(f"{label} fields are invalid; unknown={sorted(actual - expected)}, missing={sorted(expected - actual)}")
