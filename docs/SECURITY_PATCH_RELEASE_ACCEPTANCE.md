# Security patch distribution acceptance

Scope: unpublished governance-ledger 0.9.1 and waveframe-guard 0.19.1 only.
Owner approval: Stream issue 3, comments 6592311347 / 6592333882 (C1-C3).
This is separate distribution acceptance, never historical action-policy release
certification. Original runners, workflows, certificates and evidence stay
unchanged; their out-of-scope failures remain visible. No Cloud readiness claim.

## Binding and runtime freeze

Merged containment bases: Ledger ccb0961043ad26e64b7673e910ca271bd1b24794;
Guard fcd932b4f04430d6d2cbca3d13a979e455aff06e. Candidate versions are exact.
PR heads are inputs, not the merged bases. Preparation does not require fictional
PR numbers: implement first, open draft PRs, then supply real PR refs and exact
40-character heads. Start/end/aggregation rechecks invalidate all evidence if
either PR changes. Each report records this immutable pair manifest and bases.

Ledger runtime diff must be empty. Guard runtime file diff must equal exactly
waveframe_guard/__init__.py plus guard/sdk/guard.py, and each file must equal its
base bytes with exactly one declared 0.19.0 -> 0.19.1 reporting literal replaced.
No other runtime byte, file addition/removal, schema or historical fixture edit
is permitted. The exact set equality and byte comparisons are executable gates.

## Reused components (C2)

The unchanged containment Acceptance.build/environment/run helpers provide
build/source-wheel byte comparison, test-only support extraction, clean venvs,
pip reports, logs and transitive constraints. Its OriginFinder, verify_origin,
bind_repository_inputs, junit_outcomes, validate_cases and explicit skip rules
are reused unchanged. tools/package_provenance.py installed_archive verifies
actual archive origins, hashes and every installed wheel file. Its
compiler_provenance and tools/check_compiler_provenance.py are called unchanged
for exact-Git Compiler environments. tools/acceptance_pytest.py ImportBoundary
is used unchanged as an additional Ledger import boundary in every child.

Published Compiler wheels do not have Git PEP 610 provenance. That contract
does not fit compiler_provenance: the published lane uses installed_archive
with the independently pinned PyPI 0.5.0 wheel hash. No fabricated vcs_info,
rewritten direct_url.json, or assertion-disabling environment is accepted.
New logic is limited to release identity/runtime freeze, sdist rebuild comparison,
distribution-specific child accounting adapters, strict mandatory tests and
four-cell aggregation. It is not a third provenance scheme.

## Test objects and lanes

Each Ubuntu/Windows x Python 3.10/3.14 cell builds both candidate sdists and
wheels, runs strict twine checks and unchanged Guard archive inspection, then
rebuilds a second wheel from each sdist and compares every wheel payload member
(excluding RECORD itself). Source and wheel runtime maps must match. Builds,
archive hashes, payload maps, dependency install reports and failures are kept.

Original-wheel and sdist-wheel pair environments are fresh, noneditable installs.
Each runs full Ledger default/development and full Guard suites, plus a separate
mandatory Guard security lane so historical full-suite incompatibilities do not
hide security case outcomes. Compiler is the existing exact reviewed 0.5.0 Git
source, with truthful provenance checked by existing helpers. A third clean
pair uses the published Compiler 0.5.0 wheel and runs named Ledger and Guard
security suites. Other runtime dependencies resolve from PyPI and are recorded;
within-cell transitive versions are locked after the first environment.

Tests run under python -I from support trees containing tests/tools/resources,
never runtime packages. Guard's existing sdist omits some JSON/tools; unchanged
build support supplementation records every extra from the exact clean commit.
Repository inspection inputs alone can bind to the pinned source checkout;
runtime module origins must stay in the installed environment. The import
monitor fails even if a caller catches an origin exception. JUnit must agree
exactly with collection and observed execution identities/statuses.

