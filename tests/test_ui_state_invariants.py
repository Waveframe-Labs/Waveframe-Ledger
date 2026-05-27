from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "ui" / "app.js"


def test_opening_registry_semantic_preview_preserves_draft_workflow_state():
    source = APP_JS.read_text(encoding="utf-8")
    block = _action_block(source, "open-preview")

    assert "preserveWorkflow: true" in block
    assert "updateWorkflowState" not in block
    assert "exportButton.disabled = false" not in block
    assert "pendingRegistration" not in block
    assert "showPage(\"preview\")" in block


def test_viewing_receipt_does_not_register_authority():
    source = APP_JS.read_text(encoding="utf-8")
    block = _action_block(source, "view-receipt")

    assert "renderBundleDetail(entry, \"receipt\")" in block
    assert "publishCurrentBundleToRegistry" not in block
    assert "updateWorkflowState" not in block
    assert "pendingRegistration" not in block


def test_viewing_lineage_does_not_mutate_lifecycle():
    source = APP_JS.read_text(encoding="utf-8")
    block = _action_block(source, "view-lineage")

    assert "renderBundleDetail(entry, \"lineage\")" in block
    assert "updateRegistryEntry" not in block
    assert "appendLifecycleOnce" not in block
    assert "updateWorkflowState" not in block


def test_diagnostics_rendering_does_not_change_workflow_state():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderDiagnostics")

    assert "updateWorkflowState" not in body
    assert "workflowState." not in body
    assert "pendingRegistration" not in body
    assert "publishCurrentBundleToRegistry" not in body


def test_export_requires_explicit_impact_review():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "exportBundle")

    guard = body.index("if (!workflowState.impactReviewed)")
    receipt = body.index("const receipt = await buildPublicationReceipt")
    state_update = body.index("updateWorkflowState({")

    assert guard < receipt < state_update
    assert "showPage(\"diagnostics\")" in body[guard:receipt]
    assert "bundleExported: true" in body
    assert "receiptGenerated: true" in body


def test_registration_requires_successful_export_receipt():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "registerAuthorityLocally")

    guard = body.index("if (!pendingRegistration)")
    register = body.index("const entry = publishCurrentBundleToRegistry")
    state_update = body.index("updateWorkflowState({")

    assert guard < register < state_update
    assert "showPage(\"diagnostics\")" in body[guard:register]
    assert "authorityRegistered: true" in body


def test_editing_draft_invalidates_review_export_receipt_and_registration_state():
    source = APP_JS.read_text(encoding="utf-8")
    input_block = _event_listener_block(source, 'form.addEventListener("input"')
    change_block = _event_listener_block(source, 'form.addEventListener("change"')

    for block in (input_block, change_block):
        assert "pendingRegistration = null" in block
        assert "workflowTimestamps.reviewed = null" in block
        assert "workflowTimestamps.exported = null" in block
        assert "workflowTimestamps.registered = null" in block
        assert "exportButton.disabled = true" in block
        assert "registerButton.disabled = true" in block
        assert "impactReviewed: false" in block
        assert "bundleExported: false" in block
        assert "receiptGenerated: false" in block
        assert "authorityRegistered: false" in block


def test_policy_extraction_does_not_advance_publication_workflow():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "extractPolicySemantics")

    assert 'fetch("/api/extract"' in body
    assert "impactReviewed: false" in body
    assert "bundleExported: false" in body
    assert "receiptGenerated: false" in body
    assert "authorityRegistered: false" in body
    assert "exportButton.disabled = true" in body
    assert "registerButton.disabled = true" in body
    assert "pendingRegistration = null" in body
    assert "generateArtifacts" not in body


def test_using_extracted_draft_requires_impact_review_before_export():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "useExtractedDraft")

    assert "applyDraftToForm" in body
    assert "markDraftInvalidated()" in body
    assert "impactReviewed: false" in body
    assert "bundleExported: false" in body
    assert "receiptGenerated: false" in body
    assert "authorityRegistered: false" in body
    assert "Review Impact is required before export." in body
    assert "exportButton.disabled = true" in body


def test_escalation_authoring_is_text_driven_not_single_threshold_field():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")

    assert "Escalation Semantics" in html
    assert 'name="escalation_semantics"' in html
    assert 'name="escalation_threshold"' not in html
    assert "Financial transfer threshold" not in html
    assert "data.get(\"escalation_semantics\")" in source


def _function_body(source: str, function_name: str) -> str:
    marker = f"function {function_name}"
    start = source.index(marker)
    brace = source.index("{", start)
    end = _matching_brace(source, brace)
    return source[brace + 1 : end]


def _action_block(source: str, action: str) -> str:
    marker = f'action === "{action}"'
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
