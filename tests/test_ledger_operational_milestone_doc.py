from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "LEDGER_OPERATIONAL_MILESTONE.md"


def test_operational_milestone_defines_completion_criteria():
    text = DOC.read_text(encoding="utf-8")

    for capability in (
        "create a governance authority locally",
        "generate deterministic semantic artifacts",
        "diagnose governance quality",
        "review operational impact",
        "export `authority_bundle.v1`",
        "generate `publication_receipt.v1`",
        "register authority locally",
        "maintain lifecycle events",
        "reconstruct governance chronology",
        "show active authority, continuity posture, replay posture, and diagnostics",
        "export artifacts for Cloud ingestion",
    ):
        assert capability in text


def test_operational_milestone_locks_stable_artifacts():
    text = DOC.read_text(encoding="utf-8")

    for stable in (
        "authority_bundle.v1",
        "governance_impact_preview.v1",
        "authority_diff_impact.v1",
        "governance_review_packet.v1",
        "publication_receipt.v1",
        "authority_workspace_projection.v1",
        "authority_registry_entry.v1",
        "authority_lifecycle_event.v1",
        "event ordering semantics",
        "mutation boundaries",
    ):
        assert stable in text


def test_operational_milestone_marks_experimental_surfaces():
    text = DOC.read_text(encoding="utf-8")

    for experimental in (
        "local browser persistence",
        "UI layout",
        "governance diagnostics catalog",
        "registry operations UI",
        "chronology replay UI",
        "projection freshness UI",
        "drift severity taxonomy",
    ):
        assert experimental in text


def test_operational_milestone_locks_cloud_and_guard_boundaries():
    text = DOC.read_text(encoding="utf-8")

    for cloud_owned in (
        "evidence retention",
        "runtime replay packages",
        "org/team operations",
        "audit trail storage",
        "multi-user review workflows",
        "billing/auth/SSO",
        "hosted evidence continuity",
        "operational escalation queues",
    ):
        assert cloud_owned in text

    for guard_owned in (
        "runtime admissibility",
        "execution blocking",
        "proposal evaluation",
        "enforcement decisions",
        "local runtime continuity enforcement",
    ):
        assert guard_owned in text
