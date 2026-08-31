"""Released v0.6 repository-policy compatibility interpretation and publication.

This module is intentionally filesystem-free and Guard-free.  Its exact grammar
is retained for legacy APIs and as the implementation behind the built-in
repository-changes domain pack; it is not a universal company-policy grammar.
"""

from __future__ import annotations

import base64
import copy
import re
from datetime import datetime
from typing import Any

from compiler.compile_policy import compile_policy

from governance_ledger.authority_contract import compute_contract_hash, with_authority_identity
from governance_ledger.publication_provenance import (
    CUSTOMER_POLICY_PROFILE,
    MAX_RESOLUTION_RECORDS,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_STATEMENTS,
    MAX_STATEMENT_MAPPINGS,
    bytes_sha256,
    canonical_sha256,
    hash_without_field,
    resolution_record_id,
    resolution_set_id,
    source_statement_id,
    statement_mapping_id,
    validate_authority_bundle,
    validate_publication_receipt,
)
from governance_ledger.semantics.compiler import build_semantic_commit_bundle
from governance_ledger.semantics.preview import build_governance_impact_preview
from governance_ledger.semantics.publication import build_authority_bundle, build_publication_receipt


INTERPRETATION_DRAFT_V1 = "customer_policy_interpretation_draft.v1"
FINALIZATION_RESULT_V1 = "customer_policy_authority_finalization.v1"
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")
_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
_CANONICAL_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_ROLE = re.compile(r"(.+?) may be made only by ([A-Za-z][A-Za-z -]*s)\.\Z")
_PREFIX_ALLOW = re.compile(r"Agents may modify files under ([^\s]+)\.\Z")
_PREFIX_DENY = re.compile(r"Agents must not modify files under ([^\s]+)\.\Z")
_EXACT_ALLOW = re.compile(r"Agents may modify ([^\s]+)\.\Z")
_EXACT_DENY = re.compile(r"Agents must not modify ([^\s]+)\.\Z")
_APPROVAL = re.compile(
    r"(?:Transfers|Purchases|Payments|Invoices|Requests) "
    r"(above|over|at least|below|under) \$(\d+(?:\.\d{1,2})?) require "
    r"([A-Za-z][A-Za-z -]*) approval\.\Z"
)
_SOD = re.compile(r"(?:The )?[Rr]equester and approver must be separate\.\Z")
_AMBIGUOUS = re.compile(
    r"\b(normally|usually|generally|appropriate|relevant|reasonable|unless necessary|"
    r"as needed|if needed|sensitive|critical|authorized|designated|certain|some)\b",
    re.IGNORECASE,
)
_NORMATIVE = re.compile(r"\b(may|must|shall|should|cannot|require|requires|required|only|forbid|forbidden|prohibit|prohibited)\b", re.IGNORECASE)


