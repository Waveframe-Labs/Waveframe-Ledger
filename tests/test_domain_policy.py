from __future__ import annotations

import copy
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from governance_ledger.constraint_ir import (
    finalize_constraint_ir,
    finalize_runtime_fact_schema,
    validate_constraint_ir,
    validate_runtime_fact_compatibility,
)
from governance_ledger.customer_policy import (
    _interpret_customer_policy_v0_6_compatibility,
    finalize_customer_policy_authority,
    interpret_customer_policy,
)
from governance_ledger.domain_packs import (
    get_builtin_domain_pack,
    list_builtin_domain_packs,
    validate_domain_pack,
)
from governance_ledger.domain_policy import (
    apply_policy_mapping_decision,
    finalize_domain_policy_authority,
    inspect_policy_mapping_controls,
    interpret_policy_with_domain_pack,
    validate_domain_policy_publication,
)
from governance_ledger.publication_provenance import (
    classify_authority_bundle_provenance,
    validate_authority_bundle,
    validate_publication_receipt,
)


ROOT = Path(__file__).parents[1]
PACK_ID = "repository-changes"
PACK_VERSION = "1.0.0"
IDENTITIES = {
    "source_policy_id": "repository-policy",
    "source_revision": "revision-1",
    "authority_id": "repository-authority",
    "authority_version": "1.0.0",
}
HUMAN = {
    "approval_id": "approval-1",
    "approved_by": "reviewer",
    "approved_at": "2026-08-30T19:30:00Z",
    "committed_by": "committer",
    "committed_at": "2026-08-30T19:45:00Z",
    "publication_id": "publication-1",
    "published_by": "publisher",
    "published_at": "2026-08-30T20:00:00Z",
}
DIRECT_SOURCE = (
    b"Repository changes may be made only by repository maintainers. "
    b"Agents may modify README.md. "
    b"Agents must not modify files under deployment/. "
    b"Transfers above $1000000 require manager approval. "
    b"Requester and approver must be separate."
)


def _draft(source: bytes = DIRECT_SOURCE) -> dict:
    return interpret_policy_with_domain_pack(
        source,
        domain_pack_id=PACK_ID,
        domain_pack_version=PACK_VERSION,
        **IDENTITIES,
    )


def _mapped(source: bytes = b"Engineers should update the readme.") -> dict:
    draft = _draft(source)
    statement_id = draft["source_statements"][0]["statement_id"]
    application = apply_policy_mapping_decision(
        draft,
        statement_id=statement_id,
        control_id="exact-path-access",
        selections={"effect": "allow", "path": "README.md"},
        mapper_identity="mapper-1",
        mapped_at="2026-08-30T19:00:00Z",
    )
    return application["updated_interpretation"]


def _final(draft: dict | None = None, **overrides: object) -> dict:
    return finalize_domain_policy_authority(
        draft or _draft(), **{**HUMAN, **overrides}
    )


def _rehash_ir(ir: dict) -> dict:
    return finalize_constraint_ir({key: value for key, value in ir.items() if key != "ir_hash"})


def test_builtin_pack_has_separate_identity_version_and_canonical_immutable_copy() -> None:
    listed = list_builtin_domain_packs()
    assert listed == [
        {
            "domain_pack_id": PACK_ID,
            "domain_pack_version": PACK_VERSION,
            "name": "Repository changes",
            "description": listed[0]["description"],
            "canonical_hash": listed[0]["canonical_hash"],
        }
    ]
    first = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    first["name"] = "tampered"
    second = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    assert second["name"] == "Repository changes"
    assert validate_domain_pack(second)["canonical_hash"] == listed[0]["canonical_hash"]


