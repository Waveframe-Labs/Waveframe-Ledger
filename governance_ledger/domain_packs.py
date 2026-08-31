"""Installed deterministic domain-pack artifacts and trust bindings.

A pack is canonical data bound to one exact, locally installed deterministic
compiler implementation. Pack data never loads executable plugins or remote code.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from governance_ledger.constraint_ir import (
    artifact_hash,
    finalize_runtime_fact_schema,
    is_trusted_format_validator,
    validate_runtime_fact_schema,
)

DOMAIN_PACK_V1 = "domain_pack.v1"
REPOSITORY_CHANGES_PACK_ID = "repository-changes"
REPOSITORY_CHANGES_PACK_VERSION = "1.0.0"
REPOSITORY_GRAMMAR_ID = "waveframe.repository-changes.grammar.v1"
REPOSITORY_LOWERING_ID = "waveframe.repository-changes.lowering.v1"
REPOSITORY_PATH_FORMAT_ID = "waveframe.repository-changes.format.repository-relative-path.v1"
ACTING_ROLE_EMITTER_ID = "waveframe.repository-changes.emitter.acting-role.v1"
EXACT_PATH_EMITTER_ID = "waveframe.repository-changes.emitter.exact-path-access.v1"
PREFIX_PATH_EMITTER_ID = "waveframe.repository-changes.emitter.prefix-path-access.v1"

_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")
_FACT_TYPES = {"boolean", "decimal", "enum", "integer", "string", "string_set", "timestamp"}
_MATCH_MODES = {"any", "exact", "prefix"}
_TRUSTED_COMPILERS = {
    (REPOSITORY_GRAMMAR_ID, "1.0.0"): {
        "domain_packs": {(REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION)},
        "emitters": {ACTING_ROLE_EMITTER_ID, EXACT_PATH_EMITTER_ID, PREFIX_PATH_EMITTER_ID},
        "formats": {REPOSITORY_PATH_FORMAT_ID},
        "lowering": (REPOSITORY_LOWERING_ID, "1.0.0"),
    }
}


def list_builtin_domain_packs() -> list[dict[str, Any]]:
    return [
        {
            "domain_pack_id": pack["domain_pack_id"],
            "domain_pack_version": pack["domain_pack_version"],
            "name": pack["name"],
            "description": pack["description"],
            "canonical_hash": pack["canonical_hash"],
        }
        for _, pack in sorted(_BUILTIN_PACKS.items())
    ]


def get_builtin_domain_pack(domain_pack_id: str, domain_pack_version: str) -> dict[str, Any]:
    key = (domain_pack_id, domain_pack_version)
    if key not in _BUILTIN_PACKS:
        raise ValueError(f"unknown built-in domain pack version: {domain_pack_id}@{domain_pack_version}")
    result = copy.deepcopy(_BUILTIN_PACKS[key])
    validate_domain_pack(result)
    return result


def validate_domain_pack(pack: dict[str, Any]) -> dict[str, Any]:
    """Validate canonical pack data and its installed compiler trust binding."""
    _object(pack, "domain pack")
    _exact(
        pack,
        {
            "schema_version", "domain_pack_id", "domain_pack_version", "name", "description",
            "supported_actions", "resource_kinds", "resource_contracts", "subject_kinds",
            "role_kinds", "vocabulary", "synonyms", "types_and_units",
            "runtime_fact_schema", "grammar_compiler", "allowed_mapping_controls",
            "semantic_validation_rules", "compiler_lowering", "test_vectors", "canonical_hash",
        },
        "domain pack",
    )
    if pack["schema_version"] != DOMAIN_PACK_V1:
        raise ValueError(f"domain pack must be {DOMAIN_PACK_V1}")
    _portable(pack["domain_pack_id"], "domain_pack_id")
    _semver(pack["domain_pack_version"], "domain_pack_version")
    _nonempty(pack["name"], "domain pack name")
    _nonempty(pack["description"], "domain pack description")
    for field in ("supported_actions", "resource_kinds", "subject_kinds", "role_kinds"):
        _symbols(pack[field], f"domain pack {field}")

    vocabulary = pack["vocabulary"]
    _object(vocabulary, "domain pack vocabulary")
    _exact(vocabulary, {"effects", "resource_matches", "evidence_types"}, "domain pack vocabulary")
    _symbols(vocabulary["effects"], "domain pack effects")
    if vocabulary["effects"] != ["allow", "deny", "require"]:
        raise ValueError("domain pack effects must use canonical allow, deny, require ordering")
    _symbols(vocabulary["resource_matches"], "domain pack resource matches")
    if set(vocabulary["resource_matches"]) - _MATCH_MODES:
        raise ValueError("domain pack contains unknown resource match modes")
    if not isinstance(vocabulary["evidence_types"], list) or len(set(vocabulary["evidence_types"])) != len(vocabulary["evidence_types"]):
        raise ValueError("domain pack evidence_types must be a unique string array")

    runtime_facts = validate_runtime_fact_schema(pack["runtime_fact_schema"])
    resource_contracts = pack["resource_contracts"]
    if not isinstance(resource_contracts, list) or not resource_contracts:
        raise ValueError("domain pack resource_contracts must be non-empty")
    contract_kinds: list[str] = []
    for index, contract in enumerate(resource_contracts):
        label = f"domain pack resource_contracts[{index}]"
        _object(contract, label)
        _exact(
            contract,
            {"resource_kind", "permitted_match_modes", "value_type", "enum_values", "null_allowed", "format_id", "value_fact_id"},
            label,
        )
        if contract["resource_kind"] not in pack["resource_kinds"]:
            raise ValueError(f"{label}.resource_kind is outside resource_kinds")
        contract_kinds.append(contract["resource_kind"])
        modes = contract["permitted_match_modes"]
        if not isinstance(modes, list) or not modes or len(set(modes)) != len(modes) or set(modes) - _MATCH_MODES:
            raise ValueError(f"{label}.permitted_match_modes is invalid")
        value_type = contract["value_type"]
        if value_type not in _FACT_TYPES:
            raise ValueError(f"{label}.value_type is unknown")
        if value_type == "enum":
            _symbols(contract["enum_values"], f"{label}.enum_values")
        elif contract["enum_values"] is not None:
            raise ValueError(f"{label}.enum_values is only valid for enum resources")
        if not isinstance(contract["null_allowed"], bool):
            raise ValueError(f"{label}.null_allowed must be Boolean")
        format_id = contract["format_id"]
        if format_id is not None and not is_trusted_format_validator(format_id):
            raise ValueError(f"{label} requires unavailable format validator: {format_id}")
        value_fact_id = contract["value_fact_id"]
        if value_fact_id is not None and value_fact_id not in runtime_facts:
            raise ValueError(f"{label}.value_fact_id is unavailable in the runtime schema")
        if not contract["null_allowed"] and value_fact_id is None:
            raise ValueError(f"{label}.value_fact_id is required for non-null resource values")
    if sorted(contract_kinds) != sorted(pack["resource_kinds"]) or len(set(contract_kinds)) != len(contract_kinds):
        raise ValueError("resource_contracts must define every resource kind exactly once")

    declared_types: set[str] = set()
    if not isinstance(pack["types_and_units"], list) or not pack["types_and_units"]:
        raise ValueError("domain pack types_and_units must be non-empty")
    for index, item in enumerate(pack["types_and_units"]):
        label = f"domain pack types_and_units[{index}]"
        _object(item, label)
        _exact(item, {"type", "canonical_units"}, label)
        if item["type"] not in _FACT_TYPES or item["type"] in declared_types:
            raise ValueError(f"{label}.type is unknown or duplicated")
        declared_types.add(item["type"])
        if not isinstance(item["canonical_units"], list) or any(not isinstance(unit, str) or not unit for unit in item["canonical_units"]):
            raise ValueError(f"{label}.canonical_units must be strings")
    if any(contract["value_type"] not in declared_types for contract in resource_contracts):
        raise ValueError("resource contract uses a type absent from types_and_units")

    grammar = pack["grammar_compiler"]
    _identity_version(grammar, "domain pack grammar_compiler", "compiler_id", "compiler_version")
    trust = _TRUSTED_COMPILERS.get((grammar["compiler_id"], grammar["compiler_version"]))
    if trust is None:
        raise ValueError("domain pack requires an unavailable trusted grammar/compiler")
    if (pack["domain_pack_id"], pack["domain_pack_version"]) not in trust["domain_packs"]:
        raise ValueError("domain pack identity is not bound to the selected trusted grammar/compiler")
    for contract in resource_contracts:
        format_id = contract["format_id"]
        if format_id is not None and format_id not in trust["formats"]:
            raise ValueError(
                f"resource contract requires a format validator not bound to the selected compiler: {format_id}"
            )
    lowering = pack["compiler_lowering"]
    _identity_version(lowering, "domain pack compiler_lowering", "lowering_id", "lowering_version")
    if (lowering["lowering_id"], lowering["lowering_version"]) != trust["lowering"]:
        raise ValueError("domain pack requires an unavailable compiler lowering")

    controls = pack["allowed_mapping_controls"]
    if not isinstance(controls, list) or not controls:
        raise ValueError("domain pack allowed_mapping_controls must be non-empty")
    control_ids: set[str] = set()
    for index, control in enumerate(controls):
        label = f"domain pack allowed_mapping_controls[{index}]"
        _object(control, label)
        _exact(control, {"control_id", "name", "description", "selection_schema", "emitter_id"}, label)
        _portable(control["control_id"], f"{label}.control_id")
        if control["control_id"] in control_ids:
            raise ValueError("domain pack contains duplicate mapping control identities")
        control_ids.add(control["control_id"])
        _nonempty(control["name"], f"{label}.name")
        _nonempty(control["description"], f"{label}.description")
        if control["emitter_id"] not in trust["emitters"]:
            raise ValueError(f"{label} requires unavailable emitter: {control['emitter_id']}")
        selection_schema = control["selection_schema"]
        _object(selection_schema, f"{label}.selection_schema")
        for field_name, field in selection_schema.items():
            _portable(field_name, f"{label} selection field")
            _object(field, f"{label}.selection_schema.{field_name}")
            _exact(field, {"type", "enum_values", "canonical_unit", "format_id"}, f"{label}.selection_schema.{field_name}")
            if field["type"] not in _FACT_TYPES:
                raise ValueError(f"{label}.selection_schema.{field_name}.type is unknown")
            if field["type"] == "enum":
                _symbols(field["enum_values"], f"{label}.selection_schema.{field_name}.enum_values")
            elif field["enum_values"] is not None:
                raise ValueError(f"{label}.{field_name}.enum_values is only valid for enum")
            if field["canonical_unit"] is not None and (not isinstance(field["canonical_unit"], str) or not field["canonical_unit"]):
                raise ValueError(f"{label}.{field_name}.canonical_unit is invalid")
            format_id = field["format_id"]
            if format_id is not None and (format_id not in trust["formats"] or not is_trusted_format_validator(format_id)):
                raise ValueError(f"{label} requires unavailable format validator: {format_id}")

    synonyms = pack["synonyms"]
    _object(synonyms, "domain pack synonyms")
    scoped = set(pack["supported_actions"]) | set(pack["resource_kinds"]) | set(pack["subject_kinds"]) | set(pack["role_kinds"]) | {s for values in vocabulary.values() for s in values}
    for canonical, aliases in synonyms.items():
        if canonical not in scoped:
            raise ValueError(f"domain pack synonym is outside scoped vocabulary: {canonical}")
        _symbols(aliases, f"domain pack synonyms.{canonical}")
    _symbols(pack["semantic_validation_rules"], "domain pack semantic_validation_rules")
    _validate_vectors(pack["test_vectors"])
    if pack["canonical_hash"] != artifact_hash(pack, "canonical_hash"):
        raise ValueError("domain-pack canonical hash does not match canonical content")
    installed = globals().get("_BUILTIN_PACKS", {}).get(
        (pack["domain_pack_id"], pack["domain_pack_version"])
    )
    if installed is not None and pack["canonical_hash"] != installed["canonical_hash"]:
        raise ValueError("domain-pack content does not match the installed immutable version")
    return {"valid": True, "domain_pack_id": pack["domain_pack_id"], "domain_pack_version": pack["domain_pack_version"], "canonical_hash": pack["canonical_hash"]}


def mapping_control_index(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    validate_domain_pack(pack)
    return {item["control_id"]: copy.deepcopy(item) for item in pack["allowed_mapping_controls"]}


def _repository_changes_pack() -> dict[str, Any]:
    roles = ["repository-maintainer", "repository-reviewer", "security-reviewer"]
    resources = ["repository_change", "repository_path"]
    runtime = finalize_runtime_fact_schema(
        {
            "schema_version": "runtime_fact_schema.v1",
            "schema_id": "repository-changes-runtime",
            "schema_version_number": "1.0.0",
            "name": "Repository change proposal facts",
            "facts": [
                _fact("actor.subject_kind", "enum", ["agent"], None, True, "/actor/subject_kind", ["==", "!="]),
                _fact("actor.principal_id", "string", None, None, False, "/actor/principal_id", ["==", "!="]),
                _fact("actor.role", "enum", roles, None, False, "/actor/role", ["==", "!="]),
                _fact("proposal.action", "enum", ["modify"], None, True, "/action", ["==", "!="]),
                _fact("proposal.resource.kind", "enum", resources, None, True, "/resource/kind", ["==", "!="]),
                _fact("proposal.resource.path", "string", None, None, False, "/resource/path", ["==", "!=", "starts_with"]),
            ],
        }
    )
    pack: dict[str, Any] = {
        "schema_version": DOMAIN_PACK_V1,
        "domain_pack_id": REPOSITORY_CHANGES_PACK_ID,
        "domain_pack_version": REPOSITORY_CHANGES_PACK_VERSION,
        "name": "Repository changes",
        "description": "Deterministic repository-change policy grammar and guided controls.",
        "supported_actions": ["modify"],
        "resource_kinds": resources,
        "resource_contracts": [
            {"resource_kind": "repository_change", "permitted_match_modes": ["any"], "value_type": "string", "enum_values": None, "null_allowed": True, "format_id": None, "value_fact_id": None},
            {"resource_kind": "repository_path", "permitted_match_modes": ["exact", "prefix"], "value_type": "string", "enum_values": None, "null_allowed": False, "format_id": REPOSITORY_PATH_FORMAT_ID, "value_fact_id": "proposal.resource.path"},
        ],
        "subject_kinds": ["agent"],
        "role_kinds": roles,
        "vocabulary": {"effects": ["allow", "deny", "require"], "resource_matches": ["any", "exact", "prefix"], "evidence_types": []},
        "synonyms": {"modify": ["change", "modify"], "repository-maintainer": ["repository maintainer", "repository maintainers"]},
        "types_and_units": [{"type": "enum", "canonical_units": []}, {"type": "string", "canonical_units": []}],
        "runtime_fact_schema": runtime,
        "grammar_compiler": {"compiler_id": REPOSITORY_GRAMMAR_ID, "compiler_version": "1.0.0"},
        "allowed_mapping_controls": [
            _control("acting-role", "Acting role requirement", "Select the repository-scoped role required to modify the repository.", {"role": _selection("enum", enum_values=roles)}, ACTING_ROLE_EMITTER_ID),
            _control("exact-path-access", "Exact-path access", "Select allow or deny and one repository-relative exact path.", {"effect": _selection("enum", enum_values=["allow", "deny"]), "path": _selection("string", format_id=REPOSITORY_PATH_FORMAT_ID)}, EXACT_PATH_EMITTER_ID),
            _control("prefix-path-access", "Path-prefix access", "Select allow or deny and one repository-relative prefix ending in slash.", {"effect": _selection("enum", enum_values=["allow", "deny"]), "path": _selection("string", format_id=REPOSITORY_PATH_FORMAT_ID)}, PREFIX_PATH_EMITTER_ID),
        ],
        "semantic_validation_rules": ["bounded-symbols", "canonical-types-and-units", "explicit-boolean-grouping", "explicit-exception-precedence", "no-contradictory-effects", "nonempty-enforceable-rule-set", "runtime-fact-publication-gate"],
        "compiler_lowering": {"lowering_id": REPOSITORY_LOWERING_ID, "lowering_version": "1.0.0"},
        "test_vectors": {
            "positive": [{"source": "Agents may modify README.md.", "expected": "direct:allow-exact-path"}, {"source": "Agents must not modify files under deployment/.", "expected": "direct:deny-prefix-path"}],
            "negative": [{"source": "This policy describes repository work.", "expected": "requires-decision"}, {"source": "Agents should change docs.", "expected": "requires-decision"}],
            "invalid": [{"source": "Agents may modify ../secret.", "expected": "reject:unsafe-path"}, {"source": "Agents may normally modify README.md.", "expected": "requires-decision"}],
        },
    }
    pack["canonical_hash"] = artifact_hash(pack, "canonical_hash")
    validate_domain_pack(pack)
    return pack


def _fact(fact_id: str, fact_type: str, enum_values: list[str] | None, canonical_unit: str | None, required: bool, field_path: str, operators: list[str]) -> dict[str, Any]:
    return {"fact_id": fact_id, "type": fact_type, "enum_values": enum_values, "canonical_unit": canonical_unit, "required": required, "derivation": {"kind": "proposal_field", "field_path": field_path}, "comparison_operators": operators}


def _selection(value_type: str, *, enum_values: list[str] | None = None, canonical_unit: str | None = None, format_id: str | None = None) -> dict[str, Any]:
    return {"type": value_type, "enum_values": enum_values, "canonical_unit": canonical_unit, "format_id": format_id}


def _control(control_id: str, name: str, description: str, selection_schema: dict[str, dict[str, Any]], emitter_id: str) -> dict[str, Any]:
    return {"control_id": control_id, "name": name, "description": description, "selection_schema": selection_schema, "emitter_id": emitter_id}


def _validate_vectors(vectors: Any) -> None:
    _object(vectors, "domain pack test_vectors")
    _exact(vectors, {"positive", "negative", "invalid"}, "domain pack test_vectors")
    for category, items in vectors.items():
        if not isinstance(items, list) or not items:
            raise ValueError(f"domain pack test_vectors.{category} must be non-empty")
        for index, vector in enumerate(items):
            label = f"domain pack test_vectors.{category}[{index}]"
            _object(vector, label)
            _exact(vector, {"source", "expected"}, label)
            _nonempty(vector["source"], f"{label}.source")
            _nonempty(vector["expected"], f"{label}.expected")


def _identity_version(value: Any, label: str, id_field: str, version_field: str) -> None:
    _object(value, label)
    _exact(value, {id_field, version_field}, label)
    _portable(value[id_field], f"{label}.{id_field}")
    _semver(value[version_field], f"{label}.{version_field}")


def _symbols(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value or len(set(value)) != len(value) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{label} must be a non-empty unique string array")


def _object(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(f"{label} fields are invalid; unknown={sorted(actual - expected)}, missing={sorted(expected - actual)}")


def _portable(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value) or "@" in value:
        raise ValueError(f"{label} must be a portable identity without @")
    return value


def _semver(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SEMVER.fullmatch(value):
        raise ValueError(f"{label} must be canonical semver")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


_REPOSITORY_CHANGES_PACK = _repository_changes_pack()
_BUILTIN_PACKS = {(REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION): _REPOSITORY_CHANGES_PACK}
