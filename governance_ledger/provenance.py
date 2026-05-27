"""Stable provenance metadata for governance review artifacts."""

from __future__ import annotations

from datetime import datetime, timezone

from governance_ledger.semantics.extraction import build_governance_source

DEFAULT_REVIEW_STATUS = "pending"


def build_review_provenance(
    text: str,
    *,
    review_id: str | None = None,
    created_at: str | None = None,
    source_document: str | None = None,
    review_status: str = DEFAULT_REVIEW_STATUS,
) -> dict[str, str | None]:
    """Build explicit provenance metadata for a review artifact."""
    source_identity = source_governance_identity(text)
    return {
        "review_id": review_id or _stable_review_id(text),
        "created_at": created_at or _utc_now(),
        "source_document": source_document,
        "source_governance": source_identity,
        "source_hash": source_identity["source_hash"],
        "review_status": review_status,
    }


def source_governance_identity(text: str, *, version: str = "1") -> dict[str, str]:
    source = build_governance_source(text)
    source["source_version"] = version
    return source


def _stable_review_id(text: str) -> str:
    digest = build_governance_source(text)["source_hash"].removeprefix("sha256:")
    return f"review-{digest[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
