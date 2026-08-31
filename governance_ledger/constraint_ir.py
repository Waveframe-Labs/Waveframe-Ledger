"""Validation for Waveframe-owned deterministic policy artifacts.

The validators in this module are deliberately small, strict, and dependency
free.  JSON Schema files document the wire contracts; these runtime validators
enforce the semantic invariants needed before lowering and publication.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from governance_ledger.publication_provenance import canonical_sha256


CONSTRAINT_IR_V1 = "constraint_ir.v1"
RUNTIME_FACT_SCHEMA_V1 = "runtime_fact_schema.v1"

_HASH = re.compile(r"sha256:[a-f0-9]{64}\Z")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")
_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
_CANONICAL_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_DECIMAL = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d*[1-9])?\Z")
_FACT_TYPES = {"boolean", "decimal", "enum", "integer", "string", "string_set", "timestamp"}
_COMPARISONS = {"==", "!=", ">", ">=", "<", "<=", "contains", "starts_with"}
_EFFECTS = {"allow", "deny", "require"}


def artifact_hash(value: dict[str, Any], hash_field: str) -> str:
    """Return the canonical hash of an artifact without its self-hash field."""
    payload = copy.deepcopy(value)
    payload.pop(hash_field, None)
    return canonical_sha256(payload)


def finalize_runtime_fact_schema(value: dict[str, Any]) -> dict[str, Any]:
    """Return a copied runtime-fact schema with its canonical self-hash."""
    result = copy.deepcopy(value)
    result["schema_hash"] = artifact_hash(result, "schema_hash")
    validate_runtime_fact_schema(result)
    return result


def finalize_constraint_ir(value: dict[str, Any]) -> dict[str, Any]:
    """Assign deterministic constraint identities and the canonical IR hash."""
    result = copy.deepcopy(value)
    for constraint in result.get("constraints", []):
        if not isinstance(constraint, dict):
            continue
        core = copy.deepcopy(constraint)
        core.pop("constraint_id", None)
        constraint["constraint_id"] = "constraint-" + canonical_sha256(core).removeprefix(
            "sha256:"
        )
    result["ir_hash"] = artifact_hash(result, "ir_hash")
    return result


def validate_runtime_fact_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Validate ``runtime_fact_schema.v1`` and return a fact index."""
    _object(schema, "runtime fact schema")
    _exact(
        schema,
        {
            "schema_version",
            "schema_id",
            "schema_version_number",
            "name",
            "facts",
            "schema_hash",
        },
        "runtime fact schema",
    )
    if schema["schema_version"] != RUNTIME_FACT_SCHEMA_V1:
        raise ValueError(f"runtime fact schema must be {RUNTIME_FACT_SCHEMA_V1}")
    _portable(schema["schema_id"], "runtime fact schema schema_id")
    if not isinstance(schema["schema_version_number"], str) or not _SEMVER.fullmatch(
        schema["schema_version_number"]
    ):
        raise ValueError("runtime fact schema schema_version_number must be canonical semver")
    _nonempty(schema["name"], "runtime fact schema name")
    if not isinstance(schema["facts"], list) or not schema["facts"]:
        raise ValueError("runtime fact schema facts must be a non-empty array")
    facts: dict[str, dict[str, Any]] = {}
    for index, fact in enumerate(schema["facts"]):
        label = f"runtime fact schema facts[{index}]"
        _object(fact, label)
        _exact(
            fact,
            {
                "fact_id",
                "type",
                "enum_values",
                "canonical_unit",
                "required",
                "derivation",
                "comparison_operators",
            },
            label,
        )
        fact_id = fact["fact_id"]
        _fact_identity(fact_id, f"{label}.fact_id")
        if fact_id in facts:
            raise ValueError(f"runtime fact schema contains duplicate fact: {fact_id}")
        fact_type = fact["type"]
        if fact_type not in _FACT_TYPES:
            raise ValueError(f"{label}.type is unknown: {fact_type!r}")
        enum_values = fact["enum_values"]
        if fact_type == "enum":
            if (
                not isinstance(enum_values, list)
                or not enum_values
                or any(not isinstance(item, str) or not item for item in enum_values)
                or len(set(enum_values)) != len(enum_values)
            ):
                raise ValueError(f"{label}.enum_values must enumerate unique strings")
        elif enum_values is not None:
            raise ValueError(f"{label}.enum_values is only valid for enum facts")
        unit = fact["canonical_unit"]
        if unit is not None and (not isinstance(unit, str) or not unit):
            raise ValueError(f"{label}.canonical_unit must be null or a non-empty string")
        if not isinstance(fact["required"], bool):
            raise ValueError(f"{label}.required must be Boolean")
        derivation = fact["derivation"]
        if derivation is not None:
            _object(derivation, f"{label}.derivation")
            _exact(derivation, {"kind", "source"}, f"{label}.derivation")
            if derivation["kind"] not in {"proposal_field", "deterministic_expression"}:
                raise ValueError(f"{label}.derivation.kind is unknown")
            _nonempty(derivation["source"], f"{label}.derivation.source")
        operators = fact["comparison_operators"]
        if (
            not isinstance(operators, list)
            or not operators
            or len(set(operators)) != len(operators)
        ):
            raise ValueError(f"{label}.comparison_operators must be a non-empty unique array")
        unknown = set(operators) - _COMPARISONS
        if unknown:
            raise ValueError(f"{label} contains unknown comparison operators: {sorted(unknown)}")
        facts[fact_id] = fact
    _verify_hash(schema, "schema_hash", "runtime fact schema")
    return facts


