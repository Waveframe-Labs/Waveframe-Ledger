"""Deterministic domain-pack policy interpretation, mapping, and publication.

This module performs no filesystem or network access.  It uses the selected
pack's bounded grammar and controls, validates Waveframe Constraint IR, then
lowers to Ledger's existing Contract Compiler boundary.
"""

from __future__ import annotations

import base64
import copy
import re
from datetime import datetime
from typing import Any

from governance_ledger.constraint_ir import (
    artifact_hash,
    finalize_constraint_ir,
    validate_constraint_ir,
    validate_runtime_fact_compatibility,
)
from governance_ledger.domain_packs import (
    REPOSITORY_CHANGES_PACK_ID,
    REPOSITORY_CHANGES_PACK_VERSION,
    get_builtin_domain_pack,
    mapping_control_index,
)
from governance_ledger.publication_provenance import (
    bytes_sha256,
    canonical_sha256,
    validate_authority_bundle,
    validate_publication_receipt,
)
from governance_ledger.semantics.compiler import build_semantic_commit_bundle
from governance_ledger.semantics.preview import build_governance_impact_preview
from governance_ledger.semantics.publication import build_authority_bundle, build_publication_receipt


DOMAIN_POLICY_INTERPRETATION_V1 = "domain_policy_interpretation.v1"
POLICY_MAPPING_DECISION_V1 = "policy_mapping_decision.v1"
POLICY_MAPPING_APPLICATION_V1 = "policy_mapping_application.v1"
DOMAIN_POLICY_FINALIZATION_V1 = "domain_policy_finalization.v1"
DOMAIN_POLICY_AUTHORITY_BUNDLE_V1 = "domain_policy_authority_bundle.v1"
DOMAIN_POLICY_PUBLICATION_RECEIPT_V1 = "domain_policy_publication_receipt.v1"

