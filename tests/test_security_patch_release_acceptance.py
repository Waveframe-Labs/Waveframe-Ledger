"""Fail-closed contracts of the separately scoped distribution lane."""
import ast
import copy
import json
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


def test_all_authoring_and_native_v3_security_functions_are_named_and_documented():
    for file in ["tests/test_pack1_authoring_containment.py", "tests/test_policy_translation_publication_v3.py"]:
        functions = {node.name for node in ast.parse((ROOT / file).read_text(encoding="utf-8")).body
                     if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}
        assert set(release.LEDGER_SECURITY[file]) == functions
    documentation = (ROOT / "docs/SECURITY_PATCH_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    for node in release.LEDGER_NODES + release.GUARD_NODES:
        assert node in documentation


def test_trusted_helpers_and_historical_certification_are_not_modified():
    import subprocess
    subprocess.run(["git", "diff", "--exit-code", release.BASES["ledger"], "HEAD", "--",
        "tools/package_provenance.py", "tools/acceptance_pytest.py", "tools/check_compiler_provenance.py",
        "tools/run_action_policy_acceptance.py", "tools/run_deny_only_containment_acceptance.py",
        ".github/workflows/action-policy-development.yml", ".github/workflows/deny-only-containment.yml",
        "docs/acceptance", "docs/LEDGER_090_ACCEPTANCE.md"], cwd=ROOT, check=True)


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
