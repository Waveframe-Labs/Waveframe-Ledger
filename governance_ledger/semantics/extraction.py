"""Deterministic semantic extraction from governance policy text."""

from __future__ import annotations

import hashlib
import re
from typing import Any

SOURCE_SCHEMA_VERSION = "governance_source.v1"
EXTRACTION_SCHEMA_VERSION = "governance_semantic_extraction.v1"

_NON_GOALS = [
    "does not approve authority",
    "does not execute policy",
    "does not determine admissibility",
    "requires operator confirmation before publication",
]


def build_governance_source(
    source_text: str,
    *,
    source_id: str | None = None,
    source_type: str = "policy_text",
    extraction_mode: str = "deterministic_rules",
) -> dict[str, Any]:
    """Build a canonical source artifact for policy text ingestion."""
    text = _normalize_source_text(source_text)
    source_hash = _hash_text(text)
    return {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "source_id": source_id or f"source-{source_hash.removeprefix('sha256:')[:12]}",
        "source_type": source_type,
        "source_text": text,
        "canonical_text": text,
        "source_version": "1",
        "source_hash": source_hash,
        "created_at": _stable_time(source_hash),
        "extraction_mode": extraction_mode,
        "human_review_required": True,
    }


def extract_governance_semantics(
    source_text: str,
    *,
    source_id: str | None = None,
) -> dict[str, Any]:
    """Extract candidate governance meaning with deterministic pattern rules."""
    source = build_governance_source(source_text, source_id=source_id)
    text = source["source_text"]
    lower = text.lower()

    protected_resource = _extract_protected_resource(text)
    governed_action = _extract_governed_action(text)
    role = _extract_role(text)
    approval_count = _extract_approval_count(text)
    threshold = _extract_threshold(text)
    validity_days = _extract_validity_days(text)
    temporal_semantics = _extract_temporal_semantics(text, validity_days)
    continuity_revalidation = _contains_any(
        lower,
        [
            "revalidat",
            "current authority",
            "current governance state",
            "current policy version",
            "policy changes",
            "posture changes",
            "supersed",
            "compare current policy version",
        ],
    )
    revocation_invalidates = _contains_any(lower, ["revoked", "revocation"]) and _contains_any(lower, ["resume", "continuity", "invalidate"])
    state_snapshot_semantics = _extract_state_snapshot_semantics(
        text,
        continuity_revalidation=continuity_revalidation,
        revocation_invalidates=revocation_invalidates,
    )
    execution_context_semantics = _extract_execution_context_semantics(text)
    governance_actor = _extract_governance_actor(text, role, governed_action, continuity_revalidation)
    authority_role_binding = _extract_authority_role_binding(text, role)
    approval_chain_semantics = _extract_approval_chain_semantics(text, role, approval_count)
    identity_continuity_semantics = _extract_identity_continuity_semantics(
        text,
        continuity_revalidation=continuity_revalidation,
        execution_context=execution_context_semantics,
    )
    evidence_terms = _extract_evidence_terms(lower)

    candidate = {
        "protected_system": protected_resource,
        "governed_action": governed_action,
        "contract_id": _slug(protected_resource or "policy-authority"),
        "contract_version": "0.1.0",
        "governance_category": _extract_domain(text),
        "approver_role": role,
        "approval_count": approval_count,
        "escalation_threshold": threshold,
        "escalation_semantics": _extract_escalation_semantics(text, threshold, role),
        "validity_days": validity_days,
        "temporal_semantics": temporal_semantics,
        "mutation_targets": _mutation_target(governed_action) if governed_action else "",
        "continuity_revalidation": continuity_revalidation,
        "revocation_invalidates_resume": revocation_invalidates,
        "state_snapshot_semantics": state_snapshot_semantics,
        "execution_context_semantics": execution_context_semantics,
        "governance_actor": governance_actor,
        "authority_role_binding": authority_role_binding,
        "approval_chain_semantics": approval_chain_semantics,
        "identity_continuity_semantics": identity_continuity_semantics,
    }

    missing = []
    for field, label in [
        ("protected_system", "protected resource"),
        ("governed_action", "governed action"),
        ("approver_role", "approval role"),
        ("approval_count", "approval count"),
        ("escalation_threshold", "escalation threshold"),
        ("validity_days", "validity window"),
    ]:
        if candidate[field] in ("", None):
            missing.append({"field": field, "summary": f"No {label} was deterministically extracted."})

    candidate_rules = []
    if role or approval_count:
        candidate_rules.append(
            {
                "rule_type": "approval_requirement",
                "summary": _approval_summary(role, approval_count),
                "fields": {"approver_role": role, "approval_count": approval_count},
            }
        )
    if threshold:
        candidate_rules.append(
            {
                "rule_type": "escalation_threshold",
                "summary": f"Executions above ${threshold:,} require escalation review.",
                "fields": {"threshold": threshold},
            }
        )
    if continuity_revalidation or revocation_invalidates:
        candidate_rules.append(
            {
                "rule_type": "continuity_semantics",
                "summary": _continuity_summary(continuity_revalidation, revocation_invalidates),
                "fields": {
                    "continuity_revalidation": continuity_revalidation,
                    "revocation_invalidates_resume": revocation_invalidates,
                },
            }
        )
    if temporal_semantics:
        candidate_rules.append(
            {
                "rule_type": "temporal_authority_semantics",
                "summary": _temporal_summary(temporal_semantics),
                "fields": temporal_semantics,
            }
        )
    if state_snapshot_semantics:
        candidate_rules.append(
            {
                "rule_type": "state_posture_snapshot_semantics",
                "summary": "Resumed workflows are expected to compare prior governance posture against active governance state.",
                "fields": state_snapshot_semantics,
            }
        )
    if execution_context_semantics:
        candidate_rules.append(
            {
                "rule_type": "execution_context_semantics",
                "summary": _execution_context_summary(execution_context_semantics),
                "fields": execution_context_semantics,
            }
        )
    if governance_actor:
        candidate_rules.append(
            {
                "rule_type": "governance_actor",
                "summary": f"{governance_actor['actor_id']} carries governance actor responsibility.",
                "fields": governance_actor,
            }
        )
    if authority_role_binding:
        candidate_rules.append(
            {
                "rule_type": "authority_role_binding",
                "summary": f"{authority_role_binding['role_id']} is bound to {authority_role_binding['accountability_boundary']} responsibility.",
                "fields": authority_role_binding,
            }
        )
    if approval_chain_semantics:
        candidate_rules.append(
            {
                "rule_type": "approval_chain_semantics",
                "summary": _approval_chain_summary(approval_chain_semantics),
                "fields": approval_chain_semantics,
            }
        )
    if identity_continuity_semantics:
        candidate_rules.append(
            {
                "rule_type": "identity_continuity_semantics",
                "summary": "Identity continuity expectations apply to resumed governance posture.",
                "fields": identity_continuity_semantics,
            }
        )
    for term in evidence_terms:
        candidate_rules.append(
            {
                "rule_type": "required_evidence",
                "summary": f"Policy text references {term.replace('_', ' ')} evidence.",
                "fields": {"evidence_term": term},
            }
        )

    ambiguities = _ambiguities(text, candidate)
    semantic_provenance = _semantic_provenance(text, candidate)
    return {
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "extracted_at": _stable_time(source["source_hash"]),
        "extraction_method": "deterministic_pattern_pass",
        "confidence_posture": "requires_human_review",
        "candidate_authority": candidate,
        "candidate_rules": candidate_rules,
        "semantic_provenance": semantic_provenance,
        "ambiguities": ambiguities,
        "missing_information": missing,
        "non_goals": list(_NON_GOALS),
        "governance_source": source,
    }


