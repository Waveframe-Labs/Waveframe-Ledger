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
    for term in evidence_terms:
        candidate_rules.append(
            {
                "rule_type": "required_evidence",
                "summary": f"Policy text references {term.replace('_', ' ')} evidence.",
                "fields": {"evidence_term": term},
            }
        )

    ambiguities = _ambiguities(text, candidate)
    return {
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "extracted_at": _stable_time(source["source_hash"]),
        "extraction_method": "deterministic_pattern_pass",
        "confidence_posture": "requires_human_review",
        "candidate_authority": candidate,
        "candidate_rules": candidate_rules,
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
        r"(?:approved by|approval by|requires? approval from|requires? review by)\s+(?:the\s+)?(?P<value>[A-Za-z0-9 -]+?)(?:\.|,|;|\s+for|\s+when|\s+before|$)",
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
    if re.search(r"\bapproval\b|\bapproved\b", text, re.IGNORECASE):
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
    return ambiguities


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
