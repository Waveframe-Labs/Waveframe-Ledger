---
title: "Projection Dependency Graph"
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
  Canonical dependency, invalidation, freshness, and generation-order semantics
  for Ledger local registry projections.
---

# Projection Dependency Graph

Ledger projections are deterministic views over local registry facts. Dependency order matters because Registry surfaces now render lifecycle, lineage, continuity, replay, freshness, reconciliation, and health as one operational posture.

## Source Facts

The projection graph starts from durable facts:

- `authority_registry_entry.v1`
- `authority_lifecycle_event.v1`
- `publication_receipt.v1`
- `diagnostic_rollup.v1`
- exported semantic artifacts referenced by registry entries

These facts persist historically. Projections recompute from them.

## Canonical Generation Order

```text
authority_registry_entry.v1[]
  -> authority_drift_indicator.v1
  -> authority_timeline_projection.v1
  -> authority_lineage_projection.v1
  -> active_authority_projection.v1
  -> registry_health_projection.v1
  -> governance_continuity_projection.v1
  -> governance_timeline_projection.v1
  -> governance_activity_projection.v1
  -> governance_reconciliation_projection.v1
```

`governance_reconciliation_projection.v1` is intentionally late in the graph because it reconciles lifecycle state, lineage state, replay posture, continuity posture, projection freshness, active authority state, and registry health.

## Dependency Table

| Projection | Depends on | Purpose |
| --- | --- | --- |
| `authority_drift_indicator.v1` | previous and current registry entries | Detect deterministic governance rule drift. |
| `authority_timeline_projection.v1` | lifecycle events | Render one authority's lifecycle events. |
| `authority_lineage_projection.v1` | registry entries, drift indicators, authority timelines | Build version chain, supersession edges, lineage timeline, and drift. |
| `active_authority_projection.v1` | registry entries | Resolve current active authority per authority family. |
| `registry_health_projection.v1` | registry entries, lineage projection | Summarize replay readiness, warnings, and continuity drift. |
| `governance_continuity_projection.v1` | registry entries, drift indicators | Detect continuity posture, fragmentation, replay degradation, and governance churn. |
| `governance_timeline_projection.v1` | registry entries, lifecycle events, drift indicators, diagnostic rollups, receipts | Produce unified governance chronology. |
| `governance_activity_projection.v1` | registry entries, lineage projection | Produce compact operational activity feed. |
| `governance_reconciliation_projection.v1` | registry entries, lineage, health, continuity, active authority, freshness state | Reconcile cross-projection posture and emit deterministic issues. |

## Freshness Fields

Freshness-capable projections should use:

```json
{
  "generated_at": "2026-05-27T00:00:00Z",
  "source_event_ids": [],
  "freshness_posture": "fresh"
}
```

Allowed `freshness_posture` values:

- `fresh`: projection source events match current source facts.
- `stale`: projection source events are older than current source facts.
- `invalidated`: a change explicitly invalidated the projection.

`governance_reconciliation_projection.v1` records freshness for the projections it reconciles. Other projections may add these fields additively as the storage adapter matures.

## Invalidation Propagation

Invalidation starts with a registry or draft change and propagates along dependency edges.

Examples:

- `draft_updated` invalidates workspace, operational summary, diagnostics, and continuity projections.
- `authority_registered` invalidates registry entry, active authority, lineage, health, activity, timeline, and continuity projections.
- `authority_superseded` invalidates lineage, active authority, health, operational summary, activity, timeline, and continuity projections.
- `replay_posture_invalidated` invalidates operational summary, health, activity, timeline, and continuity projections.

The executable mapping lives in `projection_invalidation_plan.v1`.

## Freshness Propagation

Freshness propagates downstream:

```text
stale source facts
  -> stale lineage
  -> stale active authority
  -> stale health
  -> stale continuity
  -> stale timeline/activity
  -> reconciliation issue
```

Invalidation is stronger than staleness:

```text
invalidated projection
  -> reconciliation_posture: invalidated
```

## Reconciliation Boundary

Reconciliation does not fix state and does not generate recommendations.

It only emits deterministic observations such as:

- `projection_divergence`
- `replay_posture_inconsistent`
- `lineage_gap`
- `multiple_active_authorities`
- `continuity_posture_unstable`
- `registry_health_unstable`

This keeps Ledger in its proper role: semantic governance infrastructure, not automated policy remediation.
