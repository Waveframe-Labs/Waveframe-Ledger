<p align="center">
  <img src="https://raw.githubusercontent.com/Waveframe-Labs/.github/main/assets/branding/canon_wf_logo_extended.png" width="700">
</p>

# Governance-Ledger

Governance-Ledger turns governed source text and authority contracts into deterministic, reviewable, publishable governance authority. It is best understood as **Governance Compiler + Semantic Derivation Infrastructure**.

Ledger is not an AI policy interpreter, workflow automation layer, orchestration engine, cloud operations layer, or runtime execution system. It does not guess meaning from policy language. It normalizes supported governance statements, emits semantic diagnostics for unsafe or ambiguous structure, derives deterministic governance meaning from structured authority artifacts, gates publication, preserves lineage, and makes governance authority replayable.

## What It Provides

- Governance normalization from source text into canonical governance statements.
- Semantic diagnostics for ambiguous, conflicting, incomplete, or unsafe authority.
- Governance compilation reports with coverage, diagnostics, statement traces, and report hashes.
- Publication gating so governance authority cannot be published when blocking diagnostics are present.
- Provenance chains from source governance to compilation reports to published authority contracts.
- Publication manifests and contract registries with integrity hashes.
- Lineage verification for authority artifacts.
- Replay tooling for compilation and admissibility evidence.
- Deterministic snapshots, rollback artifacts, diffs, and review lifecycle state.
- Canonical semantic artifacts for previews, diff impacts, review packets, and authority bundles.
- Governance chronology replay and replay diff infrastructure for reconstructing authority posture from append-only events.
- Canonical schemas for generated governance, diagnostics, replay, publication, review, registry, snapshot, and semantic artifacts.

## Why This Exists

Governance used by runtime systems must be deterministic, inspectable, and reproducible. Human governance language can enter the system, but publication authority should only come from normalized statements, explicit diagnostics, approved reviews, canonical compilation reports, and traceable provenance.

Governance-Ledger exists to make that path auditable:

```text
Governance Source
  -> Normalized Statements
  -> Semantic Diagnostics
  -> Governance Compilation Report
  -> Human Review and Approval
  -> Published Authority Contract
  -> Semantic Derivation Artifacts
  -> Manifest, Registry, Snapshot
  -> Authority Bundle
  -> Lineage Verification and Replay
```

## Core Concepts

**Governance normalization**

Ledger classifies governance statements and converts supported language into canonical policy structures. Unsupported or ambiguous language remains visible as diagnostics; it is not silently converted into executable authority.

**Semantic diagnostics**

Diagnostics identify governance risks such as missing authority, overlapping thresholds, duplicate roles, weak normalization coverage, and publication-blocking compiler issues. Diagnostics are structured artifacts with stable codes, severity, domains, and publication impact.

**Governance compilation reports**

Compilation reports bind source governance identity, normalized statement traces, coverage metrics, diagnostics, compiler summaries, and a deterministic `report_hash`. They are evidence objects, not log output.

**Publication gating**

Publishing requires an approved review and generated policy that passes compiler-ingestion validation. Blocking diagnostics prevent publication. Published contract, manifest, registry, deployed review, and snapshot artifacts are written as one transaction.

**Lineage verification**

Published authority contracts include `governance_authority_lineage.v1` linking the authority to source governance and compilation report hashes. Ledger can verify that lineage independently.

**Semantic governance compilation**

Ledger owns deterministic governance interpretation after authority has been structured. Semantic derivation modules convert `authority_contract.v1` and related publication artifacts into canonical meaning artifacts without invoking Guard, Cloud, simulation, runtime evaluation, or admissibility execution.

The canonical semantic artifacts are:

- `governance_impact_preview.v1`: governance summary, enforcement behavior, consequences, lifecycle implications, and example governed outcomes.
- `authority_diff_impact.v1`: semantic impact of authority changes, including escalation, operational, lifecycle, and replay continuity implications.
- `governance_review_packet.v1`: review-ready packet binding authority, preview, optional diff impact, optional evidence, review context, immutable hashes, and explicit non-goals.
- `authority_bundle.v1`: publishable governance object binding authority contract, publication manifest, semantic artifacts, review packets, lineage, provenance, schema compatibility, and immutable inputs.

**Replayability**

Replay tooling reproduces compilation evidence from source governance and can replay admissibility decisions against authority and execution state. Replay failures produce diagnostics rather than silent disagreement.

**Deterministic governance operationalization**

Ledger records governance state transitions and publication artifacts with deterministic identifiers, hashes, normalized paths, immutable publication outputs, and rollback-capable snapshots.

