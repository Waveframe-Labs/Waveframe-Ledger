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
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import zipfile
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


def mandatory_cases(collected, outcomes, required, guard=False):
    require(len(collected) == len(set(collected)), "duplicate collection identity")
    require(set(collected) == set(outcomes), "collection/outcome mismatch")
    for name in required:
        matches = [node for node in collected if node == name or node.startswith(name + "[")]
        require(matches and any(outcomes[node]["status"] == "passed" for node in matches)
                and all(outcomes[node]["status"] == "passed" or (guard
                    and outcomes[node]["status"] == "skipped"
                    and containment.skip_allowed(node, outcomes[node].get("reason", ""), "guard-pair-installed", platform.system()))
                    for node in matches),
                "missing, skipped or failed mandatory case: " + name)


def child(config_path):
    """Distribution-specific adapter; origin/JUnit/archive verification is reused."""
    require(not sys.flags.optimize, "assertions must remain enabled")
    import pytest
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    imports, collected, outcomes, bindings = {}, [], {}, []
    finder = containment.OriginFinder(sys.prefix, imports)
    sys.meta_path.insert(0, finder)
    provenance = {}
    for name, version, modules in [("governance-ledger", "0.9.1", ["governance_ledger"]),
                                   ("waveframe-guard", "0.19.1", ["guard", "waveframe_guard"])]:
        provenance[name] = installed_archive(name, version, modules, config["archives"][name], config["install_report"])
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

    class Accounting:
        def pytest_collection_finish(self, session):
            actual = subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
            require(actual == config["head"], "repository inspection source moved")
            bindings.extend(containment.bind_repository_inputs(list(sys.modules.items()), support, source))
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
                imports=imports, provenance=provenance, origin_violations=violations, repository_inputs=bindings))

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
            mandatory_tests={"ledger": LEDGER_NODES, "guard": GUARD_NODES}, required_lanes=LANES,
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
        item.update(rebuilt_wheel=str(second), rebuilt_sha256=sha256(second), payload_sha256=contents(wheel))
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
            archives[distribution] = {"wheel": path, "sha256": sha256(path)}
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
            outcomes = containment.junit_outcomes(junit, result["collected"], result["outcomes"])
            self.report["suites"][lane] = dict(proof_sha256=sha256(proof),
                collected=len(result["collected"]), outcomes=result["outcomes"])
            self.save()
            mandatory_cases(result["collected"], outcomes, required, guard=package == "guard")
            require(not result["origin_violations"] and result["imports"], "origin proof failed")
            # Full Guard accepts ONLY the existing explicit platform skip rules;
            # mandatory security cases below additionally reject every skip.
            validation_lane = ("guard-baseline" if "-full-" in lane else "guard-pair-installed") if package == "guard" else ("ledger-development-installed" if native else "ledger-default-installed")
            counts = containment.validate_cases(result["collected"], outcomes, required, validation_lane, platform.system())
            self.report["suites"][lane] = {**counts, "proof_sha256": sha256(proof)}
        require(error is None and proof.exists(), error or "missing runtime proof")
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
                  historical_certification="not claimed", release_ready=False, runtime_activation_ready=False, cells=[])
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
            require(cell["mandatory_tests"] == {"ledger": LEDGER_NODES, "guard": GUARD_NODES}, "required manifest changed")
            for name, build in cell["builds"].items():
                require(build["head"] == pair[name]["head"], "build source identity mismatch")
                for key, hashkey, directory in [("wheel", "wheel_sha256", name + "-dist"),
                    ("sdist", "sdist_sha256", name + "-dist"),
                    ("rebuilt_wheel", "rebuilt_sha256", name + "-sdist-wheel")]:
                    filename = build[key].replace("\\", "/").rsplit("/", 1)[-1]
                    files = list(path.parent.rglob(directory + "/" + filename))
                    require(len(files) == 1 and sha256(files[0]) == build[hashkey], "retained candidate archive mismatch")
            axis = (cell["system"], ".".join(cell["python"].split()[0].split(".")[:2]))
            require(axis not in axes, "duplicate matrix cell")
            axes.add(axis)
            result["cells"].append(dict(axis=axis, report_sha256=sha256(path), builds=cell["builds"]))
        require(axes == {(os_name, py) for os_name in ("Linux", "Windows") for py in ("3.10", "3.14")}, "incomplete OS/Python axes")
        for name, repo in [("ledger", "Waveframe-Ledger"), ("guard", "Waveframe-Guard")]:
            head = subprocess.check_output(["git", "ls-remote", f"https://github.com/Waveframe-Labs/{repo}.git",
                f"refs/pull/{pair[name]['pr']}/head"], text=True).split()[0]
            require(head == pair[name]["head"], "PR moved before aggregation; re-pin all evidence")
        result.update(status="passed", matrix_complete=True)
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
