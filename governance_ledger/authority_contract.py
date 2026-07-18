"""Canonical normalization for compiled authority contracts."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def with_authority_identity(
    compiled_contract: dict[str, Any],
    lineage: dict[str, Any],
    *,
    schema_version: str | None = None,
) -> dict[str, Any]:
    """Return a contract with the requested schema identity and authority lineage."""
    contract = copy.deepcopy(compiled_contract)
    current_schema_version = contract.get("schema_version")
    if schema_version is not None and current_schema_version not in {None, schema_version}:
        raise ValueError(
            "Canonical compiler output has unsupported schema_version: "
            f"{current_schema_version}"
        )

    changed = False
    if schema_version is not None and current_schema_version is None:
        contract["schema_version"] = schema_version
        changed = True
    if contract.get("lineage") != lineage:
        contract["lineage"] = copy.deepcopy(lineage)
        changed = True
    if changed:
        contract["contract_hash"] = compute_contract_hash(contract)
    return contract


def compute_contract_hash(compiled_contract: dict[str, Any]) -> str:
    """Hash a compiled contract without its self-referential contract_hash field."""
    canonical_contract = {
        key: value
        for key, value in compiled_contract.items()
        if key != "contract_hash"
    }
    canonical = json.dumps(canonical_contract, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