**Governance chronology replay**

Ledger can replay append-only governance events to reconstruct governance meaning at a point in time. Chronology replay reconstructs active authority, lineage state, continuity posture, replay posture, projection freshness, governance health, and operational summaries without calling Guard or Cloud.

Ledger can also compare replay states across cutoffs with `governance_replay_diff.v1`, making governance posture changes over time deterministic and reviewable.

## What It Is Not

Governance-Ledger is not:

- AI policy interpretation.
- Legal advice or legal reasoning.
- A workflow automation product.
- An orchestration engine.
- A cloud governance operations service.
- A runtime mutation executor.
- A replacement for CRI-CORE Contract Compiler semantics.
- A replacement for Waveframe Guard runtime enforcement.
- A system that bypasses Guard admissibility.
- A system that infers unsupported governance meaning.

## Install

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install governance-ledger
```

Ledger relies on installed package contracts for integration behavior:

- `cricore-contract-compiler>=0.3.0`
- `waveframe-guard>=0.5.0`

Local checkout path resolution is not part of production behavior.

## Command Workflow

Generate normalized governance drafts and validation artifacts:

```powershell
governance-ledger run policies/
```

Check publication readiness:

```powershell
governance-ledger check generated/
```

Approve a reviewed governance artifact:

```powershell
governance-ledger approve reviews/finance_policy.review.json --actor governance-team
```

Publish approved governance authority:

```powershell
governance-ledger publish reviews/finance_policy.review.json
```

Inspect published authority:

```powershell
governance-ledger list contracts
governance-ledger show contracts/finance-policy-0.1.0.contract.json
```

Verify authority lineage:

```powershell
governance-ledger verify-lineage --contract contracts/finance-policy-0.1.0.contract.json
```

Replay source governance into compilation evidence:

```powershell
governance-ledger replay-authority `
  --source policies/finance_policy.txt `
  --report reviews/finance_policy.deployed.review.json `
  --contract contracts/finance-policy-0.1.0.contract.json
```

Replay execution admissibility:

```powershell
governance-ledger replay-execution `
  --contract contracts/finance-policy-0.1.0.contract.json `
  --execution-state execution_state.json
```

Generate semantic governance artifacts:

```powershell
governance-ledger preview `
  contracts/finance-policy-0.1.0.contract.json `
  --output generated/finance-policy.preview.json

governance-ledger diff-impact `
  --old contracts/finance-policy-0.1.0.contract.json `
  --new contracts/finance-policy-0.2.0.contract.json `
  --output generated/finance-policy.diff-impact.json

governance-ledger review-packet `
  --authority contracts/finance-policy-0.1.0.contract.json `
  --preview generated/finance-policy.preview.json `
  --output generated/finance-policy.review-packet.json

governance-ledger authority-bundle `
  --authority contracts/finance-policy-0.1.0.contract.json `
  --manifest contracts/finance_policy.publication_manifest.json `
  --preview generated/finance-policy.preview.json `
  --output generated/finance-policy.authority-bundle.json
```

## Artifact Layout

```text
policies/      source governance text
generated/     normalized policy drafts and validation artifacts
reviews/       review, approval, compilation, and deployment evidence
contracts/     immutable published authority contracts, manifests, registry
snapshots/     deterministic governance state snapshots
schemas/       canonical JSON schemas
governance_ledger/semantics/
               canonical semantic derivation layer
```

Publication produces:

- `contracts/<contract-id>-<version>.contract.json`
- `contracts/<policy>.publication_manifest.json`
- `contracts/index.json`
- `reviews/<policy>.deployed.review.json`
- `snapshots/<snapshot-id>.json`

Publication artifacts use normalized POSIX-style paths such as `contracts/finance-policy-0.1.0.contract.json`, even on Windows.

Semantic artifacts are deterministic derivations. They may be exported under `generated/` for review or packaging, but they are not runtime evaluations and do not change execution outcomes.

## Example Normalization

Source governance:

```text
Transfers above $1M require manager approval.
Requester and approver must be separate.
All transfer approvals must be recorded for audit purposes.
```

Normalized policy excerpt:

```json
{
  "contract_id": "finance-policy",
  "contract_version": "0.1.0",
  "authority": {
    "required_roles": ["manager"],
    "separation_of_duties": true
  },
  "approvals": {
    "required": [
      {
        "role": "manager",
        "condition": {
          "field": "amount",
          "operator": ">",
          "value": 1000000
        }
      }
    ],
    "thresholds": [
      {
        "field": "amount",
        "operator": ">",
        "value": 1000000,
        "requires_role": "manager"
      }
    ]
  },
  "artifacts": {
    "required": ["approval_audit_record"]
  }
}
```

