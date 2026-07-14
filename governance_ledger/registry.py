"""Published contract registry index for Governance-Ledger."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from governance_ledger.paths import artifact_path
from governance_ledger.schema_versions import CONTRACT_REGISTRY_V1


_LIFECYCLE_STATES = {"active", "superseded", "revoked"}


def update_contract_registry(
    contracts_dir: str | Path,
    *,
    compiled_contract: dict[str, Any],
    contract_path: str | Path,
    published_at: str,
    published_by: str,
) -> dict[str, Any]:
    """Create or update contracts/index.json with a published contract entry."""
    contracts_root = Path(contracts_dir)
    contracts_root.mkdir(parents=True, exist_ok=True)
    index_path = contracts_root / "index.json"
    registry = _read_registry(index_path)
    entry = _registry_entry(
        compiled_contract,
        contract_path=contract_path,
        published_at=published_at,
        published_by=published_by,
    )

    contracts = [
        existing
        for existing in registry["contracts"]
        if not _same_contract(existing, entry)
    ]
    contracts.append(entry)
    registry = build_contract_registry(
        contracts,
        generated_at=published_at,
    )
    _write_json(index_path, registry)
    return registry


def load_contract_registry(contracts_dir: str | Path = "contracts") -> dict[str, Any]:
    """Load contracts/index.json, returning an empty registry if absent."""
    return _read_registry(Path(contracts_dir) / "index.json")


def resolve_authority_ref(
    authority_ref: str,
    *,
    contracts_dir: str | Path = "contracts",
) -> dict[str, Any]:
    """Resolve an explicit versioned authority reference from the local registry."""
    if not _is_explicit_authority_ref(authority_ref):
        raise ValueError("Authority resolution requires an explicit versioned reference like name@1.2.0.")

    registry = load_contract_registry(contracts_dir)
    validate_registry_hash(registry)
    matches = [
        entry
        for entry in registry.get("contracts", [])
        if entry.get("authority_ref") == authority_ref
    ]
    if not matches:
        raise ValueError(f"Authority reference not found: {authority_ref}")
    if len(matches) > 1:
        raise ValueError(f"Registry contains duplicate entries for {authority_ref}.")
    entry = matches[0]
    if not entry.get("bundle_path") or not entry.get("bundle_hash"):
        raise ValueError(f"Registry entry for {authority_ref} does not identify a canonical authority bundle.")
    return {
        "authority_ref": entry["authority_ref"],
        "lifecycle_state": entry.get("lifecycle_state", "active"),
        "publication_id": entry.get("publication_id"),
        "contract_hash": entry.get("contract_hash"),
        "bundle_hash": entry.get("bundle_hash"),
        "bundle_path": entry.get("bundle_path"),
        "contract_path": entry.get("path"),
        "published_at": entry.get("published_at"),
        "published_by": entry.get("published_by"),
    }


def _registry_entry(
    compiled_contract: dict[str, Any],
    *,
    contract_path: str | Path,
    published_at: str,
    published_by: str,
) -> dict[str, str]:
    if not published_at:
        raise ValueError("Published contract registry entries require published_at.")
    contract_hash = compiled_contract["contract_hash"]
    if not contract_hash.startswith("sha256:"):
        contract_hash = f"sha256:{contract_hash}"
    return {
        "contract_id": compiled_contract["contract_id"],
        "contract_version": compiled_contract["contract_version"],
        "authority_ref": f"{compiled_contract['contract_id']}@{compiled_contract['contract_version']}",
        "contract_ref": f"{compiled_contract['contract_id']}@{compiled_contract['contract_version']}",
        "contract_hash": contract_hash,
        "path": artifact_path(contract_path),
        "published_at": published_at,
        "published_by": published_by,
    }


def build_contract_registry(
    contracts: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Return canonical registry/index.json payload with integrity metadata."""
    normalized_contracts = [_normalize_registry_entry(entry) for entry in contracts]
    normalized_contracts = sorted(
        normalized_contracts,
        key=lambda item: item["authority_ref"],
    )
    registry = {
        "schema_version": CONTRACT_REGISTRY_V1,
        "generated_at": generated_at,
        "contracts": normalized_contracts,
        "latest": _latest_by_contract(normalized_contracts),
    }
    registry["registry_hash"] = compute_registry_hash(registry)
    return registry


def validate_registry_identity(
    existing_registry: dict[str, Any],
    new_entry: dict[str, Any],
) -> None:
    """Reject same authority_ref with different immutable publication identity."""
    authority_ref = new_entry.get("authority_ref")
    for existing in existing_registry.get("contracts", []):
        if existing.get("authority_ref") != authority_ref:
            continue
        for field in ("contract_hash", "bundle_hash"):
            if existing.get(field) != new_entry.get(field):
                raise ValueError(
                    f"Refusing to republish {authority_ref} with different {field}."
                )


def compute_registry_hash(registry: dict[str, Any]) -> str:
    """Compute registry hash over canonical JSON excluding registry_hash."""
    canonical_registry = {
        key: value
        for key, value in registry.items()
        if key != "registry_hash"
    }
    canonical = json.dumps(canonical_registry, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def validate_registry_hash(registry: dict[str, Any]) -> None:
    expected = registry.get("registry_hash")
    if not expected:
        raise ValueError("Registry missing registry_hash.")
    actual = compute_registry_hash(registry)
    if actual != expected:
        raise ValueError("Registry hash mismatch.")


def _normalize_registry_entry(entry: dict[str, Any]) -> dict[str, Any]:
    contract_id = entry["contract_id"]
    contract_version = entry["contract_version"]
    authority_ref = f"{contract_id}@{contract_version}"
    contract_hash = entry["contract_hash"]
    if not contract_hash.startswith("sha256:"):
        contract_hash = f"sha256:{contract_hash}"
    normalized = {
        **entry,
        "contract_id": contract_id,
        "contract_version": contract_version,
        "authority_ref": authority_ref,
        "contract_ref": authority_ref,
        "contract_hash": contract_hash,
        "path": artifact_path(entry["path"]),
    }
    if "bundle_path" in normalized:
        normalized["bundle_path"] = artifact_path(normalized["bundle_path"])
    if normalized.get("lifecycle_state") not in _LIFECYCLE_STATES:
        normalized["lifecycle_state"] = "active"
    return normalized


def _latest_by_contract(contracts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in contracts:
        current = latest.get(entry["contract_id"])
        if current is None or _version_tuple(entry["contract_version"]) > _version_tuple(current["contract_version"]):
            latest[entry["contract_id"]] = entry
    return latest


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        return (-1, -1, -1)
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return (-1, -1, -1)


def _same_contract(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("contract_id") == right.get("contract_id")
        and left.get("contract_version") == right.get("contract_version")
    )


def _is_explicit_authority_ref(value: str) -> bool:
    if not isinstance(value, str) or value.count("@") != 1:
        return False
    authority_id, version = value.split("@", 1)
    if not authority_id or version in {"latest", "active"}:
        return False
    parts = version.split(".")
    if len(parts) != 3:
        return False
    return all(part.isdigit() for part in parts)


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"contracts": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
