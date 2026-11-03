"""Fail-closed contracts of the separately scoped distribution lane."""
import ast
import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools import run_security_patch_release_acceptance as release

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_scope_requires_exact_version_edits_and_no_behavior_changes():
    base = {p: b"prefix\n" + before + b"\nsuffix\n" for p, (before, after) in release.VERSION_EDITS.items()}
    candidate = {p: content.replace(*release.VERSION_EDITS[p]) for p, content in base.items()}
    release.exact_runtime_bytes(base, candidate, release.VERSION_EDITS)
    for changed in [base, {**candidate, "guard/behavior.py": b"new"},
                    {**candidate, "guard/sdk/guard.py": candidate["guard/sdk/guard.py"] + b"change"}]:
        with pytest.raises(RuntimeError, match="runtime"):
            release.exact_runtime_bytes(base, changed, release.VERSION_EDITS)
    with pytest.raises(RuntimeError, match="runtime"):
        release.exact_runtime_bytes({"a": b"old"}, {"a": b"new"}, {})


def test_ignored_runtime_additions_cannot_escape_byte_scope(tmp_path):
    package = tmp_path / "guard"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"original")
    base = release.runtime_tree(tmp_path, ["guard"])
    (package / "generated.py").write_bytes(b"unreviewed")
    with pytest.raises(RuntimeError, match="runtime change set"):
        release.exact_runtime_bytes(base, release.runtime_tree(tmp_path, ["guard"]), {})


@pytest.mark.parametrize("status", ["skipped", "failed"])
def test_every_mandatory_ledger_parameter_must_pass(status):
    nodes = ["tests/gate.py::test_gate[a]", "tests/gate.py::test_gate[b]"]
    outcomes = {node: {"status": "passed"} for node in nodes}
    outcomes[nodes[-1]]["status"] = status
    with pytest.raises(RuntimeError, match="mandatory"):
        release.mandatory_cases(nodes, outcomes, ["tests/gate.py::test_gate"])


def test_missing_uncollected_duplicate_and_unreported_mandatory_cases_fail():
    for nodes, outcomes in [([], {}), (["other"], {"other": {"status": "passed"}}),
        (["required"], {}), (["required", "required"], {"required": {"status": "passed"}})]:
        with pytest.raises(RuntimeError):
            release.mandatory_cases(nodes, outcomes, ["required"])


def test_guard_unexpected_skip_cannot_pass_mandatory_accounting():
    with pytest.raises(RuntimeError, match="mandatory"):
        release.mandatory_cases(["required"], {"required": {"status": "skipped", "reason": "dependency missing"}},
                                ["required"], guard=True)


def test_security_subset_does_not_claim_full_catalog_coverage():
    nodes = ["tests/security.py::test_required"]
    outcomes = {nodes[0]: {"status": "passed"}}
    assert release.account_cases(nodes, outcomes, nodes, "ledger-security-published", "Linux")["passed"] == 1
    with pytest.raises(RuntimeError, match="release catalog coverage"):
        release.account_cases(nodes, outcomes, nodes, "ledger-development-wheel", "Linux")


