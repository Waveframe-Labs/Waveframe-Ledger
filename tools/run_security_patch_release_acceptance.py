"""Exact-pair distribution acceptance, distinct from historical certification.

Reuse the reviewed containment build/environment, import monitor, repository-input
binding and JUnit helpers. Package provenance is supplied by package_provenance;
no PEP 610 metadata or historical test is rewritten to fit a candidate.
"""
from __future__ import annotations

import argparse
import email
import importlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import subprocess
import sys
import tarfile
import zipfile
import xml.etree.ElementTree as ET
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_deny_only_containment_acceptance as containment
from package_provenance import installed_archive, sha256
from acceptance_pytest import ImportBoundary

ROOT = Path(__file__).resolve().parents[1]
BASES = {"ledger": "ccb0961043ad26e64b7673e910ca271bd1b24794",
         "guard": "fcd932b4f04430d6d2cbca3d13a979e455aff06e"}
VERSIONS = {"ledger": "0.9.1", "guard": "0.19.1"}
RUNTIME = {"ledger": ["governance_ledger"], "guard": ["guard", "waveframe_guard"]}
VERSION_EDITS = {"waveframe_guard/__init__.py": (b'__version__ = "0.19.0"', b'__version__ = "0.19.1"'),
                 "guard/sdk/guard.py": (b'return "0.19.0"', b'return "0.19.1"')}
LEDGER_SECURITY = {
    "tests/test_pack1_authoring_containment.py": [
        "test_new_domain_finalization_requires_path_allow",
        "test_new_translation_approval_requires_path_allow",
        "test_candidate_allow_requires_individual_confirmation_and_enforced_disposition",
        "test_unenforceable_clause_cannot_supply_an_allow",
        "test_historical_v2_and_v3_verify_without_reauthoring",
        "test_historical_deny_approval_cannot_issue_new_v2_or_v3_authority",
        "test_replacement_grants_require_new_bound_human_acceptance",
    ],
    "tests/test_policy_translation_publication_v3.py": [
        "test_v3_publishes_two_individually_confirmed_controls_from_one_exact_clause",
        "test_historical_v3_partial_evidence_survives_but_new_deny_only_approval_is_refused",
        "test_v3_publishes_entirely_unsupported_and_informational_clauses_truthfully",
        "test_missing_residual_acknowledgment_and_control_confirmation_fail_before_publication",
        "test_duplicate_and_contradictory_controls_never_reach_v3_publication",
        "test_v3_rejects_invalid_publication_chronology",
        "test_v3_independent_validation_fails_closed_on_public_provenance_tampering",
        "test_v3_rejects_post_approval_control_confirmation_even_if_outer_hash_is_restamped",
        "test_private_provider_evidence_can_be_deleted_without_affecting_publication",
        "test_one_byte_source_change_propagates_through_every_public_identity",
        "test_v3_schemas_are_strict_and_dispatch_rejects_cross_version_masquerading",
        "test_customer_coverage_and_explanations_exclude_implementation_vocabulary",
        "test_v3_validation_and_customer_coverage_are_deterministic",
        "test_guard_0190_loads_native_v3_after_private_evidence_deletion_and_enforces",
    ],
    "tests/test_policy_translation.py": [
        "test_bounded_binding_resolution_and_review_cannot_approve_role_only_authority",
        "test_changed_human_confirmation_or_late_confirmation_invalidates_approval",
        "test_cross_source_and_cross_authority_substitution_fail_closed",
        "test_direct_clause_downgrade_fails_before_approval_even_with_another_enforced_clause",
    ],
}
GUARD_SECURITY = containment.GUARD_REQUIRED
GUARD_NODES = containment.named_nodes(GUARD_SECURITY) + containment.ACTION_REQUIRED
LEDGER_NODES = containment.named_nodes(LEDGER_SECURITY)
HARNESS_NODE = "harness::current_pair_installed_archive_provenance"
HARNESS_NODES = [HARNESS_NODE]
HISTORICAL_NODES = ["tests/test_action_policy_creation.py::test_exact_dependencies_and_installed_public_api_acceptance[" + mode + "]"
                    for mode in ("development", "release")]
