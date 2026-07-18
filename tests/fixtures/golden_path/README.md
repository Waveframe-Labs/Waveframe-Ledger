# Golden Path Published Authority Fixture

This fixture is the canonical Ledger v0.5.0 publication used by Waveframe's cross-repository Golden Path.

It was produced by the real Ledger approval and publication pipeline with fixed timestamps, then consumed unchanged by Guard v0.13.0 through the local registry resolver.

Identity:

- Authority: `finance-policy@1.0.0`
- Publication: `pub_20260717_0001`
- Contract hash: `sha256:3bd442fc699ef42643e0b22c42935f5a14e037473f05a1bc20757c0f565756f9`
- Bundle hash: `sha256:db63dd6d796f4f44f861427c1aa81e3907c54893edca64798b1602c41485c9d6`

Consumers must treat the files under `contracts/` as immutable generated artifacts. Tests may copy this directory to a temporary workspace, but must not rewrite the bundle before passing it to Guard.
