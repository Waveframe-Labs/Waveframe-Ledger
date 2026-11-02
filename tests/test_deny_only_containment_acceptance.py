"""Fail-closed contracts of the separate containment acceptance runner."""
import importlib.util
import json
from pathlib import Path

import pytest

from tools import run_deny_only_containment_acceptance as gate


def test_rejects_wrong_import_origin(tmp_path):
    with pytest.raises(RuntimeError, match="import-origin"):
        gate.verify_origin("guard", tmp_path / "checkout/guard.py", tmp_path / "venv")
    gate.verify_origin("guard", tmp_path / "venv/Lib/site-packages/guard.py", tmp_path / "venv")


def test_wrong_archive_digest_is_a_hard_failure(tmp_path):
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"actual bytes")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        gate.verify_digest(wheel, "0" * 64)


def test_honest_legacy_archive_report_binds_empty_pep610_hashes(tmp_path):
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"actual bytes")
    expected = gate.digest(wheel)
    direct = dict(url=wheel.as_uri(), archive_info={})
    report = dict(url=wheel.as_uri(), archive_info={"hash": "sha256=" + expected})
    gate.verify_archive_origins([direct, report], wheel, expected)
    with pytest.raises(RuntimeError, match="no honest sha256"):
        gate.verify_archive_origins([direct], wheel, expected)
    report["archive_info"]["hashes"] = {"sha256": "0" * 64}
    with pytest.raises(RuntimeError, match="contradictory"):
        gate.verify_archive_origins([direct, report], wheel, expected)


def test_wrong_archive_url_or_digest_cannot_be_hidden_by_install_report(tmp_path):
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"actual bytes")
    expected = gate.digest(wheel)
    valid = dict(url=wheel.as_uri(), archive_info={"hashes": {"sha256": expected}})
    with pytest.raises(RuntimeError, match="wrong archive origin"):
        gate.verify_archive_origins([dict(url="file:///different.whl", archive_info={}), valid], wheel, expected)
    with pytest.raises(RuntimeError, match="digest mismatch"):
        gate.verify_archive_origins([dict(url=wheel.as_uri(), archive_info={"hash": "sha256=" + "0" * 64}), valid], wheel, expected)


def test_nested_clean_environment_tests_receive_actual_candidate_wheel(tmp_path, monkeypatch):
    acceptance = gate.Acceptance(tmp_path / "evidence")
    wheel = tmp_path / "candidate.whl"
    acceptance.report["builds"]["ledger"] = {"wheel": str(wheel)}
    def run(label, *args, **kwargs):
        assert kwargs["env"]["WAVEFRAME_LEDGER_TEST_WHEEL"] == str(wheel)
        raise RuntimeError("captured clean-environment input")
    monkeypatch.setattr(acceptance, "run", run)
    with pytest.raises(RuntimeError, match="captured clean-environment input"):
        acceptance.suite(tmp_path / "python", tmp_path, "ledger-default-source", [], [], False)


def test_import_finder_fails_before_outside_runtime_is_executed(tmp_path, monkeypatch):
    class Outside:
        def find_spec(self, fullname, path, target):
            return importlib.util.spec_from_file_location(fullname, tmp_path / "outside.py")
    finder = gate.OriginFinder(tmp_path / "venv", {})
    monkeypatch.setattr(gate.sys, "meta_path", [finder, Outside()])
    with pytest.raises(RuntimeError, match="import-origin"):
        finder.find_spec("guard.synthetic_outside")
    assert finder.violations  # stays fatal even if an importing caller catches the exception


def test_scope_rejects_unreviewed_runtime_or_protected_fixture():
    for path in ["governance_ledger/customer_policy.py", "tests/fixtures/replacement.json"]:
        with pytest.raises(RuntimeError, match="scope drift"):
            gate.validate_scope([path], gate.LEDGER_RUNTIME | gate.NEW_FILES)


@pytest.mark.parametrize("status", ["failed", "skipped"])
def test_required_failure_or_skip_blocks_result(status):
    with pytest.raises(RuntimeError):
        gate.validate_cases(["tests/test_gate.py::test_gate"],
            {"tests/test_gate.py::test_gate": {"status": status, "reason": "unexpected"}},
            ["tests/test_gate.py::test_gate"], "guard-pair-installed", "Linux")


