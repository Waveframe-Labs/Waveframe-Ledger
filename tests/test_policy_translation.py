from __future__ import annotations

import base64
import copy
import json
import socket
import sys
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from governance_ledger import (
    apply_policy_translation_binding,
    apply_policy_translation_disposition,
    approve_policy_translation_proposal,
    create_policy_translation_proposal,
    finalize_policy_translation_authority,
    get_policy_translation_capability_catalog,
    inspect_policy_translation_proposal,
    interpret_policy_with_domain_pack,
    render_policy_translation_review,
    validate_authority_bundle,
    validate_policy_translation_proposal,
    validate_publication_receipt,
)
from governance_ledger.publication_provenance import bytes_sha256, canonical_sha256


ROOT = Path(__file__).parents[1]
NOW = "2026-09-03T12:00:00Z"
FACTS = [
    "actor.subject_kind",
    "proposal.action",
    "proposal.resource.kind",
    "proposal.resource.path",
]


def _base(source: bytes) -> dict:
    return interpret_policy_with_domain_pack(
        source,
        domain_pack_id="repository-changes",
        domain_pack_version="1.0.0",
        source_policy_id="repository-policy",
        source_revision="revision-1",
        authority_id="repository-authority",
        authority_version="1.0.0",
    )


def _path_control(path: str, *, effect: str = "allow", prefix: bool = False) -> dict:
    return {
        "control_type": "prefix_path_access" if prefix else "exact_path_access",
        "actor_kind": "autonomous_agent",
        "action": "modify",
        "resource_kind": "repository_path",
        "fact_id": "proposal.resource.path",
        "operator": "starts_with" if prefix else "==",
        "effect": effect,
        "enforcement_point": "waveframe.guard.repository-change.v1",
        "value": {"kind": "source_literal", "value": path},
        "required_runtime_facts": FACTS,
    }


def _proposal(
    source: bytes = b"Agents may modify README.md. Policy overview.\n",
    *,
    provider_explanation: str | None = "Provider says this DENIES all repository access.",
) -> dict:
    draft = _base(source)
    clauses = []
    for index, statement in enumerate(draft["source_statements"]):
        if index == 0:
            path = "README.md" if b"README.md" in source else "READNE.md"
            status = "enforceable_fully_bound"
            control = _path_control(path)
            explanation = provider_explanation
        else:
            status = "informational"
            control = None
            explanation = None
        clauses.append(
            {
                "start_byte": statement["start_byte"],
                "end_byte": statement["end_byte"],
                "status": status,
                "candidate_control": control,
                "unresolved_binding_ids": [],
                "limitation_code": None,
                "provider_explanation": explanation,
            }
        )
    return create_policy_translation_proposal(
        source,
        source_policy_id="repository-policy",
        source_revision="revision-1",
        authority_id="repository-authority",
        authority_version="1.0.0",
        clauses=clauses,
        organizational_bindings=[],
        provider_class="hosted_model",
        provider_identifier="provider/deployment",
        translation_template_version="template-1",
        translation_template_hash=bytes_sha256(b"template"),
        request_configuration_id="request-config-1",
        request_configuration_hash=bytes_sha256(b"configuration"),
        created_at=NOW,
        candidate_response_bytes=b'{"untrusted":"candidate"}',
    )


def _confirmed(proposal: dict) -> dict:
    state = None
    for index, clause in enumerate(proposal["clauses"]):
        if index == 0:
            state = apply_policy_translation_disposition(
                proposal,
                state,
                clause_id=clause["clause_id"],
                disposition="enforced",
                reason_code="human-confirmed-control",
                confirmed_by="policy-owner",
                confirmed_at="2026-09-03T12:01:00Z",
            )
        else:
            state = apply_policy_translation_disposition(
                proposal,
                state,
                clause_id=clause["clause_id"],
                disposition="informational",
                reason_code="context-only",
                acknowledge_unenforced=True,
                confirmed_by="policy-owner",
                confirmed_at="2026-09-03T12:02:00Z",
            )
    assert state is not None
    return state