HISTORICAL_HELPER = "tools/acceptance/action_policy_creation.py"
HISTORICAL_HELPER_SHA256 = "5e6a7ef052388a7c412487ec94f3ad70279cef28ca21ba5cdadb5cff8578789d"
HISTORICAL_TEST_SHA256 = "99b02b797ed85a4e59a48df13f1098fcfb1b1410ba5e057f0a04234458bb0771"
HISTORICAL_PROPERTY = "historical_failure_signature"
HISTORICAL_SIGNATURE = dict(when="call", exception_type="builtins.KeyError", args=["'vcs_info'"],
    helper_module="tools.acceptance.action_policy_creation", distribution="governance-ledger", origin_kind="archive", frames=[
        dict(path="tests/test_action_policy_creation.py", function="test_exact_dependencies_and_installed_public_api_acceptance",
             line=65, sha256=HISTORICAL_TEST_SHA256),
        dict(path=HISTORICAL_HELPER, function="provenance", line=51, sha256=HISTORICAL_HELPER_SHA256)])
LANES = [f"{package}-{mode}-{artifact}" for artifact in ("wheel", "sdist-wheel")
         for package, mode in (("ledger", "default"), ("ledger", "development"), ("guard", "full"), ("guard", "security"))]
LANES += ["ledger-security-published", "guard-security-published"]


def require(condition, message):
    containment.require(condition, message)


def exact_runtime_bytes(base, current, edits):
    """Set equality AND exact byte substitution, never a filename-only allowlist."""
    changed = {key for key in base.keys() | current.keys() if base.get(key) != current.get(key)}
    require(changed == set(edits), "runtime change set differs: " + repr(sorted(changed)))
    for path, (before, after) in edits.items():
        require(base[path].count(before) == 1, "version marker must occur once: " + path)
        require(current[path] == base[path].replace(before, after), "runtime behavior/bytes changed: " + path)


def runtime_tree(root, directories):
    files = {}
    for directory in directories:
        for path in (root / directory).rglob("*"):
            require(not path.is_symlink(), "runtime symlink is not a declared version edit")
            if path.is_file() and not (path.parent.name == "__pycache__" and path.suffix == ".pyc"):
                files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def mandatory_cases(collected, outcomes, required, guard=False, system=None):
    require(len(collected) == len(set(collected)), "duplicate collection identity")
    require(set(collected) == set(outcomes), "collection/outcome mismatch")
    for name in required:
        matches = [node for node in collected if node == name or node.startswith(name + "[")]
        require(matches and any(outcomes[node]["status"] == "passed" for node in matches)
                and all(outcomes[node]["status"] == "passed" or (guard
                    and outcomes[node]["status"] == "skipped"
                    and containment.skip_allowed(node, outcomes[node].get("reason", ""), "guard-pair-installed", system or platform.system()))
                    for node in matches),
                "missing, skipped or failed mandatory case: " + name)


def historical_failures(collected, outcomes, junit, lane):
    """Reconcile exactly two executed failures; never turn their outcomes green."""
    if lane not in {"guard-full-wheel", "guard-full-sdist-wheel"}:
        return {}
    require(junit is not None, "historical failure requires retained JUnit")
    cases = list(ET.parse(junit).iter("testcase"))
    result = {}
    for node in HISTORICAL_NODES:
        require(collected.count(node) == 1 and outcomes.get(node, {}).get("status") == "failed",
                "historical case missing, skipped, passing or unreported: " + node)
        matches = [case for case in cases if case.get("classname") == "tests.test_action_policy_creation"
                   and case.get("name") == node.split("::")[1]]
        require(len(matches) == 1, "missing/duplicate historical JUnit case: " + node)
        case = matches[0]
        failures = case.findall("failure")
        require(len(failures) == 1 and case.find("error") is None and case.find("skipped") is None,
                "historical JUnit must contain one failure: " + node)
        failure = failures[0]
        signature = outcomes[node].get("failure_signature")
        properties = [p.get("value") for p in case.findall("properties/property") if p.get("name") == HISTORICAL_PROPERTY]
        try:
            retained_signature = json.loads(properties[0]) if len(properties) == 1 else None
        except (TypeError, ValueError):
            retained_signature = None
        require(signature == HISTORICAL_SIGNATURE and len(properties) == 1
                and retained_signature == HISTORICAL_SIGNATURE, "wrong historical traceback signature: " + node)
        text = (failure.text or "").replace("\\", "/").replace("\r\n", "\n").strip()
        reason = outcomes[node].get("reason", "").replace("\\", "/").replace("\r\n", "\n").strip()
        require(failure.get("message") == "KeyError: 'vcs_info'" and text == reason
                and text.endswith(HISTORICAL_HELPER + ":51: KeyError")
                and "    def provenance():" in text
                and '>           assert direct["vcs_info"]["commit_id"] == sha, (name, direct)' in text
                and "tests/test_action_policy_creation.py:65:" in text
                and "E           KeyError: 'vcs_info'" in text,
                "wrong historical JUnit exception/origin: " + node)
        result[node] = dict(status="FAILED", classification="historical-baseline-only",
            ledger_git_commit=containment.BASELINE_LEDGER, compiler_git_commit=containment.COMPILER_HEAD,
            signature=signature, junit_sha256=sha256(junit))
    return result


