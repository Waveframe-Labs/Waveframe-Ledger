import json
from pathlib import Path

import pytest

from governance_ledger.publish import approve_review_file, publish_review_file
from governance_ledger.runner import run_policy_directory


def test_run_policy_directory_generates_draft_artifacts_only(tmp_path):
    policies_dir = tmp_path / "policies"
    generated_dir = tmp_path / "generated"
    reviews_dir = tmp_path / "reviews"
    contracts_dir = tmp_path / "contracts"
    policies_dir.mkdir()
    (policies_dir / "finance_policy.txt").write_text(
        "Transfers above $1M require manager approval.\n"
        "Proposer and approver must be separate.\n",
        encoding="utf-8",
    )

    results = run_policy_directory(
        policies_dir,
        generated_dir=generated_dir,
        reviews_dir=reviews_dir,
    )

    assert results == [
        {
            "policy": str(policies_dir / "finance_policy.txt"),
            "generated": str(generated_dir / "finance_policy.generated.json"),
            "validation": str(generated_dir / "finance_policy.validation.json"),
            "review": str(reviews_dir / "finance_policy.review.json"),
        },
    ]
    assert (generated_dir / "finance_policy.generated.json").exists()
    assert (generated_dir / "finance_policy.validation.json").exists()
    assert not contracts_dir.exists()

    review = json.loads((reviews_dir / "finance_policy.review.json").read_text())
    assert review["review_status"] == "pending"


def test_run_policy_directory_does_not_overwrite_existing_review(tmp_path):
    policies_dir, generated_dir, reviews_dir, contracts_dir, snapshots_dir = _draft_policy(tmp_path)
    review_path = reviews_dir / "finance_policy.review.json"
    approve_review_file(
        review_path,
        actor="governance-team",
        timestamp="2026-05-09T12:00:00Z",
    )

    run_policy_directory(
        policies_dir,
        generated_dir=generated_dir,
        reviews_dir=reviews_dir,
    )

    review = json.loads(review_path.read_text())
    assert review["review_status"] == "approved"


def test_publish_review_file_requires_approved_review(tmp_path):
    policies_dir, generated_dir, reviews_dir, contracts_dir, snapshots_dir = _draft_policy(tmp_path)
    review_path = reviews_dir / "finance_policy.review.json"

    with pytest.raises(ValueError, match="approved"):
        publish_review_file(
            review_path,
            generated_dir=generated_dir,
            contracts_dir=contracts_dir,
            reviews_dir=reviews_dir,
            snapshots_dir=snapshots_dir,
        )


def test_approve_then_publish_creates_contract_review_and_snapshot_artifacts(tmp_path):
    policies_dir, generated_dir, reviews_dir, contracts_dir, snapshots_dir = _draft_policy(tmp_path)
    review_path = reviews_dir / "finance_policy.review.json"

    approved_review = approve_review_file(
        review_path,
        actor="governance-team",
        timestamp="2026-05-09T12:00:00Z",
    )
    result = publish_review_file(
        review_path,
        generated_dir=generated_dir,
        contracts_dir=contracts_dir,
        reviews_dir=reviews_dir,
        snapshots_dir=snapshots_dir,
        timestamp="2026-05-09T12:30:00Z",
    )

    assert approved_review["review_status"] == "approved"
    assert Path(result["contract"]).parent == contracts_dir
    assert Path(result["deployed_review"]).parent == reviews_dir
    assert Path(result["snapshot"]).parent == snapshots_dir
    assert Path(result["contract"]).name.endswith(".contract.json")

    deployed_review = json.loads(Path(result["deployed_review"]).read_text())
    assert deployed_review["review_status"] == "deployed"
    assert deployed_review["compiled_contract"]["contract_hash"]
    assert deployed_review["deployment"]["environment"] == "production"


def _draft_policy(tmp_path):
    policies_dir = tmp_path / "policies"
    generated_dir = tmp_path / "generated"
    reviews_dir = tmp_path / "reviews"
    contracts_dir = tmp_path / "contracts"
    snapshots_dir = tmp_path / "snapshots"
    policies_dir.mkdir()
    (policies_dir / "finance_policy.txt").write_text(
        "Transfers above $1M require manager approval.\n"
        "Proposer and approver must be separate.\n",
        encoding="utf-8",
    )
    run_policy_directory(
        policies_dir,
        generated_dir=generated_dir,
        reviews_dir=reviews_dir,
    )
    return policies_dir, generated_dir, reviews_dir, contracts_dir, snapshots_dir
