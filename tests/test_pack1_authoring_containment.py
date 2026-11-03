"""New authoring refuses implicit grants; historical validators remain unchanged."""
import copy
import json
from pathlib import Path

import pytest

from governance_ledger import (
    finalize_domain_policy_authority, finalize_policy_translation_authority,
    finalize_policy_translation_authority_v3, validate_authority_bundle, validate_publication_receipt,
)
from tests.test_domain_policy import _draft, HUMAN
from tests.test_policy_translation import _proposal, _confirmed, _approved

FIXTURES = Path(__file__).parent / "synthetic_evidence" / "deny_only_v2"
PUBLICATION = dict(committed_by="synthetic-committer", committed_at="2026-09-03T12:04:00Z",
                   publication_id="synthetic-publication", published_by="synthetic-publisher", published_at="2026-09-03T12:05:00Z")


@pytest.mark.parametrize("source", [b"Agents must not modify files under deployment/.",
    b"Repository changes may be made only by repository maintainers.",
    b"Repository changes may be made only by repository maintainers. Agents must not modify files under deployment/."])
def test_new_domain_finalization_requires_path_allow(source):
    draft = _draft(source)
    original = copy.deepcopy(draft)
    with pytest.raises(ValueError, match="affirmative path grant"):
        finalize_domain_policy_authority(draft, **HUMAN)
    assert draft == original  # historical interpretation identity/status stays stable


def test_new_translation_approval_requires_path_allow():
    proposal = _proposal(b"Agents must not modify files under deployment/.")
    state = _confirmed(proposal)
    from governance_ledger import inspect_policy_translation_proposal
    assert inspect_policy_translation_proposal(proposal, state)["publication_ready"] is False
    with pytest.raises(ValueError, match="fresh human acceptance"):
        _approved(proposal, state)


def test_candidate_allow_requires_individual_confirmation_and_enforced_disposition():
    from governance_ledger import (
        apply_policy_translation_control_confirmation, apply_policy_translation_disposition,
        inspect_policy_translation_proposal,
    )
    proposal = _proposal(b"Agents must not modify files under deployment/. Agents may modify README.md.")
    deny, allow = proposal["clauses"]
    state = apply_policy_translation_control_confirmation(
        proposal, None, clause_id=deny["clause_id"],
        candidate_control_id=deny["candidate_controls"][0]["candidate_control_id"],
        confirmed_by="synthetic-owner", confirmed_at="2026-09-03T12:01:00Z")
    state = apply_policy_translation_disposition(
        proposal, state, clause_id=deny["clause_id"], coverage_status="fully_represented",
        reason_code="human-confirmed-complete", confirmed_by="synthetic-owner",
        confirmed_at="2026-09-03T12:02:00Z")
    assert inspect_policy_translation_proposal(proposal, state)["publication_ready"] is False
    with pytest.raises(ValueError, match="coverage decision|individual confirmation"):
        _approved(proposal, state)
    state = apply_policy_translation_control_confirmation(
        proposal, state, clause_id=allow["clause_id"],
        candidate_control_id=allow["candidate_controls"][0]["candidate_control_id"],
        confirmed_by="synthetic-owner", confirmed_at="2026-09-03T12:01:00Z")
    assert inspect_policy_translation_proposal(proposal, state)["publication_ready"] is False
    with pytest.raises(ValueError, match="coverage decision"):
        _approved(proposal, state)
    state = apply_policy_translation_disposition(
        proposal, state, clause_id=allow["clause_id"], coverage_status="fully_represented",
        reason_code="human-confirmed-complete", confirmed_by="synthetic-owner",
        confirmed_at="2026-09-03T12:02:00Z")
    assert inspect_policy_translation_proposal(proposal, state)["publication_ready"] is True
    _approved(proposal, state)


