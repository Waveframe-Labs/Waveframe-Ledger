from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "ui" / "app.js"
INDEX_HTML = ROOT / "ui" / "index.html"
STYLES_CSS = ROOT / "ui" / "styles.css"
README = ROOT / "README.md"


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

    compile_guard = body.index("if (!currentCompiledAuthorityContract")
    guard = body.index("if (!workflowState.impactReviewed)")
    receipt = body.index("const receipt = await buildPublicationReceipt")
    state_update = body.index("updateWorkflowState({")

    assert compile_guard < guard < receipt < state_update
    assert "compiled_contract_required" in body
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
        assert "saveWorkingAuthoringSession()" in block
        assert "saveDraftSession()" not in block
        assert "markDraftInvalidated()" not in block
        assert "scheduleLivePreview()" not in block
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


def test_authority_header_uses_committed_draft_not_live_form_state():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderAuthorityContext")

    assert "committedDraft" in body
    assert "readDraft()" not in body
    assert "No active governance posture" in body
    assert "No active governance posture" in (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


def test_new_working_session_is_empty_not_sample_authority_clone():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "startNewDraft")

    assert "policySourceText.value = \"\"" in body
    assert "clearAuthoringFields()" in body
    assert "clearExtractionReview()" in body
    assert "clearOperationalImpact()" in body
    assert "clearPublicationReadiness()" in body
    assert "resetSemanticStateMachine()" in body
    assert "currentExtraction = null" in body
    assert "committedDraft = null" in body
    assert "authoringSessionDirty = false" in body
    assert "saveWorkingAuthoringSession()" not in body
    assert "No active governance posture" in body
    assert "Manual Authority Definition" in html
    assert "Advanced Manual Authoring" not in html
    assert '<details id="manual-authority-definition" class="authoring-section governance-module">' in html
    assert "Manual-first authoring" in html
    assert "startManualFirstAuthoring" in source
    assert ">Corporate Treasury Transfer System transfers above" not in html
    assert 'value="Corporate Treasury Transfer System"' not in html
    assert 'value="transfer funds"' not in html
    assert 'value="treasury-policy"' not in html
    assert 'placeholder="e.g. Corporate Treasury Transfer System"' in html
    assert 'placeholder="e.g. transfer funds"' in html
    assert 'placeholder="e.g. treasury-policy"' in html
    assert 'name="continuity_revalidation" type="checkbox" checked' not in html
    assert 'name="revocation_invalidates_resume" type="checkbox" checked' not in html
    assert "Transfers above $250,000 require treasury governance review.</textarea>" not in html


def test_working_session_does_not_commit_semantic_interpretation():
    source = APP_JS.read_text(encoding="utf-8")
    save_body = _function_body(source, "saveDraftSession")
    working_body = _function_body(source, "saveWorkingAuthoringSession")

    assert "if (sessionOptions.commit)" in save_body
    assert "committedDraft = structuredClone(session.draft)" in save_body
    assert "authoringSessionDirty = false" in save_body
    assert "authoringSessionDirty = true" in working_body
    assert "commit: false" in working_body
    assert 'useExtractionButton.addEventListener("click", commitSemanticInterpretation)' in source


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


def test_committing_semantic_interpretation_is_boundary_before_operational_impact():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "commitSemanticInterpretation")

    assert "applyDraftToForm" in body
    assert 'semantic_state: "committed"' in body
    assert 'compiler_state: "not_compiled"' in body
    assert 'impact_state: "invalidated"' in body
    assert "impactReviewed: false" in body
    assert "bundleExported: false" in body
    assert "receiptGenerated: false" in body
    assert "authorityRegistered: false" in body
    assert "Compile Authority Contract next" in body
    assert "exportButton.disabled = true" in body