def test_domain_pack_identity_hash_tampering_fails_closed() -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    pack["domain_pack_version"] = "1.0.1"
    with pytest.raises(ValueError, match="canonical hash"):
        validate_domain_pack(pack)
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    pack["canonical_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="canonical hash"):
        validate_domain_pack(pack)


def test_pack_contains_scoped_contract_and_deterministic_vectors() -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    assert set(pack["test_vectors"]) == {"positive", "negative", "invalid"}
    assert all(pack["test_vectors"][kind] for kind in pack["test_vectors"])
    assert pack["grammar_compiler"]["compiler_id"] == "repository-changes-sentence-grammar"
    assert pack["compiler_lowering"]["lowering_id"].endswith("contract-compiler")
    assert "repository-maintainer" in pack["role_kinds"]
    assert "repository maintainer" in pack["synonyms"]["repository-maintainer"]


def test_direct_interpretation_is_repeatable_and_preserves_all_v06_behaviors() -> None:
    first = _draft()
    second = _draft()
    assert first == second
    assert first["status"] == {
        "statement_classification_complete": True,
        "requires_mapping_count": 0,
        "enforceable_constraint_count": 5,
        "ready_for_finalization": True,
        "publication_ready": False,
    }
    result = _final(first)
    assert result["canonical_compiler_input"] == {
        "contract_id": "repository-authority",
        "contract_version": "1.0.0",
        "authority": {"required_roles": ["repository-maintainer"]},
        "targets": {
            "allow": [{"match": "exact", "value": "README.md"}],
            "deny": [{"match": "prefix", "value": "deployment/"}],
        },
        "approvals": {
            "thresholds": [
                {
                    "field": "amount",
                    "operator": ">",
                    "value": 1000000,
                    "requires_role": "manager",
                }
            ]
        },
        "constraints": [
            {"type": "separation_of_duties", "roles": ["requester", "approver"]}
        ],
    }


@pytest.mark.parametrize(
    "source,expected",
    [
        (b"Agents may normally modify README.md.", "requires_mapping"),
        (b"Agents may modify README.md. Agents must not modify README.md.", "requires_mapping"),
        (b"Agents should change docs.", "requires_mapping"),
        (b"This policy describes repository work.", "informational"),
    ],
)
def test_pack_preserves_ambiguity_without_inferring_meaning(source: bytes, expected: str) -> None:
    draft = _draft(source)
    assert all(item["classification"] == expected for item in draft["source_statements"])
    assert draft["status"]["ready_for_finalization"] is False


def test_controls_are_human_readable_and_bounded() -> None:
    draft = _draft(b"Engineers should update the readme.")
    statement_id = draft["source_statements"][0]["statement_id"]
    result = inspect_policy_mapping_controls(draft, statement_id)
    assert {item["control_id"] for item in result["controls"]} == {
        "acting-role",
        "approval-threshold",
        "exact-path-access",
        "prefix-path-access",
        "requester-approver-separation",
    }
    exact = next(item for item in result["controls"] if item["control_id"] == "exact-path-access")
    assert exact["selection_schema"]["effect"]["enum"] == ["allow", "deny"]
    assert exact["selection_schema"]["path"]["pattern"] == "exact"


def test_mapping_decision_produces_every_required_deterministic_output() -> None:
    draft = _draft(b"Engineers should update the readme.")
    statement = draft["source_statements"][0]
    result = apply_policy_mapping_decision(
        draft,
        statement_id=statement["statement_id"],
        control_id="exact-path-access",
        selections={"effect": "allow", "path": "README.md"},
        mapper_identity="mapper-1",
        mapped_at="2026-08-30T19:00:00Z",
    )
    decision = result["mapping_decision"]
    assert decision["source_document_hash"] == draft["source_policy"]["snapshot_hash"]
    assert (decision["start_byte"], decision["end_byte"]) == (
        statement["start_byte"],
        statement["end_byte"],
    )
    assert decision["domain_pack"] == draft["domain_pack"]
    assert decision["selected_subject"] == {"kind": "subject_kind", "value": "agent"}
    assert decision["selected_action"] == "modify"
    assert decision["selected_effect"] == "allow"
    assert decision["mapper_identity"] == "mapper-1"
    assert decision["mapped_at"] == "2026-08-30T19:00:00Z"
    assert result["canonical_cnl_preview"] == 'ALLOW agent TO modify repository_path:exact "README.md".'
    assert result["validation_result"]["constraint_ir"]["valid"] is True
    assert result["validation_result"]["runtime_fact_compatibility"]["compatible"] is True
    assert result["source_to_constraint_mapping"]["mode"] == "human_mapping"


@pytest.mark.parametrize(
    "control,selections",
    [
        ("acting-role", {"role": "repository-maintainer"}),
        (
            "approval-threshold",
            {"action": "transfer", "operator": ">=", "amount": "2500", "role": "manager"},
        ),
        ("exact-path-access", {"effect": "deny", "path": "secrets.txt"}),
        ("prefix-path-access", {"effect": "allow", "path": "src/"}),
        ("requester-approver-separation", {}),
    ],
)
def test_every_mapping_control_produces_valid_ir(control: str, selections: dict) -> None:
    draft = _draft(b"Map this company clause.")
    # Non-normative prose is informational by design; use explicit normative text.
    draft = _draft(b"Engineers should follow the selected control.")
    statement_id = draft["source_statements"][0]["statement_id"]
    result = apply_policy_mapping_decision(
        draft,
        statement_id=statement_id,
        control_id=control,
        selections=selections,
        mapper_identity="mapper-1",
        mapped_at="2026-08-30T19:00:00Z",
    )
    assert result["validation_result"]["constraint_ir"]["valid"] is True


@pytest.mark.parametrize(
    "selections",
    [
        {"effect": "allow", "path": "README.md", "free_form_rule": {"effect": "deny"}},
        {"effect": "override", "path": "README.md"},
        {"effect": "allow", "path": "../secret"},
    ],
)
def test_arbitrary_rule_injection_and_unbounded_selections_are_rejected(selections: dict) -> None:
    draft = _draft(b"Engineers should update the readme.")
    statement_id = draft["source_statements"][0]["statement_id"]
    with pytest.raises(ValueError):
        apply_policy_mapping_decision(
            draft,
            statement_id=statement_id,
            control_id="exact-path-access",
            selections=selections,
            mapper_identity="mapper-1",
            mapped_at="2026-08-30T19:00:00Z",
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_document_hash", "sha256:" + "0" * 64),
        ("statement_id", "statement-" + "0" * 64),
        ("start_byte", 1),
        ("end_byte", 2),
        ("domain_pack", {"domain_pack_id": PACK_ID, "domain_pack_version": PACK_VERSION, "domain_pack_hash": "sha256:" + "0" * 64}),
        ("selected_effect", "deny"),
        ("decision_hash", "sha256:" + "0" * 64),
    ],
)
def test_mapping_decision_source_hash_span_pack_and_semantics_tampering_fails(
    field: str, value: object
) -> None:
    draft = _mapped()
    draft["mapping_decisions"][0][field] = value
    draft["draft_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="reconstructed|modified|inconsistent"):
        finalize_domain_policy_authority(draft, **HUMAN)


def test_direct_cnl_and_guided_mapping_produce_equivalent_ir() -> None:
    direct = _draft(b"Agents may modify README.md.")
    mapped = _mapped()
    assert direct["constraint_ir"]["constraints"] == mapped["constraint_ir"]["constraints"]
    assert direct["constraint_ir"]["ir_hash"] == mapped["constraint_ir"]["ir_hash"]
    assert direct["canonical_cnl_previews"] == mapped["canonical_cnl_previews"]


def test_constraint_ir_rejects_unknown_fields_operators_symbols_and_untyped_values() -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    base = _draft(b"Transfers above $100 require manager approval.")["constraint_ir"]
    cases = []
    unknown_field = copy.deepcopy(base)
    unknown_field["constraints"][0]["magic"] = True
    cases.append(unknown_field)
    unknown_operator = copy.deepcopy(base)
    unknown_operator["constraints"][0]["condition"]["operands"][0]["operator"] = "approximately"
    cases.append(unknown_operator)
    unknown_symbol = copy.deepcopy(base)
    unknown_symbol["constraints"][0]["action"] = "teleport"
    cases.append(unknown_symbol)
    untyped = copy.deepcopy(base)
    untyped["constraints"][0]["condition"]["operands"][0]["literal"] = 100
    cases.append(untyped)
    implicit_precedence = copy.deepcopy(base)
    implicit_precedence["constraints"][0]["condition"] = {
        "and": [base["constraints"][0]["condition"]]
    }
    cases.append(implicit_precedence)
    for value in cases:
        with pytest.raises(ValueError):
            validate_constraint_ir(_rehash_ir(value), domain_pack=pack)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("type", "integer", "type"),
        ("canonical_unit", "EUR", "unit"),
        ("comparison_operators", ["=="], "operator"),
    ],
)
def test_runtime_fact_type_unit_and_operator_mismatches_return_diagnostics(
    field: str, value: object, match: str
) -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    ir = _draft(b"Transfers above $100 require manager approval.")["constraint_ir"]
    runtime = copy.deepcopy(pack["runtime_fact_schema"])
    fact = next(item for item in runtime["facts"] if item["fact_id"] == "request.amount")
    fact[field] = value
    runtime = finalize_runtime_fact_schema({key: val for key, val in runtime.items() if key != "schema_hash"})
    result = validate_runtime_fact_compatibility(ir, runtime, domain_pack=pack)
    assert result["compatible"] is False
    assert any(match in item["message"] for item in result["diagnostics"])


