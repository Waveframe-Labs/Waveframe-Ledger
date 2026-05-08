import json
import sys
import types

from governance_authoring.extract import extract_constraints


def test_extracts_v01_constraints_from_policy_text():
    policy_text = """
    Only managers may approve transfers.
    Proposer and approver must be separate.
    Transfers above $1M require approval.
    """

    policy = extract_constraints(policy_text)

    assert policy == {
        "contract_id": "finance-policy",
        "contract_version": "0.1.0",
        "authority": {
            "required_roles": ["managers"],
        },
        "approvals": {
            "thresholds": {
                "transfer_funds": 1_000_000,
            },
        },
        "invariants": {
            "separation_of_duties": True,
        },
    }


def test_preserves_role_text_without_singularization():
    policy = extract_constraints("Only compliance may approve transfers.")

    assert policy["authority"]["required_roles"] == ["compliance"]


def test_builds_contract_files_from_policy_text(tmp_path):
    compiler_module = types.ModuleType("compiler")
    compile_policy_module = types.ModuleType("compiler.compile_policy")

    def canonical_compile_policy(policy):
        return {
            "compiled_by": "canonical-compiler",
            "policy": policy,
        }

    compile_policy_module.compile_policy = canonical_compile_policy
    sys.modules["compiler"] = compiler_module
    sys.modules["compiler.compile_policy"] = compile_policy_module

    from governance_authoring.pipeline import build_contract_files

    policy_path = tmp_path / "policy.txt"
    structured_policy_path = tmp_path / "structured_policy.json"
    compiled_contract_path = tmp_path / "compiled_contract.json"
    policy_path.write_text(
        "Only managers may approve transfers. "
        "Proposer and approver must be separate. "
        "Transfers above $1M require approval.",
        encoding="utf-8",
    )

    contract = build_contract_files(
        policy_path,
        structured_policy_path,
        compiled_contract_path,
    )

    structured_policy = json.loads(structured_policy_path.read_text(encoding="utf-8"))
    compiled_contract = json.loads(compiled_contract_path.read_text(encoding="utf-8"))

    assert structured_policy["authority"]["required_roles"] == ["managers"]
    assert structured_policy["invariants"]["separation_of_duties"] is True
    assert compiled_contract == contract
    assert compiled_contract["compiled_by"] == "canonical-compiler"
    assert compiled_contract["policy"] == structured_policy
