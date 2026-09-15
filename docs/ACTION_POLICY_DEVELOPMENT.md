# Action policy development path (issue #17)

This is an opt-in Ledger development implementation, not a released creation capability.
The default catalog remains `1.0.0`, with only `modify`; ordinary authoring and v2/v3
publication workflows retain their existing defaults. Package version and dependency
ranges remain unchanged. No hosted Cloud feature is activated.

The implementation follows [Ledger #17](https://github.com/Waveframe-Labs/Waveframe-Ledger/issues/17)
and its compiler handoff. Install the **exact candidate package** in a separate environment:

```powershell
python -m venv .venv/issue17
.venv/issue17/Scripts/python -m pip install -e '.[dev]' -r requirements-action-policy-dev.txt build twine
.venv/issue17/Scripts/python -m pip check
$env:WAVEFRAME_LEDGER_ACTION_POLICY_DEV = '1'
.venv/issue17/Scripts/python -m pytest tests/test_action_policy_v4.py -q
.venv/issue17/Scripts/python -m pytest -q
.venv/issue17/Scripts/python examples/native_v4_development.py
```

`requirements-action-policy-dev.txt` pins repository
`Waveframe-Labs/cricore-contract-compiler` at commit
`3b91fcc03c804804b2ace7302f37340a787496d9`. Its metadata still reports `0.4.0`;
that number does **not** identify this candidate. Acceptance checks its installed
PEP 610 `direct_url.json` commit and uses `from compiler import compile_action_policy`.
Published PyPI 0.4.0 lacks that API. There is no legacy compiler fallback and no
vendored compiler implementation. Candidate provenance is development evidence only,
not a published package dependency. See [recorded acceptance evidence](acceptance/issue17/README.md).

## Explicit authoring and publication

Set `WAVEFRAME_LEDGER_ACTION_POLICY_DEV=1`, obtain
`governance_ledger.action_policy.get_development_capability_catalog()`, and pass
`catalog_version="2.0.0"` explicitly to translation run/proposal creation.
Use `repository-changes@2.0.0` for domain interpretation and
`governance_ledger.action_policy_publication.finalize_policy_translation_authority_v4`
for publication. Current finalizers reject this catalog. The environment opt-in
alone never changes the default catalog or default proposal/run version.

The new immutable catalog uses `policy_translation_capability_catalog.v2` and has
six controls indexed by `(control_type, action)`. Pack, runtime schema, grammar,
each emitter, and lowering have separately versioned identities. The runtime
instance is `repository-changes-runtime@2.0.0`. Its facts contain no caller-asserted
filesystem existence or file-creation preconditions.

The bounded grammar recognizes explicit statements such as:

* `Agents may create generated/new.md and modify README.md.`
* `Agents must not create files under generated/private/.`
* `Agents must use role repository-maintainer to create repository files.`

Each resulting control needs its own confirmation, including both controls in a
mixed clause. Exact source byte spans, control identities, confirmed coverage,
review, and approval remain bound throughout publication. `write` and `change` do
not infer create/modify permission in catalog 2.0.0. Path-dependent role clauses,
conditional clauses, and other unmatched wording cannot produce controls in this
bounded path; they must remain explicitly unsupported or be rewritten and reviewed
as a new source revision. Organizational role/path inference is not added here.

An action has its own scalar `required_role`, `allow`, and `deny`. No action or no
matching allow means no permission; roles only restrict an action. Same-action
identical allow/deny selectors and duplicate selectors reject. Distinct overlapping
selectors retain explicit deny precedence. Cross-action selectors and roles never
conflict or leak. Publication requires at least one path allow overall. A deny-only
or role-only action can accompany another action with an allow; it grants no operation.
Review explicitly describes those non-grants and creation preconditions. Development
customer coverage says `Not currently enforceable`, even for completely represented
meaning. Reused confirmation coverage fields named `enforced_*` describe represented
policy meaning, not a claim of deployed runtime availability.

## Public verification and historical compatibility

Ledger lowers validated `constraint_ir.v1` to compiler-owned `action_policy.v1`.
It checks the raw output's **exact** five-field shape, `compiled_action_contract.v1`
discriminator, authority identities, full action-block equivalence, and unsigned
canonical SHA-256 before building `compiled_authority_contract.v3`. Raw compiler
hashes are unprefixed. Ledger's authority hash is separately computed over its
schema, retained raw output, actions, and source/IR/semantic/compiler provenance.

Native `authority_bundle.v4`/`publication_receipt.v4` are built directly from the
new meaning; no v3 bundle is relabeled. Validators reconstruct the source partition,
controls, individual confirmations, IR, runtime/pack/emitter bindings, normalized
compiler input, semantic commitment, authority, approval, manifest, provenance,
bundle, and receipt. Retained compiler output is compared to this independently
derived input. Verification needs no compiler package, model response, private
provider identity, or provider explanation. Hashes provide content integrity and
binding, not identity authentication against an attacker able to replace all trusted
approval and registry commitments.

Translation proposal, confirmation, approval, review, and commitment v1 structures
are reused without changing historical schemas. All three new fixture chains pass
those existing JSON schemas. Recorded catalog identity selects the trusted parser,
comparison, rendering, and emitter set; default/historical wording is unchanged.
`domain_pack.v1`, `runtime_fact_schema.v1`, and `constraint_ir.v1` validators support
the new instance vocabulary without widening the historical instance.

Explicit unknown bundle/receipt/compiled-contract versions and mixed or downgraded
envelopes reject. Established absent-version legacy envelopes remain recognized;
explicit null versions are not absent versions. Public v4 validators themselves
require the development opt-in. No historical authority is upgraded to create.

Fixtures in `tests/fixtures/action_policy_v4/{create-only,modify-only,mixed}` retain
exact source, interpretation, proposal, confirmations, review, approval, IR, input,
raw output, enriched authority, bundle, and receipt. Run the generator to reproduce
them with the real candidate; tests compare full content, not only selected hashes.

## Validation and activation gates

`tools/check_action_policy_history.py` compares canonical historical artifacts with
published Ledger 0.8.0. `tools/check_action_policy_old_runtime.py` runs under `python -I`
in separate ordinary published-package environments (`waveframe-guard==0.18.0` with
`governance-ledger==0.7.0` or `==0.8.0`). It tests native fixtures, discriminator
downgrades, unknown versions, and mixed receipt/bundle pairs. It does not bypass
Guard's Ledger `<0.9` constraint. `tools/check_action_policy_legacy_operations.py`
checks an allowed modify callback, blocked unlisted modify, and blocked create on a
historical authority using published Ledger 0.8/Guard 0.18. Callbacks do not write bytes.

`tools/check_action_policy_package.py` runs under `python -I` against the installed
Ledger wheel plus pinned compiler, reproduces all three fixtures, and verifies the
public artifacts with the compiler import unavailable. The sdist includes schemas,
fixtures, examples, and acceptance tools; runtime wheel validation uses packaged
Python validators and does not require source-tree schemas.

Remaining gates are deliberate:

* Compiler merge/release, minimum-interpreter and CI evidence, and a coordinated
  published dependency range. Local Windows/Python 3.14 evidence is not that release gate.
* Future Guard action-aware native v4 validation and runtime creation support,
  including actual bytes, existing parent, no overwrite/parent creation, workspace
  containment, collisions, races, unsupported operations, and truthful partial-write
  failure evidence. Logical authorization and operation failure remain distinct.
* Actual cross-package release compatibility, including forged legacy-envelope
  defenses in downstream readers. Native rejection tests do not prove arbitrary
  relabeling attacks safe in released readers.
* Cloud integration, explicit customer acceptance, and a separate activation decision
  before advertising the catalog as currently enforceable. No mandatory content
  capture or content hash is introduced; content stays trusted callback input.

The manual `action-policy-development.yml` workflow adds candidate validation only;
existing publication workflows are unchanged. This change does not merge, tag,
release, publish a package, operate on another repository, or implement filesystem
operations.
