"""Native v4 development publication with provider-independent reconstruction."""

from __future__ import annotations

import copy
import re

from governance_ledger import policy_translation_publication as public
from governance_ledger.action_policy import (
    CONTRACT_SCHEMA, compile_verified_action_policy, lower_action_constraints,
    require_development_opt_in, verify_action_compiler_output,
)
from governance_ledger.authority_contract import compute_contract_hash
from governance_ledger.constraint_ir import artifact_hash, validate_runtime_fact_compatibility
from governance_ledger.domain_packs import get_builtin_domain_pack
from governance_ledger.domain_policy import _build_ir, _pack_ref
from governance_ledger.publication_provenance import canonical_sha256
from governance_ledger.semantics.compiler import build_semantic_commit_bundle

BUNDLE_SCHEMA = "authority_bundle.v4"
RECEIPT_SCHEMA = "publication_receipt.v4"


def _reconstruct(source, authority, commitment, *, approved_by, approved_at,
                 committed_by, committed_at, publication_id, published_by, published_at,
                 raw_output=None):
    """Derive every public artifact from source-bound individually confirmed controls.

    Verification consumes retained compiler output and independently compares it to
    approved semantics. It needs neither a provider nor a compiler installation.
    """
    require_development_opt_in()
    if commitment["capability_catalog"]["catalog_version"] != "2.0.0":
        raise ValueError("v4 requires catalog 2.0.0; historical authorities cannot upgrade")
    constraints = public._validate_policy_translation_commitment(
        source, authority, commitment, approval_time=approved_at)
    for resolution in commitment["customer_bindings"]:
        public._nonempty(resolution["confirmed_by"], "binding confirmed_by")
    for clause in commitment["clauses"]:
        decision = clause["human_coverage_decision"]
        public._nonempty(decision["confirmed_by"], "coverage confirmed_by")
        if type(decision["acknowledged_unrepresented"]) is not bool:
            raise ValueError("coverage acknowledgment must be Boolean")
        for record in clause["controls"]:
            confirmation = record["human_confirmation"]
            public._nonempty(confirmation["confirmed_by"], "control confirmed_by")
            public._not_after(confirmation["confirmed_at"], decision["confirmed_at"], "control confirmation")
    pack = get_builtin_domain_pack("repository-changes", "2.0.0")
    ir = _build_ir(constraints, pack)
    runtime = copy.deepcopy(pack["runtime_fact_schema"])
    if not validate_runtime_fact_compatibility(ir, runtime, domain_pack=pack)["compatible"]:
        raise ValueError("action policy runtime facts are incompatible")
    policy = lower_action_constraints(authority, constraints)
    binding = public._compiler_binding(pack, commitment)
    normalized = {
        "authority": copy.deepcopy(authority),
        "canonical_compiler_input": policy,
        "policy_translation_commitment": {
            "commitment_id": commitment["commitment_id"],
            "commitment_hash": commitment["commitment_hash"],
            "compiler_binding_hash": binding["compiler_binding_hash"],
        },
    }
    semantic = build_semantic_commit_bundle({
        "schema_version": "governance_semantic_reconciliation.v1",
        "source_id": source["source_policy_id"], "source_hash": source["snapshot_hash"],
        "extraction_id": commitment["commitment_id"],
        "operator_interpretation_decisions": [copy.deepcopy(c["human_coverage_decision"]) for c in commitment["clauses"]],
        "unresolved_ambiguities": [], "semantic_conflicts": [],
        "interpretation_completeness_posture": "complete",
        "final_normalized_semantic_meaning": normalized,
    }, committed_by=public._nonempty(committed_by, "committed_by"),
       committed_at=public._utc(committed_at, "committed_at"))
    if raw_output is None:
        raw_output = compile_verified_action_policy(policy)
    verify_action_compiler_output(raw_output, policy)
    compiled = {
        "schema_version": CONTRACT_SCHEMA,
        "contract_id": policy["contract_id"], "contract_version": policy["contract_version"],
        "authority_ref": authority["authority_ref"],
        "action_requirements": copy.deepcopy(raw_output["action_requirements"]),
        "compiler_output": copy.deepcopy(raw_output),
        "provenance": {
            "source_snapshot_hash": source["snapshot_hash"],
            "policy_translation_commitment_hash": commitment["commitment_hash"],
            "constraint_ir_hash": ir["ir_hash"], "domain_pack_hash": pack["canonical_hash"],
            "runtime_fact_schema_hash": runtime["schema_hash"],
            "compiler_binding_hash": binding["compiler_binding_hash"],
            "semantic_commit_hash": semantic["semantic_commit_hash"],
        },
    }
    compiled["contract_hash"] = "sha256:" + compute_contract_hash(compiled)
    validate_compiled_authority_contract_v3(compiled)
    approval = public._publication_approval_record(commitment, ir, semantic,
        approved_by=approved_by, approved_at=approved_at)
    published_at = public._utc(published_at, "published_at")
    manifest = public._publication_manifest(source, compiled,
        public._identity(publication_id, "publication_id"),
        public._nonempty(published_by, "published_by"), published_at)
    public._validate_chronology(commitment, approval, semantic, published_at)
    authority_record = {**authority, "authority_identity_hash": canonical_sha256(authority)}
    provenance = public._provenance_bindings(source, commitment, ir, runtime, pack,
        binding, semantic, compiled, authority_record, approval, manifest)
    bundle = {
        "schema_version": BUNDLE_SCHEMA, "provenance_complete": True,
        "source_policy": copy.deepcopy(source), "policy_translation_commitment": copy.deepcopy(commitment),
        "constraint_ir": ir, "runtime_fact_schema": runtime, "domain_pack": _pack_ref(pack),
        "compiler_binding": binding, "semantic_commit_bundle": semantic,
        "compiled_authority_contract": compiled, "authority": authority_record,
        "approval_record": approval, "publication_manifest": manifest, "provenance_bindings": provenance,
    }
    bundle["bundle_hash"] = artifact_hash(bundle, "bundle_hash")
    return bundle, policy


