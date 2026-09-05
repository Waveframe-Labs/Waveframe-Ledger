# Waveframe Ledger v0.8.0 Release Notes

## Untrusted policy-translation boundary

Waveframe Ledger v0.8.0 introduces a strict authoring boundary for untrusted policy
translation proposals. An external model or deterministic form may propose bounded
controls, but every control is independently confirmed by a human before it can become
authority. Ledger validates exact source provenance, trusted capability confinement,
human decisions, chronology, and deterministic lowering. It does not call or bundle an
AI/model provider and does not claim arbitrary English policy comprehension.

One source clause may produce multiple independently confirmed controls. A partially
covered clause preserves exact residual unsupported spans and requires explicit human
acknowledgement. Only the confirmed controls become executable; residual meaning stays
visible as public provenance and never becomes implicit runtime behavior.

## Additive native v3 publication

The new `policy_translation_commitment.v1`, `authority_bundle.v3`, and
`publication_receipt.v3` artifacts are additive. They bind confirmed controls,
acknowledged residual meaning, Constraint IR, source and approval identities, and the
complete publication chain without changing existing v1/v2 artifacts. The runtime
payload remains `compiled_authority_contract.v2`.

Provider/model attribution, prompts, requests, responses, retries, failures,
explanations, and token usage remain private authoring evidence. They are independently
deletable and are not required to validate, load, or enforce the published v3 authority.

## Guard compatibility

Ledger 0.8.0 restores its optional `guard` extra with the exact release-tested
dependency:

```text
waveframe-guard==0.17.0
```

Guard 0.17.0 declares `governance-ledger>=0.7.0,<0.9.0`. It verifies native v3 bundles
and their mandatory matching receipts before enforcing the unchanged v2 compiled
runtime payload. Existing v1/v2 loading, verification, caching, runtime-fact, and
enforcement behavior remains compatible.

Install the release pair with normal dependency resolution:

```text
pip install "governance-ledger[guard]==0.8.0"
```

## Availability

Local authoring, publication, registry resolution, verification, and Guard enforcement
are available in this release. Hosted Cloud authoring and native v3 serving are not yet
available. This release does not modify or deploy Cloud or Guard.

This pull request prepares the release only. It does not merge the branch, create a tag
or GitHub release, upload to PyPI, publish a package, or deploy a service.
