"""Built-in deterministic policy domain packs.

Domain packs are canonical, immutable-by-identity artifacts.  Public callers
receive deep copies; every use revalidates the exact content hash so mutation or
identity substitution fails closed.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from governance_ledger.constraint_ir import (
    artifact_hash,
    finalize_runtime_fact_schema,
    validate_runtime_fact_schema,
)


DOMAIN_PACK_V1 = "domain_pack.v1"
REPOSITORY_CHANGES_PACK_ID = "repository-changes"
REPOSITORY_CHANGES_PACK_VERSION = "1.0.0"

_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")


def list_builtin_domain_packs() -> list[dict[str, Any]]:
    """List stable descriptors for domain packs shipped with this Ledger build."""
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
    """Return one exact built-in pack version, never a mutable global instance."""
    key = (domain_pack_id, domain_pack_version)
    if key not in _BUILTIN_PACKS:
        raise ValueError(
            f"unknown built-in domain pack version: {domain_pack_id}@{domain_pack_version}"
        )
    result = copy.deepcopy(_BUILTIN_PACKS[key])
    validate_domain_pack(result)
    return result


def validate_domain_pack(pack: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate a canonical ``domain_pack.v1`` artifact."""
    _object(pack, "domain pack")
    _exact(
        pack,
        {
            "schema_version",
            "domain_pack_id",
            "domain_pack_version",
            "name",
            "description",
            "supported_actions",
            "resource_kinds",
            "subject_kinds",
            "role_kinds",
            "vocabulary",
            "synonyms",
            "types_and_units",
            "runtime_fact_schema",
            "grammar_compiler",
            "allowed_mapping_controls",
            "semantic_validation_rules",
            "compiler_lowering",
            "test_vectors",
            "canonical_hash",
        },
        "domain pack",
    )
    if pack["schema_version"] != DOMAIN_PACK_V1:
        raise ValueError(f"domain pack must be {DOMAIN_PACK_V1}")
    _portable(pack["domain_pack_id"], "domain_pack_id")
    if not isinstance(pack["domain_pack_version"], str) or not _SEMVER.fullmatch(
        pack["domain_pack_version"]
    ):
        raise ValueError("domain_pack_version must be a canonical semantic version")
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
    _symbols(vocabulary["evidence_types"], "domain pack evidence types")
    synonyms = pack["synonyms"]
    _object(synonyms, "domain pack synonyms")
    scoped_symbols = (
        set(pack["supported_actions"])
        | set(pack["resource_kinds"])
        | set(pack["subject_kinds"])
        | set(pack["role_kinds"])
        | {symbol for values in vocabulary.values() for symbol in values}
    )
    for canonical, aliases in synonyms.items():
        _portable(canonical, "domain pack synonym identity")
        if canonical not in scoped_symbols:
            raise ValueError(f"domain pack synonym is outside scoped vocabulary: {canonical}")
        if (
            not isinstance(aliases, list)
            or not aliases
            or any(not isinstance(item, str) or not item for item in aliases)
            or len(set(aliases)) != len(aliases)
        ):
            raise ValueError(f"domain pack synonyms for {canonical} must be unique strings")
    if not isinstance(pack["types_and_units"], list) or not pack["types_and_units"]:
        raise ValueError("domain pack types_and_units must be a non-empty array")
    for index, item in enumerate(pack["types_and_units"]):
        label = f"domain pack types_and_units[{index}]"
        _object(item, label)
        _exact(item, {"type", "canonical_units"}, label)
        _portable(item["type"], f"{label}.type")
        if not isinstance(item["canonical_units"], list) or any(
            not isinstance(unit, str) or not unit for unit in item["canonical_units"]
        ):
            raise ValueError(f"{label}.canonical_units must be an array of strings")
    validate_runtime_fact_schema(pack["runtime_fact_schema"])
    _identity_version(
        pack["grammar_compiler"],
        "domain pack grammar_compiler",
        {"compiler_id", "compiler_version"},
    )
    controls = pack["allowed_mapping_controls"]
    if not isinstance(controls, list) or not controls:
        raise ValueError("domain pack allowed_mapping_controls must be non-empty")
    control_ids: set[str] = set()
    for index, control in enumerate(controls):
        label = f"domain pack allowed_mapping_controls[{index}]"
        _object(control, label)
        _exact(
            control,
            {"control_id", "name", "description", "selection_schema", "produces"},
            label,
        )
        _portable(control["control_id"], f"{label}.control_id")
        if control["control_id"] in control_ids:
            raise ValueError("domain pack contains duplicate mapping control identities")
        control_ids.add(control["control_id"])
        _nonempty(control["name"], f"{label}.name")
        _nonempty(control["description"], f"{label}.description")
        schema = control["selection_schema"]
        _object(schema, f"{label}.selection_schema")
        for field_name, field in schema.items():
            _portable(field_name, f"{label} selection field")
            _object(field, f"{label}.selection_schema.{field_name}")
            allowed = {"type", "enum", "pattern", "canonical_unit"}
            if set(field) - allowed or "type" not in field:
                raise ValueError(f"{label}.selection_schema.{field_name} has unknown fields")
            if field["type"] not in {"decimal", "enum", "repository_path"}:
                raise ValueError(f"{label}.selection_schema.{field_name}.type is unknown")
            if field["type"] == "enum" and (
                not isinstance(field.get("enum"), list) or not field["enum"]
            ):
                raise ValueError(f"{label}.selection_schema.{field_name}.enum is required")
        if control["produces"] not in {
            "acting_role_requirement",
            "approval_threshold",
            "exact_path_access",
            "prefix_path_access",
            "requester_approver_separation",
        }:
            raise ValueError(f"{label}.produces is unknown")
    _symbols(pack["semantic_validation_rules"], "domain pack semantic_validation_rules")
    _identity_version(
        pack["compiler_lowering"],
        "domain pack compiler_lowering",
        {"lowering_id", "lowering_version"},
    )
    vectors = pack["test_vectors"]
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
    supplied_hash = pack["canonical_hash"]
    if supplied_hash != artifact_hash(pack, "canonical_hash"):
        raise ValueError("domain-pack canonical hash does not match canonical content")
    return {
        "valid": True,
        "domain_pack_id": pack["domain_pack_id"],
        "domain_pack_version": pack["domain_pack_version"],
        "canonical_hash": supplied_hash,
    }