def _receipt(bundle):
    manifest = bundle["publication_manifest"]
    compiled = bundle["compiled_authority_contract"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "receipt_id": "receipt-v4-" + bundle["bundle_hash"].removeprefix("sha256:"),
        "publication_id": manifest["publication_id"],
        "authority_ref": bundle["authority"]["authority_ref"],
        "published_at": manifest["published_at"], "published_by": manifest["published_by"],
        "bundle_hash": bundle["bundle_hash"],
        **copy.deepcopy(bundle["provenance_bindings"]),
        "domain_pack": copy.deepcopy(bundle["domain_pack"]),
        "compiled_contract_ref": f"{compiled['contract_id']}@{compiled['contract_version']}",
        "provenance_complete": True,
    }
    receipt["receipt_hash"] = artifact_hash(receipt, "receipt_hash")
    return receipt


def finalize_policy_translation_authority_v4(proposal, confirmation, approval, *,
        committed_by, committed_at, publication_id, published_by, published_at):
    require_development_opt_in()
    commitment = public.build_policy_translation_commitment(proposal, confirmation, approval)
    bundle, policy = _reconstruct(proposal["source_policy"], proposal["authority"], commitment,
        approved_by=approval["approved_by"], approved_at=approval["approved_at"],
        committed_by=committed_by, committed_at=committed_at, publication_id=publication_id,
        published_by=published_by, published_at=published_at)
    receipt = _receipt(bundle)
    return {
        "result_type": "development_action_policy_publication",
        "status": {"development_publication_ready": True, "runtime_activation_ready": False},
        "canonical_compiler_input": policy,
        "compiler_output": copy.deepcopy(bundle["compiled_authority_contract"]["compiler_output"]),
        "compiled_authority_contract": copy.deepcopy(bundle["compiled_authority_contract"]),
        "authority_bundle": bundle, "publication_receipt": receipt,
        "authority_bundle_validation": validate_authority_bundle_v4(bundle),
        "publication_receipt_validation": validate_publication_receipt_v4(bundle, receipt),
        "private_translation_evidence_required": False,
    }


