"""Local Ledger UI server for artifact authoring and rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from governance_ledger.local_registry.projection import (
    build_authority_workspace_projection as build_local_authority_workspace_projection,
)
from governance_ledger.local_registry.projections.operational import build_authority_operational_summary
from governance_ledger.semantics.compiler import compile_semantic_commit_bundle
from governance_ledger.semantics.diagnostics import build_governance_quality_diagnostics
from governance_ledger.semantics.diffing import build_semantic_authority_diff
from governance_ledger.semantics.extraction import extract_governance_semantics
from governance_ledger.semantics.lifecycle_enforcement import build_semantic_lifecycle_enforcement_projection
from governance_ledger.semantics.packets import build_governance_review_packet
from governance_ledger.semantics.preview import build_governance_impact_preview
from governance_ledger.semantics.publication import build_authority_bundle, build_publication_receipt

ROOT = Path(__file__).resolve().parent.parent
UI_ROOT = ROOT / "ui"


def run_ui_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the local Ledger UI server."""
    _resolve_ui_root()
    server = ThreadingHTTPServer((host, port), LedgerUIHandler)
    print(f"Ledger UI listening at http://{host}:{port}")
    server.serve_forever()


class LedgerUIHandler(BaseHTTPRequestHandler):
    server_version = "GovernanceLedgerUI/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._write_json({"status": "ok"})
            return
        path = "/index.html" if parsed.path == "/" else parsed.path
        self._serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/extract":
            try:
                payload = self._read_json_body()
                source_text = payload.get("source_text")
                if not isinstance(source_text, str) or not source_text.strip():
                    raise ValueError("Policy text is required for semantic extraction.")
                self._write_json(extract_governance_semantics(source_text))
            except ValueError as exc:
                self._write_json({"error": str(exc)}, status=400)
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._write_json({"error": f"Unable to extract governance semantics: {exc}"}, status=500)
            return
        if parsed.path == "/api/publication-receipt":
            try:
                payload = self._read_json_body()
                bundle = payload.get("authority_bundle") if isinstance(payload.get("authority_bundle"), dict) else {}
                published_at = payload.get("published_at")
                if not isinstance(published_at, str) or not published_at:
                    raise ValueError("Publication receipt requires published_at.")
                receipt = build_publication_receipt(
                    authority_bundle=bundle,
                    published_at=published_at,
                    readiness_confirmations=(
                        payload.get("readiness_confirmations")
                        if isinstance(payload.get("readiness_confirmations"), dict)
                        else {}
                    ),
                    publication_notes=(
                        payload.get("publication_notes")
                        if isinstance(payload.get("publication_notes"), list)
                        else []
                    ),
                )
                self._write_json(build_publication_receipt_response(receipt))
            except ValueError as exc:
                self._write_json({"error": str(exc)}, status=400)
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._write_json({"error": f"Unable to build publication receipt: {exc}"}, status=500)
            return
        if parsed.path == "/api/semantic-diff":
            try:
                payload = self._read_json_body()
                previous_authority = payload.get("previous_authority")
                current_authority = payload.get("current_authority")
                if not isinstance(previous_authority, dict) or not isinstance(current_authority, dict):
                    raise ValueError("Semantic diff requires previous_authority and current_authority objects.")
                self._write_json(build_semantic_authority_diff(previous_authority, current_authority))
            except ValueError as exc:
                self._write_json({"error": str(exc)}, status=400)
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._write_json({"error": f"Unable to build semantic authority diff: {exc}"}, status=500)
            return
        if parsed.path == "/api/semantic-lifecycle-enforcement":
            try:
                payload = self._read_json_body()
                semantic_diff = payload.get("semantic_authority_diff")
                if not isinstance(semantic_diff, dict):
                    raise ValueError("Lifecycle enforcement projection requires semantic_authority_diff.")
                self._write_json(build_semantic_lifecycle_enforcement_projection(semantic_diff))
            except ValueError as exc:
                self._write_json({"error": str(exc)}, status=400)
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._write_json({"error": f"Unable to build semantic lifecycle enforcement projection: {exc}"}, status=500)
            return
        if parsed.path == "/api/compile-authority":
            try:
                payload = self._read_json_body()
                semantic_commit = payload.get("semantic_commit_bundle")
                if not isinstance(semantic_commit, dict):
                    raise ValueError("Authority compilation requires semantic_commit_bundle.")
                self._write_json(compile_semantic_commit_bundle(semantic_commit))
            except ValueError as exc:
                self._write_json({"error": str(exc)}, status=400)
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._write_json({"error": f"Unable to compile authority contract: {exc}"}, status=500)
            return
        if parsed.path != "/api/compose":
            self._write_json({"error": "not found"}, status=404)
            return
        try:
            payload = self._read_json_body()
            draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
            result = compose_authority_publication(draft)
            self._write_json(result)
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._write_json({"error": f"Unable to compose authority publication: {exc}"}, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/")
        ui_root = _resolve_ui_root()
        target = (ui_root / relative).resolve()
        if not str(target).startswith(str(ui_root.resolve())) or not target.is_file():
            self._write_json({"error": "not found"}, status=404)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def compose_authority_publication(draft: dict[str, Any]) -> dict[str, Any]:
    """Build local UI artifacts from governance authoring fields."""
    authority = build_authority_contract_from_draft(draft)
    preview = build_governance_impact_preview(authority)
    review_packet = build_governance_review_packet(
        authority_contract=authority,
        governance_impact_preview=preview,
        review_metadata={
            "disposition": "AUTHORITY_REVIEW_REQUIRED",
            "annotations": [],
        },
    )
    manifest = build_publication_manifest(authority)
    bundle = build_authority_bundle(
        authority_contract=authority,
        publication_manifest=manifest,
        governance_impact_preview=preview,
        governance_review_packets=[review_packet],
    )
    diagnostics = build_ui_diagnostics(authority, draft, bundle)
    release_narrative = build_authority_release_narrative(authority, preview, bundle)
    workspace_projection = build_authority_workspace_projection(
        authority,
        preview,
        bundle,
        diagnostics,
        release_narrative,
    )
    return {
        "authority_contract": authority,
        "governance_impact_preview": preview,
        "governance_review_packet": review_packet,
        "publication_manifest": manifest,
        "authority_bundle": bundle,
        "authority_registry_projection": build_authority_registry_projection(authority, bundle),
        "authority_release_narrative": release_narrative,
        "authority_workspace_projection": workspace_projection,
        "authority_operational_summary": build_authority_operational_summary(
            authority=authority,
            bundle=bundle,
            workspace_projection=workspace_projection,
        ),
        "diagnostics": diagnostics,
    }


def build_publication_receipt_response(receipt: dict[str, Any]) -> dict[str, Any]:
    """Wrap a publication receipt in the UI export response shape."""
    return {
        "status": "exported",
        "publication_receipt": receipt,
        "receipt_hash": receipt["receipt_hash"],
        "bundle_hash": receipt["bundle_hash"],
    }


def _resolve_ui_root() -> Path:
    candidates = [
        UI_ROOT,
        Path.cwd() / "ui",
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    raise RuntimeError("Ledger UI files were not found. Run from the repository root containing ui/.")


def build_authority_contract_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Compile local UI authoring fields into an authority contract shape."""
    protected_system = _required_text(draft, "protected_system", "protected system")
    governed_action = _required_text(draft, "governed_action", "governed action")
    approver_role = _required_text(draft, "approver_role", "approver role")
    contract_id = _slug(draft.get("contract_id") or protected_system)
    contract_version = str(draft.get("contract_version") or "0.1.0")
    approval_count = _positive_int(draft.get("approval_count"), default=1)
    threshold = _positive_number(
        draft.get("escalation_threshold") or _threshold_from_text(str(draft.get("escalation_semantics") or "")),
        default=250000,
    )
    validity_days = _positive_int(draft.get("validity_days"), default=30)
    continuity_revalidation = bool(draft.get("continuity_revalidation", True))
    revocation_invalidates_resume = bool(draft.get("revocation_invalidates_resume", True))
    temporal_semantics = _temporal_semantics_from_draft(draft, validity_days)
    state_snapshot_semantics = _state_snapshot_semantics_from_draft(
        draft,
        continuity_revalidation=continuity_revalidation,
        revocation_invalidates_resume=revocation_invalidates_resume,
    )
    execution_context_semantics = _execution_context_semantics_from_draft(draft)
    identity_semantics = _identity_semantics_from_draft(draft, approver_role, approval_count, governed_action)
    category = str(draft.get("governance_category") or "Operational")
    mutation_targets = _string_list(draft.get("mutation_targets")) or [_mutation_target(governed_action)]

    authority = {
        "schema_version": "authority_contract.v1",
        "contract_id": contract_id,
        "contract_version": contract_version,
        "governance_category": category,
        "protected_resource": protected_system,
        "scope": {
            "description": protected_system,
            "resource": protected_system,
            "domain": category,
        },
        "governed_actions": [governed_action],
        "mutation_targets": mutation_targets,
        "authority_requirements": {
            "required_roles": [approver_role],
            "approval_count": approval_count,
        },
        "approval_requirements": {
            "thresholds": [
                {
                    "field": "amount",
                    "operator": ">",
                    "value": threshold,
                    "requires_role": approver_role,
                }
            ],
            "required": [
                {
                    "role": approver_role,
                }
            ],
        },
        "escalation_requirements": {
            "threshold": {
                "field": "amount",
                "operator": ">",
                "value": threshold,
                "requires_role": approver_role,
            },
        },
        "continuity_requirements": {
            "resume_requires_current_authority": continuity_revalidation,
            "revoked_authority_invalidates_resume": revocation_invalidates_resume,
        },
        "review_requirements": {
            "approval_count": approval_count,
            "validity_window_days": validity_days,
        },
        "decision_trace_fields": [
            "authority_ref",
            "contract_hash",
            "actor",
            "action",
            "protected_resource",
            "threshold",
            "approvals",
        ],
        "replay_requirements": [
            "authority_hash",
            "decision_trace",
            "approval_evidence",
        ],
        "artifact_requirements": {
            "required": ["approval_evidence", "decision_trace"],
        },
        "stage_requirements": {
            "allowed_transitions": [
                {"from": "draft", "to": "review"},
                {"from": "review", "to": "published"},
            ],
        },
        "validity": {
            "window_days": validity_days,
        },
        "temporal_semantics": temporal_semantics,
    }
    if state_snapshot_semantics:
        authority["state_snapshot_semantics"] = state_snapshot_semantics
    if execution_context_semantics:
        authority["execution_context_semantics"] = execution_context_semantics
    authority.update(identity_semantics)
    authority["contract_hash"] = _artifact_hash(authority)
    return authority


def build_publication_manifest(authority: dict[str, Any]) -> dict[str, Any]:
    authority_ref = f"{authority['contract_id']}@{authority['contract_version']}"
    publication_id = f"pub-{authority['contract_id']}-{authority['contract_version'].replace('.', '-')}"
    contract_path = f"contracts/{authority['contract_id']}-{authority['contract_version']}.contract.json"
    source_hash = _artifact_hash(
        {
            "protected_resource": authority["protected_resource"],
            "governed_actions": authority["governed_actions"],
            "authority_ref": authority_ref,
        }
    )
    report_hash = _artifact_hash({"authority_ref": authority_ref, "contract_hash": authority["contract_hash"]})
    return {
        "schema_version": "publication_manifest.v1",
        "publication_id": publication_id,
        "published_at": None,
        "published_by": "governance-ledger-ui",
        "contracts": [
            {
                "contract_id": authority["contract_id"],
                "contract_version": authority["contract_version"],
                "contract_hash": authority["contract_hash"],
                "path": contract_path,
                "source_hash": source_hash,
                "compilation_report_hash": report_hash,
            }
        ],
        "reviews": [],
        "snapshots": [],
    }


def build_ui_diagnostics(
    authority: dict[str, Any],
    draft: dict[str, Any],
    bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    diagnostics = build_governance_quality_diagnostics(authority)
    if not bundle["schema_compatibility"]["compatible"]:
        diagnostics.append(
            _ui_diagnostic(
                "schema_compatibility",
                "Schema Compatibility",
                "Bundle schema compatibility check failed.",
                "Review generated artifacts before publication export.",
                domain="schema",
            )
        )
    if not _string_list(draft.get("mutation_targets")):
        diagnostics.append(
            _ui_diagnostic(
                "default_mutation_target",
                "Derived Mutation Target",
                "Mutation target was derived from governed action; confirm it matches the operational system.",
                "Replace the derived mutation target if the governed operation uses a different system action.",
                domain="authoring",
            )
        )
    temporal = authority.get("temporal_semantics") if isinstance(authority.get("temporal_semantics"), dict) else {}
    if temporal.get("validity_window") and temporal.get("timestamp_source") in (None, "", "unspecified"):
        diagnostics.append(
            _ui_diagnostic(
                "temporal_source_ambiguity",
                "Temporal Source Ambiguity",
                "Validity window exists but timestamp source is unspecified.",
                "Record whether expiration binds to execution payload time, signed oracle time, block timestamp, or Cloud-attested time.",
                domain="temporal",
                severity="warning",
            )
        )
    continuity = authority.get("continuity_requirements") if isinstance(authority.get("continuity_requirements"), dict) else {}
    snapshot = authority.get("state_snapshot_semantics") if isinstance(authority.get("state_snapshot_semantics"), dict) else {}
    if continuity.get("resume_requires_current_authority") and not snapshot.get("snapshot_required"):
        diagnostics.append(
            _ui_diagnostic(
                "snapshot_continuity_gap",
                "Snapshot Continuity Gap",
                "Resumed workflow revalidation is required but no state snapshot expectation is defined.",
                "Define the governance posture snapshot subject and comparison expectation for resumed workflows.",
                domain="continuity",
                severity="warning",
            )
        )
    execution_context = authority.get("execution_context_semantics") if isinstance(authority.get("execution_context_semantics"), dict) else {}
    if _draft_implies_deferred_execution(draft) and not execution_context:
        diagnostics.append(
            _ui_diagnostic(
                "execution_context_ambiguity",
                "Execution Context Ambiguity",
                "Governance semantics imply deferred execution but no execution context was defined.",
                "Model whether execution is queued, scheduled, external, resumed, agent-orchestrated, or Cloud-attested.",
                domain="execution_context",
                severity="warning",
            )
        )
    if execution_context.get("requires_replay_evidence") and not _string_list(authority.get("replay_requirements")):
        diagnostics.append(
            _ui_diagnostic(
                "replay_requirement_gap",
                "Replay Requirement Gap",
                "Queued or deferred execution semantics require replay evidence expectations.",
                "Record replay requirements that bind execution evidence to the authority version.",
                domain="replay",
                severity="warning",
            )
        )
    if execution_context.get("resume_behavior") == "revalidate_on_resume" and not continuity.get("resume_requires_current_authority"):
        diagnostics.append(
            _ui_diagnostic(
                "resume_validation_gap",
                "Resume Validation Gap",
                "Resumable execution context exists without continuity revalidation semantics.",
                "Require resumed workflows to revalidate against current governance posture.",
                domain="continuity",
                severity="warning",
            )
        )
    approval_chain = authority.get("approval_chain_semantics") if isinstance(authority.get("approval_chain_semantics"), dict) else {}
    if approval_chain.get("independence_required") and not approval_chain.get("independent_actor_refs"):
        diagnostics.append(
            _ui_diagnostic(
                "approval_independence_ambiguity",
                "Approval Independence Ambiguity",
                "Approval semantics imply separation-of-duties but independent actors are undefined.",
                "Define which actors or roles must remain independent in the approval chain.",
                domain="identity",
                severity="warning",
            )
        )
    if approval_chain.get("delegation_posture") == "ambiguous":
        diagnostics.append(
            _ui_diagnostic(
                "delegation_ambiguity",
                "Delegation Ambiguity",
                "Delegated authority language exists without delegation boundaries.",
                "Record whether delegation is prohibited or bounded by a named authority scope.",
                domain="identity",
                severity="warning",
            )
        )
    identity_continuity = authority.get("identity_continuity_semantics") if isinstance(authority.get("identity_continuity_semantics"), dict) else {}
    if (continuity.get("resume_requires_current_authority") or execution_context.get("resume_behavior") == "revalidate_on_resume") and not identity_continuity.get("identity_continuity_required"):
        diagnostics.append(
            _ui_diagnostic(
                "identity_continuity_gap",
                "Identity Continuity Gap",
                "Resumable workflow semantics exist without identity continuity expectations.",
                "Record that actor or role bindings must remain valid when execution resumes.",
                domain="identity",
                severity="warning",
            )
        )
    actor = authority.get("governance_actor") if isinstance(authority.get("governance_actor"), dict) else {}
    threshold = (authority.get("escalation_requirements") or {}).get("threshold") if isinstance(authority.get("escalation_requirements"), dict) else {}
    threshold_value = threshold.get("value") if isinstance(threshold, dict) else None
    if isinstance(threshold_value, (int, float)) and threshold_value >= 250000 and not actor.get("attestation_required"):
        diagnostics.append(
            _ui_diagnostic(
                "attestation_requirement_gap",
                "Attestation Requirement Gap",
                "High-impact governance posture exists without actor attestation semantics.",
                "Record whether the responsible actor must provide attested identity evidence.",
                domain="identity",
                severity="warning",
            )
        )
    return diagnostics


def build_authority_registry_projection(authority: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic registry display metadata for local UI persistence."""
    return {
        "schema_version": "authority_registry_projection.v1",
        "authority_ref": bundle["authority_ref"],
        "governed_resource": authority["protected_resource"],
        "governed_action": (authority.get("governed_actions") or ["unspecified action"])[0],
        "continuity_posture": _continuity_posture(authority),
        "escalation_threshold": _escalation_threshold(authority),
        "semantic_integrity_posture": "compatible"
        if bundle["schema_compatibility"]["compatible"]
        else "requires review",
    }


def build_authority_workspace_projection(
    authority: dict[str, Any],
    preview: dict[str, Any],
    bundle: dict[str, Any],
    diagnostics: list[dict[str, Any]],
    release_narrative: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical UI projection for local authority workspace state."""
    projection = build_local_authority_workspace_projection(
        authority=authority,
        preview=preview,
        bundle=bundle,
        diagnostics=diagnostics,
        publication_meaning=release_narrative["headline"],
        publication_summary=release_narrative["publication_summary"],
        operational_change=release_narrative["operational_change"],
        continuity_posture=release_narrative["continuity_summary"],
        lifecycle_effect=release_narrative["lifecycle_summary"],
        timeline=[
            {
                "event": "drafted",
                "detail": f"{bundle['authority_ref']} authority draft compiled from local authoring fields.",
            },
            {
                "event": "semantic_artifacts_generated",
                "detail": "Ledger generated deterministic preview, review packet, bundle, diagnostics, and workspace projection.",
            },
        ],
    )
    projection["diagnostics_summary"] = _legacy_diagnostics_summary(projection["diagnostic_rollup"])
    projection["semantic_sources"]["release_narrative"] = release_narrative["schema_version"]
    return projection


def build_authority_release_narrative(
    authority: dict[str, Any],
    preview: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic operator-facing publication narrative."""
    enforcement = _first_string(preview.get("enforcement_behavior"))
    lifecycle = _first_string(preview.get("lifecycle_implications"))
    continuity = _first_string(bundle.get("continuity_implications"))
    consequence = _first_string(bundle.get("operational_implications"))
    authority_ref = bundle["authority_ref"]
    resource = authority["protected_resource"]
    action = (authority.get("governed_actions") or ["governed execution"])[0]
    return {
        "schema_version": "authority_release_narrative.v1",
        "authority_ref": authority_ref,
        "headline": f"{authority_ref} governs {action} for {resource}.",
        "operational_change": enforcement or f"{action} is governed by {authority_ref}.",
        "publication_summary": (
            f"Publishing this authority creates a replayable governance record for {resource}. "
            f"{consequence or 'Execution evidence can bind to this authority version.'}"
        ),
        "continuity_summary": continuity or "Continuity posture should be reviewed before publication.",
        "lifecycle_summary": lifecycle or "Lifecycle implications should be reviewed before publication.",
    }


def _legacy_diagnostics_summary(rollup: dict[str, Any]) -> dict[str, int]:
    return {
        "findings": rollup["finding_count"],
        "warnings": rollup["warning_count"],
        "info": rollup["info_count"],
    }


def _ui_diagnostic(
    code: str,
    title: str,
    text: str,
    recommendation: str,
    *,
    domain: str,
    severity: str = "info",
) -> dict[str, Any]:
    return {
        "schema_version": "governance_quality_diagnostic.v1",
        "type": "governance_quality_diagnostic",
        "code": code,
        "title": title,
        "severity": severity,
        "domain": domain,
        "text": text,
        "recommendation": recommendation,
        "rationale": "This diagnostic exists to make publication posture explicit before export.",
        "operational_examples": [
            "A reviewer can confirm generated artifact structure before relying on the exported bundle."
        ],
        "replay_implications": [
            "Receipts and registry entries should retain enough context for later evidence review."
        ],
        "blocks_publication": False,
        "non_goals": [
            "does_not_reject_publication",
            "does_not_evaluate_admissibility",
            "does_not_call_guard",
            "does_not_call_cloud",
            "does_not_score_policy",
        ],
    }


def _first_string(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, str) and item:
            return item
    return None


def _continuity_posture(authority: dict[str, Any]) -> str:
    requirements = authority.get("continuity_requirements") or {}
    if (
        requirements.get("resume_requires_current_authority")
        and requirements.get("revoked_authority_invalidates_resume")
    ):
        return "resume revalidation and revocation invalidation"
    if requirements.get("resume_requires_current_authority"):
        return "resume revalidation"
    if requirements.get("revoked_authority_invalidates_resume"):
        return "revocation invalidation"
    return "continuity review recommended"


def _escalation_threshold(authority: dict[str, Any]) -> str:
    threshold = (authority.get("escalation_requirements") or {}).get("threshold")
    if not isinstance(threshold, dict):
        return "not defined"
    field = threshold.get("field") or "threshold"
    operator = threshold.get("operator") or ">"
    value = _format_number(threshold.get("value"))
    return f"{field} {operator} {value}"


def _format_number(value: Any) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value or "")


def _temporal_semantics_from_draft(draft: dict[str, Any], validity_days: int) -> dict[str, Any]:
    semantics = draft.get("temporal_semantics")
    if isinstance(semantics, dict) and semantics:
        result = dict(semantics)
        result.setdefault("schema_version", "temporal_authority_semantics.v1")
        result.setdefault("validity_window", f"P{validity_days}D")
        result.setdefault("timestamp_source", "unspecified")
        result.setdefault("expiration_basis", "unspecified")
        result.setdefault("runtime_enforced_by", "Guard/Cloud")
        return result
    return {
        "schema_version": "temporal_authority_semantics.v1",
        "validity_window": f"P{validity_days}D",
        "timestamp_source": str(draft.get("timestamp_source") or "unspecified"),
        "expiration_basis": str(draft.get("expiration_basis") or "unspecified"),
        "runtime_enforced_by": "Guard/Cloud",
    }


def _state_snapshot_semantics_from_draft(
    draft: dict[str, Any],
    *,
    continuity_revalidation: bool,
    revocation_invalidates_resume: bool,
) -> dict[str, Any]:
    semantics = draft.get("state_snapshot_semantics")
    if isinstance(semantics, dict) and semantics:
        result = dict(semantics)
        result.setdefault("schema_version", "state_posture_snapshot_semantics.v1")
        result.setdefault("snapshot_required", True)
        result.setdefault("snapshot_hash_algorithm", "sha256")
        result.setdefault("snapshot_subject", "active_governance_state")
        result.setdefault("resume_comparison", "snapshot_hash_must_match_active_state_hash")
        result.setdefault("drift_result", "continuity_drift_detected")
        result.setdefault("runtime_enforced_by", "Guard/Cloud")
        return result
    if not (continuity_revalidation or revocation_invalidates_resume):
        return {}
    return {
        "schema_version": "state_posture_snapshot_semantics.v1",
        "snapshot_required": True,
        "snapshot_hash_algorithm": "sha256",
        "snapshot_subject": str(draft.get("snapshot_subject") or "active_governance_state"),
        "resume_comparison": "snapshot_hash_must_match_active_state_hash",
        "drift_result": "continuity_drift_detected",
        "runtime_enforced_by": "Guard/Cloud",
    }


def _execution_context_semantics_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    semantics = draft.get("execution_context_semantics")
    if isinstance(semantics, dict) and semantics:
        result = dict(semantics)
        result.setdefault("schema_version", "execution_context_semantics.v1")
        result.setdefault("execution_context", "unspecified")
        result.setdefault("execution_boundary", "unspecified")
        result.setdefault("requires_replay_evidence", False)
        result.setdefault("requires_state_snapshot", False)
        result.setdefault("requires_temporal_validation", False)
        result.setdefault("resume_behavior", "unspecified")
        result.setdefault("continuity_risk_profile", "unspecified")
        result.setdefault("runtime_enforced_by", "Guard/Cloud")
        return result
    return {}


def _identity_semantics_from_draft(
    draft: dict[str, Any],
    approver_role: str,
    approval_count: int,
    governed_action: str,
) -> dict[str, Any]:
    result = {}
    for key in (
        "governance_actor",
        "authority_role_binding",
        "approval_chain_semantics",
        "identity_continuity_semantics",
    ):
        if isinstance(draft.get(key), dict) and draft[key]:
            result[key] = dict(draft[key])
    if "governance_actor" not in result:
        result["governance_actor"] = {
            "schema_version": "governance_actor.v1",
            "actor_id": approver_role,
            "actor_type": "human_role",
            "authority_scope": [f"{_slug(governed_action).replace('-', '_')}_approval"],
            "delegation_allowed": False,
            "attestation_required": False,
            "identity_continuity_required": bool((draft.get("continuity_revalidation", True))),
        }
    if "authority_role_binding" not in result:
        result["authority_role_binding"] = {
            "schema_version": "authority_role_binding.v1",
            "role_id": approver_role,
            "actor_ref": approver_role,
            "responsibilities": ["approval_responsibility"],
            "accountability_boundary": "governance_approval",
            "delegation_posture": "not_allowed",
        }
    if "approval_chain_semantics" not in result:
        result["approval_chain_semantics"] = {
            "schema_version": "approval_chain_semantics.v1",
            "required_approval_count": approval_count,
            "required_roles": [approver_role],
            "independence_required": approval_count > 1,
            "self_approval_prohibited": approval_count > 1,
            "independent_actor_refs": [approver_role] if approval_count > 1 else [],
            "delegation_posture": "not_allowed",
            "attestation_required": False,
            "human_in_loop_required": True,
            "ai_recommendation_posture": "not_present",
        }
    continuity = bool(draft.get("continuity_revalidation", True))
    if continuity and "identity_continuity_semantics" not in result:
        result["identity_continuity_semantics"] = {
            "schema_version": "identity_continuity_semantics.v1",
            "identity_continuity_required": True,
            "resume_identity_check": "actor_or_role_binding_must_remain_valid",
            "identity_revocation_effect": "review_required",
            "runtime_enforced_by": "Guard/Cloud",
        }
    return result


def _required_text(draft: dict[str, Any], field: str, label: str) -> str:
    value = draft.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Draft authority requires {label}.")
    return value.strip()


def _positive_int(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("Numeric governance fields must be greater than zero.")
    return parsed


def _positive_number(value: Any, *, default: int) -> int | float:
    if value in (None, ""):
        return default
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("Numeric governance fields must be greater than zero.")
    return int(parsed) if parsed.is_integer() else parsed


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _draft_implies_deferred_execution(draft: dict[str, Any]) -> bool:
    text = " ".join(
        str(draft.get(field) or "")
        for field in ("governed_action", "escalation_semantics", "protected_system")
    ).lower()
    return any(
        phrase in text
        for phrase in (
            "deferred execution",
            "later execution",
            "future execution",
            "asynchronous execution",
            "async execution",
            "delayed execution",
        )
    )


def _slug(value: Any) -> str:
    text = str(value).lower()
    chars = []
    last_dash = False
    for character in text:
        if character.isalnum():
            chars.append(character)
            last_dash = False
        elif not last_dash:
            chars.append("-")
            last_dash = True
    slug = "".join(chars).strip("-")
    return slug or "authority"


def _mutation_target(action: str) -> str:
    return action.lower().replace(" ", "_")


def _threshold_from_text(text: str) -> int | None:
    import re

    match = re.search(r"(?:above|over|exceed(?:s|ing)?|greater than)\s+\$?(?P<amount>\d[\d,]*)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"\$?(?P<amount>\d[\d,]*)\s+(?:threshold|limit)", text, re.IGNORECASE)
    return int(match.group("amount").replace(",", "")) if match else None


def _artifact_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(prog="governance-ledger-ui")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_ui_server(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
