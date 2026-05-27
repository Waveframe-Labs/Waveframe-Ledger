"""Canonical local registry state models."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

AUTHORITY_LIFECYCLE_EVENT_V1 = "authority_lifecycle_event.v1"
AUTHORITY_REGISTRY_ENTRY_V1 = "authority_registry_entry.v1"
DIAGNOSTIC_ROLLUP_V1 = "diagnostic_rollup.v1"

LIFECYCLE_EVENT_TYPES = {
    "drafted",
    "reviewed",
    "exported",
    "registered",
    "superseded",
    "revoked",
}

REGISTRY_STATUSES = {
    "draft",
    "reviewed",
    "exported",
    "registered",
    "superseded",
    "revoked",
}

SEVERITY_ORDER = {
    "none": 0,
    "info": 1,
    "warning": 2,
    "error": 3,
}


def build_authority_lifecycle_event(
    *,
    authority_ref: str,
    event_type: str,
    timestamp: str,
    authority_version: str | None = None,
    actor: str = "local-ledger-ui",
    source: str = "governance-ledger",
    artifact_hashes: dict[str, Any] | None = None,
    notes: dict[str, Any] | None = None,
    previous_event_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Build an append-only authority lifecycle event."""
    if event_type not in LIFECYCLE_EVENT_TYPES:
        raise ValueError(f"unsupported lifecycle event_type: {event_type}")
    version = authority_version or _version_from_ref(authority_ref)
    event = {
        "schema_version": AUTHORITY_LIFECYCLE_EVENT_V1,
        "event_id": event_id
        or _stable_id(
            "event",
            {
                "authority_ref": authority_ref,
                "authority_version": version,
                "event_type": event_type,
                "timestamp": timestamp,
                "artifact_hashes": artifact_hashes or {},
                "previous_event_id": previous_event_id,
            },
        ),
        "authority_ref": authority_ref,
        "authority_version": version,
        "event_type": event_type,
        "timestamp": timestamp,
        "actor": actor,
        "source": source,
        "artifact_hashes": artifact_hashes or {},
        "notes": notes or {},
        "previous_event_id": previous_event_id,
    }
    validate_lifecycle_event(event)
    return event


