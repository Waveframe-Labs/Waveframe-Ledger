"""Canonical provenance verification for customer-authored publications."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime
from typing import Any


CUSTOMER_POLICY_PROFILE = "customer_policy_provenance_complete_v1"
LEGACY_INCOMPLETE_PROFILE = "legacy_provenance_incomplete"
MAX_SOURCE_BYTES = 245_760
MAX_SOURCE_STATEMENTS = 2_048
MAX_STATEMENT_MAPPINGS = 1_024
MAX_RESOLUTION_RECORDS = 1_024
MAX_RULE_IDS_PER_MAPPING = 256
MAX_STATEMENT_IDS_PER_RESOLUTION = 64
MAX_RESOLUTION_DECISION_LENGTH = 4_096
SOURCE_STATEMENT_CLASSIFICATIONS = {
    "enforced",
    "informational",
    "unsupported",
    "requires_resolution",
}
VERSION_RELATIONSHIPS = {"publishes_as"}


def canonical_json(value: Any) -> str:
    """Serialize JSON with the canonical Ledger ordering and separators."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    """Return the prefixed SHA-256 of canonical JSON."""
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bytes_sha256(value: bytes) -> str:
    """Return the prefixed SHA-256 of exact bytes."""
    return "sha256:" + hashlib.sha256(value).hexdigest()


def hash_without_field(value: dict[str, Any], field: str) -> str:
    """Hash an object without a root self-referential hash field."""
    return canonical_sha256({key: item for key, item in value.items() if key != field})


def semantic_commit_hash(commit: dict[str, Any]) -> str:
    """Recompute the semantic hash for legacy or provenance-bound commits."""
    meaning = commit.get("committed_semantic_meaning") or {}
    bindings = commit.get("provenance_bindings")
    payload = (
        {"committed_semantic_meaning": meaning, "provenance_bindings": bindings}
        if isinstance(bindings, dict)
        else meaning
    )
    return _semantic_hash(payload)


def compiled_contract_hash(contract: dict[str, Any]) -> str:
    """Recompute a compiler contract hash using its canonical hash exclusions."""
    return _semantic_hash(contract)


def source_statement_id(
    *,
    source_policy_id: str,
    source_revision: str,
    start_byte: int,
    end_byte: int,
    statement_hash: str,
) -> str:
    """Derive a stable statement identity from source identity and exact byte span."""
    digest = canonical_sha256(
        {
            "source_policy_id": source_policy_id,
            "source_revision": source_revision,
            "start_byte": start_byte,
            "end_byte": end_byte,
            "statement_hash": statement_hash,
        }
    ).removeprefix("sha256:")
    return f"statement-{digest}"


def statement_mapping_id(statement_ids: list[str], rule_ids: list[str]) -> str:
    """Derive a stable sentence-to-rule mapping identity."""
    digest = canonical_sha256(
        {
            "statement_ids": statement_ids,
            "rule_ids": rule_ids,
        }
    ).removeprefix("sha256:")
    return f"mapping-{digest}"


def resolution_record_id(
    *,
    ambiguity_id: str,
    statement_ids: list[str],
    selected_decision: str,
    resolved_by: str,
    resolved_at: str,
) -> str:
    """Derive a stable audit identity for an ambiguity resolution record."""
    digest = canonical_sha256(
        {
            "ambiguity_id": ambiguity_id,
            "statement_ids": statement_ids,
            "selected_decision": selected_decision,
            "resolved_by": resolved_by,
            "resolved_at": resolved_at,
        }
    ).removeprefix("sha256:")
    return f"resolution-{digest}"


def resolution_set_id(records: list[dict[str, Any]]) -> str:
    """Derive the stable identity of an ordered resolution record set."""
    return f"resolution-set-{canonical_sha256(records).removeprefix('sha256:')}"


def classify_authority_bundle_provenance(bundle: dict[str, Any]) -> str:
    """Classify without inferring missing historical source lineage."""
    if (
        bundle.get("provenance_profile") == CUSTOMER_POLICY_PROFILE
        and isinstance(bundle.get("customer_policy_provenance"), dict)
        and bundle["customer_policy_provenance"].get("provenance_complete") is True
    ):
        return CUSTOMER_POLICY_PROFILE
    return LEGACY_INCOMPLETE_PROFILE


def validate_authority_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate an authority bundle according to its exact schema version."""
    if isinstance(bundle, dict) and bundle.get("schema_version") == "authority_bundle.v2":
        from governance_ledger.domain_policy import _validate_authority_bundle_v2

        return _validate_authority_bundle_v2(bundle)
    declared_profile = bundle.get("provenance_profile")
    customer_provenance = bundle.get("customer_policy_provenance")
    if declared_profile not in {None, LEGACY_INCOMPLETE_PROFILE, CUSTOMER_POLICY_PROFILE}:
        raise ValueError("authority bundle provenance_profile is unsupported")
    if isinstance(customer_provenance, dict) and declared_profile != CUSTOMER_POLICY_PROFILE:
        raise ValueError("the explicit complete provenance_profile is required for customer policy provenance")
    profile = classify_authority_bundle_provenance(bundle)
    if declared_profile == CUSTOMER_POLICY_PROFILE:
        _validate_customer_policy_bundle(bundle)
        profile = CUSTOMER_POLICY_PROFILE
    return {
        "profile": profile,
        "provenance_complete": profile == CUSTOMER_POLICY_PROFILE,
    }


