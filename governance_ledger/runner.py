"""Operational draft generation for Governance-Ledger policy directories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governance_ledger.extract import extract_constraints
from governance_ledger.review import build_review_report
from governance_ledger.validation import validate_authoring


def run_policy_directory(
    policies_dir: str | Path,
    *,
    generated_dir: str | Path = "generated",
    reviews_dir: str | Path = "reviews",
) -> list[dict[str, str]]:
    """Generate draft policy and pending review artifacts for policy text files."""
    policy_root = Path(policies_dir)
    generated_root = Path(generated_dir)
    reviews_root = Path(reviews_dir)
    generated_root.mkdir(parents=True, exist_ok=True)
    reviews_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, str]] = []
    for policy_path in sorted(policy_root.glob("*.txt")):
        results.append(
            run_policy_file(
                policy_path,
                generated_dir=generated_root,
                reviews_dir=reviews_root,
            )
        )
    return results


def run_policy_file(
    policy_path: str | Path,
    *,
    generated_dir: str | Path = "generated",
    reviews_dir: str | Path = "reviews",
) -> dict[str, str]:
    """Generate draft artifacts for one policy file without approval or publishing."""
    input_path = Path(policy_path)
    generated_root = Path(generated_dir)
    reviews_root = Path(reviews_dir)
    generated_root.mkdir(parents=True, exist_ok=True)
    reviews_root.mkdir(parents=True, exist_ok=True)

    policy_text = input_path.read_text(encoding="utf-8")
    structured_policy = extract_constraints(policy_text)
    validation = validate_authoring(policy_text, structured_policy)
    review = build_review_report(
        policy_text,
        structured_policy,
        review_id=f"review-{input_path.stem}",
        source_document=input_path.name,
        review_status="pending",
    )

    generated_path = generated_root / f"{input_path.stem}.generated.json"
    validation_path = generated_root / f"{input_path.stem}.validation.json"
    review_path = reviews_root / f"{input_path.stem}.review.json"

    _write_json(generated_path, structured_policy)
    _write_json(validation_path, validation)
    review_created = not review_path.exists()
    if review_created:
        _write_json(review_path, review)
        review_for_summary = review
    else:
        review_for_summary = json.loads(review_path.read_text(encoding="utf-8"))

    return {
        "policy": str(input_path),
        "generated": str(generated_path),
        "validation": str(validation_path),
        "review": str(review_path),
        "review_id": review_for_summary["review_id"],
        "review_status": review_for_summary["review_status"],
        "review_created": review_created,
        "constraint_count": len(review["detected_constraints"]),
        "warning_count": len(review["warnings"]),
        "ambiguity_count": sum(
            1 for warning in review["warnings"] if warning["type"] == "ambiguous_authority"
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