def test_all_authoring_and_native_v3_security_functions_are_named_and_documented():
    for file in ["tests/test_pack1_authoring_containment.py", "tests/test_policy_translation_publication_v3.py"]:
        functions = {node.name for node in ast.parse((ROOT / file).read_text(encoding="utf-8")).body
                     if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}
        assert set(release.LEDGER_SECURITY[file]) == functions
    documentation = (ROOT / "docs/SECURITY_PATCH_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    for node in release.LEDGER_NODES + release.GUARD_NODES + release.HARNESS_NODES:
        assert node in documentation


def test_trusted_helpers_and_historical_certification_are_not_modified():
    import hashlib
    # Canonical text hashes work in ordinary shallow checkouts as well.
    expected = {
        'tools/package_provenance.py': 'f957f0f248aba2218ae447ecb23cdd312b2cf5ae4010f89dcd86089e7efbf8f8',
        'tools/acceptance_pytest.py': '359d9e25d79176fbbc85230182f0578d8685570622d7b02670cf09ff9aec649e',
        'tools/check_compiler_provenance.py': 'e78600dd13c7877e3b4ac942f263533f9408d9d04c4609d354b6b3f2e735d0ad',
        'tools/run_deny_only_containment_acceptance.py': 'f68b1e098cef8c53cd997efd631a981b812e07d9ae5cf5062f1c98ef68820477',
        'tools/run_action_policy_acceptance.py': '74ff0a066ea3ca763db50792d74ce42fa690a569b1e9f5bb06ba37b2ed8d942b',
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode()).hexdigest() == digest


def test_workflow_has_release_only_triggers_and_read_only_permissions():
    workflow = (ROOT / ".github/workflows/security-patch-release.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "startsWith(github.head_ref, 'release/security-')" in workflow
    assert "contents: read" in workflow
    for forbidden in ["secrets.", "id-token:", "contents: write", "pull_request_target:", "  push:",
                      "pypi-publish", "twine upload", "repository_dispatch", "workflow_run", "environment:"]:
        assert forbidden not in workflow


def test_governance_retains_unique_wheel_exact_version_and_guard_absence():
    workflow = (ROOT / ".github/workflows/governance.yml").read_text(encoding="utf-8")
    assert "assert len(wheels)==1" in workflow
    assert ".glob('*.whl')" in workflow
    assert "m.version('governance-ledger') == tomllib.loads" in workflow
    assert "assert importlib.util.find_spec('waveframe_guard') is None" in workflow


def test_aggregate_cannot_hide_failed_or_missing_cells(tmp_path):
    pair = {name: dict(head="a" * 40, pr=1, version=release.VERSIONS[name], base=release.BASES[name])
            for name in release.BASES}
    for number in range(4):
        folder = tmp_path / str(number)
        folder.mkdir()
        (folder / "security-patch-acceptance.json").write_text(json.dumps(dict(
            pair=pair, scope="security-patch-distributions", status="failed")), encoding="utf-8")
    with pytest.raises(RuntimeError, match="failed/incomplete"):
        release.aggregate(tmp_path, pair, tmp_path / "matrix.json")
    assert json.loads((tmp_path / "matrix.json").read_text())["status"] == "failed"


@pytest.fixture
def historical_evidence(tmp_path):
    text = ('    def test_exact_dependencies_and_installed_public_api_acceptance():\n'
            '>       assert provenance()\ntests/test_action_policy_creation.py:65:\n'
            '    def provenance():\n'
            '>           assert direct["vcs_info"]["commit_id"] == sha, (name, direct)\n'
            "E           KeyError: 'vcs_info'\n\ntools/acceptance/action_policy_creation.py:51: KeyError")
    nodes = [*release.HISTORICAL_NODES, release.HARNESS_NODE]
    outcomes = {node: dict(status="failed", reason=text, failure_signature=copy.deepcopy(release.HISTORICAL_SIGNATURE))
                for node in release.HISTORICAL_NODES}
    outcomes[release.HARNESS_NODE] = dict(status="passed")
    xml = ET.Element("testsuite")
    for node in nodes:
        file, name = node.split("::")
        case = ET.SubElement(xml, "testcase", classname=file.removesuffix('.py').replace('/', '.'), name=name)
        if node in release.HISTORICAL_NODES:
            ET.SubElement(case, "failure", message="KeyError: 'vcs_info'").text = text
            props = ET.SubElement(case, "properties")
            ET.SubElement(props, "property", name=release.HISTORICAL_PROPERTY,
                          value=json.dumps(release.HISTORICAL_SIGNATURE))
    path = tmp_path / "historical.xml"
    ET.ElementTree(xml).write(path, encoding="utf-8")
    return nodes, outcomes, xml, path


def test_exact_historical_failures_stay_failed_and_are_never_passes(historical_evidence):
    nodes, observed, xml, path = historical_evidence
    original = copy.deepcopy(observed)
    checked = release.checked_outcomes(path, dict(collected=nodes, outcomes=observed))
    counts = release.account_cases(nodes, checked, release.HARNESS_NODES, "guard-full-wheel", "Linux", path)
    assert counts["passed"] == 1 and counts["failed"] == 2 and counts["collected"] == 3
    assert set(counts["historical_baseline_only"]) == set(release.HISTORICAL_NODES)
    assert all(case["status"] == "FAILED" for case in counts["historical_baseline_only"].values())
    assert observed == original and len(xml.findall("testcase/failure")) == 2
    assert all(case["ledger_git_commit"] == "a34c11d81b85963794cf28b4adad091fac15e130"
               for case in counts["historical_baseline_only"].values())


@pytest.mark.parametrize("mutation", ["absent", "unreported", "duplicate", "pass", "skip", "extra-failure"])
def test_historical_case_presence_status_and_additional_failures_are_strict(historical_evidence, mutation):
    nodes, outcomes, xml, path = historical_evidence
    node = release.HISTORICAL_NODES[0]
    if mutation == "absent":
        nodes.remove(node); outcomes.pop(node); xml.remove(xml[0])
    elif mutation == "unreported":
        outcomes.pop(node)
    elif mutation == "duplicate":
        nodes.append(node)
    elif mutation in {"pass", "skip"}:
        outcomes[node]["status"] = "passed" if mutation == "pass" else "skipped"
    else:
        nodes.append("tests/other.py::test_other")
        outcomes[nodes[-1]] = dict(status="failed", reason="KeyError: 'vcs_info'")
    ET.ElementTree(xml).write(path, encoding="utf-8")
    with pytest.raises((RuntimeError, KeyError)):
        release.account_cases(nodes, outcomes, release.HARNESS_NODES, "guard-full-wheel", "Linux", path)


@pytest.mark.parametrize("mutation", ["type", "args", "phase", "module", "distribution", "origin_kind", "path", "function", "line", "helper-bytes", "test-bytes"])
def test_historical_signature_cannot_match_another_failure(historical_evidence, mutation):
    nodes, outcomes, xml, path = historical_evidence
    signature = outcomes[nodes[0]]["failure_signature"]
    if mutation in {"type", "args", "phase", "module", "distribution", "origin_kind"}:
        key = {"type": "exception_type", "args": "args", "phase": "when", "module": "helper_module"}.get(mutation, mutation)
        signature[key] = ["'other'"] if mutation == "args" else "other"
    elif mutation == "test-bytes":
        signature["frames"][0]["sha256"] = "0" * 64
    else:
        signature["frames"][-1][{"helper-bytes": "sha256"}.get(mutation, mutation)] = "other"
    xml[0].find("properties/property").set("value", json.dumps(signature))
    ET.ElementTree(xml).write(path, encoding="utf-8")
    with pytest.raises(RuntimeError, match="signature"):
        release.historical_failures(nodes, outcomes, path, "guard-full-wheel")


@pytest.mark.parametrize("mutation", ["missing-case", "duplicate-case", "no-failure", "extra-failure", "error", "skip",
    "message", "origin", "reason", "missing-property", "duplicate-property", "bad-property", "malformed-property",
    "missing-runtime-signature", "missing-junit"])
def test_retained_junit_must_prove_the_exact_historical_exception(historical_evidence, mutation):
    nodes, outcomes, xml, path = historical_evidence
    case = xml[0]
    if mutation == "missing-case": xml.remove(case)
    elif mutation == "duplicate-case": xml.append(copy.deepcopy(case))
    elif mutation == "no-failure": case.remove(case.find("failure"))
    elif mutation == "extra-failure": ET.SubElement(case, "failure")
    elif mutation in {"error", "skip"}: ET.SubElement(case, "error" if mutation == "error" else "skipped")
    elif mutation == "message": case.find("failure").set("message", "ValueError: vcs_info")
    elif mutation == "origin":
        text = case.find("failure").text.replace("action_policy_creation.py:51", "other.py:51")
        case.find("failure").text = text; outcomes[nodes[0]]["reason"] = text
    elif mutation == "reason": outcomes[nodes[0]]["reason"] = "different runtime traceback"
    elif mutation == "missing-property": case.remove(case.find("properties"))
    elif mutation == "duplicate-property": case.find("properties").append(copy.deepcopy(case.find("properties/property")))
    elif mutation == "bad-property": case.find("properties/property").set("value", "null")
    elif mutation == "malformed-property": case.find("properties/property").set("value", "{")
    elif mutation == "missing-runtime-signature": outcomes[nodes[0]].pop("failure_signature")
    ET.ElementTree(xml).write(path, encoding="utf-8")
    with pytest.raises(RuntimeError):
        release.historical_failures(nodes, outcomes, None if mutation == "missing-junit" else path, "guard-full-sdist-wheel")


@pytest.mark.parametrize("code,historical", [(0, True), (2, True), (3, True), (-9, True), (1, False), (2, False)])
def test_only_exact_pytest_exit_codes_are_accepted(code, historical):
    with pytest.raises(RuntimeError, match="process exit"):
        release.validate_exit_code(code, historical)


@pytest.fixture
def archive_evidence():
    archives, payloads, provenance = {}, {}, {}
    for name, version, modules in [("governance-ledger", "0.9.1", ["governance_ledger"]),
                                   ("waveframe-guard", "0.19.1", ["guard", "waveframe_guard"])]:
        archives[name] = dict(sha256="a" * 64, uri="file:///accepted/" + name + ".whl")
        payloads[name] = {module + "/__init__.py": "b" * 64 for module in modules}
        provenance[name] = dict(version=version, wheel_sha256="a" * 64, installed_sha256=copy.deepcopy(payloads[name]),
            module_paths={module: "/venv/lib/" + module + "/__init__.py" for module in modules},
            origins=[dict(url=archives[name]["uri"], archive_info=dict(hashes=dict(sha256="a" * 64)))])
    proof = dict(collected=release.HARNESS_NODES.copy(), outcomes={release.HARNESS_NODE: dict(status="passed")},
                 provenance=provenance, prefix="/venv", system="Linux")
    return proof, archives, payloads


@pytest.mark.parametrize("package", ["governance-ledger", "waveframe-guard"])
@pytest.mark.parametrize("mutation", ["missing", "version", "hash", "file-bytes", "modules", "module-outside", "origins",
    "origin-url", "git-origin", "origin-hash", "contradictory-hash"])
def test_each_current_package_archive_proof_is_mandatory(archive_evidence, package, mutation):
    proof, archives, payloads = archive_evidence
    release.validate_pair_proof(proof, archives, payloads)
    item = proof["provenance"][package]
    if mutation == "missing": proof["provenance"].pop(package)
    elif mutation == "version": item["version"] = "0.0.0"
    elif mutation == "hash": item["wheel_sha256"] = "0" * 64
    elif mutation == "file-bytes": item["installed_sha256"] = {}
    elif mutation == "modules": item["module_paths"] = {}
    elif mutation == "module-outside": item["module_paths"][next(iter(item["module_paths"]))] = "/checkout/module.py"
    elif mutation == "origins": item["origins"] = []
    elif mutation == "origin-url": item["origins"][0]["url"] = "file:///other.whl"
    elif mutation == "git-origin": item["origins"][0]["vcs_info"] = {}
    elif mutation == "origin-hash": item["origins"][0]["archive_info"]["hashes"] = {}
    elif mutation == "contradictory-hash": item["origins"][0]["archive_info"]["hash"] = "sha256=" + "c" * 64
    with pytest.raises(RuntimeError):
        release.validate_pair_proof(proof, archives, payloads)


@pytest.mark.parametrize("mutation", ["missing", "unreported", "duplicate", "skipped", "failed"])
def test_named_current_pair_check_cannot_be_missing_or_nonpassing(archive_evidence, mutation):
    proof, archives, payloads = archive_evidence
    if mutation == "missing": proof["collected"] = []
    elif mutation == "unreported": proof["outcomes"] = {}
    elif mutation == "duplicate": proof["collected"] *= 2
    else: proof["outcomes"][release.HARNESS_NODE]["status"] = mutation
    with pytest.raises(RuntimeError, match="mandatory"):
        release.validate_pair_proof(proof, archives, payloads)


@pytest.mark.parametrize("lane", ["guard-security-wheel", "guard-security-published", "ledger-security-published"])
def test_historical_reconciliation_never_applies_to_other_lanes(historical_evidence, lane):
    nodes, outcomes, xml, path = historical_evidence
    with pytest.raises(RuntimeError):
        release.account_cases(nodes, outcomes, release.HARNESS_NODES, lane, "Linux", path)


def test_named_archive_check_calls_both_unchanged_helpers_and_propagates_failure(monkeypatch):
    calls = []
    config = dict(archives={"governance-ledger": {"source": "ledger"}, "waveframe-guard": {"source": "guard"}}, install_report="report")
    def helper(name, version, modules, expected, report):
        calls.append((name, version, modules, expected, report))
        return {"verified": name}
    monkeypatch.setattr(release, "installed_archive", helper)
    result = release.current_pair_installed_archive_provenance(config)
    assert [call[0:2] for call in calls] == [("governance-ledger", "0.9.1"), ("waveframe-guard", "0.19.1")]
    assert set(result) == {"governance-ledger", "waveframe-guard"}
    def failing_helper(*args):
        raise AssertionError("wrong installed bytes")
    monkeypatch.setattr(release, "installed_archive", failing_helper)
    with pytest.raises(AssertionError, match="installed bytes"):
        release.current_pair_installed_archive_provenance(config)


def test_cross_platform_aggregate_keeps_only_the_named_windows_skips():
    function = "tests/test_repository_execution_evidence.py::test_repository_execution_states_persist_and_reload"
    nodes = [function + "[v1-normal]", function + "[v1-post_callback_native]"]
    outcomes = {nodes[0]: dict(status="passed"), nodes[1]: dict(status="skipped",
        reason="Windows namespace locks prevent this replacement; fault injection runs on both OSes")}
    release.mandatory_cases(nodes, outcomes, [function], guard=True, system="Windows")
    with pytest.raises(RuntimeError):
        release.mandatory_cases(nodes, outcomes, [function], guard=True, system="Linux")