@pytest.mark.parametrize("status", ["informational", "entirely_unsupported"])
def test_unenforceable_clause_cannot_supply_an_allow(status):
    from governance_ledger import validate_policy_translation_proposal
    from tests.test_policy_translation import _restamp_proposal
    proposal = _proposal(b"Agents may modify README.md.")
    proposal["clauses"][0]["coverage_status"] = status
    _restamp_proposal(proposal)
    with pytest.raises(ValueError, match="cannot be downgraded"):
        validate_policy_translation_proposal(proposal)
    with pytest.raises(ValueError, match="cannot be downgraded"):
        _approved(proposal, _confirmed(_proposal(b"Agents may modify README.md.")))


def test_historical_v2_and_v3_verify_without_reauthoring():
    bundle = json.loads((FIXTURES / "bundle.json").read_text(encoding="utf-8"))
    receipt = json.loads((FIXTURES / "receipt.json").read_text(encoding="utf-8"))
    historical = json.loads((FIXTURES / "historical-partial-v3.json").read_text(encoding="utf-8"))
    for pair in [(bundle, receipt), (historical["finalization"]["authority_bundle"], historical["finalization"]["publication_receipt"])]:
        original = copy.deepcopy(pair)
        assert validate_authority_bundle(pair[0])["provenance_complete"]
        validate_publication_receipt(*pair)
        assert pair == original
    # Even a historically valid approval cannot issue new deny-only authority.
    for finalizer in [finalize_policy_translation_authority, finalize_policy_translation_authority_v3]:
        with pytest.raises(ValueError, match="affirmative path grant|cannot represent"):
            finalizer(historical["proposal"], historical["confirmation"], historical["approval"], **PUBLICATION)


@pytest.mark.parametrize("finalizer", [finalize_policy_translation_authority, finalize_policy_translation_authority_v3])
def test_historical_deny_approval_cannot_issue_new_v2_or_v3_authority(finalizer):
    historical = json.loads((FIXTURES / "historical-deny-approval.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="affirmative path grant"):
        finalizer(historical["proposal"], historical["confirmation"], historical["approval"], **PUBLICATION)


def test_replacement_grants_require_new_bound_human_acceptance():
    historical = json.loads((FIXTURES / "historical-deny-approval.json").read_text(encoding="utf-8"))
    old_approval = historical["approval"]
    replacement = _proposal(b"Agents may modify CHANGELOG.md.")
    # Build a new proposal through the public interface, rather than rehash edited evidence.
    from governance_ledger import create_policy_translation_proposal, interpret_policy_with_domain_pack
    from tests.test_policy_translation import _run
    draft = interpret_policy_with_domain_pack(b"Agents may modify CHANGELOG.md.",
        domain_pack_id="repository-changes", domain_pack_version="1.0.0",
        source_policy_id="repository-policy", source_revision="revision-2",
        authority_id="repository-authority", authority_version="1.0.1")
    run = _run(draft)
    replacement = create_policy_translation_proposal(b"Agents may modify CHANGELOG.md.",
        source_policy_id="repository-policy", source_revision="revision-2", authority_id="repository-authority", authority_version="1.0.1",
        clauses=[{key: value for key, value in clause.items() if key in {"start_byte", "end_byte", "coverage_status", "candidate_controls", "unresolved_binding_ids", "limitation_code", "residual_unsupported_spans"}} for clause in replacement["clauses"]],
        organizational_bindings=[], translation_runs=[run])
    fresh_state = _confirmed(replacement)
    with pytest.raises(ValueError, match="approval.*inconsistent|approval binding"):
        finalize_policy_translation_authority_v3(replacement, fresh_state, old_approval, **PUBLICATION)
    fresh_approval = _approved(replacement, fresh_state)
    final = finalize_policy_translation_authority_v3(replacement, fresh_state, fresh_approval, **PUBLICATION)
    assert fresh_approval["approval_hash"] != old_approval["approval_hash"]
    assert final["compiled_authority_contract"]["contract_version"] == "1.0.1"