_CANONICAL_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_DECIMAL = re.compile(r"(?:0|[1-9]\d*)(?:\.\d*[1-9])?\Z")
_NORMATIVE = re.compile(
    r"\b(may|must|shall|should|cannot|require|requires|required|only|forbid|"
    r"forbidden|prohibit|prohibited)\b",
    re.IGNORECASE,
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
    """Interpret exact bytes with one selected built-in domain pack.

    Matching clauses compile directly.  Other normative clauses remain bound to
    their exact byte spans and expose only the pack's bounded mapping controls.
    """
    pack = get_builtin_domain_pack(domain_pack_id, domain_pack_version)
    if (domain_pack_id, domain_pack_version) != (
        REPOSITORY_CHANGES_PACK_ID,
        REPOSITORY_CHANGES_PACK_VERSION,
    ):
        raise ValueError("the selected pack has no local deterministic grammar implementation")

    # This compatibility grammar is intentionally reused internally.  The new
    # API translates its repository-specific result into pack-scoped concepts;
    # it is not treated as a universal company-policy interpreter.
    from governance_ledger.customer_policy import (
        _interpret_customer_policy_v0_6_compatibility,
    )

    legacy = _interpret_customer_policy_v0_6_compatibility(
        source_bytes,
        source_policy_id=source_policy_id,
        source_revision=source_revision,
        authority_id=authority_id,
        authority_version=authority_version,
    )
    source = copy.deepcopy(legacy["source_policy"])
    pack_ref = _pack_ref(pack)
    constraints: list[dict[str, Any]] = []
    previews: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    statements: list[dict[str, Any]] = []
    rules = {rule["rule_id"]: rule for rule in legacy["proposed_rules"]}
    source_bytes_exact = base64.b64decode(source["source_bytes_base64"].encode("ascii"))
    all_control_ids = [item["control_id"] for item in pack["allowed_mapping_controls"]]

    for statement in legacy["source_statements"]:
        direct_constraints: list[dict[str, Any]] = []
        text = source_bytes_exact[statement["start_byte"] : statement["end_byte"]].decode(
            "utf-8"
        ).strip()
        if statement["classification"] == "enforced":
            try:
                direct_constraints = [
                    _constraint_from_legacy_rule(rules[rule_id], text, pack)
                    for rule_id in statement["proposed_rule_ids"]
                ]
            except ValueError:
                direct_constraints = []
        if direct_constraints:
            classification = "direct"
            constraint_ids: list[str] = []
            for constraint in direct_constraints:
                constraint = _finalize_constraint(constraint)
                constraints.append(constraint)
                constraint_ids.append(constraint["constraint_id"])
                previews.append(
                    {
                        "constraint_id": constraint["constraint_id"],
                        "preview": _cnl_preview(constraint),
                    }
                )
            mappings.append(_source_mapping(statement, constraint_ids, "direct", None))
            controls: list[str] = []
            reason = None
        elif statement["classification"] == "informational" and not _NORMATIVE.search(text):
            classification = "informational"
            controls = []
            reason = None
        else:
            classification = "requires_mapping"
            controls = all_control_ids
            reason = (
                "ambiguous_or_conflicting"
                if statement["classification"] == "requires_resolution"
                else "outside_deterministic_grammar"
            )
        statements.append(
            {
                "statement_id": statement["statement_id"],
                "start_byte": statement["start_byte"],
                "end_byte": statement["end_byte"],
                "statement_bytes_base64": statement["statement_bytes_base64"],
                "statement_hash": statement["statement_hash"],
                "classification": classification,
                "mapping_reason": reason,
                "available_mapping_control_ids": controls,
            }
        )

    constraint_ir = _build_ir(constraints, pack) if constraints else None
    draft: dict[str, Any] = {
        "schema_version": DOMAIN_POLICY_INTERPRETATION_V1,
        "source_policy": source,
        "authority": copy.deepcopy(legacy["authority"]),
        "domain_pack": pack_ref,
        "runtime_fact_schema": copy.deepcopy(pack["runtime_fact_schema"]),
        "source_statements": statements,
        "constraint_ir": constraint_ir,
        "canonical_cnl_previews": previews,
        "source_to_constraint_mappings": mappings,
        "mapping_decisions": [],
        "status": _draft_status(statements, constraints),
    }
    core_hash = canonical_sha256(draft)
    draft["interpretation_id"] = "domain-interpretation-" + core_hash.removeprefix("sha256:")
    draft["draft_hash"] = artifact_hash(draft, "draft_hash")
    return draft


def inspect_policy_mapping_controls(
    interpretation_draft: dict[str, Any], statement_id: str
) -> dict[str, Any]:
    """Return renderable, bounded controls for one exact unmapped statement."""
    draft = _reconstruct_domain_draft(interpretation_draft)
    statement = _statement(draft, statement_id)
    if statement["classification"] != "requires_mapping":
        raise ValueError("mapping controls are available only for a statement requiring mapping")
    pack = _pack_for_draft(draft)
    index = mapping_control_index(pack)
    return {
        "domain_pack": copy.deepcopy(draft["domain_pack"]),
        "statement": copy.deepcopy(statement),
        "controls": [index[item] for item in statement["available_mapping_control_ids"]],
    }


def apply_policy_mapping_decision(
    interpretation_draft: dict[str, Any],
    *,
    statement_id: str,
    control_id: str,
    selections: dict[str, Any],
    mapper_identity: str,
    mapped_at: str,
) -> dict[str, Any]:
    """Apply one pack-bounded human decision and return its deterministic outputs."""
    draft = _reconstruct_domain_draft(interpretation_draft)
    pack = _pack_for_draft(draft)
    statement = _statement(draft, statement_id)
    if statement["classification"] != "requires_mapping":
        raise ValueError("the selected statement does not require mapping")
    if control_id not in statement["available_mapping_control_ids"]:
        raise ValueError("the selected mapping control is not exposed for this statement")
    control = mapping_control_index(pack)[control_id]
    selections = _validate_selections(control, selections)
    constraint = _finalize_constraint(_constraint_from_control(control, selections, pack))
    preview = _cnl_preview(constraint)
    decision = _mapping_decision(
        draft,
        statement,
        control,
        selections,
        constraint,
        mapper_identity,
        mapped_at,
    )
    updated = _apply_canonical_decision(draft, decision, reconstructing=False)
    validation = validate_constraint_ir(updated["constraint_ir"], domain_pack=pack)
    compatibility = validate_runtime_fact_compatibility(
        updated["constraint_ir"], updated["runtime_fact_schema"], domain_pack=pack
    )
    mapping = next(
        item
        for item in updated["source_to_constraint_mappings"]
        if item["statement_id"] == statement_id
    )
    return {
        "schema_version": POLICY_MAPPING_APPLICATION_V1,
        "mapping_decision": copy.deepcopy(decision),
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
    """Validate, lower, and publish a fully mapped domain-policy interpretation."""
    draft = _reconstruct_domain_draft(interpretation_draft)
    if not draft["status"]["ready_for_finalization"]:
        raise ValueError("domain policy requires all normative statements to be directly compiled or mapped")
    pack = _pack_for_draft(draft)
    constraint_ir = draft["constraint_ir"]
    validation = validate_constraint_ir(constraint_ir, domain_pack=pack)
    selected_runtime = copy.deepcopy(runtime_fact_schema or draft["runtime_fact_schema"])
    runtime_compatibility = validate_runtime_fact_compatibility(
        constraint_ir, selected_runtime, domain_pack=pack
    )
    if not runtime_compatibility["compatible"]:
        messages = "; ".join(item["message"] for item in runtime_compatibility["diagnostics"])
        raise ValueError(f"domain policy is not publication-ready: {messages}")

    approved_at = _utc(approved_at, "approved_at")
    committed_at = _utc(committed_at, "committed_at")
    published_at = _utc(published_at, "published_at")
    approval_time = _utc_datetime(approved_at, "approved_at")
    if any(_utc_datetime(item["mapped_at"], "mapped_at") > approval_time for item in draft["mapping_decisions"]):
        raise ValueError("every mapped_at must be less than or equal to approved_at")
    if approval_time > _utc_datetime(committed_at, "committed_at"):
        raise ValueError("approved_at must be less than or equal to committed_at")
    if _utc_datetime(committed_at, "committed_at") > _utc_datetime(published_at, "published_at"):
        raise ValueError("committed_at must be less than or equal to published_at")

    rules = [_lower_constraint(item) for item in constraint_ir["constraints"]]
    from governance_ledger.customer_policy import (
        _compile,
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
        "operator_interpretation_decisions": copy.deepcopy(draft["mapping_decisions"]),
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
    compiled = _compile(
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
    approval_record["approval_record_hash"] = artifact_hash(
        approval_record, "approval_record_hash"
    )
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
        "reviews": [
            {"path": f"reviews/{draft['source_policy']['source_policy_id']}.domain-policy.json"}
        ],
        "snapshots": [
            {"path": f"snapshots/{draft['source_policy']['source_policy_id']}.source.json"}
        ],
    }
    preview = build_governance_impact_preview(compiled)
    legacy_bundle = build_authority_bundle(
        authority_contract=compiled,
        publication_manifest=manifest,
        governance_impact_preview=preview,
        semantic_commit_bundle=semantic_commit,
        compiled_authority_contract=compiled,
    )
    legacy_receipt = build_publication_receipt(
        authority_bundle=legacy_bundle, published_at=published_at
    )
    validate_authority_bundle(legacy_bundle)
    validate_publication_receipt(legacy_bundle, legacy_receipt)

    mappings_hash = canonical_sha256(draft["source_to_constraint_mappings"])
    outer_bundle: dict[str, Any] = {
        "schema_version": DOMAIN_POLICY_AUTHORITY_BUNDLE_V1,
        "provenance_complete": True,
        "source_policy": copy.deepcopy(draft["source_policy"]),
        "source_statements": copy.deepcopy(draft["source_statements"]),
        "interpretation": {
            "interpretation_id": draft["interpretation_id"],
            "draft_hash": draft["draft_hash"],
            "source_statements_hash": canonical_sha256(draft["source_statements"]),
            "source_to_constraint_mappings_hash": mappings_hash,
        },
        "source_to_constraint_mappings": copy.deepcopy(
            draft["source_to_constraint_mappings"]
        ),
        "mapping_decisions": copy.deepcopy(draft["mapping_decisions"]),
        "canonical_cnl_previews": copy.deepcopy(draft["canonical_cnl_previews"]),
        "constraint_ir": copy.deepcopy(constraint_ir),
        "runtime_fact_schema": selected_runtime,
        "domain_pack": copy.deepcopy(draft["domain_pack"]),
        "semantic_commit_bundle": semantic_commit,
        "compiled_authority_contract": compiled,
        "authority": {
            **copy.deepcopy(authority),
            "authority_identity_hash": canonical_sha256(authority),
        },
        "approval_record": approval_record,
        "authority_bundle_v1": legacy_bundle,
        "publication_receipt_v1": legacy_receipt,
        "compatibility": {
            "embedded_v1_profile": "legacy_provenance_incomplete",
            "reason": (
                "Released v1 schemas are unchanged; complete domain-pack lineage is bound "
                "by this versioned envelope and its receipt."
            ),
        },
    }
    outer_bundle["bundle_hash"] = artifact_hash(outer_bundle, "bundle_hash")
    outer_receipt: dict[str, Any] = {
        "schema_version": DOMAIN_POLICY_PUBLICATION_RECEIPT_V1,
        "receipt_id": "domain-receipt-" + outer_bundle["bundle_hash"].removeprefix("sha256:"),
        "publication_id": publication_id,
        "authority_ref": authority["authority_ref"],
        "published_at": published_at,
        "published_by": published_by,
        "bundle_hash": outer_bundle["bundle_hash"],
        "source_snapshot_hash": draft["source_policy"]["snapshot_hash"],
        "domain_pack_hash": pack["canonical_hash"],
        "constraint_ir_hash": constraint_ir["ir_hash"],
        "semantic_commit_hash": semantic_commit["semantic_commit_hash"],
        "semantic_commit_bundle_hash": semantic_commit["bundle_hash"],
        "compiled_contract_hash": compiled["contract_hash"],
        "embedded_authority_bundle_hash": canonical_sha256(legacy_bundle),
        "embedded_publication_receipt_hash": legacy_receipt["receipt_hash"],
        "provenance_complete": True,
    }
    outer_receipt["receipt_hash"] = artifact_hash(outer_receipt, "receipt_hash")
    provenance_validation = validate_domain_policy_publication(
        outer_bundle, outer_receipt
    )
    return {
        "schema_version": DOMAIN_POLICY_FINALIZATION_V1,
        "status": {
            "constraint_ir_valid": True,
            "runtime_fact_compatible": True,
            "provenance_complete": True,
            "publication_ready": True,
        },
        "validated_interpretation": draft,
        "constraint_ir_validation": validation,
        "runtime_fact_compatibility": runtime_compatibility,
        "approval_record": approval_record,
        "semantic_commit_bundle": semantic_commit,
        "canonical_compiler_input": compiler_input,
        "compiled_authority_contract": compiled,
        "governance_impact_preview": preview,
        "publication_manifest": manifest,
        "authority_bundle_v1": legacy_bundle,
        "publication_receipt_v1": legacy_receipt,
        "domain_policy_authority_bundle": outer_bundle,
        "domain_policy_publication_receipt": outer_receipt,
        "provenance_validation": provenance_validation,
        "canonical_hashes": {
            "source_snapshot_hash": draft["source_policy"]["snapshot_hash"],
            "interpretation_hash": draft["draft_hash"],
            "constraint_ir_hash": constraint_ir["ir_hash"],
            "runtime_fact_schema_hash": selected_runtime["schema_hash"],
            "domain_pack_hash": pack["canonical_hash"],
            "semantic_commit_hash": semantic_commit["semantic_commit_hash"],
            "semantic_commit_bundle_hash": semantic_commit["bundle_hash"],
            "compiled_contract_hash": compiled["contract_hash"],
            "authority_bundle_v1_hash": canonical_sha256(legacy_bundle),
            "publication_receipt_v1_hash": legacy_receipt["receipt_hash"],
            "domain_policy_bundle_hash": outer_bundle["bundle_hash"],
            "domain_policy_receipt_hash": outer_receipt["receipt_hash"],
        },
    }


def validate_domain_policy_publication(
    bundle: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    """Validate the complete new-workflow provenance chain and both self-hashes."""
    if not isinstance(bundle, dict) or bundle.get("schema_version") != DOMAIN_POLICY_AUTHORITY_BUNDLE_V1:
        raise ValueError(f"bundle must be {DOMAIN_POLICY_AUTHORITY_BUNDLE_V1}")
    expected_bundle_fields = {
        "schema_version",
        "provenance_complete",
        "source_policy",
        "source_statements",
        "interpretation",
        "source_to_constraint_mappings",
        "mapping_decisions",
        "canonical_cnl_previews",
        "constraint_ir",
        "runtime_fact_schema",
        "domain_pack",
        "semantic_commit_bundle",
        "compiled_authority_contract",
        "authority",
        "approval_record",
        "authority_bundle_v1",
        "publication_receipt_v1",
        "compatibility",
        "bundle_hash",
    }
    _exact(bundle, expected_bundle_fields, "domain policy authority bundle")
    if bundle["provenance_complete"] is not True:
        raise ValueError("domain policy authority bundle must declare complete provenance")
    if bundle["bundle_hash"] != artifact_hash(bundle, "bundle_hash"):
        raise ValueError("domain policy authority bundle hash does not match canonical content")
    pack = get_builtin_domain_pack(
        bundle["domain_pack"]["domain_pack_id"],
        bundle["domain_pack"]["domain_pack_version"],
    )
    if bundle["domain_pack"] != _pack_ref(pack):
        raise ValueError("domain policy authority bundle has a tampered domain-pack binding")
    validate_constraint_ir(bundle["constraint_ir"], domain_pack=pack)
    compatibility = validate_runtime_fact_compatibility(
        bundle["constraint_ir"], bundle["runtime_fact_schema"], domain_pack=pack
    )
    if not compatibility["compatible"]:
        raise ValueError("domain policy authority bundle runtime facts are incompatible")
    source = bundle["source_policy"]
    exact = base64.b64decode(source["source_bytes_base64"].encode("ascii"), validate=True)
    if bytes_sha256(exact) != source["snapshot_hash"]:
        raise ValueError("domain policy authority bundle source snapshot hash is invalid")
    for statement in bundle["source_statements"]:
        piece = exact[statement["start_byte"] : statement["end_byte"]]
        if bytes_sha256(piece) != statement["statement_hash"]:
            raise ValueError("domain policy authority bundle statement span or hash is invalid")
        if base64.b64encode(piece).decode("ascii") != statement["statement_bytes_base64"]:
            raise ValueError("domain policy authority bundle statement bytes do not match its span")
    interpretation = bundle["interpretation"]
    if interpretation["source_statements_hash"] != canonical_sha256(bundle["source_statements"]):
        raise ValueError("domain policy source statements hash is invalid")
    if interpretation["source_to_constraint_mappings_hash"] != canonical_sha256(
        bundle["source_to_constraint_mappings"]
    ):
        raise ValueError("domain policy source-to-constraint mapping hash is invalid")
    authority = bundle["authority"]
    authority_core = {
        key: authority[key]
        for key in ("authority_id", "authority_version", "authority_ref")
    }
    reconstructed_draft = {
        "schema_version": DOMAIN_POLICY_INTERPRETATION_V1,
        "source_policy": copy.deepcopy(source),
        "authority": copy.deepcopy(authority_core),
        "domain_pack": copy.deepcopy(bundle["domain_pack"]),
        "runtime_fact_schema": copy.deepcopy(bundle["runtime_fact_schema"]),
        "source_statements": copy.deepcopy(bundle["source_statements"]),
        "constraint_ir": copy.deepcopy(bundle["constraint_ir"]),
        "canonical_cnl_previews": copy.deepcopy(bundle["canonical_cnl_previews"]),
        "source_to_constraint_mappings": copy.deepcopy(
            bundle["source_to_constraint_mappings"]
        ),
        "mapping_decisions": copy.deepcopy(bundle["mapping_decisions"]),
        "status": _draft_status(
            bundle["source_statements"], bundle["constraint_ir"]["constraints"]
        ),
        "interpretation_id": interpretation["interpretation_id"],
        "draft_hash": interpretation["draft_hash"],
    }
    _reconstruct_domain_draft(reconstructed_draft)
    statement_index = {item["statement_id"]: item for item in bundle["source_statements"]}
    constraint_ids = {item["constraint_id"] for item in bundle["constraint_ir"]["constraints"]}
    for mapping in bundle["source_to_constraint_mappings"]:
        if mapping["statement_id"] not in statement_index or not set(mapping["constraint_ids"]) <= constraint_ids:
            raise ValueError("domain policy mapping references an unknown statement or constraint")
    for decision in bundle["mapping_decisions"]:
        _validate_mapping_decision_record(decision, bundle, pack)
    semantic = bundle["semantic_commit_bundle"]
    compiled = bundle["compiled_authority_contract"]
    if semantic["source_hash"] != source["snapshot_hash"]:
        raise ValueError("semantic commit is not bound to the exact domain-policy source")
    if compiled["compiled_from"]["semantic_commit_hash"] != semantic["semantic_commit_hash"]:
        raise ValueError("compiled contract is not bound to the semantic commit")
    if authority["authority_identity_hash"] != canonical_sha256(authority_core):
        raise ValueError("domain policy authority identity hash is invalid")
    if compiled["authority_ref"] != authority["authority_ref"]:
        raise ValueError("compiled contract authority identity is inconsistent")
    validate_authority_bundle(bundle["authority_bundle_v1"])
    validate_publication_receipt(
        bundle["authority_bundle_v1"], bundle["publication_receipt_v1"]
    )
    if bundle["authority_bundle_v1"].get("semantic_commit_bundle") != semantic:
        raise ValueError("embedded authority bundle semantic commit is inconsistent")
    if bundle["authority_bundle_v1"].get("compiled_authority_contract") != compiled:
        raise ValueError("embedded authority bundle compiled contract is inconsistent")
    approval = bundle["approval_record"]
    _exact(
        approval,
        {
            "approval_id",
            "approved_by",
            "approved_at",
            "approved_constraint_ir_hash",
            "approved_semantic_commit_hash",
            "approval_record_hash",
        },
        "domain policy approval record",
    )
    if approval["approval_record_hash"] != artifact_hash(approval, "approval_record_hash"):
        raise ValueError("domain policy approval record hash is invalid")
    if approval["approved_constraint_ir_hash"] != bundle["constraint_ir"]["ir_hash"]:
        raise ValueError("domain policy approval does not bind Constraint IR")
    if approval["approved_semantic_commit_hash"] != semantic["semantic_commit_hash"]:
        raise ValueError("domain policy approval does not bind the semantic commit")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != DOMAIN_POLICY_PUBLICATION_RECEIPT_V1:
        raise ValueError(f"receipt must be {DOMAIN_POLICY_PUBLICATION_RECEIPT_V1}")
    expected_receipt_fields = {
        "schema_version",
        "receipt_id",
        "publication_id",
        "authority_ref",
        "published_at",
        "published_by",
        "bundle_hash",
        "source_snapshot_hash",
        "domain_pack_hash",
        "constraint_ir_hash",
        "semantic_commit_hash",
        "semantic_commit_bundle_hash",
        "compiled_contract_hash",
        "embedded_authority_bundle_hash",
        "embedded_publication_receipt_hash",
        "provenance_complete",
        "receipt_hash",
    }
    _exact(receipt, expected_receipt_fields, "domain policy publication receipt")
    if receipt["receipt_hash"] != artifact_hash(receipt, "receipt_hash"):
        raise ValueError("domain policy publication receipt hash does not match canonical content")
    bindings = {
        "bundle_hash": bundle["bundle_hash"],
        "source_snapshot_hash": source["snapshot_hash"],
        "domain_pack_hash": pack["canonical_hash"],
        "constraint_ir_hash": bundle["constraint_ir"]["ir_hash"],
        "semantic_commit_hash": semantic["semantic_commit_hash"],
        "semantic_commit_bundle_hash": semantic["bundle_hash"],
        "compiled_contract_hash": compiled["contract_hash"],
        "embedded_authority_bundle_hash": canonical_sha256(bundle["authority_bundle_v1"]),
        "embedded_publication_receipt_hash": bundle["publication_receipt_v1"]["receipt_hash"],
        "authority_ref": authority["authority_ref"],
    }
    for field, expected in bindings.items():
        if receipt[field] != expected:
            raise ValueError(f"domain policy publication receipt {field} binding is invalid")
    if receipt["provenance_complete"] is not True:
        raise ValueError("domain policy publication receipt must declare complete provenance")
    manifest = bundle["authority_bundle_v1"]["publication_manifest"]
    if (
        receipt["publication_id"] != manifest["publication_id"]
        or receipt["published_at"] != manifest["published_at"]
        or receipt["published_by"] != manifest["published_by"]
    ):
        raise ValueError("domain policy publication receipt metadata is inconsistent")
    return {
        "valid": True,
        "provenance_complete": True,
        "bundle_hash": bundle["bundle_hash"],
        "receipt_hash": receipt["receipt_hash"],
    }


def _constraint_from_legacy_rule(
    rule: dict[str, Any], statement_text: str, pack: dict[str, Any]
) -> dict[str, Any]:
    rule_type = rule["rule_type"]
    if rule_type == "required_actor_role":
        role = rule["role"]
        if role not in pack["role_kinds"]:
            raise ValueError("direct role is outside the pack vocabulary")
        return _constraint(
            pack,
            action="modify",
            resource={"kind": "repository_change", "match": "any", "value": None},
            effect="require",
            acting_role=role,
        )
    if rule_type == "target":
        return _constraint(
            pack,
            action="modify",
            resource={"kind": "repository_path", "match": rule["match"], "value": rule["value"]},
            effect=rule["effect"],
        )
    if rule_type == "approval_threshold":
        role = rule["requires_role"]
        if role not in pack["role_kinds"]:
            raise ValueError("direct approval role is outside the pack vocabulary")
        action = _approval_action(statement_text)
        amount = _canonical_decimal(rule["value"])
        return _constraint(
            pack,
            action=action,
            resource={"kind": "financial_request", "match": "any", "value": None},
            effect="require",
            condition=_amount_condition(rule["operator"], amount),
            approvals=[{"minimum": 1, "role": role, "evidence_fact": "approval.count"}],
        )
    if rule_type == "separation_of_duties":
        return _constraint(
            pack,
            action="approve",
            resource={"kind": "financial_request", "match": "any", "value": None},
            effect="require",
            separation=[
                {
                    "roles": ["requester", "approver"],
                    "principal_facts": ["requester.principal_id", "approver.principal_id"],
                }
            ],
        )
    raise ValueError(f"legacy rule type is not lowerable by this domain pack: {rule_type}")


def _constraint_from_control(
    control: dict[str, Any], selections: dict[str, Any], pack: dict[str, Any]
) -> dict[str, Any]:
    produces = control["produces"]
    if produces == "acting_role_requirement":
        return _constraint(
            pack,
            action="modify",
            resource={"kind": "repository_change", "match": "any", "value": None},
            effect="require",
            acting_role=selections["role"],
        )
    if produces in {"exact_path_access", "prefix_path_access"}:
        match = "exact" if produces == "exact_path_access" else "prefix"
        return _constraint(
            pack,
            action="modify",
            resource={"kind": "repository_path", "match": match, "value": selections["path"]},
            effect=selections["effect"],
        )
    if produces == "approval_threshold":
        return _constraint(
            pack,
            action=selections["action"],
            resource={"kind": "financial_request", "match": "any", "value": None},
            effect="require",
            condition=_amount_condition(selections["operator"], selections["amount"]),
            approvals=[
                {"minimum": 1, "role": selections["role"], "evidence_fact": "approval.count"}
            ],
        )
    if produces == "requester_approver_separation":
        return _constraint(
            pack,
            action="approve",
            resource={"kind": "financial_request", "match": "any", "value": None},
            effect="require",
            separation=[
                {
                    "roles": ["requester", "approver"],
                    "principal_facts": ["requester.principal_id", "approver.principal_id"],
                }
            ],
        )
    raise ValueError("mapping control cannot produce a known constraint")


def _constraint(
    pack: dict[str, Any],
    *,
    action: str,
    resource: dict[str, Any],
    effect: str,
    acting_role: str | None = None,
    condition: dict[str, Any] | None = None,
    approvals: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    separation: list[dict[str, Any]] | None = None,
    exceptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    approvals = approvals or []
    evidence = evidence or []
    separation = separation or []
    exceptions = exceptions or []
    facts = {"actor.subject_kind", "proposal.action", "proposal.resource.kind"}
    if resource["match"] != "any":
        facts.add("proposal.resource.path")
    if acting_role:
        facts.add("actor.role")
    facts |= _condition_facts(condition)
    for item in approvals:
        facts.add(item["evidence_fact"])
    for item in evidence:
        facts.add(item["fact"])
    for item in separation:
        facts.update(item["principal_facts"])
    for item in exceptions:
        facts |= _condition_facts(item["condition"])
    return {
        "subject": {"kind": "subject_kind", "value": "agent"},
        "acting_role": {"kind": "role", "value": acting_role} if acting_role else None,
        "action": action,
        "resource": resource,
        "effect": effect,
        "condition": condition,
        "obligations": {
            "approvals": approvals,
            "evidence": evidence,
            "separation_of_duties": separation,
        },
        "exceptions": exceptions,
        "required_runtime_facts": sorted(facts),
    }


def _finalize_constraint(constraint: dict[str, Any]) -> dict[str, Any]:
    core = copy.deepcopy(constraint)
    core.pop("constraint_id", None)
    result = {"constraint_id": "constraint-" + canonical_sha256(core).removeprefix("sha256:"), **core}
    return result


def _build_ir(constraints: list[dict[str, Any]], pack: dict[str, Any]) -> dict[str, Any]:
    result = finalize_constraint_ir(
        {
            "schema_version": "constraint_ir.v1",
            "domain_pack": _pack_ref(pack),
            "runtime_fact_schema_hash": pack["runtime_fact_schema"]["schema_hash"],
            "constraints": copy.deepcopy(constraints),
        }
    )
    validate_constraint_ir(result, domain_pack=pack)
    return result


def _mapping_decision(
    draft: dict[str, Any],
    statement: dict[str, Any],
    control: dict[str, Any],
    selections: dict[str, Any],
    constraint: dict[str, Any],
    mapper_identity: str,
    mapped_at: str,
) -> dict[str, Any]:
    mapped_at = _utc(mapped_at, "mapped_at")
    _nonempty(mapper_identity, "mapper_identity")
    if len(mapper_identity) > 256:
        raise ValueError("mapper_identity must contain at most 256 characters")
    decision: dict[str, Any] = {
        "schema_version": POLICY_MAPPING_DECISION_V1,
        "source_document_hash": draft["source_policy"]["snapshot_hash"],
        "statement_id": statement["statement_id"],
        "start_byte": statement["start_byte"],
        "end_byte": statement["end_byte"],
        "domain_pack": copy.deepcopy(draft["domain_pack"]),
        "control_id": control["control_id"],
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
        "mapper_identity": mapper_identity,
        "mapped_at": mapped_at,
        "constraint_id": constraint["constraint_id"],
    }
    decision["decision_hash"] = artifact_hash(decision, "decision_hash")
    return decision


def _apply_canonical_decision(
    draft: dict[str, Any], decision: dict[str, Any], *, reconstructing: bool
) -> dict[str, Any]:
    result = copy.deepcopy(draft)
    pack = _pack_for_draft(result)
    statement = _statement(result, decision["statement_id"])
    if statement["classification"] != "requires_mapping":
        raise ValueError("mapping decision targets a statement that does not require mapping")
    control = mapping_control_index(pack).get(decision["control_id"])
    if control is None or control["control_id"] not in statement["available_mapping_control_ids"]:
        raise ValueError("mapping decision selects an unavailable control")
    selections = _validate_selections(control, decision["control_selections"])
    constraint = _finalize_constraint(_constraint_from_control(control, selections, pack))
    expected = _mapping_decision(
        result,
        statement,
        control,
        selections,
        constraint,
        decision["mapper_identity"],
        decision["mapped_at"],
    )
    if decision != expected:
        raise ValueError("mapping decision is modified or inconsistent with its bounded control")
    result["mapping_decisions"].append(copy.deepcopy(expected))
    if result["constraint_ir"] is None:
        constraints = [constraint]
    else:
        constraints = copy.deepcopy(result["constraint_ir"]["constraints"]) + [constraint]
    result["constraint_ir"] = _build_ir(constraints, pack)
    preview = {"constraint_id": constraint["constraint_id"], "preview": _cnl_preview(constraint)}
    result["canonical_cnl_previews"].append(preview)
    mapping = _source_mapping(
        statement, [constraint["constraint_id"]], "human_mapping", expected["decision_hash"]
    )
    result["source_to_constraint_mappings"].append(mapping)
    statement["classification"] = "mapped"
    statement["mapping_reason"] = None
    statement["available_mapping_control_ids"] = []
    result["status"] = _draft_status(result["source_statements"], constraints)
    result["draft_hash"] = artifact_hash(result, "draft_hash")
    if not reconstructing:
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
        for decision in draft["mapping_decisions"]:
            base = _apply_canonical_decision(base, decision, reconstructing=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("domain-policy interpretation cannot be reconstructed") from exc
    if base != draft:
        raise ValueError("domain-policy interpretation is modified or inconsistent")
    return base


def _validate_mapping_decision_record(
    decision: dict[str, Any], bundle: dict[str, Any], pack: dict[str, Any]
) -> None:
    if decision.get("schema_version") != POLICY_MAPPING_DECISION_V1:
        raise ValueError("domain policy bundle contains an unknown mapping decision schema")
    if decision.get("decision_hash") != artifact_hash(decision, "decision_hash"):
        raise ValueError("mapping decision canonical hash is invalid")
    if decision["source_document_hash"] != bundle["source_policy"]["snapshot_hash"]:
        raise ValueError("mapping decision source document hash is invalid")
    if decision["domain_pack"] != _pack_ref(pack):
        raise ValueError("mapping decision domain-pack binding is invalid")
    statements = {item["statement_id"]: item for item in bundle["source_statements"]}
    statement = statements.get(decision["statement_id"])
    if statement is None or (
        decision["start_byte"], decision["end_byte"]
    ) != (statement["start_byte"], statement["end_byte"]):
        raise ValueError("mapping decision statement identity or byte span is invalid")


def _lower_constraint(constraint: dict[str, Any]) -> dict[str, Any]:
    if constraint["exceptions"] or constraint["obligations"]["evidence"]:
        raise ValueError("repository-changes lowering does not support exceptions or evidence obligations")
    resource = constraint["resource"]
    obligations = constraint["obligations"]
    if constraint["acting_role"] is not None:
        rule = {
            "rule_type": "required_actor_role",
            "role": constraint["acting_role"]["value"],
        }
    elif resource["kind"] == "repository_path":
        rule = {
            "rule_type": "target",
            "effect": constraint["effect"],
            "match": resource["match"],
            "value": resource["value"],
        }
    elif obligations["approvals"]:
        comparison = constraint["condition"]["operands"][0]
        literal = comparison["literal"]["value"]
        numeric: int | float = int(literal) if "." not in literal else float(literal)
        rule = {
            "rule_type": "approval_threshold",
            "field": "amount",
            "operator": comparison["operator"],
            "value": numeric,
            "requires_role": obligations["approvals"][0]["role"],
        }
    elif obligations["separation_of_duties"]:
        rule = {
            "rule_type": "separation_of_duties",
            "roles": copy.deepcopy(obligations["separation_of_duties"][0]["roles"]),
        }
    else:
        raise ValueError("Constraint IR concept is not supported by repository-changes lowering")
    rule["rule_id"] = "rule-" + canonical_sha256(rule).removeprefix("sha256:")
    return rule


def _cnl_preview(constraint: dict[str, Any]) -> str:
    subject = constraint["subject"]["value"]
    resource = constraint["resource"]
    resource_text = f"{resource['kind']}:{resource['match']}"
    if resource["value"] is not None:
        resource_text += f' "{resource["value"]}"'
    if constraint["acting_role"]:
        return (
            f"REQUIRE {subject} ACTING AS {constraint['acting_role']['value']} TO "
            f"{constraint['action']} {resource_text}."
        )
    approvals = constraint["obligations"]["approvals"]
    if approvals:
        comparison = constraint["condition"]["operands"][0]
        literal = comparison["literal"]
        return (
            f"REQUIRE {approvals[0]['role']} APPROVAL FOR {subject} TO {constraint['action']} "
            f"{resource_text} WHEN ALL({comparison['fact']} {comparison['operator']} "
            f"{literal['type']}(\"{literal['value']}\", {literal['unit']}))."
        )
    separation = constraint["obligations"]["separation_of_duties"]
    if separation:
        return (
            f"REQUIRE SEPARATE PRINCIPALS FOR {', '.join(separation[0]['roles'])} "
            f"WHEN {subject} {constraint['action']} {resource_text}."
        )
    return f"{constraint['effect'].upper()} {subject} TO {constraint['action']} {resource_text}."


def _validate_selections(
    control: dict[str, Any], selections: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(selections, dict):
        raise ValueError("mapping selections must be an object")
    schema = control["selection_schema"]
    _exact(selections, set(schema), "mapping selections")
    result = copy.deepcopy(selections)
    for name, field in schema.items():
        value = result[name]
        if field["type"] == "enum":
            if value not in field["enum"]:
                raise ValueError(f"mapping selection {name} is outside the control's enum")
        elif field["type"] == "decimal":
            if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
                raise ValueError(f"mapping selection {name} must be a canonical decimal string")
        elif field["type"] == "repository_path":
            # Full path validation occurs through strict Constraint IR validation.
            if not isinstance(value, str) or not value:
                raise ValueError(f"mapping selection {name} must be a non-empty path")
    return result


def _source_mapping(
    statement: dict[str, Any],
    constraint_ids: list[str],
    mode: str,
    decision_hash: str | None,
) -> dict[str, Any]:
    core = {
        "statement_id": statement["statement_id"],
        "start_byte": statement["start_byte"],
        "end_byte": statement["end_byte"],
        "constraint_ids": constraint_ids,
        "mode": mode,
        "mapping_decision_hash": decision_hash,
    }
    return {
        "mapping_id": "constraint-mapping-" + canonical_sha256(core).removeprefix("sha256:"),
        **core,
    }


def _draft_status(
    statements: list[dict[str, Any]], constraints: list[dict[str, Any]]
) -> dict[str, Any]:
    requires = sum(item["classification"] == "requires_mapping" for item in statements)
    return {
        "statement_classification_complete": True,
        "requires_mapping_count": requires,
        "enforceable_constraint_count": len(constraints),
        "ready_for_finalization": requires == 0 and bool(constraints),
        "publication_ready": False,
    }


def _pack_ref(pack: dict[str, Any]) -> dict[str, str]:
    return {
        "domain_pack_id": pack["domain_pack_id"],
        "domain_pack_version": pack["domain_pack_version"],
        "domain_pack_hash": pack["canonical_hash"],
    }


def _pack_for_draft(draft: dict[str, Any]) -> dict[str, Any]:
    ref = draft["domain_pack"]
    pack = get_builtin_domain_pack(ref["domain_pack_id"], ref["domain_pack_version"])
    if ref != _pack_ref(pack):
        raise ValueError("domain-policy interpretation has a tampered domain-pack binding")
    if draft["runtime_fact_schema"] != pack["runtime_fact_schema"]:
        raise ValueError("domain-policy interpretation has a tampered runtime fact schema")
    return pack


def _statement(draft: dict[str, Any], statement_id: str) -> dict[str, Any]:
    matches = [item for item in draft["source_statements"] if item["statement_id"] == statement_id]
    if len(matches) != 1:
        raise ValueError("statement_id does not identify one source statement")
    return matches[0]


def _amount_condition(operator: str, amount: str) -> dict[str, Any]:
    return {
        "kind": "group",
        "operator": "all",
        "operands": [
            {
                "kind": "comparison",
                "operator": operator,
                "fact": "request.amount",
                "literal": {"type": "decimal", "value": amount, "unit": "USD"},
            }
        ],
    }


def _condition_facts(condition: dict[str, Any] | None) -> set[str]:
    if condition is None:
        return set()
    if condition["kind"] == "comparison":
        return {condition["fact"]}
    return {fact for operand in condition["operands"] for fact in _condition_facts(operand)}


def _approval_action(text: str) -> str:
    first = text.split(maxsplit=1)[0].lower()
    return {
        "transfers": "transfer",
        "purchases": "purchase",
        "payments": "payment",
        "invoices": "invoice",
        "requests": "request",
    }.get(first, "transfer")


def _canonical_decimal(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return format(value, "f").rstrip("0").rstrip(".")


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


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        actual = set(value) if isinstance(value, dict) else set()
        raise ValueError(
            f"{label} fields are invalid; unknown={sorted(actual - expected)}, "
            f"missing={sorted(expected - actual)}"
        )
