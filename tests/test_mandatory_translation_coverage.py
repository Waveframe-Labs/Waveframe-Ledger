"""Regression tests for catalog-1 source coverage before authority issuance."""

import json
from pathlib import Path

import pytest

from governance_ledger import (
    apply_policy_translation_control_confirmation,
    apply_policy_translation_disposition,
    approve_policy_translation_proposal,
    build_policy_translation_commitment,
    create_policy_translation_proposal,
    finalize_policy_translation_authority,
    finalize_policy_translation_authority_v3,
    inspect_policy_translation_customer_coverage,
    inspect_policy_translation_proposal,
    render_policy_translation_review,
    validate_policy_translation_commitment,
)
from tests.test_policy_translation import _approved, _base, _confirmed, _path_control, _proposal, _run


EVIDENCE = Path(__file__).parent / "synthetic_evidence" / "mandatory_translation_coverage.json"
PUBLICATION = {
    "committed_by": "synthetic-committer",
    "committed_at": "2026-11-16T12:04:00Z",
    "publication_id": "synthetic-publication",
    "published_by": "synthetic-publisher",
    "published_at": "2026-11-16T12:05:00Z",
}


@pytest.fixture(params=["R11", "R12"])
def released_record(request):
    # The offline convergence study recorded these synthetic objects with Ledger 0.9.1.
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))[request.param]


@pytest.mark.parametrize("coverage", ["false_full", "partial"])
def test_mandatory_residuals_remain_reviewable_but_block_approval(released_record, coverage):
    record = released_record[coverage]
    proposal, confirmation = record["proposal"], record["confirmation"]
    review = render_policy_translation_review(proposal, confirmation)
    assert review["coverage"]["unrepresented_clause_count"] == (coverage == "partial")
    assert inspect_policy_translation_proposal(proposal, confirmation)["publication_ready"] is False
    customer = inspect_policy_translation_customer_coverage(proposal, confirmation)
    assert [clause["customer_coverage_state"] for clause in customer["clauses"]] == [
        "Not currently enforceable"
    ]
    with pytest.raises(ValueError, match="source clause 1 is outside the supported repository grammar"):
        approve_policy_translation_proposal(
            proposal,
            confirmation,
            approved_by=released_record["false_full"]["approval"]["approved_by"],
            approved_at=released_record["false_full"]["approval"]["approved_at"],
        )


@pytest.mark.parametrize("issue", [
    build_policy_translation_commitment,
    finalize_policy_translation_authority,
    finalize_policy_translation_authority_v3,
])
def test_previously_valid_false_full_approval_cannot_issue_authority(released_record, issue):
    old = released_record["false_full"]
    kwargs = {} if issue is build_policy_translation_commitment else PUBLICATION
    with pytest.raises(ValueError, match="source clause 1 is outside the supported repository grammar"):
        issue(old["proposal"], old["confirmation"], old["approval"], **kwargs)


def test_historical_commitment_verification_requires_explicit_source_eligibility_check(released_record):
    old = released_record["false_full"]
    # Historical verification preserves evidence, including recorded false declarations.
    # The build/finalize cases above must still refuse every new issuance route.
    assert validate_policy_translation_commitment(
        old["proposal"]["source_policy"], old["proposal"]["authority"], old["commitment"],
        approved_at=old["approval"]["approved_at"],
    )["valid"] is True
    with pytest.raises(ValueError, match="source clause 1 is outside the supported repository grammar"):
        validate_policy_translation_commitment(
            old["proposal"]["source_policy"],
            old["proposal"]["authority"],
            old["commitment"],
            approved_at=old["approval"]["approved_at"],
            require_supported_source=True,
        )


@pytest.mark.parametrize("coverage", ["entirely_unsupported", "informational"])
def test_separate_mandatory_clause_blocks_the_direct_grant(coverage):
    source = b"Agents may modify README.md. Tech Lead approval is required before editing."
    draft = _base(source)
    grant, prerequisite = draft["source_statements"]
    start, end = prerequisite["start_byte"], prerequisite["end_byte"]
    unsupported = coverage == "entirely_unsupported"
    proposal = create_policy_translation_proposal(
        source,
        source_policy_id="repository-policy",
        source_revision="revision-1",
        authority_id="repository-authority",
        authority_version="1.0.0",
        clauses=[
            {
                "start_byte": grant["start_byte"],
                "end_byte": grant["end_byte"],
                "coverage_status": "fully_represented",
                "candidate_controls": [_path_control(
                    "README.md", source=source,
                    clause_start=grant["start_byte"], clause_end=grant["end_byte"],
                )],
                "unresolved_binding_ids": [],
                "limitation_code": None,
                "residual_unsupported_spans": [],
            },
            {
                "start_byte": start,
                "end_byte": end,
                "coverage_status": coverage,
                "candidate_controls": [],
                "unresolved_binding_ids": [],
                "limitation_code": "other" if unsupported else None,
                "residual_unsupported_spans": [{"start_byte": start, "end_byte": end}] if unsupported else [],
            },
        ],
        organizational_bindings=[],
        translation_runs=[_run(draft)],
    )
    grant, prerequisite = proposal["clauses"]
    state = apply_policy_translation_control_confirmation(
        proposal, None, clause_id=grant["clause_id"],
        candidate_control_id=grant["candidate_controls"][0]["candidate_control_id"],
        confirmed_by="synthetic-owner", confirmed_at="2026-09-03T12:01:00Z",
    )
    state = apply_policy_translation_disposition(
        proposal, state, clause_id=grant["clause_id"],
        coverage_status="fully_represented", reason_code="human-confirmed-complete",
        confirmed_by="synthetic-owner", confirmed_at="2026-09-03T12:02:00Z",
    )
    state = apply_policy_translation_disposition(
        proposal, state, clause_id=prerequisite["clause_id"],
        coverage_status=coverage, reason_code="not-enforceable" if unsupported else "context-only",
        acknowledge_unrepresented=unsupported,
        confirmed_by="synthetic-owner", confirmed_at="2026-09-03T12:02:00Z",
    )
    assert inspect_policy_translation_proposal(proposal, state)["publication_ready"] is False
    with pytest.raises(ValueError, match="source clause 2 is outside the supported repository grammar"):
        _approved(proposal, state)


def test_supported_approval_and_commitment_remain_available():
    proposal = _proposal(b"Agents may modify README.md. Agents must not modify files under deployment/.")
    state = _confirmed(proposal)
    assert inspect_policy_translation_proposal(proposal, state)["publication_ready"] is True
    approval = _approved(proposal, state)
    commitment = build_policy_translation_commitment(proposal, state, approval)
    assert validate_policy_translation_commitment(
        proposal["source_policy"], proposal["authority"], commitment,
        approved_at=approval["approved_at"],
    )["confirmed_control_count"] == 2
