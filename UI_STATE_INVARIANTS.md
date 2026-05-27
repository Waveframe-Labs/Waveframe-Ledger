---
title: "UI State Invariants"
document_type: "architecture"
system: "Governance-Ledger"
component: "ui"
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
  Workflow state invariants for the local Ledger UI, especially boundaries
  between rendering existing artifacts and mutating the current authority draft.
---

# UI State Invariants

The Ledger UI renders governance artifacts and guides authority publication. Viewing an artifact must not mutate the current draft workflow.

The UI state model distinguishes:

- current draft workflow state
- local registry authority state
- rendered artifact detail
- publication receipt readiness
- lifecycle mutation actions

## Core Rule

Viewing is not reviewing.

Rendering a registry artifact must not mark the current draft reviewed, exported, receipt-generated, or registered.

## Invariants

1. Opening registry artifacts does not mark the current draft reviewed.
2. Opening semantic preview does not enable export.
3. Viewing receipt does not register authority.
4. Viewing lineage does not mutate lifecycle.
5. Diagnostics rendering does not change workflow state.
6. Export requires explicit impact review.
7. Registration requires a successful export receipt.
8. Editing draft invalidates review, export, receipt, and registration state.

## Allowed Workflow Mutations

Only these interactions should mutate workflow state:

- `Review Impact`: may set `impactReviewed`.
- `Export Bundle`: may set `bundleExported` and `receiptGenerated`, only after impact review.
- `Register Authority Locally`: may set `authorityRegistered`, only after a receipt-backed export.
- Draft input/change: must clear reviewed, exported, receipt, and registered state.
- Explicit registry lifecycle actions: `Supersede` and `Revoke` mutate registry lifecycle records, not the current draft review state.

## Registry View Actions

These are view-only:

- `View bundle`
- `Open semantic preview`
- `Open diff`
- `View receipt`
- `View lineage`

They may change the visible page or selected detail panel. They must not:

- call `updateWorkflowState`
- enable export directly
- create `pendingRegistration`
- call `publishCurrentBundleToRegistry`
- append lifecycle events

## Publication Gates

Export requires:

```text
currentArtifacts exists
workflowState.impactReviewed == true
```

Registration requires:

```text
currentArtifacts exists
pendingRegistration exists
```

`pendingRegistration` is created only by a successful receipt-backed export.

## Draft Editing

Any draft `input` or `change` invalidates:

- `impactReviewed`
- `bundleExported`
- `receiptGenerated`
- `authorityRegistered`
- `workflowTimestamps.reviewed`
- `workflowTimestamps.exported`
- `workflowTimestamps.registered`
- `pendingRegistration`

This keeps the UI from showing stale publication posture after authority constraints change.
