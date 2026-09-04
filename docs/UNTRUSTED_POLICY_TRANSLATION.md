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
provider explanation as approval text. The exact candidate response may be retained as
canonical base64 plus a byte-for-byte SHA-256 in private proposal evidence. Schema
validity proves only structural and capability confinement; it does not prove that the
provider understood the policy.

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

Changing one source byte changes the snapshot hash, clause identities, proposal and
approval identities, semantic commitment, compiled contract, bundle, and receipt.

## Public trust stages

The public APIs keep trust transitions explicit:

- `get_policy_translation_capability_catalog()` returns the immutable finite catalog.
- `create_policy_translation_proposal(...)` canonicalizes exact source and raw candidate
  evidence; it performs no inference.
- `validate_policy_translation_proposal(...)` validates structure, exact coverage,
  hashes, source/authority identity, and capability confinement. It returns
  `semantic_validity: not_established`.
- `inspect_policy_translation_proposal(...)` reports exact coverage and unresolved work.
- `apply_policy_translation_binding(...)` accepts one human answer of a declared bounded
  type.
- `apply_policy_translation_disposition(...)` confirms one control or explicitly
  acknowledges one unenforced clause.
- `render_policy_translation_review(...)` derives operational text from the validated
  control. Provider explanations are never included.
- `approve_policy_translation_proposal(...)` binds the completed confirmation,
  deterministic review, catalog, source, authority, and enforced/unenforced counts.
- `finalize_policy_translation_authority(...)` replays everything from source bytes and
  lowers through the existing v2 publication implementation.

Proposal, confirmation, and approval objects are immutable canonical values. Applying a
binding or disposition returns a new confirmation rather than mutating its input.

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

Repository paths supplied as source literals must occur byte-for-byte in their clause.
Organizational roles or paths not literally established by the source remain typed,
unresolved questions until a human supplies a value accepted by the catalog.

The current catalog fails closed for human/service actors, repository identity, branch,
push, pull-request open/approve/merge, changed-file count, reviewer identity/team,
approval counts and thresholds, requester/approver separation of duties, environment,
evidence requirements, external scanner findings, IaC plans, cloud provisioning, and
financial systems. Constraint IR can represent some of these concepts, but the released
v2 repository lowering cannot; representation is not treated as support.

Those capabilities require separately released Contract Compiler/domain-pack lowerings
and matching Guard runtime fact providers/evaluators. They must not be added to a Ledger
catalog until both sides exist under immutable identities and hashes.

## Coverage and partial publication

Every clause has one proposal status:

- `enforceable_fully_bound`;
- `needs_concrete_answer`;
- `integration_dependent`;
- `unsupported`;
- `informational`.

Proposal status is not approval. Every clause still requires a human disposition.
Publication fails if a binding or clause is unresolved, if there is no enforceable
control, or if an unenforced clause lacks explicit acknowledgement. The confirmation,
approval, and finalization result report exact total, enforced, unenforced, unresolved,
and acknowledged clause counts and identities.

Released `authority_bundle.v2`, `publication_receipt.v2`,
`compiled_authority_contract.v2`, all v1 schemas, and the v0.6 compatibility path are
unchanged. No v3 runtime artifact is introduced merely to retain model output.
