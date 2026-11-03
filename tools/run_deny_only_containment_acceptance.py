"""Independent containment acceptance; never issues historical release certification."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.abc
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import venv
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LEDGER_BASE = "bd82c11dc0c4d4003063c7f2ce0f2e87f12f7bf1"
LEDGER_SECURITY_HEAD = "058d561d4a9ef7a2cfd039a9a6f44bb8793e90b6"
GUARD_BASE = "599c132038f66b5f15b47752505f0ed1aae1d641"
GUARD_HEAD = "e77c7fb718009b947daba621155baa43315fa045"
COMPILER_HEAD = "ae590dee058d3481e384dea850d5b7d980f533ff"
BASELINE_LEDGER = "a34c11d81b85963794cf28b4adad091fac15e130"
NEW_FILES = {
    ".github/workflows/deny-only-containment.yml",
    "tools/run_deny_only_containment_acceptance.py",
    "tests/test_deny_only_containment_acceptance.py",
    "docs/DENY_ONLY_CONTAINMENT_ACCEPTANCE.md",
}
LEDGER_RUNTIME = {"governance_ledger/" + name + ".py" for name in (
    "domain_policy", "policy_translation", "policy_translation_publication")}
GUARD_RUNTIME = {"guard/cognition/admissibility.py"}
PACKAGES = {"governance_ledger": "governance-ledger", "guard": "waveframe-guard",
            "waveframe_guard": "waveframe-guard", "compiler": "cricore-contract-compiler"}
LANES = ["ledger-default-source", "ledger-development-source", "guard-pair-source",
         "ledger-default-installed", "ledger-development-installed", "guard-pair-installed", "guard-baseline"]
# Complete function-level manifest, expanded to exact parameter IDs during collection.
LEDGER_REQUIRED = {
    "tests/test_pack1_authoring_containment.py": [
        "test_new_domain_finalization_requires_path_allow",
        "test_new_translation_approval_requires_path_allow",
        "test_candidate_allow_requires_individual_confirmation_and_enforced_disposition",
        "test_unenforceable_clause_cannot_supply_an_allow",
        "test_historical_v2_and_v3_verify_without_reauthoring",
        "test_historical_deny_approval_cannot_issue_new_v2_or_v3_authority",
        "test_replacement_grants_require_new_bound_human_acceptance"
    ],
    "tests/test_deny_only_containment_acceptance.py": [
        "test_rejects_wrong_import_origin",
        "test_wrong_archive_digest_is_a_hard_failure",
        "test_honest_legacy_archive_report_binds_empty_pep610_hashes",
        "test_wrong_archive_url_or_digest_cannot_be_hidden_by_install_report",
        "test_nested_clean_environment_tests_receive_actual_candidate_wheel",
        "test_import_finder_fails_before_outside_runtime_is_executed",
        "test_repository_inspection_inputs_never_rebind_runtime_modules",
        "test_scope_rejects_unreviewed_runtime_or_protected_fixture",
        "test_required_failure_or_skip_blocks_result",
        "test_uncollected_and_unreported_required_cases_block_result",
        "test_junit_cannot_omit_or_contradict_runtime_proof",
        "test_matrix_requires_all_33_real_cases",
        "test_wrong_head_historical_or_incomplete_report_cannot_pass",
        "test_pr_head_movement_is_a_hard_failure",
        "test_named_manifest_is_fully_documented",
        "test_matrix_aggregation_cannot_hide_a_missing_or_failed_cell"
    ]
}
GUARD_REQUIRED = {
    "tests/test_v2_affirmative_path_grant.py": [
        "test_33_evaluation_historical_producer_matrix",
        "test_verified_deny_only_cannot_execute_in_any_loading_mode",
        "test_historical_admission_is_preserved_and_replay_exposes_current_refusal",
        "test_v1_keeps_legacy_default_and_v2_empty_rules_have_actionable_refusal",
        "test_explicit_allow_deny_precedence_and_role_are_not_relaxed"
    ],
    "tests/test_target_scope_enforcement.py": [
        "test_legacy_authority_leaves_target_as_evidence_only",
        "test_target_scope_matching",
        "test_deny_overrides_matching_allow",
        "test_invalid_target_blocks_when_scope_exists",
        "test_malformed_target_requirements_fail_closed",
        "test_matching_is_case_sensitive_and_literal",
        "test_tool_enforces_and_preserves_the_same_target_once",
        "test_public_compiler_target_scope_enforces_at_the_tool_boundary",
        "test_action_and_arguments_cannot_select_target_scope_verdict"
    ],
    "tests/test_ledger_v2_authority_runtime.py": [
        "test_public_ledger_v07_repository_publication_executes_exact_contract_once",
        "test_v2_repeated_evaluation_is_deterministic_and_inputs_are_immutable",
        "test_fact_hash_changes_only_when_meaningful_typed_facts_change",
        "test_schema_optional_fact_may_be_omitted",
        "test_v2_repository_maintainer_role_constraint_blocks_other_published_role",
        "test_modified_v2_publication_chain_fails_before_mutation",
        "test_missing_v2_receipt_fails_before_mutation",
        "test_receipt_for_another_bundle_fails_before_mutation",
        "test_cross_version_artifacts_are_rejected",
        "test_missing_or_incorrect_runtime_facts_fail_before_callback",
        "test_repository_proposal_metadata_is_rejected_before_persistence",
        "test_caller_fact_injection_and_override_interfaces_fail_closed",
        "test_fact_injection_hidden_in_actor_metadata_fails_closed",
        "test_unsupported_runtime_fact_schema_fails_closed",
        "test_direct_v2_contract_injection_is_rejected_before_callback",
        "test_v2_loading_calls_released_public_ledger_validators",
        "test_warm_cache_and_evaluation_do_not_repeat_heavy_ledger_validation",
        "test_serialized_or_untrusted_cache_recovery_revalidates_complete_chain",
        "test_mutating_caller_copy_cannot_mutate_verified_cache",
        "test_unverified_v2_object_cannot_be_inserted_into_verified_memory_cache",
        "test_concurrent_cache_reads_never_observe_partial_replacement",
        "test_cache_refresh_revalidates_before_new_publication_activation",
        "test_callback_exception_records_failed_execution_and_unknown_mutation",
        "test_process_interruption_leaves_incomplete_unknown_attestation",
        "test_attestation_canonical_hash_and_tamper_rejection",
        "test_validation_failure_has_no_callback_or_success_attestation",
        "test_logical_publication_refs_are_portable_across_physical_layouts",
        "test_relative_workspace_root_resolves_logical_registry_once",
        "test_matching_physical_receipt_filename_cannot_bypass_logical_ref_mismatch",
        "test_logical_artifact_ref_traversal_and_ambiguous_normalization_fail_closed",
        "test_dependency_supports_ledger_v07_and_v08_without_guard_extra_or_ai_packages",
        "test_contract_hash_mismatch_after_caching_revalidates_and_is_rejected",
        "test_cross_authority_cache_substitution_is_rejected",
        "test_existing_v1_allowed_and_blocked_behavior_is_unchanged",
        "test_verified_routing_rejects_unknown_domain_versions_and_hashes",
        "test_verified_cache_cannot_override_workspace_or_downgrade_to_literal"
    ],
    "tests/test_ledger_v3_authority_runtime.py": [
        "test_v3_multi_control_publication_loads_and_enforces_both_controls",
        "test_v3_partial_coverage_enforces_only_control_and_residual_is_not_executable",
        "test_v3_multi_control_repository_evaluation_on_all_supported_platforms",
        "test_v3_publication_does_not_require_private_translation_evidence",
        "test_v3_requires_receipt",
        "test_v3_rejects_cross_version_receipt",
        "test_v3_tampering_and_substitution_fail_before_activation",
        "test_v3_cross_publication_substitution_fails",
        "test_v3_tampered_registry_diagnostic_never_identifies_artifact_as_v2",
        "test_v3_runtime_fact_incompatibility_fails_closed",
        "test_v3_cache_is_verified_reused_and_drift_rejected",
        "test_v3_unverified_and_cross_authority_cache_substitution_are_rejected",
        "test_v3_delegates_to_version_dispatched_ledger_validators",
        "test_v3_incomplete_ledger_result_stops_before_receipt_or_runtime_projection",
        "test_v3_with_ledger_07_fails_as_clear_unsupported_version"
    ],
    "tests/test_target_binding.py": [
        "test_binding_is_frozen_and_per_workspace_activation",
        "test_request_cannot_supply_binding",
        "test_context_cannot_supply_binding",
        "test_boundary_cannot_be_reinterpreted",
        "test_guard_configuration_cannot_silently_change_domain",
        "test_v1_reuse_has_distinct_domain_proof_and_receipt_identity",
        "test_binding_substitution_breaks_replay_integrity",
        "test_replay_reproduces_recorded_logic_without_workspace",
        "test_cloud_preservation_proof_has_binding_without_absolute_root"
    ],
    "tests/test_repository_execution_evidence.py": [
        "test_mediated_action_proof_identifies_boundary_but_does_not_cover_bypass",
        "test_closed_request_rejects_before_every_side_effect",
        "test_repository_execution_states_persist_and_reload",
        "test_repository_attestation_tampering_fails_validation",
        "test_accepted_closed_workspace_refusal_has_no_fabricated_decision",
        "test_save_false_returns_proof_without_persistence",
        "test_released_v1_attestation_is_validated_without_reinterpretation"
    ]
}
ACTION_REQUIRED = [
    "tests/test_action_policy_creation.py::test_action_roles_paths_and_evaluation_only",
    "tests/test_action_policy_creation.py::test_creation_once_expiry_and_modify_separation",
    "tests/test_action_policy_creation.py::test_replay_revalidates_retained_publication",
]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_digest(path, expected):
    require(digest(path) == expected, "archive/module digest mismatch: " + str(path))


def verify_archive_origins(origins, wheel, expected):
    """Use truthful metadata/report origins, accepting hash or hashes encodings."""
    verify_digest(wheel, expected)
    sha256_seen = False
    for origin in origins:
        require(origin.get("url") == Path(wheel).resolve().as_uri() and "archive_info" in origin
                and "vcs_info" not in origin, "wrong archive origin")
        info = origin["archive_info"]
        hashes = dict(info.get("hashes", {}))
        if "hash" in info:
            algorithm, value = info["hash"].split("=", 1)
            require(algorithm not in hashes or hashes[algorithm] == value, "contradictory archive digests")
            hashes[algorithm] = value
        for algorithm, value in hashes.items():
            require(hashlib.new(algorithm, Path(wheel).read_bytes()).hexdigest() == value, "archive origin digest mismatch")
        if "sha256" in hashes:
            require(hashes["sha256"] == expected, "wrong archive sha256")
            sha256_seen = True
    require(sha256_seen, "archive has no honest sha256 provenance")


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding="utf-8")


def named_nodes(manifest):
    return [file + "::" + name for file, names in manifest.items() for name in names]


def validate_scope(actual, allowed):
    require(set(actual) <= set(allowed), "unauthorized scope drift: " + repr(sorted(set(actual) - set(allowed))))


def verify_origin(name, path, prefix):
    require(Path(path).resolve().is_relative_to(Path(prefix).resolve()),
            "import-origin violation: " + name + " -> " + str(path))


def bind_repository_inputs(modules, support, source):
    """Supply real pinned source-inspection data, never runtime import paths."""
    bindings = []
    for name, module in modules:
        if not (name.split(".")[-1].startswith("test_") or name.startswith("tools.")):
            continue
        path = getattr(module, "__file__", None)
        if not path or not Path(path).resolve().is_relative_to(support):
            continue
        for key in ("ROOT", "REPO_ROOT"):
            if getattr(module, key, None) == support:
                setattr(module, key, source)
                bindings.append({"module": name, "input": key, "source": str(source)})
        if name.split(".")[-1] == "test_dependency_boundaries":
            roots = [source / "guard", source / "waveframe_guard"]
            require(all(path.is_dir() for path in roots), "source-inspection runtime roots missing")
            module.GUARD_ROOTS = roots
    return bindings


def validate_result(result, expected_ledger, expected_guard):
    require(result.get("scope") == "legacy-v2-deny-only-containment", "wrong acceptance scope")
    require(result.get("ledger_head") == expected_ledger and result.get("guard_head") == expected_guard,
            "wrong acceptance heads")
    require(result.get("status") == "passed" and set(result.get("required_lanes", [])) == set(LANES)
            and set(result["required_lanes"]) == set(result.get("passed_lanes", [])), "incomplete acceptance")
    require(result.get("release_ready") is False and result.get("runtime_activation_ready") is False
            and result.get("historical_certification") == "not claimed", "false promotion claim")


def skip_allowed(node, reason, lane, system):
    if lane.startswith("ledger-default"):
        return (node.startswith("tests/test_action_policy_v4.py::")
                and "explicit action-policy development opt-in required" in reason)
    if system == "Windows":
        return (("::test_linux_substitution_after_callback_is_failed_unknown_not_success" in node
                 and reason == "Linux post-callback substitution evidence")
                or ("::test_repository_execution_states_persist_and_reload[" in node
                    and "post_callback_native" in node
                    and reason == "Windows namespace locks prevent this replacement; fault injection runs on both OSes"))
    return False


def baseline_skip_allowed(node, reason, system):
    # Supplemental baseline full suite: exact platform limitations, never missing dependencies.
    shared = {"requires the released Ledger installation; covered by released CI"}
    windows = {"Linux post-callback substitution evidence", "Linux mount namespace",
               "Linux detected namespace substitution", "Linux post-callback namespace check",
               "Windows namespace locks prevent this replacement; fault injection runs on both OSes",
               "Windows case-sensitive directory feature/privilege unavailable",
               "symlink privilege unavailable; Windows junction tested separately", "file symlink privilege unavailable"}
    linux = {"case-insensitive filesystem required", "Windows junction/reparse test", "Windows namespace locks",
             "NTFS case-sensitive directory feature", "mount namespace tools unavailable",
             "unprivileged mount namespaces unavailable"}
    return node.startswith("tests/") and reason in (shared | (windows if system == "Windows" else linux))


def validate_cases(collected, outcomes, required, lane, system):
    require(collected and set(collected) == set(outcomes), "missing collected test results")
    for node in required:
        matches = [item for item in collected if item == node or item.startswith(node + "[")]
        require(matches, "missing required case: " + node)
        require(any(outcomes[item]["status"] == "passed" for item in matches), "required case did not execute: " + node)
    skips = []
    for node, outcome in outcomes.items():
        status, reason = outcome["status"], outcome.get("reason", "")
        if status == "skipped":
            allowed = (baseline_skip_allowed(node, reason, system) if lane == "guard-baseline"
                       else skip_allowed(node, reason, lane, system))
            require(allowed, "unexpected skip: " + node + ": " + reason)
            skips.append({"node": node, "reason": reason})
        else:
            require(status == "passed", "required test failure: " + node)
    matrix = [node for node in collected if "::test_33_evaluation_historical_producer_matrix[" in node]
    if lane.startswith("guard-pair"):
        require(len(matrix) == 33 and all(outcomes[node]["status"] == "passed" for node in matrix),
                "33-evaluation matrix incomplete")
        for function, expected in [("test_verified_deny_only_cannot_execute_in_any_loading_mode", 6),
                                   ("test_action_roles_paths_and_evaluation_only", 20),
                                   ("test_creation_once_expiry_and_modify_separation", 2),
                                   ("test_replay_revalidates_retained_publication", 2)]:
            cases = [value for node, value in outcomes.items() if "::" + function + "[" in node]
            require(len(cases) == expected and all(value["status"] == "passed" for value in cases),
                    "required parameter coverage incomplete: " + function)
    if lane.startswith("ledger-default"):
        require(len(skips) == 44, "default catalog skip contract changed")
    if lane.startswith("ledger-"):
        release = [value for node, value in outcomes.items() if node.startswith("tests/test_release_catalog_v4.py::")]
        development = [value for node, value in outcomes.items() if node.startswith("tests/test_action_policy_v4.py::")]
        require(len(release) == 70 and all(item["status"] == "passed" for item in release), "release catalog coverage missing")
        require(len(development) == 44 and all(item["status"] == ("skipped" if lane.startswith("ledger-default") else "passed")
                                            for item in development), "development catalog coverage missing")
    return {"collected": len(collected), "passed": len(collected) - len(skips), "skips": skips}


def junit_outcomes(path, collected, observed):
    """Require JUnit and collection/runtime proof to describe identical cases."""
    keys = {}
    for node in collected:
        file, *parts = node.split("::")
        key = (file.removesuffix(".py").replace("/", ".") + "".join("." + item for item in parts[:-1]), parts[-1])
        require(key not in keys, "ambiguous JUnit identity")
        keys[key] = node
    result = {}
    for case in ET.parse(path).iter("testcase"):
        key = (case.get("classname"), case.get("name"))
        require(key in keys and keys[key] not in result, "unexpected/duplicate JUnit case: " + repr(key))
        node = keys[key]
        skipped = case.find("skipped")
        status = "failed" if case.find("failure") is not None or case.find("error") is not None else ("skipped" if skipped is not None else "passed")
        require(node in observed and observed[node]["status"] == status, "JUnit/runtime outcome mismatch: " + node)
        result[node] = {"status": status}
        if skipped is not None:
            result[node]["reason"] = skipped.get("message", "").removeprefix("Skipped: ")
    require(set(result) == set(collected), "JUnit cases missing")
    return result


class OriginFinder(importlib.abc.MetaPathFinder):
    def __init__(self, prefix, observed):
        self.prefix, self.observed = prefix, observed
        self.violations = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] not in PACKAGES:
            return None
        for finder in list(sys.meta_path):
            if finder is self:
                continue
            method = getattr(finder, "find_spec", None)
            spec = method(fullname, path, target) if method else None
            if spec is not None:
                if spec.origin and spec.origin not in {"built-in", "frozen"}:
                    try:
                        verify_origin(fullname, spec.origin, self.prefix)
                    except RuntimeError as exc:
                        self.violations.append(str(exc))
                        raise
                    self.observed[fullname] = {"path": spec.origin, "sha256": digest(spec.origin)}
                return spec
        return None


def pytest_child(config_path):
    """Executed under -I from a support tree containing no runtime source."""
    import pytest
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    observed, outcomes, collected, repository_inputs = {}, {}, [], []
    finder = OriginFinder(sys.prefix, observed)
    sys.meta_path.insert(0, finder)
    for package in PACKAGES:
        module = importlib.import_module(package)
        verify_origin(package, module.__file__, sys.prefix)
    provenance = {}
    for package in set(PACKAGES.values()):
        dist = metadata.distribution(package)
        files = {}
        for file in dist.files or []:
            if str(file).replace("\\", "/").split("/")[0] in PACKAGES and Path(file).suffix in {".py", ".json"}:
                path = dist.locate_file(file)
                verify_origin(str(file), path, sys.prefix)
                files[str(file).replace("\\", "/")] = {"path": str(path), "sha256": digest(path)}
        provenance[package] = {"version": dist.version, "direct_url": dist.read_text("direct_url.json"), "modules": files}
    sys.path.insert(0, str(Path.cwd()))  # test/tools support only, no runtime modules

    class Proof:
        def pytest_collection_finish(self, session):
            if config.get("repository_source"):
                source = Path(config["repository_source"]).resolve()
                actual = subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
                require(actual == GUARD_HEAD, "wrong repository-inspection source head")
                repository_inputs.extend(bind_repository_inputs(list(sys.modules.items()), Path.cwd().resolve(), source))
            collected.extend(item.nodeid for item in session.items)

        def pytest_runtest_logreport(self, report):
            if report.failed:
                outcomes[report.nodeid] = {"status": "failed", "reason": str(report.longrepr)}
            elif report.skipped:
                reason = str(report.longrepr[2]) if isinstance(report.longrepr, tuple) else str(report.longrepr)
                outcomes[report.nodeid] = {"status": "skipped", "reason": reason.removeprefix("Skipped: ")}
            elif report.when == "call" and report.nodeid not in outcomes:
                outcomes[report.nodeid] = {"status": "passed"}

        def pytest_sessionfinish(self, session, exitstatus):
            error = None
            try:
                for name, module in list(sys.modules.items()):
                    path = getattr(module, "__file__", None)
                    if name.split(".")[0] in PACKAGES and path:
                        verify_origin(name, path, sys.prefix)
                require(finder in sys.meta_path, "import-origin monitor removed")
                require(not finder.violations, "import-origin violations were caught by caller: " + repr(finder.violations))
            except Exception as exc:
                error = str(exc)
                session.exitstatus = 1
            write(config["proof"], {"collected": collected, "outcomes": outcomes,
                  "imports": observed, "packages": provenance, "origin_error": error})
            payload = json.loads(Path(config["proof"]).read_text(encoding="utf-8"))
            payload["repository_inspection_inputs"] = repository_inputs
            write(config["proof"], payload)

    return pytest.main(["-q", "-ra", "--junitxml", config["junit"], *config["nodes"]], plugins=[Proof()])


class Acceptance:
    def __init__(self, output):
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.env = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "LEDGER_ARCHIVE_EXPECTATIONS",
                     "WAVEFRAME_LEDGER_ACTION_POLICY_DEV", "WAVEFRAME_GUARD_ACTION_POLICY_DEV",
                     "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
            self.env.pop(name, None)
        self.env.update(PYTHONUTF8="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                        PIP_CONSTRAINT=str(ROOT / "requirements-ci.txt"))
        self.report = {"scope": "legacy-v2-deny-only-containment", "status": "incomplete",
                       "release_ready": False, "runtime_activation_ready": False,
                       "historical_certification": "not claimed", "historical_failed_run":
                       "https://github.com/Waveframe-Labs/Waveframe-Ledger/actions/runs/41397540156",
                       "system": platform.system(), "python": sys.version, "commands": [],
                       "ci_run": os.environ.get("GITHUB_RUN_ID"), "ci_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                       "report_kind": "cell", "matrix_complete": False,
                       "required_lanes": [], "passed_lanes": [], "suites": {}, "builds": {}}
        self.lock = None
        self.save()

    def save(self):
        write(self.output / "containment-acceptance.json", self.report)

    def run(self, label, *command, cwd=ROOT, env=None):
        command = [str(item) for item in command]
        print(label + ": " + " ".join(command), flush=True)
        result = subprocess.run(command, cwd=cwd, env=env or self.env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
        log = str(len(self.report["commands"])) + "-" + label + ".log"
        (self.output / log).write_text(result.stdout, encoding="utf-8")
        self.report["commands"].append({"label": label, "command": command, "cwd": str(cwd), "exit": result.returncode, "log": log})
        self.save()
        require(result.returncode == 0, label + " failed: " + result.stdout[-3000:])
        return result.stdout.strip()

    def git(self, root, label, *args):
        return self.run(label, "git", "-C", root, *args)

    def heads(self, guard_root, ledger_head):
        for root, name, expected, pr in [(ROOT, "ledger", ledger_head, 27), (guard_root, "guard", GUARD_HEAD, 69)]:
            require(re.fullmatch(r"[0-9a-f]{40}", expected), "full head SHA required")
            require(self.git(root, name + "-head", "rev-parse", "HEAD") == expected, "wrong " + name + " head")
            remote = self.git(root, name + "-pr-head", "ls-remote", "origin", "refs/pull/" + str(pr) + "/head")
            require(remote.split()[0] == expected, name + " PR moved; re-pin and revalidate")
            self.git(root, name + "-clean", "diff", "--exit-code", "HEAD")
            require(not self.git(root, name + "-untracked", "status", "--porcelain", "--untracked-files=all"), "checkout not clean")

    def scopes(self, guard_root):
        for root, base, prefix, allowed, name in [(ROOT, LEDGER_BASE, "governance_ledger", LEDGER_RUNTIME, "ledger"),
                (guard_root, GUARD_BASE, "guard", GUARD_RUNTIME, "guard")]:
            self.git(root, name + "-base", "merge-base", "--is-ancestor", base, "HEAD")
            changes = self.git(root, name + "-runtime-scope", "diff", "--name-only", base, "HEAD", "--", prefix).splitlines()
            validate_scope(changes, allowed)
            self.report[name + "_runtime_diff"] = changes
        self.git(guard_root, "guard-other-runtime", "diff", "--exit-code", GUARD_BASE, "HEAD", "--", "waveframe_guard")
        self.git(ROOT, "reviewed-security-bytes", "diff", "--exit-code", LEDGER_SECURITY_HEAD, "HEAD", "--", "governance_ledger")
        validate_scope(self.git(ROOT, "pipeline-scope", "diff", "--name-only", LEDGER_SECURITY_HEAD, "HEAD").splitlines(), NEW_FILES)
        self.git(ROOT, "protected-release", "diff", "--exit-code", "3cc34e7b3cb6efca5102e0e22d559ec0c0fd583f", "HEAD",
                 "--", "tests/fixtures", "schemas", "examples/native_v4_release.py")
        self.git(ROOT, "protected-history", "diff", "--exit-code", LEDGER_BASE, "HEAD", "--", "tools/run_action_policy_acceptance.py",
                 "tools/run_guard_extra_acceptance.py", "tools/fetch_guard_candidate.py", ".github/workflows/action-policy-development.yml",
                 "docs/acceptance", "docs/LEDGER_090_ACCEPTANCE.md", "requirements-action-policy-dev.txt")
        self.save()

    def build(self, root, name, packages):
        dist = self.output / (name + "-dist")
        self.run(name + "-build", sys.executable, "-m", "build", "--outdir", dist, root)
        artifacts = list(dist.iterdir())
        wheel, = [path for path in artifacts if path.suffix == ".whl"]
        sdist, = [path for path in artifacts if path.name.endswith(".tar.gz")]
        self.run(name + "-twine", sys.executable, "-m", "twine", "check", "--strict", *artifacts)
        source = {str(p.relative_to(root)).replace("\\", "/"): digest(p)
                  for package in packages for p in (root / package).rglob("*")
                  if p.is_file() and p.suffix in {".py", ".json"}}
        with zipfile.ZipFile(wheel) as archive:
            modules = {n: hashlib.sha256(archive.read(n)).hexdigest() for n in archive.namelist()
                       if n.split("/")[0] in packages and Path(n).suffix in {".py", ".json"}}
        require(modules == source, name + " source/wheel module bytes differ")
        support = self.output / (name + "-support")
        support.mkdir()
        with tarfile.open(sdist) as archive:
            for member in archive.getmembers():
                rel = Path(*Path(member.name).parts[1:])
                require(not rel.is_absolute() and ".." not in rel.parts, "unsafe sdist path")
                if member.isfile() and rel.parts and (rel.parts[0] in {"tests", "tools", "schemas", "examples", "docs"} or len(rel.parts) == 1):
                    target = support / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
        resources = {}
        # Guard's existing sdist omits tools and JSON fixtures. Keep its packaging
        # unchanged; supplement test-only support from this exact verified tree.
        if name == "guard":
            paths = self.git(root, name + "-test-resources", "ls-files").splitlines()
            for rel in paths:
                if Path(rel).parts[0] in PACKAGES:
                    continue
                source_file, target = root / rel, support / rel
                require(source_file.is_file() and not source_file.is_symlink(), "unsupported test resource: " + rel)
                resources[rel] = digest(source_file)
                if target.exists():
                    verify_digest(target, resources[rel])
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_file, target)
        require(not any((support / package).exists() for package in PACKAGES), "runtime leaked into support tree")
        self.report["builds"][name] = {"head": self.git(root, name + "-build-head", "rev-parse", "HEAD"),
                "source_root": str(root),
                "wheel": str(wheel), "wheel_sha256": digest(wheel), "sdist": str(sdist), "sdist_sha256": digest(sdist),
                "modules": modules, "support": str(support)}
        self.report["builds"][name]["pinned_source_test_resources"] = resources
        self.save()
        return wheel, support

    def environment(self, name, requirements):
        folder = self.output / name
        venv.EnvBuilder(with_pip=True).create(folder)
        python = folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        report = self.output / (name + "-install.json")
        lock_args = ["-c", self.lock] if self.lock else []
        self.run(name + "-bootstrap-pip", python, "-m", "pip", "install", "pip==25.3")
        self.run(name + "-install", python, "-m", "pip", "install", "-r", ROOT / "requirements-ci.txt",
                 *lock_args, *requirements, "--report", report)
        installed = json.loads(report.read_text(encoding="utf-8"))
        if not self.lock:
            self.lock = self.output / "transitive-constraints.txt"
            self.lock.write_text("\n".join(item["metadata"]["name"] + "==" + item["metadata"]["version"]
                 for item in installed["install"] if item["metadata"]["name"].lower().replace("_", "-") not in set(PACKAGES.values())), encoding="utf-8")
        self.run(name + "-pip-check", python, "-m", "pip", "check")
        self.run(name + "-freeze", python, "-m", "pip", "freeze", "--all")
        self.report.setdefault("installs", {})[name] = {"report": str(report), "sha256": digest(report), "resolved": installed}
        self.save()
        return python

    def suite(self, python, support, lane, nodes, required, native, candidate=True):
        env = self.env.copy()
        # Existing clean-environment tests must install the genuine package,
        # never mistake the deliberately source-free support tree for a project.
        env["WAVEFRAME_LEDGER_TEST_WHEEL"] = self.report["builds"]["ledger"]["wheel"]
        if native:
            env.update(WAVEFRAME_LEDGER_ACTION_POLICY_DEV="1", WAVEFRAME_GUARD_ACTION_POLICY_DEV="1")
        config = self.output / (lane + "-config.json")
        proof = self.output / (lane + "-proof.json")
        write(config, {"nodes": nodes, "proof": str(proof), "junit": str(self.output / (lane + ".xml")),
                       "repository_source": self.report["builds"]["guard"]["source_root"] if lane == "guard-baseline" else None})
        self.run(lane, python, "-I", Path(__file__).resolve(), "--pytest", config, cwd=support, env=env)
        result = json.loads(proof.read_text(encoding="utf-8"))
        require(not result["origin_error"] and result["imports"], "missing/failed import-origin proof")
        if candidate:
            for name in ("ledger", "guard"):
                for rel, expected in self.report["builds"][name]["modules"].items():
                    path = python.parent.parent / ("Lib/site-packages" if os.name == "nt" else
                                                  "lib/python" + str(sys.version_info.major) + "." + str(sys.version_info.minor) + "/site-packages") / rel
                    require(path.is_file() and digest(path) == expected, "installed candidate byte mismatch: " + rel)
        for package, expected in [("cricore-contract-compiler", COMPILER_HEAD)] + ([] if candidate else [("governance-ledger", BASELINE_LEDGER)]):
            direct = json.loads(result["packages"][package]["direct_url"] or "{}")
            require(direct.get("vcs_info", {}).get("commit_id") == expected, "wrong exact dependency provenance: " + package)
        for package, version in [("cricore-contract-compiler", "0.5.0"), ("governance-ledger", "0.9.0"), ("waveframe-guard", "0.19.0")]:
            require(result["packages"][package]["version"] == version, "wrong installed version: " + package)
        for name, package in [("ledger", "governance-ledger"), ("guard", "waveframe-guard")]:
            if not candidate and name == "ledger":
                continue
            direct = json.loads(result["packages"][package]["direct_url"] or "{}")
            require(direct, "candidate install lacks honest origin")
            if "archive_info" in direct:
                expected = self.report["builds"][name]
                environment = "guard-baseline" if not candidate else ("source-built" if lane.endswith("-source") else "wheel-installed")
                matches = [item for item in self.report["installs"][environment]["resolved"]["install"]
                           if item["metadata"]["name"].lower().replace("_", "-") == package]
                require(len(matches) == 1, "missing/duplicate package install report")
                verify_archive_origins([direct, matches[0]["download_info"]], expected["wheel"], expected["wheel_sha256"])
            else:
                require(lane.endswith("-source") and direct.get("dir_info") == {}
                        and direct.get("url") == Path(self.report["builds"][name]["source_root"]).as_uri(), "wrong source-built origin")
        outcomes = junit_outcomes(self.output / (lane + ".xml"), result["collected"], result["outcomes"])
        counts = validate_cases(result["collected"], outcomes, required, lane, platform.system())
        self.report["suites"][lane] = {**counts, "proof_sha256": digest(proof)}
        self.report["passed_lanes"].append(lane)
        self.save()

    def execute(self, guard_root, expected_ledger):
        guard_root = Path(guard_root).resolve()
        self.report.update(ledger_head=expected_ledger, guard_head=GUARD_HEAD, compiler_head=COMPILER_HEAD,
                           ledger_security_head=LEDGER_SECURITY_HEAD, ledger_base=LEDGER_BASE, guard_base=GUARD_BASE)
        self.heads(guard_root, expected_ledger)
        self.scopes(guard_root)
        ledger_wheel, ledger_support = self.build(ROOT, "ledger", ["governance_ledger"])
        guard_wheel, guard_support = self.build(guard_root, "guard", ["guard", "waveframe_guard"])
        compiler = "cricore-contract-compiler @ git+https://github.com/Waveframe-Labs/cricore-contract-compiler.git@" + COMPILER_HEAD
        source = self.environment("source-built", [ROOT, guard_root, compiler])
        installed = self.environment("wheel-installed", [ledger_wheel, guard_wheel, compiler])
        baseline = self.environment("guard-baseline", [guard_wheel, compiler,
                  "governance-ledger @ git+https://github.com/Waveframe-Labs/Waveframe-Ledger.git@" + BASELINE_LEDGER])
        self.report["required_lanes"] = LANES
        self.save()
        for python, suffix in [(source, "source"), (installed, "installed")]:
            for native, label in [(False, "default"), (True, "development")]:
                self.suite(python, ledger_support, "ledger-" + label + "-" + suffix, ["tests"],
                           named_nodes(LEDGER_REQUIRED), native)
            self.suite(python, guard_support, "guard-pair-" + suffix,
                       named_nodes(GUARD_REQUIRED) + ACTION_REQUIRED, named_nodes(GUARD_REQUIRED) + ACTION_REQUIRED, True)
        self.suite(baseline, guard_support, "guard-baseline", ["tests"],
                   ["tests/test_action_policy_creation.py::test_exact_dependencies_and_installed_public_api_acceptance"], True, False)
        self.heads(guard_root, expected_ledger)
        self.scopes(guard_root)
        self.report["status"] = "passed"
        validate_result(self.report, expected_ledger, GUARD_HEAD)
        self.save()


def aggregate(folder, expected_ledger, output):
    report = dict(scope="legacy-v2-deny-only-containment", report_kind="matrix", status="incomplete",
        ledger_head=expected_ledger, guard_head=GUARD_HEAD, matrix_complete=False,
        release_ready=False, runtime_activation_ready=False, historical_certification="not claimed", cells=[])
    try:
        reports = list(Path(folder).rglob("containment-acceptance.json"))
        require(len(reports) == 4, "four independent cell reports required")
        cells = set()
        for path in reports:
            cell = json.loads(path.read_text(encoding="utf-8"))
            validate_result(cell, expected_ledger, GUARD_HEAD)
            require(cell.get("report_kind") == "cell" and cell.get("matrix_complete") is False, "not a cell result")
            key = (cell["system"], ".".join(cell["python"].split()[0].split(".")[:2]))
            require(key not in cells, "duplicate matrix cell")
            cells.add(key)
            report["cells"].append(dict(system=key[0], python=key[1], sha256=digest(path), report=str(path)))
        require(cells == {(os_name, py) for os_name in ("Linux", "Windows") for py in ("3.10", "3.14")}, "matrix axes incomplete")
        for repository, pr, expected in [("Waveframe-Ledger", 27, expected_ledger), ("Waveframe-Guard", 69, GUARD_HEAD)]:
            actual = subprocess.check_output(["git", "ls-remote", "https://github.com/Waveframe-Labs/" + repository + ".git",
                                               "refs/pull/" + str(pr) + "/head"], text=True).split()[0]
            require(actual == expected, "PR moved before matrix aggregation: " + repository)
        report.update(status="passed", matrix_complete=True)
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        write(output, report)
        raise
    write(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest", type=Path)
    parser.add_argument("--guard-root", type=Path)
    parser.add_argument("--expected-ledger")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--aggregate", type=Path)
    args = parser.parse_args()
    if args.pytest:
        return pytest_child(args.pytest)
    if args.aggregate:
        aggregate(args.aggregate, args.expected_ledger, args.output)
        return 0
    require(args.guard_root and args.expected_ledger and args.output, "explicit candidate inputs/output required")
    gate = Acceptance(args.output)
    try:
        gate.execute(args.guard_root, args.expected_ledger)
    except BaseException as exc:
        gate.report.update(status="failed", error=str(exc))
        gate.save()
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