Every mandatory Ledger authoring/v3 function below must collect and every
parameter must pass. Guard mandatory functions must collect and pass, with
only the three existing Windows platform parameter skips described below.
An unexpected skip, missing/uncollected case, duplicate identity, failure,
missing proof or contradictory JUnit result fails acceptance. Full suites
cannot substitute for the named manifest. Guard pair security lanes additionally
require exactly 33 historical matrix cases, 6 loading-mode cases, 20 action/role
cases, 2 creation-separation cases, and 2 publication replay cases.

Historical full-suite provenance assertions still demand earlier Ledger Git
commits. Such failures are retained as failures; honest candidate-wheel metadata
is never changed to satisfy them. The aggregate cannot pass with failed lanes.

## Approved skip contracts

Ledger default: exactly 44 tests/test_action_policy_v4.py development opt-in
skips; development mode: none. Mandatory authoring/v3 tests: no skips.
Guard security on Windows: exactly the existing Linux post-callback substitution
case and two post_callback_native execution-state parameters, using the unchanged
containment.skip_allowed node/reason matching; all 33 matrix cases must pass.
Full Guard additionally uses the unchanged baseline_skip_allowed platform
rules (Linux mount namespace/case-sensitivity/Windows-only features and Windows
symlink privileges/namespace limitations). Every actual node and reason is
retained in each proof. Any historical released-Ledger skip is visible and does
not substitute for mandatory security coverage. No new skip is authorized.

## Trigger and publication isolation (C3)

New workflow: workflow_dispatch or pull_request to main with explicitly scoped
release/security-* head branch and acceptance/version paths. Ordinary PRs do not
run the distribution jobs. contents: read only; no id-token, publishing secrets,
deployment environments, tag/release writer, or downstream hooks. Draft PRs
trigger the four independent cells without merging the workflow first.
Ledger governance.yml is only version-aware self-consistency: exactly one wheel
matching pyproject, exact installed version equality, Guard still absent.

## Commands and retained evidence

```text
python tools/run_security_patch_release_acceptance.py --ledger-head <40-SHA> --ledger-pr <PR> --guard-head <40-SHA> --guard-pr <PR> --guard-root <clean-Guard-checkout> --output <new-cell-directory>
python tools/run_security_patch_release_acceptance.py --ledger-head <same-SHA> --ledger-pr <same-PR> --guard-head <same-SHA> --guard-pr <same-PR> --aggregate <four-downloaded-artifact-directories> --output <new-matrix-report.json>
```

Output directories are never reused. Reports retain full commands, OS/interpreter,
pair manifest, named tests, collection/JUnit/proofs, archive and per-file hashes,
origins, resolver details, failures and skips. Actions artifacts include original
wheels/sdists and rebuilt wheels. Aggregation re-hashes retained archives and
requires all ten lanes in all four unique OS/Python cells at the same pair.
release_ready and runtime_activation_ready stay false: owner approval is separate.

## Reserved publication procedure

Only the exact artifact files accepted here may later be uploaded; do not rebuild
for publication. Select and record the accepted cell's four original archives.
After separate owner approval: Ledger 0.9.1 first; require published wheel AND
sdist SHA256 equality with the selected accepted files and clean index install
before Guard upload. Then Guard 0.19.1; require both published hashes equal and
clean-install the published pair plus Ledger [guard], pip check, provenance and
security regressions. Wrong bytes under immutable PyPI versions cannot be replaced.
Final tags bind exact accepted release commits (Ledger annotated, Guard lightweight).
No merge, tag, release, PyPI/TestPyPI upload or deployment is authorized here.
Ranges still admit affected packages: upgrade guidance explicitly selects both
patched versions. Historical approvals never silently acquire new grants.

## Complete mandatory function manifest (C1)

Parameter IDs and outcomes are retained per cell, not inferred from counts.

### Ledger authoring and v3 finalization

