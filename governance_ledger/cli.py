"""Command-line interface for Governance-Ledger operational workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from governance_ledger.publish import approve_review_file, publish_review_file
from governance_ledger.runner import run_policy_directory
from governance_ledger.checks import check_validation_directory, format_check_summary
from governance_ledger.inspect import (
    format_artifact,
    format_contract_list,
    list_contracts,
    show_artifact,
)
from governance_ledger.replay import (
    replay_admissibility,
    replay_governance_compilation,
    verify_authority_lineage,
)
from governance_ledger.semantics.diff import (
    build_authority_diff_impact,
    format_authority_diff_impact,
)
from governance_ledger.semantics.packets import (
    build_governance_review_packet,
    format_governance_review_packet,
)
from governance_ledger.semantics.preview import (
    build_governance_impact_preview,
    format_governance_impact_preview,
)
from governance_ledger.semantics.publication import (
    build_authority_bundle,
    format_authority_bundle,
)
from governance_ledger.summary import (
    build_pr_summary,
    format_publish_summary,
    format_run_summary,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="governance-ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="generate draft governance artifacts")
    run_parser.add_argument("policies_dir")
    run_parser.add_argument("--generated-dir", default="generated")
    run_parser.add_argument("--reviews-dir", default="reviews")
    run_parser.add_argument("--json", action="store_true")
    run_parser.add_argument("--pr-summary")

    approve_parser = subparsers.add_parser("approve", help="approve a review artifact")
    approve_parser.add_argument("review_path")
    approve_parser.add_argument("--actor", required=True)
    approve_parser.add_argument("--timestamp")
    approve_parser.add_argument("--note")
    approve_parser.add_argument("--json", action="store_true")

    publish_parser = subparsers.add_parser("publish", help="publish an approved review")
    publish_parser.add_argument("review_path")
    publish_parser.add_argument("--generated-dir", default="generated")
    publish_parser.add_argument("--contracts-dir", default="contracts")
    publish_parser.add_argument("--reviews-dir", default="reviews")
    publish_parser.add_argument("--snapshots-dir", default="snapshots")
    publish_parser.add_argument("--actor", default="governance-team")
    publish_parser.add_argument("--compiler-actor", default="compiler-service")
    publish_parser.add_argument("--deployed-by", default="ops-team")
    publish_parser.add_argument("--environment", default="production")
    publish_parser.add_argument("--runtime", default="waveframe-guard")
    publish_parser.add_argument("--enforcement-engine-version", default="0.12.0")
    publish_parser.add_argument("--timestamp")
    publish_parser.add_argument("--json", action="store_true")

    check_parser = subparsers.add_parser("check", help="check generated validation artifacts")
    check_parser.add_argument("generated_dir")
    check_parser.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list", help="list governance registry artifacts")
    list_parser.add_argument("kind", choices=["contracts"])
    list_parser.add_argument("--contracts-dir", default="contracts")
    list_parser.add_argument("--json", action="store_true")

    show_parser = subparsers.add_parser("show", help="show a governance artifact")
    show_parser.add_argument("path")
    show_parser.add_argument("--json", action="store_true")

    preview_parser = subparsers.add_parser(
        "preview",
        help="derive governance_impact_preview.v1 from an authority contract",
    )
    preview_parser.add_argument("contract")
    preview_parser.add_argument("--output")
    preview_parser.add_argument("--json", action="store_true")

    diff_impact_parser = subparsers.add_parser(
        "diff-impact",
        help="derive authority_diff_impact.v1 from old and new authority contracts",
    )
    diff_impact_parser.add_argument("--old", required=True)
    diff_impact_parser.add_argument("--new", required=True)
    diff_impact_parser.add_argument("--output")
    diff_impact_parser.add_argument("--json", action="store_true")

    review_packet_parser = subparsers.add_parser(
        "review-packet",
        help="derive governance_review_packet.v1 from semantic governance artifacts",
    )
    review_packet_parser.add_argument("--authority", required=True)
    review_packet_parser.add_argument("--preview", required=True)
    review_packet_parser.add_argument("--diff")
    review_packet_parser.add_argument("--execution-evidence")
    review_packet_parser.add_argument("--review-metadata")
    review_packet_parser.add_argument("--output")
    review_packet_parser.add_argument("--json", action="store_true")

    authority_bundle_parser = subparsers.add_parser(
        "authority-bundle",
        help="derive authority_bundle.v1 from published governance artifacts",
    )
    authority_bundle_parser.add_argument("--authority", required=True)
    authority_bundle_parser.add_argument("--manifest", required=True)
    authority_bundle_parser.add_argument("--preview", required=True)
    authority_bundle_parser.add_argument("--diff")
    authority_bundle_parser.add_argument("--review-packet", action="append", default=[])
    authority_bundle_parser.add_argument("--output")
    authority_bundle_parser.add_argument("--json", action="store_true")

    replay_authority_parser = subparsers.add_parser(
        "replay-authority",
        help="replay governance source into compilation report and authority contract",
    )
    replay_authority_parser.add_argument("--source", required=True)
    replay_authority_parser.add_argument("--report")
    replay_authority_parser.add_argument("--contract")
    replay_authority_parser.add_argument("--json", action="store_true")

    replay_execution_parser = subparsers.add_parser(
        "replay-execution",
        help="replay deterministic admissibility from authority contract and execution state",
    )
    replay_execution_parser.add_argument("--contract", required=True)
    replay_execution_parser.add_argument("--execution-state", required=True)
    replay_execution_parser.add_argument("--json", action="store_true")

    verify_lineage_parser = subparsers.add_parser(
        "verify-lineage",
        help="verify authority provenance lineage against an optional compilation report",
    )
    verify_lineage_parser.add_argument("--contract", required=True)
    verify_lineage_parser.add_argument("--report")
    verify_lineage_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_policy_directory(
            args.policies_dir,
            generated_dir=args.generated_dir,
            reviews_dir=args.reviews_dir,
        )
        if args.pr_summary:
            Path(args.pr_summary).write_text(
                "\n\n".join(
                    build_pr_summary(
                        json.loads(Path(item["review"]).read_text(encoding="utf-8")),
                        policy_name=Path(item["policy"]).name,
                    )
                    for item in result
                )
                + "\n",
                encoding="utf-8",
            )
    elif args.command == "approve":
        result = approve_review_file(
            args.review_path,
            actor=args.actor,
            timestamp=args.timestamp,
            note=args.note,
        )
    elif args.command == "publish":
        result = publish_review_file(
            args.review_path,
            generated_dir=args.generated_dir,
            contracts_dir=args.contracts_dir,
            reviews_dir=args.reviews_dir,
            snapshots_dir=args.snapshots_dir,
            actor=args.actor,
            compiler_actor=args.compiler_actor,
            deployed_by=args.deployed_by,
            environment=args.environment,
            runtime=args.runtime,
            enforcement_engine_version=args.enforcement_engine_version,
            timestamp=args.timestamp,
        )
    elif args.command == "check":
        result = check_validation_directory(args.generated_dir)
    elif args.command == "list":
        result = list_contracts(args.contracts_dir)
    elif args.command == "replay-authority":
        result = replay_governance_compilation(
            source_text=Path(args.source).read_text(encoding="utf-8"),
            expected_report=_read_json_arg(args.report),
            expected_contract=_read_json_arg(args.contract),
        )
    elif args.command == "replay-execution":
        result = replay_admissibility(
            authority_contract=_read_json_arg(args.contract),
            execution_state=_read_json_arg(args.execution_state),
        )
    elif args.command == "verify-lineage":
        result = verify_authority_lineage(
            authority_contract=_read_json_arg(args.contract),
            compilation_report=_read_json_arg(args.report),
        )
    elif args.command == "preview":
        result = build_governance_impact_preview(_read_json_arg(args.contract) or {})
        if args.output:
            Path(args.output).write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    elif args.command == "diff-impact":
        result = build_authority_diff_impact(
            _read_json_arg(args.old) or {},
            _read_json_arg(args.new) or {},
        )
        if args.output:
            Path(args.output).write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    elif args.command == "review-packet":
        result = build_governance_review_packet(
            authority_contract=_read_json_arg(args.authority) or {},
            governance_impact_preview=_read_json_arg(args.preview) or {},
            authority_diff_impact=_read_json_arg(args.diff),
            execution_evidence=_read_json_arg(args.execution_evidence),
            review_metadata=_read_json_arg(args.review_metadata),
        )
        if args.output:
            Path(args.output).write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    elif args.command == "authority-bundle":
        result = build_authority_bundle(
            authority_contract=_read_json_arg(args.authority) or {},
            publication_manifest=_read_json_arg(args.manifest) or {},
            governance_impact_preview=_read_json_arg(args.preview) or {},
            authority_diff_impact=_read_json_arg(args.diff),
            governance_review_packets=[
                _read_json_arg(packet_path) or {}
                for packet_path in args.review_packet
            ],
        )
        if args.output:
            Path(args.output).write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    else:
        result = show_artifact(args.path)

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.command in {"replay-authority", "replay-execution", "verify-lineage"}:
            return 0 if _replay_ok(result) else 1
    elif args.command == "run":
        print(format_run_summary(result))
    elif args.command == "publish":
        print(format_publish_summary(result))
    elif args.command == "check":
        print(format_check_summary(result))
        return 1 if result["error_count"] else 0
    elif args.command == "list":
        print(format_contract_list(result))
    elif args.command == "show":
        print(format_artifact(args.path, result))
    elif args.command == "preview":
        print(format_governance_impact_preview(result))
    elif args.command == "diff-impact":
        print(format_authority_diff_impact(result))
    elif args.command == "review-packet":
        print(format_governance_review_packet(result))
    elif args.command == "authority-bundle":
        print(format_authority_bundle(result))
    elif args.command in {"replay-authority", "replay-execution", "verify-lineage"}:
        print(_format_replay_summary(result))
        return 0 if _replay_ok(result) else 1
    else:
        print(
            "\n".join(
                [
                    "[Governance Ledger]",
                    "",
                    "Review:",
                    f"  {result['review_id']} approved",
                    "",
                    "Status:",
                    f"  {result['review_status']}",
                ]
            )
        )
    return 0


def _read_json_arg(path: str | None) -> dict | None:
    if path is None:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _replay_ok(result: dict) -> bool:
    if "replay_verified" in result:
        return bool(result["replay_verified"])
    if "lineage_verified" in result:
        return bool(result["lineage_verified"])
    return not result.get("diagnostics")


def _format_replay_summary(result: dict) -> str:
    status = "VERIFIED" if _replay_ok(result) else "FAILED"
    lines = [
        "[Governance Replay]",
        "",
        f"Status: {status}",
    ]
    if result.get("authority_ref"):
        lines.append(f"Authority: {result['authority_ref']}")
    if result.get("contract_hash"):
        lines.append(f"Contract hash: {result['contract_hash']}")
    diagnostics = result.get("diagnostics") or []
    if diagnostics:
        lines.extend(["", "Diagnostics:"])
        lines.extend(f"  {item['text']}" for item in diagnostics)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
