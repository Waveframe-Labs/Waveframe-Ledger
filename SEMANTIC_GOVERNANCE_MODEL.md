---
title: "Semantic Governance Model"
document_type: "ontology"
system: "Governance-Ledger"
component: "semantic-governance"
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
  Canonical ontology for Ledger-owned semantic governance primitives,
  projection roles, mutation boundaries, freshness semantics, and
  governance-native severity language.
---

# Semantic Governance Model

Ledger owns governance meaning.

This document defines the canonical semantic ontology for local Ledger governance authoring, registry state, projections, continuity posture, reconciliation, freshness, and operational governance coherence.

It is intentionally not a Cloud operations model and not a Guard admissibility model.

## Core Governance Primitives

### Authority

An authority is a deterministic governance object that states what operational resource is governed, what action is controlled, which authority requirements apply, when escalation occurs, what evidence is expected, and what lifecycle or continuity posture affects execution.

Canonical artifact:

- `authority_contract.v1`

Publishable envelope:

- `authority_bundle.v1`

### Lineage

Lineage is the versioned relationship between authorities in one authority family. It includes version successors, supersession relationships, revocation posture, provenance, and lifecycle continuity.

Lineage answers:

- what came before this authority
- what superseded it
- whether the version chain is complete
- whether replay or continuity can bind to prior posture

### Continuity

Continuity is the semantic relationship between authority posture and resumed, delayed, replayed, or lineage-dependent execution.

Continuity answers:

- whether resumed workflows require revalidation
- whether revocation invalidates resumed execution
- whether supersession changes execution posture
- whether lineage gaps or churn degrade governance stability

### Replay Posture

Replay posture is the evidence-readiness state that determines whether future replay review can bind to the authority, receipt, manifest, semantic hashes, and lineage.

Replay posture is not runtime replay execution. It is publication evidence readiness.

### Drift

Drift is deterministic semantic change across authority versions or lifecycle posture.

Examples:

- approval requirement changed
- escalation threshold changed
- continuity posture changed
- lifecycle posture changed

Drift is not a score and not an anomaly detector.

### Reconciliation

Reconciliation compares lifecycle state, lineage state, replay posture, continuity posture, projection freshness, active authority state, and registry health to detect deterministic divergence.

Reconciliation does not fix state and does not recommend policy changes.

### Invalidation

Invalidation is the condition where a source change makes one or more projections no longer authoritative for the current state.

Example:

```text
draft updated
  -> authority_workspace_projection.v1 invalidated
  -> authority_operational_summary.v1 invalidated
  -> governance_continuity_projection.v1 invalidated
  -> diagnostic_rollup.v1 invalidated
```

Invalidation does not delete historical artifacts.

### Freshness

Freshness is the relation between a projection and the source events or facts from which it was generated.

Freshness answers:

- was this projection generated from current source events?
- did a later lifecycle event make it stale?
- did a state transition explicitly invalidate it?

### Lifecycle Event

A lifecycle event is an append-only fact attached to an authority lineage.

Canonical artifact:

- `authority_lifecycle_event.v1`

Lifecycle events include:

- `drafted`
- `reviewed`
- `exported`
- `registered`
- `superseded`
- `revoked`

### Operational Summary

An operational summary is a projection that renders the authority as a governance object, not JSON.

It includes lifecycle posture, drift summary, replay readiness, governance meaning, and relationship graph.

Canonical projection:

- `authority_operational_summary.v1`

### Active Authority

An active authority is the current registered, non-superseded, non-revoked authority for an authority family.

Canonical projection:

- `active_authority_projection.v1`

### Governance Activity

Governance activity is a compact operational feed derived from lifecycle events and semantic drift.

Canonical projection:

- `governance_activity_projection.v1`

### Governance Coherence

Governance coherence is the operator-facing posture that summarizes whether registry state, continuity, replay, lifecycle, reconciliation, and projection freshness remain aligned.

Coherence uses governance-native language:

- healthy
- stale
- invalidated
- continuity risk
- replay risk
- authority conflict

## Projection Taxonomy

### Operational

Operational projections render governance meaning and activity for operators.

- `authority_operational_summary.v1`
- `governance_activity_projection.v1`

### Continuity

Continuity projections render authority lineage and execution-continuity semantics.

- `governance_continuity_projection.v1`
- `authority_lineage_projection.v1`

### Reconciliation

Reconciliation projections compare state surfaces for divergence, freshness, replay inconsistency, active authority ambiguity, and registry posture.

- `governance_reconciliation_projection.v1`
- `registry_health_projection.v1`

### Workspace

Workspace projections render the current working authority draft and release posture.

- `authority_workspace_projection.v1`

### Lifecycle

