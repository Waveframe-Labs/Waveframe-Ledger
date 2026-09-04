# Untrusted policy translation proposals

`policy_translation_proposal.v1` is a model-agnostic authoring boundary for engineering
policy. A model may propose a bounded interpretation, but it never decides what is
authorized:

1. A model or deterministic form proposes.
2. A human supplies organizational bindings, confirms executable controls, and
   acknowledges every unenforced clause.
3. Ledger validates, deterministically renders the review, reconstructs the result from
   the exact embedded source bytes, and compiles it through the released v2 path.
4. Guard validates and enforces the published authority without a model or proposal
   artifact.

Ledger does not call a provider, load provider credentials, access the network, or use a
provider explanation as approval text. The proposal contains an ordered, non-empty,
hash-chained `translation_runs` collection. Each descriptor binds the exact source,
catalog, provider class and model/deployment attribution, template, request
configuration, request hash, response hash, optional explanation hash, canonical
timestamps, sequence, and prior run hash. A chained run cannot start before its
predecessor completes, and every run must complete before human confirmation and
approval. The proposal contains no raw request, response, or provider-written
explanation. Schema validity proves only
structural and capability confinement; it does not prove that a provider understood the
policy.

Optional raw bytes belong in a separate private
`policy_translation_run_evidence.v1` artifact. That artifact validates independently
against one run descriptor and may be deleted under retention policy without changing
the proposal, confirmation, approval, bundle, receipt, or Guard verification. Runtime
authority never depends on it.

## Exact source and authority chain

The proposal embeds canonical base64 of the original bytes, a byte-for-byte SHA-256,
source identity and revision, authority identity and version, and the complete ordered
clause partition. Each non-empty byte belongs to exactly one clause produced by the
released deterministic partitioner. Missing, duplicate, overlapping, reordered, or
modified clauses fail validation.

Human confirmation and approval bind the proposal hash, source snapshot hash, authority
reference, capability-catalog hash, deterministic review hash, exact coverage counts,
and every binding/disposition. The derived approval identity is passed through the
unchanged `authority_bundle.v2` approval record. The approved executable meaning then
follows the existing normative chain:

`exact bytes → snapshot hash/spans → human decisions → Constraint IR → semantic commit → compiled_authority_contract.v2 → authority_bundle.v2 → publication_receipt.v2`

The v2 bundle independently contains and verifies the exact source bytes, spans,
decisions, Constraint IR, semantic commitment, compiled contract, approval, and receipt
bindings. Provider output and the proposal are deliberately absent. Guard therefore
does not need a provider, proposal, or provider explanation at evaluation time. Its
verified bundle/receipt and execution evidence transitively bind the exact source
snapshot.

Changing one source byte changes the snapshot hash, every bound translation-run
descriptor, clause identities, proposal, confirmation and approval identities, semantic
commitment, compiled contract, bundle, and receipt.

## Public trust stages

The public APIs keep trust transitions explicit:

- `get_policy_translation_capability_catalog()` returns the aggregate immutable catalog
  currently enforceable by Waveframe. Customers do not choose a catalog or profile.
- `resolve_policy_translation_capability_catalog(...)` resolves an exact catalog
  ID/version/hash only from Ledger's trusted registry. Callers cannot inject catalogs.
- `validate_policy_translation_capability_catalog(...)` rejects unreachable or
  internally inconsistent advertised capabilities.
- `create_policy_translation_run(...)` creates one ordered hash-only attribution
  descriptor against Ledger's aggregate trusted catalog; it accepts no caller-selected
  catalog.
- `create_policy_translation_run_evidence(...)` and
  `validate_policy_translation_run_evidence(...)` manage optional private raw evidence
  outside the proposal.
- `create_policy_translation_proposal(...)` canonicalizes exact source, clauses, and
  ordered run descriptors; it performs no inference.
- `validate_policy_translation_proposal(...)` validates structure, exact coverage,
  hashes, source/authority identity, and capability confinement. It returns
  `semantic_validity: not_established`.
- `inspect_policy_translation_proposal(...)` reports exact coverage and unresolved work.
- `apply_policy_translation_binding(...)` accepts one human answer of a declared bounded
  type.
- `apply_policy_translation_control_confirmation(...)` confirms one candidate control;
  every control in a clause requires its own confirmation.
- `apply_policy_translation_disposition(...)` confirms the clause-level semantic
  coverage decision and explicitly acknowledges any residual unsupported meaning.
- `render_policy_translation_review(...)` derives operational text from the validated
  control. Provider explanations are never included.
- `validate_policy_translation_review(...)` validates the strict
  `policy_translation_review.v1` artifact that approval hash-binds.
- `approve_policy_translation_proposal(...)` binds the completed confirmation,
  deterministic review, catalog, source, authority, and enforced/unenforced counts.
- `finalize_policy_translation_authority(...)` replays everything from source bytes and
  lowers through the existing v2 publication implementation.

Proposal, confirmation, and approval objects are immutable canonical values. Applying a
binding, control confirmation, or coverage decision returns a new confirmation rather
than mutating its input.

## Current truthful capability coverage

The built-in `waveframe.coding-agent.repository-change@1.0.0` catalog is the exact
intersection of Ledger's `repository-changes@1.0.0` lowering and Guard 0.16.1's trusted
repository-change runtime-fact boundary. It supports only:

