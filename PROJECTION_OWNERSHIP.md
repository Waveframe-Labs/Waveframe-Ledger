---
title: "Projection Ownership"
document_type: "architecture"
system: "Governance-Ledger"
component: "local-registry-projections"
version: "0.3.0"
status: "draft"

created: "2026-05-27"
updated: "2026-05-27"

authors:
  - "Waveframe Labs"

maintainers:
  - "Waveframe Labs"

license: "Apache-2.0"

repository: "https://github.com/Waveframe-Labs/Governance-Ledger"

summary: >
  Ownership boundaries, stability expectations, and invalidation semantics for
  Ledger registry and governance projections.
---

# Projection Ownership

Ledger projections are deterministic governance views over canonical local state. They are not UI conveniences and they are not Cloud compatibility shims.

The UI renders projections. It must not independently derive governance meaning, lifecycle posture, drift semantics, replay readiness, or continuity implications.

## Ownership Rule

`governance_ledger/local_registry/projections/` owns registry projection meaning.

Frontend code may select, format, collapse, or expand projection fields. It must not calculate:

- whether an authority is active
- whether continuity posture changed
- whether replay readiness is incomplete
- whether lineage is complete
- whether an authority has drifted
- what lifecycle event came next
- what a governance event means operationally

Those meanings flow from canonical projections.

## Canonical Projections

The following projections are canonical UI-facing governance views:

- `authority_workspace_projection.v1`: current working view of one authority draft, review, export, and registration posture.
- `authority_operational_summary.v1`: full governance object view for one selected authority.
- `authority_lineage_projection.v1`: version chain, supersession graph, continuity state, replay posture, and lineage drift.
- `governance_activity_projection.v1`: compact operational event feed for registry surfaces.
- `governance_timeline_projection.v1`: unified governance chronology across lifecycle, drift, replay, diagnostics, activation, deactivation, and supersession.
- `registry_health_projection.v1`: registry-level posture over replay readiness, continuity drift, and authority health.
- `active_authority_projection.v1`: current active authority semantics per authority family.

## Append-Only Facts

These are durable facts, not projections:

- `authority_lifecycle_event.v1`
- `publication_receipt.v1`

Append-only facts are never rewritten to make a later projection easier. Corrections must be represented by additional lifecycle events or later receipts.

## Stable Sub-Artifacts

These are deterministic sub-artifacts used by projections:

- `authority_drift_indicator.v1`
- `diagnostic_rollup.v1`
- `authority_timeline_projection.v1`

They are stable enough for tests and UI rendering, but they are not the primary object a page should consume when a richer canonical projection exists.

## Internal Aggregation Helpers

Projection modules may use private helper functions to sort lineage, normalize authority versions, summarize drift, or map lifecycle events to governance-native severity.

These helpers are implementation details. UI code must not depend on helper output shape or duplicate helper logic.

## Compatibility Layers

Compatibility layers adapt old or transitional storage shapes into canonical projection inputs.

Examples:

- browser `localStorage` records
- legacy registry state keys
- transitional bundle or receipt aliases
- compatibility import modules

Compatibility layers are adapters. They do not own governance meaning.

## Governance-Native Severity

Drift and timeline projections use governance-native severity semantics:

- `info`: advisory governance context with no immediate operational risk.
- `warning`: governance posture changed and should be reviewed.
- `critical`: authority state creates a severe lifecycle consequence, such as revocation.
- `continuity_risk`: continuity guarantees or resumed execution semantics changed.
- `replay_risk`: replay evidence, receipt posture, or semantic hash linkage is incomplete.
- `authority_conflict`: lifecycle or authority posture changed in a way that may alter active authority interpretation.

These are not infrastructure severities. They describe governance consequences.

## Invalidation Semantics

Projection invalidation is deterministic. The source facts persist; affected projections recompute.

| Change | Invalidated projections | Persist historically |
| --- | --- | --- |
| Draft changed | `authority_workspace_projection.v1`, `authority_operational_summary.v1`, `diagnostic_rollup.v1`, publication review views | Existing registry entries, lifecycle events, receipts |
| Impact reviewed | `authority_workspace_projection.v1`, `authority_operational_summary.v1`, `governance_activity_projection.v1`, `governance_timeline_projection.v1` | Prior review events |
| Bundle exported | `authority_workspace_projection.v1`, `authority_registry_entry.v1`, `authority_operational_summary.v1`, `registry_health_projection.v1`, `governance_activity_projection.v1`, `governance_timeline_projection.v1` | `publication_receipt.v1`, exported lifecycle event |
| Authority registered | `authority_registry_entry.v1`, `active_authority_projection.v1`, `authority_lineage_projection.v1`, `registry_health_projection.v1`, `governance_activity_projection.v1`, `governance_timeline_projection.v1` | Registered lifecycle event |
| Lineage changed | `authority_lineage_projection.v1`, `active_authority_projection.v1`, `registry_health_projection.v1`, `authority_operational_summary.v1`, `governance_activity_projection.v1`, `governance_timeline_projection.v1` | Lifecycle events, receipts |
| Authority superseded | `authority_lineage_projection.v1`, `active_authority_projection.v1`, `registry_health_projection.v1`, `authority_operational_summary.v1`, `governance_activity_projection.v1`, `governance_timeline_projection.v1` | Superseded lifecycle event |
| Authority revoked | `authority_lineage_projection.v1`, `active_authority_projection.v1`, `registry_health_projection.v1`, `authority_operational_summary.v1`, `governance_activity_projection.v1`, `governance_timeline_projection.v1` | Revoked lifecycle event |
| Diagnostics stale | `diagnostic_rollup.v1`, `authority_workspace_projection.v1`, `authority_operational_summary.v1`, `registry_health_projection.v1`, `governance_activity_projection.v1`, `governance_timeline_projection.v1` | Prior diagnostics if stored as evidence |
| Replay posture invalidated | `authority_operational_summary.v1`, `registry_health_projection.v1`, `governance_activity_projection.v1`, `governance_timeline_projection.v1` | Existing receipts as historical evidence |

## Recompute Rules

Projections are cheap deterministic views and should be recomputed from source facts unless explicitly persisted for audit display.

Persist:

- lifecycle events
- publication receipts
- registry entries
- exported bundles

Recompute:

- workspace projections
- operational summaries
- lineage projections
- activity projections
- governance timeline projections
- health projections
- active authority projections

## Boundary

Projection builders must not call Guard, Cloud, or runtime admissibility evaluators.

Ledger projections describe governance meaning from Ledger-owned artifacts. Cloud may store and render those artifacts. Guard may later decide admissibility from runtime context, but Guard does not own Ledger projection semantics.
