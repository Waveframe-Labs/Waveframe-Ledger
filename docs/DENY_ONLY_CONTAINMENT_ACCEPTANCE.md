# Independent deny-only containment acceptance

Scope: `legacy-v2-deny-only-containment`. This is not historical action-policy
release certification. `release_ready=false`, `runtime_activation_ready=false`,
and `historical_certification="not claimed"` remain true even on success. The
historical failed check remains separate; no branch protection or trigger is
rewired. Approval: Stream issue 3, comment 6590242049.

## Exact inputs and movement

Ledger PR 27's full head SHA comes from the PR event (or explicit manual input),
not a merge simulation. Guard PR 69 is pinned to
`e77c7fb718009b947daba621155baa43315fa045`. Both remote PR heads must equal those
inputs at start and finish. Any movement invalidates the run and requires a
deliberate re-pin/revalidation and a fresh four-cell run. Ledger runtime bytes
must also match the reviewed security head
`058d561d4a9ef7a2cfd039a9a6f44bb8793e90b6`; additions since that head are limited
to the four approved acceptance files. CI-only head movement automatically binds
a new full event SHA and reruns all checks; runtime movement requires an explicit
update of that reviewed runtime pin after review.

Released bases: Ledger `bd82c11dc0c4d4003063c7f2ce0f2e87f12f7bf1`, Guard
`599c132038f66b5f15b47752505f0ed1aae1d641`. The independent scope permits only
Ledger's three authoring modules and Guard's one cognition module. The original
release fixtures/schemas/examples/evidence and historical runners/workflow are
compared unchanged. No old `gates.base` or `combined_extra` result is accepted.

Compiler is installed from exact Git ref
`ae590dee058d3481e384dea850d5b7d980f533ff`, with honest PEP 610 provenance.
Requirements/build tools are constrained by unchanged `requirements-ci.txt`.
The first clean environment's complete transitive versions become constraints
for the other two environments in the same cell. Pip reports retain every
resolved archive URL/digest or VCS source; freeze and pip-check results are kept.
Different Python/platform cells may resolve different compatible transitive
artifacts; each cell records its own exact inputs, never an invented common lock.
Each venv first bootstraps the pinned pip version before installing candidates.
Archive provenance accepts truthful legacy `hash` and modern `hashes` fields:
metadata and install-report URLs must match the supplied wheel, every provided
digest must match its bytes, contradictory digests fail, and at least one honest
SHA256 is mandatory. Missing metadata digests are not manufactured; the retained
install report can provide them. Empty `archive_info` is still an archive origin.

## Source, installed and baseline environments

Each candidate wheel is built from its fresh sdist; source/wheel runtime file
sets and hashes must be identical. Strict twine and original metadata/dependency
resolution apply. The source-built lane installs the exact checked-out source
**non-editably** into a clean venv through ordinary pip. The installed lane
installs the freshly built candidate wheels. Both import runtime only from their
venv, never the checkout. The source-built lane is not an editable-source test.

Separate extracted sdist support trees contain tests/tools/schemas/examples/docs,
including synthetic evidence, but no runtime packages. `python -I` invokes the
runner's pytest mode with an import-finder monitor installed before importing
Ledger/Guard/Compiler; outside-venv origins fail before module execution. Startup
and final checks are mandatory. Import paths and hashes, all installed runtime
file hashes, distribution versions/origins, and install reports are retained.
Candidate installed bytes must match the candidate wheel, regardless of lane.
Nested no-Guard installation tests receive the genuine built Ledger wheel via
their existing `WAVEFRAME_LEDGER_TEST_WHEEL` input, not the source-free support
tree. Their package installation and import assertions remain unchanged.
Guard's unchanged sdist omits its acceptance tools/JSON fixtures. Its support
tree is therefore supplemented from tracked test-only resources at the exact
verified Guard commit, with every path/hash recorded and overlap bytes checked.
These resources are not misrepresented as sdist contents or runtime modules.
For the full Guard baseline, repository-inspection tests also need Git history,
runtime source text and release metadata. The runner supplies their `ROOT` /
`REPO_ROOT` data inputs from the exact pinned, re-verified Guard checkout, and
records each binding. Structural dependency checks receive nonempty real source
roots rather than vacuously inspecting an empty support tree. Test bodies and
assertions are unchanged; runtime module roots are never rebound and the source
checkout is never added to the import path. All runtime imports still must come
from the baseline venv. Remaining tracked non-runtime repository data (including
contracts and CI metadata) is copied with hashes to the support tree for tests
that read cwd-relative inputs. This is source inspection, not source importing.