def _approved(proposal: dict, confirmation: dict) -> dict:
    return approve_policy_translation_proposal(
        proposal,
        confirmation,
        approved_by="policy-owner",
        approved_at="2026-09-03T12:03:00Z",
    )


def _final(proposal: dict) -> dict:
    confirmation = _confirmed(proposal)
    approval = _approved(proposal, confirmation)
    return finalize_policy_translation_authority(
        proposal,
        confirmation,
        approval,
        committed_by="ledger-committer",
        committed_at="2026-09-03T12:04:00Z",
        publication_id="publication-1",
        published_by="ledger-publisher",
        published_at="2026-09-03T12:05:00Z",
    )


def _restamp_control(control: dict) -> None:
    control["candidate_control_id"] = "candidate-control-" + canonical_sha256(
        {key: value for key, value in control.items() if key != "candidate_control_id"}
    ).removeprefix("sha256:")


def _restamp_proposal(proposal: dict) -> None:
    payload = {
        key: value
        for key, value in proposal.items()
        if key not in {"proposal_id", "proposal_hash"}
    }
    proposal["proposal_hash"] = canonical_sha256(payload)
    proposal["proposal_id"] = "policy-translation-proposal-" + proposal[
        "proposal_hash"
    ].removeprefix("sha256:")


def _schema_validate(value: dict, filename: str) -> None:
    registry = Registry()
    for path in (ROOT / "schemas").glob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if "$id" in schema:
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = json.loads((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, registry=registry).validate(value)


def test_catalog_is_finite_hashed_and_matches_only_released_runtime_surface() -> None:
    catalog = get_policy_translation_capability_catalog()
    assert catalog["actor_kinds"] == ["autonomous_agent"]
    assert catalog["actions"] == ["modify"]
    assert [item["control_type"] for item in catalog["control_types"]] == [
        "acting_role",
        "exact_path_access",
        "prefix_path_access",
    ]
    assert {
        "push",
        "open_pull_request",
        "merge_pull_request",
        "branch_scope",
        "approval_count_or_threshold",
        "evidence_requirement",
    } <= set(catalog["known_fail_closed_capabilities"])
    assert catalog["domain_pack"]["domain_pack_hash"] == (
        "sha256:4b6ff9a3ebf3b419151fbaa3f899012dca39ff354de8e768da05146ad0c64b80"
    )
    runtime = {item["fact_id"]: item for item in catalog["facts"]}
    assert sorted(runtime) == [
        "actor.principal_id",
        "actor.role",
        "actor.subject_kind",
        "proposal.action",
        "proposal.resource.kind",
        "proposal.resource.path",
    ]
    assert catalog["catalog_hash"] == canonical_sha256(
        {key: value for key, value in catalog.items() if key != "catalog_hash"}
    )
    _schema_validate(catalog, "policy_translation_capability_catalog.v1.json")


def test_proposal_validation_is_deterministic_but_does_not_claim_semantic_validity() -> None:
    proposal = _proposal()
    first = validate_policy_translation_proposal(proposal)
    second = validate_policy_translation_proposal(copy.deepcopy(proposal))
    assert first == second
    assert first["semantic_validity"] == "not_established"
    assert first["trust_posture"] == "untrusted_authoring_input"
    _schema_validate(proposal, "policy_translation_proposal.v1.json")


@pytest.mark.parametrize("mutation", ["omitted", "duplicated", "overlap", "reordered"])
def test_clause_partition_rejects_omission_duplication_overlap_and_reordering(mutation: str) -> None:
    proposal = _proposal()
    if mutation == "omitted":
        proposal["clauses"].pop()
    elif mutation == "duplicated":
        proposal["clauses"].append(copy.deepcopy(proposal["clauses"][-1]))
    elif mutation == "overlap":
        proposal["clauses"][1]["start_byte"] -= 1
    else:
        proposal["clauses"].reverse()
    _restamp_proposal(proposal)
    with pytest.raises(ValueError, match="omits|spans|reordered"):
        validate_policy_translation_proposal(proposal)


def test_candidate_response_tampering_is_detected_even_if_proposal_is_rehashed() -> None:
    proposal = _proposal()
    proposal["provider_evidence"]["candidate_response_base64"] = base64.b64encode(
        b"tampered"
    ).decode("ascii")
    _restamp_proposal(proposal)
    with pytest.raises(ValueError, match="candidate-response hash"):
        validate_policy_translation_proposal(proposal)


def test_provider_explanation_can_contradict_but_never_controls_review_meaning() -> None:
    proposal = _proposal(provider_explanation="DENY everything and require five reviewers.")
    review = render_policy_translation_review(proposal)
    rendered = json.dumps(review)
    assert "is allowed" in review["clauses"][0]["operational_explanation"]
    assert "DENY everything" not in rendered
    assert "five reviewers" not in rendered
    assert review["provider_explanations_used"] is False
    assert review == render_policy_translation_review(copy.deepcopy(proposal))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("action", "push", "unknown action"),
        ("fact_id", "proposal.branch", "runtime fact"),
        ("operator", ">", "operator"),
        ("enforcement_point", "provider.runtime", "enforcement point"),
    ],
)
def test_unknown_action_fact_operator_and_enforcement_point_fail_closed(
    field: str, value: str, message: str
) -> None:
    proposal = _proposal()
    control = proposal["clauses"][0]["candidate_control"]
    control[field] = value
    _restamp_control(control)
    _restamp_proposal(proposal)
    with pytest.raises(ValueError, match=message):
        validate_policy_translation_proposal(proposal)