def checked_outcomes(junit, proof):
    result = containment.junit_outcomes(junit, proof["collected"], proof["outcomes"])
    for node, value in result.items():
        if value["status"] == "failed":
            value.update(proof["outcomes"][node])
    return result


def validate_exit_code(code, historical):
    require(code == (1 if historical else 0), "unexpected pytest process exit")


def account_cases(collected, outcomes, required, lane, system, junit=None):
    guard = lane.startswith("guard")
    mandatory_cases(collected, outcomes, required, guard=guard, system=system)
    historical = historical_failures(collected, outcomes, junit, lane)
    if lane == "ledger-security-published":
        validation_lane = "security-subset"  # no assertion that unselected catalog tests ran
    elif guard:
        validation_lane = "guard-baseline" if "-full-" in lane else "guard-pair-installed"
    else:
        validation_lane = "ledger-development-installed" if "-development-" in lane else "ledger-default-installed"
    current = [node for node in collected if node not in historical]
    counts = containment.validate_cases(current, {node: outcomes[node] for node in current}, required, validation_lane, system)
    return {**counts, "collected": len(collected), "failed": len(historical), "historical_baseline_only": historical}


def current_pair_installed_archive_provenance(config):
    return {name: installed_archive(name, version, modules, config["archives"][name], config["install_report"])
            for name, version, modules in [("governance-ledger", "0.9.1", ["governance_ledger"]),
                                          ("waveframe-guard", "0.19.1", ["guard", "waveframe_guard"])]}


def validate_pair_proof(proof, archives, payloads):
    """Account the existing helper's serialized proof, not a new origin scheme."""
    require(proof.get("outcomes", {}).get(HARNESS_NODE, {}).get("status") == "passed"
            and proof.get("collected", []).count(HARNESS_NODE) == 1, "missing mandatory installed-archive check")
    for name, version, modules in [("governance-ledger", "0.9.1", ["governance_ledger"]),
                                   ("waveframe-guard", "0.19.1", ["guard", "waveframe_guard"])]:
        item = proof.get("provenance", {}).get(name, {})
        expected = archives[name]
        require(item.get("version") == version and item.get("wheel_sha256") == expected["sha256"], "wrong current-pair version/hash: " + name)
        require(item.get("installed_sha256") == payloads[name] and payloads[name], "missing/different installed file bytes: " + name)
        require(set(item.get("module_paths", {})) == set(modules) and all(item["module_paths"].values()), "missing installed module origins: " + name)
        origins = item.get("origins", [])
        require(origins and all(origin.get("url") == expected["uri"] and "archive_info" in origin
                and "vcs_info" not in origin for origin in origins), "missing/different archive origins: " + name)
        for origin in origins:
            info = origin["archive_info"]
            hashes = dict(info.get("hashes", {}))
            if "hash" in info:
                algorithm, value = info["hash"].split("=", 1)
                require(algorithm not in hashes or hashes[algorithm] == value, "contradictory origin hashes")
                hashes[algorithm] = value
            require(hashes.get("sha256") == expected["sha256"], "missing/different origin SHA256: " + name)
        path_type = PureWindowsPath if proof.get("system") == "Windows" else PurePosixPath
        require(proof.get("prefix") and all(path_type(path).is_relative_to(path_type(proof["prefix"]))
                for path in item["module_paths"].values()), "installed module outside prefix: " + name)


