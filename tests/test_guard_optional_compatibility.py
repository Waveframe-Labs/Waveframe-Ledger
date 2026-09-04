from __future__ import annotations

import copy
import importlib.metadata

import pytest

from governance_ledger.replay import replay_admissibility


waveframe_guard = pytest.importorskip("waveframe_guard")


def test_released_guard_integration_preserves_allowed_and_blocked_replay() -> None:
    version = importlib.metadata.version("waveframe-guard")
    assert version == "0.16.1"
    authority_contract = _authority_contract()
    blocked_state = _execution_state(approvals=[])
    allowed_state = _execution_state(
        approvals=[{"role": "manager", "approved_by": "manager-1"}]
    )
    inputs_before = copy.deepcopy(
        [authority_contract, blocked_state, allowed_state]
    )

    blocked = replay_admissibility(
        authority_contract=authority_contract,
        execution_state=blocked_state,
    )
    allowed = replay_admissibility(
        authority_contract=authority_contract,
        execution_state=allowed_state,
    )

    assert blocked["decision"] == "BLOCKED"
    assert blocked["reason"] == "required approval missing: manager"
    assert blocked["missing_approvals"] == [
        {
            "role": "manager",
            "condition": {
                "field": "amount",
                "operator": ">",
                "value": 1_000_000,
            },
        }
    ]
    assert allowed["decision"] == "ALLOWED"
    assert allowed["reason"] == "approval evidence satisfied"
    assert allowed["missing_approvals"] == []
    assert [authority_contract, blocked_state, allowed_state] == inputs_before


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