## Diagnostics and Gates

Validation artifacts and review artifacts include structured warnings and compiler diagnostics. A diagnostic may be informational, warning-level, or publication-blocking.

Examples of publication-blocking conditions:

- Ambiguous authority, such as approval without a named approving role.
- Low governance normalization coverage.
- Overlapping approval thresholds.
- Duplicate or conflicting approval requirements.
- Compiler schema violations.
- Missing or mismatched provenance lineage.

`governance-ledger check generated/` exits non-zero when validation contains error-severity diagnostics.

## Lineage and Integrity

Published authority contracts include lineage:

```json
{
  "lineage": {
    "schema_version": "governance_authority_lineage.v1",
    "source_hash": "sha256:...",
    "compilation_report_hash": "sha256:...",
    "review_id": "review-finance_policy"
  }
}
```

Publication manifests and registries carry source and report hashes so consumers can verify the authority chain without trusting local build state.

Semantic artifacts also carry immutable input hashes. Authority bundles bind contract, manifest, preview, optional diff impact, and optional review packets into a single publishable governance object that Cloud can ingest, validate, store, replay, and operate without reconstructing governance context.

## Schemas

Canonical schemas live in [schemas/](schemas/), including:

- [governance_source.v1.json](schemas/governance_source.v1.json): governance source identity.
- [governance_diagnostic.v1.json](schemas/governance_diagnostic.v1.json): governance diagnostics.
- [governance_quality_diagnostic.v1.json](schemas/governance_quality_diagnostic.v1.json): advisory governance quality diagnostics.
- [governance_compilation_report.v1.json](schemas/governance_compilation_report.v1.json): governance compilation reports.
- [governance_impact_preview.v1.json](schemas/governance_impact_preview.v1.json): governance impact previews.
- [authority_diff_impact.v1.json](schemas/authority_diff_impact.v1.json): authority diff impacts.
- [governance_review_packet.v1.json](schemas/governance_review_packet.v1.json): governance review packets.
- [authority_bundle.v1.json](schemas/authority_bundle.v1.json): authority bundles.
- [publication_receipt.v1.json](schemas/publication_receipt.v1.json): publication receipts.
- [authority_lifecycle_event.v1.json](schemas/authority_lifecycle_event.v1.json): append-only authority lifecycle events.
- [governance_semantic_extraction.v1.json](schemas/governance_semantic_extraction.v1.json): deterministic semantic extraction artifacts.
- [governance_semantic_provenance.v1.json](schemas/governance_semantic_provenance.v1.json): semantic provenance and source-span bindings.
- [governance_semantic_reconciliation.v1.json](schemas/governance_semantic_reconciliation.v1.json): semantic reconciliation artifacts.
- [semantic_conflict.v1.json](schemas/semantic_conflict.v1.json): semantic conflicts.
- [semantic_ambiguity.v1.json](schemas/semantic_ambiguity.v1.json): semantic ambiguities.
- [semantic_interpretation_decision.v1.json](schemas/semantic_interpretation_decision.v1.json): operator interpretation decisions.
- [semantic_reconciliation_projection.v1.json](schemas/semantic_reconciliation_projection.v1.json): reconciliation projections.
- [semantic_stability_projection.v1.json](schemas/semantic_stability_projection.v1.json): semantic stability projections.
- [semantic_commit_bundle.v1.json](schemas/semantic_commit_bundle.v1.json): committed semantic interpretation bundles.
- [semantic_authority_diff.v1.json](schemas/semantic_authority_diff.v1.json): semantic authority diffs.
- [semantic_lifecycle_enforcement_projection.v1.json](schemas/semantic_lifecycle_enforcement_projection.v1.json): lifecycle enforcement consequence projections.
- [compiled_authority_contract.v1.json](schemas/compiled_authority_contract.v1.json): compiled authority contracts.
- [authority_execution_projection.v1.json](schemas/authority_execution_projection.v1.json): authority execution projections.
- [execution_requirement_projection.v1.json](schemas/execution_requirement_projection.v1.json): execution requirement projections.
- [execution_admissibility_projection.v1.json](schemas/execution_admissibility_projection.v1.json): execution admissibility projections.
- [runtime_consequence_projection.v1.json](schemas/runtime_consequence_projection.v1.json): runtime consequence projections.
- [guard_enforcement_projection.v1.json](schemas/guard_enforcement_projection.v1.json): Guard enforcement projections.
- [governance_capability.v1.json](schemas/governance_capability.v1.json): governance capabilities.
- [capability_requirement.v1.json](schemas/capability_requirement.v1.json): capability requirements.
- [capability_continuity_semantics.v1.json](schemas/capability_continuity_semantics.v1.json): capability continuity semantics.
- [capability_evidence_requirement.v1.json](schemas/capability_evidence_requirement.v1.json): capability evidence requirements.
- [capability_execution_constraint.v1.json](schemas/capability_execution_constraint.v1.json): capability execution constraints.
- [capability_identity_requirement.v1.json](schemas/capability_identity_requirement.v1.json): capability identity requirements.
- [temporal_authority_semantics.v1.json](schemas/temporal_authority_semantics.v1.json): temporal authority semantics.
- [state_posture_snapshot_semantics.v1.json](schemas/state_posture_snapshot_semantics.v1.json): state posture snapshot semantics.
- [execution_context_semantics.v1.json](schemas/execution_context_semantics.v1.json): execution context semantics.
- [governance_actor.v1.json](schemas/governance_actor.v1.json): governance actors.
- [authority_role_binding.v1.json](schemas/authority_role_binding.v1.json): authority role bindings.
- [approval_chain_semantics.v1.json](schemas/approval_chain_semantics.v1.json): approval chain semantics.
- [identity_continuity_semantics.v1.json](schemas/identity_continuity_semantics.v1.json): identity continuity semantics.
- [governance_event.v1.json](schemas/governance_event.v1.json): base governance event envelope.
- [projection_generation_event.v1.json](schemas/projection_generation_event.v1.json): projection generation events.
- [projection_invalidation_event.v1.json](schemas/projection_invalidation_event.v1.json): projection invalidation events.
- [continuity_transition_event.v1.json](schemas/continuity_transition_event.v1.json): continuity transition events.
- [governance_replay_state.v1.json](schemas/governance_replay_state.v1.json): governance chronology replay state.
- [governance_replay_diff.v1.json](schemas/governance_replay_diff.v1.json): governance replay state diffs.
- [governance_lineage_verification.v1.json](schemas/governance_lineage_verification.v1.json): lineage verification artifacts.
- [replay_authority_request.v1.json](schemas/replay_authority_request.v1.json): replay authority requests.
- [replay_execution_request.v1.json](schemas/replay_execution_request.v1.json): replay execution requests.
- [publication_manifest.v1.json](schemas/publication_manifest.v1.json): publication manifests.
- [publication_manifest.schema.json](schemas/publication_manifest.schema.json): publication manifest schema compatibility.
- [contract_registry.schema.json](schemas/contract_registry.schema.json): contract registries.
- [deployment.schema.json](schemas/deployment.schema.json): deployment records.
- [cricore_policy.schema.json](schemas/cricore_policy.schema.json): CRI-CORE policy compatibility.
- [review.schema.json](schemas/review.schema.json): reviews.
- [snapshot.schema.json](schemas/snapshot.schema.json): snapshots.