def test_compiler_boundary_is_visible_between_semantic_commit_and_operational_impact():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    compile_body = _function_body(source, "compileAuthorityContract")
    capability_body = _function_body(source, "canGenerateOperationalImpact")
    reset_body = _function_body(source, "resetCompiledAuthorityContract")
    invalidation_body = _function_body(source, "invalidateSemanticLineage")

    assert 'id="compile-authority-button"' in html
    assert "Compile Authority Contract" in html
    assert 'id="compiled-contract-boundary"' in html
    assert "Deterministic contract" in html
    assert "Contract fingerprint" in html
    assert "Guard projection preview" in html
    assert "compiled-contract-boundary" in css
    assert "background: #111" in css
    assert 'fetch("/api/compile-authority"' in compile_body
    assert 'fetch("/api/execution-projection"' in source
    assert "buildSemanticCommitBundleForUi" in compile_body
    assert "currentAuthorityExecutionProjection = await buildAuthorityExecutionProjectionForUi(compiled)" in compile_body
    assert "renderCompiledContractBoundary(compiled, currentAuthorityExecutionProjection)" in compile_body
    assert 'compiler_state: "compiled"' in compile_body
    assert "currentCompiledAuthorityContract" in capability_body
    assert 'semanticStateMachine.compiler_state === "compiled"' in capability_body
    assert "renderCompiledContractBoundary(null, null)" in reset_body
    assert "currentAuthorityExecutionProjection = null" in invalidation_body
    assert "renderGuardPreviewItems" in source


def test_publication_bundle_is_upgraded_with_compiled_contract_before_export():
    source = APP_JS.read_text(encoding="utf-8")
    upgrade_body = _function_body(source, "upgradeAuthorityBundleWithCompilerArtifacts")
    generate_body = source[source.index("async function generateArtifacts") : source.index("function setBusy")]
    export_body = _function_body(source, "exportBundle")

    assert "semantic_commit_bundle" in upgrade_body
    assert "compiled_authority_contract" in upgrade_body
    assert "semantic_commit_hash" in upgrade_body
    assert "compiled_contract_hash" in upgrade_body
    assert "compiled_authority_contract.v1" in upgrade_body
    assert "payload.authority_bundle = upgradeAuthorityBundleWithCompilerArtifacts(payload.authority_bundle)" in generate_body
    assert "currentArtifacts.authority_bundle = upgradeAuthorityBundleWithCompilerArtifacts" in export_body


def test_policy_source_changes_invalidate_semantic_lineage_before_impact_review():
    source = APP_JS.read_text(encoding="utf-8")
    block = _event_listener_block(source, 'policySourceText.addEventListener("input"')

    assert "policySourceDirty = true" in block
    assert "currentExtraction = null" in block
    assert 'invalidateSemanticLineage("policy_source_changed")' in block
    assert "impactReviewed: false" in block
    assert "bundleExported: false" in block
    assert "receiptGenerated: false" in block
    assert "authorityRegistered: false" in block


def test_operational_impact_renders_only_current_valid_semantic_lineage():
    source = APP_JS.read_text(encoding="utf-8")
    generate_start = source.index("async function generateArtifacts")
    generate_body = source[generate_start : source.index("function setBusy", generate_start)]
    render_start = source.index("function renderArtifacts")
    render_body = source[render_start : source.index("function authorityWorkspaceProjection", render_start)]
    invalidation_body = _function_body(source, "invalidateSemanticLineage")
    sync_body = _function_body(source, "syncPublicationActions")

    assert "canReviewImpact()" in generate_body
    assert "payload.ui_draft_hash = draftHash" in generate_body
    assert 'semantic_state: "valid"' in generate_body
    assert 'impact_state: "valid"' in generate_body
    assert "payload.ui_draft_hash !== committedDraftHash()" in render_body
    assert "renderInvalidatedImpact" in render_body
    assert "currentArtifacts = null" in invalidation_body
    assert "currentCompiledAuthorityContract = null" in invalidation_body
    assert "compiled_authority_contract.v1" in invalidation_body
    assert "governance_impact_preview.v1" in invalidation_body
    assert "generateButton.disabled = reviewBusy || !reviewAvailable" in sync_body


def test_ui_uses_action_level_capability_gates():
    source = APP_JS.read_text(encoding="utf-8")
    sync_body = _function_body(source, "syncPublicationActions")

    for function_name in (
        "canExtractSemantics",
        "canCommitSemanticInterpretation",
        "canReconcileAmbiguities",
        "canCompileAuthorityContract",
        "canGenerateOperationalImpact",
        "canReviewImpact",
        "canExportBundle",
        "canRegisterAuthority",
    ):
        assert f"function {function_name}" in source

    assert "extractPolicyButton.disabled = reviewBusy || !canExtractSemantics()" in sync_body
    assert "useExtractionButton.disabled = !canCommitSemanticInterpretation()" in sync_body
    assert "compileAuthorityButton.disabled = reviewBusy || !canCompileAuthorityContract()" in sync_body
    assert "openReconciliationButton.disabled = !canReconcileAmbiguities()" in sync_body
    assert "exportButton.disabled = !canExportBundle(hasArtifacts)" in sync_body
    assert "registerButton.disabled = !canRegisterAuthority()" in sync_body


