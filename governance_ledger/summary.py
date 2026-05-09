"""Human-readable summaries for Governance-Ledger operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def format_run_summary(results: list[dict[str, Any]]) -> str:
    """Format draft-generation output for terminal visibility."""
    sections = ["[Governance Ledger]"]
    for result in results:
        policy_name = Path(result["policy"]).name
        constraint_count = result.get("constraint_count", 0)
        warning_count = result.get("warning_count", 0)
        ambiguity_count = result.get("ambiguity_count", 0)

        sections.append(
            "\n".join(
                [
                    "",
                    f"Policy: {policy_name}",
                    "",
                    "Extraction:",
                    f"  {constraint_count} constraints detected",
                    "",
                    "Warnings:",
                    f"  {warning_count} warnings detected",
                    f"  {ambiguity_count} ambiguity warnings detected",
                    "",
                    "Review:",
                    f"  {result.get('review_id')} {_review_action(result)}",
                    "",
                    "Status:",
                    f"  {_status_message(result)}",
                ]
            )
        )
    return "\n".join(sections)


def _review_action(result: dict[str, Any]) -> str:
    return "created" if result.get("review_created") else "preserved"


def _status_message(result: dict[str, Any]) -> str:
    status = result.get("review_status")
    if status == "pending":
        return "pending human approval"
    return str(status)


def format_publish_summary(result: dict[str, str]) -> str:
    """Format publish output for terminal visibility."""
    return "\n".join(
        [
            "[Governance Ledger]",
            "",
            "Publication:",
            "  published approved governance review",
            "",
            "Contract:",
            f"  {result['contract']}",
            "",
            "Review:",
            f"  {result['deployed_review']}",
            "",
            "Manifest:",
            f"  {result['manifest']}",
            "",
            "Snapshot:",
            f"  {result['snapshot']}",
        ]
    )


def build_pr_summary(
    review: dict[str, Any],
    *,
    policy_name: str | None = None,
    publication_status: str | None = None,
) -> str:
    """Build a Markdown governance review summary suitable for PR comments."""
    policy = policy_name or review.get("source_document") or "unknown"
    status = publication_status or _publication_status(review)
    lines = [
        "## Governance Review Summary",
        "",
        f"Policy: {policy}",
        "",
        "Constraints Extracted:",
    ]

    constraints = review.get("detected_constraints", [])
    if constraints:
        lines.extend(f"- {_format_constraint(constraint)}" for constraint in constraints)
    else:
        lines.append("- none")

    lines.extend(["", "Warnings:"])
    warnings = review.get("warnings", [])
    if warnings:
        lines.extend(f"- {_format_warning(warning)}" for warning in warnings)
    else:
        lines.append("- none")

    lines.extend(["", "Publication Status:", status])
    return "\n".join(lines)


def _publication_status(review: dict[str, Any]) -> str:
    status = review.get("review_status")
    if status == "deployed":
        return "PUBLISHED"
    if status == "approved":
        return "READY_TO_PUBLISH"
    if status in {"pending", "reviewed"}:
        return "BLOCKED_PENDING_REVIEW"
    if status == "rejected":
        return "BLOCKED_REJECTED"
    return "UNKNOWN"


def _format_constraint(constraint: dict[str, Any]) -> str:
    constraint_type = constraint.get("type")
    if constraint_type == "required_role":
        return f"required_role: {constraint.get('value')}"
    if constraint_type == "approval_threshold":
        return f"threshold: {constraint.get('operation')} > {constraint.get('value')}"
    if constraint_type == "separation_of_duties":
        return "separation_of_duties"
    return str(constraint_type)


def _format_warning(warning: dict[str, Any]) -> str:
    warning_type = warning.get("type")
    severity = warning.get("severity", "warning")
    text = warning.get("text")
    if warning_type == "ambiguous_authority":
        return f'{severity}: ambiguous clause: "{text}"'
    if warning_type == "unsupported_constraint":
        return f'{severity}: unsupported constraint: "{text}"'
    if warning_type == "extraction_gap":
        return f'{severity}: extraction gap: "{text}"'
    return f'{severity}: {warning_type}: "{text}"'
