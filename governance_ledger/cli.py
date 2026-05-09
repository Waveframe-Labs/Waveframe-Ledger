"""Command-line interface for Governance-Ledger operational workflows."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from governance_ledger.publish import approve_review_file, publish_review_file
from governance_ledger.runner import run_policy_directory


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="governance-ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="generate draft governance artifacts")
    run_parser.add_argument("policies_dir")
    run_parser.add_argument("--generated-dir", default="generated")
    run_parser.add_argument("--reviews-dir", default="reviews")

    approve_parser = subparsers.add_parser("approve", help="approve a review artifact")
    approve_parser.add_argument("review_path")
    approve_parser.add_argument("--actor", required=True)
    approve_parser.add_argument("--timestamp")
    approve_parser.add_argument("--note")

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

    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_policy_directory(
            args.policies_dir,
            generated_dir=args.generated_dir,
            reviews_dir=args.reviews_dir,
        )
    elif args.command == "approve":
        result = approve_review_file(
            args.review_path,
            actor=args.actor,
            timestamp=args.timestamp,
            note=args.note,
        )
    else:
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

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