def validate_constraint_ir(
    constraint_ir: dict[str, Any],
    *,
    domain_pack: dict[str, Any],
) -> dict[str, Any]:
    """Strictly validate typed Constraint IR against one exact domain pack."""
    from governance_ledger.domain_packs import validate_domain_pack

    validate_domain_pack(domain_pack)
    _object(constraint_ir, "Constraint IR")
    _exact(
        constraint_ir,
        {
            "schema_version",
            "domain_pack",
            "runtime_fact_schema_hash",
            "constraints",
            "ir_hash",
        },
        "Constraint IR",
    )
    if constraint_ir["schema_version"] != CONSTRAINT_IR_V1:
        raise ValueError(f"Constraint IR must be {CONSTRAINT_IR_V1}")
    pack_ref = constraint_ir["domain_pack"]
    _object(pack_ref, "Constraint IR domain_pack")
    _exact(
        pack_ref,
        {"domain_pack_id", "domain_pack_version", "domain_pack_hash"},
        "Constraint IR domain_pack",
    )
    expected_ref = {
        "domain_pack_id": domain_pack["domain_pack_id"],
        "domain_pack_version": domain_pack["domain_pack_version"],
        "domain_pack_hash": domain_pack["canonical_hash"],
    }
    if pack_ref != expected_ref:
        raise ValueError("Constraint IR domain-pack identity, version, or hash does not match")
    runtime_schema = domain_pack["runtime_fact_schema"]
    if constraint_ir["runtime_fact_schema_hash"] != runtime_schema["schema_hash"]:
        raise ValueError("Constraint IR runtime fact schema hash does not match the domain pack")
    facts = validate_runtime_fact_schema(runtime_schema)
    constraints = constraint_ir["constraints"]
    if not isinstance(constraints, list) or not constraints:
        raise ValueError("Constraint IR must contain at least one enforceable rule")
    identities: set[str] = set()
    conflict_index: dict[str, str] = {}
    for index, constraint in enumerate(constraints):
        label = f"Constraint IR constraints[{index}]"
        _validate_constraint(constraint, label, domain_pack, facts)
        constraint_id = constraint["constraint_id"]
        if constraint_id in identities:
            raise ValueError(f"Constraint IR contains duplicate constraint: {constraint_id}")
        identities.add(constraint_id)
        core = copy.deepcopy(constraint)
        core.pop("constraint_id")
        expected_id = "constraint-" + canonical_sha256(core).removeprefix("sha256:")
        if constraint_id != expected_id:
            raise ValueError(f"{label}.constraint_id is not canonical")
        signature_payload = {
            key: constraint[key]
            for key in ("subject", "acting_role", "action", "resource", "condition")
        }
        signature = canonical_sha256(signature_payload)
        prior = conflict_index.get(signature)
        effect = constraint["effect"]
        if prior is not None and prior != effect and {prior, effect} <= {"allow", "deny"}:
            raise ValueError("Constraint IR contains contradictory allow and deny effects")
        conflict_index[signature] = effect
    _verify_hash(constraint_ir, "ir_hash", "Constraint IR")
    return {
        "valid": True,
        "constraint_count": len(constraints),
        "required_runtime_facts": sorted(
            {fact for item in constraints for fact in item["required_runtime_facts"]}
        ),
        "ir_hash": constraint_ir["ir_hash"],
    }