def test_missing_runtime_fact_returns_actionable_diagnostic_and_blocks_publication() -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    draft = _draft(b"Transfers above $100 require manager approval.")
    runtime = copy.deepcopy(pack["runtime_fact_schema"])
    runtime["facts"] = [item for item in runtime["facts"] if item["fact_id"] != "request.amount"]
    runtime = finalize_runtime_fact_schema({key: val for key, val in runtime.items() if key != "schema_hash"})
    compatibility = validate_runtime_fact_compatibility(
        draft["constraint_ir"], runtime, domain_pack=pack
    )
    assert compatibility["compatible"] is False
    assert any(
        item["message"]
        == "This rule requires request.amount, but the selected runtime schema does not provide it."
        for item in compatibility["diagnostics"]
    )
    with pytest.raises(ValueError, match="requires request.amount"):
        _final(draft, runtime_fact_schema=runtime)


def test_contradictory_effects_and_empty_enforceable_sets_are_rejected() -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    allow = _draft(b"Agents may modify README.md.")["constraint_ir"]
    deny = copy.deepcopy(allow["constraints"][0])
    deny["effect"] = "deny"
    contradictory = _rehash_ir({**allow, "constraints": [allow["constraints"][0], deny]})
    with pytest.raises(ValueError, match="contradictory"):
        validate_constraint_ir(contradictory, domain_pack=pack)
    empty = _rehash_ir({**allow, "constraints": []})
    with pytest.raises(ValueError, match="at least one enforceable rule"):
        validate_constraint_ir(empty, domain_pack=pack)