def test_type_invalid_value_and_unavailable_runtime_fact_fail_closed() -> None:
    proposal = _proposal()
    control = proposal["clauses"][0]["candidate_control"]
    control["value"]["value"] = 7
    _restamp_control(control)
    _restamp_proposal(proposal)
    with pytest.raises(ValueError, match="non-empty string"):
        validate_policy_translation_proposal(proposal)

    proposal = _proposal()
    control = proposal["clauses"][0]["candidate_control"]
    control["required_runtime_facts"] = [*FACTS, "proposal.branch"]
    _restamp_control(control)
    _restamp_proposal(proposal)
    with pytest.raises(ValueError, match="runtime facts"):
        validate_policy_translation_proposal(proposal)


def test_guessed_path_and_provider_resolved_organization_binding_are_rejected() -> None:
    proposal = _proposal()
    control = proposal["clauses"][0]["candidate_control"]
    control["value"]["value"] = "secret/guessed.txt"
    _restamp_control(control)
    _restamp_proposal(proposal)
    with pytest.raises(ValueError, match="guessed"):
        validate_policy_translation_proposal(proposal)

    proposal = _binding_proposal()
    proposal["organizational_bindings"][0]["status"] = "resolved"
    _restamp_proposal(proposal)
    with pytest.raises(ValueError, match="cannot present.*resolved"):
        validate_policy_translation_proposal(proposal)


def _binding_proposal() -> dict:
    source = b"Only the designated repository custodians may make repository changes."
    statement = _base(source)["source_statements"][0]
    binding_id = "repository-custodian-role"
    control = {
        "control_type": "acting_role",
        "actor_kind": "autonomous_agent",
        "action": "modify",
        "resource_kind": "repository_change",
        "fact_id": "actor.role",
        "operator": "==",
        "effect": "require",
        "enforcement_point": "waveframe.guard.repository-change.v1",
        "value": {"kind": "organizational_binding", "binding_id": binding_id},
        "required_runtime_facts": [
            "actor.role",
            "actor.subject_kind",
            "proposal.action",
            "proposal.resource.kind",
        ],
    }
    return create_policy_translation_proposal(
        source,
        source_policy_id="repository-policy",
        source_revision="revision-1",
        authority_id="repository-authority",
        authority_version="1.0.0",
        clauses=[
            {
                "start_byte": statement["start_byte"],
                "end_byte": statement["end_byte"],
                "status": "needs_concrete_answer",
                "candidate_control": control,
                "unresolved_binding_ids": [binding_id],
                "limitation_code": None,
                "provider_explanation": None,
            }
        ],
        organizational_bindings=[
            {
                "binding_id": binding_id,
                "binding_type": "repository_role",
                "symbol": "designated repository custodians",
                "question": "Which released repository role represents the custodians?",
                "status": "unresolved",
            }
        ],
        provider_class="guided_deterministic",
        provider_identifier=None,
        translation_template_version="template-1",
        translation_template_hash=bytes_sha256(b"template"),
        request_configuration_id="request-config-1",
        request_configuration_hash=bytes_sha256(b"configuration"),
        created_at=NOW,
        candidate_response_bytes=b"guided candidate",
    )