- `tests/test_pack1_authoring_containment.py::test_new_domain_finalization_requires_path_allow`
- `tests/test_pack1_authoring_containment.py::test_new_translation_approval_requires_path_allow`
- `tests/test_pack1_authoring_containment.py::test_candidate_allow_requires_individual_confirmation_and_enforced_disposition`
- `tests/test_pack1_authoring_containment.py::test_unenforceable_clause_cannot_supply_an_allow`
- `tests/test_pack1_authoring_containment.py::test_historical_v2_and_v3_verify_without_reauthoring`
- `tests/test_pack1_authoring_containment.py::test_historical_deny_approval_cannot_issue_new_v2_or_v3_authority`
- `tests/test_pack1_authoring_containment.py::test_replacement_grants_require_new_bound_human_acceptance`
- `tests/test_policy_translation_publication_v3.py::test_v3_publishes_two_individually_confirmed_controls_from_one_exact_clause`
- `tests/test_policy_translation_publication_v3.py::test_historical_v3_partial_evidence_survives_but_new_deny_only_approval_is_refused`
- `tests/test_policy_translation_publication_v3.py::test_v3_publishes_entirely_unsupported_and_informational_clauses_truthfully`
- `tests/test_policy_translation_publication_v3.py::test_missing_residual_acknowledgment_and_control_confirmation_fail_before_publication`
- `tests/test_policy_translation_publication_v3.py::test_duplicate_and_contradictory_controls_never_reach_v3_publication`
- `tests/test_policy_translation_publication_v3.py::test_v3_rejects_invalid_publication_chronology`
- `tests/test_policy_translation_publication_v3.py::test_v3_independent_validation_fails_closed_on_public_provenance_tampering`
- `tests/test_policy_translation_publication_v3.py::test_v3_rejects_post_approval_control_confirmation_even_if_outer_hash_is_restamped`
- `tests/test_policy_translation_publication_v3.py::test_private_provider_evidence_can_be_deleted_without_affecting_publication`
- `tests/test_policy_translation_publication_v3.py::test_one_byte_source_change_propagates_through_every_public_identity`
- `tests/test_policy_translation_publication_v3.py::test_v3_schemas_are_strict_and_dispatch_rejects_cross_version_masquerading`
- `tests/test_policy_translation_publication_v3.py::test_customer_coverage_and_explanations_exclude_implementation_vocabulary`
- `tests/test_policy_translation_publication_v3.py::test_v3_validation_and_customer_coverage_are_deterministic`
- `tests/test_policy_translation_publication_v3.py::test_guard_0190_loads_native_v3_after_private_evidence_deletion_and_enforces`
- `tests/test_policy_translation.py::test_bounded_binding_resolution_and_review_cannot_approve_role_only_authority`
- `tests/test_policy_translation.py::test_changed_human_confirmation_or_late_confirmation_invalidates_approval`
- `tests/test_policy_translation.py::test_cross_source_and_cross_authority_substitution_fail_closed`
- `tests/test_policy_translation.py::test_direct_clause_downgrade_fails_before_approval_even_with_another_enforced_clause`

### Guard containment, cache, replay and compatibility

