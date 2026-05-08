"""Link approved governance reviews to external compiled contract artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from governance_authoring.lifecycle import transition_review_status
from governance_authoring.provenance import _utc_now

REQUIRED_LINKAGE_STATUS = "approved"
DEFAULT_COMPILED_BY = "compiler-service"


def attach_compiled_contract(
    review: dict[str, Any],
    compiled_contract: dict[str, Any],
    *,
    actor: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Attach lightweight compiled contract lineage after approval."""
    if review.get("review_status") != REQUIRED_LINKAGE_STATUS:
        raise ValueError("Compiled contracts can only be attached to approved reviews.")

    compiled_at = timestamp or _utc_now()
    updated_review = transition_review_status(
        review,
        "compiled",
        actor=actor,
        timestamp=compiled_at,
        note="Linked compiled contract.",
    )
    updated_review["compiled_contract"] = {
        "contract_id": _required_contract_field(compiled_contract, "contract_id"),
        "contract_version": _required_contract_field(compiled_contract, "contract_version"),
        "contract_hash": compiled_contract.get("contract_hash")
        or _hash_compiled_contract(compiled_contract),
    }
    updated_review["compiled_by"] = actor or DEFAULT_COMPILED_BY
    updated_review["compiled_at"] = compiled_at

    return updated_review


def _required_contract_field(compiled_contract: dict[str, Any], field: str) -> Any:
    value = compiled_contract.get(field)
    if value in (None, ""):
        raise ValueError(f"Compiled contract missing required field: {field}")
    return value


def _hash_compiled_contract(compiled_contract: dict[str, Any]) -> str:
    canonical_payload = json.dumps(
        compiled_contract,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()