def test_bounded_binding_resolution_and_review_then_v2_publication() -> None:
    proposal = _binding_proposal()
    inspection = inspect_policy_translation_proposal(proposal)
    assert inspection["publication_ready"] is False
    assert inspection["unresolved_bindings"][0]["binding_id"] == "repository-custodian-role"
    with pytest.raises(ValueError, match="outside the released role"):
        apply_policy_translation_binding(
            proposal,
            None,
            binding_id="repository-custodian-role",
            value="invented-team",
            confirmed_by="owner",
            confirmed_at=NOW,
        )
    state = apply_policy_translation_binding(
        proposal,
        None,
        binding_id="repository-custodian-role",
        value="repository-maintainer",
        confirmed_by="owner",
        confirmed_at=NOW,
    )
    assert "repository-maintainer" in render_policy_translation_review(proposal, state)[
        "clauses"
    ][0]["operational_explanation"]
    state = apply_policy_translation_disposition(
        proposal,
        state,
        clause_id=proposal["clauses"][0]["clause_id"],
        disposition="enforced",
        reason_code="human-confirmed-control",
        confirmed_by="owner",
        confirmed_at="2026-09-03T12:01:00Z",
    )
    approval = _approved(proposal, state)
    _schema_validate(state, "policy_translation_confirmation.v1.json")
    _schema_validate(approval, "policy_translation_approval.v1.json")
    result = finalize_policy_translation_authority(
        proposal,
        state,
        approval,
        committed_by="committer",
        committed_at="2026-09-03T12:04:00Z",
        publication_id="publication-1",
        published_by="publisher",
        published_at="2026-09-03T12:05:00Z",
    )
    assert result["compiled_authority_contract"]["authority_requirements"] == {
        "required_roles": ["repository-maintainer"]
    }
    assert result["proposal_evidence_required_by_guard"] is False


def test_partial_coverage_requires_every_exact_unenforced_acknowledgement() -> None:
    proposal = _proposal()
    first = apply_policy_translation_disposition(
        proposal,
        None,
        clause_id=proposal["clauses"][0]["clause_id"],
        disposition="enforced",
        reason_code="human-confirmed-control",
        confirmed_by="owner",
        confirmed_at=NOW,
    )
    with pytest.raises(ValueError, match="acknowledgement"):
        apply_policy_translation_disposition(
            proposal,
            first,
            clause_id=proposal["clauses"][1]["clause_id"],
            disposition="informational",
            reason_code="context-only",
            confirmed_by="owner",
            confirmed_at=NOW,
        )
    with pytest.raises(ValueError, match="every source clause"):
        approve_policy_translation_proposal(
            proposal, first, approved_by="owner", approved_at=NOW
        )


def test_unsupported_clause_cannot_silently_become_enforced() -> None:
    proposal = _proposal()
    clause = proposal["clauses"][1]
    clause["status"] = "unsupported"
    _restamp_proposal(proposal)
    validate_policy_translation_proposal(proposal)
    with pytest.raises(ValueError, match="requires a validated candidate control"):
        apply_policy_translation_disposition(
            proposal,
            None,
            clause_id=clause["clause_id"],
            disposition="enforced",
            reason_code="human-confirmed-control",
            confirmed_by="owner",
            confirmed_at=NOW,
        )