def _extract_protected_resource(text: str) -> str:
    patterns = [
        r"^(?P<value>[A-Z][A-Za-z0-9 &-]+?(?:System|Service|Platform|API|Workflow|Process))\s+",
        r"(?:governs?|protects?|applies to|for)\s+(?:the\s+)?(?P<value>[A-Z][A-Za-z0-9 &-]+?(?:System|Service|Platform|API|Workflow|Process))\b",
        r"(?:system|resource)\s*:\s*(?P<value>[^.\n]+)",
    ]
    return _first_match(text, patterns)


def _extract_governed_action(text: str) -> str:
    patterns = [
        r"(?:action|operation)\s*:\s*(?P<value>[^.\n]+)",
        r"\b(?P<value>transfers?)\s+above\b",
        r"(?:before|for|when)\s+(?P<value>[a-z][a-z ]{2,40}?)\s+(?:above|over|exceeding|requires?|must)",
        r"(?P<value>transfer(?:s|ring)? funds|issue credentials|deploy(?:ing)? to production|access patient records)",
    ]
    value = _first_match(text, patterns).lower()
    return {
        "transfers funds": "transfer funds",
        "transfer": "transfer funds",
        "transfers": "transfer funds",
        "transfer funds": "transfer funds",
        "transferring funds": "transfer funds",
        "issue credentials": "issue credentials",
        "deploying to production": "deploy to production",
    }.get(value, value)