def test_uncollected_and_unreported_required_cases_block_result():
    with pytest.raises(RuntimeError, match="missing required"):
        gate.validate_cases(["a"], {"a": {"status": "passed"}}, ["missing"], "candidate", "Linux")
    with pytest.raises(RuntimeError, match="missing collected"):
        gate.validate_cases(["a", "b"], {"a": {"status": "passed"}}, [], "candidate", "Linux")


def test_matrix_requires_all_33_real_cases():
    node = "tests/test_v2_affirmative_path_grant.py::test_33_evaluation_historical_producer_matrix[x]"
    with pytest.raises(RuntimeError, match="33-evaluation"):
        gate.validate_cases([node], {node: {"status": "passed"}}, [], "guard-pair-installed", "Linux")


@pytest.mark.parametrize("change", ["head", "scope", "status", "lane", "promotion"])
def test_wrong_head_historical_or_incomplete_report_cannot_pass(change):
    result = dict(scope="legacy-v2-deny-only-containment", status="passed", ledger_head="ledger",
        guard_head="guard", required_lanes=gate.LANES, passed_lanes=list(gate.LANES),
        release_ready=False, runtime_activation_ready=False, historical_certification="not claimed")
    gate.validate_result(result, "ledger", "guard")
    if change == "head":
        result["ledger_head"] = "old"
    elif change == "scope":
        result = {"gates": {"base": "passed"}, "status": "passed"}
    elif change == "status":
        result["status"] = "incomplete"
    elif change == "lane":
        result["passed_lanes"] = []
    else:
        result["release_ready"] = True
    with pytest.raises(RuntimeError):
        gate.validate_result(result, "ledger", "guard")


def test_pr_head_movement_is_a_hard_failure(tmp_path, monkeypatch):
    acceptance = gate.Acceptance(tmp_path / "evidence")
    def git(root, label, *args):
        if args[0] == "rev-parse":
            return "a" * 40
        if args[0] == "ls-remote":
            return "b" * 40 + "\trefs/pull/27/head"
        return ""
    monkeypatch.setattr(acceptance, "git", git)
    with pytest.raises(RuntimeError, match="PR moved"):
        acceptance.heads(tmp_path, "a" * 40)
    assert json.loads((tmp_path / "evidence/containment-acceptance.json").read_text())["status"] == "incomplete"


def test_named_manifest_is_fully_documented():
    doc = (Path(__file__).parents[1] / "docs/DENY_ONLY_CONTAINMENT_ACCEPTANCE.md").read_text(encoding="utf-8")
    for node in gate.named_nodes(gate.LEDGER_REQUIRED) + gate.named_nodes(gate.GUARD_REQUIRED) + gate.ACTION_REQUIRED:
        assert node in doc, node


@pytest.mark.parametrize("fault", ["missing", "duplicate", "wrong_head", "failed", "old_certificate"])
def test_matrix_aggregation_cannot_hide_a_missing_or_failed_cell(tmp_path, fault):
    for index, (system, python) in enumerate((s, p) for s in ("Linux", "Windows") for p in ("3.10", "3.14")):
        if fault == "missing" and index == 3:
            continue
        cell = dict(scope="legacy-v2-deny-only-containment", report_kind="cell", status="passed",
            ledger_head="a" * 40, guard_head=gate.GUARD_HEAD, system=system, python=python,
            matrix_complete=False, required_lanes=gate.LANES, passed_lanes=gate.LANES,
            release_ready=False, runtime_activation_ready=False, historical_certification="not claimed")
        if index == 3:
            if fault == "duplicate":
                cell.update(system="Linux", python="3.10")
            elif fault == "wrong_head":
                cell["ledger_head"] = "b" * 40
            elif fault == "failed":
                cell["status"] = "failed"
            elif fault == "old_certificate":
                cell = {"gates": {"base": "passed"}}
        folder = tmp_path / str(index)
        folder.mkdir()
        gate.write(folder / "containment-acceptance.json", cell)
    output = tmp_path / "matrix.json"
    with pytest.raises(RuntimeError):
        gate.aggregate(tmp_path, "a" * 40, output)
    assert json.loads(output.read_text())["status"] == "failed"