def test_registry_stores_compiled_contract_lineage():
    source = APP_JS.read_text(encoding="utf-8")
    publish_body = _function_body(source, "publishCurrentBundleToRegistry")
    detail_body = _function_body(source, "renderRegistryDetailSummary")

    assert "compiled_contract_hash" in publish_body
    assert "semantic_commit_hash" in publish_body
    assert "compiler_version" in publish_body
    assert "compiled_authority_contract: currentArtifacts.compiled_authority_contract" in publish_body
    assert "Compiled Contract Lineage" in detail_body
    assert "Guard compatibility" in detail_body


def test_change_review_prefers_compiled_contracts_and_shows_guard_behavior_changes():
    source = APP_JS.read_text(encoding="utf-8")
    payload_body = _function_body(source, "authorityArtifactFromPayload")
    entry_body = _function_body(source, "authorityArtifactFromEntry")

    assert "payload.compiled_authority_contract" in payload_body
    assert "payload.authority_bundle?.compiled_authority_contract" in payload_body
    assert "entry.artifacts?.compiled_authority_contract" in entry_body
    assert "entry.bundle?.compiled_authority_contract" in entry_body
    assert "Guard behavior changes" in source
    assert "guard_enforcement_changes" in source


def test_publication_review_surfaces_compiled_authority_contract():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderCompiledContractPanel")

    assert 'id="compiled-contract-panel"' in html
    assert "Compiled Authority Contract" in html
    assert "Capability count" in body
    assert "Admissibility constraints" in body
    assert "Replay obligations" in body
    assert "Continuity requirements" in body
    assert "Guard compatibility posture" in body
    assert "Compiled contract hash" in body


def test_authoring_ui_exposes_staged_pipeline_not_apply_buttons():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")

    assert "Draft Policy" in html
    assert "Extract Governance Meaning" in html
    assert "Reconcile Ambiguities" in html
    assert "Commit Semantic Interpretation" in html
    assert "Compile Authority Contract" in html
    assert "commit-boundary-action" in html
    assert "Generate Operational Impact" in html
    assert "Apply Deterministic Fields" not in html
    assert "Apply All Candidate Semantics" not in html
    assert "Save Draft" not in html
    assert "useExtractedDraft" not in source


def test_extraction_ui_renders_capabilities_as_first_class_surface():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderSemanticExtraction")

    assert 'id="extracted-capabilities"' in html
    assert "Capability Explorer" in html
    assert "renderCapabilities(\"#extracted-capabilities\"" in body
    assert "Governed targets" in body
    assert "Governed operations" in body
    assert "Mutation classes" in body
    assert "function capabilitySummaries" in source
    assert "capabilityRequirementGroups" in source
    assert "capabilityRelationshipStrip" in source
    assert "This capability requires" in source


def test_extraction_gaps_open_manual_definition_without_prefilling_values():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderSemanticExtraction")

    assert "extraction.missing_information?.length" in body
    assert "openManualAuthorityDefinition()" in body
    assert "function closeManualAuthorityDefinition" in source


def test_extraction_ui_surfaces_operator_resolution_workflow():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderSemanticExtraction")

    assert 'id="reconciliation-workflow"' in html
    assert "Reconciliation Workspace" in html
    assert "Operator resolution workflow" not in html
    assert "renderReconciliationWorkflow(\"#reconciliation-workflow\"" in body
    assert "closest(\"details\")?.setAttribute(\"open\", \"\")" in source
    assert "Block publication" in source
    assert "Require signed authority timestamp" in source
    assert "Mark unresolved ambiguity" in source


