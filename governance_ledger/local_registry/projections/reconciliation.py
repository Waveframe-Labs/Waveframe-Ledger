"""Governance reconciliation projections for local registry state."""

from __future__ import annotations

from typing import Any

from governance_ledger.local_registry.projections.active import build_active_authority_projection
from governance_ledger.local_registry.projections.continuity import build_governance_continuity_projection
from governance_ledger.local_registry.projections.health import build_registry_health_projection
from governance_ledger.local_registry.projections.lineage import build_authority_lineage_projection

GOVERNANCE_RECONCILIATION_PROJECTION_V1 = "governance_reconciliation_projection.v1"

DEFAULT_RECONCILED_PROJECTIONS = [
    "active_authority_projection.v1",
    "authority_lineage_projection.v1",
    "authority_operational_summary.v1",
    "governance_continuity_projection.v1",
    "governance_timeline_projection.v1",
    "registry_health_projection.v1",
]


def build_governance_reconciliation_projection(
    *,
    entries: list[dict[str, Any]],
    generated_at: str | None = None,
    projection_freshness: list[dict[str, Any]] | None = None,
    invalidated_projections: list[str] | None = None,
    expected_receipt_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Reconcile lifecycle, lineage, replay, continuity, freshness, active state, and registry health."""
    ordered = sorted(entries, key=_lineage_sort_key)
    source_event_ids = _source_event_ids(ordered)
    generated = generated_at or _latest_timestamp(ordered)
    invalidated = set(invalidated_projections or [])
    freshness = _projection_freshness(
        generated_at=generated,
        source_event_ids=source_event_ids,
        projection_freshness=projection_freshness,
        invalidated_projections=invalidated,
    )
    issues = (
        _freshness_issues(freshness)
        + _active_authority_issues(ordered)
        + _lineage_issues(ordered)
        + _replay_issues(ordered, expected_receipt_hashes or {})
        + _continuity_issues(ordered)
        + _registry_health_issues(ordered)
    )
    issues.sort(key=lambda item: (item["severity"], item["reconciliation_issue_type"], item.get("authority_ref") or ""))
    return {
        "schema_version": GOVERNANCE_RECONCILIATION_PROJECTION_V1,
        "generated_at": generated,
        "source_event_ids": source_event_ids,
        "freshness_posture": _aggregate_freshness(freshness),
        "reconciliation_posture": _reconciliation_posture(issues, freshness),
        "projection_freshness": freshness,
        "issues": issues,
    }


def _projection_freshness(
    *,
    generated_at: str,
    source_event_ids: list[str],
    projection_freshness: list[dict[str, Any]] | None,
    invalidated_projections: set[str],
) -> list[dict[str, Any]]:
    supplied = {item["projection"]: item for item in projection_freshness or [] if item.get("projection")}
    projections = sorted(set(DEFAULT_RECONCILED_PROJECTIONS) | set(supplied) | invalidated_projections)
    freshness = []
    for projection in projections:
        supplied_item = supplied.get(projection, {})
        supplied_sources = sorted(supplied_item.get("source_event_ids") or source_event_ids)
        posture = supplied_item.get("freshness_posture") or "fresh"
        if projection in invalidated_projections:
            posture = "invalidated"
        elif supplied_sources != source_event_ids:
            posture = "stale"
        freshness.append(
            {
                "projection": projection,
                "generated_at": supplied_item.get("generated_at") or generated_at,
                "source_event_ids": supplied_sources,
                "freshness_posture": posture,
            }
        )
    return freshness


def _freshness_issues(freshness: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    for item in freshness:
        if item["freshness_posture"] not in {"stale", "invalidated"}:
            continue
        issues.append(
            _issue(
                issue_type="projection_divergence",
                severity="warning" if item["freshness_posture"] == "stale" else "authority_conflict",
                summary=f"{item['projection']} is {item['freshness_posture']} relative to current registry source events.",
                projection=item["projection"],
                reason="projection freshness does not match current source event lineage",
            )
        )
    return issues


def _active_authority_issues(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    grouped = _group_by_family(entries)
    active_projection = build_active_authority_projection(entries=entries)
    for family, family_entries in grouped.items():
        active = [entry for entry in family_entries if entry.get("status") == "registered" and not entry.get("superseded_by")]
        if len(active) > 1:
            issues.append(
                _issue(
                    issue_type="multiple_active_authorities",
                    severity="authority_conflict",
                    summary=f"{family} has multiple registered active authorities.",
                    authority_ref=family,
                )
            )
        resolved = next((item for item in active_projection["active_authorities"] if item["authority_family"] == family), None)
        if resolved and resolved["status"] == "revoked":
            issues.append(
                _issue(
                    issue_type="revoked_active_authority",
                    severity="critical",
                    summary=f"{family} resolves to a revoked active authority posture.",
                    authority_ref=family,
                )
            )
    return issues


def _lineage_issues(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    lineage = build_authority_lineage_projection(entries=entries)
    refs = {entry["authority_ref"] for entry in entries}
    for entry in entries:
        if entry.get("superseded_by") and entry["superseded_by"] not in refs:
            issues.append(
                _issue(
                    issue_type="lineage_gap",
                    severity="authority_conflict",
                    summary=f"{entry['authority_ref']} points to missing superseding authority {entry['superseded_by']}.",
                    authority_ref=entry["authority_ref"],
                    missing_authority_version=_version_from_ref(entry["superseded_by"]),
                )
            )
    for missing_version in _missing_patch_versions(entries):
        issues.append(
            _issue(
                issue_type="lineage_gap",
                severity="warning",
                summary=f"Authority lineage is missing version {missing_version}.",
                authority_ref=lineage.get("authority_family"),
                missing_authority_version=missing_version,
            )
        )
    return issues


def _replay_issues(entries: list[dict[str, Any]], expected_receipt_hashes: dict[str, str]) -> list[dict[str, Any]]:
    issues = []
    for entry in entries:
        actual = _receipt_hash(entry)
        expected = expected_receipt_hashes.get(entry["authority_ref"]) or entry.get("expected_receipt_hash")
        if expected is not None and actual != expected:
            issues.append(
                _issue(
                    issue_type="replay_posture_inconsistent",
                    severity="replay_risk",
                    summary=f"{entry['authority_ref']} replay receipt posture differs from expected receipt hash.",
                    authority_ref=entry["authority_ref"],
                    expected_receipt_hash=expected,
                    actual_receipt_hash=actual,
                )
            )
        elif expected is None and entry.get("status") in {"exported", "registered"} and actual is None:
            issues.append(
                _issue(
                    issue_type="replay_posture_inconsistent",
                    severity="replay_risk",
                    summary=f"{entry['authority_ref']} has exported or registered posture without a receipt hash.",
                    authority_ref=entry["authority_ref"],
                    expected_receipt_hash="publication_receipt.v1",
                    actual_receipt_hash=None,
                )
            )
    return issues


def _continuity_issues(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    continuity = build_governance_continuity_projection(entries=entries)
    for family in continuity["authority_families"]:
        if family["continuity_posture"] == "stable":
            continue
        issues.append(
            _issue(
                issue_type="continuity_posture_unstable",
                severity=_continuity_severity(family["continuity_posture"]),
                summary=f"{family['authority_family']} continuity posture is {family['continuity_posture']}.",
                authority_ref=family["authority_family"],
                reason=family["continuity_posture"],
            )
        )
    return issues


def _registry_health_issues(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    health = build_registry_health_projection(entries=entries)
    if health["registry_posture"] == "healthy":
        return []
    return [
        _issue(
            issue_type="registry_health_unstable",
            severity="warning",
            summary=f"Registry health posture is {health['registry_posture']}.",
            reason=health["registry_posture"],
        )
    ]


def _issue(
    *,
    issue_type: str,
    severity: str,
    summary: str,
    authority_ref: str | None = None,
    projection: str | None = None,
    reason: str | None = None,
    expected_receipt_hash: str | None = None,
    actual_receipt_hash: str | None = None,
    missing_authority_version: str | None = None,
) -> dict[str, Any]:
    issue = {
        "schema_version": "governance_reconciliation_issue.v1",
        "reconciliation_issue_type": issue_type,
        "severity": severity,
        "summary": summary,
        "authority_ref": authority_ref,
        "projection": projection,
        "reason": reason,
        "expected_receipt_hash": expected_receipt_hash,
        "actual_receipt_hash": actual_receipt_hash,
        "missing_authority_version": missing_authority_version,
    }
    return {key: value for key, value in issue.items() if value is not None}


def _aggregate_freshness(freshness: list[dict[str, Any]]) -> str:
    postures = {item["freshness_posture"] for item in freshness}
    if "invalidated" in postures:
        return "invalidated"
    if "stale" in postures:
        return "stale"
    return "fresh"


def _reconciliation_posture(issues: list[dict[str, Any]], freshness: list[dict[str, Any]]) -> str:
    if _aggregate_freshness(freshness) == "invalidated":
        return "invalidated"
    if issues:
        return "issues_detected"
    return "reconciled"


def _continuity_severity(posture: str) -> str:
    if posture in {"fragmented", "ambiguous"}:
        return "authority_conflict"
    if posture == "continuity_at_risk":
        return "continuity_risk"
    if posture == "replay_degraded":
        return "replay_risk"
    return "warning"


def _source_event_ids(entries: list[dict[str, Any]]) -> list[str]:
    ids = []
    for entry in entries:
        ids.extend(entry.get("lifecycle_event_ids") or [])
        ids.extend(
            event["event_id"]
            for event in entry.get("lifecycle_events") or entry.get("lifecycle_timeline") or []
            if event.get("event_id")
        )
    return sorted(set(ids))


def _latest_timestamp(entries: list[dict[str, Any]]) -> str | None:
    timestamps = []
    for entry in entries:
        if entry.get("updated_at"):
            timestamps.append(entry["updated_at"])
        timestamps.extend(
            event["timestamp"]
            for event in entry.get("lifecycle_events") or entry.get("lifecycle_timeline") or []
            if event.get("timestamp")
        )
    return sorted(timestamps)[-1] if timestamps else None


def _group_by_family(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(_authority_family(entry["authority_ref"]), []).append(entry)
    return grouped


def _missing_patch_versions(entries: list[dict[str, Any]]) -> list[str]:
    grouped = _group_by_family(entries)
    missing: list[str] = []
    for family_entries in grouped.values():
        parsed = [_parse_semver(entry.get("authority_version") or _version_from_ref(entry["authority_ref"])) for entry in family_entries]
        parsed = [version for version in parsed if version is not None]
        by_major_minor: dict[tuple[int, int], set[int]] = {}
        for major, minor, patch in parsed:
            by_major_minor.setdefault((major, minor), set()).add(patch)
        for (major, minor), patches in by_major_minor.items():
            for patch in range(min(patches), max(patches) + 1):
                if patch not in patches:
                    missing.append(f"{major}.{minor}.{patch}")
    return sorted(set(missing))


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    parts = value.split(".")
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _receipt_hash(entry: dict[str, Any]) -> str | None:
    return entry.get("latest_receipt_hash") or (entry.get("publication_receipt") or {}).get("receipt_hash")


def _lineage_sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    authority_ref = entry["authority_ref"]
    return (_authority_family(authority_ref), entry.get("authority_version") or _version_from_ref(authority_ref))


def _authority_family(authority_ref: str) -> str:
    return authority_ref.split("@", 1)[0]


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
