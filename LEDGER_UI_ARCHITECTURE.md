---
title: "Ledger UI Architecture"
document_type: "architecture"
system: "Governance-Ledger"
component: "ui"
version: "0.3.0"
status: "draft"

created: "2026-05-25"
updated: "2026-05-25"

authors:
  - "Waveframe Labs"

maintainers:
  - "Waveframe Labs"

license: "Apache-2.0"

repository: "https://github.com/Waveframe-Labs/Governance-Ledger"

summary: >
  Architecture boundary and first-scope workflow for a local Ledger UI focused
  on governance authoring, semantic publication, and authority_bundle.v1 export.
---

# Ledger UI Architecture

The Ledger UI should feel like creating operational governance, not configuring software.

The first UI should be a focused local operational surface for governance authoring and semantic publication. It should not introduce login systems, organization management, billing, multi-user workflows, RBAC, cloud sync, or runtime operations.

## Product Boundary

Ledger owns governance meaning:

- governance authoring workflow
- deterministic semantic generation
- operational consequence derivation
- lifecycle and continuity implications
- lineage and provenance presentation
- schema compatibility presentation
- `authority_bundle.v1` export

Cloud owns governance operations:

- ingest
- validate
- store
- render
- review
- replay
- operate
- export

Guard owns governance admissibility:

- runtime allow or block decisions
- execution-state evaluation
- enforcement traces
- decision replay semantics

The UI must render Ledger artifacts and call Ledger semantic modules. It must not reconstruct governance meaning in frontend logic.

## Design Character

The Ledger UI should feel:

- calm
- authoritative
- governance-oriented
- institutionally legible
- operationally precise

It should not feel:

- cyberpunk
- terminal-themed
- DevOps-heavy
- observability-first
- infrastructure telemetry-oriented

The user should feel they are creating, reviewing, and publishing authority, not tuning application settings.

## First Navigation

The initial UI navigation should be intentionally narrow:

- Overview
- Draft Authority
- Semantic Preview
- Change Review
- Publication Review
- Authority Registry
- Diagnostics

No global admin console, user settings, organization switcher, billing surface, cloud sync status, or runtime operations pane should be introduced in the first version.

## Canonical Publication Object

`authority_bundle.v1` is the Ledger-produced publication envelope and the preferred authority publication object for Cloud ingestion.

Conceptually:

```text
authority_bundle.v1 =
  authority artifact
  + publication manifest
  + registry entry
  + deterministic semantic artifacts
```

Cloud accepts this object at:

```text
POST /v1/authorities
```

The Ledger UI should treat `authority_bundle.v1` as the final local export artifact.

## Clean Bundle Shape

The Ledger UI should guide users toward this clean shape:

```json
{
  "schema_version": "authority_bundle.v1",
  "authority_artifact": {
    "schema_version": "authority_contract.v1",
    "contract_id": "treasury-policy",
    "contract_version": "2.1.0",
    "governance_category": "Financial",
    "protected_resource": "Corporate Treasury Transfer System",
    "mutation_targets": ["bank_api.transfer_funds"],
    "authority_requirements": {},
    "escalation_requirements": {},
    "continuity_requirements": {},
    "review_requirements": {},
    "decision_trace_fields": [],
    "replay_requirements": [],
    "contract_hash": "sha256:..."
  },
  "publication_manifest": {
    "schema_version": "publication_manifest.v1",
    "publication_id": "pub-treasury-policy-2-1-0",
    "published_at": "2026-05-25T00:00:00Z",
    "published_by": "governance-ledger",
    "contracts": [
      {
        "contract_id": "treasury-policy",
        "contract_version": "2.1.0",
        "contract_hash": "sha256:...",
        "path": "contracts/treasury-policy-2.1.0.contract.json",
        "source_hash": "sha256:...",
        "compilation_report_hash": "sha256:..."
      }
    ],
    "reviews": [],
    "snapshots": []
  },
  "registry_entry": {
    "organization_id": "org-finance",
    "authority_owner": "treasury-governance",
    "authority_ref": "treasury-policy@2.1.0",
    "contract_ref": "treasury-policy@2.1.0",
    "contract_id": "treasury-policy",
    "contract_version": "2.1.0",
    "contract_hash": "sha256:...",
    "path": "contracts/treasury-policy-2.1.0.contract.json",
    "published_at": "2026-05-25T00:00:00Z",
    "published_by": "governance-ledger",
    "source_hash": "sha256:...",
    "compilation_report_hash": "sha256:..."
  },
  "preview": {},
  "diff": {},
  "review_packet": {},
  "lineage": {}
}
```

Cloud tolerates transitional aliases, but the Ledger UI should present one canonical shape. Transitional aliases are compatibility details, not authoring concepts.

## Page Responsibilities

### Overview

Purpose: orient the operator around current local governance work.

Responsibilities:

- show current draft authority identity
- show semantic artifact readiness
- show publication readiness
- show latest local bundles
- show blocking diagnostics summary

Must not:

- show runtime telemetry
- show cloud sync state
- imply authority has been deployed

### Draft Authority

Purpose: create the structured authority artifact.

This is the canonical governance drafting workflow. Inputs should be governance concepts, not implementation knobs:

- protected system
- governed action
- governance category
- mutation targets
- approver role
- approval count
- escalation threshold
- validity window
- continuity requirements
- review requirements
- decision trace fields
- replay requirements

