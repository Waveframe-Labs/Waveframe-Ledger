---
title: "Published Authority Specification"
filetype: "documentation"
type: "platform-contract"
domain: "governance-publication"
version: "1.0.0-draft"
status: "Draft"
created: "2026-07-13"
updated: "2026-07-13"
author:
  name: "Waveframe Labs"
license: "Apache-2.0"
ai_assisted: "partial"
---

# Published Authority Specification

## 1. Purpose

This document defines **Published Authority** as the canonical governance publication concept used across the Waveframe platform.

A Published Authority is not merely a compiled contract file. It is an immutable, version-addressed governance publication that binds deterministic enforcement semantics to the evidence required to identify, verify, distribute, inspect, and replay that authority.

The platform lifecycle is:

```text
Human policy
  -> Ledger review and approval
  -> deterministic compilation
  -> Published Authority
  -> registry resolution
  -> Guard enforcement
  -> Cloud preservation
  -> Operations inspection
```

This specification establishes the boundary between governance authoring and runtime enforcement. Ledger owns publication. Guard consumes published authority. Cloud stores and distributes it. Operations surfaces its state and evidence.

## 2. Product ownership

| Component | Responsibility |
| --- | --- |
| Waveframe Ledger | Author, review, approve, compile, publish, and register authority. |
| Contract Compiler | Produce deterministic compiled enforcement semantics. |
| Waveframe Guard | Resolve an explicit authority reference and enforce it before execution. |
| CRI-CORE | Evaluate admissibility under the resolved compiled authority. |
| Waveframe Cloud | Store, distribute, preserve, and lifecycle-manage published authority and execution evidence. |
| Operations | Explain publication state, runtime outcomes, receipts, lineage, and replay history. |

No component other than Ledger may redefine the semantic contents of a Published Authority.

## 3. Canonical term

The user-facing platform term is:

```text
Published Authority
```

The canonical machine-readable publication object is:

```text
authority_bundle.v1
```

`authority_bundle.v1` is the transport and preservation representation of a Published Authority. The conceptual name and schema name serve different purposes:

- **Published Authority** is the product and domain concept.
- **`authority_bundle.v1`** is the canonical serialized object currently used to represent it.

A compiled contract by itself is not a Published Authority.

## 4. Authority identity

Every Published Authority MUST have an immutable identity composed of:

```text
authority_id + authority_version + contract_hash
```

The canonical human- and API-facing reference is:

```text
<authority_id>@<authority_version>
```

Example:

```text
finance-policy@1.2.0
```

The reference identifies a single published version. The `contract_hash` verifies the immutable compiled authority resolved by that reference.

### 4.1 Identity requirements

A Published Authority MUST include:

- `authority_id`
- `authority_version`
- `authority_ref`
- `contract_hash`
- `publication_id`
- `published_at`
- `schema_version`

The following invariant MUST hold:

```text
authority_ref == authority_id + "@" + authority_version
```

A registry MUST reject ambiguous or unversioned runtime resolution.

The following is valid:

```text
finance-policy@1.2.0
```

The following is not a deterministic runtime reference:

```text
finance-policy
```

Aliases such as `latest` or `active` may exist in operator-facing discovery surfaces, but Guard MUST resolve them to an explicit immutable authority reference before enforcement begins.

## 5. Required publication contents

A Published Authority MUST bind the following classes of information.

### 5.1 Compiled enforcement authority

The deterministic compiled authority consumed by Guard and CRI-CORE, including:

- contract identifier
- contract version
- authority requirements
- approval requirements
- artifact requirements
- stage requirements
- invariants
- contract hash

### 5.2 Publication identity

The immutable publication record, including:

- publication identifier
- publication timestamp
- publisher identity or publishing actor
- authority reference
- publication status
- publication schema version

### 5.3 Governance lineage

The evidence connecting the published authority to its source and review process, including as applicable:

- source governance identity
- source hash
- compilation report hash
- review identifier
- approval evidence
- compiler identity and version
- provenance chain

### 5.4 Semantic review artifacts

The deterministic artifacts required to understand the authority without reinterpreting policy, including as applicable:

- governance impact preview
- authority diff impact
- governance review packet
- diagnostics
- compatibility declarations

### 5.5 Publication integrity

The hashes and manifests required to verify that the publication has not changed, including:

- contract hash
- publication manifest hash
- bundle hash or equivalent canonical object hash
- bound artifact hashes
- schema compatibility metadata

## 6. Publication transaction

Publication MUST be treated as one deterministic transaction.

A successful Ledger publication produces or updates all required artifacts together:

```text
compiled authority contract
publication manifest
authority bundle
registry entry
deployed review record
snapshot
publication receipt
```

Publication MUST fail without partial registration when any required gate fails.

Blocking conditions include:

- review is not approved
- compilation diagnostics block publication
- authority identity conflicts with an existing immutable version
- contract hash does not match the compiled authority
- required lineage evidence is missing or inconsistent
- registry update cannot be completed
- snapshot or receipt generation fails where required by the publication transaction

Published artifacts are immutable. Corrections require a new authority version and a new publication.

## 7. Registry contract

The authority registry is the deterministic discovery surface between publication and enforcement.

A registry entry MUST allow a consumer to resolve:

```text
finance-policy@1.2.0
```

into the corresponding Published Authority or its compiled enforcement subset.

### 7.1 Minimum registry entry

A registry entry MUST include:

- `authority_ref`
- `authority_id`
- `authority_version`
- `contract_hash`
- `publication_id`
- `published_at`
- `lifecycle_state`
- a deterministic location or retrieval identifier for the canonical authority bundle

### 7.2 Lifecycle state

Supported lifecycle states are:

- `active`
- `superseded`
- `revoked`

Lifecycle state does not alter the immutable contents of the published version. It is append-only operational metadata associated with that version.

Guard policy determines whether a resolved state is acceptable. For example, a runtime may reject revoked authority and warn on superseded authority.

### 7.3 Registry implementations

The registry contract MUST remain implementation-independent.

Valid implementations may include:

- Ledger local publication registry
- verified local cache
- Waveframe Cloud organization registry
- self-hosted enterprise registry
- offline registry snapshot

Guard MUST depend on the registry interface and canonical publication contract, not on Ledger file paths or Cloud-specific storage internals.

## 8. Guard resolution contract

The intended developer-facing API is explicit authority selection:

```python
@guard.protect(authority="finance-policy@1.2.0")
def transfer(execution_request):
    ...
```

The resolution sequence is:

```text
authority reference
  -> registry lookup
  -> publication identity verification
  -> contract hash verification
  -> lifecycle-state check
  -> compiled authority extraction
  -> local enforcement
```

Guard MUST NOT:

- interpret source policy
- choose an authority version implicitly at enforcement time
- trust a contract whose hash does not match the publication identity
- require knowledge of Ledger's internal file layout
- make Cloud availability a prerequisite for a locally cached admissibility decision

## 9. Cloud contract

Cloud stores and distributes Published Authorities but does not author or reinterpret them.

Cloud MAY:

- accept a canonical `authority_bundle.v1`
- validate schema shape and hashes
- enforce organization ownership
- preserve immutable publication artifacts
- expose explicit authority lookup
- maintain lifecycle metadata
- issue durable publication receipts
- distribute verified authority to Guard
- export replay and recovery packages

Cloud MUST NOT:

- compile source policy into authority
- modify published authority semantics
- decide runtime admissibility
- replace Guard or CRI-CORE as the execution boundary

## 10. Operations contract

Operations surfaces the state of Published Authority across the platform.

The operator experience SHOULD expose:

- authority reference
- version
- contract hash
- publication identifier
- publisher
- publication time
- lifecycle state
- review and approval status
- source and compilation lineage
- deployment and cache posture
- Guard usage and associated outcomes
- receipts and replay packages

Operations explains what happened and what needs attention. It does not author policy or decide admissibility.

## 11. Naming and compatibility

The repository is named **Waveframe Ledger**.

The Python distribution name MAY remain:

```text
governance-ledger
```

The repository name, product name, import package, and PyPI distribution name are independent identifiers. Renaming the GitHub repository does not require changing:

- the PyPI project name
- the `governance_ledger` Python package
- the `governance-ledger` CLI command

A package rename should occur only as a deliberate compatibility migration, not as a consequence of repository branding.

## 12. Sprint 1 acceptance criteria

Sprint 1 is complete when Waveframe Ledger can prove the following locally:

1. Publishing produces a stable `authority_ref`.
2. Publishing produces a stable `publication_id`.
3. Publishing binds the exact compiled `contract_hash`.
4. Publishing emits a canonical `authority_bundle.v1`.
5. The local registry records the authority bundle by explicit versioned reference.
6. A lookup for `finance-policy@1.2.0` deterministically resolves the correct immutable publication.
7. Duplicate publication of the same identity cannot silently replace different contents.
8. Published identity and registry behavior are covered by tests.
9. Existing publication, snapshot, lineage, and replay behavior remains compatible.
10. Guard-specific loading is deferred until the Ledger publication contract is complete.

## 13. Non-goals for Sprint 1

Sprint 1 does not include:

- hosted Cloud retrieval
- Guard networking
- billing or entitlements
- organization administration UI
- policy interpretation by an AI model
- runtime enforcement changes
- replacement of existing canonical schemas without a demonstrated incompatibility

## 14. Governing principle

A governance policy becomes operational only when it is published as immutable, verifiable, version-addressed authority.

```text
Ledger publishes authority.
Guard resolves and enforces authority.
Cloud preserves and distributes authority.
Operations explains authority and its consequences.
```