Lifecycle projections render chronology, lifecycle transition posture, replay posture changes, diagnostics, drift, activation, and deactivation.

- `governance_timeline_projection.v1`
- `authority_timeline_projection.v1`

### Activity And Registry Selection

Registry selection projections resolve current operational registry views.

- `active_authority_projection.v1`
- `projection_invalidation_plan.v1`

## Mutation Boundaries

These are ontology rules, not UI preferences.

### Viewing Is Not A Lifecycle Transition

Viewing bundle, preview, receipt, diff, diagnostics, lineage, or timeline artifacts must not create lifecycle events.

### Rendering Is Not Approval

Rendering an artifact must not approve, review, export, register, supersede, revoke, or otherwise mutate authority posture.

### Preview Is Not Review

Generating or viewing `governance_impact_preview.v1` does not mean the operator reviewed impact.

Review requires an explicit review action.

### Export Is Not Registration

Exporting `authority_bundle.v1` creates or prepares publication evidence. It does not register the authority lifecycle event unless a separate explicit registration action occurs.

### Registration Is Not Admissibility

Registering an authority locally records lifecycle posture and evidence. It does not make any runtime execution admissible.

Guard owns admissibility.

### Diagnostics Are Advisory

Diagnostics describe deterministic governance quality observations. They do not reject publication, approve authority, or evaluate runtime execution.

## Projection Freshness Semantics

### Fresh

`fresh` means the projection was generated from the current source event set and no known invalidation applies.

### Stale

`stale` means newer source events exist than the projection's recorded `source_event_ids`, but the projection was not explicitly invalidated.

### Invalidated

`invalidated` means a source transition explicitly made the projection unfit for current operational posture.

Examples:

- draft changed after review
- authority superseded
- replay posture invalidated
- diagnostics stale

### Reconciled

`reconciled` means reconciliation found no divergence across lifecycle, lineage, replay, continuity, projection freshness, active authority state, or registry health.

## Invalidation Propagation

Invalidation propagates from source facts to dependent projections.

Examples:

```text
draft changed
  -> workspace projection invalidated
  -> operational summary invalidated
  -> continuity projection invalidated
  -> diagnostics rollup invalidated

authority registered
  -> registry entry changed
  -> active authority projection invalidated
  -> lineage projection invalidated
  -> health projection invalidated
  -> activity projection invalidated
  -> timeline projection invalidated
  -> continuity projection invalidated

replay posture invalidated
  -> operational summary invalidated
  -> registry health invalidated
  -> governance activity invalidated
  -> governance timeline invalidated
  -> governance continuity invalidated
```

Historical source facts persist. Projections recompute.

## Governance-Native Severity Semantics

Ledger uses governance-native severity semantics.

These are not infrastructure alert levels.

### info

Contextual governance information with no immediate continuity, replay, or authority conflict.

### warning

A governance posture changed or requires operator awareness, but does not directly indicate continuity risk, replay risk, or authority conflict.

### critical

A lifecycle posture has severe governance consequence, such as revocation.

### continuity_risk

Continuity semantics changed or resumed execution posture may require revalidation.

### replay_risk

Replay evidence, receipt posture, semantic hash linkage, manifest alignment, or lineage evidence is incomplete or inconsistent.

### authority_conflict

Authority interpretation is ambiguous or conflicting, such as multiple active authorities in one authority family.

## Projection Generation Standard

All canonical projections should evolve toward a common metadata envelope.

Required standard fields:

```json
{
  "schema_version": "projection_name.v1",
  "projection_version": "v1",
  "generated_at": "2026-05-27T00:00:00Z",
  "source_event_ids": [],
  "freshness_posture": "fresh",
  "projection_dependencies": []
}
```

### generated_at

The deterministic or runtime timestamp when the projection was generated.

When deterministic test generation is required, callers may supply `generated_at`.

### source_event_ids

The lifecycle event IDs, registry event IDs, or source artifact identifiers used to build the projection.

### freshness_posture

One of:

- `fresh`
- `stale`
- `invalidated`

### projection_version

The additive evolution version of the projection contract.

For `*.v1` projections, this should be `v1`.

### projection_dependencies

The projection schemas or source facts required to derive the projection.

Examples:

- `authority_registry_entry.v1`
- `authority_lifecycle_event.v1`
- `authority_lineage_projection.v1`
- `governance_continuity_projection.v1`

## Non-Goals

Ledger semantic projections must not:

- invoke Guard
- call Cloud
- evaluate runtime admissibility
- probabilistically score governance risk
- generate AI recommendations
- mutate source facts during rendering
- replace explicit lifecycle actions

Ledger produces deterministic governance meaning. Cloud operates it. Guard evaluates runtime admissibility.
