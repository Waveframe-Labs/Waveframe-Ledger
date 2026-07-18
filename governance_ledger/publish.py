"""Operational approval and publish workflows for Governance-Ledger reviews."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from governance_ledger.contract_linkage import attach_compiled_contract
from governance_ledger.deployment import attach_deployment
from governance_ledger.lifecycle import transition_review_status
from governance_ledger.paths import artifact_path
from governance_ledger.schema_versions import (
    COMPILED_AUTHORITY_CONTRACT_V1,
    PUBLICATION_MANIFEST_V1,
)
from governance_ledger.provenance import _utc_now
from governance_ledger.registry import (
    build_contract_registry,
    validate_registry_identity,
    validate_registry_hash,
)
from governance_ledger.semantics.preview import build_governance_impact_preview
from governance_ledger.semantics.publication import build_authority_bundle, build_publication_receipt
from governance_ledger.snapshot import create_snapshot
from governance_ledger.validation import has_validation_errors, validate_compiler_policy


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
    review_errors = [
        warning
        for warning in review.get("warnings", [])
        if warning.get("severity") == "error"
    ]
    if review_errors:
        messages = "; ".join(warning.get("text", "governance validation error") for warning in review_errors)
        raise ValueError(f"Publishing requires governance validation to pass: {messages}")
    published_at = timestamp or _utc_now()

    policy_stem = _policy_stem_from_review_path(review_input_path)
    generated_path = Path(generated_dir) / f"{policy_stem}.generated.json"
    structured_policy = _read_json(generated_path)
    compiler_validation = validate_compiler_policy(structured_policy)
    if has_validation_errors(compiler_validation):
        raise ValueError(
            "Publishing requires generated policy to match the canonical compiler ingestion schema."
        )

    compiled_contract = _compile_policy(
        structured_policy,
        lineage=_publication_lineage(review),
    )
    contract_path = Path(contracts_dir) / _contract_filename(compiled_contract)
    manifest_path = Path(contracts_dir) / f"{policy_stem}.publication_manifest.json"
    publication_id = _publication_id(
        published_at,
        contracts_dir=Path(contracts_dir),
        manifest_path=manifest_path,
    )

    compiled_review = attach_compiled_contract(
        review,
        compiled_contract,
        actor=compiler_actor,
        timestamp=published_at,
    )
    deployed_review = attach_deployment(
        compiled_review,
        environment=environment,
        runtime=runtime,
        deployed_by=deployed_by,
        enforcement_engine_version=enforcement_engine_version,
        timestamp=published_at,
    )
    deployed_review["published_by"] = actor
    deployed_review["publication_id"] = publication_id

    deployed_review_path = Path(reviews_dir) / f"{policy_stem}.deployed.review.json"

    snapshot = create_snapshot(deployed_review, created_at=published_at)
    snapshot["publication_id"] = publication_id
    snapshot_path = Path(snapshots_dir) / f"{snapshot['snapshot_id']}.json"

    manifest = _build_publication_manifest(
        compiled_contract,
        publication_id=publication_id,
        contract_path=contract_path,
        deployed_review_path=deployed_review_path,
        snapshot_path=snapshot_path,
        published_at=published_at,
        published_by=actor,
    )
    authority_ref = f"{compiled_contract['contract_id']}@{compiled_contract['contract_version']}"
    authority_stem = f"{compiled_contract['contract_id']}-{compiled_contract['contract_version']}"
    bundle_path = Path(contracts_dir) / f"{authority_stem}.authority-bundle.json"
    receipt_path = Path(contracts_dir) / f"{authority_stem}.publication-receipt.json"

    governance_impact_preview = build_governance_impact_preview(compiled_contract)
    authority_bundle = build_authority_bundle(
        authority_contract=compiled_contract,
        publication_manifest=manifest,
        governance_impact_preview=governance_impact_preview,
    )
    publication_receipt = build_publication_receipt(
        authority_bundle=authority_bundle,
        published_at=published_at,
    )
    bundle_hash = publication_receipt["bundle_hash"]

    registry_path = Path(contracts_dir) / "index.json"
    registry = _build_next_registry(
        registry_path,
        compiled_contract=compiled_contract,
        contract_path=contract_path,
        bundle_path=bundle_path,
        bundle_hash=bundle_hash,
        publication_id=publication_id,
        published_at=published_at,
        published_by=actor,
    )

    transaction = _PublicationTransaction(publication_id)
    try:
        _validate_publication_payloads(
            compiled_contract=compiled_contract,
            authority_bundle=authority_bundle,
            registry=registry,
            manifest=manifest,
        )
        transaction.stage_json(contract_path, compiled_contract, immutable=True)
        transaction.stage_json(deployed_review_path, deployed_review)
        transaction.stage_json(snapshot_path, snapshot)
        transaction.stage_json(manifest_path, manifest, immutable=True)
        transaction.stage_json(bundle_path, authority_bundle, immutable=True)
        transaction.stage_json(receipt_path, publication_receipt, immutable=True)
        transaction.stage_json(registry_path, registry)
        transaction.commit()
        validate_registry_hash(_read_json(registry_path))
    except Exception:
        transaction.rollback()
        raise

    return {
        "contract": str(contract_path),
        "authority": authority_ref,
        "authority_bundle": str(bundle_path),
        "authority_bundle_hash": bundle_hash,
        "deployed_review": str(deployed_review_path),
        "manifest": str(manifest_path),
        "publication_id": publication_id,
        "publication_receipt": str(receipt_path),
        "publication_status": "COMMITTED",
        "registry": str(registry_path),
        "registry_hash": registry["registry_hash"],
        "snapshot": str(snapshot_path),
    }


def _compile_policy(
    policy: dict[str, Any],
    *,
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from compiler.compile_policy import compile_policy

    compiler_input = dict(policy)
    if lineage is not None:
        compiler_input["lineage"] = lineage
    compiled_contract = compile_policy(compiler_input)
    if lineage is not None:
        compiled_contract = _with_authority_lineage(compiled_contract, lineage)
    if not compiled_contract.get("contract_id") or not compiled_contract.get("contract_version"):
        raise ValueError("Canonical compiler output missing contract identity fields.")
    return compiled_contract


def _with_authority_lineage(
    compiled_contract: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    contract = dict(compiled_contract)
    schema_version = contract.get("schema_version")
    if schema_version not in {None, COMPILED_AUTHORITY_CONTRACT_V1}:
        raise ValueError(
            "Canonical compiler output has unsupported schema_version: "
            f"{schema_version}"
        )
    changed = False
    if schema_version is None:
        contract["schema_version"] = COMPILED_AUTHORITY_CONTRACT_V1
        changed = True
    if contract.get("lineage") != lineage:
        contract["lineage"] = dict(lineage)
        changed = True
    if changed:
        contract["contract_hash"] = _compute_contract_hash(contract)
    return contract


def _compute_contract_hash(compiled_contract: dict[str, Any]) -> str:
    canonical_contract = {
        key: value
        for key, value in compiled_contract.items()
        if key != "contract_hash"
    }
    canonical = json.dumps(canonical_contract, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _publication_lineage(review: dict[str, Any]) -> dict[str, Any]:
    compilation_report = review.get("compilation_report") or {}
    return {
        "schema_version": "governance_authority_lineage.v1",
        "source_hash": review.get("source_hash"),
        "compilation_report_hash": compilation_report.get("report_hash"),
        "review_id": review.get("review_id"),
    }


def _contract_filename(compiled_contract: dict[str, Any]) -> str:
    contract_id = compiled_contract["contract_id"]
    contract_version = compiled_contract["contract_version"]
    return f"{contract_id}-{contract_version}.contract.json"


def _build_publication_manifest(
    compiled_contract: dict[str, Any],
    *,
    publication_id: str,
    contract_path: Path,
    deployed_review_path: Path,
    snapshot_path: Path,
    published_at: str,
    published_by: str,
) -> dict[str, Any]:
    contract_hash = compiled_contract["contract_hash"]
    if not contract_hash.startswith("sha256:"):
        contract_hash = f"sha256:{contract_hash}"
    contract_entry = {
        "schema_version": PUBLICATION_MANIFEST_V1,
        "publication_id": publication_id,
        "published_at": published_at,
        "published_by": published_by,
        "contracts": [
            {
                "contract_id": compiled_contract["contract_id"],
                "contract_version": compiled_contract["contract_version"],
                "contract_hash": contract_hash,
                "path": artifact_path(contract_path),
            }
        ],
        "reviews": [
            {
                "path": artifact_path(deployed_review_path),
            }
        ],
        "snapshots": [
            {
                "path": artifact_path(snapshot_path),
            }
        ],
    }
    _attach_lineage_metadata(contract_entry["contracts"][0], compiled_contract)
    return contract_entry


def _policy_stem_from_review_path(review_path: Path) -> str:
    name = review_path.name
    suffix = ".review.json"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return review_path.stem


def _publication_id(
    published_at: str,
    *,
    contracts_dir: Path,
    manifest_path: Path | None = None,
) -> str:
    if manifest_path is not None and manifest_path.exists():
        existing = _read_json(manifest_path).get("publication_id")
        if isinstance(existing, str) and existing:
            return existing
    timestamp = "".join(character for character in published_at if character.isdigit())
    date = (timestamp[:8] or "00000000").ljust(8, "0")
    next_sequence = _next_publication_sequence(contracts_dir, date)
    return f"pub_{date}_{next_sequence:04d}"


def _next_publication_sequence(contracts_dir: Path, date: str) -> int:
    prefix = f"pub_{date}_"
    sequence = 0
    if contracts_dir.exists():
        for manifest_path in contracts_dir.glob("*.publication_manifest.json"):
            try:
                publication_id = _read_json(manifest_path).get("publication_id", "")
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(publication_id, str) and publication_id.startswith(prefix):
                suffix = publication_id[len(prefix):]
                if suffix.isdigit():
                    sequence = max(sequence, int(suffix))
    return sequence + 1


def _build_next_registry(
    registry_path: Path,
    *,
    compiled_contract: dict[str, Any],
    contract_path: Path,
    bundle_path: Path,
    bundle_hash: str,
    publication_id: str,
    published_at: str,
    published_by: str,
) -> dict[str, Any]:
    existing_registry = _read_json(registry_path) if registry_path.exists() else {"contracts": []}
    contract_id = compiled_contract["contract_id"]
    contract_version = compiled_contract["contract_version"]
    contract_hash = compiled_contract["contract_hash"]
    if not contract_hash.startswith("sha256:"):
        contract_hash = f"sha256:{contract_hash}"

    contracts = [
        entry
        for entry in existing_registry.get("contracts", [])
        if not (
            entry.get("contract_id") == contract_id
            and entry.get("contract_version") == contract_version
        )
    ]
    registry_entry = {
        "contract_id": contract_id,
        "contract_version": contract_version,
        "authority_ref": f"{contract_id}@{contract_version}",
        "contract_ref": f"{contract_id}@{contract_version}",
        "contract_hash": contract_hash,
        "path": artifact_path(contract_path),
        "bundle_path": artifact_path(bundle_path),
        "bundle_hash": bundle_hash,
        "lifecycle_state": "active",
        "publication_id": publication_id,
        "published_at": published_at,
        "published_by": published_by,
    }
    _attach_lineage_metadata(registry_entry, compiled_contract)
    validate_registry_identity(existing_registry, registry_entry)
    contracts = [
        entry
        for entry in contracts
        if entry.get("authority_ref") != registry_entry["authority_ref"]
    ]
    contracts.append(registry_entry)
    return build_contract_registry(contracts, generated_at=published_at)


def _attach_lineage_metadata(target: dict[str, Any], compiled_contract: dict[str, Any]) -> None:
    lineage = compiled_contract.get("lineage") or {}
    for key in ["source_hash", "compilation_report_hash"]:
        if lineage.get(key) is not None:
            target[key] = lineage[key]


def _validate_publication_payloads(
    *,
    compiled_contract: dict[str, Any],
    authority_bundle: dict[str, Any],
    registry: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    contract_id = compiled_contract.get("contract_id")
    contract_version = compiled_contract.get("contract_version")
    contract_hash = compiled_contract.get("contract_hash")
    if not contract_id or not contract_version or not contract_hash:
        raise ValueError("Publication requires contract_id, contract_version, and contract_hash.")
    if not manifest.get("publication_id"):
        raise ValueError("Publication manifest missing publication_id.")
    normalized_hash = contract_hash if contract_hash.startswith("sha256:") else f"sha256:{contract_hash}"
    authority_ref = f"{contract_id}@{contract_version}"
    if authority_bundle.get("authority_ref") != authority_ref:
        raise ValueError(f"Authority bundle reference does not match compiled contract for {authority_ref}.")
    if authority_bundle.get("contract_hash") != normalized_hash:
        raise ValueError(f"Authority bundle hash entry does not match compiled contract for {authority_ref}.")

    validate_registry_hash(registry)
    matches = [
        entry
        for entry in registry.get("contracts", [])
        if entry.get("authority_ref") == authority_ref
    ]
    if len(matches) != 1:
        raise ValueError(f"Registry must contain exactly one entry for {authority_ref}.")
    if matches[0].get("contract_hash") != normalized_hash:
        raise ValueError(f"Registry hash entry does not match compiled contract for {authority_ref}.")
    if matches[0].get("bundle_path") is None or matches[0].get("bundle_hash") is None:
        raise ValueError(f"Registry entry must identify the canonical authority bundle for {authority_ref}.")
    if matches[0].get("lifecycle_state") not in {"active", "superseded", "revoked"}:
        raise ValueError(f"Registry lifecycle_state is invalid for {authority_ref}.")


class _PublicationTransaction:
    def __init__(self, publication_id: str) -> None:
        self.publication_id = publication_id
        self._staged: list[dict[str, Any]] = []
        self._committed: list[dict[str, Any]] = []

    def stage_json(
        self,
        path: Path,
        payload: dict[str, Any],
        *,
        immutable: bool = False,
    ) -> None:
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if immutable and path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing != serialized:
                raise ValueError(f"Refusing to overwrite immutable publication output: {path}")
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        token = hashlib.sha256(f"{self.publication_id}:{path}".encode("utf-8")).hexdigest()[:12]
        temp_path = path.parent / f".{path.name}.{self.publication_id}.{token}.tmp"
        backup_path = path.parent / f".{path.name}.{self.publication_id}.{token}.bak"
        temp_path.write_text(serialized, encoding="utf-8")
        self._staged.append(
            {
                "path": path,
                "temp_path": temp_path,
                "backup_path": backup_path,
                "existed": path.exists(),
            }
        )

    def commit(self) -> None:
        try:
            for item in self._staged:
                path = item["path"]
                temp_path = item["temp_path"]
                backup_path = item["backup_path"]
                if path.exists():
                    shutil.copy2(path, backup_path)
                temp_path.replace(path)
                self._committed.append(item)
        except Exception:
            self.rollback()
            raise

    def rollback(self) -> None:
        for item in reversed(self._committed):
            path = item["path"]
            backup_path = item["backup_path"]
            if backup_path.exists():
                backup_path.replace(path)
            elif path.exists():
                path.unlink()
        for item in self._staged:
            temp_path = item["temp_path"]
            backup_path = item["backup_path"]
            if temp_path.exists():
                temp_path.unlink()
            if backup_path.exists():
                backup_path.unlink()
        self._committed.clear()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_immutable_json(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != serialized:
            raise ValueError(f"Refusing to overwrite immutable publication output: {path}")
        return
    path.write_text(serialized, encoding="utf-8")