The third venv runs the full unmodified Guard suite with candidate Guard and the
historical Ledger dependency `a34c11d81b85963794cf28b4adad091fac15e130` plus the
exact Compiler pin. This is a separate baseline functional/provenance regression,
not certification of the candidate Ledger/Guard pair. No dependency-provenance
assertion is removed, re-pinned to a candidate, or silently deselected.

## Required lanes and skip contract

Seven lanes per cell: full Ledger default/development in both source-built and
wheel-installed environments; the named candidate-pair Guard manifest in both
environments with both development flags set; full Guard baseline with both
flags set. All listed function names must collect and have a passing case.
Collected parameter IDs and every outcome must agree; failures, collection
errors, missing results, xfails, missing functions and unexpected skips fail.
The 33-case matrix must collect and pass exactly 33 cases in each pair lane.
Full Ledger lanes additionally require all 70 release cases; development executes
all 44 development cases and default skips exactly those 44 documented opt-ins.

Platform-only exceptions are reported, never counted as passed: Windows skips
the native post-callback namespace replacement variants of the repository proof
test, whose fault-injection variants still run. The Linux-only v2 post-callback
function is supplemental in the baseline full suite rather than required on
Windows. The full baseline allows only the exact platform/privilege skip reasons
enumerated in the runner (Windows junction/namespace/case features, Linux mount
namespace capability, case-insensitive filesystem and the existing released-
installation-only native-cloud probe). Missing catalogs/dependencies or disabled
development flags are never accepted skips. Actual skipped IDs/reasons are kept.

The candidate-pair manifest deliberately does not claim to be the full Guard
historical release suite: its exact-dependency assertions run unmodified in the
separate correctly pinned full baseline. Every candidate-pair function selected
below is explicit; this is not a broad `-k not provenance` exclusion.

## Invocation and retained evidence

After review/commit, use a clean exact-head checkout of each PR and pinned tools:

```text
python -m pip install -r requirements-ci.txt
python tools/run_deny_only_containment_acceptance.py --expected-ledger FULL_LEDGER_SHA --guard-root ABSOLUTE_GUARD_CHECKOUT --output NEW_ABSOLUTE_OUTPUT_DIRECTORY
```

Workflow deny-only-containment.yml runs independently on Ubuntu/Windows x
Python 3.10/3.14. Each cell retains an incomplete/failed/passed
`containment-acceptance.json`, commands and exit codes, immutable build outputs,
hashes, install reports, constraints, import proofs, JUnit and skip reports.
Cell success has `matrix_complete=false` and claims only that cell. A separate
aggregate check requires four distinct exact-head passing reports with all seven
lanes; only then does its new matrix result set `matrix_complete=true`.

Artifacts include both candidate SHAs, OS and interpreter in their names. They
never overwrite historical release records. A green new check does not make the
old required check green or authorize merge/release/activation. Changing any
required-status routing remains a separate owner decision.

## Complete named required-test manifest

Full Ledger default/development and the full Guard baseline additionally execute
their entire collected suites. The following names are mandatory coverage, not
an assertion that unlisted full-suite cases are optional. Parameter IDs are
expanded and recorded by pytest in each lane. The three explicit action probes
run both development and released generations (20 role/path cases and two each
creation/replay cases). Retained artifacts preserve the original matrix producer
versions and hashes; these are not patched backports of old Guard versions.

