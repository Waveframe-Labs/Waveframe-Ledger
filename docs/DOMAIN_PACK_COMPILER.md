# Deterministic Domain-Pack Policy Compiler

## Scope and promise

A Waveframe domain pack is an immutable, versioned compiler contract for one bounded policy domain. It is more than a lexicon: it binds scoped vocabulary and synonyms to typed concepts, canonical units, a runtime-fact schema, one deterministic grammar/compiler identity, guided mapping controls, semantic validation rules, one compiler-lowering identity, positive/negative/invalid conformance vectors, and a canonical hash.

This production slice ships one built-in pack: `repository-changes` version `1.0.0`. It does not install packs remotely and does not implement a marketplace or hosted registry. A later platform slice can let an organization host private packs, but a private pack will still need immutable identity/version/hash selection and the same local validation contract; mutable global vocabulary is not part of the design.

No function in this workflow calls an AI model, probabilistic classifier, embeddings service, external inference service, spaCy heuristic, or network lookup. Arbitrary company prose cannot be automatically interpreted under that constraint. Waveframe does not claim otherwise.

## Four distinct representations

The representations have deliberately separate purposes:

1. **Original policy** is the customer's exact UTF-8 bytes. Ledger preserves those bytes, their SHA-256, and a complete ordered partition into statement byte spans.
2. **Canonical controlled language (CNL)** is a deterministic, human-readable preview of the selected meaning. It is review material, not the authority compiler's canonical data model.
3. **Constraint IR** is Waveframe-owned `constraint_ir.v1`: strict typed enforcement meaning. It is not Rego, Cedar, DMN, or JSON Logic.
4. **Compiled authority** is the existing Contract Compiler output used by Ledger's publication pipeline. A pack's named lowering converts supported Constraint IR concepts to that existing boundary.

A CNL preview is always derived from typed meaning. Editing preview text cannot inject a rule.

## Constraint IR and runtime facts

`constraint_ir.v1` represents a subject-kind or exact-principal selector, optional acting role, action, resource selector, allow/deny/require effect, explicitly grouped Boolean conditions, typed literals with canonical units, approval and evidence obligations, separation-of-duty obligations, explicit condition-bearing exceptions, and an exact sorted set of required runtime facts.

Runtime facts are defined by `runtime_fact_schema.v1`. Each fact has a canonical dotted identity, type, optional enum, canonical unit, required/optional status, deterministic derivation description where applicable, and supported comparison operators. Literal types and units must exactly match their fact. Boolean composition uses explicit `group` nodes (`all`, `any`, or unary `not`); object ordering or implicit precedence never carries meaning.

Validation rejects unknown fields, unknown operators or symbols, incompatible comparisons, implicit precedence, untyped values, unavailable facts, undeclared referenced facts, contradictory allow/deny effects, malformed exceptions, and empty enforceable rule sets.

Runtime-fact availability is a publication gate because an unenforceable condition is not partial success. If a rule uses `account.created_at` and the selected schema lacks it, the diagnostic is:

> This rule requires account.created_at, but the selected runtime schema does not provide it.

Ledger never drops that condition or silently weakens the rule.

Explicit exceptions are nested on their parent constraint and carry their own effect and explicitly grouped condition. That makes exception precedence inspectable. The built-in repository lowering does not currently expose exception or evidence controls because the existing compiler boundary has no corresponding representation; publication fails rather than omitting them.

## Guided human mapping without JSON

Directly recognized clauses produce CNL, Constraint IR, and a source-to-constraint mapping. A normative clause outside the deterministic grammar becomes `requires_mapping`; Ledger does not guess its meaning.

`allowed_mapping_controls` in the selected pack describe bounded fields that a future Console can render as forms or decision tables. The Console user selects named choices and enters validated values such as one repository-relative path. They do not author policy JSON or rule JSON.

A successful mapping creates `policy_mapping_decision.v1`, binding:

- the exact source-document hash, statement ID, and byte span;
- exact domain-pack identity, version, and hash;
- the selected pack control and its bounded selections;
- selected subject/role, action, resource, effect, typed condition, obligations, exceptions, and required runtime facts;
- mapper identity, canonical UTC mapping time, generated constraint identity, and canonical decision hash.

The decision produces a canonical CNL preview, typed Constraint IR, source-to-constraint mapping, and both IR/runtime validation results. Unknown selection fields, unknown enum members, unsafe paths, free-form rules, modified spans, and modified hashes fail closed. Finalization reconstructs the interpretation from exact source bytes and replays every decision through the pack control, so recomputing only an outer hash cannot authorize changed meaning.