- actor kind `autonomous_agent` (lowered to the released `agent` subject);
- action `modify`;
- repository-scoped acting roles from the released role enum;
- exact repository-path allow/deny;
- repository-path-prefix allow/deny;
- the released actor/action/resource/path runtime facts and their exact supported
  equality/prefix operators;
- enforcement at `waveframe.guard.repository-change.v1`.

Source literals carry an absolute byte span, exact UTF-8 surface value, byte-slice hash,
and deterministic canonical value. Their spans must stay inside the clause and cover a
whole lexical token: substrings such as `README.md` from `README.md.bak`, `deploy/` from
`predeploy/`, and role names inside larger identifiers fail closed. Quotes and backticks
at both edges remain valid lexical boundaries; when accepted by the released path
grammar, their bytes remain part of the exact path literal rather than being silently
stripped. Repository-role surface synonyms are canonicalized only by the released
domain-pack vocabulary.
Organizational roles or paths not literally established by the source remain typed,
unresolved questions until a human supplies a value accepted by the catalog.

The proposal schema uses portable structural identifiers; it does not encode the three
current control types, fact IDs, operators, effects, binding types, or enforcement point.
Semantic availability comes only from resolving the proposal's exact catalog reference
through Ledger's internal trusted registry. The initial registry contains only the
built-in repository catalog. The catalog derives its advertised facts, operators,
effects, binding types, and enforcement points from reachable control definitions. It
advertises only `==` and `starts_with`; `!=` is absent because no candidate control and
v2 lowering use it. Adding a trusted capability later therefore does not require
`policy_translation_proposal.v2`, but it still requires released compiler lowering and
Guard runtime support before the aggregate catalog may advertise it.

The current catalog fails closed for human/service actors, repository identity, branch,
push, pull-request open/approve/merge, changed-file count, reviewer identity/team,
approval counts and thresholds, requester/approver separation of duties, environment,
evidence requirements, external scanner findings, IaC plans, cloud provisioning, and
financial systems. Constraint IR can represent some of these concepts, but the released
v2 repository lowering cannot; representation is not treated as support.

Those capabilities require separately released Contract Compiler/domain-pack lowerings
and matching Guard runtime fact providers/evaluators. They must not be added to a Ledger
catalog until both sides exist under immutable identities and hashes.

Guard 0.16.1 independently validates the final v2 publication, but its released Python
package metadata constrains Ledger to `<0.8.0` and consequently excludes this
`0.8.0.dev0` checkout. Ledger's compatibility job installs that exact released Guard
wheel without dependency resolution as supplemental runtime evidence only. It is not
package compatibility. Ledger 0.8 publication is blocked until a separately reviewed
Guard release widens and tests the range, Ledger restores an extra pinned to that
release, and a clean `pip install "governance-ledger[guard]"` plus `pip check` passes.

## Coverage and partial publication

Every clause has an ordered `candidate_controls` array containing zero or more controls.
Each control carries its own exact source-literal span and hash. Duplicate or
contradictory controls fail validation. Every clause also has exactly one proposal
coverage decision:

- `fully_represented`;
- `partially_represented`, with exact residual unsupported spans;
- `entirely_unsupported`, with exact residual unsupported spans;
- `informational`.

Proposal validation reconstructs deterministic domain interpretation. A clause already
recognized as direct must contain every corresponding control in deterministic order
and exact executable semantics; neither provider output nor a human decision may omit
one or downgrade the clause. For arbitrary English outside that deterministic grammar,
Ledger cannot mathematically prove that an untrusted translator extracted every
meaning. Ledger proves source preservation, capability confinement, and the exact
mapping the human reviewed; semantic completeness is explicitly human-confirmed.

A clause is not fully represented merely because one meaning was mapped. Partial
publication requires exact residual spans and the approver's explicit acknowledgement.
Publication fails if a binding, control confirmation, or clause decision is unresolved,
if there is no confirmed enforceable control, or if residual/unsupported meaning lacks
acknowledgement. Coverage reports exact clause and control totals and identities.
Because a partially represented clause contains both enforced and residual unenforced
meaning, it truthfully appears in both the enforced-clause and unenforced-clause sets;
the dedicated partial count removes any ambiguity.

The unchanged v2 path can publish a deterministic source statement that produces
multiple native constraints (for example, `Agents may modify README.md and
CHANGELOG.md.`). Released `policy_mapping_decision.v1` can encode only one human-mapped
control for an otherwise pending statement. Consequently, finalization fails closed if
an arbitrary pending clause contains multiple human-mapped controls; representing that
approval meaning requires a separately reviewed normative publication extension, not a
silent change to v2.

The same v2 limitation applies to a pending clause that mixes an enforced mapping with
residual unsupported meaning: released `policy_mapping_decision.v1` classifies the whole
statement with one disposition. Ledger can validate, render, and approve the explicit
partial boundary, but finalization fails closed because v2 cannot truthfully preserve
that mixed normative meaning. Publication requires a separately reviewed additive
normative schema/path; Ledger does not silently label the entire clause enforced.

Released `authority_bundle.v2`, `publication_receipt.v2`,
`compiled_authority_contract.v2`, all v1 schemas, and the v0.6 compatibility path are
unchanged. No v3 runtime artifact is introduced merely to retain model output.