def test_explicit_exception_has_declared_precedence_but_is_not_silently_lowered() -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    ir = copy.deepcopy(_draft(b"Agents must not modify files under deployment/.")["constraint_ir"])
    constraint = ir["constraints"][0]
    constraint["exceptions"] = [
        {
            "exception_id": "emergency-change",
            "effect": "allow",
            "condition": {
                "kind": "group",
                "operator": "all",
                "operands": [
                    {
                        "kind": "comparison",
                        "operator": "==",
                        "fact": "actor.role",
                        "literal": {"type": "enum", "value": "security-reviewer", "unit": None},
                    }
                ],
            },
        }
    ]
    constraint["required_runtime_facts"] = sorted(
        set(constraint["required_runtime_facts"]) | {"actor.role"}
    )
    ir = _rehash_ir(ir)
    assert validate_constraint_ir(ir, domain_pack=pack)["valid"] is True
    # The built-in lowerer has no existing compiler representation for exceptions.
    draft = _draft(b"Agents must not modify files under deployment/.")
    draft["constraint_ir"] = ir
    with pytest.raises(ValueError, match="modified|inconsistent"):
        _final(draft)


def test_constraint_ir_supports_exact_principals_and_evidence_obligations() -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    ir = copy.deepcopy(_draft(b"Agents may modify README.md.")["constraint_ir"])
    constraint = ir["constraints"][0]
    constraint["subject"] = {"kind": "principal_id", "value": "service-account-17"}
    constraint["effect"] = "require"
    constraint["obligations"]["evidence"] = [
        {"evidence_type": "change-record", "fact": "evidence.change_record_id"}
    ]
    constraint["required_runtime_facts"] = sorted(
        (set(constraint["required_runtime_facts"]) - {"actor.subject_kind"})
        | {"actor.principal_id", "evidence.change_record_id"}
    )
    ir = _rehash_ir(ir)
    assert validate_constraint_ir(ir, domain_pack=pack)["valid"] is True