### Mandatory Ledger

```text
tests/test_pack1_authoring_containment.py::test_new_domain_finalization_requires_path_allow
tests/test_pack1_authoring_containment.py::test_new_translation_approval_requires_path_allow
tests/test_pack1_authoring_containment.py::test_candidate_allow_requires_individual_confirmation_and_enforced_disposition
tests/test_pack1_authoring_containment.py::test_unenforceable_clause_cannot_supply_an_allow
tests/test_pack1_authoring_containment.py::test_historical_v2_and_v3_verify_without_reauthoring
tests/test_pack1_authoring_containment.py::test_historical_deny_approval_cannot_issue_new_v2_or_v3_authority
tests/test_pack1_authoring_containment.py::test_replacement_grants_require_new_bound_human_acceptance
tests/test_deny_only_containment_acceptance.py::test_rejects_wrong_import_origin
tests/test_deny_only_containment_acceptance.py::test_wrong_archive_digest_is_a_hard_failure
tests/test_deny_only_containment_acceptance.py::test_honest_legacy_archive_report_binds_empty_pep610_hashes
tests/test_deny_only_containment_acceptance.py::test_wrong_archive_url_or_digest_cannot_be_hidden_by_install_report
tests/test_deny_only_containment_acceptance.py::test_nested_clean_environment_tests_receive_actual_candidate_wheel
tests/test_deny_only_containment_acceptance.py::test_import_finder_fails_before_outside_runtime_is_executed
tests/test_deny_only_containment_acceptance.py::test_repository_inspection_inputs_never_rebind_runtime_modules
tests/test_deny_only_containment_acceptance.py::test_scope_rejects_unreviewed_runtime_or_protected_fixture
tests/test_deny_only_containment_acceptance.py::test_required_failure_or_skip_blocks_result
tests/test_deny_only_containment_acceptance.py::test_uncollected_and_unreported_required_cases_block_result
tests/test_deny_only_containment_acceptance.py::test_matrix_requires_all_33_real_cases
tests/test_deny_only_containment_acceptance.py::test_wrong_head_historical_or_incomplete_report_cannot_pass
tests/test_deny_only_containment_acceptance.py::test_pr_head_movement_is_a_hard_failure
tests/test_deny_only_containment_acceptance.py::test_named_manifest_is_fully_documented
tests/test_deny_only_containment_acceptance.py::test_matrix_aggregation_cannot_hide_a_missing_or_failed_cell
```

### Candidate-pair Guard