def _extract_role(text: str) -> str:
    patterns = [
        r"(?:approved by|approval by|requires? approval from|requires? review by)\s+(?:the\s+)?(?P<value>[A-Za-z0-9 -]+?)(?:\.|,|;|\s+for|\s+when|\s+before|\s+with|\s+and|$)",
        r"(?:approver role|approval role)\s*:\s*(?P<value>[^.\n]+)",
    ]
    return _slug(_first_match(text, patterns))


def _extract_approval_count(text: str) -> int | None:
    numeric = re.search(r"(?P<count>\d+)\s+(?:independent\s+)?approvals?", text, re.IGNORECASE)
    if numeric:
        return int(numeric.group("count"))
    words = {"one": 1, "two": 2, "three": 3}
    match = re.search(r"\b(one|two|three)\s+(?:independent\s+)?approvals?\b", text, re.IGNORECASE)
    if match:
        return words[match.group(1).lower()]
    if re.search(r"\bapproval\b|\bapproved\b|\bapprove\b", text, re.IGNORECASE):
        return 1
    return None


def _extract_threshold(text: str) -> int | None:
    match = re.search(r"(?:above|over|exceed(?:s|ing)?|greater than)\s+\$?(?P<amount>\d[\d,]*)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"\$?(?P<amount>\d[\d,]*)\s+(?:threshold|limit)", text, re.IGNORECASE)
    return int(match.group("amount").replace(",", "")) if match else None


def _extract_validity_days(text: str) -> int | None:
    match = re.search(r"(?:valid|expires?|validity)\s+(?:for|after|within)?\s*(?P<days>\d+)\s+days?", text, re.IGNORECASE)
    return int(match.group("days")) if match else None


def _extract_temporal_semantics(text: str, validity_days: int | None) -> dict[str, Any]:
    if validity_days is None and not re.search(r"\bexpires?\s+after\s+approval\b", text, re.IGNORECASE):
        return {}
    timestamp_source, expiration_basis = _extract_timestamp_source(text)
    temporal = {
        "schema_version": "temporal_authority_semantics.v1",
        "timestamp_source": timestamp_source,
        "expiration_basis": expiration_basis,
        "runtime_enforced_by": "Guard/Cloud",
    }
    if validity_days is not None:
        temporal["validity_window"] = f"P{validity_days}D"
    else:
        temporal["expiration_trigger"] = "approval_completion"
    return temporal


def _extract_timestamp_source(text: str) -> tuple[str, str]:
    lower = text.lower()
    if _contains_any(lower, ["signed oracle", "oracle timestamp", "oracle time"]):
        return "signed_oracle", "signed_oracle_time"
    if "block timestamp" in lower or "block time" in lower:
        return "block_timestamp", "block_timestamp"
    if _contains_any(lower, ["cloud attested time", "cloud-attested time", "attested time"]):
        return "cloud_attested_time", "cloud_attested_time"
    if _contains_any(lower, ["execution payload", "signed execution time", "signed execution timestamp"]):
        return "execution_payload", "signed_execution_time"
    return "unspecified", "unspecified"


def _extract_state_snapshot_semantics(
    text: str,
    *,
    continuity_revalidation: bool,
    revocation_invalidates: bool,
) -> dict[str, Any]:
    lower = text.lower()
    if not (continuity_revalidation or revocation_invalidates or _contains_any(lower, ["current governance state", "current policy version", "snapshot"])):
        return {}
    return {
        "schema_version": "state_posture_snapshot_semantics.v1",
        "snapshot_required": True,
        "snapshot_hash_algorithm": "sha256",
        "snapshot_subject": _extract_snapshot_subject(lower),
        "resume_comparison": "snapshot_hash_must_match_active_state_hash",
        "drift_result": "continuity_drift_detected",
        "runtime_enforced_by": "Guard/Cloud",
    }


def _extract_snapshot_subject(lower: str) -> str:
    if _contains_any(lower, ["active governance state", "current governance state"]):
        return "active_governance_state"
    if "current policy version" in lower or "policy version" in lower:
        return "current_policy_version"
    if _contains_any(lower, ["authority posture", "current authority"]):
        return "authority_posture"
    return "unspecified"


def _extract_execution_context_semantics(text: str) -> dict[str, Any]:
    lower = text.lower()
    context = ""
    boundary = "unspecified"
    if _contains_any(lower, ["queued deployment", "queued execution", "queued transfer", "queued "]):
        context = "queued_async"
        boundary = "external_worker"
    elif _contains_any(lower, ["scheduled transfer", "scheduled execution", "scheduled deployment"]):
        context = "scheduled_execution"
        boundary = "scheduler"
    elif _contains_any(lower, ["batch execution", "batch transfer", "batch deployment"]):
        context = "queued_async"
        boundary = "external_worker"
    elif _contains_any(lower, ["external settlement system", "external system", "settlement system"]):
        context = "external_system_execution"
        boundary = "external_system"
    elif _contains_any(lower, ["manual override"]):
        context = "local_interactive"
        boundary = "local_process"
    elif _contains_any(lower, ["multi-step approval", "multi stage approval", "multi-stage approval"]):
        context = "human_approval_chain"
        boundary = "human_review"
    elif _contains_any(lower, ["multi-stage workflow", "multi stage workflow", "multi-step workflow"]):
        context = "multi_stage_workflow"
        boundary = "agent_orchestrator"
    elif _contains_any(lower, ["agent orchestrated", "agent-orchestrated", "agent orchestration"]):
        context = "agent_orchestrated"
        boundary = "agent_orchestrator"
    elif _contains_any(lower, ["cloud attested execution", "cloud-attested execution"]):
        context = "cloud_attested_execution"
        boundary = "cloud_attestation"
    elif _contains_any(lower, ["resume after approval", "execution may resume later", "may resume later", "resumed workflow"]):
        context = "resumed_workflow"
        boundary = "external_worker"
    if not context:
        return {}
    resumable = context == "resumed_workflow" or _contains_any(lower, ["resume", "resumed", "may resume later"])
    temporal = context in {"queued_async", "scheduled_execution", "external_system_execution", "cloud_attested_execution"}
    replay = context not in {"local_interactive"}
    return {
        "schema_version": "execution_context_semantics.v1",
        "execution_context": context,
        "execution_boundary": boundary,
        "requires_replay_evidence": replay,
        "requires_state_snapshot": resumable or context in {"queued_async", "scheduled_execution", "multi_stage_workflow"},
        "requires_temporal_validation": temporal,
        "resume_behavior": "revalidate_on_resume" if resumable else "none",
        "continuity_risk_profile": _execution_risk_profile(context, resumable),
        "runtime_enforced_by": "Guard/Cloud",
    }


def _execution_risk_profile(context: str, resumable: bool) -> str:
    if context in {"external_system_execution", "cloud_attested_execution"}:
        return "high"
    if resumable or context in {"queued_async", "scheduled_execution", "multi_stage_workflow", "agent_orchestrated"}:
        return "medium"
    return "low"


def _extract_governance_actor(
    text: str,
    role: str,
    governed_action: str,
    continuity_revalidation: bool,
) -> dict[str, Any]:
    actor_id = role or _identity_actor_from_text(text)
    if not actor_id:
        return {}
    lower = text.lower()
    return {
        "schema_version": "governance_actor.v1",
        "actor_id": actor_id,
        "actor_type": _actor_type(actor_id, lower),
        "authority_scope": [_authority_scope(governed_action)],
        "delegation_allowed": _delegation_posture(lower) == "allowed_with_boundary",
        "attestation_required": _contains_any(lower, ["attested operator", "attested actor", "attested reviewer", "identity attestation"]),
        "identity_continuity_required": continuity_revalidation or _contains_any(lower, ["identity continuity", "same operator", "same approver"]),
    }


def _extract_authority_role_binding(text: str, role: str) -> dict[str, Any]:
    role_id = role or _identity_actor_from_text(text)
    if not role_id:
        return {}
    lower = text.lower()
    return {
        "schema_version": "authority_role_binding.v1",
        "role_id": role_id,
        "actor_ref": role_id,
        "responsibilities": _responsibilities(lower),
        "accountability_boundary": _accountability_boundary(lower),
        "delegation_posture": _delegation_posture(lower),
    }


def _extract_approval_chain_semantics(text: str, role: str, approval_count: int | None) -> dict[str, Any]:
    lower = text.lower()
    if not (role or approval_count or "approval" in lower or "reviewer" in lower or "dual control" in lower):
        return {}
    independence = _contains_any(lower, ["independent reviewer", "independent approval", "independent approvals", "cannot self-approve", "self approve", "dual control", "separation of duties", "originate and approve"])
    return {
        "schema_version": "approval_chain_semantics.v1",
        "required_approval_count": approval_count,
        "required_roles": [role] if role else [],
        "independence_required": independence,
        "self_approval_prohibited": _contains_any(lower, ["cannot self-approve", "self approve", "separation of duties", "originate and approve"]),
        "independent_actor_refs": [role] if independence and role and "independent" not in role else [],
        "delegation_posture": _delegation_posture(lower),
        "attestation_required": _contains_any(lower, ["attested operator", "attested actor", "attested reviewer", "identity attestation"]),
        "human_in_loop_required": _contains_any(lower, ["human-in-the-loop", "human in the loop", "human approval"]),
        "ai_recommendation_posture": "recommendation_only" if "ai-generated recommendation" in lower else "not_present",
    }


def _extract_identity_continuity_semantics(
    text: str,
    *,
    continuity_revalidation: bool,
    execution_context: dict[str, Any],
) -> dict[str, Any]:
    lower = text.lower()
    required = continuity_revalidation or execution_context.get("resume_behavior") == "revalidate_on_resume" or _contains_any(lower, ["identity continuity", "same operator", "same approver"])
    if not required:
        return {}
    return {
        "schema_version": "identity_continuity_semantics.v1",
        "identity_continuity_required": True,
        "resume_identity_check": "actor_or_role_binding_must_remain_valid",
        "identity_revocation_effect": "revoked_identity_invalidates_resume"
        if _contains_any(lower, ["identity revocation", "revoked identity", "revoked actor", "revoked role"])
        else "review_required",
        "runtime_enforced_by": "Guard/Cloud",
    }


def _identity_actor_from_text(text: str) -> str:
    patterns = [
        r"(?:approved by|approval by|requires? approval from|requires? review by)\s+(?:the\s+)?(?P<value>finance|security team|manager|independent reviewer|attested operator|human operator)",
        r"\b(?P<value>finance|security team|manager|independent reviewer|attested operator)\s+approval\b",
    ]
    return _slug(_first_match(text, patterns))


def _actor_type(actor_id: str, lower: str) -> str:
    if "ai-generated recommendation" in lower:
        return "agent"
    if "external" in lower:
        return "external_party"
    if "team" in actor_id or actor_id in {"finance", "security-team"}:
        return "team"
    return "human_role"


def _authority_scope(governed_action: str) -> str:
    if governed_action:
        return f"{_slug(governed_action).replace('-', '_')}_approval"
    return "governance_approval"


def _responsibilities(lower: str) -> list[str]:
    responsibilities = ["approval_responsibility"]
    if "review" in lower or "reviewer" in lower:
        responsibilities.append("review_responsibility")
    if "override" in lower or "break glass" in lower:
        responsibilities.append("override_responsibility")
    if "attested" in lower:
        responsibilities.append("attestation_responsibility")
    if "ai-generated recommendation" in lower:
        responsibilities.append("recommendation_responsibility")
    return sorted(set(responsibilities))


def _accountability_boundary(lower: str) -> str:
    if "break glass" in lower:
        return "break_glass"
    if "manager override" in lower or "override" in lower:
        return "manager_override"
    if "security team" in lower:
        return "security_review"
    if "ai-generated recommendation" in lower:
        return "recommendation_only"
    return "governance_approval"


def _delegation_posture(lower: str) -> str:
    if "delegated authority" not in lower and "delegation" not in lower:
        return "not_allowed"
    if _contains_any(lower, ["within boundary", "bounded delegation", "delegation boundary"]):
        return "allowed_with_boundary"
    return "ambiguous"


def _extract_escalation_semantics(text: str, threshold: int | None, role: str) -> str:
    if threshold and role:
        return f"Executions above ${threshold:,} require {role} review."
    if threshold:
        return f"Executions above ${threshold:,} require escalation review."
    sentences = [part.strip() for part in re.split(r"[.;]", text) if part.strip()]
    for sentence in sentences:
        if _contains_any(sentence.lower(), ["escalat", "review", "approval", "threshold", "above", "over", "large"]):
            return sentence
    return ""


def _extract_domain(text: str) -> str:
    lower = text.lower()
    if _contains_any(lower, ["treasury", "transfer", "financial", "payment"]):
        return "Financial"
    if _contains_any(lower, ["credential", "access", "identity"]):
        return "Access Control"
    if _contains_any(lower, ["patient", "clinical", "health"]):
        return "Healthcare"
    if _contains_any(lower, ["deployment", "production"]):
        return "Operational"
    return "Operational"


def _extract_evidence_terms(lower: str) -> list[str]:
    terms = []
    for needle, term in [
        ("approval evidence", "approval_evidence"),
        ("decision trace", "decision_trace"),
        ("replay", "replay"),
        ("receipt", "publication_receipt"),
    ]:
        if needle in lower:
            terms.append(term)
    return terms


def _ambiguities(text: str, candidate: dict[str, Any]) -> list[dict[str, str]]:
    ambiguities = []
    if re.search(r"\bappropriate\b|\bas needed\b|\bmaterial\b|\bsignificant\b", text, re.IGNORECASE):
        ambiguities.append(
            {
                "ambiguity_type": "ambiguous_governance_language",
                "summary": "Policy text contains qualitative language that requires operator review.",
            }
        )
    if candidate["continuity_revalidation"] and not candidate["revocation_invalidates_resume"]:
        ambiguities.append(
            {
                "ambiguity_type": "partial_continuity_language",
                "summary": "Continuity revalidation was detected, but revocation behavior was not explicit.",
            }
        )
    temporal = candidate.get("temporal_semantics") if isinstance(candidate.get("temporal_semantics"), dict) else {}
    if temporal.get("validity_window") and temporal.get("timestamp_source") == "unspecified":
        ambiguities.append(
            {
                "ambiguity_type": "timestamp_source_unspecified",
                "summary": "Validity window was detected, but the timestamp source for expiration interpretation is unspecified.",
            }
        )
    snapshot = candidate.get("state_snapshot_semantics") if isinstance(candidate.get("state_snapshot_semantics"), dict) else {}
    if snapshot.get("snapshot_required") and snapshot.get("snapshot_subject") == "unspecified":
        ambiguities.append(
            {
                "ambiguity_type": "state_snapshot_subject_unspecified",
                "summary": "Continuity revalidation was detected, but the governance state snapshot subject is unspecified.",
            }
        )
    if _implies_deferred_execution(text) and not candidate.get("execution_context_semantics"):
        ambiguities.append(
            {
                "ambiguity_type": "execution_context_ambiguity",
                "summary": "Policy language implies deferred execution, but no canonical execution context was deterministically extracted.",
            }
        )
    approval_chain = candidate.get("approval_chain_semantics") if isinstance(candidate.get("approval_chain_semantics"), dict) else {}
    if approval_chain.get("independence_required") and not approval_chain.get("independent_actor_refs"):
        ambiguities.append(
            {
                "ambiguity_type": "approval_independence_ambiguity",
                "summary": "Approval semantics imply separation-of-duties, but independent actors are undefined.",
            }
        )
    if approval_chain.get("delegation_posture") == "ambiguous":
        ambiguities.append(
            {
                "ambiguity_type": "delegation_ambiguity",
                "summary": "Delegated authority language exists without delegation boundaries.",
            }
        )
    return ambiguities


def _semantic_provenance(text: str, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    provenance_specs = [
        ("protected_resource", candidate.get("protected_system"), [candidate.get("protected_system")]),
        ("governed_action", candidate.get("governed_action"), [candidate.get("governed_action")]),
        ("approval_role", candidate.get("approver_role"), [candidate.get("approver_role"), str(candidate.get("approver_role") or "").replace("-", " "), "approved by", "approval by", "approval from", "review by"]),
        ("approval_count", candidate.get("approval_count"), ["approval", "approvals", "approve", "approved"]),
        ("escalation_threshold", candidate.get("escalation_threshold"), ["above", "over", "exceed", str(candidate.get("escalation_threshold") or "")]),
        ("validity_window", (candidate.get("temporal_semantics") or {}).get("validity_window"), ["valid for", "expires", "validity"]),
        ("timestamp_source", (candidate.get("temporal_semantics") or {}).get("timestamp_source"), ["signed execution timestamp", "signed oracle", "block timestamp", "cloud-attested time"]),
        ("state_snapshot", (candidate.get("state_snapshot_semantics") or {}).get("snapshot_required"), ["current governance state", "current policy version", "revalidat", "snapshot"]),
        ("execution_context", (candidate.get("execution_context_semantics") or {}).get("execution_context"), ["queued", "scheduled", "batch", "external", "manual override", "multi-step", "resume later"]),
        ("responsible_actor", (candidate.get("governance_actor") or {}).get("actor_id"), [(candidate.get("governance_actor") or {}).get("actor_id")]),
        ("approval_independence", (candidate.get("approval_chain_semantics") or {}).get("independence_required"), ["independent reviewer", "cannot self-approve", "dual control", "separation of duties", "originate and approve", "approve"]),
        ("delegation_posture", (candidate.get("approval_chain_semantics") or {}).get("delegation_posture"), ["delegated authority", "delegation"]),
        ("attestation_requirement", (candidate.get("approval_chain_semantics") or {}).get("attestation_required"), ["attested operator", "attested actor", "attested reviewer", "identity attestation"]),
        ("identity_continuity", (candidate.get("identity_continuity_semantics") or {}).get("identity_continuity_required"), ["identity continuity", "same operator", "same approver", "resume"]),
    ]
    for field, value, needles in provenance_specs:
        if value in ("", None, {}, []):
            continue
        confidence = _confidence_for_value(value)
        span = _source_span(text, [needle for needle in needles if needle])
        entries.append(
            {
                "schema_version": "governance_semantic_provenance.v1",
                "field": field,
                "value": value,
                "confidence": confidence if span else "low",
                "source_spans": [span] if span else [],
                "extraction_method": "deterministic_pattern",
            }
        )
    return entries


def _confidence_for_value(value: Any) -> str:
    if value in (True, False) or isinstance(value, (int, float)):
        return "high"
    if isinstance(value, str) and value not in {"unspecified", "ambiguous", "not_present"}:
        return "high"
    return "low"


def _source_span(text: str, needles: list[str]) -> dict[str, Any] | None:
    lower = text.lower()
    for needle in needles:
        clean = str(needle or "").lower()
        if not clean:
            continue
        index = lower.find(clean)
        if index >= 0:
            end = index + len(clean)
            return {"text": text[index:end], "start": index, "end": end}
    return None


def _first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return " ".join(match.group("value").strip(" .,:;").split())
    return ""


def _approval_summary(role: str, count: int | None) -> str:
    if role and count:
        return f"{count} approval{'s' if count != 1 else ''} required from {role}."
    if role:
        return f"Approval required from {role}."
    return f"{count} approval{'s' if count != 1 else ''} required."


def _continuity_summary(revalidation: bool, revocation_invalidates: bool) -> str:
    if revalidation and revocation_invalidates:
        return "Resumed workflows require revalidation and revoked authorities invalidate resumed execution."
    if revalidation:
        return "Resumed workflows require continuity revalidation when governance posture changes."
    return "Revoked authorities invalidate resumed execution continuity."


def _temporal_summary(temporal: dict[str, Any]) -> str:
    if temporal.get("validity_window"):
        return (
            f"Authority validity intent is {temporal['validity_window']} with "
            f"{temporal.get('timestamp_source', 'unspecified')} timestamp binding."
        )
    return "Authority expiration is tied to approval completion with runtime enforcement outside Ledger."


def _execution_context_summary(execution_context: dict[str, Any]) -> str:
    context = str(execution_context.get("execution_context", "unspecified")).replace("_", " ")
    if execution_context.get("requires_replay_evidence"):
        return f"{context.title()} requires replay-backed governance evidence."
    return f"{context.title()} execution context is modeled for governance interpretation."


def _approval_chain_summary(approval_chain: dict[str, Any]) -> str:
    count = approval_chain.get("required_approval_count") or "operator-reviewed"
    roles = ", ".join(approval_chain.get("required_roles") or ["unspecified role"])
    if approval_chain.get("independence_required"):
        return f"{count} approvals require independent responsibility from {roles}."
    return f"{count} approvals bind responsibility to {roles}."


def _implies_deferred_execution(text: str) -> bool:
    return _contains_any(
        text.lower(),
        [
            "deferred execution",
            "later execution",
            "future execution",
            "asynchronous execution",
            "async execution",
            "delayed execution",
        ],
    )


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _normalize_source_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_time(source_hash: str) -> str:
    # Stable logical timestamp: deterministic artifacts must not depend on wall-clock time.
    seconds = int(source_hash.removeprefix("sha256:")[:8], 16) % (365 * 24 * 60 * 60)
    day = seconds // 86400 + 1
    hour = seconds % 86400 // 3600
    minute = seconds % 3600 // 60
    second = seconds % 60
    month = min(12, (day - 1) // 31 + 1)
    month_day = ((day - 1) % 28) + 1
    return f"2026-{month:02d}-{month_day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"


def _slug(value: str) -> str:
    text = str(value or "").strip().lower()
    chars = []
    last_dash = False
    for char in text:
        if char.isalnum():
            chars.append(char)
            last_dash = False
        elif not last_dash:
            chars.append("-")
            last_dash = True
    return "".join(chars).strip("-")


def _mutation_target(action: str) -> str:
    return _slug(action).replace("-", "_")