def test_domain_publication_binds_complete_provenance_without_mutating_v1_semantics() -> None:
    result = _final(_mapped())
    bundle = result["domain_policy_authority_bundle"]
    receipt = result["domain_policy_publication_receipt"]
    assert validate_domain_policy_publication(bundle, receipt)["provenance_complete"] is True
    assert bundle["provenance_complete"] is True
    assert bundle["domain_pack"] == result["validated_interpretation"]["domain_pack"]
    assert bundle["constraint_ir"] == result["validated_interpretation"]["constraint_ir"]
    assert bundle["mapping_decisions"] == result["validated_interpretation"]["mapping_decisions"]
    assert bundle["semantic_commit_bundle"] == result["semantic_commit_bundle"]
    assert bundle["compiled_authority_contract"] == result["compiled_authority_contract"]
    assert bundle["authority_bundle_v1"]["schema_version"] == "authority_bundle.v1"
    assert bundle["publication_receipt_v1"]["schema_version"] == "publication_receipt.v1"
    assert classify_authority_bundle_provenance(bundle["authority_bundle_v1"]) == "legacy_provenance_incomplete"


@pytest.mark.parametrize(
    "path",
    [
        ("domain_pack", "domain_pack_hash"),
        ("source_statements", 0, "start_byte"),
        ("mapping_decisions", 0, "decision_hash"),
        ("constraint_ir", "ir_hash"),
        ("semantic_commit_bundle", "semantic_commit_hash"),
        ("compiled_authority_contract", "contract_hash"),
        ("authority", "authority_ref"),
        ("authority_bundle_v1", "contract_hash"),
    ],
)
def test_domain_publication_complete_provenance_tamper_matrix(path: tuple[object, ...]) -> None:
    result = _final(_mapped())
    bundle = copy.deepcopy(result["domain_policy_authority_bundle"])
    target: object = bundle
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    leaf = path[-1]
    current = target[leaf]  # type: ignore[index]
    target[leaf] = current + "-tampered" if isinstance(current, str) else 1  # type: ignore[index]
    with pytest.raises(ValueError):
        validate_domain_policy_publication(bundle, result["domain_policy_publication_receipt"])


def test_one_byte_source_change_propagates_through_downstream_identities() -> None:
    first = _final(_draft(b"Agents may modify README.md."))
    second = _final(_draft(b"Agents may modify README.md.\n"))
    for field in (
        "source_snapshot_hash",
        "interpretation_hash",
        "semantic_commit_bundle_hash",
        "compiled_contract_hash",
        "authority_bundle_v1_hash",
        "publication_receipt_v1_hash",
        "domain_policy_bundle_hash",
        "domain_policy_receipt_hash",
    ):
        assert first["canonical_hashes"][field] != second["canonical_hashes"][field]


def test_legacy_v06_api_is_an_exact_compatibility_delegate_with_stable_hashes() -> None:
    source = (
        b"Repository changes may be made only by repository maintainers.\n"
        b"Agents may modify README.md.\n"
        b"Agents must not modify files under deployment/."
    )
    identities = {
        "source_policy_id": "repo-change-policy",
        "source_revision": "revision-2026-08",
        "authority_id": "repo-change-authority",
        "authority_version": "6.0.0",
    }
    public = interpret_customer_policy(source, **identities)
    compatibility = _interpret_customer_policy_v0_6_compatibility(source, **identities)
    assert public == compatibility
    assert public["draft_hash"] == "sha256:02a21d437bdb6c029c3bbc8a98d766dbffb696e103154aeb595d76f3af471bec"
    final = finalize_customer_policy_authority(
        public,
        resolutions=[],
        approval_id="approval-1",
        approved_by="reviewer",
        approved_at="2026-08-29T13:59:00Z",
        committed_by="committer",
        committed_at="2026-08-29T13:59:30Z",
        publication_id="publication-1",
        published_by="publisher",
        published_at="2026-08-29T14:00:00Z",
    )
    assert final["canonical_hashes"]["authority_bundle_hash"] == "sha256:b1fc5e8a717adc07c0f3f8ec0d6b0b760cfe0bc7a28c3654e3e9366c480c9749"
    assert final["canonical_hashes"]["publication_receipt_hash"] == "sha256:6b5b7a69aebd0ec9d6ffcade311c38d99f85b101aae8a3f119b27b68a2916cb3"


