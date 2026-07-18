# ---
# title: "Golden Path Published Authority Fixture Tests"
# filetype: "python"
# type: "test"
# domain: "governance-publication"
# version: "1.0.0"
# status: "Active"
# author:
#   name: "Waveframe Labs"
# license: "Apache-2.0"
# ai_assisted: "partial"
# ---

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden_path"
CONTRACTS_ROOT = FIXTURE_ROOT / "contracts"
AUTHORITY_REF = "finance-policy@1.0.0"
CONTRACT_HASH = "sha256:3bd442fc699ef42643e0b22c42935f5a14e037473f05a1bc20757c0f565756f9"
BUNDLE_HASH = "sha256:db63dd6d796f4f44f861427c1aa81e3907c54893edca64798b1602c41485c9d6"


def test_golden_path_fixture_preserves_published_authority_identity() -> None:
    registry = _read_json(CONTRACTS_ROOT / "index.json")
    bundle = _read_json(CONTRACTS_ROOT / "finance-policy-1.0.0.authority-bundle.json")
    contract = _read_json(CONTRACTS_ROOT / "finance-policy-1.0.0.contract.json")
    receipt = _read_json(CONTRACTS_ROOT / "finance-policy-1.0.0.publication-receipt.json")

    assert registry["schema_version"] == "contract_registry.v1"
    assert registry["registry_hash"] == _hash_without(registry, "registry_hash")

    entry = registry["contracts"][0]
    assert entry["authority_ref"] == AUTHORITY_REF
    assert entry["contract_hash"] == CONTRACT_HASH
    assert entry["bundle_hash"] == BUNDLE_HASH
    assert entry["lifecycle_state"] == "active"
    assert (FIXTURE_ROOT / entry["bundle_path"]).is_file()
    assert (FIXTURE_ROOT / entry["path"]).is_file()

    assert bundle["schema_version"] == "authority_bundle.v1"
    assert bundle["authority_ref"] == AUTHORITY_REF
    assert bundle["contract_hash"] == CONTRACT_HASH
    assert bundle["publication_id"] == entry["publication_id"]
    assert f"sha256:{_canonical_hash(bundle)}" == BUNDLE_HASH

    assert contract["schema_version"] == "compiled_authority_contract.v1"
    assert f"{contract['contract_id']}@{contract['contract_version']}" == AUTHORITY_REF
    assert f"sha256:{contract['contract_hash']}" == CONTRACT_HASH
    assert f"sha256:{_canonical_hash({key: value for key, value in contract.items() if key != 'contract_hash'})}" == CONTRACT_HASH
    assert bundle["authority_contract"] == contract

    assert receipt["schema_version"] == "publication_receipt.v1"
    assert receipt["authority_ref"] == AUTHORITY_REF
    assert receipt["publication_id"] == entry["publication_id"]
    assert receipt["bundle_hash"] == BUNDLE_HASH


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_without(payload: dict[str, Any], key: str) -> str:
    return f"sha256:{_canonical_hash({name: value for name, value in payload.items() if name != key})}"