def _interpret_customer_policy_v0_6_compatibility(
    source_bytes: bytes,
    *,
    source_policy_id: str,
    source_revision: str,
    authority_id: str,
    authority_version: str,
) -> dict[str, Any]:
    """Run the released v0.6 repository-sentence compatibility interpreter.

    Only the documented v0.6 sentence grammar is recognized.  Similar-looking
    text is retained as unsupported or requires_resolution, never inferred.
    """
    exact_source = _validate_source(source_bytes)
    source_policy_id = _identity(source_policy_id, "source_policy_id")
    source_revision = _identity(source_revision, "source_revision")
    authority_id = _identity(authority_id, "authority_id")
    if not isinstance(authority_version, str) or not _SEMVER.fullmatch(authority_version):
        raise ValueError("authority_version must be a canonical semantic version")

    source_ref = f"{source_policy_id}@{source_revision}"
    authority_ref = f"{authority_id}@{authority_version}"
    statements: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    rule_by_statement: dict[str, list[dict[str, Any]]] = {}
    ambiguities: list[dict[str, Any]] = []

    spans = _partition_source(exact_source)
    if len(spans) > MAX_SOURCE_STATEMENTS:
        raise ValueError(f"policy exceeds maximum of {MAX_SOURCE_STATEMENTS} source statements")
    for start, end in spans:
        statement_bytes = exact_source[start:end]
        statement_hash = bytes_sha256(statement_bytes)
        statement_id = source_statement_id(
            source_policy_id=source_policy_id,
            source_revision=source_revision,
            start_byte=start,
            end_byte=end,
            statement_hash=statement_hash,
        )
        text = statement_bytes.decode("utf-8").strip()
        classification, proposed = _interpret_statement(text)
        proposed = [_with_rule_id(rule) for rule in proposed]
        rule_by_statement[statement_id] = proposed
        rules.extend(proposed)
        statement = {
            "statement_id": statement_id,
            "start_byte": start,
            "end_byte": end,
            "statement_bytes_base64": base64.b64encode(statement_bytes).decode("ascii"),
            "statement_hash": statement_hash,
            "classification": classification,
            "proposed_rule_ids": [rule["rule_id"] for rule in proposed],
        }
        statements.append(statement)
        if classification == "requires_resolution":
            ambiguities.append(_lexical_ambiguity(statement_id, text, proposed))

    _require_unique_rules(rules)
    conflicts = _conflict_components(statements, rule_by_statement)
    for component in conflicts:
        for statement in statements:
            if statement["statement_id"] in component:
                statement["classification"] = "requires_resolution"
        ambiguities.append(_conflict_ambiguity(component, statements, rule_by_statement))

    ambiguities.sort(key=lambda item: (min(item["statement_ids"]), item["ambiguity_id"]))
    if len(ambiguities) > MAX_RESOLUTION_RECORDS:
        raise ValueError(f"policy exceeds maximum of {MAX_RESOLUTION_RECORDS} ambiguities")
    mappings = _mappings(statements)
    if len(mappings) > MAX_STATEMENT_MAPPINGS:
        raise ValueError(f"policy exceeds maximum of {MAX_STATEMENT_MAPPINGS} statement mappings")

    unresolved_ambiguity_count = len(ambiguities)
    enforceable_rule_count = len(
        {rule_id for mapping in mappings for rule_id in mapping["rule_ids"]}
    )
    draft: dict[str, Any] = {
        "schema_version": INTERPRETATION_DRAFT_V1,
        "source_policy": {
            "source_policy_id": source_policy_id,
            "source_revision": source_revision,
            "source_policy_ref": source_ref,
            "content_encoding": "base64",
            "source_bytes_base64": base64.b64encode(exact_source).decode("ascii"),
            "snapshot_hash": bytes_sha256(exact_source),
        },
        "authority": {
            "authority_id": authority_id,
            "authority_version": authority_version,
            "authority_ref": authority_ref,
        },
        "version_binding": {
            "source_policy_ref": source_ref,
            "authority_ref": authority_ref,
            "relationship": "publishes_as",
        },
        "source_statements": statements,
        "proposed_rules": rules,
        "statement_rule_mappings": mappings,
        "ambiguities": ambiguities,
        "status": {
            "statement_classification_complete": True,
            "interpretation_complete": unresolved_ambiguity_count == 0,
            "requires_resolution_count": sum(
                statement["classification"] == "requires_resolution" for statement in statements
            ),
            "unresolved_ambiguity_count": unresolved_ambiguity_count,
            "enforceable_rule_count": enforceable_rule_count,
            "ready_for_finalization": (
                unresolved_ambiguity_count == 0 and enforceable_rule_count > 0
            ),
            "publication_ready": False,
        },
    }
    draft["interpretation_id"] = "interpretation-" + canonical_sha256(draft).removeprefix("sha256:")
    draft["draft_hash"] = canonical_sha256(draft)
    return draft


def interpret_customer_policy(
    source_bytes: bytes,
    *,
    source_policy_id: str,
    source_revision: str,
    authority_id: str,
    authority_version: str,
) -> dict[str, Any]:
    """Compatibility API for the exact released v0.6 behavior and hashes.

    New integrations should select a domain pack through
    :func:`interpret_policy_with_domain_pack`.  This wrapper deliberately does
    not add pack metadata to its artifacts because doing so would change v0.6
    canonical identities.
    """
    return _interpret_customer_policy_v0_6_compatibility(
        source_bytes,
        source_policy_id=source_policy_id,
        source_revision=source_revision,
        authority_id=authority_id,
        authority_version=authority_version,
    )


def interpret_customer_policy_text(source_text: str, **identities: str) -> dict[str, Any]:
    """Encode a string as UTF-8 without normalizing any characters or newlines."""
    if not isinstance(source_text, str):
        raise TypeError("source_text must be a string")
    return interpret_customer_policy(source_text.encode("utf-8"), **identities)