def test_reconciliation_workspace_records_operator_decisions_and_blocks_unresolved_commit():
    source = APP_JS.read_text(encoding="utf-8")
    render_body = _function_body(source, "renderReconciliationWorkflow")
    commit_gate = _function_body(source, "canCommitSemanticInterpretation")
    commit_body = _function_body(source, "commitSemanticInterpretation")

    assert "semantic_interpretation_decision.v1" in source
    assert "semantic_unresolved_blocker.v1" in source
    assert "interpretationAuditTrail" in source
    assert "reconciliation-audit-trail" in render_body
    assert "dataset.saveResolution" in render_body
    assert "dataset.markUnresolved" in render_body
    assert "ambiguityTier" in render_body
    assert "interpretationComparisonPanel" in render_body
    assert "decisionRevisionHistory" in render_body
    assert "reconciliationDivergencePanel" in render_body
    assert "ambiguityGovernanceClass" in render_body
    assert "interpretationConfidencePosture" in render_body
    assert "interpretationConsequencePreview" in render_body
    assert "Operator rationale is required" in source
    assert "reconciliationIsComplete()" in commit_gate
    assert "Semantic commit is blocked. Review the Semantic commit blockers panel" in commit_body
    assert "governance_semantic_reconciliation" in commit_body
    assert "semantic_reconciliation_projection" in commit_body


def test_manual_authoring_declares_manual_first_and_extraction_assisted_modes():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "startManualFirstAuthoring")

    assert "manual-first or extraction-assisted drafting" in html
    assert "Manual-first authority definition opened" in body
    assert "Extraction remains optional" in body
    assert "Extraction-assisted overrides must be explicitly committed" in body


def test_reconciliation_tiers_lower_informational_friction_and_gate_high_impact():
    source = APP_JS.read_text(encoding="utf-8")
    tier_body = _function_body(source, "ambiguityTier")
    save_body = _function_body(source, "saveInterpretationDecision")

    assert '"timestamp_source_unspecified", "state_snapshot_subject_unspecified"' not in tier_body
    assert "approval_independence_ambiguity" in tier_body
    assert "undefined_threshold" in tier_body
    assert "contradictory_approval_semantics" in tier_body
    assert 'tier === "informational" ? "Accept informational posture"' in source
    assert '"Optional rationale"' not in source
    assert 'tier === "high-impact" && !rationale' in save_body
    assert 'tier === "high-impact" && !attested' in save_body


def test_reconciliation_uses_explicit_ambiguity_resolution_states():
    source = APP_JS.read_text(encoding="utf-8")
    reconciliation_body = _function_body(source, "buildGovernanceSemanticReconciliation")
    render_body = _function_body(source, "renderReconciliationWorkflow")
    decision_body = _function_body(source, "buildInterpretationDecision")
    save_body = _function_body(source, "saveInterpretationDecision")
    progression_body = _function_body(source, "ambiguityResolvedForProgression")
    readiness_body = _function_body(source, "semanticCommitReadiness")
    gate_body = _function_body(source, "reconciliationIsComplete")

    for state in ("pending", "acknowledged", "interpreted", "unresolved", "superseded"):
        assert state in source

    assert 'choice = tier === "informational"' in save_body
    assert '"Accept informational posture"' in save_body
    assert 'choices = tier === "informational" ? null' in render_body
    assert 'if (tier === "informational") {' in render_body
    assert 'actions.append(save);' in render_body
    assert 'if (tier !== "informational") item.appendChild(rationale)' in render_body
    assert 'else if (tier === "blocking") {' in render_body
    assert 'actions.append(unresolved);' in render_body
    assert 'decision_posture: resolutionState === "acknowledged" ? "operator_acknowledged" : "operator_reviewed"' in decision_body
    assert "ambiguity_resolution_state: resolutionState" in decision_body
    assert 'if (ambiguityTier(ambiguity) === "blocking") return false' in progression_body
    assert 'state === "acknowledged") return ambiguityTier(ambiguity) === "informational"' in progression_body
    assert "ambiguity_resolution_states: states" in reconciliation_body
    assert "!ambiguityResolvedForProgression(ambiguity)" in reconciliation_body
    assert "semantic_commit_readiness: semanticCommitReadiness()" in reconciliation_body
    assert "semantic_commit_readiness: currentReconciliation.semantic_commit_readiness" in source
    assert "schema_version: \"semantic_commit_readiness.v1\"" in readiness_body
    assert "semantic_commit_ready: blockingReasons.length === 0" in readiness_body
    assert "resolution_state_pending" in readiness_body
    assert "resolution_state_unresolved" in readiness_body
    assert "semanticCommitReadiness().semantic_commit_ready" in gate_body
    assert "ambiguity_fingerprint" in source
    assert "function ambiguityFingerprint" in source
    assert "semanticRecordMatchesAmbiguity" in source
    assert "withoutSemanticRecordForAmbiguity" in source