def mapping_control_index(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return validated mapping controls indexed by their public identity."""
    validate_domain_pack(pack)
    return {item["control_id"]: copy.deepcopy(item) for item in pack["allowed_mapping_controls"]}


def _repository_changes_pack() -> dict[str, Any]:
    roles = ["approver", "manager", "repository-maintainer", "requester", "security-reviewer"]
    actions = ["approve", "invoice", "modify", "payment", "purchase", "request", "transfer"]
    resource_kinds = ["financial_request", "repository_change", "repository_path"]
    runtime = finalize_runtime_fact_schema(
        {
            "schema_version": "runtime_fact_schema.v1",
            "schema_id": "repository-changes-runtime",
            "schema_version_number": "1.0.0",
            "name": "Repository changes proposal facts",
            "facts": [
                _fact("actor.subject_kind", "enum", ["agent"], None, True, "actor.subject_kind", ["==", "!="]),
                _fact("actor.principal_id", "string", None, None, False, "actor.principal_id", ["==", "!="]),
                _fact("actor.role", "enum", roles, None, False, "actor.role", ["==", "!="]),
                _fact("approval.count", "integer", None, "count", False, "approvals.count", ["==", "!=", ">", ">=", "<", "<="]),
                _fact("approver.principal_id", "string", None, None, False, "approvals.approver_principal_id", ["==", "!="]),
                _fact("evidence.change_record_id", "string", None, None, False, "evidence.change_record_id", ["==", "!="]),
                _fact("proposal.action", "enum", actions, None, True, "proposal.action", ["==", "!="]),
                _fact("proposal.resource.kind", "enum", resource_kinds, None, True, "proposal.resource.kind", ["==", "!="]),
                _fact("proposal.resource.path", "string", None, None, False, "proposal.resource.path", ["==", "!=", "starts_with"]),
                _fact("request.amount", "decimal", None, "USD", False, "request.amount", ["==", "!=", ">", ">=", "<", "<="]),
                _fact("requester.principal_id", "string", None, None, False, "proposal.requester_principal_id", ["==", "!="]),
            ],
        }
    )
    pack: dict[str, Any] = {
        "schema_version": DOMAIN_PACK_V1,
        "domain_pack_id": REPOSITORY_CHANGES_PACK_ID,
        "domain_pack_version": REPOSITORY_CHANGES_PACK_VERSION,
        "name": "Repository changes",
        "description": (
            "Deterministic repository-change policy grammar and guided controls retained "
            "from Ledger v0.6, scoped to this pack."
        ),
        "supported_actions": actions,
        "resource_kinds": resource_kinds,
        "subject_kinds": ["agent"],
        "role_kinds": roles,
        "vocabulary": {
            "effects": ["allow", "deny", "require"],
            "resource_matches": ["any", "exact", "prefix"],
            "evidence_types": ["change-record"],
        },
        "synonyms": {
            "repository-maintainer": ["repository maintainer", "repository maintainers"],
            "modify": ["change", "modify"],
            "transfer": ["transfer", "transfers"],
        },
        "types_and_units": [
            {"type": "boolean", "canonical_units": []},
            {"type": "decimal", "canonical_units": ["USD"]},
            {"type": "enum", "canonical_units": []},
            {"type": "integer", "canonical_units": ["count"]},
            {"type": "string", "canonical_units": []},
            {"type": "timestamp", "canonical_units": ["UTC"]},
        ],
        "runtime_fact_schema": runtime,
        "grammar_compiler": {
            "compiler_id": "repository-changes-sentence-grammar",
            "compiler_version": "1.0.0",
        },
        "allowed_mapping_controls": [
            _control(
                "acting-role",
                "Acting role requirement",
                "Select the role that must act for repository changes.",
                {"role": {"type": "enum", "enum": roles}},
                "acting_role_requirement",
            ),
            _control(
                "approval-threshold",
                "Approval threshold",
                "Select an action, USD amount comparison, and required approver role.",
                {
                    "action": {"type": "enum", "enum": ["invoice", "payment", "purchase", "request", "transfer"]},
                    "operator": {"type": "enum", "enum": [">", ">=", "<"]},
                    "amount": {"type": "decimal", "canonical_unit": "USD", "pattern": "canonical-decimal"},
                    "role": {"type": "enum", "enum": roles},
                },
                "approval_threshold",
            ),
            _control(
                "exact-path-access",
                "Exact-path access",
                "Select allow or deny and one repository-relative exact path.",
                {
                    "effect": {"type": "enum", "enum": ["allow", "deny"]},
                    "path": {"type": "repository_path", "pattern": "exact"},
                },
                "exact_path_access",
            ),
            _control(
                "prefix-path-access",
                "Path-prefix access",
                "Select allow or deny and one repository-relative prefix ending in slash.",
                {
                    "effect": {"type": "enum", "enum": ["allow", "deny"]},
                    "path": {"type": "repository_path", "pattern": "prefix"},
                },
                "prefix_path_access",
            ),
            _control(
                "requester-approver-separation",
                "Requester/approver separation",
                "Require requester and approver principal identities to differ.",
                {},
                "requester_approver_separation",
            ),
        ],
        "semantic_validation_rules": [
            "bounded-symbols",
            "canonical-types-and-units",
            "explicit-boolean-grouping",
            "explicit-exception-precedence",
            "no-contradictory-effects",
            "nonempty-enforceable-rule-set",
            "runtime-fact-publication-gate",
        ],
        "compiler_lowering": {
            "lowering_id": "repository-changes-to-cricore-contract-compiler",
            "lowering_version": "1.0.0",
        },
        "test_vectors": {
            "positive": [
                {"source": "Agents may modify README.md.", "expected": "direct:allow-exact-path"},
                {"source": "Requester and approver must be separate.", "expected": "direct:separation-of-duties"},
            ],
            "negative": [
                {"source": "This policy describes repository work.", "expected": "informational"},
                {"source": "Agents should update docs.", "expected": "requires-mapping"},
            ],
            "invalid": [
                {"source": "Agents may modify ../secret.", "expected": "reject:unsafe-path"},
                {"source": "Agents may modify an appropriate file.", "expected": "requires-mapping:ambiguous"},
            ],
        },
    }
    pack["canonical_hash"] = artifact_hash(pack, "canonical_hash")
    validate_domain_pack(pack)
    return pack


def _fact(
    fact_id: str,
    fact_type: str,
    enum_values: list[str] | None,
    canonical_unit: str | None,
    required: bool,
    source: str,
    operators: list[str],
) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "type": fact_type,
        "enum_values": enum_values,
        "canonical_unit": canonical_unit,
        "required": required,
        "derivation": {"kind": "proposal_field", "source": source},
        "comparison_operators": operators,
    }


def _control(
    control_id: str,
    name: str,
    description: str,
    selection_schema: dict[str, dict[str, Any]],
    produces: str,
) -> dict[str, Any]:
    return {
        "control_id": control_id,
        "name": name,
        "description": description,
        "selection_schema": selection_schema,
        "produces": produces,
    }


def _identity_version(value: Any, label: str, fields: set[str]) -> None:
    _object(value, label)
    _exact(value, fields, label)
    for field, item in value.items():
        if field.endswith("version"):
            if not isinstance(item, str) or not _SEMVER.fullmatch(item):
                raise ValueError(f"{label}.{field} must be a canonical semantic version")
        else:
            _portable(item, f"{label}.{field}")


def _symbols(value: Any, label: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or len(set(value)) != len(value)
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError(f"{label} must be a non-empty unique string array")


def _object(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{label} fields are invalid; unknown={sorted(actual - expected)}, "
            f"missing={sorted(expected - actual)}"
        )


def _portable(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value) or "@" in value:
        raise ValueError(f"{label} must be a portable identity without @")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


_REPOSITORY_CHANGES_PACK = _repository_changes_pack()
_BUILTIN_PACKS = {
    (REPOSITORY_CHANGES_PACK_ID, REPOSITORY_CHANGES_PACK_VERSION): _REPOSITORY_CHANGES_PACK
}
