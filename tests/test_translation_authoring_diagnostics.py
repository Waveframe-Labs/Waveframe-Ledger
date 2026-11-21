"""Review corrections: complete diagnostics and historical verification boundaries."""

import copy
import json
from pathlib import Path

import pytest

from governance_ledger import (
    inspect_policy_translation_customer_coverage,
    inspect_policy_translation_proposal,
    validate_authority_bundle_v3,
    validate_policy_translation_commitment,
)
from governance_ledger.publication_provenance import canonical_sha256
from tests.test_policy_translation import _approved, _confirmed, _proposal


def test_all_blockers_retain_exact_utf8_text_and_appear_in_one_refusal():
    source = "Agents may modify README.md. Café policy.\nTech Lead approval is required before editing.".encode()
    proposal = _proposal(source)
    state = _confirmed(proposal)
    inspection = inspect_policy_translation_proposal(proposal, state)
    blockers = inspection["source_coverage_blockers"]
    assert inspection["publication_ready"] is False
    assert [item["clause_index"] for item in blockers] == [2, 3]
    assert [item["source_text"] for item in blockers] == [
        "Café policy.\n", "Tech Lead approval is required before editing."
    ]
    for item in blockers:
        assert source[item["start_byte"]:item["end_byte"]] == item["source_text"].encode()
    assert blockers[1]["start_byte"] == source.index(b"Tech Lead")
    with pytest.raises(ValueError) as refusal:
        _approved(proposal, state)
    for item in blockers:
        message = str(refusal.value)
        assert f"source clause {item['clause_index']} is outside the supported repository grammar" in message
        assert f"[{item['start_byte']}, {item['end_byte']})" in message
        assert repr(item["source_text"]) in message
    assert "CATALOG_1_AUTHORING.md" in str(refusal.value)


@pytest.mark.parametrize("text", [
    "Policy overview.",
    "Tech Lead approval is required before editing.",
    "Log each change and obtain security approval.",
])
def test_informational_label_cannot_hide_a_customer_approval_blocker(text):
    source = ("Agents may modify README.md. " + text).encode()
    proposal = _proposal(source)
    assert proposal["clauses"][1]["coverage_status"] == "informational"
    view = inspect_policy_translation_customer_coverage(proposal, _confirmed(proposal))
    assert [row["customer_coverage_state"] for row in view["clauses"]] == [
        "Not currently enforceable", "Not currently enforceable"
    ]
    assert [row["blocks_approval"] for row in view["clauses"]] == [False, True]
    assert len(view["approval_blockers"]) == 1
    blocker = view["approval_blockers"][0]
    assert blocker["clause_id"] == proposal["clauses"][1]["clause_id"]
    assert blocker["source_text"] == text


def test_historical_standalone_verification_agrees_with_bundle_verification():
    path = Path(__file__).parent / "synthetic_evidence/deny_only_v2/historical-partial-v3.json"
    finalization = json.loads(path.read_text())["finalization"]
    bundle = finalization["authority_bundle"]
    assert validate_authority_bundle_v3(bundle)["provenance_complete"] is True
    authority = {key: bundle["authority"][key] for key in (
        "authority_id", "authority_version", "authority_ref"
    )}
    result = validate_policy_translation_commitment(
        bundle["source_policy"], authority, bundle["policy_translation_commitment"],
        approved_at=bundle["approval_record"]["approved_at"],
    )
    assert result["valid"] is True
    with pytest.raises(ValueError, match="outside the supported repository grammar"):
        validate_policy_translation_commitment(
            bundle["source_policy"], authority, bundle["policy_translation_commitment"],
            approved_at=bundle["approval_record"]["approved_at"], require_supported_source=True,
        )


def test_historical_mode_still_rejects_restamped_source_span_tampering():
    path = Path(__file__).parent / "synthetic_evidence/mandatory_translation_coverage.json"
    old = json.loads(path.read_text())["R11"]["false_full"]
    commitment = copy.deepcopy(old["commitment"])
    commitment["clauses"][0]["end_byte"] -= 1
    payload = {key: value for key, value in commitment.items()
               if key not in {"commitment_id", "commitment_hash"}}
    commitment["commitment_hash"] = canonical_sha256(payload)
    commitment["commitment_id"] = "policy-translation-commitment-" + commitment["commitment_hash"].removeprefix("sha256:")
    with pytest.raises(ValueError):
        validate_policy_translation_commitment(
            old["proposal"]["source_policy"], old["proposal"]["authority"], commitment,
            approved_at=old["approval"]["approved_at"],
        )