## Built-in repository-change pack

`repository-changes` / `1.0.0` moves the v0.6 repository sentence grammar behind a domain-specific boundary. Its implementation may continue using its existing exact regular expressions; regexes are an implementation detail, not a public grammar class.

The direct grammar preserves acting-role requirements, exact-path allow/deny, path-prefix allow/deny, numeric approval thresholds, requester/approver separation, and the existing ambiguity/conflict behavior. The pack's guided controls express the same five categories. Pack vocabulary is local to this artifact.

The legacy APIs remain exact v0.6 compatibility wrappers. They intentionally do not add pack metadata, because doing so would change released canonical hashes:

- `interpret_customer_policy(...)`
- `interpret_customer_policy_text(...)`
- `finalize_customer_policy_authority(...)`

## Public API path

All new APIs are available from `governance_ledger`:

```python
from governance_ledger import (
    apply_policy_mapping_decision,
    finalize_domain_policy_authority,
    get_builtin_domain_pack,
    inspect_policy_mapping_controls,
    interpret_policy_with_domain_pack,
    list_builtin_domain_packs,
    validate_constraint_ir,
    validate_domain_pack,
    validate_domain_policy_publication,
    validate_runtime_fact_compatibility,
    validate_runtime_fact_schema,
)

packs = list_builtin_domain_packs()
pack = get_builtin_domain_pack("repository-changes", "1.0.0")

draft = interpret_policy_with_domain_pack(
    exact_policy_bytes,
    domain_pack_id="repository-changes",
    domain_pack_version="1.0.0",
    source_policy_id="repository-policy",
    source_revision="rev-17",
    authority_id="repository-authority",
    authority_version="1.0.0",
)

ir_result = validate_constraint_ir(draft["constraint_ir"], domain_pack=pack)
runtime_result = validate_runtime_fact_compatibility(
    draft["constraint_ir"], pack["runtime_fact_schema"], domain_pack=pack
)

# For a source statement whose classification is `requires_mapping`:
controls = inspect_policy_mapping_controls(draft, statement_id)
application = apply_policy_mapping_decision(
    draft,
    statement_id=statement_id,
    control_id="exact-path-access",
    selections={"effect": "allow", "path": "README.md"},
    mapper_identity="policy-owner@example.com",
    mapped_at="2026-08-30T19:00:00Z",
)
draft = application["updated_interpretation"]

publication = finalize_domain_policy_authority(
    draft,
    approval_id="approval-001",
    approved_by="policy-owner@example.com",
    approved_at="2026-08-30T19:30:00Z",
    committed_by="policy-owner@example.com",
    committed_at="2026-08-30T19:45:00Z",
    publication_id="publication-001",
    published_by="publisher@example.com",
    published_at="2026-08-30T20:00:00Z",
)
```

Direct-only policies skip the mapping calls. A multi-clause policy can apply mapping decisions successively by passing each application's `updated_interpretation` to the next call.

## Publication and compatibility decision

Released `semantic_commit_bundle.v1`, `authority_bundle.v1`, and `publication_receipt.v1` meanings are unchanged. The new path uses them through the existing Ledger/compiler pipeline, then wraps them in additive `domain_policy_authority_bundle.v1` and `domain_policy_publication_receipt.v1` artifacts.

The embedded `authority_bundle.v1` truthfully remains `legacy_provenance_incomplete`: its released schema has no domain-pack lineage profile. The additive envelope is the object that declares complete new-workflow provenance and binds:

```text
exact source bytes
→ exact statement spans
→ direct parse or policy_mapping_decision.v1
→ canonical CNL preview
→ constraint_ir.v1
→ runtime_fact_schema.v1
→ domain_pack.v1 identity/version/hash
→ semantic_commit_bundle.v1
→ compiled_authority_contract.v1
→ authority identity/version
→ embedded authority_bundle.v1 and publication_receipt.v1
→ domain_policy_authority_bundle.v1
→ domain_policy_publication_receipt.v1
```

The semantic-meaning hash can remain stable when a source-only byte changes, as defined by the released semantic commit contract. Its full bundle hash, compiled lineage, both authority bundles, and both receipts change, preserving source-sensitive lineage without changing v1 hash semantics. Missing historical lineage is never inferred for legacy artifacts.