def _finalize_customer_policy_authority_v0_6_compatibility(
    interpretation_draft: dict[str, Any],
    *,
    resolutions: list[dict[str, Any]],
    approval_id: str,
    approved_by: str,
    approved_at: str,
    committed_by: str,
    committed_at: str,
    publication_id: str,
    published_by: str,
    published_at: str,
) -> dict[str, Any]:
    """Finalize a reconstructed interpretation using only explicit human inputs."""
    supplied = copy.deepcopy(interpretation_draft)
    reconstructed = _reconstruct_draft(supplied)
    if supplied != reconstructed:
        raise ValueError("interpretation draft is modified or inconsistent with its exact source bytes")
    supplied_resolutions = copy.deepcopy(resolutions)
    final_statements, confirmed_rules, resolution_records = _apply_resolutions(
        reconstructed, supplied_resolutions
    )
    if not confirmed_rules:
        raise ValueError(
            "customer-policy authority cannot publish without at least one enforceable confirmed rule"
        )
    mappings = _mappings(final_statements)
    if {rule_id for mapping in mappings for rule_id in mapping["rule_ids"]} != {
        rule["rule_id"] for rule in confirmed_rules
    }:
        raise ValueError("mapped rule union must equal the confirmed semantic rule set")
    _require_no_rule_conflicts(confirmed_rules)

    source = reconstructed["source_policy"]
    authority = reconstructed["authority"]
    provenance_statements = [
        {key: value for key, value in statement.items() if key != "proposed_rule_ids"}
        for statement in final_statements
    ]
    final_mappings = mappings
    interpretation = {
        "interpretation_id": reconstructed["interpretation_id"],
        "statement_rule_mappings": final_mappings,
        "mapping_hash": canonical_sha256(final_mappings),
    }
    resolution = {
        "resolution_id": resolution_set_id(resolution_records),
        "ambiguity_resolutions": resolution_records,
        "resolution_hash": canonical_sha256(resolution_records),
    }
    semantic_bindings = {
        "source_policy_ref": source["source_policy_ref"],
        "source_snapshot_hash": source["snapshot_hash"],
        "source_statements_hash": canonical_sha256(provenance_statements),
        "interpretation_id": interpretation["interpretation_id"],
        "mapping_hash": interpretation["mapping_hash"],
        "resolution_id": resolution["resolution_id"],
        "resolution_hash": resolution["resolution_hash"],
    }
    approved_at = _utc(approved_at, "approved_at")
    committed_at = _utc(committed_at, "committed_at")
    published_at = _utc(published_at, "published_at")
    _validate_publication_chronology(
        resolution_records,
        approved_at=approved_at,
        committed_at=committed_at,
        published_at=published_at,
    )
    compiler_input = _compiler_input(authority, confirmed_rules)
    normalized_meaning = _normalized_semantic_meaning(
        authority, confirmed_rules, compiler_input
    )
    reconciliation = {
        "schema_version": "governance_semantic_reconciliation.v1",
        "source_id": source["source_policy_id"],
        "source_hash": source["snapshot_hash"],
        "extraction_id": reconstructed["interpretation_id"],
        "operator_interpretation_decisions": resolution_records,
        "unresolved_ambiguities": [],
        "semantic_conflicts": [],
        "interpretation_completeness_posture": "complete",
        "final_normalized_semantic_meaning": normalized_meaning,
    }
    semantic_commit = build_semantic_commit_bundle(
        reconciliation,
        committed_by=_nonempty(committed_by, "committed_by"),
        committed_at=committed_at,
        provenance_bindings=semantic_bindings,
    )
    compiled = _compile(compiler_input, semantic_commit, reconstructed)
    _validate_cross_artifact_rule_equivalence(
        confirmed_rules=confirmed_rules,
        normalized_meaning=normalized_meaning,
        semantic_commit=semantic_commit,
        compiler_input=compiler_input,
        compiled_contract=compiled,
    )
    approval_record = {
        "approval_id": _identity(approval_id, "approval_id"),
        "approved_by": _nonempty(approved_by, "approved_by"),
        "approved_at": approved_at,
        "approved_semantic_commit_hash": semantic_commit["semantic_commit_hash"],
    }
    approval_record["approval_record_hash"] = canonical_sha256(approval_record)
    version_binding = copy.deepcopy(reconstructed["version_binding"])
    version_binding["binding_hash"] = canonical_sha256(version_binding)
    customer_provenance = {
        "profile": CUSTOMER_POLICY_PROFILE,
        "provenance_complete": True,
        "source_policy": copy.deepcopy(source),
        "source_statements": provenance_statements,
        "interpretation": interpretation,
        "resolution": resolution,
        "approval_record": approval_record,
        "version_binding": version_binding,
    }
    publication_id = _identity(publication_id, "publication_id")
    published_by = _nonempty(published_by, "published_by")
    manifest = {
        "schema_version": "publication_manifest.v1",
        "publication_id": publication_id,
        "published_at": published_at,
        "published_by": published_by,
        "contracts": [
            {
                "contract_id": compiled["contract_id"],
                "contract_version": compiled["contract_version"],
                "contract_hash": compiled["contract_hash"],
                "source_hash": source["snapshot_hash"],
                "path": f"contracts/{compiled['contract_id']}-{compiled['contract_version']}.contract.json",
            }
        ],
        "reviews": [{"path": f"reviews/{source['source_policy_id']}.interpretation.json"}],
        "snapshots": [{"path": f"snapshots/{source['source_policy_id']}.source.json"}],
    }
    preview = build_governance_impact_preview(compiled)
    bundle = build_authority_bundle(
        authority_contract=compiled,
        publication_manifest=manifest,
        governance_impact_preview=preview,
        semantic_commit_bundle=semantic_commit,
        compiled_authority_contract=compiled,
        customer_policy_provenance=customer_provenance,
    )
    receipt = build_publication_receipt(authority_bundle=bundle, published_at=published_at)
    validate_authority_bundle(bundle)
    validate_publication_receipt(bundle, receipt)
    validated_interpretation = copy.deepcopy(reconstructed)
    validated_interpretation["source_statements"] = final_statements
    validated_interpretation["statement_rule_mappings"] = final_mappings
    validated_interpretation["status"] = {
        "statement_classification_complete": True,
        "interpretation_complete": True,
        "requires_resolution_count": 0,
        "unresolved_ambiguity_count": 0,
        "enforceable_rule_count": len(confirmed_rules),
        "ready_for_finalization": True,
        "publication_ready": True,
    }
    validated_interpretation["final_interpretation_hash"] = canonical_sha256(
        {key: value for key, value in validated_interpretation.items() if key != "final_interpretation_hash"}
    )
    return {
        "schema_version": FINALIZATION_RESULT_V1,
        "status": {
            "statement_classification_complete": True,
            "interpretation_complete": True,
            "ready_for_finalization": True,
            "provenance_complete": True,
            "publication_ready": True,
        },
        "validated_interpretation": validated_interpretation,
        "resolution_set": resolution,
        "approval_record": approval_record,
        "semantic_commit_bundle": semantic_commit,
        "canonical_compiler_input": compiler_input,
        "compiled_authority_contract": compiled,
        "governance_impact_preview": preview,
        "publication_manifest": manifest,
        "customer_policy_provenance": customer_provenance,
        "authority_bundle": bundle,
        "publication_receipt": receipt,
        "canonical_identities": {
            "source_policy_ref": source["source_policy_ref"],
            "interpretation_id": interpretation["interpretation_id"],
            "resolution_id": resolution["resolution_id"],
            "approval_id": approval_record["approval_id"],
            "semantic_commit_id": semantic_commit["semantic_commit_id"],
            "authority_ref": compiled["authority_ref"],
            "publication_id": manifest["publication_id"],
            "receipt_id": receipt["receipt_id"],
        },
        "canonical_hashes": {
            "source_snapshot_hash": source["snapshot_hash"],
            "source_statements_hash": semantic_bindings["source_statements_hash"],
            "draft_hash": reconstructed["draft_hash"],
            "interpretation_hash": validated_interpretation["final_interpretation_hash"],
            "mapping_hash": interpretation["mapping_hash"],
            "resolution_hash": resolution["resolution_hash"],
            "approval_record_hash": approval_record["approval_record_hash"],
            "version_binding_hash": version_binding["binding_hash"],
            "semantic_commit_hash": semantic_commit["semantic_commit_hash"],
            "compiled_contract_hash": compiled["contract_hash"],
            "publication_manifest_hash": canonical_sha256(manifest),
            "authority_bundle_hash": canonical_sha256(bundle),
            "publication_receipt_hash": receipt["receipt_hash"],
        },
    }