def capture_historical_signature(call, support):
    exc = call.excinfo
    frames = []
    if exc:
        for entry in list(exc.traceback)[-2:]:
            path = Path(entry.path).resolve()
            frames.append(dict(path=path.relative_to(support).as_posix() if path.is_relative_to(support) else str(path),
                               function=entry.name, line=entry.lineno + 1, sha256=sha256(path)))
    local = list(exc.traceback)[-1].frame.f_locals if exc else {}
    direct = local.get("direct")
    return dict(when=call.when, exception_type=(type(exc.value).__module__ + "." + type(exc.value).__qualname__) if exc else None,
                args=[repr(arg) for arg in exc.value.args] if exc else [], frames=frames,
                helper_module=list(exc.traceback)[-1].frame.f_globals.get("__name__") if exc else None,
                distribution=local.get("name"), origin_kind="archive" if isinstance(direct, dict)
                and "archive_info" in direct and "vcs_info" not in direct else "other")


def child(config_path):
    """Distribution-specific adapter; origin/JUnit/archive verification is reused."""
    require(not sys.flags.optimize, "assertions must remain enabled")
    import pytest
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    imports, collected, outcomes, bindings = {}, [], {}, []
    finder = containment.OriginFinder(sys.prefix, imports)
    sys.meta_path.insert(0, finder)
    provenance = current_pair_installed_archive_provenance(config)
    if config["published_compiler"]:
        provenance["cricore-contract-compiler"] = installed_archive("cricore-contract-compiler", "0.5.0",
            ["compiler"], config["archives"]["cricore-contract-compiler"], config["install_report"])
    else:
        # Exact Git installation: the existing helper's contract fits unchanged.
        from package_provenance import compiler_provenance
        provenance["cricore-contract-compiler"] = compiler_provenance()
    support, source = Path.cwd().resolve(), Path(config["source"]).resolve()
    sys.path.insert(0, str(support))  # tests/tools only; no runtime sources
    os.environ.update(LEDGER_EXPECT_IMPORT_ROOT=sys.prefix, LEDGER_IMPORT_REPORT=config["ledger_imports"])

    class ArchiveCheck(pytest.Item):
        def runtest(self):
            provenance.update(current_pair_installed_archive_provenance(config))

    class Accounting:
        def pytest_collection_modifyitems(self, session, config, items):
            items.append(ArchiveCheck.from_parent(session, name=HARNESS_NODE.split("::")[1], nodeid=HARNESS_NODE))

        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_makereport(self, item, call):
            outcome = yield
            report = outcome.get_result()
            if item.nodeid in HISTORICAL_NODES and call.when == "call":
                signature = capture_historical_signature(call, support)
                item.user_properties.append((HISTORICAL_PROPERTY, json.dumps(signature, sort_keys=True)))
                report.user_properties.append((HISTORICAL_PROPERTY, json.dumps(signature, sort_keys=True)))
                report.historical_failure_signature = signature

        def pytest_collection_finish(self, session):
            actual = subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
            require(actual == config["head"], "repository inspection source moved")
            bindings.extend(containment.bind_repository_inputs(list(sys.modules.items()), support, source))
            collected.extend(item.nodeid for item in session.items)

        def pytest_runtest_logreport(self, report):
            if report.failed:
                outcomes[report.nodeid] = {"status": "failed", "reason": str(report.longrepr)}
                if hasattr(report, "historical_failure_signature"):
                    outcomes[report.nodeid]["failure_signature"] = report.historical_failure_signature
            elif report.skipped:
                reason = str(report.longrepr[2]) if isinstance(report.longrepr, tuple) else str(report.longrepr)
                outcomes[report.nodeid] = {"status": "skipped", "reason": reason.removeprefix("Skipped: ")}
            elif report.when == "call" and report.nodeid not in outcomes:
                outcomes[report.nodeid] = {"status": "passed"}

        def pytest_sessionfinish(self, session, exitstatus):
            violations = list(finder.violations)
            for name, module in list(sys.modules.items()):
                path = getattr(module, "__file__", None)
                if name.split(".")[0] in containment.PACKAGES and path:
                    try:
                        containment.verify_origin(name, path, sys.prefix)
                    except RuntimeError as exc:
                        violations.append(str(exc))
            if finder not in sys.meta_path:
                violations.append("origin monitor removed")
            if violations:
                session.exitstatus = 1
            containment.write(config["proof"], dict(collected=collected, outcomes=outcomes,
                imports=imports, provenance=provenance, origin_violations=violations, repository_inputs=bindings,
                prefix=sys.prefix, system=platform.system()))

    return pytest.main(["-q", "-ra", "--junitxml", config["junit"], *config["nodes"]],
                       plugins=[ImportBoundary(), Accounting()])