def test_reconciliation_renders_semantic_commit_blocker_observability():
    source = APP_JS.read_text(encoding="utf-8")
    css = STYLES_CSS.read_text(encoding="utf-8")
    render_body = _function_body(source, "renderReconciliationWorkflow")
    readiness_render_body = _function_body(source, "renderSemanticCommitReadiness")

    assert "renderSemanticCommitReadiness(node)" in render_body
    assert 'panel.id = "semantic-commit-readiness"' in readiness_render_body
    assert "Semantic commit blockers" in readiness_render_body
    assert "All required ambiguities are acknowledged or interpreted." in readiness_render_body
    assert "${item.ambiguity_id} (${shortHash(item.ambiguity_fingerprint" in readiness_render_body
    assert "-> ${item.resolution_state}" in readiness_render_body
    assert "All IDs:" in readiness_render_body
    assert "Resolved IDs:" in readiness_render_body
    assert "Pending IDs:" in readiness_render_body
    assert ".semantic-commit-readiness" in css


def test_reconciliation_surfaces_interpretation_authority_and_consequence_preview():
    source = APP_JS.read_text(encoding="utf-8")
    css = STYLES_CSS.read_text(encoding="utf-8")
    class_body = _function_body(source, "ambiguityGovernanceClass")
    confidence_body = _function_body(source, "interpretationConfidencePosture")
    decision_body = _function_body(source, "buildInterpretationDecision")
    consequences_body = _function_body(source, "interpretationConsequencesForChoice")

    for label in (
        "lexical ambiguity",
        "semantic ambiguity",
        "operational ambiguity",
        "continuity ambiguity",
        "authority ambiguity",
        "admissibility ambiguity",
    ):
        assert label in class_body

    for posture in ("stable", "sensitive", "fragile", "unsafe"):
        assert posture in confidence_body

    assert "governance_class: ambiguityGovernanceClass(ambiguity)" in decision_body
    assert "interpretation_confidence_posture: interpretationConfidencePosture(ambiguity)" in decision_body
    assert "interpretation_consequences: interpretationConsequencesForChoice(ambiguity, choice)" in decision_body
    assert "Guard projection changes approval verification requirements." in consequences_body
    assert "Admissibility, continuity, and escalation projections may change." in consequences_body
    assert "interpretation-consequence-preview" in css
    assert "reconciliation-classification" in css
    assert "reconciliation-badge" in css


def test_reconciliation_options_have_deterministic_strategy_provenance():
    source = APP_JS.read_text(encoding="utf-8")
    css = STYLES_CSS.read_text(encoding="utf-8")
    strategies_body = _function_body(source, "reconciliationStrategiesForAmbiguity")
    sources_body = _function_body(source, "reconciliationStrategySources")
    comparison_body = _function_body(source, "interpretationComparisonPanel")

    for label in (
        "policy modality",
        "lifecycle semantics",
        "continuity semantics",
        "authority semantics",
        "admissibility semantics",
        "temporal semantics",
        "evidence semantics",
    ):
        assert label in sources_body

    assert "reconciliationStrategyProvenancePanel" in source
    assert "Strategy source:" in comparison_body
    assert "Prohibit delegation" in strategies_body
    assert "Constrain delegation to explicit role binding" in strategies_body
    assert "Require governance renewal review" in strategies_body
    assert "reconciliation-strategy-provenance" in css


def test_manual_fields_have_explicit_provenance_and_no_restore_hydration():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    restore_body = _function_body(source, "restoreDraftSession")

    assert 'data-provenance-for="contract_version"' in html
    assert 'id="populate-committed-draft-button"' in html
    summary_start = html.index('<summary class="authoring-copy">')
    summary_end = html.index("</summary>", summary_start)
    assert 'id="populate-committed-draft-button"' not in html[summary_start:summary_end]
    assert "setFieldProvenance" in source
    assert "populateManualFieldsFromCommittedDraft" in source
    assert "applyDraftToForm(committedDraft, \"Committed\")" in source
    assert "Manual fields remain empty until explicitly populated" in restore_body