def finalize_customer_policy_authority(
    interpretation_draft: dict[str, Any],
    *,
    resolutions: list[dict[str, Any]],
    approval_id: str,
    approved_by: str,
    approved_at: str,
    committed_by: str,
    committed_at: str,
    publication_id: str,
    published_by: str,
    published_at: str,
) -> dict[str, Any]:
    """Compatibility API for the exact released v0.6 publication path."""
    return _finalize_customer_policy_authority_v0_6_compatibility(
        interpretation_draft,
        resolutions=resolutions,
        approval_id=approval_id,
        approved_by=approved_by,
        approved_at=approved_at,
        committed_by=committed_by,
        committed_at=committed_at,
        publication_id=publication_id,
        published_by=published_by,
        published_at=published_at,
    )


def _validate_source(value: bytes) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError("source_bytes must be exact bytes")
    if not value or len(value) > MAX_SOURCE_BYTES:
        raise ValueError(f"source policy must contain 1 to {MAX_SOURCE_BYTES} UTF-8 bytes")
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("source policy must contain valid UTF-8 text") from exc
    if not text.strip():
        raise ValueError("source policy must contain non-empty UTF-8 text")
    return bytes(value)


def _identity(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value) or "@" in value:
        raise ValueError(f"{label} must be a non-ambiguous portable identity without @")
    return value


def _nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _utc(value: str, label: str) -> str:
    _utc_datetime(value, label)
    return value


