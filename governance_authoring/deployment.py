"""Attach runtime deployment provenance to compiled governance reviews."""

from __future__ import annotations

from typing import Any

from governance_authoring.lifecycle import transition_review_status
from governance_authoring.provenance import _utc_now

REQUIRED_DEPLOYMENT_STATUS = "compiled"
DEFAULT_ENFORCEMENT_ENGINE = "cricore"


def attach_deployment(
    review: dict[str, Any],
    *,
    environment: str,
    runtime: str,
    deployed_by: str,
    enforcement_engine_version: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Attach deployment provenance and transition compiled reviews to deployed."""
    if review.get("review_status") != REQUIRED_DEPLOYMENT_STATUS:
        raise ValueError("Deployments can only be attached to compiled reviews.")
    if not review.get("compiled_contract"):
        raise ValueError("Deployment requires compiled contract linkage.")

    deployed_at = timestamp or _utc_now()
    updated_review = transition_review_status(
        review,
        "deployed",
        actor=deployed_by,
        timestamp=deployed_at,
        note="Attached deployment provenance.",
    )
    updated_review["deployment"] = {
        "environment": _required_deployment_value(environment, "environment"),
        "runtime": _required_deployment_value(runtime, "runtime"),
        "enforcement_engine": DEFAULT_ENFORCEMENT_ENGINE,
        "engine_version": _required_deployment_value(
            enforcement_engine_version,
            "enforcement_engine_version",
        ),
        "deployed_by": _required_deployment_value(deployed_by, "deployed_by"),
        "deployed_at": deployed_at,
    }

    return updated_review


def _required_deployment_value(value: str, field: str) -> str:
    if not value:
        raise ValueError(f"Deployment missing required field: {field}")
    return value
