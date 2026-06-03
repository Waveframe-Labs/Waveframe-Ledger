# Changelog

## 0.4.0 - 2026-06-03

Governance-Ledger v0.4.0 formalizes the public deterministic governance object layer, governance event architecture, chronology replay contracts, semantic reconciliation, compiled authority contracts, and execution-facing projection boundaries.

### Added

- Governance event architecture with canonical event schemas:
  - `governance_event.v1`
  - `projection_generation_event.v1`
  - `projection_invalidation_event.v1`
  - `continuity_transition_event.v1`
- Deterministic governance chronology replay via `governance_replay_state.v1`.
- Governance replay diff via `governance_replay_diff.v1`.
- Architecture docs for projection ownership, dependency graph, semantic governance model, governance event model, chronology replay, and event ordering semantics.
- Semantic extraction, reconciliation, provenance, temporal continuity, execution context, identity responsibility, compiled authority, semantic lifecycle enforcement, authority execution, and Guard enforcement projection schemas.

### Changed

- README now documents governance event architecture, chronology replay, and new canonical public schemas.
- Public package surface is normalized around deterministic governance objects and reference tooling.
- Package version bumped to `0.4.0`.

### Verification

- Full public-core test suite passes with `198` tests after private workspace staging.

## 0.3.0 - 2026-05-24

Governance-Ledger v0.3.0 adds the canonical semantic derivation layer and promotes semantic governance artifacts to first-class Ledger outputs.

### Added

- `governance_ledger/semantics/` as the canonical semantic derivation layer.
- `governance_impact_preview.v1` for deterministic governance summaries, enforcement behavior, consequences, lifecycle implications, and example governed outcomes.
- `authority_diff_impact.v1` for semantic impact of authority changes, including operational, escalation, lifecycle continuity, and replay continuity implications.
- `governance_review_packet.v1` for review-ready packets that bind authority, previews, optional diffs, optional evidence, review context, immutable inputs, and non-goals.
- `authority_bundle.v1` as the publishable governance object binding authority contracts, publication manifests, semantic artifacts, optional review packets, lineage, provenance, schema compatibility, and immutable inputs.
- CLI commands: `preview`, `diff-impact`, `review-packet`, and `authority-bundle`.
- Canonical JSON schemas for all new semantic artifacts.
- `SEMANTICS.md` documenting semantic governance compilation boundaries, artifacts, guarantees, and CLI examples.

### Changed

- README now describes Ledger as governance compiler and semantic derivation infrastructure.
- Documentation now explicitly distinguishes Ledger-owned governance meaning from Cloud-owned governance operations and Guard-owned admissibility.
- Package version bumped to `0.3.0`.

### Verification

- Full test suite passes with `125` tests.

## 0.2.0 - 2026-05-17

Governance-Ledger v0.2.0 is a major release that repositions Ledger as governance compiler and semantic validation infrastructure.

### Added

- Governance normalization engine with statement classification, normalized statement traces, and coverage reporting.
- Semantic diagnostics for ambiguous authority, weak coverage, overlapping thresholds, duplicate requirements, and compiler validation issues.
- Governance compilation reports with source identity, normalized statements, diagnostics, compiler summaries, and deterministic report hashes.
- Publication gating based on validation errors and blocking compiler diagnostics.
- Authority provenance chain using `governance_authority_lineage.v1`.
- Lineage verification CLI through `verify-lineage`.
- Governance replay tooling through `replay-authority` and `replay-execution`.
- Publication integrity checks for contract, manifest, registry, deployed review, and snapshot transactions.
- Canonical JSON schemas for governance source identity, diagnostics, compilation reports, replay requests, publication manifests, registries, reviews, and snapshots.
- Registry integrity hashing and normalized publication paths.
- Normalization corpus tests for domain policy examples.

### Changed

- Reframed Ledger from earlier extraction-centered workflows to deterministic governance operationalization infrastructure.
- Publishing now treats lineage as Ledger-owned publication evidence and stamps it onto compiled authority contracts before manifest and registry assembly.
- Runtime integration now relies on installed package contracts rather than local checkout path resolution.
- Package version bumped to `0.2.0`.

### Removed

- Local integration path resolution helper.
- Guard compatibility shim for missing replay admissibility exports.
- Test-time imports that pointed at monorepo integration paths.

### Verification

- Full test suite passes with `96` tests.

## 0.1.1 - 2026-05-10

- Early deterministic governance ledger workflows.
- Review lifecycle transitions.
- Basic policy normalization and validation.
- Publication artifacts, manifests, registry entries, snapshots, and rollback support.