def validate_publication_receipt(
    authority_bundle: dict[str, Any],
    publication_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Verify every receipt binding against the canonical authority bundle."""
    bundle_version = authority_bundle.get("schema_version") if isinstance(authority_bundle, dict) else None
    receipt_version = publication_receipt.get("schema_version") if isinstance(publication_receipt, dict) else None
    if bundle_version == "authority_bundle.v2" or receipt_version == "publication_receipt.v2":
        if bundle_version != "authority_bundle.v2" or receipt_version != "publication_receipt.v2":
            raise ValueError("authority bundle and publication receipt schema versions do not match")
        from governance_ledger.domain_policy import _validate_publication_receipt_v2

        return _validate_publication_receipt_v2(authority_bundle, publication_receipt)
    bundle_status = validate_authority_bundle(authority_bundle)
    receipt = publication_receipt
    expected_bundle_hash = canonical_sha256(authority_bundle)
    _require_equal(receipt.get("bundle_hash"), expected_bundle_hash, "receipt bundle_hash")
    _require_equal(receipt.get("publication_id"), authority_bundle.get("publication_id"), "receipt publication_id")
    _require_equal(receipt.get("authority_ref"), authority_bundle.get("authority_ref"), "receipt authority_ref")
    _require_equal(receipt.get("contract_hash"), authority_bundle.get("contract_hash"), "receipt contract_hash")
    receipt_id_digest = hashlib.sha256(
        (
            f"{receipt.get('publication_id')}:{receipt.get('authority_ref')}:"
            f"{receipt.get('published_at')}"
        ).encode("utf-8")
    ).hexdigest()
    _require_equal(receipt.get("receipt_id"), f"receipt_{receipt_id_digest[:12]}", "receipt_id")

    immutable = authority_bundle.get("immutable_inputs") or {}
    receipt_immutable = receipt.get("immutable_inputs") or {}
    _require_equal(receipt.get("manifest_hash"), immutable.get("manifest_hash"), "receipt manifest_hash")
    _require_equal(receipt.get("review_packet_hashes"), immutable.get("review_packet_hashes"), "receipt review_packet_hashes")
    _require_equal(receipt.get("semantic_commit_hash"), immutable.get("semantic_commit_hash"), "receipt semantic_commit_hash")
    _require_equal(receipt.get("compiled_contract_hash"), immutable.get("compiled_contract_hash"), "receipt compiled_contract_hash")
    expected_semantic_artifacts = {
        item["artifact_type"]: item["artifact_hash"]
        for item in authority_bundle.get("semantic_artifacts") or []
        if isinstance(item, dict) and item.get("artifact_type") and item.get("artifact_hash")
    }
    _require_equal(
        receipt.get("semantic_artifact_hashes"),
        expected_semantic_artifacts,
        "receipt semantic_artifact_hashes",
    )
    for field in [
        "authority_hash",
        "manifest_hash",
        "preview_hash",
        "diff_hash",
        "semantic_commit_hash",
        "compiled_contract_hash",
        "bundle_hash",
    ]:
        expected = expected_bundle_hash if field == "bundle_hash" else immutable.get(field)
        _require_equal(receipt_immutable.get(field), expected, f"receipt immutable_inputs.{field}")

    if bundle_status["provenance_complete"]:
        _require_equal(receipt.get("provenance_profile"), CUSTOMER_POLICY_PROFILE, "receipt provenance_profile")
        expected_bindings = _receipt_provenance_bindings(authority_bundle)
        _require_equal(receipt.get("provenance_bindings"), expected_bindings, "receipt provenance_bindings")
        for field, expected in expected_bindings.items():
            _require_equal(receipt_immutable.get(field), expected, f"receipt immutable_inputs.{field}")
        manifest = authority_bundle.get("publication_manifest") or {}
        _require_equal(receipt.get("published_at"), manifest.get("published_at"), "receipt published_at")
        _require_equal(receipt.get("published_by"), manifest.get("published_by"), "receipt published_by")
        lineage_continuity = receipt.get("lineage_continuity") or {}
        _require_equal(lineage_continuity.get("lineage_complete"), True, "receipt lineage completeness")

    expected_receipt_hash = hash_without_field(receipt, "receipt_hash")
    _require_equal(receipt.get("receipt_hash"), expected_receipt_hash, "receipt_hash")
    return bundle_status


def receipt_provenance_bindings(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return the complete receipt binding model for a validated bundle."""
    _validate_customer_policy_bundle(bundle)
    return _receipt_provenance_bindings(bundle)


def _validate_customer_policy_bundle(bundle: dict[str, Any]) -> None:
    _require_equal(bundle.get("schema_version"), "authority_bundle.v1", "bundle schema_version")
    provenance = _required_object(bundle, "customer_policy_provenance")
    _require_equal(provenance.get("profile"), CUSTOMER_POLICY_PROFILE, "customer provenance profile")
    _require_equal(provenance.get("provenance_complete"), True, "customer provenance completeness")

    source = _required_object(provenance, "source_policy")
    source_policy_id = _required_string(source, "source_policy_id")
    source_revision = _required_string(source, "source_revision")
    if "@" in source_policy_id or "@" in source_revision:
        raise ValueError("source policy identity and revision must not contain @")
    source_ref = f"{source_policy_id}@{source_revision}"
    _require_equal(source.get("source_policy_ref"), source_ref, "source policy reference")
    _require_equal(source.get("content_encoding"), "base64", "source content_encoding")
    source_bytes = _decode_base64(_required_string(source, "source_bytes_base64"), "source bytes")
    if not source_bytes:
        raise ValueError("source policy must contain non-empty UTF-8 text")
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise ValueError(f"source policy exceeds maximum of {MAX_SOURCE_BYTES} bytes")
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("source policy must contain valid UTF-8 text") from exc
    if not source_text.strip():
        raise ValueError("source policy must contain non-empty UTF-8 text")
    source_snapshot_hash = bytes_sha256(source_bytes)
    _require_equal(source.get("snapshot_hash"), source_snapshot_hash, "source snapshot_hash")

    statements = _required_list(provenance, "source_statements")
    if not statements:
        raise ValueError("customer provenance requires at least one source statement")
    if len(statements) > MAX_SOURCE_STATEMENTS:
        raise ValueError(
            f"customer provenance exceeds maximum of {MAX_SOURCE_STATEMENTS} source statements"
        )
    statement_ids: set[str] = set()
    statement_spans: set[tuple[int, int]] = set()
    classifications: dict[str, str] = {}
    expected_start = 0
    for index, statement_value in enumerate(statements):
        if not isinstance(statement_value, dict):
            raise ValueError(f"source_statements[{index}] must be an object")
        statement = statement_value
        _require_exact_fields(
            statement,
            {
                "statement_id",
                "start_byte",
                "end_byte",
                "statement_bytes_base64",
                "statement_hash",
                "classification",
            },
            f"source_statements[{index}]",
        )
        start = _required_integer(statement, "start_byte")
        end = _required_integer(statement, "end_byte")
        if start < 0 or end <= start or end > len(source_bytes):
            raise ValueError(f"source_statements[{index}] has an invalid byte span")
        if (start, end) in statement_spans:
            raise ValueError(f"source_statements[{index}] duplicates a byte span")
        if start < expected_start:
            raise ValueError(f"source_statements[{index}] is overlapping or out of order")
        if start > expected_start:
            raise ValueError(f"source_statements[{index}] omits source policy bytes")
        statement_spans.add((start, end))
        expected_start = end
        statement_bytes = source_bytes[start:end]
        supplied_statement_bytes = _decode_base64(
            _required_string(statement, "statement_bytes_base64"),
            f"source_statements[{index}] bytes",
        )
        _require_equal(
            supplied_statement_bytes,
            statement_bytes,
            f"source_statements[{index}] byte span",
        )
        encoded = base64.b64encode(statement_bytes).decode("ascii")
        _require_equal(statement.get("statement_bytes_base64"), encoded, f"source_statements[{index}] bytes")
        expected_statement_hash = bytes_sha256(statement_bytes)
        _require_equal(statement.get("statement_hash"), expected_statement_hash, f"source_statements[{index}] hash")
        expected_statement_id = source_statement_id(
            source_policy_id=source_policy_id,
            source_revision=source_revision,
            start_byte=start,
            end_byte=end,
            statement_hash=expected_statement_hash,
        )
        _require_equal(statement.get("statement_id"), expected_statement_id, f"source_statements[{index}] id")
        if expected_statement_id in statement_ids:
            raise ValueError(f"duplicate source statement identity: {expected_statement_id}")
        statement_ids.add(expected_statement_id)
        classification = _required_string(statement, "classification")
        if classification not in SOURCE_STATEMENT_CLASSIFICATIONS:
            raise ValueError(f"source_statements[{index}] has an invalid final classification")
        classifications[expected_statement_id] = classification
    if expected_start != len(source_bytes):
        raise ValueError("source statement partition omits trailing source policy bytes")
    unresolved_statement_ids = [
        statement_id
        for statement_id, classification in classifications.items()
        if classification == "requires_resolution"
    ]
    if unresolved_statement_ids:
        raise ValueError(
            "provenance-complete publication cannot contain requires_resolution statements"
        )
    source_statements_hash = canonical_sha256(statements)

    interpretation = _required_object(provenance, "interpretation")
    interpretation_id = _required_string(interpretation, "interpretation_id")
    mappings = _required_list(interpretation, "statement_rule_mappings")
    if len(mappings) > MAX_STATEMENT_MAPPINGS:
        raise ValueError(
            f"customer provenance exceeds maximum of {MAX_STATEMENT_MAPPINGS} statement mappings"
        )
    mapped_rule_ids: set[str] = set()
    mapped_statement_ids: set[str] = set()
    mapping_ids: set[str] = set()
    for index, mapping_value in enumerate(mappings):
        if not isinstance(mapping_value, dict):
            raise ValueError(f"statement_rule_mappings[{index}] must be an object")
        mapping = mapping_value
        _require_exact_fields(
            mapping,
            {"mapping_id", "statement_ids", "rule_ids"},
            f"statement_rule_mappings[{index}]",
        )
        mapped_statements = _required_string_list(mapping, "statement_ids")
        rule_ids = _required_string_list(mapping, "rule_ids")
        if len(mapped_statements) != 1:
            raise ValueError(
                f"statement_rule_mappings[{index}] must reference exactly one source statement"
            )
        if not rule_ids:
            raise ValueError(f"statement_rule_mappings[{index}] requires confirmed rule_ids")
        if len(rule_ids) > MAX_RULE_IDS_PER_MAPPING:
            raise ValueError(
                f"statement_rule_mappings[{index}] exceeds maximum rule IDs per mapping"
            )
        unknown = set(mapped_statements) - statement_ids
        if unknown:
            raise ValueError(f"statement_rule_mappings[{index}] references unknown statements: {sorted(unknown)}")
        statement_id = mapped_statements[0]
        if classifications[statement_id] != "enforced":
            raise ValueError(
                f"{classifications[statement_id]} source statement must not acquire enforceable rules"
            )
        if statement_id in mapped_statement_ids:
            raise ValueError(f"source statement has duplicate enforceable mappings: {statement_id}")
        expected_mapping_id = statement_mapping_id(mapped_statements, rule_ids)
        _require_equal(mapping.get("mapping_id"), expected_mapping_id, f"statement_rule_mappings[{index}] id")
        if expected_mapping_id in mapping_ids:
            raise ValueError(f"duplicate statement mapping identity: {expected_mapping_id}")
        mapping_ids.add(expected_mapping_id)
        mapped_statement_ids.add(statement_id)
        mapped_rule_ids.update(rule_ids)
    enforced_statement_ids = {
        statement_id
        for statement_id, classification in classifications.items()
        if classification == "enforced"
    }
    if mapped_statement_ids != enforced_statement_ids:
        raise ValueError("every enforced source statement requires exactly one confirmed-rule mapping")
    mapping_hash = canonical_sha256(mappings)
    _require_equal(interpretation.get("mapping_hash"), mapping_hash, "interpretation mapping_hash")

    resolution = _required_object(provenance, "resolution")
    resolution_id = _required_string(resolution, "resolution_id")
    resolutions = _required_list(resolution, "ambiguity_resolutions")
    if len(resolutions) > MAX_RESOLUTION_RECORDS:
        raise ValueError(
            f"customer provenance exceeds maximum of {MAX_RESOLUTION_RECORDS} resolution records"
        )
    resolution_ids: set[str] = set()
    ambiguity_ids: set[str] = set()
    for index, record_value in enumerate(resolutions):
        if not isinstance(record_value, dict):
            raise ValueError(f"ambiguity_resolutions[{index}] must be an object")
        record = record_value
        _require_exact_fields(
            record,
            {
                "resolution_id",
                "ambiguity_id",
                "statement_ids",
                "selected_decision",
                "resolved_by",
                "resolved_at",
            },
            f"ambiguity_resolutions[{index}]",
        )
        ambiguity_id = _required_string(record, "ambiguity_id")
        referenced_statements = _required_string_list(record, "statement_ids")
        if not referenced_statements:
            raise ValueError(f"ambiguity_resolutions[{index}] requires statement_ids")
        if len(referenced_statements) > MAX_STATEMENT_IDS_PER_RESOLUTION:
            raise ValueError(f"ambiguity_resolutions[{index}] references too many statements")
        unknown = set(referenced_statements) - statement_ids
        if unknown:
            raise ValueError(
                f"ambiguity_resolutions[{index}] references unknown statements: {sorted(unknown)}"
            )
        selected_decision = _required_string(record, "selected_decision")
        if not selected_decision.strip() or len(selected_decision) > MAX_RESOLUTION_DECISION_LENGTH:
            raise ValueError(f"ambiguity_resolutions[{index}] selected_decision is invalid")
        resolved_by = _required_string(record, "resolved_by")
        resolved_at = _required_string(record, "resolved_at")
        _validate_resolution_time(resolved_at, index)
        expected_record_id = resolution_record_id(
            ambiguity_id=ambiguity_id,
            statement_ids=referenced_statements,
            selected_decision=selected_decision,
            resolved_by=resolved_by,
            resolved_at=resolved_at,
        )
        _require_equal(
            record.get("resolution_id"),
            expected_record_id,
            f"ambiguity_resolutions[{index}] resolution_id",
        )
        if expected_record_id in resolution_ids:
            raise ValueError(f"duplicate resolution identity: {expected_record_id}")
        if ambiguity_id in ambiguity_ids:
            raise ValueError(f"duplicate ambiguity identity: {ambiguity_id}")
        resolution_ids.add(expected_record_id)
        ambiguity_ids.add(ambiguity_id)
    _require_equal(resolution_id, resolution_set_id(resolutions), "resolution set identity")
    resolution_hash = canonical_sha256(resolutions)
    _require_equal(resolution.get("resolution_hash"), resolution_hash, "resolution hash")

    semantic_commit = _required_object(bundle, "semantic_commit_bundle")
    semantic_commit_id = _required_string(semantic_commit, "semantic_commit_id")
    expected_semantic_hash = semantic_commit_hash(semantic_commit)
    _require_equal(semantic_commit.get("semantic_commit_hash"), expected_semantic_hash, "semantic commit hash")
    _require_equal(semantic_commit.get("source_id"), source_policy_id, "semantic commit source_id")
    _require_equal(semantic_commit.get("source_hash"), source_snapshot_hash, "semantic commit source_hash")
    _require_equal(
        semantic_commit.get("resolved_interpretations"),
        resolutions,
        "semantic commit ambiguity resolutions",
    )
    confirmed_rule_ids = _confirmed_rule_ids(semantic_commit)
    if confirmed_rule_ids != mapped_rule_ids:
        raise ValueError("sentence-to-rule mappings do not match confirmed semantic rule identities")
    semantic_bindings = {
        "source_policy_ref": source_ref,
        "source_snapshot_hash": source_snapshot_hash,
        "source_statements_hash": source_statements_hash,
        "interpretation_id": interpretation_id,
        "mapping_hash": mapping_hash,
        "resolution_id": resolution_id,
        "resolution_hash": resolution_hash,
    }
    _require_equal(semantic_commit.get("provenance_bindings"), semantic_bindings, "semantic commit provenance_bindings")
    if "bundle_hash" in semantic_commit:
        _require_equal(
            semantic_commit.get("bundle_hash"),
            _semantic_hash(semantic_commit),
            "semantic commit bundle_hash",
        )

    approval = _required_object(provenance, "approval_record")
    approval_id = _required_string(approval, "approval_id")
    _required_string(approval, "approved_by")
    _required_string(approval, "approved_at")
    _require_equal(
        approval.get("approved_semantic_commit_hash"),
        expected_semantic_hash,
        "approval approved_semantic_commit_hash",
    )
    approval_record_hash = hash_without_field(approval, "approval_record_hash")
    _require_equal(approval.get("approval_record_hash"), approval_record_hash, "approval record hash")

    compiled = _required_object(bundle, "compiled_authority_contract")
    compiled_from = _required_object(compiled, "compiled_from")
    _require_equal(compiled_from.get("semantic_commit_id"), semantic_commit_id, "compiled semantic_commit_id")
    _require_equal(compiled_from.get("semantic_commit_hash"), expected_semantic_hash, "compiled semantic_commit_hash")
    _require_equal(compiled_from.get("source_hash"), source_snapshot_hash, "compiled source_hash")
    expected_compiled_hash = compiled_contract_hash(compiled)
    _require_equal(compiled.get("contract_hash"), expected_compiled_hash, "compiled contract hash")
    contract_id = _required_string(compiled, "contract_id")
    contract_version = _required_string(compiled, "contract_version")
    authority_ref = f"{contract_id}@{contract_version}"
    _require_equal(compiled.get("authority_ref"), authority_ref, "compiled authority_ref")
    _require_equal(bundle.get("authority_ref"), authority_ref, "bundle authority_ref")
    _require_equal(bundle.get("contract_hash"), expected_compiled_hash, "bundle contract_hash")
    _require_equal(bundle.get("compiled_contract_hash"), expected_compiled_hash, "bundle compiled_contract_hash")
    _require_equal(bundle.get("semantic_commit_hash"), expected_semantic_hash, "bundle semantic_commit_hash")
    _require_equal(bundle.get("authority_contract"), compiled, "bundle authority_contract")

    version_binding = _required_object(provenance, "version_binding")
    _require_equal(version_binding.get("source_policy_ref"), source_ref, "version source_policy_ref")
    _require_equal(version_binding.get("authority_ref"), authority_ref, "version authority_ref")
    relationship = _required_string(version_binding, "relationship")
    if relationship not in VERSION_RELATIONSHIPS:
        raise ValueError(f"unsupported version relationship: {relationship}")
    version_binding_hash = hash_without_field(version_binding, "binding_hash")
    _require_equal(version_binding.get("binding_hash"), version_binding_hash, "version binding_hash")

    manifest = _required_object(bundle, "publication_manifest")
    _require_equal(bundle.get("publication_id"), manifest.get("publication_id"), "bundle publication_id")
    manifest_contract = _manifest_contract(manifest)
    _require_equal(manifest_contract.get("contract_id"), contract_id, "manifest contract_id")
    _require_equal(manifest_contract.get("contract_version"), contract_version, "manifest contract_version")
    _require_equal(manifest_contract.get("contract_hash"), expected_compiled_hash, "manifest contract_hash")
    _require_equal(manifest_contract.get("source_hash"), source_snapshot_hash, "manifest source_hash")

    authority_identity_hash = canonical_sha256(
        {
            "authority_id": contract_id,
            "authority_version": contract_version,
            "authority_ref": authority_ref,
        }
    )
    expected_immutable = {
        "provenance_profile": CUSTOMER_POLICY_PROFILE,
        "provenance_complete": True,
        "source_policy_id": source_policy_id,
        "source_revision": source_revision,
        "source_policy_ref": source_ref,
        "source_snapshot_hash": source_snapshot_hash,
        "source_statements_hash": source_statements_hash,
        "interpretation_id": interpretation_id,
        "mapping_hash": mapping_hash,
        "resolution_id": resolution_id,
        "resolution_hash": resolution_hash,
        "approval_id": approval_id,
        "approval_record_hash": approval_record_hash,
        "semantic_commit_id": semantic_commit_id,
        "semantic_commit_hash": expected_semantic_hash,
        "compiled_contract_id": contract_id,
        "compiled_contract_version": contract_version,
        "compiled_contract_ref": authority_ref,
        "compiled_contract_hash": expected_compiled_hash,
        "authority_id": contract_id,
        "authority_version": contract_version,
        "authority_ref": authority_ref,
        "authority_identity_hash": authority_identity_hash,
        "version_binding_hash": version_binding_hash,
    }
    immutable = _required_object(bundle, "immutable_inputs")
    _require_equal(immutable.get("authority_hash"), expected_compiled_hash, "immutable_inputs.authority_hash")
    _require_equal(immutable.get("manifest_hash"), canonical_sha256(manifest), "immutable_inputs.manifest_hash")
    preview = _required_object(bundle, "governance_impact_preview")
    _require_equal(immutable.get("preview_hash"), canonical_sha256(preview), "immutable_inputs.preview_hash")
    diff = bundle.get("authority_diff_impact")
    _require_equal(
        immutable.get("diff_hash"),
        canonical_sha256(diff) if isinstance(diff, dict) else None,
        "immutable_inputs.diff_hash",
    )
    packets = bundle.get("governance_review_packets")
    if not isinstance(packets, list):
        raise ValueError("governance_review_packets is required and must be an array")
    _require_equal(
        immutable.get("review_packet_hashes"),
        [canonical_sha256(packet) for packet in packets],
        "immutable_inputs.review_packet_hashes",
    )
    for field, expected in expected_immutable.items():
        _require_equal(immutable.get(field), expected, f"immutable_inputs.{field}")


def _receipt_provenance_bindings(bundle: dict[str, Any]) -> dict[str, Any]:
    immutable = bundle["immutable_inputs"]
    fields = [
        "provenance_profile",
        "provenance_complete",
        "source_policy_id",
        "source_revision",
        "source_policy_ref",
        "source_snapshot_hash",
        "source_statements_hash",
        "interpretation_id",
        "mapping_hash",
        "resolution_id",
        "resolution_hash",
        "approval_id",
        "approval_record_hash",
        "semantic_commit_id",
        "semantic_commit_hash",
        "compiled_contract_id",
        "compiled_contract_version",
        "compiled_contract_ref",
        "compiled_contract_hash",
        "authority_id",
        "authority_version",
        "authority_ref",
        "authority_identity_hash",
        "version_binding_hash",
    ]
    return {field: immutable[field] for field in fields}


def _confirmed_rule_ids(semantic_commit: dict[str, Any]) -> set[str]:
    meaning = semantic_commit.get("committed_semantic_meaning") or {}
    rules = meaning.get("confirmed_rules")
    if not isinstance(rules, list):
        raise ValueError("customer semantic commit requires a confirmed_rules array")
    result: set[str] = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"confirmed_rules[{index}] must be an object")
        rule_id = _required_string(rule, "rule_id")
        if rule_id in result:
            raise ValueError(f"duplicate confirmed rule identity: {rule_id}")
        result.add(rule_id)
    return result