- `tests/test_v2_affirmative_path_grant.py::test_33_evaluation_historical_producer_matrix`
- `tests/test_v2_affirmative_path_grant.py::test_verified_deny_only_cannot_execute_in_any_loading_mode`
- `tests/test_v2_affirmative_path_grant.py::test_historical_admission_is_preserved_and_replay_exposes_current_refusal`
- `tests/test_v2_affirmative_path_grant.py::test_v1_keeps_legacy_default_and_v2_empty_rules_have_actionable_refusal`
- `tests/test_v2_affirmative_path_grant.py::test_explicit_allow_deny_precedence_and_role_are_not_relaxed`
- `tests/test_target_scope_enforcement.py::test_legacy_authority_leaves_target_as_evidence_only`
- `tests/test_target_scope_enforcement.py::test_target_scope_matching`
- `tests/test_target_scope_enforcement.py::test_deny_overrides_matching_allow`
- `tests/test_target_scope_enforcement.py::test_invalid_target_blocks_when_scope_exists`
- `tests/test_target_scope_enforcement.py::test_malformed_target_requirements_fail_closed`
- `tests/test_target_scope_enforcement.py::test_matching_is_case_sensitive_and_literal`
- `tests/test_target_scope_enforcement.py::test_tool_enforces_and_preserves_the_same_target_once`
- `tests/test_target_scope_enforcement.py::test_public_compiler_target_scope_enforces_at_the_tool_boundary`
- `tests/test_target_scope_enforcement.py::test_action_and_arguments_cannot_select_target_scope_verdict`
- `tests/test_ledger_v2_authority_runtime.py::test_public_ledger_v07_repository_publication_executes_exact_contract_once`
- `tests/test_ledger_v2_authority_runtime.py::test_v2_repeated_evaluation_is_deterministic_and_inputs_are_immutable`
- `tests/test_ledger_v2_authority_runtime.py::test_fact_hash_changes_only_when_meaningful_typed_facts_change`
- `tests/test_ledger_v2_authority_runtime.py::test_schema_optional_fact_may_be_omitted`
- `tests/test_ledger_v2_authority_runtime.py::test_v2_repository_maintainer_role_constraint_blocks_other_published_role`
- `tests/test_ledger_v2_authority_runtime.py::test_modified_v2_publication_chain_fails_before_mutation`
- `tests/test_ledger_v2_authority_runtime.py::test_missing_v2_receipt_fails_before_mutation`
- `tests/test_ledger_v2_authority_runtime.py::test_receipt_for_another_bundle_fails_before_mutation`
- `tests/test_ledger_v2_authority_runtime.py::test_cross_version_artifacts_are_rejected`
- `tests/test_ledger_v2_authority_runtime.py::test_missing_or_incorrect_runtime_facts_fail_before_callback`
- `tests/test_ledger_v2_authority_runtime.py::test_repository_proposal_metadata_is_rejected_before_persistence`
- `tests/test_ledger_v2_authority_runtime.py::test_caller_fact_injection_and_override_interfaces_fail_closed`
- `tests/test_ledger_v2_authority_runtime.py::test_fact_injection_hidden_in_actor_metadata_fails_closed`
- `tests/test_ledger_v2_authority_runtime.py::test_unsupported_runtime_fact_schema_fails_closed`
- `tests/test_ledger_v2_authority_runtime.py::test_direct_v2_contract_injection_is_rejected_before_callback`
- `tests/test_ledger_v2_authority_runtime.py::test_v2_loading_calls_released_public_ledger_validators`
- `tests/test_ledger_v2_authority_runtime.py::test_warm_cache_and_evaluation_do_not_repeat_heavy_ledger_validation`
- `tests/test_ledger_v2_authority_runtime.py::test_serialized_or_untrusted_cache_recovery_revalidates_complete_chain`
- `tests/test_ledger_v2_authority_runtime.py::test_mutating_caller_copy_cannot_mutate_verified_cache`
- `tests/test_ledger_v2_authority_runtime.py::test_unverified_v2_object_cannot_be_inserted_into_verified_memory_cache`
- `tests/test_ledger_v2_authority_runtime.py::test_concurrent_cache_reads_never_observe_partial_replacement`
- `tests/test_ledger_v2_authority_runtime.py::test_cache_refresh_revalidates_before_new_publication_activation`
- `tests/test_ledger_v2_authority_runtime.py::test_callback_exception_records_failed_execution_and_unknown_mutation`
- `tests/test_ledger_v2_authority_runtime.py::test_process_interruption_leaves_incomplete_unknown_attestation`
- `tests/test_ledger_v2_authority_runtime.py::test_attestation_canonical_hash_and_tamper_rejection`
- `tests/test_ledger_v2_authority_runtime.py::test_validation_failure_has_no_callback_or_success_attestation`
- `tests/test_ledger_v2_authority_runtime.py::test_logical_publication_refs_are_portable_across_physical_layouts`
- `tests/test_ledger_v2_authority_runtime.py::test_relative_workspace_root_resolves_logical_registry_once`
- `tests/test_ledger_v2_authority_runtime.py::test_matching_physical_receipt_filename_cannot_bypass_logical_ref_mismatch`
- `tests/test_ledger_v2_authority_runtime.py::test_logical_artifact_ref_traversal_and_ambiguous_normalization_fail_closed`
- `tests/test_ledger_v2_authority_runtime.py::test_dependency_supports_ledger_v07_and_v08_without_guard_extra_or_ai_packages`
- `tests/test_ledger_v2_authority_runtime.py::test_contract_hash_mismatch_after_caching_revalidates_and_is_rejected`
- `tests/test_ledger_v2_authority_runtime.py::test_cross_authority_cache_substitution_is_rejected`
- `tests/test_ledger_v2_authority_runtime.py::test_existing_v1_allowed_and_blocked_behavior_is_unchanged`
- `tests/test_ledger_v2_authority_runtime.py::test_verified_routing_rejects_unknown_domain_versions_and_hashes`
- `tests/test_ledger_v2_authority_runtime.py::test_verified_cache_cannot_override_workspace_or_downgrade_to_literal`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_multi_control_publication_loads_and_enforces_both_controls`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_partial_coverage_enforces_only_control_and_residual_is_not_executable`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_multi_control_repository_evaluation_on_all_supported_platforms`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_publication_does_not_require_private_translation_evidence`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_requires_receipt`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_rejects_cross_version_receipt`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_tampering_and_substitution_fail_before_activation`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_cross_publication_substitution_fails`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_tampered_registry_diagnostic_never_identifies_artifact_as_v2`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_runtime_fact_incompatibility_fails_closed`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_cache_is_verified_reused_and_drift_rejected`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_unverified_and_cross_authority_cache_substitution_are_rejected`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_delegates_to_version_dispatched_ledger_validators`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_incomplete_ledger_result_stops_before_receipt_or_runtime_projection`
- `tests/test_ledger_v3_authority_runtime.py::test_v3_with_ledger_07_fails_as_clear_unsupported_version`
- `tests/test_target_binding.py::test_binding_is_frozen_and_per_workspace_activation`
- `tests/test_target_binding.py::test_request_cannot_supply_binding`
- `tests/test_target_binding.py::test_context_cannot_supply_binding`
- `tests/test_target_binding.py::test_boundary_cannot_be_reinterpreted`
- `tests/test_target_binding.py::test_guard_configuration_cannot_silently_change_domain`
- `tests/test_target_binding.py::test_v1_reuse_has_distinct_domain_proof_and_receipt_identity`
- `tests/test_target_binding.py::test_binding_substitution_breaks_replay_integrity`
- `tests/test_target_binding.py::test_replay_reproduces_recorded_logic_without_workspace`
- `tests/test_target_binding.py::test_cloud_preservation_proof_has_binding_without_absolute_root`
- `tests/test_repository_execution_evidence.py::test_mediated_action_proof_identifies_boundary_but_does_not_cover_bypass`
- `tests/test_repository_execution_evidence.py::test_closed_request_rejects_before_every_side_effect`
- `tests/test_repository_execution_evidence.py::test_repository_execution_states_persist_and_reload`
- `tests/test_repository_execution_evidence.py::test_repository_attestation_tampering_fails_validation`
- `tests/test_repository_execution_evidence.py::test_accepted_closed_workspace_refusal_has_no_fabricated_decision`
- `tests/test_repository_execution_evidence.py::test_save_false_returns_proof_without_persistence`
- `tests/test_repository_execution_evidence.py::test_released_v1_attestation_is_validated_without_reinterpretation`
- `tests/test_action_policy_creation.py::test_action_roles_paths_and_evaluation_only`
- `tests/test_action_policy_creation.py::test_creation_once_expiry_and_modify_separation`
- `tests/test_action_policy_creation.py::test_replay_revalidates_retained_publication`