def test_continuity_posture_label_is_operational_not_alarmist():
    source = APP_JS.read_text(encoding="utf-8")

    assert 'continuity_risk: "Continuity Controls Active"' in source
    assert 'coherenceMetric("Continuity Controls"' in source
    assert '"Continuity Risk"' not in source
    assert "continuity risk" not in source.lower()


def test_escalation_authoring_is_text_driven_not_single_threshold_field():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")

    assert "Escalation Semantics" in html
    assert 'name="escalation_semantics"' in html
    assert 'name="escalation_threshold"' not in html
    assert "Financial transfer threshold" not in html
    assert "data.get(\"escalation_semantics\")" in source


def test_change_review_renders_semantic_authority_diff_artifact():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderChangeReview")

    assert "semantic_authority_diff.v1" in html
    assert 'id="change-semantic-diff"' in html
    assert 'id="change-guard-compatibility"' in html
    assert 'id="change-replay-continuity"' in html
    assert 'id="change-admissibility-projection"' in html
    assert 'id="change-unsafe-now"' in html
    assert "refreshChangeReviewSemanticDiff(payload)" in body
    assert 'fetch("/api/semantic-diff"' in source
    assert 'fetch("/api/semantic-lifecycle-enforcement"' in source


def test_registry_detail_surfaces_semantic_change_and_guard_impact():
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderRegistryDetailSummary")

    assert "What Changed Since Previous Version" in body
    assert "semantic_diff_summary" in source
    assert "guard_compatibility_projection" in source
    assert "replay_revalidation_required" in source
    assert "Lifecycle Enforcement Consequences" in body
    assert "lifecycleEnforcementSummaryView" in source


def test_change_review_surfaces_lifecycle_enforcement_chain():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    render_body = _function_body(source, "renderSemanticDiffLists")

    assert "What becomes unsafe now?" in html
    assert "Execution admissibility projection" in html
    assert "semantic_lifecycle_enforcement_projection.v1" in source
    assert "Replay continuity posture" in render_body
    assert "Projection only. Runtime admissibility remains Guard/Cloud-owned." in render_body
    assert "Unsafe-governance observations" in render_body


def test_supersede_attaches_semantic_diff_summary_without_guard_or_cloud_calls():
    source = APP_JS.read_text(encoding="utf-8")
    block = _action_block(source, "supersede")

    assert "fetchSemanticAuthorityDiff" in block
    assert "semanticDiffRegistrySummary" in block
    assert "semantic_diff_summary" in block
    assert "semantic_authority_diff" in block
    assert "semantic_lifecycle_enforcement_projection" in block
    assert "waveframe_guard" not in source
    assert "Cloud" not in block


def test_ui_uses_canonical_waveframe_branding_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = STYLES_CSS.read_text(encoding="utf-8")
    manifest = (ROOT / "ui" / "assets" / "branding" / "site.webmanifest").read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert "/assets/branding/canon_wf_logo_extended.png" in html
    assert "/assets/branding/canon_wf_logo_mark_transparent.png" in html
    assert "/assets/branding/favicon.ico" in html
    assert "/assets/branding/favicon-96x96.png" in html
    assert "/assets/branding/apple-touch-icon.png" in html
    assert "/assets/branding/site.webmanifest" in html
    assert "/assets/favicon-32x32.png" not in html
    assert "brand-logo" in css
    assert "context-mark" in css
    assert "Waveframe Ledger" in manifest
    assert "/assets/branding/web-app-manifest-192x192.png" in manifest
    assert "/assets/branding/web-app-manifest-512x512.png" in manifest
    assert "ui/assets/branding/canon_wf_logo_extended.png" in readme