def validate_runtime_fact_compatibility(
    constraint_ir: dict[str, Any],
    runtime_fact_schema: dict[str, Any],
    *,
    domain_pack: dict[str, Any],
) -> dict[str, Any]:
    """Return actionable compatibility diagnostics without weakening the IR."""
    validate_constraint_ir(constraint_ir, domain_pack=domain_pack)
    selected_facts = validate_runtime_fact_schema(runtime_fact_schema)
    expected_facts = {
        item["fact_id"]: item for item in domain_pack["runtime_fact_schema"]["facts"]
    }
    diagnostics: list[dict[str, str]] = []
    if runtime_fact_schema["schema_hash"] != constraint_ir["runtime_fact_schema_hash"]:
        diagnostics.append(
            {
                "code": "runtime_schema_hash_mismatch",
                "message": "The selected runtime schema is not the schema bound by this Constraint IR.",
            }
        )
    for constraint in constraint_ir["constraints"]:
        constraint_id = constraint["constraint_id"]
        for fact_id in constraint["required_runtime_facts"]:
            actual = selected_facts.get(fact_id)
            if actual is None:
                diagnostics.append(
                    {
                        "code": "missing_runtime_fact",
                        "constraint_id": constraint_id,
                        "fact_id": fact_id,
                        "message": (
                            f"This rule requires {fact_id}, but the selected runtime schema "
                            "does not provide it."
                        ),
                    }
                )
                continue
            expected = expected_facts[fact_id]
            for field, description in (
                ("type", "type"),
                ("canonical_unit", "canonical unit"),
                ("comparison_operators", "supported comparison operators"),
            ):
                if actual[field] != expected[field]:
                    diagnostics.append(
                        {
                            "code": f"runtime_fact_{field}_mismatch",
                            "constraint_id": constraint_id,
                            "fact_id": fact_id,
                            "message": (
                                f"This rule requires {fact_id} with {description} "
                                f"{expected[field]!r}, but the selected runtime schema provides "
                                f"{actual[field]!r}."
                            ),
                        }
                    )
    return {
        "compatible": not diagnostics,
        "constraint_ir_hash": constraint_ir["ir_hash"],
        "runtime_fact_schema_hash": runtime_fact_schema["schema_hash"],
        "diagnostics": diagnostics,
    }


