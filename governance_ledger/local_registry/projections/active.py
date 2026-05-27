"""Active authority projections."""

from __future__ import annotations

from typing import Any

ACTIVE_AUTHORITY_PROJECTION_V1 = "active_authority_projection.v1"


def build_active_authority_projection(
    *,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve current active authority versions by authority family."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(_authority_family(entry["authority_ref"]), []).append(entry)
    active = []
    for family, family_entries in sorted(grouped.items()):
        candidate = _active_entry(family_entries)
        active.append(
            {
                "authority_family": family,
                "active_authority_ref": candidate["authority_ref"] if candidate else None,
                "active_authority_version": (candidate.get("authority_version") or _version_from_ref(candidate["authority_ref"])) if candidate else None,
                "status": candidate.get("status") if candidate else "none",
                "reason": _active_reason(candidate),
            }
        )
    return {
        "schema_version": ACTIVE_AUTHORITY_PROJECTION_V1,
        "active_authorities": active,
    }


def _active_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    registered = [entry for entry in entries if entry.get("status") == "registered" and not entry.get("superseded_by")]
    if registered:
        return sorted(registered, key=lambda item: item.get("authority_version") or _version_from_ref(item["authority_ref"]))[-1]
    available = [entry for entry in entries if entry.get("status") not in {"revoked", "superseded"}]
    if available:
        return sorted(available, key=lambda item: item.get("authority_version") or _version_from_ref(item["authority_ref"]))[-1]
    return None


def _active_reason(entry: dict[str, Any] | None) -> str:
    if not entry:
        return "no active authority"
    if entry.get("status") == "registered":
        return "latest registered authority without supersession"
    return "latest non-revoked authority posture"


def _authority_family(authority_ref: str) -> str:
    return authority_ref.split("@", 1)[0]


def _version_from_ref(authority_ref: str) -> str:
    if "@" not in authority_ref:
        return "unversioned"
    return authority_ref.rsplit("@", 1)[1] or "unversioned"