class Acceptance(containment.Acceptance):
    def save(self):
        containment.write(self.output / "security-patch-acceptance.json", self.report)

    def __init__(self, output, pair):
        super().__init__(output)
        self.pair = pair
        self.env.pop("PYTHONOPTIMIZE", None)
        self.report.update(scope="security-patch-distributions", pair=pair,
            mandatory_tests={"ledger": LEDGER_NODES, "guard": GUARD_NODES, "harness": HARNESS_NODES}, required_lanes=LANES,
            historical_certification="not claimed", distribution_acceptance=False)
        self.save()

    def heads(self, guard_root):
        for name, root in [("ledger", ROOT), ("guard", guard_root)]:
            expected = self.pair[name]["head"]
            require(re.fullmatch("[0-9a-f]{40}", expected), "exact full SHA required")
            require(self.git(root, name + "-head", "rev-parse", "HEAD") == expected, "wrong checkout head")
            remote = self.git(root, name + "-pr-ref", "ls-remote", "origin", f"refs/pull/{self.pair[name]['pr']}/head")
            require(remote.split()[0] == expected, name + " PR changed: re-pin and revalidate all cells")
            require(not self.git(root, name + "-clean", "status", "--porcelain", "--untracked-files=all"), "checkout not clean")

    def scopes(self, guard_root):
        for name, root in [("ledger", ROOT), ("guard", guard_root)]:
            base = BASES[name]
            self.git(root, name + "-ancestor", "merge-base", "--is-ancestor", base, "HEAD")
            paths = self.git(root, name + "-runtime-files", "ls-tree", "-r", "--name-only", base, "--", *RUNTIME[name]).splitlines()
            old = {p: subprocess.check_output(["git", "-C", str(root), "show", base + ":" + p]) for p in paths}
            # Include ignored/untracked runtime resources too: Git cleanliness
            # alone must not let generated implementation enter a distribution.
            current = runtime_tree(root, RUNTIME[name])
            exact_runtime_bytes(old, current, {} if name == "ledger" else VERSION_EDITS)
            metadata = tomllib.loads(subprocess.check_output(["git", "-C", str(root), "show", base + ":pyproject.toml"], text=True))
            metadata["project"]["version"] = VERSIONS[name]
            if name == "ledger":
                metadata["tool"]["waveframe"]["guard-compatibility"].update(ledger="0.9.1", guard="0.19.1")
            require(tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")) == metadata,
                    "undeclared package metadata/dependency change: " + name)
            self.git(root, name + "-immutable-history", "diff", "--exit-code", base, "HEAD", "--",
                     "tests/fixtures", "tests/synthetic_evidence", "schemas", "docs/acceptance",
                     "tools/run_action_policy_acceptance.py", "tools/run_guard_extra_acceptance.py",
                     "tools/fetch_guard_candidate.py", "tools/run_deny_only_containment_acceptance.py",
                     "tools/package_provenance.py", "tools/acceptance_pytest.py", "tools/check_compiler_provenance.py",
                     ".github/workflows/action-policy-development.yml", ".github/workflows/deny-only-containment.yml",
                     "docs/LEDGER_090_ACCEPTANCE.md", "docs/RELEASE_019_ACCEPTANCE.md")
            if name == "guard":
                self.git(root, "historical-provenance-contract", "diff", "--exit-code", base, "HEAD", "--",
                         HISTORICAL_HELPER, "tests/test_action_policy_creation.py", "tests/conftest.py")
        self.report["runtime_scope"] = {"ledger": [], "guard": list(VERSION_EDITS)}
        self.save()

    def build(self, root, name, packages):
        wheel, support = super().build(root, name, packages)
        item = self.report["builds"][name]
        with tarfile.open(item["sdist"]) as archive:
            require(all(not Path(m.name).is_absolute() and ".." not in Path(m.name).parts
                        and "\\" not in m.name and ":" not in m.name
                        and (m.isfile() or m.isdir()) for m in archive.getmembers()), "unsafe sdist")
            unpack = self.output / (name + "-sdist-source")
            # Windows' supported Python 3.10.11 lacks tarfile extraction filters.
            # Extract only checked regular files, with no links or special types.
            for member in archive.getmembers():
                if member.isfile():
                    target = unpack / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
        source, = list(unpack.iterdir())
        rebuilt = self.output / (name + "-sdist-wheel")
        self.run(name + "-rebuild-sdist", sys.executable, "-m", "build", "--wheel", "--outdir", rebuilt, source)
        second, = rebuilt.glob("*.whl")
        def contents(path):
            with zipfile.ZipFile(path) as archive:
                return {p: sha256_bytes(archive.read(p)) for p in archive.namelist() if not p.endswith("/RECORD")}
        require(contents(wheel) == contents(second), "sdist wheel payload differs: " + name)
        self.run(name + "-rebuilt-twine", sys.executable, "-m", "twine", "check", "--strict", second)
        with zipfile.ZipFile(wheel) as archive:
            metadata, = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            info = email.message_from_bytes(archive.read(metadata))
            require(info["Version"] == VERSIONS[name] and info["Requires-Python"] == ">=3.10", "wrong release metadata")
        item.update(wheel_uri=wheel.resolve().as_uri(), rebuilt_wheel=str(second),
                    rebuilt_uri=second.resolve().as_uri(), rebuilt_sha256=sha256(second), payload_sha256=contents(wheel))
        self.save()
        return wheel, support

    def suite(self, python, support, lane, nodes, required, native, artifact, published=False):
        package = "ledger" if lane.startswith("ledger") else "guard"
        config, proof, junit = [self.output / (lane + suffix) for suffix in ("-config.json", "-proof.json", ".xml")]
        env = self.env.copy()
        if native:
            env.update(WAVEFRAME_LEDGER_ACTION_POLICY_DEV="1", WAVEFRAME_GUARD_ACTION_POLICY_DEV="1")
        env.update(WAVEFRAME_LEDGER_TEST_WHEEL=self.report["builds"]["ledger"][artifact], GUARD_EXPECT_INSTALLED="1")
        archives = {}
        for name, distribution in [("ledger", "governance-ledger"), ("guard", "waveframe-guard")]:
            path = self.report["builds"][name][artifact]
            archives[distribution] = {"wheel": path, "sha256": sha256(path), "uri": Path(path).resolve().as_uri()}
        if published:
            archives["cricore-contract-compiler"] = self.report["published_compiler"]
        environment = "published-pair" if published else artifact + "-pair"
        containment.write(config, dict(nodes=nodes, proof=str(proof), junit=str(junit), archives=archives,
            install_report=str(self.output / (environment + "-install.json")), published_compiler=published,
            source=self.report["builds"][package]["source_root"], head=self.pair[package]["head"],
            ledger_imports=str(self.output / (lane + "-ledger-imports.json"))))
        error = None
        try:
            self.run(lane, python, "-I", Path(__file__).resolve(), "--pytest", config, cwd=support, env=env)
        except RuntimeError as exc:
            error = str(exc)
        if proof.exists():
            result = json.loads(proof.read_text(encoding="utf-8"))
            outcomes = checked_outcomes(junit, result)
            self.report["suites"][lane] = dict(proof_sha256=sha256(proof),
                collected=len(result["collected"]), outcomes=result["outcomes"])
            self.save()
            require(not result["origin_violations"] and result["imports"], "origin proof failed")
            validate_pair_proof(result, archives, {distribution: self.report["builds"][name]["payload_sha256"]
                for name, distribution in [("ledger", "governance-ledger"), ("guard", "waveframe-guard")]})
            # Full Guard accepts ONLY the existing explicit platform skip rules;
            # mandatory cases reject every other skip, including missing archive checks.
            counts = account_cases(result["collected"], outcomes, required + HARNESS_NODES, lane, platform.system(), junit)
            self.report["suites"][lane] = {**counts, "proof_sha256": sha256(proof), "junit_sha256": sha256(junit)}
        else:
            raise RuntimeError(error or "missing runtime proof")
        validate_exit_code(self.report["commands"][-1]["exit"], counts["historical_baseline_only"])
        self.report["passed_lanes"].append(lane)
        self.save()

    def execute(self, guard_root):
        self.heads(guard_root)
        self.scopes(guard_root)
        lw, ls = self.build(ROOT, "ledger", RUNTIME["ledger"])
        gw, gs = self.build(guard_root, "guard", RUNTIME["guard"])
        # Use the already-reviewed Guard archive inspector with its version argument.
        sys.path.insert(0, str(guard_root))
        inspector = importlib.import_module("tools.acceptance.package_acceptance")
        inspector._inspect_wheel(gw, "0.19.1")
        inspector._inspect_sdist(Path(self.report["builds"]["guard"]["sdist"]), "0.19.1")
        errors = []
        for artifact in ("wheel", "rebuilt_wheel"):
            python = self.environment(artifact + "-pair", [self.report["builds"][n][artifact] for n in ("ledger", "guard")] + [
                "cricore-contract-compiler @ git+https://github.com/Waveframe-Labs/cricore-contract-compiler.git@" + containment.COMPILER_HEAD])
            self.run(artifact + "-compiler-provenance", python, "-I", ROOT / "tools/check_compiler_provenance.py")
            label = "wheel" if artifact == "wheel" else "sdist-wheel"
            for package, mode, support, nodes, required, native in [
                ("ledger", "default", ls, ["tests"], LEDGER_NODES, False),
                ("ledger", "development", ls, ["tests"], LEDGER_NODES, True),
                ("guard", "full", gs, ["tests"], GUARD_NODES, True),
                ("guard", "security", gs, GUARD_NODES, GUARD_NODES, True)]:
                lane = f"{package}-{mode}-{label}"
                try:
                    self.suite(python, support, lane, nodes, required, native, artifact)
                except BaseException as exc:
                    errors.append({"lane": lane, "error": str(exc)})
                    self.report["failures"] = errors
                    self.save()
        published = self.output / "published-compiler"
        self.run("download-published-compiler", sys.executable, "-m", "pip", "download", "--only-binary=:all:",
                 "--no-deps", "--dest", published, "cricore-contract-compiler==0.5.0")
        cw, = published.glob("*.whl")
        require(sha256(cw) == "1bc689d2885e32641ac3ade7e710a4d0fe079c089f1a2160e2d86f328bbb7c44", "published compiler changed")
        self.report["published_compiler"] = dict(wheel=str(cw), sha256=sha256(cw))
        python = self.environment("published-pair", [lw, gw, cw])
        for package, support, required in [("ledger", ls, LEDGER_NODES), ("guard", gs, GUARD_NODES)]:
            lane = package + "-security-published"
            try:
                self.suite(python, support, lane, required, required, True, "wheel", True)
            except BaseException as exc:
                errors.append({"lane": lane, "error": str(exc)})
                self.report["failures"] = errors
                self.save()
        self.heads(guard_root)
        self.scopes(guard_root)
        require(not errors and set(self.report["passed_lanes"]) == set(LANES), "distribution acceptance has failed lanes")
        self.report.update(status="passed", distribution_acceptance=True)
        self.save()