def _validate_constraint(
    constraint: dict[str, Any],
    label: str,
    pack: dict[str, Any],
    facts: dict[str, dict[str, Any]],
) -> None:
    _object(constraint, label)
    _exact(
        constraint,
        {
            "constraint_id",
            "subject",
            "acting_role",
            "action",
            "resource",
            "effect",
            "condition",
            "obligations",
            "exceptions",
            "required_runtime_facts",
        },
        label,
    )
    if not isinstance(constraint["constraint_id"], str) or not re.fullmatch(
        r"constraint-[a-f0-9]{64}", constraint["constraint_id"]
    ):
        raise ValueError(f"{label}.constraint_id is invalid")
    subject = constraint["subject"]
    _object(subject, f"{label}.subject")
    _exact(subject, {"kind", "value"}, f"{label}.subject")
    if subject["kind"] == "subject_kind":
        if subject["value"] not in pack["subject_kinds"]:
            raise ValueError(f"{label}.subject contains an unknown subject symbol")
        referenced = {"actor.subject_kind"}
    elif subject["kind"] == "principal_id":
        _nonempty(subject["value"], f"{label}.subject.value")
        referenced = {"actor.principal_id"}
    else:
        raise ValueError(f"{label}.subject contains an unknown selector kind")
    role = constraint["acting_role"]
    if role is not None:
        _object(role, f"{label}.acting_role")
        _exact(role, {"kind", "value"}, f"{label}.acting_role")
        if role["kind"] != "role" or role["value"] not in pack["role_kinds"]:
            raise ValueError(f"{label}.acting_role contains an unknown role symbol")
    if constraint["action"] not in pack["supported_actions"]:
        raise ValueError(f"{label}.action contains an unknown action symbol")
    resource = constraint["resource"]
    _object(resource, f"{label}.resource")
    _exact(resource, {"kind", "match", "value"}, f"{label}.resource")
    if resource["kind"] not in pack["resource_kinds"]:
        raise ValueError(f"{label}.resource contains an unknown resource kind")
    if resource["match"] not in {"any", "exact", "prefix"}:
        raise ValueError(f"{label}.resource.match is unknown")
    if resource["match"] == "any":
        if resource["value"] is not None:
            raise ValueError(f"{label}.resource.value must be null for an any selector")
    else:
        _repository_path(resource["value"], resource["match"], f"{label}.resource.value")
    if constraint["effect"] not in _EFFECTS:
        raise ValueError(f"{label}.effect is unknown")
    referenced |= {"proposal.action", "proposal.resource.kind"}
    if resource["match"] != "any":
        referenced.add("proposal.resource.path")
    if role is not None:
        referenced.add("actor.role")
    referenced |= _validate_condition(constraint["condition"], f"{label}.condition", facts)
    obligations = constraint["obligations"]
    _object(obligations, f"{label}.obligations")
    _exact(
        obligations,
        {"approvals", "evidence", "separation_of_duties"},
        f"{label}.obligations",
    )
    for index, item in enumerate(obligations["approvals"]):
        item_label = f"{label}.obligations.approvals[{index}]"
        _object(item, item_label)
        _exact(item, {"minimum", "role", "evidence_fact"}, item_label)
        if not isinstance(item["minimum"], int) or isinstance(item["minimum"], bool) or item["minimum"] < 1:
            raise ValueError(f"{item_label}.minimum must be a positive integer")
        if item["role"] not in pack["role_kinds"]:
            raise ValueError(f"{item_label}.role contains an unknown role symbol")
        _fact_identity(item["evidence_fact"], f"{item_label}.evidence_fact")
        referenced.add(item["evidence_fact"])
    for index, item in enumerate(obligations["evidence"]):
        item_label = f"{label}.obligations.evidence[{index}]"
        _object(item, item_label)
        _exact(item, {"evidence_type", "fact"}, item_label)
        if item["evidence_type"] not in pack["vocabulary"]["evidence_types"]:
            raise ValueError(f"{item_label}.evidence_type contains an unknown symbol")
        _fact_identity(item["fact"], f"{item_label}.fact")
        referenced.add(item["fact"])
    for index, item in enumerate(obligations["separation_of_duties"]):
        item_label = f"{label}.obligations.separation_of_duties[{index}]"
        _object(item, item_label)
        _exact(item, {"roles", "principal_facts"}, item_label)
        if (
            not isinstance(item["roles"], list)
            or len(item["roles"]) < 2
            or len(set(item["roles"])) != len(item["roles"])
            or set(item["roles"]) - set(pack["role_kinds"])
        ):
            raise ValueError(f"{item_label}.roles must contain distinct pack roles")
        if not isinstance(item["principal_facts"], list) or len(item["principal_facts"]) != len(item["roles"]):
            raise ValueError(f"{item_label}.principal_facts must align with roles")
        for fact_id in item["principal_facts"]:
            _fact_identity(fact_id, f"{item_label}.principal_facts")
            referenced.add(fact_id)
    if constraint["effect"] == "require" and role is None and not any(obligations.values()):
        raise ValueError(f"{label} require effect needs an acting-role or obligation")
    exceptions = constraint["exceptions"]
    if not isinstance(exceptions, list):
        raise ValueError(f"{label}.exceptions must be an array")
    exception_ids: set[str] = set()
    for index, exception in enumerate(exceptions):
        item_label = f"{label}.exceptions[{index}]"
        _object(exception, item_label)
        _exact(exception, {"exception_id", "effect", "condition"}, item_label)
        _portable(exception["exception_id"], f"{item_label}.exception_id")
        if exception["exception_id"] in exception_ids:
            raise ValueError(f"{label}.exceptions contains duplicate identities")
        exception_ids.add(exception["exception_id"])
        if exception["effect"] not in _EFFECTS or exception["effect"] == constraint["effect"]:
            raise ValueError(f"{item_label}.effect must explicitly override the parent effect")
        if exception["condition"] is None:
            raise ValueError(f"{item_label}.condition is required for explicit precedence")
        referenced |= _validate_condition(exception["condition"], f"{item_label}.condition", facts)
    required = constraint["required_runtime_facts"]
    if (
        not isinstance(required, list)
        or required != sorted(set(required))
        or any(not isinstance(item, str) for item in required)
    ):
        raise ValueError(f"{label}.required_runtime_facts must be sorted and unique")
    unavailable = set(required) - set(facts)
    if unavailable:
        fact_id = sorted(unavailable)[0]
        raise ValueError(
            f"This rule requires {fact_id}, but the selected runtime schema does not provide it."
        )
    if set(required) != referenced:
        missing = sorted(referenced - set(required))
        extra = sorted(set(required) - referenced)
        raise ValueError(
            f"{label}.required_runtime_facts must exactly declare referenced facts; "
            f"missing={missing}, extra={extra}"
        )


