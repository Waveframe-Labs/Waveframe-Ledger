"""Operational approval and publish workflows for Governance-Ledger reviews."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from governance_ledger.contract_linkage import attach_compiled_contract
from governance_ledger.deployment import attach_deployment
from governance_ledger.lifecycle import transition_review_status
from governance_ledger.snapshot import create_snapshot


def approve_review_file(
    review_path: str | Path,
    *,
    actor: str,
    timestamp: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Approve a pending or reviewed review artifact in place."""
    path = Path(review_path)
    review = _read_json(path)

    if review.get("review_status") == "pending":
        review = transition_review_status(
            review,
            "reviewed",
            actor=actor,
            timestamp=timestamp,
            note="Reviewed generated governance artifact.",
        )
    if review.get("review_status") == "reviewed":
        review = transition_review_status(
            review,
            "approved",
            actor=actor,
            timestamp=timestamp,
            note=note or "Approved governance artifact for publishing.",
        )
    elif review.get("review_status") != "approved":
        raise ValueError("Only pending, reviewed, or approved reviews can be approved.")

    approval_timestamp = review["lifecycle"][-1]["timestamp"]
    approval_note = review["lifecycle"][-1]["note"]
    review["approved_by"] = actor
    review["approved_at"] = approval_timestamp
    review["approval_note"] = approval_note

    _write_json(path, review)
    return review


def publish_review_file(
    review_path: str | Path,
    *,
    generated_dir: str | Path = "generated",
    contracts_dir: str | Path = "contracts",
    reviews_dir: str | Path = "reviews",
    snapshots_dir: str | Path = "snapshots",
    actor: str = "governance-team",
    compiler_actor: str = "compiler-service",
    deployed_by: str = "ops-team",
    environment: str = "production",
    runtime: str = "waveframe-guard",
    enforcement_engine_version: str = "0.12.0",
    timestamp: str | None = None,
) -> dict[str, str]:
    """Publish an approved review into contract, deployed review, and snapshot artifacts."""
    review_input_path = Path(review_path)
    review = _read_json(review_input_path)
    if review.get("review_status") != "approved":
        raise ValueError("Publishing requires review_status == 'approved'.")

    policy_stem = _policy_stem_from_review_path(review_input_path)
    generated_path = Path(generated_dir) / f"{policy_stem}.generated.json"
    structured_policy = _read_json(generated_path)

    compiled_contract = _compile_policy(structured_policy)
    contract_path = Path(contracts_dir) / _contract_filename(compiled_contract)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(contract_path, compiled_contract)

    compiled_review = attach_compiled_contract(
        review,
        compiled_contract,
        actor=compiler_actor,
        timestamp=timestamp,
    )
    deployed_review = attach_deployment(
        compiled_review,
        environment=environment,
        runtime=runtime,
        deployed_by=deployed_by,
        enforcement_engine_version=enforcement_engine_version,
        timestamp=timestamp,
    )
    deployed_review["published_by"] = actor

    deployed_review_path = Path(reviews_dir) / f"{policy_stem}.deployed.review.json"
    deployed_review_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(deployed_review_path, deployed_review)

    snapshot = create_snapshot(deployed_review, created_at=timestamp)
    snapshot_path = Path(snapshots_dir) / f"{snapshot['snapshot_id']}.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(snapshot_path, snapshot)

    manifest = _build_publication_manifest(
        compiled_contract,
        contract_path=contract_path,
        deployed_review_path=deployed_review_path,
        snapshot_path=snapshot_path,
        published_at=timestamp,
        published_by=actor,
    )
    manifest_path = Path(contracts_dir) / f"{policy_stem}.publication_manifest.json"
    _write_json(manifest_path, manifest)

    return {
        "contract": str(contract_path),
        "deployed_review": str(deployed_review_path),
        "manifest": str(manifest_path),
        "snapshot": str(snapshot_path),
    }


def _compile_policy(policy: dict[str, Any]) -> dict[str, Any]:
    try:
        from compiler.compile_policy import compile_policy
    except ImportError:
        return _example_compile_policy(policy, "canonical compiler unavailable")

    try:
        compiled_contract = compile_policy(policy)
    except Exception as exc:
        return _example_compile_policy(
            policy,
            f"canonical compiler rejected v0.1 policy shape: {exc}",
        )
    if not compiled_contract.get("contract_id") or not compiled_contract.get("contract_version"):
        return _example_compile_policy(
            policy,
            "canonical compiler output missing contract identity fields",
        )
    return compiled_contract


def _example_compile_policy(policy: dict[str, Any], compiler_note: str) -> dict[str, Any]:
    compiled_contract = {
        "contract_id": policy.get("contract_id", "finance-policy"),
        "contract_version": policy.get("contract_version", "0.1.0"),
        "schema_version": "example-compiled-contract/v0.1",
        "compiler": "governance-ledger-example",
        "compiler_note": compiler_note,
        "authority": policy.get("authority", {}),
        "approvals": policy.get("approvals", {}),
        "invariants": policy.get("invariants", {}),
    }
    compiled_contract["contract_hash"] = _canonical_hash(compiled_contract)
    return compiled_contract


def _canonical_hash(payload: dict[str, Any]) -> str:
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()


def _contract_filename(compiled_contract: dict[str, Any]) -> str:
    contract_id = compiled_contract["contract_id"]
    contract_version = compiled_contract["contract_version"]
    return f"{contract_id}-{contract_version}.contract.json"


def _build_publication_manifest(
    compiled_contract: dict[str, Any],
    *,
    contract_path: Path,
    deployed_review_path: Path,
    snapshot_path: Path,
    published_at: str | None,
    published_by: str,
) -> dict[str, Any]:
    contract_hash = compiled_contract["contract_hash"]
    if not contract_hash.startswith("sha256:"):
        contract_hash = f"sha256:{contract_hash}"
    return {
        "published_at": published_at,
        "published_by": published_by,
        "contracts": [
            {
                "contract_id": compiled_contract["contract_id"],
                "contract_version": compiled_contract["contract_version"],
                "contract_hash": contract_hash,
                "path": str(contract_path),
            }
        ],
        "reviews": [
            {
                "path": str(deployed_review_path),
            }
        ],
        "snapshots": [
            {
                "path": str(snapshot_path),
            }
        ],
    }


def _policy_stem_from_review_path(review_path: Path) -> str:
    name = review_path.name
    suffix = ".review.json"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return review_path.stem


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