def _manifest_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    contracts = manifest.get("contracts")
    if not isinstance(contracts, list) or len(contracts) != 1 or not isinstance(contracts[0], dict):
        raise ValueError("customer publication manifest requires exactly one contract")
    return contracts[0]


def _semantic_hash(value: Any) -> str:
    canonical = canonical_json(_without_compiler_hashes(value))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _without_compiler_hashes(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_compiler_hashes(item)
            for key, item in value.items()
            if key not in {"contract_hash", "bundle_hash"}
        }
    if isinstance(value, list):
        return [_without_compiler_hashes(item) for item in value]
    return value


def _decode_base64(value: str, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} must be canonical base64")
    return decoded


def _validate_resolution_time(value: str, index: int) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError(f"ambiguity_resolutions[{index}] resolved_at must be canonical UTC")
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError(
            f"ambiguity_resolutions[{index}] resolved_at must be canonical UTC"
        ) from exc


def _require_exact_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    missing = fields - set(value)
    extra = set(value) - fields
    if missing:
        raise ValueError(f"{label} is missing required fields: {sorted(missing)}")
    if extra:
        raise ValueError(f"{label} contains unsupported fields: {sorted(extra)}")


def _required_object(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = value.get(field)
    if not isinstance(result, dict):
        raise ValueError(f"{field} is required and must be an object")
    return result


def _required_list(value: dict[str, Any], field: str) -> list[Any]:
    result = value.get(field)
    if not isinstance(result, list):
        raise ValueError(f"{field} is required and must be an array")
    return result


def _required_string(value: dict[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{field} is required and must be a non-empty string")
    return result


def _required_integer(value: dict[str, Any], field: str) -> int:
    result = value.get(field)
    if not isinstance(result, int) or isinstance(result, bool):
        raise ValueError(f"{field} is required and must be an integer")
    return result


def _required_string_list(value: dict[str, Any], field: str) -> list[str]:
    result = value.get(field)
    if not isinstance(result, list) or any(not isinstance(item, str) or not item for item in result):
        raise ValueError(f"{field} is required and must be an array of non-empty strings")
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must contain unique values")
    return result


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} is missing or inconsistent")