def _validate_condition(
    condition: Any, label: str, facts: dict[str, dict[str, Any]]
) -> set[str]:
    if condition is None:
        return set()
    _object(condition, label)
    kind = condition.get("kind")
    if kind == "group":
        _exact(condition, {"kind", "operator", "operands"}, label)
        operator = condition["operator"]
        if operator not in {"all", "any", "not"}:
            raise ValueError(f"{label}.operator is unknown")
        operands = condition["operands"]
        if not isinstance(operands, list) or not operands:
            raise ValueError(f"{label}.operands must be a non-empty array")
        if operator == "not" and len(operands) != 1:
            raise ValueError(f"{label} not group requires exactly one operand")
        referenced: set[str] = set()
        for index, operand in enumerate(operands):
            referenced |= _validate_condition(operand, f"{label}.operands[{index}]", facts)
        return referenced
    if kind == "comparison":
        _exact(condition, {"kind", "operator", "fact", "literal"}, label)
        fact_id = condition["fact"]
        if fact_id not in facts:
            raise ValueError(
                f"This rule requires {fact_id}, but the selected runtime schema does not provide it."
            )
        fact = facts[fact_id]
        operator = condition["operator"]
        if operator not in _COMPARISONS:
            raise ValueError(f"{label}.operator is unknown")
        if operator not in fact["comparison_operators"]:
            raise ValueError(f"{label} uses unsupported operator {operator!r} for {fact_id}")
        _validate_literal(condition["literal"], f"{label}.literal", fact)
        return {fact_id}
    raise ValueError(f"{label} must use an explicit group or comparison node")


def _validate_literal(literal: dict[str, Any], label: str, fact: dict[str, Any]) -> None:
    _object(literal, label)
    _exact(literal, {"type", "value", "unit"}, label)
    if literal["type"] != fact["type"]:
        raise ValueError(
            f"{label}.type {literal['type']!r} is incompatible with fact type {fact['type']!r}"
        )
    if literal["unit"] != fact["canonical_unit"]:
        raise ValueError(
            f"{label}.unit {literal['unit']!r} is incompatible with canonical unit "
            f"{fact['canonical_unit']!r}"
        )
    value = literal["value"]
    fact_type = fact["type"]
    if fact_type == "boolean" and not isinstance(value, bool):
        raise ValueError(f"{label}.value must be Boolean")
    if fact_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError(f"{label}.value must be an integer")
    if fact_type == "decimal" and (not isinstance(value, str) or not _DECIMAL.fullmatch(value)):
        raise ValueError(f"{label}.value must be a canonical decimal string")
    if fact_type in {"string", "enum"} and (not isinstance(value, str) or not value):
        raise ValueError(f"{label}.value must be a non-empty typed string")
    if fact_type == "enum" and value not in fact["enum_values"]:
        raise ValueError(f"{label}.value is not in the fact enum")
    if fact_type == "string_set" and (
        not isinstance(value, list)
        or value != sorted(set(value))
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError(f"{label}.value must be a sorted unique string array")
    if fact_type == "timestamp":
        if not isinstance(value, str) or not _CANONICAL_UTC.fullmatch(value):
            raise ValueError(f"{label}.value must be canonical UTC")
        try:
            datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError(f"{label}.value must be canonical UTC") from exc


def _repository_path(value: Any, match: str, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty repository-relative path")
    if value.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", value) or "\\" in value:
        raise ValueError(f"{label} must be a repository-relative forward-slash path")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} contains a control character")
    if match == "prefix":
        if not value.endswith("/"):
            raise ValueError(f"{label} prefix must end with a slash")
        segments = value[:-1].split("/")
    else:
        if value.endswith("/"):
            raise ValueError(f"{label} exact path must not end with a slash")
        segments = value.split("/")
    if not segments or any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError(f"{label} contains an unsafe path segment")


def _verify_hash(value: dict[str, Any], field: str, label: str) -> None:
    supplied = value[field]
    if not isinstance(supplied, str) or not _HASH.fullmatch(supplied):
        raise ValueError(f"{label} {field} must be canonical SHA-256")
    if supplied != artifact_hash(value, field):
        raise ValueError(f"{label} {field} does not match canonical content")


def _object(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        raise ValueError(f"{label} fields are invalid; unknown={unknown}, missing={missing}")


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _portable(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value) or "@" in value:
        raise ValueError(f"{label} must be a portable identity without @")
    return value


def _fact_identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", value
    ):
        raise ValueError(f"{label} must be a canonical dotted fact identity")
    return value
