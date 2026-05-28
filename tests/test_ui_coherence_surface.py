from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "ui" / "app.js"
INDEX_HTML = ROOT / "ui" / "index.html"


def test_coherence_surface_has_overview_and_registry_mount_points():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="overview-coherence-banner"' in html
    assert 'id="registry-coherence-banner"' in html


def test_coherence_surface_renders_projection_freshness_and_invalidation():
    source = APP_JS.read_text(encoding="utf-8")

    assert "function registryCoherenceProjection" in source
    assert "function authorityCoherenceProjection" in source
    assert "function projectionFreshnessForEntry" in source
    assert "Operational summary invalidated by draft changes. Impact review required before export." in source
    assert "authority_operational_summary.v1" in source
    assert "governance_continuity_projection.v1" in source
    assert "governance_timeline_projection.v1" in source
    assert "replay_posture" in source


def test_draft_edit_marks_projection_invalidation_visible():
    source = APP_JS.read_text(encoding="utf-8")
    input_block = _event_listener_block(source, 'form.addEventListener("input"')
    change_block = _event_listener_block(source, 'form.addEventListener("change"')
    invalidation_body = _function_body(source, "saveWorkingAuthoringSession")

    assert "saveWorkingAuthoringSession()" in input_block
    assert "saveWorkingAuthoringSession()" in change_block
    assert 'invalidateSemanticLineage("draft_changed")' in invalidation_body


def test_impact_review_clears_projection_invalidation():
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("function generateArtifacts")
    segment = source[start : source.index("function setBusy", start)]

    reviewed_at = segment.index("workflowTimestamps.reviewed = new Date().toISOString();")
    clear = segment.index("clearWorkflowInvalidation();")
    render = segment.index("renderArtifacts(payload")

    assert reviewed_at < clear < render


def _function_body(source: str, function_name: str) -> str:
    marker = f"function {function_name}"
    start = source.index(marker)
    brace = source.index("{", start)
    end = _matching_brace(source, brace)
    return source[brace + 1 : end]


def _event_listener_block(source: str, marker: str) -> str:
    start = source.index(marker)
    brace = source.index("{", start)
    end = _matching_brace(source, brace)
    return source[brace + 1 : end]


def _matching_brace(source: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("no matching brace found")