## Documentation

- [CHANGELOG.md](CHANGELOG.md)
- [PROJECTION_OWNERSHIP.md](PROJECTION_OWNERSHIP.md)
- [PROJECTION_DEPENDENCY_GRAPH.md](PROJECTION_DEPENDENCY_GRAPH.md)
- [SEMANTIC_GOVERNANCE_MODEL.md](SEMANTIC_GOVERNANCE_MODEL.md)
- [GOVERNANCE_EVENT_MODEL.md](GOVERNANCE_EVENT_MODEL.md)
- [GOVERNANCE_CHRONOLOGY_REPLAY.md](GOVERNANCE_CHRONOLOGY_REPLAY.md)
- [EVENT_ORDERING_SEMANTICS.md](EVENT_ORDERING_SEMANTICS.md)
- [GOVERNANCE_SEMANTIC_RECONCILIATION.md](GOVERNANCE_SEMANTIC_RECONCILIATION.md)
- [TEMPORAL_AND_STATE_CONTINUITY.md](TEMPORAL_AND_STATE_CONTINUITY.md)
- [EXECUTION_CONTEXT_MODEL.md](EXECUTION_CONTEXT_MODEL.md)
- [IDENTITY_AND_RESPONSIBILITY_MODEL.md](IDENTITY_AND_RESPONSIBILITY_MODEL.md)
- [GOVERNANCE_OBJECT_MODEL.md](GOVERNANCE_OBJECT_MODEL.md)
- [SEMANTICS.md](SEMANTICS.md)
- [LIFECYCLE.md](LIFECYCLE.md)
- [PROVENANCE.md](PROVENANCE.md)
- [NON_GOALS.md](NON_GOALS.md)
- [schemas/](schemas/)
