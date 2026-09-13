# Ledger issue #25 durable acceptance

Candidate `a34c11d81b85963794cf28b4adad091fac15e130`, draft [#26](https://github.com/Waveframe-Labs/Waveframe-Ledger/pull/26), stacked on `3cc34e7b3cb6efca5102e0e22d559ec0c0fd583f`.
The [final-head required CI](https://github.com/Waveframe-Labs/Waveframe-Ledger/actions/runs/34786440114) passed all four Windows/Linux x Python 3.10/3.14 cells.
See handoff.json for per-suite JUnit outcomes, exact package SHA-256 hashes and downstream coordination.

Each retained CI ZIP contains fresh Ledger wheel/sdist bytes, the same bytes used in base/combined acceptance,
complete command logs and exit codes, JUnit, source/installed import paths, exact Compiler Git and verified
archive provenance, Guard candidate provenance, ordinary pip resolver reports, package/example checks,
56 required real execution probes, Guard upgrade and old-Ledger rejection checks. Nested immutable Guard
archives retain the original failed combined evidence and prior install/upgrade and supplemental probes.
SHA256SUMS covers every retained file except itself. These archives are committed here independently of
expiring CI retention; the candidate branch and older PR stack heads are unchanged.

Base source and installed suites each passed 674/0/47 (default) and 718/0/3 (development), as passed/failed/skipped.
Combined suites each passed 678/0/44 (default) and 722/0/0 (development).
Every suite executed all 70 release cases; every development suite executed all 44 opt-in cases.
The 44 default skips are intentional development opt-ins; base additionally skips three optional Guard entries
because Guard is absent. Combined optional integrations all execute. Totals include new meaningful regressions.

Historical issue25/41d75bc CI failed because the retained Guard 0.17 example has no close() API;
historical issue25/10ece3b CI failed because the provenance verifier initially rejected Guard's real relocated docs.
Those failed producer results are retained under historical-failed/ and were replaced only by complete
fresh-package runs at the final head. Earlier local preflights are not part of final acceptance.

`release_ready=false`, `runtime_activation_ready=false`. Guard must repin and revalidate this exact Ledger
candidate, rerun its currently red combined CI and correct its stale README minimum Ledger 0.7 claim.
Cloud must complete final package-set/Console acceptance; Cloud #151 used earlier candidate packages.
Guard's retained final-wheel same-device bind-mount pass remains tied to its exact accepted wheel.
Publication order remains Compiler 0.5.0 -> Ledger 0.9.0 -> Guard 0.19.0, followed by ordinary index acceptance
and separately authorized Cloud rollout/activation. No sibling changes, merge, tag, publication, deployment
or activation are authorized. Deletion, rename and macOS remain subsequent scope.
