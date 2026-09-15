"""Development-only action semantics; no runtime or filesystem implementation."""

from __future__ import annotations

import copy
import os
import re
from typing import Any

from governance_ledger.authority_contract import compute_contract_hash
from governance_ledger.constraint_ir import artifact_hash, validate_format_value

DEV_ENV = "WAVEFRAME_LEDGER_ACTION_POLICY_DEV"
VERSION = "2.0.0"
ENFORCEMENT_POINT = "waveframe.guard.repository-change.v2-development"
CONTRACT_SCHEMA = "compiled_authority_contract.v3"
REVIEW_BOUNDARY = (
    " Development validation only; compatible Guard and hosted Cloud activation are pending. "
    "An absent action or missing matching allow grants no permission. A matching deny wins "
    "within the same action; rules never cross actions. Roles restrict an action and grant no paths. "
    "Creation requires one new regular file under an existing parent in the selected workspace, "
    "without overwrite or parent creation. Guard must check filesystem state, not caller facts."
)


def require_development_opt_in() -> None:
    if os.environ.get(DEV_ENV) != "1":
        raise ValueError(f"action policy development requires explicit {DEV_ENV}=1")


def get_development_capability_catalog() -> dict[str, Any]:
    require_development_opt_in()
    from governance_ledger.domain_packs import get_builtin_domain_pack
    from governance_ledger.domain_policy import _pack_ref
    from governance_ledger.policy_translation import _build_repository_capability_catalog

    catalog = _build_repository_capability_catalog()
    pack = get_builtin_domain_pack("repository-changes", VERSION)
    catalog.update(schema_version="policy_translation_capability_catalog.v2",
                   catalog_version=VERSION, domain_pack=_pack_ref(pack),
                   actions=["create", "modify"])
    for fact in catalog["facts"]:
        if fact["fact_id"] == "proposal.action":
            fact["enum_values"] = ["create", "modify"]
    controls = catalog["control_types"]
    catalog["control_types"] = [
        {**copy.deepcopy(control), "action": action,
         "mapping_control_id": action + "-" + control["mapping_control_id"]}
        for action in catalog["actions"] for control in controls
    ]
    catalog["enforcement_points"][0].update(
        enforcement_point_id=ENFORCEMENT_POINT, actions=["create", "modify"])
    catalog["catalog_hash"] = artifact_hash(catalog, "catalog_hash")
    return catalog


def parse_action_statement(text: str, pack: dict) -> list[dict]:
    """Closed grammar: no inference from change/write or path-conditioned roles."""
    from governance_ledger.domain_policy import _constraint, _finalize_constraint
    from governance_ledger.domain_packs import REPOSITORY_PATH_FORMAT_ID

    role = re.fullmatch(r"Agents must use role ([a-z-]+) to (create|modify) repository files\.", text.strip())
    if role:
        value, action = role.groups()
        if value not in pack["role_kinds"]:
            return []
        return [_finalize_constraint(_constraint(action=action, acting_role=value,
            effect="require", resource={"kind": "repository_change", "match": "any", "value": None}))]
    match = re.fullmatch(r"Agents (may|must not) (.+)\.", text.strip())
    if not match:
        return []
    effect = "allow" if match[1] == "may" else "deny"
    constraints = []
    action = None
    for fragment in match[2].split(" and "):
        part = re.fullmatch(r"(?:(create|modify) )?(files under )?([^\s]+)", fragment)
        if not part:
            return []
        explicit_action, prefix, path = part.groups()
        action = explicit_action or action
        if action is None:
            return []
        mode = "prefix" if prefix else "exact"
        try:
            validate_format_value(REPOSITORY_PATH_FORMAT_ID, path, match_mode=mode, label="action path")
        except ValueError:
            return []
        constraints.append(_finalize_constraint(_constraint(action=action, effect=effect,
            resource={"kind": "repository_path", "match": mode, "value": path})))
    return constraints


def lower_action_constraints(authority: dict, constraints: list[dict]) -> dict:
    """Project validated Ledger IR into the compiler-owned closed public input."""
    actions: dict[str, dict] = {}
    for item in constraints:
        action = item["action"]
        if action not in {"create", "modify"}:
            raise ValueError("unknown action")
        if (item["condition"] is not None or item["exceptions"] or
            item["obligations"] != {"approvals": [], "evidence": [], "separation_of_duties": []} or
            item["subject"] != {"kind": "subject_kind", "value": "agent"}):
            raise ValueError("unsupported action constraint")
        block = actions.setdefault(action, {"required_role": None, "allow": [], "deny": []})
        role, resource, effect = item["acting_role"], item["resource"], item["effect"]
        if role is not None:
            if effect != "require" or resource != {"kind": "repository_change", "match": "any", "value": None}:
                raise ValueError("path-dependent role clauses are unsupported")
            if block["required_role"] not in {None, role["value"]}:
                raise ValueError("conflicting action-wide roles")
            block["required_role"] = role["value"]
        else:
            if effect not in {"allow", "deny"} or resource["kind"] != "repository_path":
                raise ValueError("unsupported action path constraint")
            rule = {"match": resource["match"], "value": resource["value"]}
            if rule in block[effect] or rule in block["deny" if effect == "allow" else "allow"]:
                raise ValueError("duplicate or contradictory same-action selector")
            block[effect].append(rule)
    if not actions or not any(block["allow"] for block in actions.values()):
        raise ValueError("publication requires at least one path allow; deny-only/role-only grants no operation")
    for block in actions.values():
        for effect in ("allow", "deny"):
            block[effect].sort(key=lambda rule: (rule["match"], rule["value"]))
    return {"schema_version": "action_policy.v1", "contract_id": authority["authority_id"],
            "contract_version": authority["authority_version"],
            "action_requirements": dict(sorted(actions.items()))}


def verify_action_compiler_output(raw: dict, policy: dict) -> None:
    """Independently check raw unsigned hash and complete identity/semantic equality."""
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version", "contract_id", "contract_version", "action_requirements", "contract_hash"
    }:
        raise ValueError("action compiler output has an invalid exact shape")
    if raw["schema_version"] != "compiled_action_contract.v1":
        raise ValueError("action compiler output discriminator is unsupported")
    if not isinstance(raw["contract_hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", raw["contract_hash"]):
        raise ValueError("action compiler hash must be unprefixed SHA-256 hex")
    if raw["contract_hash"] != compute_contract_hash(raw):
        raise ValueError("action compiler unsigned canonical hash mismatch")
    for field in ("contract_id", "contract_version", "action_requirements"):
        if raw[field] != policy[field]:
            raise ValueError(f"action compiler output substitution: {field}")


def compile_verified_action_policy(policy: dict) -> dict:
    require_development_opt_in()
    try:
        from compiler import compile_action_policy
    except ImportError as exc:
        raise ValueError("required compile_action_policy API unavailable; no legacy fallback") from exc
    if not callable(compile_action_policy):
        raise ValueError("required compile_action_policy API unavailable; no legacy fallback")
    raw = compile_action_policy(copy.deepcopy(policy))
    verify_action_compiler_output(raw, policy)
    return copy.deepcopy(raw)
