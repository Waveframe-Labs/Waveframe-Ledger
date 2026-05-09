import json
from pathlib import Path

import pytest

from governance_ledger.publish import approve_review_file, publish_review_file
from governance_ledger.runner import run_policy_directory
from governance_ledger.checks import check_validation_directory
from governance_ledger.summary import build_pr_summary, format_run_summary


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
            "review_id": "review-finance_policy",
            "review_status": "pending",
            "review_created": True,
            "constraint_count": 3,
            "warning_count": 0,
            "ambiguity_count": 0,
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
        note="Approved finance governance.",
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
    assert approved_review["approved_by"] == "governance-team"
    assert approved_review["approved_at"] == "2026-05-09T12:00:00Z"
    assert approved_review["approval_note"] == "Approved finance governance."
    assert Path(result["contract"]).parent == contracts_dir
    assert Path(result["deployed_review"]).parent == reviews_dir
    assert Path(result["manifest"]).parent == contracts_dir
    assert Path(result["snapshot"]).parent == snapshots_dir
    assert Path(result["contract"]).name.endswith(".contract.json")

    deployed_review = json.loads(Path(result["deployed_review"]).read_text())
    assert deployed_review["review_status"] == "deployed"
    assert deployed_review["compiled_contract"]["contract_hash"]
    assert deployed_review["deployment"]["environment"] == "production"

    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["published_at"] == "2026-05-09T12:30:00Z"
    assert manifest["contracts"][0]["contract_hash"].startswith("sha256:")
    assert manifest["contracts"][0]["path"] == result["contract"]


def test_check_validation_directory_fails_on_error_severity(tmp_path):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    (generated_dir / "policy.validation.json").write_text(
        json.dumps(
            {
                "warnings": [
                    {
                        "type": "ambiguous_authority",
                        "severity": "error",
                        "text": "appropriate manager",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = check_validation_directory(generated_dir)

    assert result["status"] == "failed"
    assert result["error_count"] == 1


def test_format_run_summary_exposes_operational_counts(tmp_path):
    policies_dir, generated_dir, reviews_dir, contracts_dir, snapshots_dir = _draft_policy(tmp_path)
    results = run_policy_directory(
        policies_dir,
        generated_dir=generated_dir,
        reviews_dir=reviews_dir,
    )

    summary = format_run_summary(results)

    assert "[Governance Ledger]" in summary
    assert "Policy: finance_policy.txt" in summary
    assert "3 constraints detected" in summary
    assert "0 ambiguity warnings detected" in summary
    assert "pending human approval" in summary
    assert "review-finance_policy preserved" in summary


def test_build_pr_summary_formats_constraints_warnings_and_status():
    review = {
        "source_document": "finance_policy.txt",
        "review_status": "pending",
        "detected_constraints": [
            {
                "type": "required_role",
                "value": "manager",
                "source_text": "require manager approval",
            },
            {
                "type": "approval_threshold",
                "operation": "transfer_funds",
                "value": 1_000_000,
                "source_text": "above $1M",
            },
            {
                "type": "separation_of_duties",
                "value": True,
                "source_text": "must be separate",
            },
        ],
        "warnings": [
            {
                "type": "ambiguous_authority",
                "severity": "error",
                "text": "appropriate manager",
            },
        ],
    }

    summary = build_pr_summary(review)

    assert "## Governance Review Summary" in summary
    assert "Policy: finance_policy.txt" in summary
    assert "- required_role: manager" in summary
    assert "- threshold: transfer_funds > 1000000" in summary
    assert "- separation_of_duties" in summary
    assert 'error: ambiguous clause: "appropriate manager"' in summary
    assert "BLOCKED_PENDING_REVIEW" in summary


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