```text
tests/test_v2_affirmative_path_grant.py::test_33_evaluation_historical_producer_matrix
tests/test_v2_affirmative_path_grant.py::test_verified_deny_only_cannot_execute_in_any_loading_mode
tests/test_v2_affirmative_path_grant.py::test_historical_admission_is_preserved_and_replay_exposes_current_refusal
tests/test_v2_affirmative_path_grant.py::test_v1_keeps_legacy_default_and_v2_empty_rules_have_actionable_refusal
tests/test_v2_affirmative_path_grant.py::test_explicit_allow_deny_precedence_and_role_are_not_relaxed
tests/test_target_scope_enforcement.py::test_legacy_authority_leaves_target_as_evidence_only
tests/test_target_scope_enforcement.py::test_target_scope_matching
tests/test_target_scope_enforcement.py::test_deny_overrides_matching_allow
tests/test_target_scope_enforcement.py::test_invalid_target_blocks_when_scope_exists
tests/test_target_scope_enforcement.py::test_malformed_target_requirements_fail_closed
tests/test_target_scope_enforcement.py::test_matching_is_case_sensitive_and_literal
tests/test_target_scope_enforcement.py::test_tool_enforces_and_preserves_the_same_target_once
tests/test_target_scope_enforcement.py::test_public_compiler_target_scope_enforces_at_the_tool_boundary
tests/test_target_scope_enforcement.py::test_action_and_arguments_cannot_select_target_scope_verdict
tests/test_ledger_v2_authority_runtime.py::test_public_ledger_v07_repository_publication_executes_exact_contract_once
tests/test_ledger_v2_authority_runtime.py::test_v2_repeated_evaluation_is_deterministic_and_inputs_are_immutable
tests/test_ledger_v2_authority_runtime.py::test_fact_hash_changes_only_when_meaningful_typed_facts_change
tests/test_ledger_v2_authority_runtime.py::test_schema_optional_fact_may_be_omitted
tests/test_ledger_v2_authority_runtime.py::test_v2_repository_maintainer_role_constraint_blocks_other_published_role
tests/test_ledger_v2_authority_runtime.py::test_modified_v2_publication_chain_fails_before_mutation
tests/test_ledger_v2_authority_runtime.py::test_missing_v2_receipt_fails_before_mutation
tests/test_ledger_v2_authority_runtime.py::test_receipt_for_another_bundle_fails_before_mutation
tests/test_ledger_v2_authority_runtime.py::test_cross_version_artifacts_are_rejected
tests/test_ledger_v2_authority_runtime.py::test_missing_or_incorrect_runtime_facts_fail_before_callback
tests/test_ledger_v2_authority_runtime.py::test_repository_proposal_metadata_is_rejected_before_persistence
tests/test_ledger_v2_authority_runtime.py::test_caller_fact_injection_and_override_interfaces_fail_closed
tests/test_ledger_v2_authority_runtime.py::test_fact_injection_hidden_in_actor_metadata_fails_closed
tests/test_ledger_v2_authority_runtime.py::test_unsupported_runtime_fact_schema_fails_closed
tests/test_ledger_v2_authority_runtime.py::test_direct_v2_contract_injection_is_rejected_before_callback
tests/test_ledger_v2_authority_runtime.py::test_v2_loading_calls_released_public_ledger_validators
tests/test_ledger_v2_authority_runtime.py::test_warm_cache_and_evaluation_do_not_repeat_heavy_ledger_validation
tests/test_ledger_v2_authority_runtime.py::test_serialized_or_untrusted_cache_recovery_revalidates_complete_chain
tests/test_ledger_v2_authority_runtime.py::test_mutating_caller_copy_cannot_mutate_verified_cache
tests/test_ledger_v2_authority_runtime.py::test_unverified_v2_object_cannot_be_inserted_into_verified_memory_cache
tests/test_ledger_v2_authority_runtime.py::test_concurrent_cache_reads_never_observe_partial_replacement
tests/test_ledger_v2_authority_runtime.py::test_cache_refresh_revalidates_before_new_publication_activation
tests/test_ledger_v2_authority_runtime.py::test_callback_exception_records_failed_execution_and_unknown_mutation
tests/test_ledger_v2_authority_runtime.py::test_process_interruption_leaves_incomplete_unknown_attestation
tests/test_ledger_v2_authority_runtime.py::test_attestation_canonical_hash_and_tamper_rejection
tests/test_ledger_v2_authority_runtime.py::test_validation_failure_has_no_callback_or_success_attestation
tests/test_ledger_v2_authority_runtime.py::test_logical_publication_refs_are_portable_across_physical_layouts
tests/test_ledger_v2_authority_runtime.py::test_relative_workspace_root_resolves_logical_registry_once
tests/test_ledger_v2_authority_runtime.py::test_matching_physical_receipt_filename_cannot_bypass_logical_ref_mismatch
tests/test_ledger_v2_authority_runtime.py::test_logical_artifact_ref_traversal_and_ambiguous_normalization_fail_closed
tests/test_ledger_v2_authority_runtime.py::test_dependency_supports_ledger_v07_and_v08_without_guard_extra_or_ai_packages
tests/test_ledger_v2_authority_runtime.py::test_contract_hash_mismatch_after_caching_revalidates_and_is_rejected
tests/test_ledger_v2_authority_runtime.py::test_cross_authority_cache_substitution_is_rejected
tests/test_ledger_v2_authority_runtime.py::test_existing_v1_allowed_and_blocked_behavior_is_unchanged
tests/test_ledger_v2_authority_runtime.py::test_verified_routing_rejects_unknown_domain_versions_and_hashes
tests/test_ledger_v2_authority_runtime.py::test_verified_cache_cannot_override_workspace_or_downgrade_to_literal
tests/test_ledger_v3_authority_runtime.py::test_v3_multi_control_publication_loads_and_enforces_both_controls
tests/test_ledger_v3_authority_runtime.py::test_v3_partial_coverage_enforces_only_control_and_residual_is_not_executable
tests/test_ledger_v3_authority_runtime.py::test_v3_multi_control_repository_evaluation_on_all_supported_platforms
tests/test_ledger_v3_authority_runtime.py::test_v3_publication_does_not_require_private_translation_evidence
tests/test_ledger_v3_authority_runtime.py::test_v3_requires_receipt
tests/test_ledger_v3_authority_runtime.py::test_v3_rejects_cross_version_receipt
tests/test_ledger_v3_authority_runtime.py::test_v3_tampering_and_substitution_fail_before_activation
tests/test_ledger_v3_authority_runtime.py::test_v3_cross_publication_substitution_fails
tests/test_ledger_v3_authority_runtime.py::test_v3_tampered_registry_diagnostic_never_identifies_artifact_as_v2
tests/test_ledger_v3_authority_runtime.py::test_v3_runtime_fact_incompatibility_fails_closed
tests/test_ledger_v3_authority_runtime.py::test_v3_cache_is_verified_reused_and_drift_rejected
tests/test_ledger_v3_authority_runtime.py::test_v3_unverified_and_cross_authority_cache_substitution_are_rejected
tests/test_ledger_v3_authority_runtime.py::test_v3_delegates_to_version_dispatched_ledger_validators
tests/test_ledger_v3_authority_runtime.py::test_v3_incomplete_ledger_result_stops_before_receipt_or_runtime_projection
tests/test_ledger_v3_authority_runtime.py::test_v3_with_ledger_07_fails_as_clear_unsupported_version
tests/test_target_binding.py::test_binding_is_frozen_and_per_workspace_activation
tests/test_target_binding.py::test_request_cannot_supply_binding
tests/test_target_binding.py::test_context_cannot_supply_binding
tests/test_target_binding.py::test_boundary_cannot_be_reinterpreted
tests/test_target_binding.py::test_guard_configuration_cannot_silently_change_domain
tests/test_target_binding.py::test_v1_reuse_has_distinct_domain_proof_and_receipt_identity
tests/test_target_binding.py::test_binding_substitution_breaks_replay_integrity
tests/test_target_binding.py::test_replay_reproduces_recorded_logic_without_workspace
tests/test_target_binding.py::test_cloud_preservation_proof_has_binding_without_absolute_root
tests/test_repository_execution_evidence.py::test_mediated_action_proof_identifies_boundary_but_does_not_cover_bypass
tests/test_repository_execution_evidence.py::test_closed_request_rejects_before_every_side_effect
tests/test_repository_execution_evidence.py::test_repository_execution_states_persist_and_reload
tests/test_repository_execution_evidence.py::test_repository_attestation_tampering_fails_validation
tests/test_repository_execution_evidence.py::test_accepted_closed_workspace_refusal_has_no_fabricated_decision
tests/test_repository_execution_evidence.py::test_save_false_returns_proof_without_persistence
tests/test_repository_execution_evidence.py::test_released_v1_attestation_is_validated_without_reinterpretation
```

### Explicit action-v3 compatibility probes

```text
tests/test_action_policy_creation.py::test_action_roles_paths_and_evaluation_only
tests/test_action_policy_creation.py::test_creation_once_expiry_and_modify_separation
tests/test_action_policy_creation.py::test_replay_revalidates_retained_publication
```

### Full Guard baseline provenance case (both generations)

```text
tests/test_action_policy_creation.py::test_exact_dependencies_and_installed_public_api_acceptance
```