Output:

- `authority_contract.v1` or clean `authority_artifact` draft

Must not:

- call Guard
- call Cloud
- ask for runtime infrastructure settings
- derive human meaning in UI-only logic

### Semantic Preview

Purpose: render deterministic authority meaning.

Consumes:

- `governance_impact_preview.v1`

Responsibilities:

- show governance summary
- show enforcement behavior
- show operational consequences
- show lifecycle implications
- show continuity implications
- show example governed outcomes

Must not:

- generate meaning in the frontend
- run simulation
- evaluate admissibility

### Change Review

Purpose: review governance change impact between authority versions.

Consumes:

- `authority_diff_impact.v1`

Responsibilities:

- show changed governance rules
- show operational implications
- show escalation impact
- show lifecycle continuity implications
- show replay continuity implications

Must not:

- perform ad hoc object diffing in the UI
- decide whether changes are acceptable
- mutate either authority version

### Publication Review

Purpose: review and export the publishable governance object.

This is the most important page in the first UI.

Consumes:

- `authority_contract.v1`
- `publication_manifest.v1`
- `governance_impact_preview.v1`
- optional `authority_diff_impact.v1`
- optional `governance_review_packet.v1`
- lineage metadata
- provenance metadata
- schema compatibility metadata

Responsibilities:

- show governance summary
- show operational consequences
- show continuity implications
- show diff impacts
- show immutable input hashes
- show lineage
- show provenance
- show schema compatibility
- show publication manifest
- export `authority_bundle.v1`

Primary action:

```text
Export authority_bundle.v1
```

Must not:

- deploy authority
- approve on behalf of a human
- call Cloud
- call Guard
- alter replay
- mutate evidence
- change execution outcomes

### Authority Registry

Purpose: local bundle registry.

Responsibilities:

- persist local `authority_bundle_registry.v1` state
- list local `authority_bundle.v1` exports
- show `authority_ref`, lifecycle status, publication timestamps, and supersession state
- show governed resource, governed action, continuity posture, escalation threshold, and semantic integrity posture
- show immutable hashes, lineage summary, and replay metadata when present
- support local artifact actions: view bundle, open semantic preview, open diff, export bundle, supersede, revoke, and view lineage
- render lifecycle timeline events for drafted, reviewed, published, superseded, and revoked states

Must not:

- sync to Cloud
- present itself as source of runtime truth
- manage organizations or users
- derive governance meaning in frontend code

### Diagnostics

Purpose: make governance quality and semantic safety visible.

Initial diagnostics should include:

- ambiguous governance language
- missing escalation rules
- continuity gaps
- replay incompleteness
- lifecycle incompatibilities
- semantic inconsistencies
- schema compatibility failures
- missing lineage or provenance fields

Long-term, this can become one of Ledger UI's strongest differentiators.

Must not:

- auto-fix authority without explicit user action
- hide blocking diagnostics
- downgrade semantic risks into style warnings

## Artifact Flow

```text
Draft Authority
  -> authority_contract.v1
  -> governance_impact_preview.v1
  -> optional authority_diff_impact.v1
  -> optional governance_review_packet.v1
  -> publication_manifest.v1
  -> registry_entry
  -> authority_bundle.v1
```

The UI may orchestrate local Ledger calls, but semantic meaning must come from Ledger modules and versioned artifacts.

## Export Flow

1. User drafts authority.
2. Ledger builds authority artifact.
3. Ledger derives impact preview.
4. Ledger optionally derives authority diff.
5. Ledger optionally creates review packet.
6. Ledger prepares publication manifest and registry entry.
7. Ledger assembles `authority_bundle.v1`.
8. UI exports the bundle locally.

Cloud ingestion is outside first-scope UI.

## Semantic Artifact Rendering

The UI renders these artifacts:

- `governance_impact_preview.v1`
- `authority_diff_impact.v1`
- `governance_review_packet.v1`
- `authority_bundle.v1`

The UI must not create alternate semantic meanings that differ from those artifacts.

## Transitional Cloud Compatibility

Cloud tolerates aliases during transition:

- `authority_artifact` or `authority_contract` or `contract`
- `registry_entry` or `registry_metadata`
- `preview` or `governance_preview`
- `diff` or `authority_diff`
- `review_packet` or `governance_review_packet`
- `lineage` or `provenance` or `lineage_provenance`

Ledger UI should not expose these aliases as choices. It should emit the clean Ledger shape and let Cloud handle compatibility.

## Ledger Must Not Do

The UI and local semantic flow must not:

- implement login systems
- implement organization management
- implement billing
- implement multi-user collaboration
- implement RBAC
- sync with Cloud in first scope
- call Guard
- call Cloud
- run runtime admissibility evaluation
- deploy authority
- mutate execution evidence
- alter replay artifacts
- bypass Guard
- infer unsupported governance meaning
- present generated semantics as human approval

## Implementation Guidance

The first implementation should prefer a small local app with durable local files over a broad platform shell.

Recommended behavior:

- artifact-first state model
- local workspace storage
- explicit export actions
- stable hashes and visible lineage
- concise diagnostics
- calm forms with governance language
- no decorative operational telemetry

The UI should make the operator feel they are shaping institutional authority, reviewing its operational consequences, and exporting a canonical governance publication object.