@pytest.mark.parametrize(
    "source",
    [
        b"Agents may normally modify README.md.",
        b"Agents may modify ../secret.",
        b"Agents may modify README.md. Agents must not modify README.md.",
        b"Agents should update docs.",
    ],
)
def test_legacy_v06_rejected_or_unready_behavior_is_unchanged(source: bytes) -> None:
    try:
        public = interpret_customer_policy(source, **IDENTITIES)
    except ValueError as public_error:
        with pytest.raises(type(public_error), match="target"):
            _interpret_customer_policy_v0_6_compatibility(source, **IDENTITIES)
    else:
        assert public == _interpret_customer_policy_v0_6_compatibility(source, **IDENTITIES)


def test_released_v1_legacy_artifacts_remain_readable() -> None:
    fixture = ROOT / "tests/fixtures/golden_path/contracts/finance-policy-1.0.0.authority-bundle.json"
    bundle = json.loads(fixture.read_text(encoding="utf-8"))
    receipt = json.loads(
        (fixture.parent / "finance-policy-1.0.0.publication-receipt.json").read_text(encoding="utf-8")
    )
    assert validate_authority_bundle(bundle)["provenance_complete"] is False
    assert validate_publication_receipt(bundle, receipt)["provenance_complete"] is False


def test_new_artifacts_validate_against_their_json_schemas() -> None:
    pack = get_builtin_domain_pack(PACK_ID, PACK_VERSION)
    draft = _mapped()
    result = _final(draft)
    schemas = {
        json.loads(path.read_text(encoding="utf-8"))["$id"]: json.loads(
            path.read_text(encoding="utf-8")
        )
        for path in (ROOT / "schemas").glob("*.json")
        if "$id" in json.loads(path.read_text(encoding="utf-8"))
    }
    registry = Registry().with_resources(
        (uri, Resource.from_contents(schema)) for uri, schema in schemas.items()
    )
    for artifact, filename in (
        (pack["runtime_fact_schema"], "runtime_fact_schema.v1.json"),
        (draft["constraint_ir"], "constraint_ir.v1.json"),
        (pack, "domain_pack.v1.json"),
        (draft["mapping_decisions"][0], "policy_mapping_decision.v1.json"),
        (result["domain_policy_authority_bundle"], "domain_policy_authority_bundle.v1.json"),
        (result["domain_policy_publication_receipt"], "domain_policy_publication_receipt.v1.json"),
    ):
        schema = json.loads((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, registry=registry).validate(artifact)


def test_domain_workflow_is_guard_filesystem_and_network_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    guard_before = sys.modules.get("waveframe_guard")
    original = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = _final(_mapped())
    finally:
        os.chdir(original)
    assert list(tmp_path.iterdir()) == []
    assert result["status"]["publication_ready"] is True
    assert sys.modules.get("waveframe_guard") is guard_before


def test_base_install_imports_and_runs_without_guard_in_fresh_interpreter() -> None:
    script = """
import sys
from governance_ledger import interpret_policy_with_domain_pack
assert 'waveframe_guard' not in sys.modules
d = interpret_policy_with_domain_pack(b'Agents may modify README.md.', domain_pack_id='repository-changes', domain_pack_version='1.0.0', source_policy_id='p', source_revision='r', authority_id='a', authority_version='1.0.0')
assert d['status']['ready_for_finalization']
assert 'waveframe_guard' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], text=True, capture_output=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