def build_authority_registry_entry(
    *,
    authority_ref: str,
    status: str,
    protected_resource: str,
    governed_action: str,
    continuity_posture: str,
    replay_readiness: str,
    diagnostic_summary: dict[str, Any],
    lifecycle_events: list[dict[str, Any]],
    created_at: str,
    updated_at: str,
    authority_version: str | None = None,
    latest_bundle_hash: str | None = None,
    latest_receipt_hash: str | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
) -> dict[str, Any]:
    """Build a durable local registry entry from canonical registry state."""
    if status not in REGISTRY_STATUSES:
        raise ValueError(f"unsupported registry status: {status}")
    version = authority_version or _version_from_ref(authority_ref)
    event_ids = []
    for event in lifecycle_events:
        validate_lifecycle_event(event)
        if event["authority_ref"] != authority_ref:
            raise ValueError("lifecycle event authority_ref does not match registry entry")
        event_ids.append(event["event_id"])
    entry = {
        "schema_version": AUTHORITY_REGISTRY_ENTRY_V1,
        "authority_ref": authority_ref,
        "authority_version": version,
        "status": status,
        "protected_resource": protected_resource,
        "governed_action": governed_action,
        "continuity_posture": continuity_posture,
        "replay_readiness": replay_readiness,
        "diagnostic_summary": diagnostic_summary,
        "latest_bundle_hash": latest_bundle_hash,
        "latest_receipt_hash": latest_receipt_hash,
        "lifecycle_event_ids": event_ids,
        "supersedes": supersedes,
        "superseded_by": superseded_by,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    validate_registry_entry(entry)
    return entry


def build_diagnostic_rollup(
    *,
    authority_ref: str,
    diagnostics: list[dict[str, Any]],
    authority_version: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic advisory diagnostic summary for an authority state."""
    severities = [_normal_severity(item.get("severity")) for item in diagnostics]
    domains = sorted(
        {
            str(item.get("domain"))
            for item in diagnostics
            if isinstance(item.get("domain"), str) and item.get("domain")
        }
    )
    diagnostic_ids = [
        str(item.get("code") or item.get("diagnostic_id"))
        for item in diagnostics
        if item.get("code") or item.get("diagnostic_id")
    ]
    highest = "none"
    for severity in severities:
        if SEVERITY_ORDER[severity] > SEVERITY_ORDER[highest]:
            highest = severity
    rollup = {
        "schema_version": DIAGNOSTIC_ROLLUP_V1,
        "authority_ref": authority_ref,
        "authority_version": authority_version or _version_from_ref(authority_ref),
        "finding_count": len(diagnostics),
        "warning_count": sum(1 for severity in severities if severity == "warning"),
        "info_count": sum(1 for severity in severities if severity == "info"),
        "domains": domains,
        "highest_severity": highest,
        "diagnostic_ids": diagnostic_ids,
    }
    validate_diagnostic_rollup(rollup)
    return rollup


def append_lifecycle_event(
    events: list[dict[str, Any]],
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return a new lifecycle list with an event appended without mutating prior events."""
    validate_lifecycle_event(event)
    for existing in events:
        validate_lifecycle_event(existing)
        if existing["event_id"] == event["event_id"]:
            raise ValueError("duplicate lifecycle event_id")
    return [deepcopy(item) for item in events] + [deepcopy(event)]


def validate_lifecycle_event(event: dict[str, Any]) -> None:
    if event.get("schema_version") != AUTHORITY_LIFECYCLE_EVENT_V1:
        raise ValueError("unsupported lifecycle event schema_version")
    for field in ("event_id", "authority_ref", "authority_version", "event_type", "timestamp", "actor", "source"):
        if not isinstance(event.get(field), str) or not event[field]:
            raise ValueError(f"lifecycle event {field} must be a non-empty string")
    if event["event_type"] not in LIFECYCLE_EVENT_TYPES:
        raise ValueError("unsupported lifecycle event_type")
    if not isinstance(event.get("artifact_hashes"), dict):
        raise ValueError("lifecycle event artifact_hashes must be an object")
    if not isinstance(event.get("notes"), dict):
        raise ValueError("lifecycle event notes must be an object")
    if event.get("previous_event_id") is not None and not isinstance(event["previous_event_id"], str):
        raise ValueError("lifecycle event previous_event_id must be null or string")


def validate_registry_entry(entry: dict[str, Any]) -> None:
    if entry.get("schema_version") != AUTHORITY_REGISTRY_ENTRY_V1:
        raise ValueError("unsupported registry entry schema_version")
    for field in (
        "authority_ref",
        "authority_version",
        "status",
        "protected_resource",
        "governed_action",
        "continuity_posture",
        "replay_readiness",
        "created_at",
        "updated_at",
    ):
        if not isinstance(entry.get(field), str) or not entry[field]:
            raise ValueError(f"registry entry {field} must be a non-empty string")
    if entry["status"] not in REGISTRY_STATUSES:
        raise ValueError("unsupported registry status")
    if not isinstance(entry.get("diagnostic_summary"), dict):
        raise ValueError("registry entry diagnostic_summary must be an object")
    if not isinstance(entry.get("lifecycle_event_ids"), list):
        raise ValueError("registry entry lifecycle_event_ids must be an array")
    if not all(isinstance(item, str) and item for item in entry["lifecycle_event_ids"]):
        raise ValueError("registry entry lifecycle_event_ids must contain non-empty strings")


def validate_diagnostic_rollup(rollup: dict[str, Any]) -> None:
    if rollup.get("schema_version") != DIAGNOSTIC_ROLLUP_V1:
        raise ValueError("unsupported diagnostic rollup schema_version")
    for field in ("authority_ref", "authority_version", "highest_severity"):
        if not isinstance(rollup.get(field), str) or not rollup[field]:
            raise ValueError(f"diagnostic rollup {field} must be a non-empty string")
    if rollup["highest_severity"] not in SEVERITY_ORDER:
        raise ValueError("unsupported diagnostic rollup highest_severity")
    for field in ("finding_count", "warning_count", "info_count"):
        if not isinstance(rollup.get(field), int) or rollup[field] < 0:
            raise ValueError(f"diagnostic rollup {field} must be a non-negative integer")
    if not isinstance(rollup.get("domains"), list):
        raise ValueError("diagnostic rollup domains must be an array")
    if not isinstance(rollup.get("diagnostic_ids"), list):
        raise ValueError("diagnostic rollup diagnostic_ids must be an array")


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    version = authority_ref.rsplit("@", 1)[1]
    return version or "unversioned"


def _normal_severity(value: Any) -> str:
    severity = str(value or "info")
    return severity if severity in SEVERITY_ORDER else "info"


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"