def sha256_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def aggregate(folder, pair, output):
    result = dict(scope="security-patch-distributions", pair=pair, status="failed", matrix_complete=False,
                  distribution_acceptance=False, historical_certification="not claimed", release_ready=False,
                  runtime_activation_ready=False, cells=[])
    try:
        reports = list(Path(folder).rglob("security-patch-acceptance.json"))
        require(len(reports) == 4, "exactly four cell reports required")
        axes = set()
        for path in reports:
            cell = json.loads(path.read_text(encoding="utf-8"))
            require(cell["pair"] == pair and cell["scope"] == result["scope"], "different pair provenance")
            require(cell["status"] == "passed" and cell.get("distribution_acceptance") is True
                    and set(cell["passed_lanes"]) == set(LANES), "failed/incomplete cell")
            require(cell["historical_certification"] == "not claimed" and cell["release_ready"] is False
                    and cell["runtime_activation_ready"] is False, "false historical/promotion claim")
            require(cell["mandatory_tests"] == {"ledger": LEDGER_NODES, "guard": GUARD_NODES, "harness": HARNESS_NODES}, "required manifest changed")
            for name, build in cell["builds"].items():
                require(build["head"] == pair[name]["head"], "build source identity mismatch")
                for key, hashkey, directory in [("wheel", "wheel_sha256", name + "-dist"),
                    ("sdist", "sdist_sha256", name + "-dist"),
                    ("rebuilt_wheel", "rebuilt_sha256", name + "-sdist-wheel")]:
                    filename = build[key].replace("\\", "/").rsplit("/", 1)[-1]
                    files = list(path.parent.rglob(directory + "/" + filename))
                    require(len(files) == 1 and sha256(files[0]) == build[hashkey], "retained candidate archive mismatch")
            require(set(cell["suites"]) == set(LANES), "missing lane evidence")
            historical = {}
            for lane in LANES:
                proof_path, junit = path.parent / (lane + "-proof.json"), path.parent / (lane + ".xml")
                require(sha256(proof_path) == cell["suites"][lane]["proof_sha256"]
                        and sha256(junit) == cell["suites"][lane]["junit_sha256"], "lane proof/JUnit changed")
                proof = json.loads(proof_path.read_text(encoding="utf-8"))
                require(proof.get("imports") and not proof.get("origin_violations"), "missing/failed import proof")
                artifact = "rebuilt_wheel" if "sdist-wheel" in lane else "wheel"
                archives = {distribution: dict(sha256=cell["builds"][name]["rebuilt_sha256" if artifact == "rebuilt_wheel" else "wheel_sha256"],
                    uri=cell["builds"][name]["rebuilt_uri" if artifact == "rebuilt_wheel" else "wheel_uri"])
                    for name, distribution in [("ledger", "governance-ledger"), ("guard", "waveframe-guard")]}
                validate_pair_proof(proof, archives, {distribution: cell["builds"][name]["payload_sha256"]
                    for name, distribution in [("ledger", "governance-ledger"), ("guard", "waveframe-guard")]})
                required = (LEDGER_NODES if lane.startswith("ledger") else GUARD_NODES) + HARNESS_NODES
                counts = account_cases(proof["collected"], checked_outcomes(junit, proof), required, lane, cell["system"], junit)
                require(all(cell["suites"][lane][key] == value for key, value in counts.items()), "lane accounting changed")
                if counts["historical_baseline_only"]:
                    historical[lane] = counts["historical_baseline_only"]
            axis = (cell["system"], ".".join(cell["python"].split()[0].split(".")[:2]))
            require(axis not in axes, "duplicate matrix cell")
            axes.add(axis)
            result["cells"].append(dict(axis=axis, report_sha256=sha256(path), builds=cell["builds"], historical_baseline_only=historical))
        require(axes == {(os_name, py) for os_name in ("Linux", "Windows") for py in ("3.10", "3.14")}, "incomplete OS/Python axes")
        for name, repo in [("ledger", "Waveframe-Ledger"), ("guard", "Waveframe-Guard")]:
            head = subprocess.check_output(["git", "ls-remote", f"https://github.com/Waveframe-Labs/{repo}.git",
                f"refs/pull/{pair[name]['pr']}/head"], text=True).split()[0]
            require(head == pair[name]["head"], "PR moved before aggregation; re-pin all evidence")
        result.update(status="passed", matrix_complete=True, distribution_acceptance=True)
    except BaseException as exc:
        result["error"] = str(exc)
        raise
    finally:
        containment.write(output, result)


def main():
    require(not sys.flags.optimize, "assertions must remain enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest", type=Path)
    parser.add_argument("--guard-root", type=Path)
    parser.add_argument("--ledger-head")
    parser.add_argument("--guard-head")
    parser.add_argument("--ledger-pr", type=int)
    parser.add_argument("--guard-pr", type=int)
    parser.add_argument("--aggregate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.pytest:
        return child(args.pytest)
    require(args.ledger_pr and args.guard_pr and args.output, "real PR identities/output required")
    pair = {name: dict(head=getattr(args, name + "_head"), pr=getattr(args, name + "_pr"),
                       version=VERSIONS[name], base=BASES[name]) for name in ("ledger", "guard")}
    require(all(re.fullmatch("[0-9a-f]{40}", p["head"] or "") for p in pair.values()), "full exact heads required")
    if args.aggregate:
        aggregate(args.aggregate, pair, args.output)
        return 0
    require(args.guard_root, "explicit Guard checkout required")
    gate = Acceptance(args.output, pair)
    try:
        gate.execute(args.guard_root.resolve())
    except BaseException as exc:
        gate.report.update(status="failed", error=str(exc))
        gate.save()
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
