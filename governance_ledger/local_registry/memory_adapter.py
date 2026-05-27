"""In-memory adapter for the local registry state model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from governance_ledger.local_registry.models import (
    append_lifecycle_event,
    validate_diagnostic_rollup,
    validate_lifecycle_event,
    validate_registry_entry,
)


class MemoryRegistryAdapter:
    """Small adapter implementation for tests and future storage-boundary work."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._diagnostic_rollups: dict[str, dict[str, Any]] = {}
        self._workspace_projections: dict[str, dict[str, Any]] = {}

    def save_workspace_projection(self, projection: dict[str, Any]) -> None:
        if projection.get("schema_version") != "authority_workspace_projection.v1":
            raise ValueError("unsupported workspace projection schema_version")
        self._workspace_projections[projection["authority_ref"]] = deepcopy(projection)

    def load_workspace_projection(self, authority_ref: str) -> dict[str, Any] | None:
        projection = self._workspace_projections.get(authority_ref)
        return deepcopy(projection) if projection else None

    def list_registry_entries(self) -> list[dict[str, Any]]:
        return [deepcopy(entry) for entry in self._entries.values()]

    def get_registry_entry(self, authority_ref: str) -> dict[str, Any] | None:
        entry = self._entries.get(authority_ref)
        return deepcopy(entry) if entry else None

    def save_registry_entry(self, entry: dict[str, Any]) -> None:
        validate_registry_entry(entry)
        self._entries[entry["authority_ref"]] = deepcopy(entry)

    def append_lifecycle_event(self, authority_ref: str, event: dict[str, Any]) -> list[dict[str, Any]]:
        validate_lifecycle_event(event)
        if event["authority_ref"] != authority_ref:
            raise ValueError("lifecycle event authority_ref does not match append target")
        current = self._events.get(authority_ref, [])
        updated = append_lifecycle_event(current, event)
        self._events[authority_ref] = updated
        return [deepcopy(item) for item in updated]

    def list_lifecycle_events(self, authority_ref: str) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._events.get(authority_ref, [])]

    def save_publication_receipt(self, authority_ref: str, receipt: dict[str, Any]) -> None:
        if receipt.get("schema_version") != "publication_receipt.v1":
            raise ValueError("unsupported publication receipt schema_version")
        self._receipts[authority_ref] = deepcopy(receipt)

    def get_publication_receipt(self, authority_ref: str) -> dict[str, Any] | None:
        receipt = self._receipts.get(authority_ref)
        return deepcopy(receipt) if receipt else None

    def save_diagnostic_rollup(self, authority_ref: str, rollup: dict[str, Any]) -> None:
        validate_diagnostic_rollup(rollup)
        if rollup["authority_ref"] != authority_ref:
            raise ValueError("diagnostic rollup authority_ref does not match save target")
        self._diagnostic_rollups[authority_ref] = deepcopy(rollup)

    def get_diagnostic_rollup(self, authority_ref: str) -> dict[str, Any] | None:
        rollup = self._diagnostic_rollups.get(authority_ref)
        return deepcopy(rollup) if rollup else None
