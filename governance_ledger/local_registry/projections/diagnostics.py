"""Diagnostic projections for local registry state."""

from __future__ import annotations

from typing import Any

from governance_ledger.local_registry.models import build_diagnostic_rollup


def build_diagnostic_rollup_projection(
    *,
    authority_ref: str,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the canonical diagnostic rollup projection."""
    return build_diagnostic_rollup(authority_ref=authority_ref, diagnostics=diagnostics)
