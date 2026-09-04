from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess
import sys
import venv
import zipfile

import pytest

from governance_ledger.extract import extract_constraints
from governance_ledger.integrations.guard import GuardIntegrationUnavailableError
from governance_ledger.replay import replay_admissibility, replay_governance_compilation
from governance_ledger.review import build_review_report


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def built_ledger_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    wheel_dir = tmp_path_factory.mktemp("ledger-wheel")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(wheel_dir.glob("governance_ledger-*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_built_wheel_has_guard_only_in_the_explicit_optional_extra(
    built_ledger_wheel: Path,
) -> None:
    with zipfile.ZipFile(built_ledger_wheel) as archive:
        metadata_name = next(
            name
            for name in archive.namelist()
            if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode("utf-8")
    guard_requirements = [
        line
        for line in metadata.splitlines()
        if line.lower().startswith("requires-dist: waveframe-guard")
    ]

    assert len(guard_requirements) == 1
    assert "extra == \"guard\"" in guard_requirements[0]
    assert "==0.16.1" in guard_requirements[0]
    assert not any(
        line.lower().startswith("requires-dist: waveframe-guard")
        and "extra ==" not in line
        for line in metadata.splitlines()
    )


def test_clean_environment_installs_and_runs_core_without_guard(
    built_ledger_wheel: Path,
    tmp_path: Path,
) -> None:
    environment = tmp_path / "clean-environment"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            str(built_ledger_wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    smoke = subprocess.run(
        [str(python), "-c", _CLEAN_ENVIRONMENT_SMOKE],
        check=True,
        capture_output=True,
        text=True,
    )

    assert smoke.stdout.strip() == "ledger-core-without-guard: ok"


def test_importing_all_ledger_modules_does_not_import_guard() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_BOUNDARY_SMOKE],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "ledger-import-boundary: ok"


def test_injected_evaluator_replay_is_deterministic_and_non_mutating(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "waveframe_guard", None)
    authority_contract = _authority_contract()
    execution_state = _execution_state(approvals=[])
    original_contract = copy.deepcopy(authority_contract)
    original_execution_state = copy.deepcopy(execution_state)

    def evaluator(contract: dict, state: dict) -> dict:
        contract["evaluator_mutation"] = True
        state["evaluator_mutation"] = True
        return {
            "allowed": False,
            "reason": "injected evaluator blocked execution",
            "missing_approvals": [{"role": "manager"}],
            "trace": {"evaluator": "injected"},
        }

    first = replay_admissibility(
        authority_contract=authority_contract,
        execution_state=execution_state,
        evaluator=evaluator,
    )
    second = replay_admissibility(
        authority_contract=authority_contract,
        execution_state=execution_state,
        evaluator=evaluator,
    )

    assert first == second
    assert first["decision"] == "BLOCKED"
    assert first["decision_trace"] == {"evaluator": "injected"}
    assert authority_contract == original_contract
    assert execution_state == original_execution_state
    assert sys.modules["waveframe_guard"] is None


def test_missing_evaluator_and_guard_raises_actionable_ledger_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "waveframe_guard", None)

    with pytest.raises(
        GuardIntegrationUnavailableError,
        match=r'pip install "governance-ledger\[guard\]"',
    ) as caught:
        replay_admissibility(
            authority_contract=_authority_contract(),
            execution_state=_execution_state(approvals=[]),
        )
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


def test_authority_replay_remains_guard_independent(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "waveframe_guard", None)
    source = "Transfers above $1000000 require manager approval."
    policy = extract_constraints(source)
    review = build_review_report(source, policy)

    replay = replay_governance_compilation(
        source_text=source,
        expected_report=review["compilation_report"],
    )

    assert replay["replay_verified"] is True
    assert sys.modules["waveframe_guard"] is None


def _authority_contract() -> dict:
    return {
        "schema_version": "compiled_authority_contract.v1",
        "contract_id": "finance-policy",
        "contract_version": "0.1.0",
        "contract_hash": "sha256:contract",
        "lineage": {
            "schema_version": "governance_authority_lineage.v1",
            "source_hash": "sha256:source",
            "compilation_report_hash": "sha256:report",
        },
        "approval_requirements": {
            "required": [
                {
                    "role": "manager",
                    "condition": {
                        "field": "amount",
                        "operator": ">",
                        "value": 1_000_000,
                    },
                }
            ]
        },
    }


def _execution_state(*, approvals: list[dict]) -> dict:
    return {
        "schema_version": "governed_execution_state.v1",
        "authority_ref": "finance-policy@0.1.0",
        "source_hash": "sha256:source",
        "compilation_report_hash": "sha256:report",
        "actor": {"id": "employee-1", "type": "human", "role": "employee"},
        "approvals": approvals,
        "action": "transfer",
        "target": "transfer",
        "arguments": {"amount": 1_250_000},
        "artifacts": [],
    }


_IMPORT_BOUNDARY_SMOKE = r"""
import importlib
import pkgutil
import sys

import governance_ledger

for module in pkgutil.walk_packages(
    governance_ledger.__path__,
    prefix="governance_ledger.",
):
    importlib.import_module(module.name)

assert not any(
    name == "waveframe_guard" or name.startswith("waveframe_guard.")
    for name in sys.modules
)
print("ledger-import-boundary: ok")
"""


_CLEAN_ENVIRONMENT_SMOKE = r"""
import copy
import importlib.metadata
import sys

try:
    importlib.metadata.version("waveframe-guard")
except importlib.metadata.PackageNotFoundError:
    pass
else:
    raise AssertionError("waveframe-guard distribution must be absent")

import governance_ledger
from governance_ledger.extract import extract_constraints
from governance_ledger.lifecycle import transition_review_status
from governance_ledger.replay import (
    replay_admissibility,
    replay_governance_compilation,
    verify_authority_lineage,
)
from governance_ledger.review import build_review_report
from governance_ledger.semantics.compiler import compile_semantic_commit_bundle
from governance_ledger.validation import validate_authoring

assert "waveframe_guard" not in sys.modules
source = "Transfers above $1000000 require manager approval."
policy = extract_constraints(source)
review = build_review_report(source, policy)
assert not any(
    warning.get("severity") == "error"
    for warning in validate_authoring(source, policy)["warnings"]
)
review = transition_review_status(review, "reviewed", actor="governance-team")
review = transition_review_status(review, "approved", actor="governance-team")
assert review["review_status"] == "approved"
assert replay_governance_compilation(
    source_text=source,
    expected_report=review["compilation_report"],
)["replay_verified"] is True

semantic_commit = {
    "schema_version": "semantic_commit_bundle.v1",
    "source_hash": review["source_hash"],
    "semantic_commit_id": "semantic-clean-environment",
    "semantic_commit_hash": "sha256:semantic",
    "resolved_interpretations": [],
    "committed_semantic_meaning": {
        "contract_id": "clean-environment-policy",
        "contract_version": "1.0.0",
        "confirmed_rules": [],
    },
}
compiled = compile_semantic_commit_bundle(semantic_commit)
lineage = {
    "schema_version": "governance_authority_lineage.v1",
    "source_hash": review["source_hash"],
    "compilation_report_hash": review["compilation_report"]["report_hash"],
}
authority = {**compiled, "lineage": lineage}
before = copy.deepcopy(authority)

def evaluator(contract, execution_state):
    contract["changed"] = True
    execution_state["changed"] = True
    return {
        "allowed": True,
        "reason": "injected evaluator allowed execution",
        "missing_approvals": [],
        "trace": {"evaluator": "clean-environment"},
    }

execution_state = {
    "authority_ref": compiled["authority_ref"],
    "source_hash": lineage["source_hash"],
    "compilation_report_hash": lineage["compilation_report_hash"],
}
replay = replay_admissibility(
    authority_contract=authority,
    execution_state=execution_state,
    evaluator=evaluator,
)
assert replay["allowed"] is True
assert authority == before
assert verify_authority_lineage(authority_contract=authority)["lineage_verified"] is True
assert "waveframe_guard" not in sys.modules
print("ledger-core-without-guard: ok")
"""