def validate_compiled_authority_contract_v3(contract):
    require_development_opt_in()
    public._exact(contract, {"schema_version", "contract_id", "contract_version", "authority_ref",
        "action_requirements", "compiler_output", "provenance", "contract_hash"}, CONTRACT_SCHEMA)
    if contract["schema_version"] != CONTRACT_SCHEMA:
        raise ValueError("unknown or mixed compiled authority schema")
    public._identity(contract["contract_id"], "contract_id")
    if not isinstance(contract["contract_version"], str) or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", contract["contract_version"]):
        raise ValueError("contract_version must be canonical semver")
    if contract["authority_ref"] != f"{contract['contract_id']}@{contract['contract_version']}":
        raise ValueError("compiled authority identity mismatch")
    # Build IR-shaped constraints to validate the entire closed action surface without
    # invoking the compiler. Bundle validation additionally checks approved source.
    from governance_ledger.domain_policy import _constraint, _finalize_constraint
    blocks = contract["action_requirements"]
    if not isinstance(blocks, dict) or not blocks or set(blocks) - {"create", "modify"}:
        raise ValueError("invalid compiled action requirements")
    constraints = []
    for action, block in blocks.items():
        public._exact(block, {"required_role", "allow", "deny"}, "action block")
        if block["required_role"] is not None:
            constraints.append(_finalize_constraint(_constraint(action=action, effect="require",
                acting_role=block["required_role"], resource={"kind": "repository_change", "match": "any", "value": None})))
        for effect in ("allow", "deny"):
            if not isinstance(block[effect], list):
                raise ValueError("action selectors must be arrays")
            for rule in block[effect]:
                public._exact(rule, {"match", "value"}, "action selector")
                constraints.append(_finalize_constraint(_constraint(action=action, effect=effect,
                    resource={"kind": "repository_path", **rule})))
    pack = get_builtin_domain_pack("repository-changes", "2.0.0")
    _build_ir(constraints, pack)
    policy = lower_action_constraints({"authority_id": contract["contract_id"],
        "authority_version": contract["contract_version"]}, constraints)
    # Empty blocks are meaningful non-grants and remain present.
    for action in blocks:
        policy["action_requirements"].setdefault(action, {"required_role": None, "allow": [], "deny": []})
    verify_action_compiler_output(contract["compiler_output"], policy)
    if contract["action_requirements"] != contract["compiler_output"]["action_requirements"]:
        raise ValueError("compiled action surface differs from raw compiler output")
    public._exact(contract["provenance"], {"source_snapshot_hash", "policy_translation_commitment_hash",
        "constraint_ir_hash", "domain_pack_hash", "runtime_fact_schema_hash", "compiler_binding_hash",
        "semantic_commit_hash"}, "compiled provenance")
    if any(not isinstance(value, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", value)
           for value in contract["provenance"].values()):
        raise ValueError("invalid compiled provenance hash")
    if contract["contract_hash"] != "sha256:" + compute_contract_hash(contract):
        raise ValueError("compiled authority canonical hash mismatch")
    return {"schema_version": CONTRACT_SCHEMA, "valid": True, "contract_hash": contract["contract_hash"]}


def validate_authority_bundle_v4(bundle):
    require_development_opt_in()
    if not isinstance(bundle, dict) or bundle.get("schema_version") != BUNDLE_SCHEMA:
        raise ValueError("expected native authority_bundle.v4")
    try:
        authority = {key: bundle["authority"][key] for key in ("authority_id", "authority_version", "authority_ref")}
        approval, semantic, manifest = bundle["approval_record"], bundle["semantic_commit_bundle"], bundle["publication_manifest"]
        compiled = bundle["compiled_authority_contract"]
        validate_compiled_authority_contract_v3(compiled)
        expected, _ = _reconstruct(bundle["source_policy"], authority, bundle["policy_translation_commitment"],
            approved_by=approval["approved_by"], approved_at=approval["approved_at"],
            committed_by=semantic["committed_by"], committed_at=semantic["committed_at"],
            publication_id=manifest["publication_id"], published_by=manifest["published_by"],
            published_at=manifest["published_at"], raw_output=compiled["compiler_output"])
        if bundle != expected:
            raise ValueError("v4 bundle differs from independent source/confirmation reconstruction")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("malformed native v4 bundle") from exc
    return {"schema_version": BUNDLE_SCHEMA, "valid": True, "provenance_complete": True,
            "bundle_hash": bundle["bundle_hash"], "runtime_activation_ready": False}


def validate_publication_receipt_v4(bundle, receipt):
    status = validate_authority_bundle_v4(bundle)
    if receipt != _receipt(bundle):
        raise ValueError("v4 receipt is inconsistent with native v4 bundle")
    return {**status, "schema_version": RECEIPT_SCHEMA, "receipt_hash": receipt["receipt_hash"]}
