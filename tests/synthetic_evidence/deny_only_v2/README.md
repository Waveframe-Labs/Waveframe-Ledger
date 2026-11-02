Historical synthetic evidence, retained for validation regression only.

`bundle.json` and `receipt.json` are unmodified files from the Stream #3
executable reproduction using Ledger 0.9.0 / Compiler 0.5.0. Source release
commits: bd82c11dc0c4d4003063c7f2ce0f2e87f12f7bf1 and
f817a1bca65806c9ee33ccc74c2238952ebf8f01.

`historical-partial-v3.json` was generated with the installed, unpatched Ledger
0.9.0 / Compiler 0.5.0 using the pre-containment partial-translation fixture and
public approval/finalization APIs. It retains proposal/confirmation/approval
and finalization for tests that verify history but refuse new issuance. These
are synthetic local artifacts; never publish or activate them.

`historical-deny-approval.json` was produced by the same installed original
Ledger 0.9.0 public approval API, for the exact deterministic deny-only clause.
Both new finalizers must refuse it despite its valid historical approval binding.
