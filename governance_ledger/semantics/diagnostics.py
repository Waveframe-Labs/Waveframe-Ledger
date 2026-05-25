"""Deterministic governance quality diagnostics for authority artifacts."""

from __future__ import annotations

from typing import Any

GOVERNANCE_QUALITY_DIAGNOSTIC_V1 = "governance_quality_diagnostic.v1"


def build_governance_quality_diagnostics(authority_contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Return advisory governance quality diagnostics for an authority contract.

    These diagnostics are quality signals only. They do not reject publication,
    evaluate admissibility, call Guard, or score policy quality.
    """
    authority = authority_contract or {}
    diagnostics: list[dict[str, Any]] = []

    if _missing_escalation_threshold(authority):
        diagnostics.append(
            _diagnostic(
                code="GQ001",
                title="Missing Escalation Path",
                text="High-value or threshold-sensitive authority has no explicit escalation threshold.",
                domain="escalation",
                recommendation="Define the operational threshold where governance review is required.",
                severity="warning",
            )
        )

    continuity = authority.get("continuity_requirements") if isinstance(authority.get("continuity_requirements"), dict) else {}
    if not continuity.get("resume_requires_current_authority"):
        diagnostics.append(
            _diagnostic(
                code="GQ002",
                title="Weak Continuity Posture",
                text="Long-running or resumed workflows do not require continuity revalidation against current authority posture.",
                domain="continuity",
                recommendation="Require resumed workflows to revalidate continuity before execution completes.",
                severity="warning",
            )
        )

    replay_requirements = _strings(authority.get("replay_requirements"))
    if not {"authority_hash", "decision_trace"}.issubset(set(replay_requirements)):
        diagnostics.append(
            _diagnostic(
                code="GQ003",
                title="Replay Weakness",
                text="Authority does not describe enough replay continuity expectations for future evidence binding.",
                domain="replay",
                recommendation="Include authority_hash and decision_trace in replay requirements.",
                severity="warning",
            )
        )

    approval_count = _approval_count(authority)
    roles = _required_roles(authority)
    if approval_count <= 1 or len(set(roles)) <= 1:
        diagnostics.append(
            _diagnostic(
                code="GQ004",
                title="Approval Risk",
                text="Single-role approval model may concentrate execution authority.",
                domain="approval",
                recommendation="Consider independent approval count or distinct approval roles for high-impact actions.",
                severity="info",
            )
        )

    if not _defines_supersession(authority):
        diagnostics.append(
            _diagnostic(
                code="GQ005",
                title="Lifecycle Ambiguity",
                text="Authority does not define supersession expectations for future lifecycle changes.",
                domain="lifecycle",
                recommendation="Describe how successor authority versions supersede this authority.",
                severity="info",
            )
        )

    return diagnostics


def _diagnostic(
    *,
    code: str,
    title: str,
    text: str,
    domain: str,
    recommendation: str,
    severity: str,
) -> dict[str, Any]:
    return {
        "schema_version": GOVERNANCE_QUALITY_DIAGNOSTIC_V1,
        "type": "governance_quality_diagnostic",
        "code": code,
        "title": title,
        "text": text,
        "severity": severity,
        "domain": domain,
        "recommendation": recommendation,
        "blocks_publication": False,
        "non_goals": [
            "does_not_reject_publication",
            "does_not_evaluate_admissibility",
            "does_not_call_guard",
            "does_not_call_cloud",
            "does_not_score_policy",
        ],
    }


def _missing_escalation_threshold(authority: dict[str, Any]) -> bool:
    escalation = authority.get("escalation_requirements")
    if not isinstance(escalation, dict):
        return True
    threshold = escalation.get("threshold")
    if not isinstance(threshold, dict):
        return True
    value = threshold.get("value")
    return value in (None, "")


def _approval_count(authority: dict[str, Any]) -> int:
    for container_name in ("authority_requirements", "review_requirements"):
        container = authority.get(container_name)
        if isinstance(container, dict):
            value = container.get("approval_count")
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return 1


def _required_roles(authority: dict[str, Any]) -> list[str]:
    roles = []
    authority_requirements = authority.get("authority_requirements")
    if isinstance(authority_requirements, dict):
        roles.extend(_strings(authority_requirements.get("required_roles")))
    approval_requirements = authority.get("approval_requirements")
    if isinstance(approval_requirements, dict):
        required = approval_requirements.get("required")
        if isinstance(required, list):
            for item in required:
                if isinstance(item, dict) and isinstance(item.get("role"), str):
                    roles.append(item["role"])
    return [role for role in roles if role]


def _defines_supersession(authority: dict[str, Any]) -> bool:
    lifecycle = authority.get("lifecycle_requirements")
    if isinstance(lifecycle, dict) and lifecycle.get("supersession"):
        return True
    stage_requirements = authority.get("stage_requirements")
    transitions = stage_requirements.get("allowed_transitions") if isinstance(stage_requirements, dict) else []
    if not isinstance(transitions, list):
        return False
    for transition in transitions:
        if not isinstance(transition, dict):
            continue
        values = {str(transition.get("from", "")).lower(), str(transition.get("to", "")).lower()}
        if "superseded" in values or "supersede" in values:
            return True
    return False


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
