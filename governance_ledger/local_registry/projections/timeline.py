"""Timeline projections for local registry state."""

from __future__ import annotations

from typing import Any


def build_timeline_projection(
    *,
    authority_ref: str,
    lifecycle_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an ordered lifecycle timeline projection for an authority."""
    return {
        "schema_version": "authority_timeline_projection.v1",
        "authority_ref": authority_ref,
        "events": sorted(
            [
                {
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type") or event.get("event"),
                    "timestamp": event.get("timestamp"),
                    "artifact_hashes": event.get("artifact_hashes") or {"bundle_hash": event.get("hash")},
                    "detail": (event.get("notes") or {}).get("detail") or event.get("detail") or "",
                    "previous_event_id": event.get("previous_event_id"),
                }
                for event in lifecycle_events
            ],
            key=lambda item: item.get("timestamp") or "",
        ),
    }
