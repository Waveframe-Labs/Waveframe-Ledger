"""Canonical local registry projections."""

from governance_ledger.local_registry.projections.diagnostics import build_diagnostic_rollup_projection
from governance_ledger.local_registry.projections.lineage import build_authority_lineage_projection
from governance_ledger.local_registry.projections.operational import build_authority_operational_summary
from governance_ledger.local_registry.projections.registry import build_authority_drift_indicators
from governance_ledger.local_registry.projections.timeline import build_timeline_projection
from governance_ledger.local_registry.projections.workspace import build_authority_workspace_projection

__all__ = [
    "build_authority_drift_indicators",
    "build_authority_lineage_projection",
    "build_authority_operational_summary",
    "build_authority_workspace_projection",
    "build_diagnostic_rollup_projection",
    "build_timeline_projection",
]
