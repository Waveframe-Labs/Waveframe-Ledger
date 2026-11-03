# Pack-1 authoring containment

Pending independent review; no release, migration or deployment is performed.
Coordination: https://github.com/Waveframe-Labs/Waveframe-Operations/issues/3

New repository-changes/1.0.0 authority finalization must contain an affirmative
path allow. Deny-only and acting-role-only policies cannot become newly issued
live-ready authority. The same gate applies before catalog-1 translation
approval and before native v2/v3 finalization, including attempts to finalize a
historically valid approval. This does not extend the gate to action catalogs
2/3 or historical compiled v1 workflows.

The guard is deliberately in new-authoring operations. Existing interpretation
status, immutable pack/catalog identities, review hashes, compiled contract
semantics, compiler output and historical validators are unchanged. Structural
draft readiness is not a promise that new issuance passes the live-safety gate.
Historical deny-only v2 and v3 publications remain verifiable byte-for-byte.
This Ledger protection does not contain execution on its own: use the paired
Guard correction for historical or already cached authority.

To replace a prohibited or incomplete authority, author explicit intended grants
in a new source revision and authority version, individually confirm the new
controls and coverage, review the complete candidate, and obtain fresh human
acceptance. Create new commitments/bundle/receipt hashes through the normal
public workflow. Do not reuse historical approvals, overwrite artifacts or
silently add an allow-all rule. Changed candidate/source/authority bindings
invalidate old confirmations and approvals. The stateless library cannot infer
a prior publication or enforce global revision/identity uniqueness; callers
must preserve revision history and authenticated reviewer/registry controls.
No replacement publication or activation occurs in these PRs.

Tests: `python -m pytest -q tests/test_pack1_authoring_containment.py` checks
domain refusal, translation approval refusal, historical v2/v3 verification,
historical-approval finalization refusal and fresh approval of a new source and
authority revision. The full suite covers explicit grants, existing catalog
generations, legacy output hashes and validation/tampering behavior. New synthetic
evidence lives under `tests/synthetic_evidence/deny_only_v2`, outside the preserved
historical `tests/fixtures` tree. Approval selects allows only from individually
confirmed controls with fully or partially represented human coverage decisions;
proposal and confirmation validation establish their catalog-supported semantics.

## Patch upgrade guidance

The 0.9.1 Ledger / 0.19.1 Guard security patch candidates require an affirmative
path grant. Guard refuses live `compiled_authority_contract.v2` authorization
when `target_requirements.allow` is empty, including deny-only and role-only
authority, with an actionable diagnostic. Deny precedence and explicit grants
remain enforced. Ledger gates new pack-1 repository approval/finalization on
confirmed, enforceable path allows; candidate controls alone do not count.

Historical bundles, receipts, hashes and approvals remain unchanged and
verifiable. Replay retains recorded evidence and exposes any current live
refusal; it does not restore the old permission. Historical v1 and action-scoped
v3 evaluation semantics are unchanged. Replace missing grants with a new source
and authority revision and fresh human review/acceptance. Never reuse an old
approval for changed grants.

Previously published Ledger 0.9.0 and Guard 0.19.0 remain affected in the reproduced
scope. Dependency ranges still admit older packages. After separate publication
approval, explicitly upgrade both packages:

```text
python -m pip install --upgrade governance-ledger==0.9.1 waveframe-guard==0.19.1
python -m pip check
```

A Ledger-only upgrade does not patch an older Guard; a Guard-only upgrade does
not supply Ledger's new-authoring gate. An already satisfied optional extra does
not establish that both patches are installed. No Cloud activation, production
consumer upgrade, or automatic repair of existing approvals is claimed.

These are unreleased candidates. Historical action-policy certification remains
unchanged; separate distribution acceptance must validate these exact artifacts.
Publishing requires separate owner approval and must use only the accepted
files, with SHA256 equality checked on PyPI for Ledger before Guard upload.
Final tags must bind the exact accepted commits (Ledger annotated, Guard
lightweight). No tags or publication are part of this preparation.