def test_cross_source_and_cross_authority_substitution_fail_closed() -> None:
    proposal = _proposal()
    confirmation = _confirmed(proposal)
    source_substitution = copy.deepcopy(proposal)
    source_substitution["source_policy"]["source_policy_id"] = "other-policy"
    source_substitution["source_policy"]["source_policy_ref"] = "other-policy@revision-1"
    _restamp_proposal(source_substitution)
    with pytest.raises(ValueError, match="clause identity"):
        validate_policy_translation_proposal(source_substitution)

    authority_substitution = copy.deepcopy(proposal)
    authority_substitution["authority"]["authority_id"] = "other-authority"
    authority_substitution["authority"]["authority_ref"] = "other-authority@1.0.0"
    _restamp_proposal(authority_substitution)
    validate_policy_translation_proposal(authority_substitution)
    with pytest.raises(ValueError, match="substituted across"):
        approve_policy_translation_proposal(
            authority_substitution,
            confirmation,
            approved_by="owner",
            approved_at=NOW,
        )


def test_changed_human_confirmation_or_late_confirmation_invalidates_approval() -> None:
    proposal = _proposal()
    confirmation = _confirmed(proposal)
    approval = _approved(proposal, confirmation)
    tampered = copy.deepcopy(confirmation)
    tampered["clause_decisions"][0]["confirmed_by"] = "different-owner"
    tampered["clause_decisions"][0]["decision_hash"] = canonical_sha256(
        {
            key: value
            for key, value in tampered["clause_decisions"][0].items()
            if key != "decision_hash"
        }
    )
    tampered["confirmation_hash"] = canonical_sha256(
        {key: value for key, value in tampered.items() if key != "confirmation_hash"}
    )
    with pytest.raises(ValueError, match="approval binding is invalid"):
        finalize_policy_translation_authority(
            proposal,
            tampered,
            approval,
            committed_by="committer",
            committed_at="2026-09-03T12:04:00Z",
            publication_id="publication-1",
            published_by="publisher",
            published_at="2026-09-03T12:05:00Z",
        )

    with pytest.raises(ValueError, match="confirmation must precede"):
        approve_policy_translation_proposal(
            proposal,
            confirmation,
            approved_by="owner",
            approved_at="2026-09-03T11:59:00Z",
        )


def test_directly_compiled_clause_cannot_be_approved_as_unenforced() -> None:
    proposal = _proposal()
    state = None
    state = apply_policy_translation_disposition(
        proposal,
        state,
        clause_id=proposal["clauses"][0]["clause_id"],
        disposition="unsupported",
        reason_code="not-enforceable",
        acknowledge_unenforced=True,
        confirmed_by="owner",
        confirmed_at=NOW,
    )
    state = apply_policy_translation_disposition(
        proposal,
        state,
        clause_id=proposal["clauses"][1]["clause_id"],
        disposition="informational",
        reason_code="context-only",
        acknowledge_unenforced=True,
        confirmed_by="owner",
        confirmed_at=NOW,
    )
    with pytest.raises(ValueError, match="at least one enforced"):
        _approved(proposal, state)


def test_one_byte_source_mutation_changes_every_downstream_normative_identity() -> None:
    first_proposal = _proposal(b"Agents may modify README.md. Policy overview.\n")
    second_proposal = _proposal(b"Agents may modify READNE.md. Policy overview.\n")
    first = _final(first_proposal)
    second = _final(second_proposal)
    assert first_proposal["proposal_hash"] != second_proposal["proposal_hash"]
    for field in (
        "source_snapshot_hash",
        "interpretation_hash",
        "constraint_ir_hash",
        "semantic_commit_hash",
        "compiled_contract_hash",
        "authority_bundle_hash",
        "publication_receipt_hash",
    ):
        assert first["canonical_hashes"][field] != second["canonical_hashes"][field]