def test_overview_uses_single_operational_status_surface():
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = STYLES_CSS.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")

    assert "workflow-state-banner" not in html
    assert "workflow-state-step" not in html
    assert "workflow-state-banner" not in css
    assert "Operational status rail" in html
    assert "context-lifecycle-state" in html
    assert "context-continuity-state" in html
    assert "context-replay-state" in html
    assert "setContextChip(\"#context-continuity-state\"" in source
    assert "setContextChip(\"#context-replay-state\"" in source
    assert "Pending Review" not in html
    assert "Incomplete" not in html
    assert "Unpublished" not in html
    assert "white-space: nowrap" in css
    assert "border-radius: 999px" in css
    assert "font-size: 2.2rem" in css
    assert "min-height: 29px" in css
    assert "min-height: 38px" in css
    assert "Attention Queue" in html
    assert "Pending governance actions" not in html
    assert "Authority state, lifecycle alerts" not in html
    assert "Execution governance" in html
    assert "Lifecycle" in html
    assert "Continuity" in html
    assert "Replay" in html
    assert "Registry" in html
    assert "No committed authority draft" not in html
    assert "Operational governance posture and continuity state." in html
    assert "Registry Inventory" in html
    assert 'id="operational-priority-bar"' in html
    assert "Primary blocker" in html
    assert 'id="priority-continuity"' in html
    assert 'id="priority-replay"' in html
    assert 'id="priority-publication"' in html
    assert "function renderOperationalPriorityBar" in source
    assert "primaryOperationalBlocker()" in source
    assert "continuityPriorityText" in source
    assert "replayPriorityText" in source
    assert "publicationPriorityText" in source
    assert ".operational-priority-bar" in css
    assert "dataset.queuePage = page" in source
    assert "showPage(page)" in source
    assert '"Operational impact review required", "Confirm governance consequences before activation.", "preview"' in source


def test_publication_surface_uses_activation_language():
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")

    assert "Activate Authority" in html
    assert "Move reviewed governance meaning into receipt-backed lifecycle continuity" in html
    assert "Create Publication Receipt" in html
    assert "Register Authority Posture" in html
    assert "Activation meaning" in html
    assert "Activation creates a replayable governance authority" in html
    assert "Bind reviewed authority meaning to replayable publication evidence." in source
    assert "Ledger created activation evidence. Register locally to record the authority lifecycle posture." in source


def test_ui_severity_semantics_are_documented():
    doc = (ROOT / "UI_SEVERITY_SEMANTICS.md").read_text(encoding="utf-8")

    for label in (
        "informational",
        "advisory",
        "pending",
        "review-required",
        "continuity-sensitive",
        "replay-sensitive",
        "blocking",
        "invalid",
        "revoked",
        "superseded",
    ):
        assert f"`{label}`" in doc

    assert "governance posture, not infrastructure telemetry" in doc
    assert "These labels do not represent Guard admissibility decisions" in doc


def test_create_authority_has_persistent_workflow_navigator():
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = STYLES_CSS.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    nav_body = _function_body(source, "renderAuthoringWorkflowNav")
    navigation_body = _function_body(source, "handleAuthoringWorkflowNavigation")
    sync_body = _function_body(source, "syncPublicationActions")

    assert 'id="authoring-workflow-nav"' in html
    for label in (
        "Draft",
        "Extraction",
        "Reconciliation",
        "Committed",
        "Compiled",
        "Impact Review",
        "Publication",
    ):
        assert f"<span>{label}</span>" in html

    assert 'data-workflow-jump="policy-source-text"' in html
    assert 'data-workflow-jump="extraction-review"' in html
    assert 'data-workflow-jump="reconciliation-workflow"' in html
    assert 'data-workflow-jump="compiled-contract-boundary"' in html
    assert 'data-workflow-page="preview"' in html
    assert 'data-workflow-page="publication"' in html
    assert ".authoring-workflow-nav" in css
    assert "position: sticky" in css
    assert "grid-template-columns: repeat(7, minmax(0, 1fr))" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "renderAuthoringWorkflowNav()" in sync_body
    assert "reconciliationWorkflowPosture()" in nav_body
    assert "canGenerateOperationalImpact()" in nav_body
    assert "canExportBundle()" in nav_body
    assert "showPage(button.dataset.workflowPage)" in navigation_body
    assert "scrollIntoView({ behavior: \"smooth\", block: \"center\" })" in navigation_body
    assert 'document.querySelector("#authoring-workflow-nav")?.addEventListener("click", handleAuthoringWorkflowNavigation)' in source


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