def _utc_datetime(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not _CANONICAL_UTC.fullmatch(value):
        raise ValueError(f"{label} must be canonical UTC (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be canonical UTC (YYYY-MM-DDTHH:MM:SSZ)") from exc


def _validate_publication_chronology(
    resolution_records: list[dict[str, Any]],
    *,
    approved_at: str,
    committed_at: str,
    published_at: str,
) -> None:
    approval_time = _utc_datetime(approved_at, "approved_at")
    commit_time = _utc_datetime(committed_at, "committed_at")
    publication_time = _utc_datetime(published_at, "published_at")
    for index, record in enumerate(resolution_records):
        resolution_time = _utc_datetime(
            record["resolved_at"], f"resolutions[{index}].resolved_at"
        )
        if resolution_time > approval_time:
            raise ValueError(
                f"resolutions[{index}].resolved_at must be less than or equal to approved_at"
            )
    if approval_time > commit_time:
        raise ValueError("approved_at must be less than or equal to committed_at")
    if commit_time > publication_time:
        raise ValueError("committed_at must be less than or equal to published_at")


def _partition_source(source: bytes) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    while index < len(source):
        byte = source[index]
        boundary = byte == 10 or (
            byte in b".!?"
            and (index + 1 == len(source) or source[index + 1] in b" \t\r\n")
        )
        index += 1
        if not boundary:
            continue
        while index < len(source) and source[index] in b" \t\r\n":
            index += 1
        spans.append((start, index))
        start = index
    if start < len(source):
        spans.append((start, len(source)))
    return spans


def _interpret_statement(text: str) -> tuple[str, list[dict[str, Any]]]:
    if _AMBIGUOUS.search(text) and _NORMATIVE.search(text):
        return "requires_resolution", _recover_ambiguous_rules(text)
    return _interpret_supported_statement(text)


def _interpret_supported_statement(text: str) -> tuple[str, list[dict[str, Any]]]:
    match = _ROLE.fullmatch(text)
    if match:
        role = _role_slug(match.group(2)[:-1])
        return "enforced", [{"rule_type": "required_actor_role", "role": role}]
    for pattern, effect, target_match in (
        (_PREFIX_ALLOW, "allow", "prefix"),
        (_PREFIX_DENY, "deny", "prefix"),
        (_EXACT_ALLOW, "allow", "exact"),
        (_EXACT_DENY, "deny", "exact"),
    ):
        match = pattern.fullmatch(text)
        if match:
            value = _target(match.group(1), target_match)
            return "enforced", [
                {"rule_type": "target", "effect": effect, "match": target_match, "value": value}
            ]
    match = _APPROVAL.fullmatch(text)
    if match:
        operator = {"above": ">", "over": ">", "at least": ">=", "below": "<", "under": "<"}[match.group(1)]
        amount_text = match.group(2)
        amount: int | float = int(amount_text) if "." not in amount_text else float(amount_text)
        return "enforced", [{
            "rule_type": "approval_threshold",
            "field": "amount",
            "operator": operator,
            "value": amount,
            "requires_role": _role_slug(match.group(3)),
        }]
    if _SOD.fullmatch(text):
        return "enforced", [{"rule_type": "separation_of_duties", "roles": ["requester", "approver"]}]
    return ("unsupported", []) if _NORMATIVE.search(text) else ("informational", [])


def _recover_ambiguous_rules(text: str) -> list[dict[str, Any]]:
    modifiers = list(_AMBIGUOUS.finditer(text))
    if len(modifiers) != 1:
        return []
    modifier = modifiers[0]
    start, end = modifier.span()
    if end < len(text) and text[end] == " ":
        end += 1
    elif start > 0 and text[start - 1] == " ":
        start -= 1
    candidate = text[:start] + text[end:]
    try:
        classification, rules = _interpret_supported_statement(candidate)
    except ValueError:
        return []
    return rules if classification == "enforced" and len(rules) == 1 else []


def _role_slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _target(value: str, match: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("target must be a non-empty repository-relative path")
    if value.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", value) or "\\" in value:
        raise ValueError("target must be a repository-relative forward-slash path")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("target must not contain NUL or control characters")
    if match == "prefix":
        if not value.endswith("/"):
            raise ValueError("prefix target must use a deterministic trailing slash")
        segments = value[:-1].split("/")
    else:
        if value.endswith("/"):
            raise ValueError("exact target must not end with a slash")
        segments = value.split("/")
    if not segments or any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("target contains an unsafe empty or traversal segment")
    return value


def _with_rule_id(rule: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(rule)
    result["rule_id"] = "rule-" + canonical_sha256(rule).removeprefix("sha256:")
    return result


def _require_unique_rules(rules: list[dict[str, Any]]) -> None:
    # Duplicates are retained for conflict resolution, but identity collisions for
    # different meanings would violate the canonical identifier contract.
    meanings: dict[str, dict[str, Any]] = {}
    for rule in rules:
        rule_id = rule["rule_id"]
        prior = meanings.get(rule_id)
        if prior is not None and prior != rule:
            raise ValueError("canonical rule identity collision")
        meanings[rule_id] = rule


def _mappings(statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for statement in statements:
        rule_ids = statement.get("proposed_rule_ids") or []
        if statement["classification"] != "enforced":
            continue
        if not rule_ids:
            raise ValueError("an enforced statement requires one or more confirmed rules")
        statement_ids = [statement["statement_id"]]
        result.append({
            "mapping_id": statement_mapping_id(statement_ids, rule_ids),
            "statement_ids": statement_ids,
            "rule_ids": rule_ids,
        })
    return result


def _lexical_ambiguity(
    statement_id: str,
    text: str,
    proposed_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    core = {"ambiguity_type": "ambiguous_language", "statement_ids": [statement_id], "text_hash": canonical_sha256(text)}
    ambiguity_id = "ambiguity-" + canonical_sha256(core).removeprefix("sha256:")
    options = []
    if len(proposed_rules) == 1:
        rule = proposed_rules[0]
        options.append(
            _option(
                ambiguity_id,
                "enforce_unqualified_meaning",
                "Enforce the deterministically recovered unqualified meaning",
                [{
                    "statement_id": statement_id,
                    "classification": "enforced",
                    "rule_ids": [rule["rule_id"]],
                }],
                _rule_consequence(rule),
            )
        )
    options.extend(
        [
            _option(
                ambiguity_id,
                "retain_unsupported",
                "Retain as unsupported",
                [{"statement_id": statement_id, "classification": "unsupported", "rule_ids": []}],
                "No enforceable rule is produced; the statement remains visible as unsupported.",
            ),
            _option(
                ambiguity_id,
                "retain_informational",
                "Retain as informational",
                [{"statement_id": statement_id, "classification": "informational", "rule_ids": []}],
                "No enforceable rule is produced; the statement remains visible as informational.",
            ),
        ]
    )
    return {
        "ambiguity_id": ambiguity_id,
        "ambiguity_type": "ambiguous_language",
        "statement_ids": [statement_id],
        "summary": "Normative language contains a term whose meaning is outside the deterministic grammar.",
        "options": options,
    }


def _rules_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["rule_id"] == right["rule_id"]:
        return True
    if left["rule_type"] != "target" or right["rule_type"] != "target" or left["effect"] == right["effect"]:
        return False
    if left["match"] == right["match"] == "exact":
        return left["value"] == right["value"]
    if left["match"] == "prefix" and right["match"] == "exact":
        return right["value"].startswith(left["value"])
    if left["match"] == "exact" and right["match"] == "prefix":
        return left["value"].startswith(right["value"])
    return left["value"].startswith(right["value"]) or right["value"].startswith(left["value"])


def _conflict_components(
    statements: list[dict[str, Any]], rule_by_statement: dict[str, list[dict[str, Any]]]
) -> list[set[str]]:
    edges: dict[str, set[str]] = {}
    candidates = [
        (statement["statement_id"], rule)
        for statement in statements
        if statement["classification"] == "enforced"
        for rule in rule_by_statement[statement["statement_id"]]
    ]
    for index, (left_id, left) in enumerate(candidates):
        for right_id, right in candidates[index + 1 :]:
            if left_id != right_id and _rules_conflict(left, right):
                edges.setdefault(left_id, set()).add(right_id)
                edges.setdefault(right_id, set()).add(left_id)
    components = []
    unseen = set(edges)
    while unseen:
        seed = min(unseen)
        component = set()
        pending = [seed]
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(edges.get(current, set()) - component)
        unseen -= component
        components.append(component)
    return sorted(components, key=lambda value: min(value))


def _conflict_ambiguity(
    component: set[str], statements: list[dict[str, Any]], rule_by_statement: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    ordered = [s["statement_id"] for s in statements if s["statement_id"] in component]
    core = {"ambiguity_type": "rule_conflict", "statement_ids": ordered}
    ambiguity_id = "ambiguity-" + canonical_sha256(core).removeprefix("sha256:")
    options = []
    for retained in ordered:
        outcomes = [
            {
                "statement_id": statement_id,
                "classification": "enforced" if statement_id == retained else "unsupported",
                "rule_ids": [rule["rule_id"] for rule in rule_by_statement[statement_id]] if statement_id == retained else [],
            }
            for statement_id in ordered
        ]
        retained_rules = rule_by_statement[retained]
        options.append(
            _option(
                ambiguity_id,
                f"retain_{retained}",
                "Retain one stated meaning",
                outcomes,
                "Enforce only: " + "; ".join(
                    _rule_consequence(rule) for rule in retained_rules
                ),
            )
        )
    options.append(_option(
        ambiguity_id,
        "retain_none",
        "Retain every conflicting statement as unsupported",
        [{"statement_id": statement_id, "classification": "unsupported", "rule_ids": []} for statement_id in ordered],
        "No enforceable rule is produced by the conflicting statements.",
    ))
    return {
        "ambiguity_id": ambiguity_id,
        "ambiguity_type": "rule_conflict",
        "statement_ids": ordered,
        "summary": "Duplicate or contradictory rules require an explicit bounded selection; no precedence is inferred.",
        "options": options,
    }


def _option(
    ambiguity_id: str,
    key: str,
    label: str,
    outcomes: list[dict[str, Any]],
    enforcement_consequence: str,
) -> dict[str, Any]:
    option_id = "option-" + canonical_sha256({"ambiguity_id": ambiguity_id, "key": key, "statement_outcomes": outcomes}).removeprefix("sha256:")
    return {
        "option_id": option_id,
        "label": label,
        "enforcement_consequence": enforcement_consequence,
        "statement_outcomes": outcomes,
    }


def _rule_consequence(rule: dict[str, Any]) -> str:
    rule_type = rule["rule_type"]
    if rule_type == "target":
        return f"Enforce {rule['match']} {rule['effect']} for {rule['value']}."
    if rule_type == "required_actor_role":
        return f"Require acting role {rule['role']}."
    if rule_type == "approval_threshold":
        return (
            f"Require {rule['requires_role']} approval when {rule['field']} "
            f"{rule['operator']} {rule['value']}."
        )
    if rule_type == "separation_of_duties":
        return "Require separation of duties for " + ", ".join(rule["roles"]) + "."
    raise ValueError(f"unsupported rule consequence type: {rule_type}")


def _reconstruct_draft(draft: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(draft, dict) or draft.get("schema_version") != INTERPRETATION_DRAFT_V1:
        raise ValueError(f"interpretation_draft must be {INTERPRETATION_DRAFT_V1}")
    try:
        encoded = draft["source_policy"]["source_bytes_base64"]
        source = base64.b64decode(encoded.encode("ascii"), validate=True)
        if base64.b64encode(source).decode("ascii") != encoded:
            raise ValueError
        return interpret_customer_policy(
            source,
            source_policy_id=draft["source_policy"]["source_policy_id"],
            source_revision=draft["source_policy"]["source_revision"],
            authority_id=draft["authority"]["authority_id"],
            authority_version=draft["authority"]["authority_version"],
        )
    except (KeyError, AttributeError, UnicodeError, ValueError) as exc:
        raise ValueError("interpretation draft cannot be reconstructed from canonical source and identities") from exc


def _apply_resolutions(
    draft: dict[str, Any], resolutions: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(resolutions, list) or len(resolutions) > MAX_RESOLUTION_RECORDS:
        raise ValueError(f"resolutions must be an array with at most {MAX_RESOLUTION_RECORDS} records")
    expected = {item["ambiguity_id"]: item for item in draft["ambiguities"]}
    supplied: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(resolutions):
        if not isinstance(record, dict) or set(record) != {"ambiguity_id", "selected_option_id", "resolved_by", "resolved_at"}:
            raise ValueError(f"resolutions[{index}] is malformed")
        ambiguity_id = _nonempty(record["ambiguity_id"], f"resolutions[{index}].ambiguity_id")
        if ambiguity_id not in expected:
            raise ValueError(f"resolutions[{index}] references an unknown ambiguity")
        if ambiguity_id in supplied:
            raise ValueError(f"duplicate resolution for ambiguity: {ambiguity_id}")
        supplied[ambiguity_id] = record
    missing = set(expected) - set(supplied)
    if missing:
        raise ValueError(f"finalization requires a resolution for every ambiguity: {sorted(missing)}")
    statements = copy.deepcopy(draft["source_statements"])
    by_id = {item["statement_id"]: item for item in statements}
    rule_index = {rule["rule_id"]: rule for rule in draft["proposed_rules"]}
    records = []
    for supplied_record in resolutions:
        ambiguity = expected[supplied_record["ambiguity_id"]]
        option_id = _nonempty(supplied_record["selected_option_id"], "selected_option_id")
        options = {item["option_id"]: item for item in ambiguity["options"]}
        if option_id not in options:
            raise ValueError("a resolution may only select an interpreter-produced option")
        option = options[option_id]
        for outcome in option["statement_outcomes"]:
            statement = by_id[outcome["statement_id"]]
            statement["classification"] = outcome["classification"]
            statement["proposed_rule_ids"] = list(outcome["rule_ids"])
        values = {
            "ambiguity_id": ambiguity["ambiguity_id"],
            "statement_ids": list(ambiguity["statement_ids"]),
            "selected_decision": option_id,
            "resolved_by": _nonempty(supplied_record["resolved_by"], "resolved_by"),
            "resolved_at": _utc(supplied_record["resolved_at"], "resolved_at"),
        }
        records.append({"resolution_id": resolution_record_id(**values), **values})
    unresolved = [item["statement_id"] for item in statements if item["classification"] == "requires_resolution"]
    if unresolved:
        raise ValueError(f"finalization cannot retain unresolved statements: {unresolved}")
    rules = []
    seen = set()
    for statement in statements:
        if statement["classification"] != "enforced":
            statement["proposed_rule_ids"] = []
        for rule_id in statement["proposed_rule_ids"]:
            if rule_id not in rule_index:
                raise ValueError("resolution attempted free-form rule injection")
            if rule_id not in seen:
                rules.append(copy.deepcopy(rule_index[rule_id]))
                seen.add(rule_id)
    return statements, rules, records


def _require_no_rule_conflicts(rules: list[dict[str, Any]]) -> None:
    for index, left in enumerate(rules):
        for right in rules[index + 1 :]:
            if _rules_conflict(left, right):
                raise ValueError("confirmed rules contain an unresolved duplicate or contradiction")


def _rule_model(rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "required_actor_roles": sorted(
            rule["role"]
            for rule in rules
            if rule["rule_type"] == "required_actor_role"
        ),
        "target_rules": {
            "allow": [
                {"match": rule["match"], "value": rule["value"]}
                for rule in rules
                if rule["rule_type"] == "target" and rule["effect"] == "allow"
            ],
            "deny": [
                {"match": rule["match"], "value": rule["value"]}
                for rule in rules
                if rule["rule_type"] == "target" and rule["effect"] == "deny"
            ],
        },
        "approval_thresholds": [
            {key: rule[key] for key in ("field", "operator", "value", "requires_role")}
            for rule in rules
            if rule["rule_type"] == "approval_threshold"
        ],
        "separation_of_duties_constraints": [
            list(rule["roles"])
            for rule in rules
            if rule["rule_type"] == "separation_of_duties"
        ],
    }


def _normalized_semantic_meaning(
    authority: dict[str, Any],
    confirmed_rules: list[dict[str, Any]],
    compiler_input: dict[str, Any],
) -> dict[str, Any]:
    model = _rule_model(confirmed_rules)
    return {
        "contract_id": authority["authority_id"],
        "contract_version": authority["authority_version"],
        "governed_targets": sorted(
            rule["value"]
            for rule in confirmed_rules
            if rule["rule_type"] == "target"
        ),
        "governed_operations": ["modify"]
        if model["target_rules"]["allow"] or model["target_rules"]["deny"]
        else [],
        **model,
        "confirmed_rules": copy.deepcopy(confirmed_rules),
        "canonical_compiler_input": copy.deepcopy(compiler_input),
    }


def _validate_cross_artifact_rule_equivalence(
    *,
    confirmed_rules: list[dict[str, Any]],
    normalized_meaning: dict[str, Any],
    semantic_commit: dict[str, Any],
    compiler_input: dict[str, Any],
    compiled_contract: dict[str, Any],
) -> None:
    model = _rule_model(confirmed_rules)
    if normalized_meaning.get("confirmed_rules") != confirmed_rules:
        raise ValueError("normalized semantic meaning does not match confirmed rules")
    if normalized_meaning.get("canonical_compiler_input") != compiler_input:
        raise ValueError("normalized semantic meaning does not match canonical compiler input")
    for field, expected in model.items():
        if normalized_meaning.get(field) != expected:
            raise ValueError(f"normalized semantic meaning {field} is inconsistent")
    if "approver_roles" in normalized_meaning:
        raise ValueError("required actor roles must not be projected into approver_roles")
    if semantic_commit.get("committed_semantic_meaning") != normalized_meaning:
        raise ValueError("semantic commit meaning is inconsistent with normalized meaning")

    compiled_actor_roles = (
        compiled_contract.get("authority_requirements") or {}
    ).get("required_roles", [])
    if compiled_actor_roles != model["required_actor_roles"]:
        raise ValueError("compiled actor roles are inconsistent with confirmed rules")
    compiled_targets = compiled_contract.get("target_requirements") or {
        "allow": [],
        "deny": [],
    }
    if compiled_targets != model["target_rules"]:
        raise ValueError("compiled target requirements are inconsistent with confirmed rules")
    compiled_thresholds = (
        compiled_contract.get("approval_requirements") or {}
    ).get("thresholds", [])
    if compiled_thresholds != model["approval_thresholds"]:
        raise ValueError("compiled approval thresholds are inconsistent with confirmed rules")
    compiled_separation = (compiled_contract.get("invariants") or {}).get(
        "separation_of_duties", []
    )
    if compiled_separation != model["separation_of_duties_constraints"]:
        raise ValueError("compiled separation-of-duties constraints are inconsistent")


def _compiler_input(authority: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_id": authority["authority_id"],
        "contract_version": authority["authority_version"],
    }
    model = _rule_model(rules)
    roles = model["required_actor_roles"]
    if roles:
        payload["authority"] = {"required_roles": roles}
    allow = model["target_rules"]["allow"]
    deny = model["target_rules"]["deny"]
    if allow or deny:
        payload["targets"] = {"allow": allow, "deny": deny}
    thresholds = model["approval_thresholds"]
    if thresholds:
        payload["approvals"] = {"thresholds": thresholds}
    constraints = [
        {"type": "separation_of_duties", "roles": roles}
        for roles in model["separation_of_duties_constraints"]
    ]
    if constraints:
        payload["constraints"] = constraints
    return payload


def _compile(
    compiler_input: dict[str, Any], semantic_commit: dict[str, Any], draft: dict[str, Any]
) -> dict[str, Any]:
    canonical_output = compile_policy(copy.deepcopy(compiler_input))
    lineage = {
        "schema_version": "governance_authority_lineage.v1",
        "source_hash": draft["source_policy"]["snapshot_hash"],
        "compilation_report_hash": draft["draft_hash"],
        "review_id": draft["interpretation_id"],
    }
    compiled = with_authority_identity(
        canonical_output, lineage, schema_version="compiled_authority_contract.v1"
    )
    compiled["authority_ref"] = draft["authority"]["authority_ref"]
    compiled["compiled_from"] = {
        "schema_version": semantic_commit["schema_version"],
        "semantic_commit_id": semantic_commit["semantic_commit_id"],
        "semantic_commit_hash": semantic_commit["semantic_commit_hash"],
        "source_hash": draft["source_policy"]["snapshot_hash"],
        "resolved_interpretation_count": len(semantic_commit["resolved_interpretations"]),
    }
    compiled["contract_hash"] = "sha256:" + compute_contract_hash(compiled)
    return compiled