def test_v2_publication_independently_validates_without_proposal_evidence() -> None:
    result = _final(_proposal())
    bundle = result["authority_bundle"]
    receipt = result["publication_receipt"]
    assert "provider_evidence" not in json.dumps(bundle)
    assert "policy_translation_proposal" not in json.dumps(bundle)
    assert validate_authority_bundle(bundle)["provenance_complete"] is True
    assert validate_publication_receipt(bundle, receipt)["provenance_complete"] is True
    assert result["policy_translation_coverage"]["enforced_clause_count"] == 1
    assert result["policy_translation_coverage"]["unenforced_clause_count"] == 1


def test_translation_boundary_is_network_filesystem_guard_and_credentials_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    guard_before = sys.modules.get("waveframe_guard")
    monkeypatch.chdir(tmp_path)
    proposal = _proposal()
    assert validate_policy_translation_proposal(proposal)["valid"] is True
    assert list(tmp_path.iterdir()) == []
    assert sys.modules.get("waveframe_guard") is guard_before


def test_proposal_cannot_masquerade_as_released_runtime_schema() -> None:
    proposal = _proposal()
    for filename, version in (
        ("authority_bundle.v1.json", "authority_bundle.v1"),
        ("authority_bundle.v2.json", "authority_bundle.v2"),
        ("publication_receipt.v1.json", "publication_receipt.v1"),
        ("publication_receipt.v2.json", "publication_receipt.v2"),
    ):
        masquerading = copy.deepcopy(proposal)
        masquerading["schema_version"] = version
        with pytest.raises(jsonschema.ValidationError):
            _schema_validate(masquerading, filename)


def test_guard_0161_cold_verification_binds_v2_publication_to_exact_source(
    tmp_path: Path,
) -> None:
    pytest.importorskip("waveframe_guard")
    from importlib.metadata import version

    from waveframe_guard.authority import load_authority
    from waveframe_guard.authority.adapters import LocalRegistryResolver

    assert version("waveframe-guard") == "0.16.1"
    result = _final(_proposal())
    bundle = result["authority_bundle"]
    receipt = result["publication_receipt"]
    contract = result["compiled_authority_contract"]
    bundle_ref = "contracts/repository-authority-1.0.0.authority-bundle.json"
    receipt_ref = "contracts/repository-authority-1.0.0.publication-receipt.json"
    (tmp_path / "contracts").mkdir()
    (tmp_path / bundle_ref).write_text(json.dumps(bundle), encoding="utf-8")
    (tmp_path / receipt_ref).write_text(json.dumps(receipt), encoding="utf-8")
    registry = {
        "schema_version": "contract_registry.v1",
        "contracts": [
            {
                "contract_id": "repository-authority",
                "contract_version": "1.0.0",
                "authority_ref": "repository-authority@1.0.0",
                "contract_hash": contract["contract_hash"],
                "bundle_path": bundle_ref,
                "bundle_hash": bundle["bundle_hash"],
                "receipt_path": receipt_ref,
                "receipt_hash": receipt["receipt_hash"],
                "publication_id": receipt["publication_id"],
                "published_at": receipt["published_at"],
                "published_by": receipt["published_by"],
                "lifecycle_state": "active",
            }
        ],
    }
    registry["registry_hash"] = canonical_sha256(registry)
    registry_path = tmp_path / "contracts" / "index.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    authority = load_authority(
        "repository-authority@1.0.0",
        resolver=LocalRegistryResolver(registry_path, workspace_root=tmp_path),
    )
    evidence = authority.authority_evidence
    assert evidence is not None
    assert authority.contract["lineage"]["source_hash"] == bundle["source_policy"][
        "snapshot_hash"
    ]
    assert evidence["authority_bundle"]["bundle_hash"] == bundle["bundle_hash"]
    assert evidence["publication_receipt"]["receipt_hash"] == receipt["receipt_hash"]
    assert authority.runtime_integrity_hash
    assert "provider_evidence" not in json.dumps(evidence)
