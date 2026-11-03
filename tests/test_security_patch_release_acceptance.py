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
    for node in release.LEDGER_NODES + release.GUARD_NODES:
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
