from __future__ import annotations

import base64
import json
from pathlib import Path

import jsonschema
import pytest

from governance_ledger.publication_provenance import (
    CUSTOMER_POLICY_PROFILE,
    LEGACY_INCOMPLETE_PROFILE,
    bytes_sha256,
    canonical_json,
    canonical_sha256,
    classify_authority_bundle_provenance,
    source_statement_id,
    statement_mapping_id,
    validate_authority_bundle,
    validate_publication_receipt,
)
from governance_ledger.semantics.compiler import (
    build_semantic_commit_bundle,
    compile_semantic_commit_bundle,
)
from governance_ledger.semantics.preview import build_governance_impact_preview
from governance_ledger.semantics.publication import (
    build_authority_bundle,
    build_publication_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/provenance_complete"


def test_valid_provenance_complete_publication_binds_distinct_versions() -> None:
    bundle, receipt = _complete_publication()

    assert validate_authority_bundle(bundle) == {
        "profile": CUSTOMER_POLICY_PROFILE,
        "provenance_complete": True,
    }
    assert validate_publication_receipt(bundle, receipt)["provenance_complete"] is True
    assert bundle["customer_policy_provenance"]["source_policy"]["source_policy_ref"] == "repository-change-policy@rev-17"
    assert bundle["authority_ref"] == "repository-change-authority@6.0.0"
    assert bundle["customer_policy_provenance"]["version_binding"]["relationship"] == "publishes_as"
    assert receipt["provenance_bindings"]["source_policy_ref"] != receipt["provenance_bindings"]["authority_ref"]


@pytest.mark.parametrize(
    "path",
    [
        "provenance_profile",
        "customer_policy_provenance",
        "customer_policy_provenance.profile",
        "customer_policy_provenance.provenance_complete",
        "customer_policy_provenance.source_policy",
        "customer_policy_provenance.source_policy.source_policy_id",
        "customer_policy_provenance.source_policy.source_revision",
        "customer_policy_provenance.source_policy.snapshot_hash",
        "customer_policy_provenance.source_statements",
        "customer_policy_provenance.source_statements.0.statement_id",
        "customer_policy_provenance.source_statements.0.start_byte",
        "customer_policy_provenance.source_statements.0.end_byte",
        "customer_policy_provenance.interpretation",
        "customer_policy_provenance.interpretation.mapping_hash",
        "customer_policy_provenance.resolution",
        "customer_policy_provenance.resolution.resolution_hash",
        "customer_policy_provenance.approval_record",
        "customer_policy_provenance.approval_record.approval_record_hash",
        "customer_policy_provenance.version_binding",
        "customer_policy_provenance.version_binding.binding_hash",
        "semantic_commit_bundle",
        "compiled_authority_contract",
        "immutable_inputs.provenance_profile",
        "immutable_inputs.provenance_complete",
        "immutable_inputs.source_policy_id",
        "immutable_inputs.source_revision",
        "immutable_inputs.source_policy_ref",
        "immutable_inputs.source_snapshot_hash",
        "immutable_inputs.source_statements_hash",
        "immutable_inputs.interpretation_id",
        "immutable_inputs.mapping_hash",
        "immutable_inputs.resolution_id",
        "immutable_inputs.resolution_hash",
        "immutable_inputs.approval_id",
        "immutable_inputs.approval_record_hash",
        "immutable_inputs.semantic_commit_id",
        "immutable_inputs.semantic_commit_hash",
        "immutable_inputs.compiled_contract_id",
        "immutable_inputs.compiled_contract_version",
        "immutable_inputs.compiled_contract_ref",
        "immutable_inputs.compiled_contract_hash",
        "immutable_inputs.authority_id",
        "immutable_inputs.authority_version",
        "immutable_inputs.authority_ref",
        "immutable_inputs.authority_identity_hash",
        "immutable_inputs.version_binding_hash",
    ],
)
def test_complete_profile_rejects_every_missing_required_component(path: str) -> None:
    bundle, _ = _complete_publication()
    _delete_path(bundle, path)

    with pytest.raises(ValueError, match="required|missing|inconsistent|completeness"):
        validate_authority_bundle(bundle)


@pytest.mark.parametrize(
    "path",
    [
        "customer_policy_provenance.source_policy.snapshot_hash",
        "customer_policy_provenance.source_statements.0.statement_hash",
        "customer_policy_provenance.interpretation.mapping_hash",
        "customer_policy_provenance.resolution.resolution_hash",
        "customer_policy_provenance.approval_record.approval_record_hash",
        "customer_policy_provenance.version_binding.binding_hash",
        "semantic_commit_bundle.semantic_commit_hash",
        "compiled_authority_contract.contract_hash",
        "immutable_inputs.source_snapshot_hash",
        "immutable_inputs.source_statements_hash",
        "immutable_inputs.mapping_hash",
        "immutable_inputs.resolution_hash",
        "immutable_inputs.approval_record_hash",
        "immutable_inputs.semantic_commit_hash",
        "immutable_inputs.compiled_contract_hash",
        "immutable_inputs.authority_identity_hash",
        "immutable_inputs.version_binding_hash",
    ],
)
def test_complete_profile_rejects_each_individual_hash_mismatch(path: str) -> None:
    bundle, _ = _complete_publication()
    _set_path(bundle, path, "sha256:" + "0" * 64)

    with pytest.raises(ValueError, match="hash|inconsistent"):
        validate_authority_bundle(bundle)


def test_source_byte_tampering_fails_closed() -> None:
    bundle, _ = _complete_publication()
    source = bundle["customer_policy_provenance"]["source_policy"]
    tampered = bytearray(base64.b64decode(source["source_bytes_base64"]))
    tampered[0] ^= 1
    source["source_bytes_base64"] = base64.b64encode(tampered).decode("ascii")

    with pytest.raises(ValueError, match="source snapshot_hash"):
        validate_authority_bundle(bundle)


def test_unexplained_or_unbound_version_relationship_fails() -> None:
    bundle, _ = _complete_publication()
    bundle["customer_policy_provenance"]["version_binding"]["relationship"] = ""

    with pytest.raises(ValueError, match="relationship"):
        validate_authority_bundle(bundle)

    bundle, _ = _complete_publication()
    bundle["customer_policy_provenance"]["version_binding"]["authority_ref"] = "repository-change-authority@rev-17"
    with pytest.raises(ValueError, match="version authority_ref"):
        validate_authority_bundle(bundle)


@pytest.mark.parametrize(
    "path,new_value",
    [
        ("customer_policy_provenance.interpretation.statement_rule_mappings.0.rule_ids.0", "rule-role-maintainer-x"),
        ("customer_policy_provenance.resolution.ambiguity_resolutions", [{"ambiguity_id": "a-1", "resolution": "explicit"}]),
        ("customer_policy_provenance.approval_record.approved_by", "mallory@example.com"),
        ("semantic_commit_bundle.committed_semantic_meaning.confirmed_rules.0.effect", "deny"),
        ("compiled_authority_contract.authority_ref", "other@6.0.0"),
        ("publication_meaning", "tampered bundle byte"),
    ],
)
def test_receipt_verification_detects_changed_publication_inputs(path: str, new_value: object) -> None:
    bundle, receipt = _complete_publication()
    _set_path(bundle, path, new_value)

    with pytest.raises(ValueError):
        validate_publication_receipt(bundle, receipt)


@pytest.mark.parametrize(
    "path",
    [
        "provenance_bindings.source_snapshot_hash",
        "provenance_bindings.provenance_profile",
        "provenance_bindings.provenance_complete",
        "provenance_bindings.source_policy_id",
        "provenance_bindings.source_revision",
        "provenance_bindings.source_policy_ref",
        "provenance_bindings.interpretation_id",
        "provenance_bindings.mapping_hash",
        "provenance_bindings.resolution_id",
        "provenance_bindings.resolution_hash",
        "provenance_bindings.approval_id",
        "provenance_bindings.approval_record_hash",
        "provenance_bindings.semantic_commit_id",
        "provenance_bindings.semantic_commit_hash",
        "provenance_bindings.compiled_contract_id",
        "provenance_bindings.compiled_contract_version",
        "provenance_bindings.compiled_contract_ref",
        "provenance_bindings.compiled_contract_hash",
        "provenance_bindings.authority_id",
        "provenance_bindings.authority_version",
        "provenance_bindings.authority_ref",
        "provenance_bindings.authority_identity_hash",
        "provenance_bindings.version_binding_hash",
        "bundle_hash",
        "semantic_commit_hash",
        "compiled_contract_hash",
        "receipt_id",
        "immutable_inputs.bundle_hash",
        "receipt_hash",
    ],
)
def test_receipt_rejects_each_changed_bound_hash(path: str) -> None:
    bundle, receipt = _complete_publication()
    _set_path(receipt, path, "sha256:" + "0" * 64)

    with pytest.raises(ValueError, match="receipt|inconsistent"):
        validate_publication_receipt(bundle, receipt)


def test_complete_publication_generation_is_deterministic() -> None:
    first_bundle, first_receipt = _complete_publication()
    second_bundle, second_receipt = _complete_publication()

    assert first_bundle == second_bundle
    assert first_receipt == second_receipt
    assert canonical_sha256(first_bundle) == canonical_sha256(second_bundle)
    assert first_receipt["receipt_hash"] == second_receipt["receipt_hash"]
    assert first_bundle["semantic_commit_hash"] == second_bundle["semantic_commit_hash"]
    assert first_bundle["compiled_contract_hash"] == second_bundle["compiled_contract_hash"]


def test_legacy_bundles_are_truthfully_classified_without_inference() -> None:
    legacy = json.loads(
        (ROOT / "tests/fixtures/golden_path/contracts/finance-policy-1.0.0.authority-bundle.json").read_text(
            encoding="utf-8"
        )
    )

    assert "provenance_profile" not in legacy
    assert classify_authority_bundle_provenance(legacy) == LEGACY_INCOMPLETE_PROFILE
    assert validate_authority_bundle(legacy) == {
        "profile": LEGACY_INCOMPLETE_PROFILE,
        "provenance_complete": False,
    }
    legacy_receipt = json.loads(
        (ROOT / "tests/fixtures/golden_path/contracts/finance-policy-1.0.0.publication-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    bundle_schema = json.loads((ROOT / "schemas/authority_bundle.v1.json").read_text(encoding="utf-8"))
    receipt_schema = json.loads((ROOT / "schemas/publication_receipt.v1.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(bundle_schema).validate(legacy)
    jsonschema.Draft202012Validator(receipt_schema).validate(legacy_receipt)


def test_schema_validation_and_canonical_serialization() -> None:
    bundle, receipt = _complete_publication()
    bundle_schema = json.loads((ROOT / "schemas/authority_bundle.v1.json").read_text(encoding="utf-8"))
    receipt_schema = json.loads((ROOT / "schemas/publication_receipt.v1.json").read_text(encoding="utf-8"))
    semantic_schema = json.loads((ROOT / "schemas/semantic_commit_bundle.v1.json").read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(bundle_schema).validate(bundle)
    jsonschema.Draft202012Validator(receipt_schema).validate(receipt)
    jsonschema.Draft202012Validator(semantic_schema).validate(bundle["semantic_commit_bundle"])
    assert canonical_json({"z": 1, "a": "café"}) == '{"a":"caf\\u00e9","z":1}'
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def _complete_publication() -> tuple[dict, dict]:
    fixture = json.loads((FIXTURE_ROOT / "publication-inputs.json").read_text(encoding="utf-8"))
    source_bytes = base64.b64decode(
        (FIXTURE_ROOT / "repository-change-policy.base64").read_text(encoding="ascii").strip(),
        validate=True,
    )
    source_policy_id = fixture["source_policy"]["source_policy_id"]
    source_revision = fixture["source_policy"]["source_revision"]
    source_ref = f"{source_policy_id}@{source_revision}"
    source_hash = bytes_sha256(source_bytes)
    source_statements = []
    cursor = 0
    for statement_bytes in source_bytes.splitlines(keepends=True):
        start = cursor
        end = cursor + len(statement_bytes)
        statement_hash = bytes_sha256(statement_bytes)
        source_statements.append(
            {
                "statement_id": source_statement_id(
                    source_policy_id=source_policy_id,
                    source_revision=source_revision,
                    start_byte=start,
                    end_byte=end,
                    statement_hash=statement_hash,
                ),
                "start_byte": start,
                "end_byte": end,
                "statement_bytes_base64": base64.b64encode(statement_bytes).decode("ascii"),
                "statement_hash": statement_hash,
            }
        )
        cursor = end

    mappings = []
    for statement, mapped_rules in zip(
        source_statements,
        fixture["interpretation"]["statement_rule_ids"],
    ):
        statement_ids = [statement["statement_id"]]
        mappings.append(
            {
                "mapping_id": statement_mapping_id(statement_ids, mapped_rules),
                "statement_ids": statement_ids,
                "rule_ids": mapped_rules,
            }
        )
    interpretation = {
        "interpretation_id": fixture["interpretation"]["interpretation_id"],
        "statement_rule_mappings": mappings,
        "mapping_hash": canonical_sha256(mappings),
    }
    resolution = {
        "resolution_id": fixture["resolution"]["resolution_id"],
        "ambiguity_resolutions": fixture["resolution"]["ambiguity_resolutions"],
        "resolution_hash": canonical_sha256(fixture["resolution"]["ambiguity_resolutions"]),
    }
    semantic_bindings = {
        "source_policy_ref": source_ref,
        "source_snapshot_hash": source_hash,
        "source_statements_hash": canonical_sha256(source_statements),
        "interpretation_id": interpretation["interpretation_id"],
        "mapping_hash": interpretation["mapping_hash"],
        "resolution_id": resolution["resolution_id"],
        "resolution_hash": resolution["resolution_hash"],
    }
    reconciliation = {
        "schema_version": "governance_semantic_reconciliation.v1",
        "source_id": source_policy_id,
        "source_hash": source_hash,
        "extraction_id": "extraction-repository-change-001",
        "operator_interpretation_decisions": [],
        "unresolved_ambiguities": [],
        "semantic_conflicts": [],
        "interpretation_completeness_posture": "complete",
        "final_normalized_semantic_meaning": {
            "contract_id": fixture["authority"]["authority_id"],
            "contract_version": fixture["authority"]["authority_version"],
            "governed_targets": ["README.md", "deployment/"],
            "governed_operations": ["modify"],
            "approver_roles": ["repository-maintainer"],
            "confirmed_rules": fixture["confirmed_rules"],
        },
    }
    semantic_commit = build_semantic_commit_bundle(
        reconciliation,
        committed_by=fixture["semantic_commit"]["committed_by"],
        committed_at=fixture["semantic_commit"]["committed_at"],
        provenance_bindings=semantic_bindings,
    )
    compiled_contract = compile_semantic_commit_bundle(semantic_commit)
    approval_record = {
        "approval_id": fixture["approval"]["approval_id"],
        "approved_by": fixture["approval"]["approved_by"],
        "approved_at": fixture["approval"]["approved_at"],
        "approved_semantic_commit_hash": semantic_commit["semantic_commit_hash"],
    }
    approval_record["approval_record_hash"] = canonical_sha256(approval_record)
    authority_ref = compiled_contract["authority_ref"]
    version_binding = {
        "source_policy_ref": source_ref,
        "authority_ref": authority_ref,
        "relationship": fixture["version_relationship"],
    }
    version_binding["binding_hash"] = canonical_sha256(version_binding)
    provenance = {
        "profile": CUSTOMER_POLICY_PROFILE,
        "provenance_complete": True,
        "source_policy": {
            "source_policy_id": source_policy_id,
            "source_revision": source_revision,
            "source_policy_ref": source_ref,
            "content_encoding": "base64",
            "source_bytes_base64": base64.b64encode(source_bytes).decode("ascii"),
            "snapshot_hash": source_hash,
        },
        "source_statements": source_statements,
        "interpretation": interpretation,
        "resolution": resolution,
        "approval_record": approval_record,
        "version_binding": version_binding,
    }
    manifest = {
        "schema_version": "publication_manifest.v1",
        "publication_id": fixture["publication"]["publication_id"],
        "published_at": fixture["publication"]["published_at"],
        "published_by": fixture["publication"]["published_by"],
        "contracts": [
            {
                "contract_id": compiled_contract["contract_id"],
                "contract_version": compiled_contract["contract_version"],
                "contract_hash": compiled_contract["contract_hash"],
                "source_hash": source_hash,
                "path": "contracts/repository-change-authority-6.0.0.contract.json",
            }
        ],
        "reviews": [{"path": "reviews/repository-change-policy.review.json"}],
        "snapshots": [{"path": "snapshots/repository-change-policy.json"}],
    }
    bundle = build_authority_bundle(
        authority_contract=compiled_contract,
        publication_manifest=manifest,
        governance_impact_preview=build_governance_impact_preview(compiled_contract),
        semantic_commit_bundle=semantic_commit,
        compiled_authority_contract=compiled_contract,
        customer_policy_provenance=provenance,
    )
    receipt = build_publication_receipt(
        authority_bundle=bundle,
        published_at=manifest["published_at"],
    )
    return bundle, receipt


def _path_parts(path: str) -> list[str | int]:
    return [int(part) if part.isdigit() else part for part in path.split(".")]


def _delete_path(value: dict, path: str) -> None:
    parts = _path_parts(path)
    parent: object = value
    for part in parts[:-1]:
        parent = parent[part]  # type: ignore[index]
    del parent[parts[-1]]  # type: ignore[index]


def _set_path(value: dict, path: str, replacement: object) -> None:
    parts = _path_parts(path)
    parent: object = value
    for part in parts[:-1]:
        parent = parent[part]  # type: ignore[index]
    parent[parts[-1]] = replacement  # type: ignore[index]
