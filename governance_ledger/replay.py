from __future__ import annotations

import copy
from typing import Any

from governance_ledger.authority_contract import with_authority_identity
from governance_ledger.diagnostics import build_diagnostic
from governance_ledger.extract import extract_constraints
from governance_ledger.provenance import source_governance_identity
from governance_ledger.review import build_review_report


def replay_governance_compilation(
    *,
    source_text: str,
    expected_report: dict[str, Any] | None = None,
    expected_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = extract_constraints(source_text)
    review = build_review_report(source_text, policy)
    compiled_contract = _compile_policy(
        policy,
        lineage=_expected_lineage(expected_contract),
        schema_version=_expected_schema_version(expected_contract),
    )
    report = review["compilation_report"]
    source_identity = source_governance_identity(source_text)
    diagnostics: list[dict[str, Any]] = []

    checks = {
        "source_hash_match": True,
        "report_hash_match": True,
        "contract_hash_match": True,
        "authority_source_hash_match": True,
        "authority_compilation_report_hash_match": True,
        "authority_provenance_chain_present": True,
    }
    if expected_report is not None:
        checks["source_hash_match"] = (
            expected_report.get("source_hash")
            == source_identity["source_hash"]
        )
        checks["report_hash_match"] = (
            expected_report.get("report_hash")
            == report.get("report_hash")
        )
        if not checks["report_hash_match"]:
            diagnostics.append(_compilation_report_hash_mismatch(expected_report, report))
    if expected_contract is not None:
        checks["contract_hash_match"] = (
            expected_contract.get("contract_hash")
            == compiled_contract.get("contract_hash")
        )
        lineage = expected_contract.get("lineage") if isinstance(expected_contract.get("lineage"), dict) else {}
        checks["authority_provenance_chain_present"] = _lineage_complete(lineage)
        if not checks["authority_provenance_chain_present"]:
            diagnostics.append(_missing_provenance_chain())
        if expected_report is not None and lineage:
            checks["authority_source_hash_match"] = (
                lineage.get("source_hash") == expected_report.get("source_hash")
            )
            checks["authority_compilation_report_hash_match"] = (
                lineage.get("compilation_report_hash") == expected_report.get("report_hash")
            )
            if not checks["authority_source_hash_match"]:
                diagnostics.append(_authority_source_hash_mismatch(lineage, expected_report))
            if not checks["authority_compilation_report_hash_match"]:
                diagnostics.append(_authority_compilation_report_hash_mismatch(lineage, expected_report))

    return {
        "schema_version": "governance_replay_result.v1",
        "source_governance": source_identity,
        "compilation_report": report,
        "compiled_contract": compiled_contract,
        "diagnostics": diagnostics,
        "checks": checks,
        "replay_verified": all(checks.values()),
    }


def replay_admissibility(
    *,
    authority_contract: dict[str, Any],
    execution_state: dict[str, Any],
) -> dict[str, Any]:
    from waveframe_guard import evaluate_admissibility

    diagnostics = []
    lineage = authority_contract.get("lineage") if isinstance(authority_contract.get("lineage"), dict) else {}
    lineage_complete = _lineage_complete(lineage)
    if not lineage_complete:
        diagnostics.append(_missing_provenance_chain())
    if lineage.get("source_hash") and execution_state.get("source_hash"):
        if lineage["source_hash"] != execution_state["source_hash"]:
            diagnostics.append(_execution_source_hash_mismatch(lineage, execution_state))
            lineage_complete = False
    if lineage.get("compilation_report_hash") and execution_state.get("compilation_report_hash"):
        if lineage["compilation_report_hash"] != execution_state["compilation_report_hash"]:
            diagnostics.append(_execution_compilation_report_hash_mismatch(lineage, execution_state))
            lineage_complete = False

    decision = evaluate_admissibility(copy.deepcopy(authority_contract), copy.deepcopy(execution_state))
    return {
        "schema_version": "governance_replay_admissibility.v1",
        "authority_ref": execution_state.get("authority_ref"),
        "contract_hash": authority_contract.get("contract_hash"),
        "source_hash": lineage.get("source_hash"),
        "compilation_report_hash": lineage.get("compilation_report_hash"),
        "decision": "ALLOWED" if decision["allowed"] else "BLOCKED",
        "allowed": decision["allowed"],
        "reason": decision["reason"],
        "missing_approvals": decision["missing_approvals"],
        "decision_trace": decision.get("trace"),
        "diagnostics": diagnostics,
        "lineage_verified": lineage_complete and not diagnostics,
    }


def verify_authority_lineage(
    *,
    authority_contract: dict[str, Any],
    compilation_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lineage = authority_contract.get("lineage") if isinstance(authority_contract.get("lineage"), dict) else {}
    diagnostics = []
    checks = {
        "authority_provenance_chain_present": _lineage_complete(lineage),
        "authority_source_hash_match": True,
        "authority_compilation_report_hash_match": True,
    }
    if not checks["authority_provenance_chain_present"]:
        diagnostics.append(_missing_provenance_chain())
    if compilation_report is not None and lineage:
        checks["authority_source_hash_match"] = (
            lineage.get("source_hash") == compilation_report.get("source_hash")
        )
        checks["authority_compilation_report_hash_match"] = (
            lineage.get("compilation_report_hash") == compilation_report.get("report_hash")
        )
        if not checks["authority_source_hash_match"]:
            diagnostics.append(_authority_source_hash_mismatch(lineage, compilation_report))
        if not checks["authority_compilation_report_hash_match"]:
            diagnostics.append(_authority_compilation_report_hash_mismatch(lineage, compilation_report))

    return {
        "schema_version": "governance_lineage_verification.v1",
        "authority_ref": _authority_ref(authority_contract),
        "contract_hash": authority_contract.get("contract_hash"),
        "source_hash": lineage.get("source_hash"),
        "compilation_report_hash": lineage.get("compilation_report_hash"),
        "checks": checks,
        "diagnostics": diagnostics,
        "lineage_verified": all(checks.values()) and not diagnostics,
    }


def _expected_lineage(expected_contract: dict[str, Any] | None) -> dict[str, Any] | None:
    if expected_contract is None:
        return None
    lineage = expected_contract.get("lineage")
    return copy.deepcopy(lineage) if isinstance(lineage, dict) else None


def _expected_schema_version(expected_contract: dict[str, Any] | None) -> str | None:
    if expected_contract is None:
        return None
    schema_version = expected_contract.get("schema_version")
    return schema_version if isinstance(schema_version, str) else None


def _compile_policy(
    policy: dict[str, Any],
    *,
    lineage: dict[str, Any] | None = None,
    schema_version: str | None = None,
) -> dict[str, Any]:
    from compiler.compile_policy import compile_policy

    compiler_input = copy.deepcopy(policy)
    if lineage is not None:
        compiler_input["lineage"] = lineage
    compiled_contract = compile_policy(compiler_input)
    if lineage is not None:
        compiled_contract = with_authority_identity(
            compiled_contract,
            lineage,
            schema_version=schema_version,
        )
    return compiled_contract

def _authority_ref(authority_contract: dict[str, Any]) -> str | None:
    contract_id = authority_contract.get("contract_id")
    contract_version = authority_contract.get("contract_version")
    if not contract_id or not contract_version:
        return None
    return f"{contract_id}@{contract_version}"


def _lineage_complete(lineage: dict[str, Any]) -> bool:
    return (
        lineage.get("schema_version") == "governance_authority_lineage.v1"
        and isinstance(lineage.get("source_hash"), str)
        and bool(lineage["source_hash"])
        and isinstance(lineage.get("compilation_report_hash"), str)
        and bool(lineage["compilation_report_hash"])
    )


def _authority_source_hash_mismatch(
    lineage: dict[str, Any],
    expected_report: dict[str, Any],
) -> dict[str, Any]:
    return build_diagnostic(
        code="G801",
        severity="error",
        title="Authority source hash does not match compilation report lineage",
        detail=(
            f"Authority source hash {lineage.get('source_hash')} does not match "
            f"compilation report source hash {expected_report.get('source_hash')}."
        ),
        recommendation="Rebuild and republish the authority artifact from the referenced governance source.",
    )


def _compilation_report_hash_mismatch(
    expected_report: dict[str, Any],
    replayed_report: dict[str, Any],
) -> dict[str, Any]:
    return build_diagnostic(
        code="G802",
        severity="error",
        title="Compilation report hash mismatch during replay validation",
        detail=(
            f"Expected report hash {expected_report.get('report_hash')} but replay produced "
            f"{replayed_report.get('report_hash')}."
        ),
        recommendation="Verify the governance source, normalizer version, and compilation report artifact.",
    )


def _authority_compilation_report_hash_mismatch(
    lineage: dict[str, Any],
    expected_report: dict[str, Any],
) -> dict[str, Any]:
    return build_diagnostic(
        code="G802",
        severity="error",
        title="Compilation report hash mismatch during replay validation",
        detail=(
            f"Authority references compilation report hash {lineage.get('compilation_report_hash')} "
            f"but the supplied report hash is {expected_report.get('report_hash')}."
        ),
        recommendation="Verify that the authority artifact was published from the supplied compilation report.",
    )


def _missing_provenance_chain() -> dict[str, Any]:
    return build_diagnostic(
        code="G803",
        severity="error",
        title="Execution evaluated against authority with missing provenance chain",
        detail=(
            "Authority artifact must include governance_authority_lineage.v1 with source_hash "
            "and compilation_report_hash."
        ),
        recommendation="Republish the authority artifact with canonical governance lineage metadata.",
    )


def _execution_source_hash_mismatch(
    lineage: dict[str, Any],
    execution_state: dict[str, Any],
) -> dict[str, Any]:
    return build_diagnostic(
        code="G801",
        severity="error",
        title="Authority source hash does not match execution state lineage",
        detail=(
            f"Authority source hash {lineage.get('source_hash')} does not match "
            f"execution state source hash {execution_state.get('source_hash')}."
        ),
        recommendation="Reject the replay bundle and bind execution state to the exact authority lineage.",
    )


def _execution_compilation_report_hash_mismatch(
    lineage: dict[str, Any],
    execution_state: dict[str, Any],
) -> dict[str, Any]:
    return build_diagnostic(
        code="G802",
        severity="error",
        title="Compilation report hash mismatch during replay validation",
        detail=(
            f"Authority references compilation report hash {lineage.get('compilation_report_hash')} "
            f"but execution state references {execution_state.get('compilation_report_hash')}."
        ),
        recommendation="Reject the replay bundle and verify the authority/report/execution evidence chain.",
    )
