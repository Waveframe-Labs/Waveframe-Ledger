const form = document.querySelector("#authority-form");
const generateButton = document.querySelector("#generate-button");
const publicationReviewButton = document.querySelector("#publication-review-button");
const exportButton = document.querySelector("#export-button");
const registerButton = document.querySelector("#register-button");
const newDraftButton = document.querySelector("#new-draft-button");
const saveDraftButton = document.querySelector("#save-draft-button");
const extractPolicyButton = document.querySelector("#extract-policy-button");
const useExtractionButton = document.querySelector("#use-extraction-button");
const compileAuthorityButton = document.querySelector("#compile-authority-button");
const applyAllExtractionButton = document.querySelector("#apply-all-extraction-button");
const openReconciliationButton = document.querySelector("#open-reconciliation-button");
const manualFirstButton = document.querySelector("#manual-first-button");
const populateCommittedDraftButton = document.querySelector("#populate-committed-draft-button");
const manualAuthorityDefinition = document.querySelector("#manual-authority-definition");
const policySourceText = document.querySelector("#policy-source-text");
const draftSessionStatus = document.querySelector("#draft-session-status");
let currentArtifacts = null;
let pendingRegistration = null;
let currentExtraction = null;
let currentReconciliation = null;
let interpretationDecisions = [];
let unresolvedReconciliationBlocks = [];
let interpretationAuditTrail = [];
let currentSemanticExtras = {};
let currentSemanticCommitBundle = null;
let currentCompiledAuthorityContract = null;
let currentSemanticAuthorityDiff = null;
let currentLifecycleEnforcementProjection = null;
let semanticDiffRequestToken = 0;
let committedDraft = null;
let authoringSessionDirty = false;
let policySourceDirty = false;
let livePreviewTimer = null;
let reviewBusy = false;
let workflowTimestamps = {
  draftSaved: null,
  reviewed: null,
  exported: null,
  registered: null,
};
let workflowState = {
  draftReady: false,
  impactReviewed: false,
  bundleExported: false,
  receiptGenerated: false,
  authorityRegistered: false,
};
let workflowInvalidation = {
  active: false,
  reason: null,
  updated_at: null,
  invalidated_projections: [],
};
let semanticStateMachine = {
  schema_version: "semantic_state_machine.v1",
  draft_state: "uncommitted",
  semantic_state: "not_ready",
  compiler_state: "not_compiled",
  impact_state: "not_reviewed",
  publication_state: "blocked",
  draft_hash: null,
  artifact_draft_hash: null,
  compiled_contract_hash: null,
  invalidation_reason: null,
};
const DRAFT_SESSION_KEY = "governance-ledger:draft-authority-session:v1";
const BUNDLE_REGISTRY_KEY = "governance-ledger:authority-bundle-registry:v1";

const $ = (selector) => document.querySelector(selector);

function readDraft() {
  const data = new FormData(form);
  return {
    protected_system: data.get("protected_system"),
    governed_action: data.get("governed_action"),
    contract_id: data.get("contract_id"),
    contract_version: data.get("contract_version"),
    governance_category: data.get("governance_category"),
    approver_role: data.get("approver_role"),
    approval_count: data.get("approval_count"),
    escalation_semantics: data.get("escalation_semantics"),
    validity_days: data.get("validity_days"),
    mutation_targets: data.get("mutation_targets"),
    continuity_revalidation: data.get("continuity_revalidation") === "on",
    revocation_invalidates_resume: data.get("revocation_invalidates_resume") === "on",
    ...currentSemanticExtras,
  };
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function stableHash(value) {
  const text = canonicalJson(value);
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `draft:${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function committedDraftHash() {
  return committedDraft ? stableHash(committedDraft) : null;
}

function resetCompiledAuthorityContract(reason = "not_compiled") {
  currentSemanticCommitBundle = null;
  currentCompiledAuthorityContract = null;
  setSemanticState({
    compiler_state: reason,
    compiled_contract_hash: null,
  });
}

function setSemanticState(partial) {
  semanticStateMachine = {
    ...semanticStateMachine,
    ...partial,
  };
}

function buildDraftSession(draft, options) {
  const sessionOptions = options || {};
  const previous = loadDraftSession();
  const now = new Date().toISOString();
  const committed = sessionOptions.commit ? draft : committedDraft || previous?.committed_draft || null;
  return {
    schema_version: "draft_authority_session.v1",
    session_id: previous?.session_id || `draft-${crypto.randomUUID()}`,
    created_at: previous?.created_at || now,
    updated_at: now,
    draft,
    committed_draft: committed,
    authoring_session_state: {
      dirty: sessionOptions.commit ? false : authoringSessionDirty,
      state: sessionOptions.commit ? "committed" : authoringSessionDirty ? "working_changes" : "restored",
      updated_at: now,
    },
  };
}

function loadDraftSession() {
  try {
    const raw = window.localStorage.getItem(DRAFT_SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw);
    if (session.schema_version !== "draft_authority_session.v1") return null;
    return session;
  } catch {
    return null;
  }
}

function saveDraftSession(options) {
  const sessionOptions = options || {};
  const session = buildDraftSession(readDraft(), sessionOptions);
  if (sessionOptions.commit) {
    committedDraft = structuredClone(session.draft);
    authoringSessionDirty = false;
    setSemanticState({
      draft_state: "committed",
      semantic_state: policySourceDirty ? "invalidated" : "manual_authoring_committed",
      impact_state: policySourceDirty ? "invalidated" : "not_reviewed",
      publication_state: "blocked",
      draft_hash: committedDraftHash(),
      artifact_draft_hash: null,
      invalidation_reason: policySourceDirty ? "policy_source_changed" : null,
    });
  }
  window.localStorage.setItem(DRAFT_SESSION_KEY, JSON.stringify(session));
  draftSessionStatus.textContent = sessionOptions.commit
    ? `draft_authority_session.v1 committed locally ${new Date(session.updated_at).toLocaleTimeString()}`
    : `Unsaved draft changes held in working session ${new Date(session.updated_at).toLocaleTimeString()}`;
  workflowTimestamps.draftSaved = session.updated_at;
  updateWorkflowState({ draftReady: Boolean(committedDraft) });
  return session;
}

function restoreDraftSession() {
  const session = loadDraftSession();
  if (!session) {
    committedDraft = null;
    authoringSessionDirty = false;
    policySourceDirty = false;
    currentExtraction = null;
    currentSemanticExtras = {};
    resetCompiledAuthorityContract();
    if (policySourceText) policySourceText.value = "";
    resetSemanticStateMachine("draft_not_committed");
    clearAuthoringFields();
    clearExtractionReview();
    clearOperationalImpact();
    clearPublicationReadiness();
    draftSessionStatus.textContent = "No committed authority draft. Start with policy text or manual authoring.";
    updateWorkflowState({ draftReady: false });
    return;
  }
  committedDraft = session.committed_draft || session.draft || null;
  authoringSessionDirty = Boolean(session.authoring_session_state?.dirty);
  setSemanticState({
    draft_state: authoringSessionDirty ? "dirty" : "committed",
    semantic_state: authoringSessionDirty ? "invalidated" : "manual_authoring_committed",
    impact_state: authoringSessionDirty ? "invalidated" : "not_reviewed",
    publication_state: "blocked",
    draft_hash: committedDraftHash(),
    artifact_draft_hash: null,
    invalidation_reason: authoringSessionDirty ? "working_authoring_changes" : "restored_committed_draft",
  });
  currentSemanticExtras = semanticExtrasFromCandidate(session.draft || {});
  resetCompiledAuthorityContract("not_compiled");
  clearAuthoringFields();
  draftSessionStatus.textContent = authoringSessionDirty
    ? `Working session state restored ${new Date(session.updated_at).toLocaleTimeString()}. Manual fields remain empty until explicitly populated.`
    : `Committed draft state restored ${new Date(session.updated_at).toLocaleTimeString()}. Manual fields remain empty until explicitly populated.`;
  updateWorkflowState({ draftReady: Boolean(committedDraft) });
}

function commitCurrentDraft() {
  return saveDraftSession({ commit: true });
}

function saveWorkingAuthoringSession() {
  authoringSessionDirty = true;
  invalidateSemanticLineage("draft_changed");
  return saveDraftSession({ commit: false });
}

function resetSemanticStateMachine(reason = "no_committed_draft") {
  currentSemanticCommitBundle = null;
  currentCompiledAuthorityContract = null;
  setSemanticState({
    draft_state: "uncommitted",
    semantic_state: "not_ready",
    compiler_state: "not_compiled",
    impact_state: "not_reviewed",
    publication_state: "blocked",
    draft_hash: null,
    artifact_draft_hash: null,
    compiled_contract_hash: null,
    invalidation_reason: reason,
  });
}

function clearAuthoringFields() {
  for (const field of Array.from(form.elements)) {
    if (!field.name) continue;
    if (field.type === "checkbox") {
      field.checked = false;
    } else if (field.tagName === "SELECT") {
      field.selectedIndex = 0;
    } else {
      field.value = "";
    }
    setFieldProvenance(field.name, "Manual");
  }
  closeManualAuthorityDefinition();
}

function setFieldProvenance(fieldName, provenance) {
  const chip = document.querySelector(`[data-provenance-for="${fieldName}"]`);
  if (!chip) return;
  chip.textContent = provenance;
  chip.dataset.provenance = provenance.toLowerCase().replaceAll(" ", "-");
}

function markManualFieldProvenance(event) {
  const field = event.target;
  if (field?.name) setFieldProvenance(field.name, "Manual");
}

function clearExtractionReview() {
  currentExtraction = null;
  resetReconciliationState();
  currentSemanticExtras = {};
  renderCapabilities("#extracted-capabilities", []);
  renderDefinitionValues("#extracted-authority", {
    "Candidate status": "No candidate semantics extracted",
    "Commit status": "No committed authority draft",
  });
  renderExtractionList("#extracted-rules", [], "No candidate obligations extracted.");
  renderExtractionList("#extracted-ambiguities", [], "No extraction ambiguities recorded.");
  renderExtractionList("#extracted-missing", [], "No interpretation boundaries recorded.");
  renderProvenanceList("#semantic-provenance", []);
  renderReconciliationWorkflow("#reconciliation-workflow", []);
  $("#extraction-status").textContent = "Extraction has not run yet. Operator confirmation is required before an authority draft changes.";
}

function resetReconciliationState() {
  currentReconciliation = null;
  interpretationDecisions = [];
  unresolvedReconciliationBlocks = [];
  interpretationAuditTrail = [];
}

function clearOperationalImpact() {
  currentSemanticAuthorityDiff = null;
  currentLifecycleEnforcementProjection = null;
  $("#preview-summary").textContent = "No committed semantic interpretation yet. Commit semantics before generating operational impact.";
  renderList("#preview-enforcement", []);
  renderList("#preview-consequences", []);
  renderList("#preview-lifecycle", []);
  renderList("#outcome-explorer", []);
  renderOutcomes([]);
  renderExecutionContext("#change-execution-context", null);
  renderChangeReview(null);
  renderPublicationProjection(null);
  $("#bundle-meaning").textContent = "No bundle generated yet.";
  renderList("#publication-consequences", []);
  $("#manifest-json").textContent = "No publication manifest generated yet.";
  $("#bundle-json").textContent = "No authority bundle generated yet.";
  $("#receipt-json").textContent = "No publication receipt generated yet.";
}

function clearPublicationReadiness() {
  for (const field of document.querySelectorAll(".readiness-list input[type='checkbox']")) {
    field.checked = false;
  }
  for (const field of document.querySelectorAll(".notes-panel textarea")) {
    field.value = "";
  }
}

function startNewDraft() {
  window.localStorage.removeItem(DRAFT_SESSION_KEY);
  currentArtifacts = null;
  pendingRegistration = null;
  currentExtraction = null;
  currentSemanticAuthorityDiff = null;
  currentLifecycleEnforcementProjection = null;
  currentSemanticExtras = {};
  resetCompiledAuthorityContract();
  committedDraft = null;
  authoringSessionDirty = false;
  policySourceDirty = false;
  workflowTimestamps = {
    draftSaved: null,
    reviewed: null,
    exported: null,
    registered: null,
  };
  if (policySourceText) policySourceText.value = "";
  clearAuthoringFields();
  resetSemanticStateMachine();
  clearExtractionReview();
  clearOperationalImpact();
  clearPublicationReadiness();
  exportButton.disabled = true;
  registerButton.disabled = true;
  useExtractionButton.disabled = true;
  if (applyAllExtractionButton) applyAllExtractionButton.disabled = true;
  openReconciliationButton.disabled = true;
  $("#status-authority-ref").textContent = "not generated";
  $("#status-semantic").textContent = "draft required";
  $("#status-bundle").textContent = "not exported";
  $("#release-registration").textContent = "Bundle not exported.";
  clearWorkflowInvalidation();
  updateWorkflowState({
    draftReady: false,
    impactReviewed: false,
    bundleExported: false,
    receiptGenerated: false,
    authorityRegistered: false,
  });
  draftSessionStatus.textContent = "No committed authority draft. Start with policy text or manual authoring.";
  renderAuthorityContext();
  renderOperationsOverview();
  renderBundleRegistry();
  syncPublicationActions();
  showPage("draft");
}

async function extractPolicySemantics() {
  const sourceText = policySourceText?.value || "";
  extractPolicyButton.disabled = true;
  extractPolicyButton.textContent = "Extracting Meaning...";
  try {
    const response = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_text: sourceText }),
    });
    const extraction = await response.json();
    if (!response.ok) {
      throw new Error(extraction.error || "Unable to extract governance meaning.");
    }
    currentExtraction = extraction;
    resetReconciliationState();
    resetCompiledAuthorityContract("semantic_extraction_provisional");
    policySourceDirty = false;
    setSemanticState({
      draft_state: committedDraft ? "committed" : "uncommitted",
      semantic_state: "extracted_requires_confirmation",
      compiler_state: "not_compiled",
      impact_state: "invalidated",
      publication_state: "blocked",
      draft_hash: committedDraftHash(),
      artifact_draft_hash: null,
      compiled_contract_hash: null,
      invalidation_reason: "extraction_requires_operator_confirmation",
    });
    renderSemanticExtraction(extraction);
    pendingRegistration = null;
    exportButton.disabled = true;
    registerButton.disabled = true;
    workflowTimestamps.reviewed = null;
    workflowTimestamps.exported = null;
    workflowTimestamps.registered = null;
    updateWorkflowState({
      draftReady: workflowState.draftReady,
      impactReviewed: false,
      bundleExported: false,
      receiptGenerated: false,
      authorityRegistered: false,
    });
  } catch (error) {
    renderDiagnostics([{ severity: "error", code: "policy_extraction_error", text: error.message }]);
  } finally {
    extractPolicyButton.textContent = "Extract Governance Meaning";
    syncPublicationActions();
  }
}

function renderSemanticExtraction(extraction) {
  const candidate = extraction?.candidate_authority || {};
  const temporal = candidate.temporal_semantics || {};
  const snapshot = candidate.state_snapshot_semantics || {};
  const executionContext = candidate.execution_context_semantics || {};
  const actor = candidate.governance_actor || {};
  const approvalChain = candidate.approval_chain_semantics || {};
  renderCapabilities("#extracted-capabilities", extraction.candidate_capabilities || candidate.capabilities || []);
  renderDefinitionValues("#extracted-authority", {
    Resource: candidate.protected_system || "Not explicitly defined",
    Action: candidate.governed_action || "Not explicitly defined",
    "Governed targets": summarizeArray(candidate.governed_targets || candidate.governed_action_targets),
    "Governed operations": summarizeArray(candidate.governed_operations),
    "Mutation classes": summarizeArray(candidate.mutation_classes),
    "Approval role": candidate.approver_role || "Not explicitly defined",
    "Approval count": candidate.approval_count ?? "Not explicitly defined",
    "Escalation threshold": candidate.escalation_threshold ? `$${Number(candidate.escalation_threshold).toLocaleString()}` : "Not explicitly defined",
    Continuity: candidate.continuity_revalidation || candidate.revocation_invalidates_resume ? "continuity semantics detected" : "Not explicitly defined",
    "Validity window": temporal.validity_window || (candidate.validity_days ? `P${candidate.validity_days}D` : "Not explicitly defined"),
    "Timestamp source": temporal.timestamp_source || "Not explicitly defined",
    "Snapshot expectation": snapshot.snapshot_required ? "required for resumed workflows" : "Not explicitly defined",
    "Execution context": executionContext.execution_context ? formatLabel(executionContext.execution_context) : "Not explicitly defined",
    "Execution boundary": executionContext.execution_boundary ? formatLabel(executionContext.execution_boundary) : "Not explicitly defined",
    "Responsible actor": actor.actor_id || "Not explicitly defined",
    "Approval independence": approvalChain.independence_required ? "required" : "not specified",
    "Actor attestation": approvalChain.attestation_required ? "required" : "not specified",
  });
  renderExtractionList("#extracted-rules", extraction.candidate_rules, "No deterministic obligations extracted.");
  renderExtractionList("#extracted-ambiguities", extraction.ambiguities, "No ambiguity detected by deterministic patterns.");
  renderExtractionList("#extracted-missing", extraction.missing_information, "No undefined anchor fields detected.");
  renderProvenanceList("#semantic-provenance", extraction.semantic_provenance);
  renderReconciliationWorkflow("#reconciliation-workflow", extraction.ambiguities);
  if (extraction.missing_information?.length) {
    openManualAuthorityDefinition();
  }
  $("#extraction-status").textContent = `${extraction.schema_version} requires operator confirmation. Source hash ${shortHash(extraction.source_hash)}.`;
}

function renderCapabilities(selector, capabilities) {
  const node = $(selector);
  if (!node) return;
  node.innerHTML = "";
  const list = capabilities?.length ? capabilities : [];
  if (!list.length) {
    const empty = document.createElement("p");
    empty.className = "quiet";
    empty.textContent = "No operational capabilities were deterministically extracted.";
    node.appendChild(empty);
    return;
  }
  for (const capability of list) {
    const article = document.createElement("details");
    article.className = "capability-card";
    article.open = list.length === 1;
    const summary = document.createElement("summary");
    const heading = document.createElement("h5");
    heading.textContent = formatLabel(capability.action || capability.capability_id);
    const type = document.createElement("span");
    type.className = "capability-type";
    type.textContent = formatLabel(capability.action_type);
    summary.append(heading, type);
    const impact = document.createElement("p");
    impact.className = "capability-impact";
    impact.textContent = capabilityImpactSummary(capability);
    const relationships = capabilityRelationshipStrip(capability);
    const groups = document.createElement("div");
    groups.className = "capability-requirement-grid";
    for (const [label, values] of Object.entries(capabilityRequirementGroups(capability))) {
      groups.appendChild(capabilityRequirementGroup(label, values));
    }
    const bullets = document.createElement("ul");
    bullets.className = "capability-bullets";
    for (const summary of capabilitySummaries(capability)) {
      const item = document.createElement("li");
      item.textContent = summary;
      bullets.appendChild(item);
    }
    article.append(summary, impact, relationships, groups, bullets);
    node.appendChild(article);
  }
}

function capabilityImpactSummary(capability) {
  const action = formatLabel(capability.action || capability.capability_id || "Capability");
  const requirementCount = (capability.requirements || []).length
    + (capability.evidence_requirements || []).length
    + (capability.continuity_semantics ? 1 : 0)
    + (capability.identity_requirements ? 1 : 0);
  return `${action} is a provisional governed capability with ${requirementCount || "no explicit"} extracted requirement${requirementCount === 1 ? "" : "s"}.`;
}

function capabilityRelationshipStrip(capability) {
  const strip = document.createElement("div");
  strip.className = "capability-relationship-strip";
  const continuity = capability.continuity_semantics || {};
  const execution = capability.execution_constraints || {};
  const identity = capability.identity_requirements?.approval_chain_semantics || {};
  const evidence = capability.evidence_requirements || [];
  const relationships = {
    Continuity: continuity.revalidation_required || continuity.revocation_invalidates_resume ? "controls active" : "not specified",
    Replay: evidence.length ? `${evidence.length} evidence requirement${evidence.length === 1 ? "" : "s"}` : "not specified",
    Identity: identity.independence_required || identity.self_approval_prohibited ? "approval boundary" : "not specified",
    Execution: execution.execution_context || execution.execution_boundary || "authority default",
  };
  for (const [label, value] of Object.entries(relationships)) {
    const item = document.createElement("div");
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = String(value);
    item.append(span, strong);
    strip.appendChild(item);
  }
  return strip;
}

function capabilityRequirementGroups(capability) {
  const continuity = capability.continuity_semantics || {};
  const snapshot = continuity.state_snapshot_semantics || {};
  const execution = capability.execution_constraints || {};
  const identity = capability.identity_requirements?.approval_chain_semantics || {};
  return {
    "This capability requires": (capability.requirements || []).map((item) => item.summary || item.requirement_type).filter(Boolean),
    "Evidence obligations": (capability.evidence_requirements || []).map((item) => item.summary || item.evidence_type).filter(Boolean),
    "Continuity controls": [
      continuity.revalidation_required ? "Continuity validation before resumed execution." : "",
      continuity.revocation_invalidates_resume ? "Revoked authority invalidates resumed execution." : "",
      snapshot.snapshot_required ? "Snapshot hash comparison against active governance posture." : "",
    ].filter(Boolean),
    "Execution and identity": [
      execution.execution_context ? `Execution context: ${formatLabel(execution.execution_context)}.` : "",
      execution.execution_boundary ? `Execution boundary: ${formatLabel(execution.execution_boundary)}.` : "",
      identity.independence_required ? "Independent approval responsibilities required." : "",
      identity.self_approval_prohibited ? "Self approval prohibited." : "",
      identity.ai_recommendation_posture === "advisory_only" ? "AI recommendation boundary is advisory only." : "",
    ].filter(Boolean),
  };
}

function capabilityRequirementGroup(label, values) {
  const group = document.createElement("section");
  group.className = "capability-requirement-group";
  const heading = document.createElement("strong");
  heading.textContent = label;
  const list = document.createElement("ul");
  const items = values.length ? values : ["Not explicitly defined by deterministic extraction."];
  for (const value of items) {
    const item = document.createElement("li");
    item.textContent = value;
    list.appendChild(item);
  }
  group.append(heading, list);
  return group;
}

function capabilitySummaries(capability) {
  const summaries = [];
  for (const requirement of capability.requirements || []) {
    if (requirement.summary) summaries.push(requirement.summary);
  }
  const continuity = capability.continuity_semantics || {};
  if (continuity.revalidation_required) summaries.push("Requires continuity validation before resumed execution.");
  if (continuity.revocation_invalidates_resume) summaries.push("Revoked authority invalidates resumed execution.");
  const snapshot = continuity.state_snapshot_semantics || {};
  if (snapshot.snapshot_required) summaries.push("Requires snapshot hash comparison against active governance posture.");
  for (const evidence of capability.evidence_requirements || []) {
    if (evidence.summary) summaries.push(evidence.summary);
  }
  const identity = capability.identity_requirements?.approval_chain_semantics || {};
  if (identity.independence_required) summaries.push("Requires independent approval responsibilities.");
  if (identity.self_approval_prohibited) summaries.push("Self approval is prohibited.");
  if (identity.ai_recommendation_posture === "advisory_only") summaries.push("AI recommendations are advisory only.");
  return [...new Set(summaries)].slice(0, 7);
}

function renderReconciliationWorkflow(selector, ambiguities) {
  const node = $(selector);
  if (!node) return;
  node.innerHTML = "";
  const list = ambiguities?.filter((item) => item.requires_operator_resolution !== false) || [];
  if (!list.length) {
    const empty = document.createElement("p");
    empty.className = "quiet";
    empty.textContent = "No operator resolution workflow is required for the current extraction.";
    node.appendChild(empty);
    return;
  }
  for (const [index, ambiguity] of list.entries()) {
    const normalized = semanticAmbiguity(ambiguity, index + 1);
    const tier = ambiguityTier(normalized);
    const existingDecision = interpretationDecisions.find((decision) => decision.ambiguity_id === normalized.ambiguity_id);
    const existingBlock = unresolvedReconciliationBlocks.find((block) => block.ambiguity_id === normalized.ambiguity_id);
    const item = document.createElement("div");
    item.className = "resolution-item";
    item.dataset.ambiguityId = normalized.ambiguity_id;
    const title = document.createElement("strong");
    title.textContent = formatLabel(normalized.ambiguity_type);
    const severity = document.createElement("span");
    severity.className = `ambiguity-severity ${tier}`;
    severity.textContent = formatLabel(tier);
    const summary = document.createElement("p");
    summary.textContent = reconciliationTierSummary(tier, normalized.summary || "Operator interpretation is required.");
    const comparison = interpretationComparisonPanel(ambiguity, existingDecision);
    const choices = document.createElement("div");
    choices.className = "resolution-choices";
    for (const choice of resolutionChoicesForAmbiguity(ambiguity)) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.resolutionChoice = choice;
      button.className = choice === existingDecision?.selected_interpretation ? "selected" : "";
      button.textContent = choice;
      choices.appendChild(button);
    }
    const rationale = document.createElement("textarea");
    rationale.rows = 2;
    rationale.dataset.resolutionRationale = normalized.ambiguity_id;
    rationale.placeholder = tier === "informational" ? "Optional rationale" : "Operator rationale for this interpretation";
    rationale.value = existingDecision?.justification || existingBlock?.rationale || "";
    let attestation = null;
    if (tier === "high-impact") {
      attestation = document.createElement("label");
      attestation.className = "resolution-attestation";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.dataset.resolutionAttestation = normalized.ambiguity_id;
      const span = document.createElement("span");
      span.textContent = "I attest this interpretation changes operational governance meaning.";
      attestation.append(checkbox, span);
    }
    const actions = document.createElement("div");
    actions.className = "resolution-actions";
    const save = document.createElement("button");
    save.type = "button";
    save.className = "tertiary-action";
    save.dataset.saveResolution = normalized.ambiguity_id;
    save.textContent = tier === "informational" ? "Quick acknowledge" : "Save interpretation decision";
    const unresolved = document.createElement("button");
    unresolved.type = "button";
    unresolved.className = "tertiary-action";
    unresolved.dataset.markUnresolved = normalized.ambiguity_id;
    unresolved.textContent = "Mark unresolved blocker";
    actions.append(save, unresolved);
    const status = document.createElement("p");
    status.className = "resolution-status";
    status.textContent = existingDecision
      ? `Resolved by ${existingDecision.operator}: ${existingDecision.selected_interpretation}`
      : existingBlock
        ? `Unresolved blocker: ${existingBlock.rationale || existingBlock.selected_interpretation}`
        : "Decision required before semantic commitment.";
    const history = decisionRevisionHistory(normalized.ambiguity_id);
    if (tier === "blocking") {
      save.disabled = true;
      status.textContent = "Blocking ambiguity. Resolve policy language before semantic commitment.";
    }
    item.append(title, severity, summary, comparison, choices, rationale);
    if (attestation) item.appendChild(attestation);
    item.append(actions, status, history);
    node.appendChild(item);
  }
  const divergence = reconciliationDivergencePanel();
  node.appendChild(divergence);
  const audit = document.createElement("div");
  audit.id = "reconciliation-audit-trail";
  audit.className = "reconciliation-audit-trail";
  const auditTitle = document.createElement("strong");
  auditTitle.textContent = "Interpretation audit trail";
  const auditList = document.createElement("ul");
  const entries = interpretationAuditTrail.length
    ? interpretationAuditTrail
    : [{ action: "awaiting_operator_decisions", summary: "No interpretation decisions recorded yet." }];
  for (const entry of entries) {
    const line = document.createElement("li");
    line.textContent = entry.summary || formatLabel(entry.action);
    auditList.appendChild(line);
  }
  audit.append(auditTitle, auditList);
  node.appendChild(audit);
}

function ambiguityTier(ambiguity) {
  const type = ambiguity.ambiguity_type || "";
  if (["contradictory_approval_semantics", "mutually_exclusive_lifecycle_behavior", "unresolved_governed_action"].includes(type)) return "blocking";
  if (["approval_independence_ambiguity", "undefined_threshold", "scope_expansion_ambiguity", "replay_invalidation_ambiguity"].includes(type)) return "high-impact";
  return "informational";
}

function ambiguitySeverity(ambiguity) {
  return ambiguityTier(ambiguity);
}

function reconciliationTierSummary(tier, summary) {
  if (tier === "informational") return `${summary} Quick acknowledgement is allowed; rationale is optional.`;
  if (tier === "high-impact") return `${summary} Explicit interpretation, rationale, and operator attestation are required.`;
  return `${summary} This blocks semantic commitment until the source policy or governed action is clarified.`;
}

function interpretationComparisonPanel(ambiguity, existingDecision) {
  const panel = document.createElement("div");
  panel.className = "interpretation-comparison";
  const heading = document.createElement("strong");
  heading.textContent = "Interpretation options";
  const list = document.createElement("ul");
  for (const choice of resolutionChoicesForAmbiguity(ambiguity)) {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = choice;
    const meaning = document.createElement("small");
    meaning.textContent = interpretationOptionMeaning(ambiguity, choice);
    item.classList.toggle("selected", choice === existingDecision?.selected_interpretation);
    item.append(label, meaning);
    list.appendChild(item);
  }
  panel.append(heading, list);
  return panel;
}

function interpretationOptionMeaning(ambiguity, choice) {
  const type = ambiguity.ambiguity_type || ambiguity.type || "";
  if (/unresolved|block publication/i.test(choice)) return "Keeps semantic commitment blocked until an operator resolves the ambiguity.";
  if (type === "timestamp_source_unspecified") return "Runtime replay evidence may bind against orchestration or signed authority timestamps.";
  if (type === "state_snapshot_subject_unspecified") return "Paused workflows remain resumable only when the selected governance snapshot still matches.";
  if (type === "approval_independence_ambiguity") return "Execution becomes admissible only when approval evidence satisfies the selected independence boundary.";
  if (type === "undefined_threshold") return "Executions crossing the selected threshold enter escalation review before publication meaning is trusted.";
  if (type === "scope_expansion_ambiguity") return "Additional governed targets become part of the authority surface and require continuity review.";
  if (type === "replay_invalidation_ambiguity") return "Existing replay evidence may need revalidation before resumed workflows continue.";
  return "The selected interpretation becomes deterministic governance meaning after semantic commitment.";
}

function decisionRevisionHistory(ambiguityId) {
  const panel = document.createElement("div");
  panel.className = "decision-revision-history";
  const title = document.createElement("strong");
  title.textContent = "Decision revision history";
  const list = document.createElement("ul");
  const entries = interpretationAuditTrail.filter((entry) => entry.details?.ambiguity_id === ambiguityId);
  const values = entries.length ? entries : [{ summary: "No decision revisions recorded for this ambiguity." }];
  for (const entry of values) {
    const item = document.createElement("li");
    item.textContent = entry.summary || formatLabel(entry.action);
    list.appendChild(item);
  }
  panel.append(title, list);
  return panel;
}

function reconciliationDivergencePanel() {
  const panel = document.createElement("div");
  panel.className = "semantic-divergence-panel";
  const title = document.createElement("strong");
  title.textContent = "Semantic divergence check";
  const text = document.createElement("p");
  const resolved = interpretationDecisions.length;
  const unresolved = unresolvedReconciliationBlocks.length;
  text.textContent = resolved || unresolved
    ? `${resolved} operator interpretation${resolved === 1 ? "" : "s"} and ${unresolved} unresolved blocker${unresolved === 1 ? "" : "s"} are recorded for this extraction.`
    : "No operator interpretation drift is present because no decisions have been recorded yet.";
  panel.append(title, text);
  return panel;
}

function resolutionChoicesForAmbiguity(ambiguity) {
  const type = ambiguity.ambiguity_type || ambiguity.type || "";
  if (type === "timestamp_source_unspecified") {
    return ["Block publication", "Assume orchestrator timestamp", "Require signed authority timestamp", "Mark unresolved ambiguity"];
  }
  if (type === "state_snapshot_subject_unspecified") {
    return ["Require active governance state snapshot", "Require current policy version snapshot", "Mark unresolved ambiguity"];
  }
  if (type === "approval_independence_ambiguity") {
    return ["Require independent actors", "Define reviewer roles", "Mark unresolved ambiguity"];
  }
  return ["Resolve interpretation", "Reject candidate meaning", "Mark unresolved ambiguity"];
}

function semanticAmbiguity(item, index = 1) {
  return {
    schema_version: "semantic_ambiguity.v1",
    ambiguity_id: item.ambiguity_id || `ambiguity-${String(index).padStart(3, "0")}`,
    ambiguity_type: item.ambiguity_type || item.type || "semantic_ambiguity",
    text: item.text || item.summary || "",
    summary: item.summary || item.text || "",
    requires_operator_resolution: item.requires_operator_resolution !== false,
  };
}

function requiredSemanticAmbiguities() {
  return (currentExtraction?.ambiguities || [])
    .map((item, index) => semanticAmbiguity(item, index + 1))
    .filter((item) => item.requires_operator_resolution);
}

function blockingSemanticAmbiguities() {
  return requiredSemanticAmbiguities().filter((ambiguity) => ambiguityTier(ambiguity) === "blocking");
}

function decisionTypeForAmbiguity(ambiguity) {
  const type = ambiguity.ambiguity_type || ambiguity.type || "";
  if (type === "timestamp_source_unspecified") return "timestamp_source_definition";
  if (type === "state_snapshot_subject_unspecified") return "state_snapshot_subject_definition";
  if (type === "undefined_threshold") return "threshold_definition";
  return "operator_semantic_interpretation";
}

function fieldForDecisionType(decisionType) {
  return {
    threshold_definition: "escalation_threshold",
    timestamp_source_definition: "timestamp_source",
    state_snapshot_subject_definition: "state_snapshot_subject",
  }[decisionType] || decisionType;
}

function resolvedValueForChoice(ambiguity, choice) {
  const decisionType = decisionTypeForAmbiguity(ambiguity);
  if (decisionType === "timestamp_source_definition") {
    if (choice === "Assume orchestrator timestamp") return "execution_payload";
    if (choice === "Require signed authority timestamp") return "signed_oracle";
  }
  if (decisionType === "state_snapshot_subject_definition") {
    if (choice === "Require active governance state snapshot") return "active_governance_state";
    if (choice === "Require current policy version snapshot") return "current_policy_version";
  }
  if (decisionType === "threshold_definition") {
    const match = String(choice).match(/\d[\d,]*/);
    return match ? Number(match[0].replaceAll(",", "")) : choice;
  }
  return choice;
}

function isUnresolvedChoice(choice) {
  return /unresolved|block publication/i.test(String(choice || ""));
}

function buildInterpretationDecision(ambiguity, choice, rationale) {
  const decisionType = decisionTypeForAmbiguity(ambiguity);
  const resolvedValue = resolvedValueForChoice(ambiguity, choice);
  const field = fieldForDecisionType(decisionType);
  const rejected = resolutionChoicesForAmbiguity(ambiguity).filter((candidate) => candidate !== choice);
  const stablePayload = {
    decision_type: decisionType,
    field,
    selected_interpretation: choice,
    rejected_interpretations: rejected,
    operator: "local-ledger-ui",
    justification: rationale,
  };
  const hash = stableHash(stablePayload).replace("sha256:", "");
  return {
    schema_version: "semantic_interpretation_decision.v1",
    decision_id: `decision-${hash.slice(0, 12)}`,
    field,
    selected_interpretation: choice,
    rejected_interpretations: rejected,
    decision_type: decisionType,
    ambiguity_id: ambiguity.ambiguity_id,
    resolved_value: resolvedValue,
    rationale,
    operator: "local-ledger-ui",
    timestamp: stableDecisionTimestamp(hash),
    justification: rationale,
    decision_posture: "operator_reviewed",
  };
}

function stableDecisionTimestamp(hash) {
  const seconds = parseInt(hash.slice(0, 8), 16) % 60;
  return `2026-01-01T00:00:${String(seconds).padStart(2, "0")}Z`;
}

function recordInterpretationAudit(action, summary, details = {}) {
  const payload = { action, summary, details };
  const hash = stableHash(payload).replace("sha256:", "");
  interpretationAuditTrail.push({
    schema_version: "semantic_interpretation_audit_event.v1",
    event_id: `interpretation-audit-${hash.slice(0, 12)}`,
    action,
    summary,
    details,
    timestamp: stableDecisionTimestamp(hash),
  });
}

function buildGovernanceSemanticReconciliation() {
  if (!currentExtraction) return null;
  const ambiguities = requiredSemanticAmbiguities();
  const blockingIds = new Set(blockingSemanticAmbiguities().map((ambiguity) => ambiguity.ambiguity_id));
  const resolvedIds = new Set(interpretationDecisions.map((decision) => decision.ambiguity_id));
  const blockedIds = new Set(unresolvedReconciliationBlocks.map((block) => block.ambiguity_id));
  const unresolved = ambiguities.filter((ambiguity) => blockingIds.has(ambiguity.ambiguity_id) || !resolvedIds.has(ambiguity.ambiguity_id) || blockedIds.has(ambiguity.ambiguity_id));
  const normalized = unresolved.length ? {} : normalizedAuthorityFromDecisions(currentExtraction.candidate_authority || {});
  return {
    schema_version: "governance_semantic_reconciliation.v1",
    source_id: currentExtraction.source_id,
    source_hash: currentExtraction.source_hash,
    extraction_id: `extraction-${String(currentExtraction.source_hash || "").replace("sha256:", "").slice(0, 12)}`,
    what_was_inferred: currentExtraction.candidate_rules || [],
    ambiguities,
    operator_interpretation_decisions: interpretationDecisions,
    normalization_decisions: normalizationDecisions(),
    rejected_candidates: unresolvedReconciliationBlocks,
    semantic_conflicts: [],
    unresolved_ambiguities: unresolved,
    final_normalized_semantic_meaning: normalized,
    interpretation_completeness_posture: blockingIds.size ? "blocked" : unresolved.length ? "operator_required" : "complete",
    interpretation_audit_trail: interpretationAuditTrail,
  };
}

function normalizedAuthorityFromDecisions(candidate) {
  const normalized = structuredClone(candidate || {});
  for (const decision of interpretationDecisions) {
    if (decision.decision_type === "threshold_definition") {
      normalized.escalation_threshold = decision.resolved_value;
      normalized.escalation_semantics = `Executions above $${Number(decision.resolved_value).toLocaleString()} require escalation review.`;
    }
    if (decision.decision_type === "timestamp_source_definition") {
      const temporal = { ...(normalized.temporal_semantics || {}) };
      temporal.schema_version = "temporal_authority_semantics.v1";
      temporal.timestamp_source = decision.resolved_value;
      temporal.runtime_enforced_by = "Guard/Cloud";
      normalized.temporal_semantics = temporal;
    }
    if (decision.decision_type === "state_snapshot_subject_definition") {
      const snapshot = { ...(normalized.state_snapshot_semantics || {}) };
      snapshot.schema_version = "state_posture_snapshot_semantics.v1";
      snapshot.snapshot_required = true;
      snapshot.snapshot_hash_algorithm = "sha256";
      snapshot.snapshot_subject = decision.resolved_value;
      snapshot.resume_comparison = "snapshot_hash_must_match_active_state_hash";
      snapshot.drift_result = "continuity_drift_detected";
      snapshot.runtime_enforced_by = "Guard/Cloud";
      normalized.state_snapshot_semantics = snapshot;
    }
  }
  return normalized;
}

function normalizationDecisions() {
  const labels = [];
  for (const decision of interpretationDecisions) {
    if (decision.decision_type === "threshold_definition") labels.push("threshold normalized from operator interpretation");
    if (decision.decision_type === "timestamp_source_definition") labels.push("timestamp source normalized from operator interpretation");
    if (decision.decision_type === "state_snapshot_subject_definition") labels.push("state snapshot subject normalized from operator interpretation");
  }
  return [...new Set(labels)];
}

function updateReconciliationState() {
  currentReconciliation = buildGovernanceSemanticReconciliation();
  syncPublicationActions();
}

function reconciliationIsComplete() {
  if (!currentExtraction) return false;
  const reconciliation = currentReconciliation || buildGovernanceSemanticReconciliation();
  return reconciliation?.interpretation_completeness_posture === "complete";
}

function summarizeArray(values) {
  const list = (values || []).filter(Boolean).map((item) => formatLabel(item));
  return list.length ? list.join(", ") : "Not explicitly defined";
}

function renderExtractionList(selector, items, emptyText) {
  const node = $(selector);
  if (!node) return;
  node.innerHTML = "";
  const list = items?.length ? items : [{ summary: emptyText }];
  for (const item of list) {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = item.rule_type ? formatLabel(item.rule_type) : item.ambiguity_type ? formatLabel(item.ambiguity_type) : item.field ? formatLabel(item.field) : "Extraction status";
    const span = document.createElement("span");
    span.textContent = item.summary;
    li.append(strong, span);
    node.appendChild(li);
  }
}

function renderProvenanceList(selector, items) {
  const node = $(selector);
  if (!node) return;
  node.innerHTML = "";
  const list = items?.length ? items : [{ field: "provenance", confidence: "low", source_spans: [], value: "No deterministic source support recorded." }];
  for (const item of list) {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = `${formatLabel(item.field)} - ${formatLabel(item.confidence || "low")} confidence`;
    const span = document.createElement("span");
    const sourceText = item.source_spans?.[0]?.text ? `Source: "${item.source_spans[0].text}"` : "No direct source span recorded.";
    span.textContent = sourceText;
    li.append(strong, span);
    node.appendChild(li);
  }
}

function commitSemanticInterpretation() {
  currentReconciliation = currentReconciliation || buildGovernanceSemanticReconciliation();
  if (!currentExtraction?.candidate_authority || !reconciliationIsComplete()) {
    openReconciliationReview();
    $("#extraction-status").textContent = "Resolve or explicitly clear all reconciliation blockers before committing semantic interpretation.";
    return;
  }
  recordInterpretationAudit("semantic_interpretation_committed", "Semantic interpretation committed as deterministic draft meaning.");
  currentReconciliation = buildGovernanceSemanticReconciliation();
  const normalizedMeaning = currentReconciliation.final_normalized_semantic_meaning || currentExtraction.candidate_authority;
  applyDraftToForm(normalizedMeaning, "Committed");
  currentSemanticExtras = {
    ...semanticExtrasFromCandidate(normalizedMeaning),
    governance_semantic_reconciliation: currentReconciliation,
    semantic_reconciliation_projection: {
      schema_version: "semantic_reconciliation_projection.v1",
      source_id: currentReconciliation.source_id,
      unresolved_ambiguities: currentReconciliation.unresolved_ambiguities,
      operator_reviewed_interpretations: currentReconciliation.operator_interpretation_decisions,
      conflicting_extracted_semantics: currentReconciliation.semantic_conflicts,
      normalization_decisions: currentReconciliation.normalization_decisions,
      interpretation_completeness_posture: currentReconciliation.interpretation_completeness_posture,
    },
  };
  currentArtifacts = null;
  pendingRegistration = null;
  resetCompiledAuthorityContract("semantic_commit_requires_compilation");
  policySourceDirty = false;
  commitCurrentDraft();
  setSemanticState({
    draft_state: "committed",
    semantic_state: "committed",
    compiler_state: "not_compiled",
    impact_state: "invalidated",
    publication_state: "blocked",
    draft_hash: committedDraftHash(),
    artifact_draft_hash: null,
    compiled_contract_hash: null,
    invalidation_reason: "semantic_interpretation_committed_requires_impact_review",
  });
  workflowInvalidation = {
    active: true,
    reason: "semantic_interpretation_committed_requires_impact_review",
    updated_at: new Date().toISOString(),
    invalidated_projections: [
      "governance_impact_preview.v1",
      "authority_diff_impact.v1",
      "semantic_authority_diff.v1",
      "authority_workspace_projection.v1",
      "authority_operational_summary.v1",
      "publication_readiness",
    ],
  };
  workflowTimestamps.reviewed = null;
  workflowTimestamps.exported = null;
  workflowTimestamps.registered = null;
  exportButton.disabled = true;
  registerButton.disabled = true;
  updateWorkflowState({
    draftReady: true,
    impactReviewed: false,
    bundleExported: false,
    receiptGenerated: false,
    authorityRegistered: false,
  });
  $("#extraction-status").textContent = `Semantic interpretation committed. Fingerprint ${shortHash(committedDraftHash() || "draft:unavailable")}. Compile Authority Contract next.`;
  renderReconciliationWorkflow("#reconciliation-workflow", currentExtraction.ambiguities);
  renderOperatorGuidance(
    "Semantic interpretation committed.",
    "Compile the deterministic authority contract before operational impact review.",
  );
}

function openReconciliationReview() {
  if (!currentExtraction) return;
  const ambiguityCount = currentExtraction.ambiguities?.length || 0;
  const provenanceCount = currentExtraction.semantic_provenance?.length || 0;
  document.querySelector("#reconciliation-workflow")?.closest("details")?.setAttribute("open", "");
  document.querySelector("#reconciliation-workflow")?.scrollIntoView({ behavior: "smooth", block: "center" });
  $("#extraction-status").textContent = `Step 3 - Reconciliation Workspace: ${ambiguityCount} ambiguities and ${provenanceCount} provenance entries are ready for operator interpretation decisions.`;
  renderOperatorGuidance(
    "Resolve interpretation boundaries.",
    "Save interpretation decisions, then commit semantic interpretation before impact review.",
  );
}

function openManualAuthorityDefinition() {
  setManualAuthorityExpanded(true);
}

function closeManualAuthorityDefinition() {
  setManualAuthorityExpanded(false);
}

function setManualAuthorityExpanded(isExpanded) {
  if (!manualAuthorityDefinition) return;
  manualAuthorityDefinition.toggleAttribute("open", Boolean(isExpanded));
  manualAuthorityDefinition.dataset.expanded = String(Boolean(isExpanded));
}

function startManualFirstAuthoring() {
  openManualAuthorityDefinition();
  form.elements.protected_system?.focus();
  draftSessionStatus.textContent = "Manual-first authority definition opened. Extraction remains optional; manual fields are operator-authored semantic anchors.";
  $("#extraction-status").textContent = "Manual-first mode: write semantic anchors directly, then commit the draft before operational impact review. Extraction-assisted overrides must be explicitly committed.";
}

function handleReconciliationInteraction(event) {
  const choiceButton = event.target.closest("[data-resolution-choice]");
  if (choiceButton) {
    const item = choiceButton.closest(".resolution-item");
    item?.querySelectorAll("[data-resolution-choice]").forEach((button) => button.classList.remove("selected"));
    choiceButton.classList.add("selected");
    item.dataset.selectedChoice = choiceButton.dataset.resolutionChoice;
    return;
  }

  const saveButton = event.target.closest("[data-save-resolution]");
  if (saveButton) {
    saveInterpretationDecision(saveButton.dataset.saveResolution);
    return;
  }

  const unresolvedButton = event.target.closest("[data-mark-unresolved]");
  if (unresolvedButton) {
    markInterpretationUnresolved(unresolvedButton.dataset.markUnresolved);
  }
}

function saveInterpretationDecision(ambiguityId) {
  const item = document.querySelector(`[data-ambiguity-id="${ambiguityId}"]`);
  const ambiguity = requiredSemanticAmbiguities().find((candidate) => candidate.ambiguity_id === ambiguityId);
  const choice = item?.dataset.selectedChoice || item?.querySelector("[data-resolution-choice].selected")?.dataset.resolutionChoice;
  const rationale = item?.querySelector("[data-resolution-rationale]")?.value?.trim() || "";
  const tier = ambiguity ? ambiguityTier(ambiguity) : "informational";
  const attested = Boolean(item?.querySelector("[data-resolution-attestation]")?.checked);
  const status = item?.querySelector(".resolution-status");
  if (!ambiguity || !choice) {
    if (status) status.textContent = "Select an interpretation before saving the decision.";
    return;
  }
  if (tier === "high-impact" && !rationale) {
    if (status) status.textContent = "Operator rationale is required before saving the decision.";
    return;
  }
  if (tier === "high-impact" && !attested) {
    if (status) status.textContent = "Operator attestation is required before saving this high-impact interpretation.";
    return;
  }
  if (tier === "blocking") {
    if (status) status.textContent = "Blocking ambiguity cannot be committed from reconciliation. Clarify the source policy first.";
    return;
  }
  if (isUnresolvedChoice(choice)) {
    markInterpretationUnresolved(ambiguityId, choice, rationale);
    return;
  }
  const decision = buildInterpretationDecision(ambiguity, choice, rationale || "Acknowledged informational interpretation.");
  interpretationDecisions = [
    ...interpretationDecisions.filter((item) => item.ambiguity_id !== ambiguityId),
    decision,
  ];
  unresolvedReconciliationBlocks = unresolvedReconciliationBlocks.filter((item) => item.ambiguity_id !== ambiguityId);
  recordInterpretationAudit(
    "interpretation_decision_saved",
    `${formatLabel(ambiguity.ambiguity_type)} resolved as ${choice}.`,
    { ambiguity_id: ambiguityId, decision_id: decision.decision_id },
  );
  updateReconciliationState();
  renderReconciliationWorkflow("#reconciliation-workflow", currentExtraction.ambiguities);
}

function markInterpretationUnresolved(ambiguityId, selectedInterpretation = "Mark unresolved ambiguity", rationale = "") {
  const ambiguity = requiredSemanticAmbiguities().find((candidate) => candidate.ambiguity_id === ambiguityId);
  const item = document.querySelector(`[data-ambiguity-id="${ambiguityId}"]`);
  const enteredRationale = rationale || item?.querySelector("[data-resolution-rationale]")?.value?.trim() || "";
  const status = item?.querySelector(".resolution-status");
  const tier = ambiguity ? ambiguityTier(ambiguity) : "informational";
  if (!ambiguity) return;
  if (tier !== "informational" && !enteredRationale) {
    if (status) status.textContent = "Operator rationale is required before marking an ambiguity unresolved.";
    return;
  }
  unresolvedReconciliationBlocks = [
    ...unresolvedReconciliationBlocks.filter((block) => block.ambiguity_id !== ambiguityId),
    {
      schema_version: "semantic_unresolved_blocker.v1",
      ambiguity_id: ambiguityId,
      ambiguity_type: ambiguity.ambiguity_type,
      selected_interpretation: selectedInterpretation,
      rationale: enteredRationale || "Acknowledged as unresolved informational ambiguity.",
      operator: "local-ledger-ui",
    },
  ];
  interpretationDecisions = interpretationDecisions.filter((decision) => decision.ambiguity_id !== ambiguityId);
  recordInterpretationAudit(
    "interpretation_marked_unresolved",
    `${formatLabel(ambiguity.ambiguity_type)} remains an unresolved blocker.`,
    { ambiguity_id: ambiguityId },
  );
  updateReconciliationState();
  renderReconciliationWorkflow("#reconciliation-workflow", currentExtraction.ambiguities);
}

function semanticExtrasFromCandidate(candidate) {
  const extras = {};
  for (const key of [
    "temporal_semantics",
    "state_snapshot_semantics",
    "execution_context_semantics",
    "governance_actor",
    "authority_role_binding",
    "approval_chain_semantics",
    "identity_continuity_semantics",
  ]) {
    if (candidate?.[key] && typeof candidate[key] === "object") {
      extras[key] = candidate[key];
    }
  }
  return extras;
}

function applyDraftToForm(candidate, provenance = "Committed") {
  for (const [key, value] of Object.entries(candidate || {})) {
    const field = form.elements[key];
    if (!field || value === null || value === undefined || value === "") continue;
    if (field.type === "checkbox") {
      field.checked = Boolean(value);
    } else {
      field.value = value;
    }
    setFieldProvenance(key, provenance);
  }
}

function populateManualFieldsFromCommittedDraft() {
  if (!committedDraft) {
    draftSessionStatus.textContent = "No committed interpretation is available to populate manual fields.";
    return;
  }
  openManualAuthorityDefinition();
  applyDraftToForm(committedDraft, "Committed");
  authoringSessionDirty = false;
  draftSessionStatus.textContent = "Manual fields populated from committed interpretation.";
}

function buildSemanticCommitBundleForUi() {
  if (!currentReconciliation || currentReconciliation.interpretation_completeness_posture !== "complete") {
    throw new Error("Semantic reconciliation must be complete before compilation.");
  }
  if (!committedDraft) {
    throw new Error("Committed semantic meaning is required before compilation.");
  }
  const semanticHash = stableHash(committedDraft);
  return {
    schema_version: "semantic_commit_bundle.v1",
    source_id: currentReconciliation.source_id,
    source_hash: currentReconciliation.source_hash,
    extraction_id: currentReconciliation.extraction_id,
    semantic_commit_id: `semantic-commit-${semanticHash.replace("draft:", "")}`,
    semantic_commit_hash: semanticHash,
    committed_at: new Date().toISOString(),
    committed_by: "local-ledger-ui",
    committed_capabilities: committedDraft.capabilities || [],
    resolved_interpretations: currentReconciliation.operator_interpretation_decisions || [],
    approved_constraints: {
      approval: committedDraft.approval_chain_semantics || {},
      escalation: {
        escalation_threshold: committedDraft.escalation_threshold || null,
        escalation_semantics: committedDraft.escalation_semantics || "",
      },
      continuity: committedDraft.state_snapshot_semantics || {},
      execution: committedDraft.execution_context_semantics || {},
    },
    lifecycle_posture: {
      revocation_invalidates_resume: Boolean(committedDraft.revocation_invalidates_resume),
      supersession_requires_revalidation: Boolean(committedDraft.continuity_revalidation),
    },
    continuity_posture: committedDraft.state_snapshot_semantics || {},
    identity_bindings: {
      governance_actor: committedDraft.governance_actor || {},
      authority_role_binding: committedDraft.authority_role_binding || {},
      approval_chain_semantics: committedDraft.approval_chain_semantics || {},
      identity_continuity_semantics: committedDraft.identity_continuity_semantics || {},
    },
    execution_admissibility_semantics: {
      execution_context: committedDraft.execution_context_semantics || {},
      temporal_validation: committedDraft.temporal_semantics || {},
      runtime_enforced_by: "Guard/Cloud",
      ledger_boundary: "models deterministic runtime representation only",
    },
    replay_obligations: committedDraft.state_snapshot_semantics?.snapshot_required
      ? [{ obligation_type: "state_snapshot_evidence", required: true, binding: "active_governance_state" }]
      : [],
    committed_semantic_meaning: committedDraft,
    non_goals: [
      "does_not_interpret_raw_policy_text",
      "does_not_compile_provisional_extraction",
      "does_not_resolve_ambiguities",
      "does_not_call_guard",
      "does_not_determine_runtime_admissibility",
    ],
    bundle_hash: stableHash({
      semantic_hash: semanticHash,
      decisions: currentReconciliation.operator_interpretation_decisions || [],
    }),
  };
}

async function compileAuthorityContract() {
  if (!canCompileAuthorityContract()) {
    renderOperatorGuidance(
      "Semantic compilation unavailable.",
      "Commit semantic interpretation before compiling the deterministic authority contract.",
    );
    return;
  }
  compileAuthorityButton.disabled = true;
  compileAuthorityButton.textContent = "Compiling Contract...";
  try {
    const semanticCommitBundle = buildSemanticCommitBundleForUi();
    const response = await fetch("/api/compile-authority", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ semantic_commit_bundle: semanticCommitBundle }),
    });
    const compiled = await response.json();
    if (!response.ok) {
      throw new Error(compiled.error || "Unable to compile authority contract.");
    }
    currentSemanticCommitBundle = semanticCommitBundle;
    currentCompiledAuthorityContract = compiled;
    setSemanticState({
      compiler_state: "compiled",
      compiled_contract_hash: compiled.contract_hash || null,
      impact_state: "not_reviewed",
      publication_state: "compiled_not_reviewed",
      invalidation_reason: null,
    });
    $("#extraction-status").textContent = `Authority contract compiled. Contract hash ${shortHash(compiled.contract_hash || "compiled:unavailable")}. Generate Operational Impact next.`;
    renderOperatorGuidance(
      "Authority contract compiled.",
      "Generate operational impact from the compiled deterministic authority contract before publication review.",
    );
  } catch (error) {
    resetCompiledAuthorityContract("compile_failed");
    renderDiagnostics([{ severity: "error", code: "authority_compile_error", text: error.message }]);
    renderOperatorGuidance("Authority compilation failed.", error.message);
  } finally {
    compileAuthorityButton.textContent = "Compile Authority Contract";
    syncPublicationActions();
  }
}

async function generateArtifacts(options = {}) {
  const shouldNavigate = options.navigate === true;
  const isReview = options.review === true || shouldNavigate;
  const isBackground = options.background === true;
  if (!isBackground && !canReviewImpact()) {
    renderInvalidatedImpact(semanticStateMachine.invalidation_reason || "draft_changed");
    renderOperatorGuidance(
      "Current semantics are invalidated.",
      "Resolve the working draft or source extraction before reviewing operational impact.",
    );
    syncPublicationActions();
    return;
  }
  if (!isBackground) {
    setBusy(true);
  }
  try {
    commitCurrentDraft();
    const draft = readDraft();
    const draftHash = stableHash(draft);
    const response = await fetch("/api/compose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unable to generate semantic artifacts.");
    }
    payload.ui_draft_hash = draftHash;
    payload.semantic_commit_bundle = currentSemanticCommitBundle;
    payload.compiled_authority_contract = currentCompiledAuthorityContract;
    currentArtifacts = payload;
    pendingRegistration = null;
    if (isReview) {
      workflowTimestamps.reviewed = new Date().toISOString();
      clearWorkflowInvalidation();
      setSemanticState({
        draft_state: "committed",
        semantic_state: "valid",
        compiler_state: "compiled",
        impact_state: "valid",
        publication_state: "reviewed_not_exported",
        draft_hash: draftHash,
        artifact_draft_hash: draftHash,
        compiled_contract_hash: currentCompiledAuthorityContract?.contract_hash || null,
        invalidation_reason: null,
      });
    }
    renderArtifacts(payload, { reviewed: isReview });
    exportButton.disabled = !isReview;
    registerButton.disabled = true;
    if (shouldNavigate) {
      showPage("preview");
    }
  } catch (error) {
    renderDiagnostics([{ severity: "error", code: "ui_generation_error", text: error.message }]);
  } finally {
    if (!isBackground) {
      setBusy(false);
    }
  }
}

function setBusy(isBusy) {
  reviewBusy = isBusy;
  generateButton.disabled = isBusy;
  generateButton.textContent = isBusy ? "Generating Impact..." : "Generate Operational Impact";
  publicationReviewButton.disabled = isBusy;
  publicationReviewButton.textContent = isBusy ? "Generating Impact..." : "Generate Operational Impact";
  compileAuthorityButton.disabled = isBusy || !canCompileAuthorityContract();
  if (!isBusy) {
    syncPublicationActions();
  }
}

function updateWorkflowState(partial) {
  workflowState = { ...workflowState, ...partial };
  renderWorkflowState();
  renderOperatorGuidance();
}

function renderWorkflowState() {
  const steps = [
    ["draft", workflowState.draftReady, "Ready"],
    ["impact", workflowState.impactReviewed, "Reviewed"],
    ["exported", workflowState.bundleExported, "Exported"],
    ["receipt", workflowState.receiptGenerated, "Generated"],
    ["registered", workflowState.authorityRegistered, "Registered"],
  ];
  const firstPending = steps.find(([_, complete]) => !complete)?.[0] || null;
  for (const [step, complete, completeLabel] of steps) {
    const node = document.querySelector(`[data-workflow-step="${step}"]`);
    if (!node) continue;
    node.classList.toggle("complete", complete);
    node.classList.toggle("current", !complete && step === firstPending);
    node.querySelector("strong").textContent = complete ? completeLabel : "Pending";
  }
  syncPublicationActions();
  renderAuthorityContext();
  renderOperationsOverview();
  if (semanticStateMachine.impact_state === "invalidated" && !currentArtifacts) {
    renderInvalidatedImpact(semanticStateMachine.invalidation_reason);
    renderInvalidatedChangeReview(semanticStateMachine.invalidation_reason);
    renderPublicationProjection(null);
  } else {
    renderPublicationProjection(authorityWorkspaceProjection());
  }
}

function syncPublicationActions() {
  const hasArtifacts = Boolean(currentArtifacts);
  const reviewAvailable = canGenerateOperationalImpact();
  extractPolicyButton.disabled = reviewBusy || !canExtractSemantics();
  useExtractionButton.disabled = !canCommitSemanticInterpretation();
  compileAuthorityButton.disabled = reviewBusy || !canCompileAuthorityContract();
  if (applyAllExtractionButton) applyAllExtractionButton.disabled = true;
  openReconciliationButton.disabled = !canReconcileAmbiguities();
  generateButton.disabled = reviewBusy || !reviewAvailable;
  publicationReviewButton.disabled = reviewBusy || !reviewAvailable || workflowState.impactReviewed;
  exportButton.disabled = !canExportBundle(hasArtifacts);
  registerButton.disabled = !canRegisterAuthority();
}

function canExtractSemantics() {
  return Boolean(policySourceText?.value?.trim());
}

function canCommitSemanticInterpretation() {
  return Boolean(
    currentExtraction?.candidate_authority
      && semanticStateMachine.semantic_state !== "committed"
      && reconciliationIsComplete(),
  );
}

function canReconcileAmbiguities() {
  return Boolean(currentExtraction);
}

function canCompileAuthorityContract() {
  return Boolean(
    committedDraft
      && currentReconciliation?.interpretation_completeness_posture === "complete"
      && semanticStateMachine.semantic_state === "committed"
      && semanticStateMachine.draft_state === "committed"
      && semanticStateMachine.compiler_state !== "compiled"
      && !authoringSessionDirty
      && !policySourceDirty,
  );
}

function canGenerateOperationalImpact() {
  return Boolean(
    workflowState.draftReady
      && !authoringSessionDirty
      && !policySourceDirty
      && semanticStateMachine.semantic_state === "committed"
      && semanticStateMachine.compiler_state === "compiled"
      && currentCompiledAuthorityContract
      && semanticStateMachine.draft_state === "committed",
  );
}

function canReviewImpact() {
  return canGenerateOperationalImpact();
}

function canExportBundle(hasArtifacts = Boolean(currentArtifacts)) {
  return Boolean(hasArtifacts && workflowState.impactReviewed && semanticStateMachine.impact_state === "valid");
}

function canRegisterAuthority() {
  return Boolean(pendingRegistration && workflowState.bundleExported && semanticStateMachine.impact_state === "valid" && !workflowState.authorityRegistered);
}

function renderOperatorGuidance(title, body) {
  const guidance = $("#operator-guidance");
  if (!guidance) return;
  if (title && body) {
    guidance.querySelector("strong").textContent = title;
    guidance.querySelector("span").textContent = body;
    return;
  }
  if (authoringSessionDirty) {
    guidance.querySelector("strong").textContent = "Unsaved draft changes.";
    guidance.querySelector("span").textContent = "Extract and commit semantic interpretation before treating edits as authority posture.";
  } else if (!workflowState.draftReady) {
    guidance.querySelector("strong").textContent = "Draft policy text.";
    guidance.querySelector("span").textContent = "Extract candidate semantics, reconcile ambiguities, then commit the semantic interpretation.";
  } else if (semanticStateMachine.semantic_state === "committed" && semanticStateMachine.compiler_state !== "compiled") {
    guidance.querySelector("strong").textContent = "Compile authority contract next.";
    guidance.querySelector("span").textContent = "Compilation turns committed governance meaning into deterministic runtime representation.";
  } else if (!workflowState.impactReviewed) {
    guidance.querySelector("strong").textContent = "Generate operational impact next.";
    guidance.querySelector("span").textContent = "Ledger has a compiled authority contract. Generate impact to review publication-relevant meaning.";
  } else if (!workflowState.bundleExported) {
    guidance.querySelector("strong").textContent = "Impact is reviewed.";
    guidance.querySelector("span").textContent = "Export the authority bundle to create receipt evidence and prepare local registration.";
  } else if (!workflowState.authorityRegistered) {
    guidance.querySelector("strong").textContent = "Bundle exported with receipt evidence.";
    guidance.querySelector("span").textContent = "Register the authority locally to record the lifecycle event and make it visible in the registry.";
  } else {
    guidance.querySelector("strong").textContent = "Authority registered locally.";
    guidance.querySelector("span").textContent = "The registry now holds lifecycle lineage, receipt posture, and replay-ready publication evidence.";
  }
}

function renderAuthorityContext() {
  const stableDraft = committedDraft || null;
  const authorityRef = currentArtifacts?.authority_bundle?.authority_ref || (stableDraft ? `${stableDraft.contract_id || "authority"}@${stableDraft.contract_version || "draft"}` : "No committed authority draft");
  const registryEntry = currentArtifacts?.authority_bundle ? findRegistryEntry(currentArtifacts.authority_bundle.authority_ref) : null;
  $("#context-authority-ref").textContent = authorityRef;
  $("#context-reviewed-at").textContent = workflowTimestamps.reviewed
    ? relativeTime(workflowTimestamps.reviewed)
    : "not reviewed";
  $("#context-lineage").textContent = registryEntry
    ? `${formatLabel(registryEntry.status)} lineage`
    : "draft lineage";
  setContextChip("#context-draft-state", !authoringSessionDirty, authoringSessionDirty ? "Unsaved changes" : "Draft");
  setContextChip("#context-review-state", workflowState.impactReviewed, workflowState.impactReviewed ? "Impact reviewed" : "Impact pending");
  setContextChip("#context-export-state", workflowState.bundleExported, workflowState.bundleExported ? "Exported" : "Not exported");
  setContextChip("#context-register-state", workflowState.authorityRegistered, workflowState.authorityRegistered ? "Registered" : "Not registered");
}

function setContextChip(selector, complete, text) {
  const node = $(selector);
  if (!node) return;
  node.textContent = text;
  node.classList.toggle("complete", complete);
  node.classList.toggle("active", !complete);
}

function scheduleLivePreview() {
  window.clearTimeout(livePreviewTimer);
  livePreviewTimer = window.setTimeout(() => {
    generateArtifacts({ background: true });
  }, 450);
}

function renderInvalidatedImpact(reason) {
  $("#status-semantic").textContent = "semantic extraction invalidated";
  $("#status-bundle").textContent = "publication blocked";
  $("#preview-summary").textContent = invalidatedImpactMessage(reason);
  renderList("#preview-enforcement", ["Extraction and reconciliation are required before Ledger can render current enforcement behavior."]);
  renderList("#preview-consequences", ["Prior operational consequences were cleared because they were derived from stale semantic lineage."]);
  renderList("#preview-lifecycle", ["Lifecycle implications require a fresh review derived from the current committed draft."]);
  renderExecutionContext("#preview-execution-context", null);
  renderOutcomes([]);
  renderList("#outcome-explorer", ["No operational outcome is reviewable until semantic meaning is regenerated for the current draft."]);
}

function renderInvalidatedChangeReview(reason) {
  const status = $("#change-review-status");
  const narrative = $("#change-narrative");
  const operational = $("#change-operational");
  const continuity = $("#change-continuity");
  const replay = $("#change-replay");
  const executionContext = $("#change-execution-context");
  const lineage = $("#change-lineage");
  if (!status || !narrative || !operational || !continuity || !replay || !executionContext || !lineage) return;
  status.textContent = "Semantic lineage invalidated";
  narrative.querySelector("h3").textContent = "Change review requires current semantic meaning.";
  narrative.querySelector("p").textContent = invalidatedImpactMessage(reason);
  operational.textContent = "Operational change is not reviewable until extraction or draft reconciliation is refreshed.";
  continuity.textContent = "Continuity posture is invalidated because it was derived from prior semantic inputs.";
  renderReplayPosture(replay, null, null);
  renderExecutionContext("#change-execution-context", null);
  lineage.innerHTML = "";
  appendLineageEmpty(lineage);
}

function invalidatedImpactMessage(reason) {
  if (reason === "policy_source_changed") {
    return "Semantic extraction invalidated by policy text changes. Extract governance meaning again before reviewing operational impact.";
  }
  if (reason === "draft_changed") {
    return "Semantic extraction invalidated by draft changes. Save the draft, then review impact from the current committed authority state.";
  }
  return "Semantic extraction invalidated. Regenerate governance meaning before reviewing operational impact.";
}

function renderArtifacts(payload, options = {}) {
  const reviewed = options.reviewed === true;
  const preserveWorkflow = options.preserveWorkflow === true;
  if (!preserveWorkflow && payload?.ui_draft_hash && payload.ui_draft_hash !== committedDraftHash()) {
    renderInvalidatedImpact("draft_changed");
    renderInvalidatedChangeReview("draft_changed");
    return;
  }
  const preview = payload.governance_impact_preview;
  const bundle = payload.authority_bundle;
  const workspaceProjection = authorityWorkspaceProjection(payload);
  $("#status-authority-ref").textContent = bundle.authority_ref;
  $("#status-semantic").textContent = reviewed ? "ready" : "changes need review";
  $("#status-bundle").textContent = reviewed ? "ready to export" : "review impact before export";
  if (!preserveWorkflow) {
    updateWorkflowState({
      draftReady: true,
      impactReviewed: reviewed,
      bundleExported: false,
      receiptGenerated: false,
      authorityRegistered: false,
    });
  }

  $("#preview-summary").textContent = preview.governance_summary;
  renderList("#preview-enforcement", preview.enforcement_behavior);
  renderList("#preview-consequences", preview.operational_consequences);
  renderList("#preview-lifecycle", preview.lifecycle_implications);
  renderExecutionContext("#preview-execution-context", preview.execution_context);
  renderOutcomes(preview.example_governed_outcomes);
  renderList("#outcome-explorer", buildOutcomeExplorer(preview, bundle));

  $("#bundle-meaning").textContent = bundle.publication_meaning;
  $("#integrity-posture").textContent = bundle.schema_compatibility.compatible
    ? "Semantic artifacts, manifest, and bundle schema expectations are aligned."
    : "Schema posture requires review before publication export.";
  $("#lineage-posture").textContent = bundle.lineage.source_hash && bundle.lineage.compilation_report_hash
    ? "Source and compilation lineage are present for authority publication."
    : "Lineage is incomplete; review source and compilation provenance before export.";
  renderList("#publication-consequences", bundle.operational_implications);
  renderDefinitionList("#immutable-inputs", bundle.immutable_inputs);
  renderDefinitionList("#lineage-list", bundle.lineage);
  $("#schema-compatibility").textContent = bundle.schema_compatibility.compatible
    ? "Compatible with additive v1 semantic artifact expectations."
    : "Schema compatibility requires review before export.";
  $("#manifest-json").textContent = JSON.stringify(payload.publication_manifest, null, 2);
  $("#bundle-json").textContent = JSON.stringify(bundle, null, 2);
  $("#receipt-json").textContent = "No publication receipt generated yet.";
  renderPublicationProjection(workspaceProjection);
  renderChangeReview(payload, { reviewed });
  renderOperationsOverview();

  renderDiagnostics(payload.diagnostics);
}

function authorityWorkspaceProjection(payload = currentArtifacts) {
  if (!payload) return null;
  const projection = payload.authority_workspace_projection || {};
  const narrative = payload.authority_release_narrative || {};
  const bundle = payload.authority_bundle || {};
  const registryEntry = bundle.authority_ref ? findRegistryEntry(bundle.authority_ref) : null;
  return {
    schema_version: "authority_workspace_projection.v1",
    authority_ref: bundle.authority_ref || narrative.authority_ref || projection.authority_ref,
    lifecycle_posture: registryEntry?.status || projection.lifecycle_posture || "draft",
    review_state: workflowState.impactReviewed ? "impact_reviewed" : projection.review_state || "impact_pending",
    export_state: workflowState.bundleExported ? "exported" : projection.export_state || "not_exported",
    registration_state: workflowState.authorityRegistered || registryEntry ? "registered" : projection.registration_state || "not_registered",
    operational_change: projection.operational_change || narrative.operational_change,
    continuity_posture: projection.continuity_posture || narrative.continuity_summary,
    lifecycle_effect: projection.lifecycle_effect || narrative.lifecycle_summary,
    publication_meaning: projection.publication_meaning || narrative.headline,
    publication_summary: projection.publication_summary || narrative.publication_summary,
    registry_posture: publicationRegistryPosture(registryEntry),
    replay_posture: registryEntry?.publication_receipt?.receipt_hash
      ? `Replay review can bind to receipt ${registryEntry.publication_receipt.receipt_hash}.`
      : projection.replay_posture,
  };
}

function publicationRegistryPosture(registryEntry) {
  if (registryEntry) {
    return "Authority registered locally. Registry lifecycle now has a registered authority event.";
  }
  if (workflowState.receiptGenerated) {
    return "Bundle exported. Authority is not registered locally yet.";
  }
  if (workflowState.impactReviewed) {
    return "Bundle ready to export. Authority not registered locally.";
  }
  return "Review impact before exporting this authority bundle.";
}

function renderPublicationProjection(projection) {
  $("#release-headline").textContent = projection?.publication_meaning || "Review impact before publishing.";
  $("#release-summary").textContent = projection?.publication_summary || "Create or restore an authority draft to see what publishing changes operationally.";
  $("#release-operational").textContent = projection?.operational_change || "Pending impact review.";
  $("#release-continuity").textContent = projection?.continuity_posture || "Pending impact review.";
  $("#release-lifecycle").textContent = projection?.lifecycle_effect || "Pending impact review.";
  $("#release-registration").textContent = projection?.registry_posture || "Bundle not exported.";
}

function renderExecutionContext(selector, executionContext) {
  const node = $(selector);
  if (!node) return;
  if (!executionContext) {
    renderDefinitionValues(selector, {
      Context: "not modeled",
      Continuity: "authority defaults",
    });
    return;
  }
  renderDefinitionValues(selector, {
    Context: formatLabel(executionContext.execution_context || "unspecified"),
    "Replay posture": executionContext.replay_posture || "authority defaults",
    "Resume behavior": executionContext.resume_posture || "not modeled",
    "Runtime boundary": executionContext.runtime_enforced_by || "Guard/Cloud",
  });
}

function renderList(selector, items) {
  const node = $(selector);
  node.innerHTML = "";
  for (const item of items || []) {
    const li = document.createElement("li");
    li.textContent = item;
    node.appendChild(li);
  }
}

function renderOutcomes(items) {
  const node = $("#preview-outcomes");
  node.innerHTML = "";
  for (const item of items || []) {
    const article = document.createElement("div");
    article.className = "outcome-item";
    const title = document.createElement("strong");
    title.textContent = formatLabel(item.outcome);
    const body = document.createElement("span");
    body.textContent = item.description;
    article.append(title, body);
    node.appendChild(article);
  }
}

function renderDefinitionList(selector, value) {
  const node = $(selector);
  node.innerHTML = "";
  for (const [key, item] of Object.entries(value || {})) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = formatLabel(key);
    dd.textContent = typeof item === "object" && item !== null ? JSON.stringify(item) : String(item);
    node.append(dt, dd);
  }
}

function renderDiagnostics(items) {
  const node = $("#diagnostics-list");
  const summary = $("#diagnostics-summary");
  node.innerHTML = "";
  summary.innerHTML = "";
  const diagnostics = (items || []).map(projectDiagnostic);
  const warningCount = diagnostics.filter((item) => item.severity === "warning").length;
  const infoCount = diagnostics.filter((item) => item.severity === "info").length;
  const domains = new Set(diagnostics.map((item) => item.domain).filter(Boolean));
  summary.append(
    diagnosticMetric("Findings", diagnostics.length),
    diagnosticMetric("Warnings", warningCount),
    diagnosticMetric("Info", infoCount),
    diagnosticMetric("Domains", domains.size),
  );
  if (!items || items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("strong");
    title.textContent = "No advisory diagnostics.";
    const text = document.createElement("span");
    text.textContent = "This draft has no current quality warnings. Continue reviewing publication posture before export.";
    empty.append(title, text);
    node.appendChild(empty);
    return;
  }
  for (const item of items) {
    const projected = projectDiagnostic(item);
    const row = document.createElement("div");
    row.className = `diagnostic-row ${projected.severity || "info"}`;
    const heading = document.createElement("div");
    heading.className = "diagnostic-heading";
    const title = document.createElement("strong");
    title.textContent = projected.operational_guidance;
    const domain = document.createElement("span");
    domain.className = "diagnostic-domain";
    domain.textContent = projected.domain || "governance";
    heading.append(title, domain);
    const text = document.createElement("span");
    text.textContent = projected.governance_detail;
    row.append(heading, text);
    if (projected.recommendation) {
      const recommendation = document.createElement("p");
      recommendation.className = "diagnostic-recommendation";
      recommendation.textContent = projected.recommendation;
      row.appendChild(recommendation);
    }
    if (projected.rationale || projected.operational_examples?.length || projected.replay_implications?.length || projected.technical_detail) {
      const details = document.createElement("details");
      details.className = "diagnostic-rationale";
      const summary = document.createElement("summary");
      summary.textContent = "Governance detail and technical context";
      details.appendChild(summary);
      if (projected.rationale) {
        const rationale = document.createElement("p");
        rationale.textContent = projected.rationale;
        details.appendChild(rationale);
      }
      appendDetailList(details, "Operational examples", projected.operational_examples);
      appendDetailList(details, "Replay implications", projected.replay_implications);
      if (projected.technical_detail) {
        const technical = document.createElement("pre");
        technical.className = "technical-diagnostic";
        technical.textContent = projected.technical_detail;
        details.appendChild(technical);
      }
      row.appendChild(details);
    }
    node.appendChild(row);
  }
}

function projectDiagnostic(item) {
  const diagnostic = item || {};
  const code = diagnostic.code || "diagnostic";
  if (code === "publication_evidence_unavailable" || code === "publication_receipt_error") {
    return {
      severity: "warning",
      domain: "publication",
      operational_guidance: "Publication receipt has not been generated yet.",
      governance_detail: "Current authority export could not create replayable publication evidence.",
      recommendation: "Review the authority bundle and export again to create a publication receipt.",
      rationale: "Publication receipts bind the exported authority to lineage, semantic artifact hashes, and publication posture.",
      operational_examples: [
        "A later review can confirm which authority bundle was exported and when.",
      ],
      replay_implications: [
        "Without a receipt, future replay review has less publication evidence to bind against.",
      ],
      technical_detail: `${code}: ${diagnostic.text || diagnostic.recommendation || "receipt generation failed"}`,
    };
  }
  return {
    severity: diagnostic.severity || "info",
    domain: diagnostic.domain || "governance",
    operational_guidance: diagnostic.title || formatLabel(code),
    governance_detail: diagnostic.text || "Governance posture should be reviewed.",
    recommendation: diagnostic.recommendation || "",
    rationale: diagnostic.rationale || "",
    operational_examples: diagnostic.operational_examples || [],
    replay_implications: diagnostic.replay_implications || [],
    technical_detail: diagnostic.technical_detail || (diagnostic.code ? `${diagnostic.code}: ${diagnostic.type || "diagnostic"}` : ""),
  };
}

function appendDetailList(node, label, items) {
  if (!items || items.length === 0) return;
  const title = document.createElement("strong");
  title.textContent = label;
  const list = document.createElement("ul");
  list.className = "semantic-list";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  }
  node.append(title, list);
}

function diagnosticMetric(label, value) {
  const metric = document.createElement("div");
  metric.className = "diagnostic-metric";
  const labelNode = document.createElement("span");
  labelNode.textContent = label;
  const valueNode = document.createElement("strong");
  valueNode.textContent = value;
  metric.append(labelNode, valueNode);
  return metric;
}

function loadBundleRegistry() {
  try {
    const raw = window.localStorage.getItem(BUNDLE_REGISTRY_KEY);
    if (!raw) return emptyBundleRegistry();
    const registry = JSON.parse(raw);
    if (registry.schema_version !== "authority_bundle_registry.v1") return emptyBundleRegistry();
    if (!Array.isArray(registry.authorities)) return emptyBundleRegistry();
    return registry;
  } catch {
    return emptyBundleRegistry();
  }
}

function emptyBundleRegistry() {
  return {
    schema_version: "authority_bundle_registry.v1",
    updated_at: null,
    authorities: [],
  };
}

function saveBundleRegistry(registry) {
  registry.updated_at = new Date().toISOString();
  window.localStorage.setItem(BUNDLE_REGISTRY_KEY, JSON.stringify(registry));
  renderBundleRegistry();
  renderOperationsOverview();
  renderChangeReview(currentArtifacts, { reviewed: workflowState.impactReviewed });
}

function publishCurrentBundleToRegistry(receipt, publicationNotes) {
  if (!currentArtifacts) return null;
  const registry = loadBundleRegistry();
  const bundle = currentArtifacts.authority_bundle;
  const authority = currentArtifacts.authority_contract;
  const projection = currentArtifacts.authority_registry_projection || {};
  const now = new Date().toISOString();
  const draftSession = loadDraftSession();
  const existing = registry.authorities.find((entry) => entry.authority_ref === bundle.authority_ref);
  const existingNotes = Array.isArray(existing?.publication_notes) ? existing.publication_notes : [];
  const appendedNotes = [...existingNotes, ...publicationNotes];
  const lifecycle = registryLifecycleEvents(existing).length
    ? registryLifecycleEvents(existing)
    : [
        lifecycleEvent("drafted", draftSession?.created_at || now, { bundle_hash: authority.contract_hash }, "Authority draft captured locally."),
        lifecycleEvent("reviewed", now, { bundle_hash: bundle.immutable_inputs.preview_hash }, "Impact reviewed by Ledger."),
      ];
  const registeredLifecycle = appendLifecycleOnce(
    lifecycle,
    "registered",
    receipt?.published_at || now,
    {
      bundle_hash: receipt?.bundle_hash || bundle.contract_hash,
      receipt_hash: receipt?.receipt_hash || null,
      manifest_hash: receipt?.manifest_hash || bundle.immutable_inputs.manifest_hash || null,
    },
    "Authority registered locally with authority_bundle.v1 and publication_receipt.v1.",
  );
  const diagnosticSummary = buildDiagnosticRollup(bundle.authority_ref, currentArtifacts.diagnostics || []);

  const entry = {
    schema_version: "authority_registry_entry.v1",
    registry_id: existing?.registry_id || `registry-${crypto.randomUUID()}`,
    authority_ref: bundle.authority_ref,
    authority_version: authorityVersionFromRef(bundle.authority_ref),
    status: existing?.status || "registered",
    published_at: existing?.published_at || receipt?.published_at || now,
    supersedes: existing?.supersedes || null,
    superseded_by: existing?.superseded_by || null,
    protected_resource: projection.governed_resource || authority.protected_resource,
    governed_action: projection.governed_action || "unspecified action",
    continuity_posture: projection.continuity_posture || "continuity review recommended",
    replay_readiness: receipt?.receipt_hash ? "receipt available" : "receipt pending",
    diagnostic_summary: diagnosticSummary,
    escalation_threshold: projection.escalation_threshold || "not defined",
    semantic_integrity_posture: projection.semantic_integrity_posture || "requires review",
    contract_hash: bundle.contract_hash,
    latest_bundle_hash: receipt?.bundle_hash || bundle.contract_hash,
    latest_receipt_hash: receipt?.receipt_hash || null,
    lifecycle_event_ids: registeredLifecycle.map((event) => event.event_id),
    created_at: existing?.created_at || draftSession?.created_at || now,
    updated_at: receipt?.published_at || now,
    immutable_inputs: bundle.immutable_inputs,
    lineage: bundle.lineage,
    lifecycle_events: registeredLifecycle,
    publication_receipt: receipt,
    publication_notes: appendedNotes,
    bundle,
    artifacts: {
      authority_contract: currentArtifacts.authority_contract,
      governance_impact_preview: currentArtifacts.governance_impact_preview,
      authority_diff_impact: bundle.authority_diff_impact || null,
      governance_review_packet: currentArtifacts.governance_review_packet,
      publication_manifest: currentArtifacts.publication_manifest,
      authority_bundle: bundle,
      publication_receipt: receipt,
      authority_registry_projection: projection,
      authority_workspace_projection: currentArtifacts.authority_workspace_projection,
      authority_operational_summary: currentArtifacts.authority_operational_summary,
      diagnostics: currentArtifacts.diagnostics || [],
    },
    operational_summary: registryOperationalSummary({
      authority_ref: bundle.authority_ref,
      authority_version: authorityVersionFromRef(bundle.authority_ref),
      status: existing?.status || "registered",
      protected_resource: projection.governed_resource || authority.protected_resource,
      governed_action: projection.governed_action || "unspecified action",
      continuity_posture: projection.continuity_posture || "continuity review recommended",
      replay_readiness: receipt?.receipt_hash ? "receipt available" : "receipt pending",
      publication_receipt: receipt,
      latest_receipt_hash: receipt?.receipt_hash || null,
      immutable_inputs: bundle.immutable_inputs,
      lineage: bundle.lineage,
      lifecycle_events: registeredLifecycle,
      diagnostic_summary: diagnosticSummary,
      bundle,
      artifacts: {
        authority_workspace_projection: currentArtifacts.authority_workspace_projection,
        authority_operational_summary: currentArtifacts.authority_operational_summary,
      },
    }),
  };

  registry.authorities = [entry, ...registry.authorities.filter((item) => item.authority_ref !== entry.authority_ref)];
  saveBundleRegistry(registry);
  return entry;
}

function lifecycleEvent(event, timestamp, artifactHashes, detail, previousEventId = null, authorityRef = null) {
  const eventAuthorityRef = authorityRef || currentArtifacts?.authority_bundle?.authority_ref || "unknown@draft";
  return {
    schema_version: "authority_lifecycle_event.v1",
    event_id: `event-${crypto.randomUUID()}`,
    authority_ref: eventAuthorityRef,
    authority_version: authorityVersionFromRef(eventAuthorityRef),
    event_type: event,
    timestamp,
    actor: "local-ledger-ui",
    source: "governance-ledger",
    artifact_hashes: artifactHashes || {},
    notes: { detail },
    previous_event_id: previousEventId,
  };
}

function appendLifecycleOnce(timeline, event, timestamp, artifactHashes, detail, authorityRef = null) {
  const hashKey = JSON.stringify(artifactHashes || {});
  if (timeline.some((item) => lifecycleEventType(item) === event && JSON.stringify(item.artifact_hashes || { bundle_hash: item.hash || null }) === hashKey)) {
    return timeline;
  }
  const previous = timeline[timeline.length - 1]?.event_id || null;
  return [...timeline, lifecycleEvent(event, timestamp, artifactHashes, detail, previous, authorityRef)];
}

function authorityVersionFromRef(authorityRef) {
  const parts = String(authorityRef || "").split("@");
  return parts.length > 1 && parts[parts.length - 1] ? parts[parts.length - 1] : "unversioned";
}

function buildDiagnosticRollup(authorityRef, diagnostics) {
  const severityRank = { none: 0, info: 1, warning: 2, error: 3 };
  const normalized = (diagnostics || []).map((item) => ({
    code: item.code || item.diagnostic_id,
    domain: item.domain,
    severity: severityRank[item.severity] ? item.severity : "info",
  }));
  const highest = normalized.reduce(
    (current, item) => (severityRank[item.severity] > severityRank[current] ? item.severity : current),
    "none",
  );
  return {
    schema_version: "diagnostic_rollup.v1",
    authority_ref: authorityRef,
    authority_version: authorityVersionFromRef(authorityRef),
    finding_count: normalized.length,
    warning_count: normalized.filter((item) => item.severity === "warning").length,
    info_count: normalized.filter((item) => item.severity === "info").length,
    domains: [...new Set(normalized.map((item) => item.domain).filter(Boolean))].sort(),
    highest_severity: highest,
    diagnostic_ids: normalized.map((item) => item.code).filter(Boolean),
  };
}

function clearWorkflowInvalidation() {
  workflowInvalidation = {
    active: false,
    reason: null,
    updated_at: null,
    invalidated_projections: [],
  };
}

function markDraftInvalidated() {
  workflowInvalidation = {
    active: true,
    reason: "draft_changed",
    updated_at: new Date().toISOString(),
    invalidated_projections: [
      "authority_workspace_projection.v1",
      "authority_operational_summary.v1",
      "governance_continuity_projection.v1",
      "governance_timeline_projection.v1",
      "replay_posture",
    ],
  };
}

function invalidateSemanticLineage(reason) {
  const now = new Date().toISOString();
  currentArtifacts = null;
  currentSemanticAuthorityDiff = null;
  currentLifecycleEnforcementProjection = null;
  currentSemanticCommitBundle = null;
  currentCompiledAuthorityContract = null;
  pendingRegistration = null;
  setSemanticState({
    draft_state: "dirty",
    semantic_state: "invalidated",
    compiler_state: "invalidated",
    impact_state: "invalidated",
    publication_state: "blocked",
    draft_hash: committedDraftHash(),
    artifact_draft_hash: null,
    compiled_contract_hash: null,
    invalidation_reason: reason,
    invalidated_at: now,
  });
  workflowInvalidation = {
    active: true,
    reason,
    updated_at: now,
    invalidated_projections: [
      "governance_semantic_extraction.v1",
      "governance_semantic_provenance.v1",
      "governance_semantic_reconciliation.v1",
      "semantic_commit_bundle.v1",
      "compiled_authority_contract.v1",
      "governance_impact_preview.v1",
      "authority_diff_impact.v1",
      "authority_workspace_projection.v1",
      "authority_operational_summary.v1",
      "publication_readiness",
    ],
  };
  renderInvalidatedImpact(reason);
  renderInvalidatedChangeReview(reason);
}

function registryCoherenceProjection(registry = loadBundleRegistry()) {
  const entries = registry.authorities || [];
  const activeByFamily = new Map();
  for (const entry of entries) {
    if (entry.status !== "registered" || entry.superseded_by) continue;
    const family = authorityFamily(entry.authority_ref);
    activeByFamily.set(family, [...(activeByFamily.get(family) || []), entry]);
  }
  const authorityConflicts = [...activeByFamily.values()].filter((items) => items.length > 1).length;
  const replayRisks = entries.filter((entry) => !entry.latest_receipt_hash && !entry.publication_receipt?.receipt_hash).length;
  const continuityRisks = entries.filter((entry) => authorityCoherenceProjection(entry, registry).severity === "continuity_risk").length;
  const staleProjections = entries.reduce(
    (total, entry) => total + projectionFreshnessForEntry(entry, registry).filter((item) => item.freshness_posture === "stale" || item.freshness_posture === "invalidated").length,
    workflowInvalidation.active ? workflowInvalidation.invalidated_projections.length : 0,
  );
  const posture = authorityConflicts
    ? "authority_conflict"
    : continuityRisks
      ? "continuity_risk"
      : replayRisks
        ? "replay_risk"
        : staleProjections
          ? "stale"
          : "healthy";
  return {
    schema_version: "governance_coherence_surface.v1",
    posture,
    title: coherenceTitle(posture),
    summary: coherenceSummary({ posture, continuityRisks, replayRisks, authorityConflicts, staleProjections }),
    counts: {
      continuity_risk: continuityRisks,
      replay_degradation: replayRisks,
      authority_conflict: authorityConflicts,
      stale_projections: staleProjections,
    },
    draft_invalidation: workflowInvalidation,
  };
}

function authorityCoherenceProjection(entry, registry = loadBundleRegistry()) {
  const familyEntries = (registry.authorities || []).filter((item) => authorityFamily(item.authority_ref) === authorityFamily(entry.authority_ref));
  const active = familyEntries.filter((item) => item.status === "registered" && !item.superseded_by);
  const freshness = projectionFreshnessForEntry(entry, registry);
  const hasInvalidated = freshness.some((item) => item.freshness_posture === "invalidated");
  const hasStale = freshness.some((item) => item.freshness_posture === "stale");
  const replayMissing = !entry.latest_receipt_hash && !entry.publication_receipt?.receipt_hash;
  const continuityRisk = ["superseded", "revoked"].includes(entry.status) || String(entry.continuity_posture || "").includes("revocation");
  const severity = active.length > 1
    ? "authority_conflict"
    : continuityRisk
      ? "continuity_risk"
      : replayMissing
        ? "replay_risk"
        : hasInvalidated
          ? "invalidated"
          : hasStale
            ? "stale"
            : "healthy";
  return {
    schema_version: "authority_coherence_surface.v1",
    authority_ref: entry.authority_ref,
    severity,
    label: coherenceTitle(severity),
    freshness,
    causality: continuityCausality(entry, registry, severity),
  };
}

function continuityCausality(entry, registry = loadBundleRegistry(), severity = null) {
  const events = registryLifecycleEvents(entry);
  const eventTypes = events.map(lifecycleEventType);
  const familyEntries = (registry.authorities || []).filter((item) => authorityFamily(item.authority_ref) === authorityFamily(entry.authority_ref));
  const activeSuccessors = familyEntries.filter((item) => item.status === "registered" && !item.superseded_by && item.authority_ref !== entry.authority_ref);
  const draftChanged = workflowInvalidation.active && currentArtifacts?.authority_bundle?.authority_ref === entry.authority_ref;
  const isRevoked = entry.status === "revoked" || eventTypes.includes("revoked");
  const isSuperseded = entry.status === "superseded" || eventTypes.includes("superseded") || Boolean(entry.superseded_by);
  const hasActiveSuccessor = activeSuccessors.length > 0;
  const posture = severity || authorityCoherenceProjection(entry, registry).severity;
  let reason = "Registry lineage, replay evidence, and lifecycle posture are coherent for this authority.";
  if (posture === "authority_conflict") {
    reason = `Multiple active ${authorityFamily(entry.authority_ref)} authorities are registered locally.`;
  } else if (isRevoked && isSuperseded && !hasActiveSuccessor) {
    reason = `${entry.authority_ref} was superseded and later revoked, but no currently active registered successor authority exists.`;
  } else if (isRevoked) {
    reason = `${entry.authority_ref} is revoked in the local registry lineage.`;
  } else if (isSuperseded) {
    reason = `${entry.authority_ref} was superseded by ${entry.superseded_by || "a successor authority"}.`;
  } else if (posture === "continuity_risk") {
    reason = `${entry.authority_ref} includes continuity semantics that require resumed execution to revalidate when authority posture changes.`;
  } else if (posture === "replay_risk") {
    reason = `${entry.authority_ref} does not have receipt-backed replay evidence attached.`;
  } else if (draftChanged) {
    reason = "The current draft changed after impact review, so the workspace view is no longer valid.";
  }
  const contributingEvents = events
    .filter((event) => ["drafted", "reviewed", "exported", "registered", "superseded", "revoked"].includes(lifecycleEventType(event)))
    .map((event) => ({
      type: formatLabel(lifecycleEventType(event)),
      timestamp: event.timestamp,
      detail: lifecycleEventDetail(event),
    }));
  if (draftChanged) {
    contributingEvents.push({
      type: "Draft Modified After Review",
      timestamp: workflowInvalidation.updated_at,
      detail: "Current draft changes invalidated reviewed workspace state.",
    });
  }
  return {
    posture,
    reason,
    impact: posture === "continuity_risk" || isRevoked || isSuperseded
      ? "Resumed execution should require governance revalidation before continuation."
      : posture === "replay_risk"
        ? "Replay review has less publication evidence to bind against until a receipt is present."
        : "No additional continuity action is indicated by the current local registry state.",
    contributing_events: contributingEvents,
    scopes: {
      current_draft: workflowState.impactReviewed ? "impact reviewed" : "pending review",
      historical_authority: formatLabel(entry.status),
      registry_lineage: lineageChainText(entry, registry),
      replay_evidence: entry.latest_receipt_hash || entry.publication_receipt?.receipt_hash ? "receipt-backed" : "receipt pending",
    },
  };
}

function projectionFreshnessForEntry(entry, registry = loadBundleRegistry()) {
  const generatedAt = entry.updated_at || entry.published_at || registry.updated_at || null;
  const sourceEventIds = registryLifecycleEvents(entry).map((event) => event.event_id || `${lifecycleEventType(event)}:${event.timestamp}`);
  const invalidated = workflowInvalidation.active && currentArtifacts?.authority_bundle?.authority_ref === entry.authority_ref
    ? new Set(workflowInvalidation.invalidated_projections)
    : new Set();
  const receiptPresent = Boolean(entry.latest_receipt_hash || entry.publication_receipt?.receipt_hash);
  return [
    projectionFreshnessItem("Operational Summary", "authority_operational_summary.v1", generatedAt, sourceEventIds, invalidated),
    projectionFreshnessItem("Lifecycle Timeline", "governance_timeline_projection.v1", generatedAt, sourceEventIds, invalidated),
    projectionFreshnessItem(
      "Replay Posture",
      "replay_posture",
      generatedAt,
      sourceEventIds,
      invalidated,
      receiptPresent ? "fresh" : "invalidated",
      receiptPresent ? "info" : "replay_risk",
      receiptPresent ? "Receipt-backed replay posture is available." : "Replay posture invalidated because receipt evidence is missing.",
    ),
    projectionFreshnessItem(
      "Continuity Posture",
      "governance_continuity_projection.v1",
      generatedAt,
      sourceEventIds,
      invalidated,
      "fresh",
      ["superseded", "revoked"].includes(entry.status) ? "continuity_risk" : "info",
      ["superseded", "revoked"].includes(entry.status)
        ? "Continuity posture refreshed after lifecycle posture changed."
        : "Continuity posture reflects current local lifecycle state.",
    ),
  ];
}

function projectionFreshnessItem(label, projection, generatedAt, sourceEventIds, invalidated, posture = "fresh", severity = "info", summary = null) {
  const freshness = invalidated.has(projection) ? "invalidated" : posture;
  return {
    projection,
    label,
    generated_at: generatedAt,
    source_event_ids: sourceEventIds,
    freshness_posture: freshness,
    severity: freshness === "invalidated" ? "authority_conflict" : severity,
    summary: summary || `${label} generated ${generatedAt ? relativeTime(generatedAt) : "from current workspace state"}.`,
  };
}

function authorityFamily(authorityRef) {
  return String(authorityRef || "").split("@", 1)[0] || "authority";
}

function coherenceTitle(posture) {
  return {
    healthy: "Registry Healthy",
    stale: "State Stale",
    invalidated: "State Invalidated",
    continuity_risk: "Continuity Controls Active",
    replay_risk: "Replay Risk",
    authority_conflict: "Authority Conflict",
  }[posture] || formatLabel(posture);
}

function coherenceSummary({ posture, continuityRisks, replayRisks, authorityConflicts, staleProjections }) {
  if (posture === "healthy") return "Registry coherence is valid across lifecycle, replay, continuity, and state freshness.";
  if (authorityConflicts) return `${authorityConflicts} authority conflict${authorityConflicts === 1 ? "" : "s"} require lifecycle reconciliation.`;
  if (continuityRisks) return `${continuityRisks} continuity-sensitive authority posture${continuityRisks === 1 ? "" : "s"} present in local authority lineage.`;
  if (replayRisks) return `${replayRisks} replay posture${replayRisks === 1 ? "" : "s"} missing receipt-backed continuity.`;
  return `${staleProjections} governance view${staleProjections === 1 ? "" : "s"} stale or invalidated relative to current workflow state.`;
}

function registryLifecycleEvents(entry) {
  return entry?.lifecycle_events || entry?.lifecycle_timeline || [];
}

function lifecycleEventType(event) {
  return event.event_type || event.event;
}

function lifecycleEventHash(event) {
  return event.artifact_hashes?.bundle_hash || event.hash || "no hash";
}

function shortHash(value) {
  const text = String(value || "");
  if (!text || text === "no hash") return "evidence pending";
  const normalized = text.replace(/^sha256:/, "");
  return `sha256:${normalized.slice(0, 10)}`;
}

function lifecycleEventDetail(event) {
  const detail = event.notes?.detail || event.detail || "Lifecycle event recorded.";
  if (detail === "Semantic artifacts generated by Ledger.") return "Impact reviewed by Ledger.";
  if (detail === "Authority registered locally with authority_bundle.v1 and publication_receipt.v1.") return "Authority registered locally with receipt-backed publication evidence.";
  return detail;
}

function entryProtectedResource(entry) {
  return entry.protected_resource || entry.governed_resource || "unspecified resource";
}

function diagnosticRollupSummary(rollup) {
  if (!rollup) return "none";
  return `${rollup.finding_count || 0} findings, ${rollup.highest_severity || "none"}`;
}

function registryOperationalSummary(entry) {
  const stored = entry.operational_summary || entry.artifacts?.authority_operational_summary;
  const workspace = entry.artifacts?.authority_workspace_projection || {};
  const summary = stored
    ? {
        ...stored,
        lifecycle: {
          ...(stored.lifecycle || {}),
          status: entry.status,
          events: registryLifecycleEvents(entry),
        },
        replay_readiness: replayReadinessProjection(entry, stored.replay_readiness),
        relationship_graph: relationshipGraphProjection(entry, stored.relationship_graph),
      }
    : {
        schema_version: "authority_operational_summary.v1",
        authority_ref: entry.authority_ref,
        authority_version: entry.authority_version || authorityVersionFromRef(entry.authority_ref),
        protected_resource: entryProtectedResource(entry),
        governed_action: entry.governed_action,
        lifecycle: {
          status: entry.status,
          events: registryLifecycleEvents(entry),
        },
        drift_summary: [],
        replay_readiness: replayReadinessProjection(entry),
        governance_meaning: [
          workspace.operational_change || firstText(entry.bundle?.operational_implications) || `${entry.authority_ref} governs ${entry.governed_action}.`,
          workspace.continuity_posture || entry.continuity_posture || "Continuity posture should be reviewed.",
          workspace.replay_posture || "Replay evidence binds to this authority lineage when receipt evidence is present.",
        ],
        relationship_graph: relationshipGraphProjection(entry),
      };
  return summary;
}

function replayReadinessProjection(entry, existing = {}) {
  const receiptPresent = Boolean(entry.latest_receipt_hash || entry.publication_receipt?.receipt_hash || existing.receipt_present);
  const immutable = entry.immutable_inputs || {};
  return {
    receipt_present: receiptPresent,
    semantic_hashes_aligned: Boolean(existing.semantic_hashes_aligned || immutable.preview_hash || immutable.review_packet_hashes || immutable.diff_hash),
    lineage_complete: Boolean(existing.lineage_complete || entry.lineage),
    manifest_aligned: Boolean(existing.manifest_aligned || immutable.manifest_hash || entry.publication_receipt?.manifest_hash),
    summary: existing.summary || (receiptPresent ? `Replay can bind to receipt ${entry.latest_receipt_hash || entry.publication_receipt.receipt_hash}.` : "Publication receipt evidence is missing."),
  };
}

function relationshipGraphProjection(entry, existing = {}) {
  const nodes = existing.nodes?.length
    ? existing.nodes
    : [
        {
          authority_ref: entry.authority_ref,
          authority_version: entry.authority_version || authorityVersionFromRef(entry.authority_ref),
          status: entry.status,
        },
      ];
  const edges = existing.edges?.length ? existing.edges : [];
  if (entry.superseded_by && !edges.some((edge) => edge.from === entry.authority_ref && edge.to === entry.superseded_by)) {
    edges.push({ from: entry.authority_ref, to: entry.superseded_by, relationship: "superseded_by" });
  }
  return { nodes, edges };
}

function renderBundleRegistry() {
  const registry = loadBundleRegistry();
  const summary = $("#bundle-registry-summary");
  const list = $("#bundle-registry");
  const filtered = filterRegistryEntries(registry.authorities);
  summary.innerHTML = "";
  list.innerHTML = "";
  renderRegistryOperationsOverview(registry);

  const registeredCount = registry.authorities.filter((entry) => entry.status === "registered").length;
  const revokedCount = registry.authorities.filter((entry) => entry.status === "revoked").length;
  const supersededCount = registry.authorities.filter((entry) => entry.status === "superseded").length;
  summary.append(
    registryMetric("Authorities", registry.authorities.length),
    registryMetric("Registered", registeredCount),
    registryMetric("Superseded", supersededCount),
    registryMetric("Revoked", revokedCount),
  );

  if (registry.authorities.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("strong");
    title.textContent = "No registered authorities yet.";
    const text = document.createElement("span");
    text.textContent = "Register an exported authority bundle to begin a replayable governance chronology.";
    empty.append(title, text);
    list.appendChild(empty);
    renderBundleDetail(null);
    return;
  }

  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("strong");
    title.textContent = "No authorities match these filters.";
    const text = document.createElement("span");
    text.textContent = "Try clearing search terms or expanding lifecycle and continuity filters.";
    empty.append(title, text);
    list.appendChild(empty);
    renderBundleDetail(null);
    return;
  }

  for (const entry of filtered) {
    list.appendChild(authorityRegistryCard(entry));
  }
  renderBundleDetail(filtered[0] || null);
}

function renderRegistryOperationsOverview(registry) {
  const entries = registry.authorities || [];
  const eventItems = registryEvents(entries);
  renderCoherenceBanner("#registry-coherence-banner", registryCoherenceProjection(registry));
  renderDefinitionValues("#registry-inventory", {
    Authorities: entries.length,
    Registered: entries.filter((entry) => entry.status === "registered").length,
    Superseded: entries.filter((entry) => entry.status === "superseded").length,
    Revoked: entries.filter((entry) => entry.status === "revoked").length,
    "Replay ready": entries.filter((entry) => entry.latest_receipt_hash || entry.publication_receipt?.receipt_hash).length,
    "Warnings": entries.reduce((total, entry) => total + (entry.diagnostic_summary?.warning_count || 0), 0),
  });
  renderTextList("#registry-lifecycle-posture", registryLifecyclePosture(entries), ["Lifecycle not started", "Register an authority to begin local lifecycle tracking."]);
  renderTextList("#registry-replay-readiness", registryReplayReadiness(entries), ["Replay posture awaiting receipt", "Export and register an authority to create receipt-backed replay readiness."]);
  renderTextList("#registry-drift-indicators", registryDriftIndicators(entries), ["No continuity drift detected", "No supersession, revocation, or stale review posture currently requires attention."]);
  renderActivityItems("#registry-recent-events", eventItems.slice(0, 6), ["No governance chronology yet", "Lifecycle events will appear after export, registration, supersession, or revocation."]);
}

function registryEvents(entries) {
  const events = [];
  for (const entry of entries) {
    for (const event of registryLifecycleEvents(entry)) {
      events.push({
        title: `${formatLabel(lifecycleEventType(event))}: ${entry.authority_ref}`,
        text: `${formatDateTime(event.timestamp)} | ${lifecycleEventDetail(event)}`,
        timestamp: event.timestamp,
      });
    }
  }
  return events.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
}

function registryLifecyclePosture(entries) {
  const posture = [];
  const registered = entries.filter((entry) => entry.status === "registered").length;
  const superseded = entries.filter((entry) => entry.status === "superseded").length;
  const revoked = entries.filter((entry) => entry.status === "revoked").length;
  if (registered) posture.push(["Active authorities", `${registered} authority record${registered === 1 ? "" : "s"} registered locally.`]);
  if (superseded) posture.push(["Supersession chains", `${superseded} authority record${superseded === 1 ? "" : "s"} superseded and require lineage review.`]);
  if (revoked) posture.push(["Revocation posture", `${revoked} authority record${revoked === 1 ? "" : "s"} revoked locally.`]);
  if (!posture.length && entries.length) posture.push(["Registry populated", "Authorities exist, but no active lifecycle exception requires attention."]);
  return posture.slice(0, 4);
}

function registryReplayReadiness(entries) {
  return entries.slice(0, 4).map((entry) => {
    const ready = entry.latest_receipt_hash || entry.publication_receipt?.receipt_hash;
    return [
      entry.authority_ref,
      ready
        ? `Replay can bind to receipt ${shortHash(entry.latest_receipt_hash || entry.publication_receipt.receipt_hash)}.`
        : "Receipt evidence is missing; replay readiness is incomplete.",
    ];
  });
}

function registryDriftIndicators(entries) {
  const indicators = [];
  for (const entry of entries) {
    if (entry.status === "superseded") {
      indicators.push([entry.authority_ref, `Superseded by ${entry.superseded_by || "pending successor"}; review resumed execution continuity.`]);
    } else if (entry.status === "revoked") {
      indicators.push([entry.authority_ref, "Revoked authority should invalidate resumed execution posture where continuity requires current authority."]);
    } else if ((entry.diagnostic_summary?.warning_count || 0) > 0) {
      indicators.push([entry.authority_ref, `${entry.diagnostic_summary.warning_count} diagnostic warning${entry.diagnostic_summary.warning_count === 1 ? "" : "s"} require governance awareness.`]);
    }
  }
  return indicators.slice(0, 4);
}

function renderOperationsOverview() {
  const registry = loadBundleRegistry();
  const bundle = currentArtifacts?.authority_bundle;
  const registryEntry = bundle ? findRegistryEntry(bundle.authority_ref) : null;
  const diagnostics = currentArtifacts?.diagnostics || [];
  const pendingActions = pendingGovernanceActions(registry, diagnostics);
  const alerts = lifecycleAlerts(registry, diagnostics);
  renderCoherenceBanner("#overview-coherence-banner", registryCoherenceProjection(registry));

  setText("#overview-authority-state", registryEntry ? formatLabel(registryEntry.status) : workflowState.impactReviewed ? "Reviewed Draft" : "Draft");
  setText("#overview-replay-readiness", workflowState.receiptGenerated || registryEntry?.publication_receipt ? "receipt available" : "receipt pending");
  setText("#overview-continuity-posture", continuityOverviewText(registryEntry, bundle));

  renderTextList("#overview-pending-actions", pendingActions, ["No pending actions", "No current draft, receipt, or registry action requires attention."]);
  renderTextList("#overview-lifecycle-alerts", alerts, ["No lifecycle alerts", "No revocation, supersession, or drift posture currently requires attention."]);
  renderRegistryHealth(registry);
  renderActivityFeed(registry);
  renderRelationshipFeed(registry);
}

function renderCoherenceBanner(selector, coherence) {
  const node = $(selector);
  if (!node) return;
  node.innerHTML = "";
  node.className = `coherence-banner ${coherence.posture}`;
  const lead = document.createElement("div");
  lead.className = "coherence-lead";
  const title = document.createElement("strong");
  title.textContent = coherence.title;
  const summary = document.createElement("span");
  summary.textContent = coherence.summary;
  lead.append(title, summary);
  const metrics = document.createElement("div");
  metrics.className = "coherence-metrics";
  metrics.append(
    coherenceMetric("Replay Continuity", coherence.counts.replay_degradation ? "Degraded" : "Stable", coherence.counts.replay_degradation ? "replay_risk" : "healthy"),
    coherenceMetric("Continuity Controls", coherence.counts.continuity_risk, coherence.counts.continuity_risk ? "continuity_risk" : "healthy"),
    coherenceMetric("Authority Conflicts", coherence.counts.authority_conflict, coherence.counts.authority_conflict ? "authority_conflict" : "healthy"),
    coherenceMetric("State Validity", coherence.counts.stale_projections ? `${coherence.counts.stale_projections} stale` : "Valid", coherence.counts.stale_projections ? "stale" : "healthy"),
  );
  node.append(lead, metrics);
  if (coherence.draft_invalidation?.active) {
    const invalidation = document.createElement("div");
    invalidation.className = "coherence-invalidation";
    invalidation.textContent = "Operational summary invalidated by draft changes. Impact review required before export.";
    node.appendChild(invalidation);
  }
}

function coherenceMetric(label, value, posture) {
  const item = document.createElement("div");
  item.className = `coherence-metric ${posture}`;
  const labelNode = document.createElement("span");
  labelNode.textContent = label;
  const valueNode = document.createElement("strong");
  valueNode.textContent = String(value);
  item.append(labelNode, valueNode);
  return item;
}

function setText(selector, text) {
  const node = $(selector);
  if (node) node.textContent = text;
}

function continuityOverviewText(registryEntry, bundle) {
  if (registryEntry?.continuity_posture) return registryEntry.continuity_posture;
  const firstContinuity = firstText(bundle?.continuity_implications);
  return firstContinuity || "review pending";
}

function pendingGovernanceActions(registry, diagnostics) {
  const actions = [];
  if (!workflowState.impactReviewed) {
    actions.push(["Review impact", "Confirm current authority meaning before export."]);
  }
  if (workflowState.impactReviewed && !workflowState.bundleExported) {
    actions.push(["Export bundle", "Create publication receipt evidence for the reviewed authority."]);
  }
  if (workflowState.receiptGenerated && !workflowState.authorityRegistered) {
    actions.push(["Register locally", "Record the authority lifecycle event in the local registry."]);
  }
  const warningCount = diagnostics.filter((item) => item.severity === "warning").length;
  if (warningCount > 0) {
    actions.push(["Review diagnostics", `${warningCount} governance warning${warningCount === 1 ? "" : "s"} require operator awareness.`]);
  }
  if (registry.authorities.length === 0) {
    actions.push(["Create registry baseline", "No authorities are registered locally yet."]);
  }
  return actions.slice(0, 4);
}

function lifecycleAlerts(registry, diagnostics) {
  const revoked = registry.authorities.filter((entry) => entry.status === "revoked").length;
  const superseded = registry.authorities.filter((entry) => entry.status === "superseded").length;
  const alerts = [];
  if (revoked) alerts.push(["Revoked authority posture", `${revoked} authority record${revoked === 1 ? "" : "s"} marked revoked.`]);
  if (superseded) alerts.push(["Supersession chain present", `${superseded} authority record${superseded === 1 ? "" : "s"} superseded locally.`]);
  if (diagnostics.some((item) => item.code === "GQ005")) {
    alerts.push(["Lifecycle ambiguity", "Supersession expectations should be clarified before broader publication."]);
  }
  if (!alerts.length) alerts.push(["No lifecycle alerts", "No revocation, supersession, or drift posture currently requires attention."]);
  return alerts.slice(0, 4);
}

function renderTextList(selector, items, empty) {
  const node = $(selector);
  if (!node) return;
  node.innerHTML = "";
  const materialized = items.length ? items : [empty];
  for (const [title, text] of materialized) {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = title;
    const span = document.createElement("span");
    span.textContent = text;
    li.append(strong, span);
    node.appendChild(li);
  }
}

function renderRegistryHealth(registry) {
  const active = registry.authorities.filter((entry) => entry.status === "registered").length;
  const superseded = registry.authorities.filter((entry) => entry.status === "superseded").length;
  const revoked = registry.authorities.filter((entry) => entry.status === "revoked").length;
  const replayReady = registry.authorities.filter((entry) => entry.latest_receipt_hash || entry.publication_receipt?.receipt_hash).length;
  renderDefinitionValues("#overview-registry-health", {
    Authorities: registry.authorities.length,
    Active: active,
    Superseded: superseded,
    Revoked: revoked,
    "Replay ready": replayReady,
    "Updated": registry.updated_at ? relativeTime(registry.updated_at) : "not registered",
  });
}

function renderDefinitionValues(selector, values) {
  const node = $(selector);
  if (!node) return;
  node.innerHTML = "";
  for (const [label, value] of Object.entries(values)) {
    const wrapper = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = String(value);
    wrapper.append(dt, dd);
    node.appendChild(wrapper);
  }
}

function renderActivityFeed(registry) {
  const events = [];
  for (const entry of registry.authorities) {
    for (const event of registryLifecycleEvents(entry)) {
      events.push({
        title: `${formatLabel(lifecycleEventType(event))}: ${entry.authority_ref}`,
        text: `${formatDateTime(event.timestamp)} | ${lifecycleEventDetail(event)}`,
        timestamp: event.timestamp,
      });
    }
  }
  if (workflowTimestamps.reviewed) {
    events.push({
      title: `Reviewed: ${currentArtifacts?.authority_bundle?.authority_ref || "current draft"}`,
      text: "Semantic impact reviewed in this workspace.",
      timestamp: workflowTimestamps.reviewed,
    });
  }
  events.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
  renderActivityItems("#overview-activity-feed", events.slice(0, 5), ["No recent activity", "Review or register an authority to create local lifecycle activity."]);
}

function renderRelationshipFeed(registry) {
  const relationships = registry.authorities.map((entry) => ({
    title: entry.authority_ref,
    text: relationshipSummary(entry),
    timestamp: entry.published_at,
  }));
  renderActivityItems("#overview-relationship-feed", relationships.slice(0, 5), ["No authority relationships", "Registered authorities will show active, superseded, and revoked lineage posture here."]);
}

function renderActivityItems(selector, items, empty) {
  const node = $(selector);
  if (!node) return;
  node.innerHTML = "";
  const materialized = items.length ? items : [{ title: empty[0], text: empty[1] }];
  for (const item of materialized) {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = item.title;
    const span = document.createElement("span");
    span.textContent = item.text;
    li.append(strong, span);
    node.appendChild(li);
  }
}

function filterRegistryEntries(entries) {
  const search = ($("#registry-search")?.value || "").trim().toLowerCase();
  const status = $("#registry-status-filter")?.value || "all";
  const continuity = $("#registry-continuity-filter")?.value || "all";
  return entries.filter((entry) => {
    const haystack = [
      entry.authority_ref,
      entryProtectedResource(entry),
      entry.governed_action,
      entry.continuity_posture,
      entry.escalation_threshold,
      entry.semantic_integrity_posture,
      entry.replay_readiness,
    ]
      .join(" ")
      .toLowerCase();
    if (search && !haystack.includes(search)) return false;
    if (status !== "all" && entry.status !== status) return false;
    if (continuity === "revalidation" && !entry.continuity_posture.includes("revalidation")) return false;
    if (continuity === "revocation" && !entry.continuity_posture.includes("revocation")) return false;
    if (continuity === "review" && !entry.continuity_posture.includes("review recommended")) return false;
    return true;
  });
}

function registryMetric(label, value) {
  const metric = document.createElement("div");
  metric.className = "registry-metric";
  const labelNode = document.createElement("span");
  labelNode.textContent = label;
  const valueNode = document.createElement("strong");
  valueNode.textContent = value;
  metric.append(labelNode, valueNode);
  return metric;
}

function authorityRegistryCard(entry) {
  const coherence = authorityCoherenceProjection(entry);
  const registry = loadBundleRegistry();
  const posture = authorityCardPosture(entry, registry, coherence);
  const article = document.createElement("article");
  article.className = `authority-card ${posture.classes.join(" ")}`;

  const header = document.createElement("div");
  header.className = "authority-card-header";
  const titleBlock = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = entry.authority_ref;
  const subtitle = document.createElement("p");
  subtitle.textContent = `${entryProtectedResource(entry)} | ${entry.governed_action}`;
  titleBlock.append(title, subtitle);
  const status = document.createElement("span");
  status.className = `status-badge ${entry.status}`;
  status.textContent = posture.label;
  header.append(titleBlock, status);

  const coherenceRow = document.createElement("div");
  coherenceRow.className = "authority-coherence-row";
  coherenceRow.append(
    coherenceChip(coherence.label, coherence.severity),
    ...coherence.freshness.slice(0, 3).map((item) => coherenceChip(`${item.label}: ${freshnessLabel(item)}`, item.freshness_posture === "fresh" ? item.severity : item.freshness_posture)),
  );

  const meta = document.createElement("dl");
  meta.className = "authority-meta";
  appendMeta(meta, "Last event", latestLifecycleText(entry));
  appendMeta(meta, "Continuity", entry.continuity_posture);
  appendMeta(meta, "Replay", entry.replay_readiness || (entry.publication_receipt?.receipt_hash ? "receipt available" : "receipt pending"));
  appendMeta(meta, "Escalation", entry.escalation_threshold);
  appendMeta(meta, "Diagnostics", diagnosticRollupSummary(entry.diagnostic_summary));
  appendMeta(meta, "Evidence", entry.latest_receipt_hash ? `receipt ${shortHash(entry.latest_receipt_hash)}` : entry.latest_bundle_hash ? `bundle ${shortHash(entry.latest_bundle_hash)}` : "receipt pending");

  const timeline = document.createElement("ol");
  timeline.className = "lifecycle-timeline";
  for (const event of registryLifecycleEvents(entry)) {
    const item = document.createElement("li");
    item.className = `timeline-event ${timelineEventSeverity(event, entry)}`;
    const eventName = document.createElement("strong");
    eventName.textContent = formatLabel(lifecycleEventType(event));
    const eventTime = document.createElement("time");
    eventTime.textContent = formatDateTime(event.timestamp);
    const eventDetail = document.createElement("span");
    eventDetail.textContent = shortHash(lifecycleEventHash(event));
    item.append(eventName, eventTime, eventDetail);
    timeline.appendChild(item);
  }

  const relationship = document.createElement("div");
  relationship.className = "authority-relationship";
  const relationshipTitle = document.createElement("strong");
  relationshipTitle.textContent = "Lineage";
  const relationshipText = document.createElement("span");
  relationshipText.textContent = lineageChainText(entry, registry);
  relationship.append(relationshipTitle, relationshipText);

  const actions = document.createElement("div");
  actions.className = "authority-actions";
  for (const action of [
    ["view-bundle", "View bundle"],
    ["open-preview", "Open impact view"],
    ["open-diff", "Open diff"],
    ["export", "Export bundle"],
    ["view-receipt", "View receipt"],
    ["supersede", "Supersede"],
    ["revoke", "Revoke"],
    ["view-lineage", "View lineage"],
  ]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tertiary-action";
    button.dataset.registryAction = action[0];
    button.dataset.authorityRef = entry.authority_ref;
    button.textContent = action[1];
    actions.appendChild(button);
  }

  article.append(header, coherenceRow, meta, relationship, timeline, actions);
  return article;
}

function authorityCardPosture(entry, registry, coherence) {
  const classes = [];
  const familyEntries = (registry.authorities || []).filter((item) => authorityFamily(item.authority_ref) === authorityFamily(entry.authority_ref));
  const active = entry.status === "registered" && !entry.superseded_by && !familyEntries.some((item) => item.supersedes === entry.authority_ref && item.status === "registered");
  if (active) classes.push("active-authority");
  if (entry.status === "superseded") classes.push("is-superseded");
  if (entry.status === "revoked") classes.push("is-revoked");
  if (coherence.severity === "continuity_risk") classes.push("has-continuity-risk");
  if (coherence.severity === "replay_risk") classes.push("has-replay-risk");
  return {
    classes,
    label: active ? "Active authority" : formatLabel(entry.status),
  };
}

function latestLifecycleText(entry) {
  const events = registryLifecycleEvents(entry);
  const latest = [...events].sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0))[0];
  if (!latest) return "not recorded";
  return `${formatLabel(lifecycleEventType(latest))} ${relativeTime(latest.timestamp)}`;
}

function timelineEventSeverity(event, entry) {
  const type = lifecycleEventType(event);
  if (type === "revoked") return "critical";
  if (type === "superseded" || entry.status === "superseded") return "continuity_risk";
  if (type === "exported" || type === "registered") return "healthy";
  return "info";
}

function lineageChainText(entry, registry) {
  const family = authorityFamily(entry.authority_ref);
  const versions = (registry.authorities || [])
    .filter((item) => authorityFamily(item.authority_ref) === family)
    .sort((a, b) => versionSortValue(a.authority_version || authorityVersionFromRef(a.authority_ref)) - versionSortValue(b.authority_version || authorityVersionFromRef(b.authority_ref)))
    .map((item) => {
      const version = item.authority_version || authorityVersionFromRef(item.authority_ref);
      const suffix = item.status === "registered" && !item.superseded_by ? " active" : item.status === "revoked" ? " revoked" : item.status === "superseded" ? " superseded" : "";
      return `${version}${suffix ? ` (${suffix.trim()})` : ""}`;
    });
  return versions.length ? versions.join(" -> ") : relationshipSummary(entry);
}

function versionSortValue(version) {
  return String(version || "0")
    .split(".")
    .reduce((total, part, index) => total + (Number.parseInt(part, 10) || 0) / 100 ** index, 0);
}

function relationshipSummary(entry) {
  if (entry.status === "revoked") {
    return "This authority is revoked locally. Resumed execution should be reviewed against revocation posture.";
  }
  if (entry.status === "superseded") {
    return `This authority has been superseded by ${entry.superseded_by || "a successor authority"}. Review continuity before relying on resumed work.`;
  }
  return "This authority is the active local lifecycle record for its authority reference.";
}

function coherenceChip(text, posture) {
  const chip = document.createElement("span");
  chip.className = `coherence-chip ${posture || "healthy"}`;
  chip.textContent = text;
  return chip;
}

function freshnessLabel(item) {
  if (item.freshness_posture === "invalidated") return "Invalidated";
  if (item.freshness_posture === "stale") return "Stale";
  if (item.severity === "continuity_risk") return "Warning";
  if (item.severity === "replay_risk") return "Replay Risk";
  return "Valid";
}

function appendMeta(list, label, value) {
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = label;
  dd.textContent = value || "none";
  list.append(dt, dd);
}

function renderBundleDetail(entry, mode = "summary") {
  const detail = $("#bundle-detail");
  detail.innerHTML = "";
  if (!entry) {
    const title = document.createElement("h3");
    title.textContent = "Registry detail";
    const empty = document.createElement("p");
    empty.className = "quiet";
    empty.textContent = "Register an authority to inspect lifecycle, continuity posture, replay readiness, and lineage.";
    detail.append(title, empty);
    return;
  }

  if (mode === "summary") {
    renderRegistryDetailSummary(detail, entry);
    return;
  }

  const title = document.createElement("h3");
  title.textContent = mode === "lineage"
    ? "Lineage"
    : mode === "diff"
      ? "Authority diff"
      : mode === "receipt"
        ? "Publication receipt"
        : "Authority bundle";
  const text = document.createElement("p");
  text.className = "quiet";
  text.textContent = `${entry.authority_ref} | ${formatLabel(entry.status)}`;
  const summary = document.createElement("div");
  summary.className = "technical-summary";
  summary.append(
    registryDetailMetric("Lifecycle", formatLabel(entry.status), latestLifecycleText(entry)),
    registryDetailMetric("Replay", entry.publication_receipt ? "receipt present" : "receipt missing", entry.publication_receipt?.receipt_hash ? shortHash(entry.publication_receipt.receipt_hash) : "No receipt evidence"),
    registryDetailMetric("Continuity", entry.continuity_posture || "review recommended", entry.superseded_by ? `Superseded by ${entry.superseded_by}` : relationshipSummary(entry)),
  );
  const details = document.createElement("details");
  details.className = "technical-details";
  const detailsSummary = document.createElement("summary");
  detailsSummary.textContent = "Technical details";
  const body = document.createElement("pre");
  body.className = "json-view";
  if (mode === "lineage") {
    body.textContent = JSON.stringify(
      {
        entry: registryEntrySummary(entry),
        lifecycle_events: registryLifecycleEvents(entry),
        lineage: entry.lineage,
        immutable_inputs: entry.immutable_inputs,
        diagnostic_rollup: entry.diagnostic_summary,
      },
      null,
      2,
    );
  } else if (mode === "receipt") {
    body.textContent = entry.publication_receipt
      ? JSON.stringify(entry.publication_receipt, null, 2)
      : "No publication_receipt.v1 artifact is attached to this registry entry.";
  } else if (mode === "diff") {
    body.textContent = JSON.stringify(
      {
        semantic_authority_diff: entry.artifacts?.semantic_authority_diff || entry.semantic_authority_diff || null,
        semantic_lifecycle_enforcement_projection: entry.artifacts?.semantic_lifecycle_enforcement_projection || entry.semantic_lifecycle_enforcement_projection || null,
        semantic_diff_summary: entry.semantic_diff_summary || null,
        authority_diff_impact: entry.artifacts?.authority_diff_impact || null,
      },
      null,
      2,
    );
  } else {
    body.textContent = JSON.stringify(
      {
        entry: registryEntrySummary(entry),
        lifecycle_events: registryLifecycleEvents(entry),
        publication_receipt: entry.publication_receipt || null,
        diagnostic_rollup: entry.diagnostic_summary || null,
        bundle: entry.bundle,
      },
      null,
      2,
    );
  }
  details.append(detailsSummary, body);
  detail.append(title, text, summary, details);
}

function renderRegistryDetailSummary(detail, entry) {
  const summary = registryOperationalSummary(entry);
  const coherence = authorityCoherenceProjection(entry);
  const shell = document.createElement("div");
  shell.className = "registry-detail-shell";
  const header = document.createElement("div");
  header.className = "registry-detail-summary";
  const titleBlock = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = summary.authority_ref;
  const subtitle = document.createElement("p");
  subtitle.textContent = `${summary.protected_resource || entryProtectedResource(entry)} | ${summary.governed_action || entry.governed_action}`;
  titleBlock.append(title, subtitle);
  const status = document.createElement("span");
  status.className = `status-badge ${entry.status}`;
  status.textContent = formatLabel(summary.lifecycle?.status || entry.status);
  header.append(titleBlock, status);

  const metrics = document.createElement("div");
  metrics.className = "registry-detail-grid";
  metrics.append(
    registryDetailMetric("Lifecycle", formatLabel(entry.status), latestLifecycleText(entry)),
    registryDetailMetric("Replay", replayReadinessLabel(summary.replay_readiness), summary.replay_readiness?.receipt_present ? "Receipt evidence present" : "Receipt evidence pending"),
    registryDetailMetric("Continuity", entry.continuity_posture || "review recommended", coherence.severity === "continuity_risk" ? "Continuity controls active" : "Continuity posture recorded"),
    registryDetailMetric("Coherence", coherence.label, freshnessLabel(coherence.freshness[0] || {})),
  );
  const scope = registryScopeStrip(coherence.causality);
  const causality = continuityCausalityPanel(coherence.causality);

  const freshness = document.createElement("div");
  freshness.className = "projection-freshness-grid";
  for (const item of coherence.freshness) {
    freshness.appendChild(projectionFreshnessCard(item));
  }

  const freshnessTimeline = document.createElement("ol");
  freshnessTimeline.className = "freshness-timeline";
  for (const item of coherence.freshness) {
    const row = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = item.label;
    row.append(strong, projectionStatusDetail(item));
    freshnessTimeline.appendChild(row);
  }

  const meaning = document.createElement("ul");
  meaning.className = "operations-list";
  const meaningItems = summary.governance_meaning?.length ? summary.governance_meaning : ["No governance meaning has been registered for this authority yet."];
  for (const item of meaningItems) {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = item;
    li.appendChild(strong);
    meaning.appendChild(li);
  }

  const replay = document.createElement("dl");
  replay.className = "compact-dl";
  renderDefinitionValuesInto(replay, {
    Receipt: summary.replay_readiness?.receipt_present ? "present" : "missing",
    "Semantic hashes": summary.replay_readiness?.semantic_hashes_aligned ? "aligned" : "incomplete",
    Lineage: summary.replay_readiness?.lineage_complete ? "complete" : "incomplete",
    Manifest: summary.replay_readiness?.manifest_aligned ? "aligned" : "incomplete",
  });

  const drift = document.createElement("ul");
  drift.className = "operations-list";
  const driftItems = summary.drift_summary?.length ? summary.drift_summary : [{ drift_type: "No continuity drift detected", summary: "No lineage drift currently requires attention." }];
  for (const item of driftItems) {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = formatLabel(item.drift_type);
    const span = document.createElement("span");
    span.textContent = item.summary || (item.from || item.to ? `${item.from || "none"} -> ${item.to || "none"}` : "");
    li.append(strong, span);
    drift.appendChild(li);
  }

  const timeline = document.createElement("ol");
  timeline.className = "registry-detail-timeline";
  for (const event of summary.lifecycle?.events || registryLifecycleEvents(entry)) {
    const item = document.createElement("li");
    item.className = `timeline-event ${timelineEventSeverity(event, entry)}`;
    const eventName = document.createElement("strong");
    eventName.textContent = formatLabel(lifecycleEventType(event));
    const eventDetail = document.createElement("span");
    eventDetail.textContent = `${formatDateTime(event.timestamp)} | ${lifecycleEventDetail(event)}`;
    const evidence = document.createElement("code");
    evidence.textContent = lifecycleEvidencePosture(event);
    item.append(eventName, eventDetail, evidence);
    timeline.appendChild(item);
  }
  if (!timeline.children.length) {
    const item = document.createElement("li");
    const eventName = document.createElement("strong");
    eventName.textContent = "No lifecycle events";
    const eventDetail = document.createElement("span");
    eventDetail.textContent = "Register this authority to create append-only lifecycle history.";
    const evidence = document.createElement("code");
    evidence.textContent = "no evidence";
    item.append(eventName, eventDetail, evidence);
    timeline.appendChild(item);
  }

  const graph = renderRelationshipGraph(summary.relationship_graph);
  const semanticDiffShell = document.createElement("div");
  semanticDiffShell.className = "registry-semantic-diff-summary";
  semanticDiffShell.dataset.semanticDiffSummaryFor = entry.authority_ref;
  semanticDiffShell.appendChild(semanticDiffSummaryView(entry.semantic_diff_summary || entry.artifacts?.semantic_authority_diff || null));
  const lifecycleProjectionShell = document.createElement("div");
  lifecycleProjectionShell.className = "registry-lifecycle-enforcement-summary";
  lifecycleProjectionShell.dataset.lifecycleEnforcementFor = entry.authority_ref;
  lifecycleProjectionShell.appendChild(lifecycleEnforcementSummaryView(entry.semantic_lifecycle_enforcement_projection || entry.artifacts?.semantic_lifecycle_enforcement_projection || null));
  const blocks = document.createElement("div");
  blocks.className = "registry-detail-blocks";
  blocks.append(
    registryDetailBlock("Identity", identitySummary(entry, summary)),
    registryDetailBlock("What Changed Since Previous Version", semanticDiffShell, "wide"),
    registryDetailBlock("Lifecycle Enforcement Consequences", lifecycleProjectionShell, "wide"),
    registryDetailBlock("Why This Posture Exists", causality, "wide"),
    registryDetailBlock("Lifecycle", timeline, "wide"),
    registryDetailBlock("Continuity", freshnessTimeline, "wide"),
    registryDetailBlock("Replay", replay),
    registryDetailBlock("Drift", drift),
    registryDetailBlock("Governance Meaning", meaning),
    registryDetailBlock("Lineage", graph),
    registryDetailBlock("State Validity", freshness),
  );

  shell.append(
    header,
    metrics,
    scope,
    blocks,
  );
  detail.appendChild(shell);
  refreshRegistryDetailSemanticDiff(entry);
}

function registryDetailBlock(title, content, variant = "") {
  const block = document.createElement("section");
  block.className = `registry-detail-block ${variant}`.trim();
  const heading = document.createElement("h3");
  heading.textContent = title;
  block.appendChild(heading);
  block.appendChild(content);
  return block;
}

function registryScopeStrip(causality) {
  const strip = document.createElement("div");
  strip.className = "registry-scope-strip";
  const scopes = causality?.scopes || {};
  for (const [label, value] of Object.entries({
    "Current Draft": scopes.current_draft || "pending review",
    "Historical Authority": scopes.historical_authority || "not registered",
    "Registry Lineage": scopes.registry_lineage || "lineage pending",
    "Replay Evidence": scopes.replay_evidence || "receipt pending",
  })) {
    const item = document.createElement("div");
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    item.append(span, strong);
    strip.appendChild(item);
  }
  return strip;
}

function continuityCausalityPanel(causality) {
  const panel = document.createElement("div");
  panel.className = `continuity-causality ${causality?.posture || "healthy"}`;
  const reason = document.createElement("p");
  reason.className = "causality-reason";
  const reasonLabel = document.createElement("strong");
  reasonLabel.textContent = "Reason";
  const reasonText = document.createElement("span");
  reasonText.textContent = causality?.reason || "No continuity-sensitive posture is indicated by the current local registry state.";
  reason.append(reasonLabel, reasonText);
  const impact = document.createElement("p");
  impact.className = "causality-impact";
  const impactLabel = document.createElement("strong");
  impactLabel.textContent = "Operational impact";
  const impactText = document.createElement("span");
  impactText.textContent = causality?.impact || "No additional continuity action is indicated.";
  impact.append(impactLabel, impactText);
  const events = document.createElement("ol");
  events.className = "causality-events";
  const contributing = causality?.contributing_events?.length ? causality.contributing_events : [{ type: "No contributing events", detail: "Lifecycle history has not created a continuity concern.", timestamp: null }];
  for (const event of contributing.slice(-6)) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = event.type;
    const detail = document.createElement("span");
    detail.textContent = `${event.timestamp ? `${formatDateTime(event.timestamp)} | ` : ""}${event.detail}`;
    item.append(title, detail);
    events.appendChild(item);
  }
  panel.append(reason, impact, events);
  return panel;
}

function identitySummary(entry, summary) {
  const list = document.createElement("dl");
  list.className = "compact-dl";
  renderDefinitionValuesInto(list, {
    Authority: summary.authority_ref || entry.authority_ref,
    Resource: summary.protected_resource || entryProtectedResource(entry),
    Action: summary.governed_action || entry.governed_action,
    Lineage: lineageChainText(entry, loadBundleRegistry()),
  });
  return list;
}

function projectionFreshnessCard(item) {
  const card = document.createElement("article");
  card.className = `projection-freshness-card ${item.freshness_posture} ${item.severity}`;
  const label = document.createElement("span");
  label.textContent = item.label;
  const value = document.createElement("strong");
  value.textContent = projectionStatusLabel(item);
  const generated = document.createElement("small");
  generated.textContent = `Last generated: ${lastGeneratedLabel(item)}`;
  card.append(label, value, generated);
  return card;
}

function projectionStatusLabel(item) {
  if (item.freshness_posture === "invalidated") return "Invalidated";
  if (item.freshness_posture === "stale") return "Stale";
  if (item.freshness_posture === "fresh") return "Valid";
  return freshnessLabel(item);
}

function lastGeneratedLabel(item) {
  return item.generated_at ? relativeTime(item.generated_at) : "current workspace state";
}

function projectionStatusDetail(item) {
  const detail = document.createElement("dl");
  detail.className = "freshness-status";
  renderDefinitionValuesInto(detail, {
    "Projection status": projectionStatusLabel(item),
    "Last generated": lastGeneratedLabel(item),
  });
  if (item.freshness_posture === "invalidated" || item.severity === "replay_risk" || item.severity === "continuity_risk") {
    const note = document.createElement("p");
    note.textContent = freshnessTimelineText(item);
    detail.appendChild(note);
  }
  return detail;
}

function freshnessTimelineText(item) {
  if (item.freshness_posture === "invalidated") {
    return "Invalidated after draft modification; impact review is required before export.";
  }
  if (item.severity === "continuity_risk") {
    return "Refreshed after supersession or revocation posture changed.";
  }
  if (item.severity === "replay_risk") {
    return "Replay posture is incomplete until receipt evidence is present.";
  }
  return "Projection is valid for the current registry state.";
}

function replayReadinessLabel(replay) {
  if (!replay) return "receipt pending";
  return replay.receipt_present && replay.semantic_hashes_aligned && replay.lineage_complete && replay.manifest_aligned
    ? "replay ready"
    : replay.receipt_present
      ? "receipt present"
      : "receipt pending";
}

function renderDefinitionValuesInto(node, values) {
  node.innerHTML = "";
  for (const [label, value] of Object.entries(values)) {
    const wrapper = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    wrapper.append(dt, dd);
    node.appendChild(wrapper);
  }
}

function renderRelationshipGraph(graph) {
  const list = document.createElement("ol");
  list.className = "relationship-graph";
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  if (!nodes.length) {
    const item = document.createElement("li");
    item.textContent = "No lineage relationships recorded yet.";
    list.appendChild(item);
    return list;
  }
  for (const node of [...nodes].sort((a, b) => versionSortValue(a.authority_version || authorityVersionFromRef(a.authority_ref)) - versionSortValue(b.authority_version || authorityVersionFromRef(b.authority_ref)))) {
    const item = document.createElement("li");
    item.className = `relationship-node ${node.status || "draft"}`;
    const label = document.createElement("strong");
    label.textContent = authorityVersionFromRef(node.authority_ref);
    const outgoing = edges.filter((edge) => edge.from === node.authority_ref);
    const span = document.createElement("span");
    span.textContent = outgoing.length ? `continues to ${outgoing.map((edge) => authorityVersionFromRef(edge.to)).join(", ")}` : `${formatLabel(node.status || "current")} lineage node`;
    item.append(label, span);
    list.appendChild(item);
  }
  return list;
}

function registryDetailMetric(label, value, note = "") {
  const node = document.createElement("div");
  node.className = "registry-detail-metric";
  const labelNode = document.createElement("span");
  labelNode.textContent = label;
  const valueNode = document.createElement("strong");
  valueNode.textContent = value || "none";
  node.append(labelNode, valueNode);
  if (note) {
    const noteNode = document.createElement("small");
    noteNode.textContent = note;
    node.appendChild(noteNode);
  }
  return node;
}

function lifecycleEvidencePosture(event) {
  const hashes = event.artifact_hashes || {};
  if (hashes.receipt_hash) return `receipt ${shortHash(hashes.receipt_hash)}`;
  if (hashes.bundle_hash) return `bundle ${shortHash(hashes.bundle_hash)}`;
  if (event.hash) return `hash ${shortHash(event.hash)}`;
  return "evidence pending";
}

function registryEntrySummary(entry) {
  return {
    schema_version: entry.schema_version,
    authority_ref: entry.authority_ref,
    authority_version: entry.authority_version || authorityVersionFromRef(entry.authority_ref),
    status: entry.status,
    protected_resource: entryProtectedResource(entry),
    governed_action: entry.governed_action,
    continuity_posture: entry.continuity_posture,
    replay_readiness: entry.replay_readiness || (entry.publication_receipt?.receipt_hash ? "receipt available" : "receipt pending"),
    latest_bundle_hash: entry.latest_bundle_hash || entry.contract_hash,
    latest_receipt_hash: entry.latest_receipt_hash || entry.publication_receipt?.receipt_hash || null,
    lifecycle_event_ids: entry.lifecycle_event_ids || registryLifecycleEvents(entry).map((event) => event.event_id || `${lifecycleEventType(event)}:${event.timestamp}`),
    supersedes: entry.supersedes || null,
    superseded_by: entry.superseded_by || null,
    created_at: entry.created_at || entry.published_at || null,
    updated_at: entry.updated_at || entry.published_at || null,
  };
}

function authorityArtifactFromEntry(entry) {
  if (!entry) return null;
  return entry.artifacts?.authority_contract
    || entry.bundle?.authority_artifact
    || entry.bundle?.authority_contract
    || entry.bundle?.contract
    || null;
}

function authorityArtifactFromPayload(payload) {
  if (!payload) return null;
  return payload.authority_contract
    || payload.authority_bundle?.authority_artifact
    || payload.authority_bundle?.authority_contract
    || payload.authority_bundle?.contract
    || null;
}

function previousRegistryEntryForAuthority(authorityRef, currentEntry = null, registry = loadBundleRegistry()) {
  const family = authorityFamily(authorityRef);
  if (currentEntry?.supersedes) {
    const explicit = registry.authorities.find((entry) => entry.authority_ref === currentEntry.supersedes);
    if (explicit) return explicit;
  }
  const targetVersion = versionSortValue(authorityVersionFromRef(authorityRef));
  const candidates = (registry.authorities || [])
    .filter((entry) => entry.authority_ref !== authorityRef && authorityFamily(entry.authority_ref) === family)
    .filter((entry) => versionSortValue(entry.authority_version || authorityVersionFromRef(entry.authority_ref)) <= targetVersion)
    .sort((a, b) => versionSortValue(b.authority_version || authorityVersionFromRef(b.authority_ref)) - versionSortValue(a.authority_version || authorityVersionFromRef(a.authority_ref)));
  return candidates[0] || null;
}

async function fetchSemanticAuthorityDiff(previousAuthority, currentAuthority) {
  const response = await fetch("/api/semantic-diff", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      previous_authority: previousAuthority,
      current_authority: currentAuthority,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Unable to generate semantic authority diff.");
  }
  return payload;
}

async function fetchSemanticLifecycleEnforcementProjection(diff) {
  const response = await fetch("/api/semantic-lifecycle-enforcement", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      semantic_authority_diff: diff,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Unable to generate semantic lifecycle enforcement projection.");
  }
  if (payload.schema_version !== "semantic_lifecycle_enforcement_projection.v1") {
    throw new Error("semantic lifecycle enforcement projection response was incomplete.");
  }
  return payload;
}

function semanticDiffRegistrySummary(diff) {
  if (!diff || diff.schema_version !== "semantic_authority_diff.v1") return null;
  const changes = diff.semantic_changes || [];
  const guard = diff.guard_compatibility_projection || {};
  const lifecycle = diff.semantic_lifecycle_enforcement_projection || null;
  return {
    schema_version: "semantic_diff_summary.v1",
    previous_authority_ref: diff.previous_authority_ref,
    current_authority_ref: diff.current_authority_ref,
    change_count: changes.length,
    change_classes: [...new Set(changes.map((change) => change.change_class).filter(Boolean))].sort(),
    highest_severity: semanticDiffHighestSeverity(changes),
    operational_impact: diff.operational_impact_narratives || [],
    replay_revalidation_required: semanticDiffRequiresRevalidation(diff),
    replay_compatibility_warnings: diff.replay_compatibility_warnings || [],
    guard_compatibility_posture: guard.compatibility_posture || "no_new_guard_obligations",
    guard_enforcement_changes: guard.new_enforcement_obligations || [],
    unsafe_now: lifecycle?.what_becomes_unsafe_now || [],
    execution_admissibility_projection: lifecycle?.execution_admissibility_projection || null,
    replay_continuity_projection: lifecycle?.replay_continuity_projection || null,
  };
}

function semanticDiffHighestSeverity(changes) {
  const rank = {
    informational: 1,
    moderate: 2,
    "high-impact": 3,
    "breaking-governance-change": 4,
  };
  return (changes || []).reduce((current, change) => {
    const severity = change.severity || "informational";
    return (rank[severity] || 0) > (rank[current] || 0) ? severity : current;
  }, "informational");
}

function semanticDiffRequiresRevalidation(diff) {
  const changes = diff?.semantic_changes || [];
  return changes.some((change) => (
    change.change_class === "continuity_change"
    || String(change.semantic_path || "").startsWith("continuity.")
    || (change.replay_compatibility_warnings || []).some((warning) => String(warning).toLowerCase().includes("resumed execution"))
  ));
}

function semanticDiffMatchesCurrentPayload(diff, payload) {
  if (!diff || !payload?.authority_bundle) return false;
  return diff.current_authority_ref === payload.authority_bundle.authority_ref;
}

function semanticDiffList(items, fallback) {
  const list = document.createElement("ul");
  list.className = "semantic-list";
  const values = items?.length ? items : [fallback];
  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = value;
    list.appendChild(item);
  }
  return list;
}

function semanticDiffSummaryView(diffOrSummary, options = {}) {
  const diff = diffOrSummary?.schema_version === "semantic_authority_diff.v1" ? diffOrSummary : null;
  const summary = diff ? semanticDiffRegistrySummary(diff) : diffOrSummary;
  const panel = document.createElement("div");
  panel.className = "semantic-diff-summary";
  if (!summary) {
    const empty = document.createElement("p");
    empty.className = "quiet";
    empty.textContent = options.emptyText || "No previous authority version is available for semantic comparison.";
    panel.appendChild(empty);
    return panel;
  }
  const header = document.createElement("div");
  header.className = "semantic-diff-header";
  const title = document.createElement("strong");
  title.textContent = "What changed since previous version";
  const chip = document.createElement("span");
  chip.className = `diff-severity ${summary.highest_severity || "informational"}`;
  chip.textContent = formatLabel(summary.highest_severity || "informational");
  header.append(title, chip);
  const refs = document.createElement("p");
  refs.className = "quiet";
  refs.textContent = `${summary.previous_authority_ref || "previous authority"} -> ${summary.current_authority_ref || "current authority"}`;
  const classes = document.createElement("div");
  classes.className = "semantic-change-classes";
  for (const changeClass of summary.change_classes || []) {
    const classChip = document.createElement("span");
    classChip.textContent = formatLabel(changeClass);
    classes.appendChild(classChip);
  }
  const impact = semanticDiffList(
    summary.operational_impact,
    summary.change_count ? "Semantic changes detected; no additional operational narrative was emitted." : "No operational semantic changes detected.",
  );
  panel.append(header, refs, classes, impact);
  return panel;
}

function renderSemanticAuthorityDiff(node, diff, fallback = "No previous authority version is available for semantic comparison.") {
  if (!node) return;
  node.innerHTML = "";
  if (!diff) {
    const empty = document.createElement("p");
    empty.className = "quiet";
    empty.textContent = fallback;
    node.appendChild(empty);
    return;
  }
  const version = document.createElement("span");
  version.className = "artifact-pill muted";
  version.textContent = diff.schema_version;
  const summary = semanticDiffSummaryView(diff);
  const changes = document.createElement("ol");
  changes.className = "semantic-change-list";
  for (const change of diff.semantic_changes || []) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = `${formatLabel(change.change_class)} - ${change.semantic_path}`;
    const detail = document.createElement("span");
    detail.textContent = (change.operational_impact || []).join(" ");
    item.append(title, detail);
    changes.appendChild(item);
  }
  if (!changes.children.length) {
    const item = document.createElement("li");
    item.textContent = "No operational semantic change detected between these authority meanings.";
    changes.appendChild(item);
  }
  node.append(version, summary, changes);
}

function renderSemanticDiffLists(diff, lifecycleProjection = null) {
  const replayNode = $("#change-replay-continuity");
  const guardNode = $("#change-guard-compatibility");
  const unsafeNode = $("#change-unsafe-now");
  const admissibilityNode = $("#change-admissibility-projection");
  if (replayNode) {
    const replayProjection = lifecycleProjection?.replay_continuity_projection || null;
    renderList(
      "#change-replay-continuity",
      replayProjection
        ? [
            `Replay continuity posture: ${formatLabel(replayProjection.posture)}.`,
            replayProjection.existing_workflows_need_revalidation
              ? "Existing workflows need governance revalidation before relying on resumed execution continuity."
              : "Existing workflows do not require new revalidation from this projection.",
            ...(replayProjection.observations || []),
          ]
        : diff
        ? [
            semanticDiffRequiresRevalidation(diff)
              ? "Existing resumed workflows should require governance revalidation against the new authority posture."
              : "No resumed-workflow revalidation change was derived from this semantic diff.",
            ...(diff.replay_compatibility_warnings || []),
          ]
        : ["Replay continuity impact appears after a previous authority version is available."],
    );
  }
  if (guardNode) {
    const guard = lifecycleProjection?.guard_policy_projection || diff?.guard_compatibility_projection || {};
    const guardChanges = guard.enforcement_changes || guard.new_enforcement_obligations || [];
    renderList(
      "#change-guard-compatibility",
      lifecycleProjection || diff
        ? (guardChanges.length
            ? guardChanges
            : ["No new Guard enforcement obligations are derived. Ledger does not call Guard."])
        : ["Guard compatibility projection appears after semantic diff generation."],
    );
  }
  if (unsafeNode) {
    renderList(
      "#change-unsafe-now",
      lifecycleProjection
        ? ((lifecycleProjection.what_becomes_unsafe_now || []).map((item) => item.summary))
        : ["Unsafe-governance observations appear after lifecycle enforcement projection generation."],
    );
  }
  if (admissibilityNode) {
    const projection = lifecycleProjection?.execution_admissibility_projection;
    renderList(
      "#change-admissibility-projection",
      projection
        ? [
            `Projection posture: ${formatLabel(projection.projection_posture)}.`,
            ...(projection.admissibility_observations || []),
            "Projection only. Runtime admissibility remains Guard/Cloud-owned.",
          ]
        : ["Execution admissibility projection appears after semantic lifecycle analysis."],
    );
  }
}

function lifecycleEnforcementSummaryView(projection) {
  const panel = document.createElement("div");
  panel.className = "lifecycle-enforcement-summary";
  if (!projection) {
    const empty = document.createElement("p");
    empty.className = "quiet";
    empty.textContent = "No semantic lifecycle enforcement projection has been generated for this authority relationship.";
    panel.appendChild(empty);
    return panel;
  }
  const headline = document.createElement("div");
  headline.className = "semantic-diff-header";
  const title = document.createElement("strong");
  title.textContent = "Semantic change -> operational consequence -> continuity impact -> admissibility projection";
  const chip = document.createElement("span");
  chip.className = `diff-severity ${projection.execution_admissibility_projection?.projection_posture || "informational"}`;
  chip.textContent = formatLabel(projection.execution_admissibility_projection?.projection_posture || "unchanged");
  headline.append(title, chip);
  const replay = document.createElement("p");
  replay.className = "quiet";
  replay.textContent = `Replay continuity: ${formatLabel(projection.replay_continuity_projection?.posture || "stable")}.`;
  const unsafe = semanticDiffList(
    (projection.what_becomes_unsafe_now || []).map((item) => item.summary),
    "No unsafe-governance observations were derived from this semantic diff.",
  );
  panel.append(headline, replay, unsafe);
  return panel;
}

async function refreshChangeReviewSemanticDiff(payload = currentArtifacts) {
  const node = $("#change-semantic-diff");
  if (!payload?.authority_bundle || !node) return;
  const token = ++semanticDiffRequestToken;
  const currentAuthority = authorityArtifactFromPayload(payload);
  const registryEntry = findRegistryEntry(payload.authority_bundle.authority_ref);
  const previousEntry = previousRegistryEntryForAuthority(payload.authority_bundle.authority_ref, registryEntry);
  const previousAuthority = authorityArtifactFromEntry(previousEntry);
  if (!previousAuthority || !currentAuthority) {
    currentSemanticAuthorityDiff = null;
    currentLifecycleEnforcementProjection = null;
    renderSemanticAuthorityDiff(node, null);
    renderSemanticDiffLists(null, null);
    return;
  }
  renderSemanticAuthorityDiff(node, null, "Generating semantic_authority_diff.v1 from Ledger semantic modules...");
  try {
    const diff = await fetchSemanticAuthorityDiff(previousAuthority, currentAuthority);
    if (token !== semanticDiffRequestToken) return;
    const lifecycleProjection = await fetchSemanticLifecycleEnforcementProjection(diff);
    if (token !== semanticDiffRequestToken) return;
    diff.semantic_lifecycle_enforcement_projection = lifecycleProjection;
    currentSemanticAuthorityDiff = diff;
    currentLifecycleEnforcementProjection = lifecycleProjection;
    payload.semantic_authority_diff = diff;
    payload.semantic_lifecycle_enforcement_projection = lifecycleProjection;
    renderSemanticAuthorityDiff(node, diff);
    renderSemanticDiffLists(diff, lifecycleProjection);
  } catch (error) {
    if (token !== semanticDiffRequestToken) return;
    currentLifecycleEnforcementProjection = null;
    renderSemanticAuthorityDiff(node, null, error.message);
    renderSemanticDiffLists(null, null);
  }
}

async function refreshRegistryDetailSemanticDiff(entry) {
  const target = document.querySelector(`[data-semantic-diff-summary-for="${entry.authority_ref}"]`);
  const lifecycleTarget = document.querySelector(`[data-lifecycle-enforcement-for="${entry.authority_ref}"]`);
  if (!target) return;
  const currentAuthority = authorityArtifactFromEntry(entry);
  const previousEntry = previousRegistryEntryForAuthority(entry.authority_ref, entry);
  const previousAuthority = authorityArtifactFromEntry(previousEntry);
  if (!currentAuthority || !previousAuthority) {
    target.replaceChildren(semanticDiffSummaryView(entry.semantic_diff_summary || null));
    if (lifecycleTarget) lifecycleTarget.replaceChildren(lifecycleEnforcementSummaryView(entry.semantic_lifecycle_enforcement_projection || null));
    return;
  }
  try {
    const diff = await fetchSemanticAuthorityDiff(previousAuthority, currentAuthority);
    const lifecycleProjection = await fetchSemanticLifecycleEnforcementProjection(diff);
    diff.semantic_lifecycle_enforcement_projection = lifecycleProjection;
    target.replaceChildren(semanticDiffSummaryView(diff));
    if (lifecycleTarget) lifecycleTarget.replaceChildren(lifecycleEnforcementSummaryView(lifecycleProjection));
  } catch (error) {
    const empty = document.createElement("p");
    empty.className = "quiet";
    empty.textContent = error.message;
    target.replaceChildren(empty);
    if (lifecycleTarget) lifecycleTarget.replaceChildren(lifecycleEnforcementSummaryView(null));
  }
}

function findRegistryEntry(authorityRef) {
  return loadBundleRegistry().authorities.find((entry) => entry.authority_ref === authorityRef) || null;
}

function updateRegistryEntry(authorityRef, updater) {
  const registry = loadBundleRegistry();
  registry.authorities = registry.authorities.map((entry) => {
    if (entry.authority_ref !== authorityRef) return entry;
    return updater(entry);
  });
  saveBundleRegistry(registry);
  return registry.authorities.find((entry) => entry.authority_ref === authorityRef) || null;
}

async function handleRegistryAction(event) {
  const button = event.target.closest("[data-registry-action]");
  if (!button) return;
  const entry = findRegistryEntry(button.dataset.authorityRef);
  if (!entry) return;
  const action = button.dataset.registryAction;
  if (action === "view-bundle") {
    renderBundleDetail(entry, "bundle");
  } else if (action === "open-preview") {
    currentArtifacts = entry.artifacts;
    renderArtifacts(currentArtifacts, {
      reviewed: ["reviewed", "exported", "registered", "superseded", "revoked"].includes(entry.status),
      preserveWorkflow: true,
    });
    syncPublicationActions();
    showPage("preview");
  } else if (action === "open-diff") {
    renderBundleDetail(entry, "diff");
    showPage("bundles");
  } else if (action === "export") {
    downloadBundle(entry.bundle);
  } else if (action === "view-receipt") {
    renderBundleDetail(entry, "receipt");
  } else if (action === "supersede") {
    const successor = currentArtifacts?.authority_bundle?.authority_ref;
    const supersededBy = successor && successor !== entry.authority_ref ? successor : "pending successor";
    let semanticDiff = null;
    let lifecycleProjection = null;
    if (successor && successor !== entry.authority_ref) {
      const previousAuthority = authorityArtifactFromEntry(entry);
      const currentAuthority = authorityArtifactFromPayload(currentArtifacts);
      if (previousAuthority && currentAuthority) {
        try {
          semanticDiff = await fetchSemanticAuthorityDiff(previousAuthority, currentAuthority);
          lifecycleProjection = await fetchSemanticLifecycleEnforcementProjection(semanticDiff);
          semanticDiff.semantic_lifecycle_enforcement_projection = lifecycleProjection;
        } catch {
          semanticDiff = null;
          lifecycleProjection = null;
        }
      }
    }
    const semanticDiffSummary = semanticDiffRegistrySummary(semanticDiff);
    const updated = updateRegistryEntry(entry.authority_ref, (item) => ({
      ...item,
      status: "superseded",
      updated_at: new Date().toISOString(),
      superseded_by: item.superseded_by || supersededBy,
      semantic_diff_summary: semanticDiffSummary || item.semantic_diff_summary || null,
      semantic_authority_diff: semanticDiff || item.semantic_authority_diff || null,
      semantic_lifecycle_enforcement_projection: lifecycleProjection || item.semantic_lifecycle_enforcement_projection || null,
      lifecycle_events: appendLifecycleOnce(
        registryLifecycleEvents(item),
        "superseded",
        new Date().toISOString(),
        { bundle_hash: item.latest_bundle_hash || item.contract_hash },
        semanticDiffSummary?.operational_impact?.length
          ? `Superseded by ${item.superseded_by || supersededBy}. ${semanticDiffSummary.operational_impact[0]}`
          : `Superseded by ${item.superseded_by || supersededBy}.`,
        item.authority_ref,
      ),
      artifacts: {
        ...(item.artifacts || {}),
        semantic_authority_diff: semanticDiff || item.artifacts?.semantic_authority_diff || null,
        semantic_lifecycle_enforcement_projection: lifecycleProjection || item.artifacts?.semantic_lifecycle_enforcement_projection || null,
      },
    }));
    renderOperatorGuidance(
      "Authority marked superseded.",
      `${entry.authority_ref} now has a supersession lifecycle event. Review lineage and continuity before resumed execution relies on older posture.`,
    );
    renderBundleDetail(updated, "lineage");
  } else if (action === "revoke") {
    const updated = updateRegistryEntry(entry.authority_ref, (item) => ({
      ...item,
      status: "revoked",
      updated_at: new Date().toISOString(),
      lifecycle_events: appendLifecycleOnce(
        registryLifecycleEvents(item),
        "revoked",
        new Date().toISOString(),
        { bundle_hash: item.latest_bundle_hash || item.contract_hash },
        "Authority marked revoked in the local registry.",
        item.authority_ref,
      ),
    }));
    renderOperatorGuidance(
      "Authority marked revoked.",
      `${entry.authority_ref} is revoked in the local registry. Future review should treat resumed execution under this authority as invalidated posture.`,
    );
    renderBundleDetail(updated, "lineage");
  } else if (action === "view-lineage") {
    renderBundleDetail(entry, "lineage");
  }
}

function buildOutcomeExplorer(preview, bundle) {
  const outcomes = [];
  if (preview.enforcement_behavior?.length) {
    outcomes.push(preview.enforcement_behavior[0]);
  }
  if (preview.lifecycle_implications?.length) {
    outcomes.push(...preview.lifecycle_implications);
  }
  outcomes.push(`Replay evidence will bind to ${bundle.authority_ref} and ${bundle.contract_hash}.`);
  return outcomes;
}

async function exportBundle() {
  if (!currentArtifacts) return;
  if (!workflowState.impactReviewed) {
    renderDiagnostics([
      {
        severity: "warning",
        code: "impact_review_required",
        title: "Generate operational impact before exporting.",
        domain: "publication",
        text: "The authority draft changed after the last reviewed impact.",
        recommendation: "Generate Operational Impact, then export the authority bundle.",
      },
    ]);
    showPage("diagnostics");
    return;
  }
  try {
    const bundle = currentArtifacts.authority_bundle;
    const publishedAt = new Date().toISOString();
    const readiness = readReadinessConfirmations();
    const notes = readPublicationNotes(publishedAt);
    const receipt = await buildPublicationReceipt(bundle, publishedAt, readiness, notes);
    $("#receipt-json").textContent = JSON.stringify(receipt, null, 2);
    pendingRegistration = { receipt, notes };
    workflowTimestamps.exported = publishedAt;
    registerButton.disabled = false;
    $("#status-bundle").textContent = "bundle exported";
    renderOperatorGuidance(
      "Bundle exported with receipt evidence.",
      "Ledger created a publication receipt. Register locally to record the authority lifecycle event.",
    );
    updateWorkflowState({
      draftReady: true,
      impactReviewed: true,
      bundleExported: true,
      receiptGenerated: true,
      authorityRegistered: false,
    });
    renderPublicationProjection(authorityWorkspaceProjection());
    try {
      downloadBundle(bundle);
    } catch (downloadError) {
      renderDiagnostics([
        {
          severity: "warning",
          code: "bundle_download_unavailable",
          title: "Bundle export evidence is ready",
          domain: "publication",
          text: "Ledger generated the publication receipt, but the browser did not complete the file download.",
          recommendation: "Register the authority locally. You can export the bundle again from the registry if the file was not saved.",
          technical_detail: String(downloadError?.message || downloadError || "download failed"),
        },
      ]);
    }
  } catch (error) {
    pendingRegistration = null;
    registerButton.disabled = true;
    $("#release-registration").textContent = "Bundle export did not complete. Authority is not registered locally.";
    $("#receipt-json").textContent = "Publication receipt was not generated for this export.";
    updateWorkflowState({
      bundleExported: false,
      receiptGenerated: false,
      authorityRegistered: false,
    });
    renderDiagnostics([
      {
        severity: "warning",
        code: "publication_evidence_unavailable",
        title: "Publication evidence could not be recorded",
        domain: "publication",
        text: "Ledger could not create the publication receipt for this bundle export.",
        recommendation: operationalReceiptRecommendation(error),
      },
    ]);
    showPage("diagnostics");
  }
}

function registerAuthorityLocally() {
  if (!currentArtifacts) {
    renderDiagnostics([
      {
        severity: "warning",
        code: "publication_evidence_unavailable",
        title: "Authority impact has not been reviewed",
        domain: "publication",
        text: "Review the authority impact before registering an authority lifecycle event.",
        recommendation: "Create or restore a draft, review impact, then export the authority bundle.",
      },
    ]);
    showPage("diagnostics");
    return;
  }
  if (!pendingRegistration) {
    renderDiagnostics([
      {
        severity: "warning",
        code: "publication_evidence_unavailable",
        title: "Publication receipt has not been generated yet",
        domain: "publication",
        text: "The authority bundle must be exported with a receipt before local registration.",
        recommendation: "Export the bundle again, then register the authority locally.",
      },
    ]);
    showPage("diagnostics");
    return;
  }
  const entry = publishCurrentBundleToRegistry(pendingRegistration.receipt, pendingRegistration.notes);
  workflowTimestamps.registered = new Date().toISOString();
  $("#status-bundle").textContent = "registered locally";
  renderOperatorGuidance(
    "Authority registered locally.",
    `${entry.authority_ref} is now visible in the registry with lifecycle lineage and receipt evidence.`,
  );
  registerButton.disabled = true;
  updateWorkflowState({
    draftReady: true,
    impactReviewed: true,
    bundleExported: true,
    receiptGenerated: true,
    authorityRegistered: true,
  });
  renderPublicationProjection(authorityWorkspaceProjection());
  renderBundleDetail(entry, "receipt");
  showPage("bundles");
}

function renderChangeReview(payload, options) {
  options = options || {};
  const status = $("#change-review-status");
  const narrative = $("#change-narrative");
  const operational = $("#change-operational");
  const continuity = $("#change-continuity");
  const replay = $("#change-replay");
  const semanticDiff = $("#change-semantic-diff");
  const executionContext = $("#change-execution-context");
  const lineage = $("#change-lineage");
  if (!status || !narrative || !operational || !continuity || !replay || !executionContext || !lineage) return;
  lineage.innerHTML = "";
  if (!payload?.authority_bundle) {
    status.textContent = "No authority reviewed";
    narrative.querySelector("h3").textContent = "Review a draft or registered authority to see operational change.";
    narrative.querySelector("p").textContent = "Change Review explains threshold posture, continuity implications, replay expectations, and lifecycle context in operator language.";
    operational.textContent = "Review impact to generate the current authority posture.";
    continuity.textContent = "Registered lineage will show supersession path, resumed execution impact, and replay continuity obligations here.";
    renderReplayPosture(replay, null, null);
    renderSemanticAuthorityDiff(semanticDiff, null, "No semantic_authority_diff.v1 artifact has been generated for this authority pair.");
    renderSemanticDiffLists(null, null);
    renderExecutionContext("#change-execution-context", null);
    appendLineageEmpty(lineage);
    return;
  }
  const bundle = payload.authority_bundle;
  const preview = payload.governance_impact_preview || {};
  const registryEntry = findRegistryEntry(bundle.authority_ref);
  status.textContent = registryEntry ? `${formatLabel(registryEntry.status)} lineage` : "Draft lineage";
  narrative.querySelector("h3").textContent = options.reviewed
    ? `${bundle.authority_ref} is ready for publication review.`
    : `${bundle.authority_ref} has unreviewed draft changes.`;
  narrative.querySelector("p").textContent = options.reviewed
    ? "This review summarizes what changes operationally before the authority is exported or registered."
    : "Review impact to confirm the latest authored constraints before exporting this authority.";
  operational.textContent = firstText(preview.enforcement_behavior)
    || firstText(bundle.operational_implications)
    || "Operational impact will appear after review.";
  continuity.textContent = firstText(bundle.continuity_implications)
    || "No continuity implication has been derived yet. Review continuity posture before publication.";
  renderReplayPosture(replay, bundle, registryEntry);
  const activeSemanticDiff = payload.semantic_authority_diff || (semanticDiffMatchesCurrentPayload(currentSemanticAuthorityDiff, payload) ? currentSemanticAuthorityDiff : null);
  const activeLifecycleProjection = payload.semantic_lifecycle_enforcement_projection
    || activeSemanticDiff?.semantic_lifecycle_enforcement_projection
    || (semanticDiffMatchesCurrentPayload(currentSemanticAuthorityDiff, payload) ? currentLifecycleEnforcementProjection : null);
  renderSemanticAuthorityDiff(semanticDiff, activeSemanticDiff);
  renderSemanticDiffLists(activeSemanticDiff, activeLifecycleProjection);
  renderExecutionContext("#change-execution-context", preview.execution_context);
  renderLineageChain(lineage, registryEntry, bundle);
  refreshChangeReviewSemanticDiff(payload);
}

function appendLineageEmpty(node) {
  const item = document.createElement("li");
  const title = document.createElement("strong");
  title.textContent = "No lineage yet";
  const text = document.createElement("span");
  text.textContent = "Register an authority to create lifecycle history.";
  item.append(title, text);
  node.appendChild(item);
}

function renderLineageChain(node, registryEntry, bundle) {
  if (registryLifecycleEvents(registryEntry).length) {
    for (const event of registryLifecycleEvents(registryEntry)) {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = formatLabel(lifecycleEventType(event));
      const text = document.createElement("span");
      text.textContent = `${formatDateTime(event.timestamp)} | ${lifecycleEventDetail(event)}`;
      item.append(title, text);
      node.appendChild(item);
    }
    return;
  }
  const draft = document.createElement("li");
  const draftTitle = document.createElement("strong");
  draftTitle.textContent = "Draft";
  const draftText = document.createElement("span");
  draftText.textContent = `${bundle.authority_ref} has generated authority meaning but has not been registered locally.`;
  draft.append(draftTitle, draftText);
  node.appendChild(draft);
}

function renderReplayPosture(node, bundle, registryEntry) {
  node.innerHTML = "";
  const summary = document.createElement("strong");
  const receiptHash = registryEntry?.publication_receipt?.receipt_hash || registryEntry?.latest_receipt_hash;
  if (receiptHash) {
    summary.textContent = "Replay evidence complete";
    const explanation = document.createElement("span");
    explanation.textContent = "Receipt-backed replay evidence is available for this registered authority.";
    const details = document.createElement("details");
    details.className = "replay-hash-details";
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "View receipt hash";
    const hash = document.createElement("code");
    hash.className = "replay-hash";
    hash.textContent = receiptHash;
    details.append(detailsSummary, hash);
    node.append(summary, explanation, details);
    return;
  }
  if (bundle?.immutable_inputs?.preview_hash) {
    summary.textContent = "Replay evidence pending";
    const explanation = document.createElement("span");
    explanation.textContent = "Export will create publication receipt evidence that binds this authority to reviewed governance meaning.";
    node.append(summary, explanation);
    return;
  }
  summary.textContent = "Replay posture pending";
  const explanation = document.createElement("span");
  explanation.textContent = "Replay implications appear after the authority impact has been reviewed.";
  node.append(summary, explanation);
}

function replaySummary(bundle, registryEntry) {
  if (registryEntry?.publication_receipt?.receipt_hash) {
    return `Replay review can bind to receipt ${registryEntry.publication_receipt.receipt_hash}.`;
  }
  if (bundle?.immutable_inputs?.preview_hash) {
    return "Export will create publication receipt evidence that binds this authority to semantic artifact hashes.";
  }
  return "Replay posture will appear after authority impact has been reviewed.";
}

function firstText(value) {
  if (!Array.isArray(value)) return "";
  return value.find((item) => typeof item === "string" && item) || "";
}

async function buildPublicationReceipt(bundle, publishedAt, readiness, notes) {
  const response = await fetch("/api/publication-receipt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      authority_bundle: bundle,
      published_at: publishedAt,
      readiness_confirmations: readiness,
      publication_notes: notes,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    const reason = payload.error || "Unable to generate publication receipt.";
    throw new Error(response.status === 404 ? "publication receipt service unavailable" : reason);
  }
  if (payload.status && payload.status !== "exported") {
    throw new Error(`publication receipt response reported ${payload.status}`);
  }
  const receipt = payload.publication_receipt || payload;
  if (!receipt || receipt.schema_version !== "publication_receipt.v1" || !receipt.receipt_hash || !receipt.bundle_hash) {
    throw new Error("publication receipt response was incomplete");
  }
  return receipt;
}

function operationalReceiptRecommendation(error) {
  const message = String(error?.message || "");
  if (message.includes("publication receipt service unavailable") || message.toLowerCase().includes("not found")) {
    return "Refresh the local Ledger UI server, then export again to create a replayable publication receipt.";
  }
  if (message.includes("publication receipt response was incomplete")) {
    return "Ledger exported the bundle response without complete receipt evidence; refresh the local UI server and export again.";
  }
  return message || "Review the authority bundle and export again to create a publication receipt.";
}

function readReadinessConfirmations() {
  return {
    semantic_diagnostics_reviewed: Boolean(document.querySelector('[name="semantic_diagnostics_reviewed"]')?.checked),
    lineage_validated: Boolean(document.querySelector('[name="lineage_validated"]')?.checked),
    continuity_posture_reviewed: Boolean(document.querySelector('[name="continuity_posture_reviewed"]')?.checked),
    replay_implications_reviewed: Boolean(document.querySelector('[name="replay_implications_reviewed"]')?.checked),
    lifecycle_implications_acknowledged: Boolean(document.querySelector('[name="lifecycle_implications_acknowledged"]')?.checked),
  };
}

function readPublicationNotes(createdAt) {
  return [
    publicationNote("reason_for_supersession", "reason_for_supersession", createdAt),
    publicationNote("operational_change_summary", "operational_change_summary", createdAt),
    publicationNote("governance_revision_context", "governance_revision_context", createdAt),
  ].filter(Boolean);
}

function publicationNote(fieldName, noteType, createdAt) {
  const field = document.querySelector(`[name="${fieldName}"]`);
  const text = field?.value?.trim();
  if (!text) return null;
  return {
    note_type: noteType,
    text,
    created_at: createdAt,
  };
}

function downloadBundle(bundle) {
  const fileName = `${bundle.authority_ref.replace("@", "-").replaceAll(".", "-")}.authority-bundle.json`;
  const blob = new Blob([JSON.stringify(bundle, null, 2) + "\n"], { type: "application/json" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function formatLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDateTime(value) {
  if (!value) return "not recorded";
  return new Date(value).toLocaleString();
}

function relativeTime(value) {
  if (!value) return "not recorded";
  const elapsedSeconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (elapsedSeconds < 60) return "just now";
  const elapsedMinutes = Math.round(elapsedSeconds / 60);
  if (elapsedMinutes < 60) return `${elapsedMinutes}m ago`;
  const elapsedHours = Math.round(elapsedMinutes / 60);
  if (elapsedHours < 24) return `${elapsedHours}h ago`;
  return formatDateTime(value);
}

function showPage(pageId) {
  const targetPage = document.querySelector(`[data-page="${pageId}"]`) ? pageId : "draft";
  document.querySelectorAll("[data-page]").forEach((page) => {
    page.classList.toggle("active", page.dataset.page === targetPage);
  });
  document.querySelectorAll("[data-page-link]").forEach((link) => {
    link.classList.toggle("active", link.dataset.pageLink === targetPage);
  });
  if (window.location.hash !== `#${targetPage}`) {
    history.replaceState(null, "", `#${targetPage}`);
  }
}

generateButton.addEventListener("click", () => generateArtifacts({ navigate: true, review: true }));
publicationReviewButton.addEventListener("click", () => generateArtifacts({ review: true }));
exportButton.addEventListener("click", exportBundle);
registerButton.addEventListener("click", registerAuthorityLocally);
newDraftButton.addEventListener("click", startNewDraft);
saveDraftButton?.addEventListener("click", commitCurrentDraft);
extractPolicyButton.addEventListener("click", extractPolicySemantics);
useExtractionButton.addEventListener("click", commitSemanticInterpretation);
compileAuthorityButton.addEventListener("click", compileAuthorityContract);
applyAllExtractionButton?.addEventListener("click", commitSemanticInterpretation);
openReconciliationButton.addEventListener("click", openReconciliationReview);
manualFirstButton?.addEventListener("click", startManualFirstAuthoring);
populateCommittedDraftButton?.addEventListener("click", populateManualFieldsFromCommittedDraft);
document.querySelector("#reconciliation-workflow")?.addEventListener("click", handleReconciliationInteraction);
policySourceText.addEventListener("input", () => {
  policySourceDirty = true;
  currentExtraction = null;
  resetReconciliationState();
  useExtractionButton.disabled = true;
  if (applyAllExtractionButton) applyAllExtractionButton.disabled = true;
  openReconciliationButton.disabled = true;
  $("#extraction-status").textContent = "Policy text changed. Extract governance meaning again before reviewing operational impact.";
  invalidateSemanticLineage("policy_source_changed");
  workflowTimestamps.reviewed = null;
  workflowTimestamps.exported = null;
  workflowTimestamps.registered = null;
  exportButton.disabled = true;
  registerButton.disabled = true;
  updateWorkflowState({
    impactReviewed: false,
    bundleExported: false,
    receiptGenerated: false,
    authorityRegistered: false,
  });
});
form.addEventListener("input", (event) => {
  markManualFieldProvenance(event);
  saveWorkingAuthoringSession();
  pendingRegistration = null;
  workflowTimestamps.reviewed = null;
  workflowTimestamps.exported = null;
  workflowTimestamps.registered = null;
  exportButton.disabled = true;
  registerButton.disabled = true;
  updateWorkflowState({
    impactReviewed: false,
    bundleExported: false,
    receiptGenerated: false,
    authorityRegistered: false,
  });
});
form.addEventListener("change", (event) => {
  markManualFieldProvenance(event);
  saveWorkingAuthoringSession();
  pendingRegistration = null;
  workflowTimestamps.reviewed = null;
  workflowTimestamps.exported = null;
  workflowTimestamps.registered = null;
  exportButton.disabled = true;
  registerButton.disabled = true;
  updateWorkflowState({
    impactReviewed: false,
    bundleExported: false,
    receiptGenerated: false,
    authorityRegistered: false,
  });
});
$("#bundle-registry").addEventListener("click", handleRegistryAction);
$("#registry-search").addEventListener("input", renderBundleRegistry);
$("#registry-status-filter").addEventListener("change", renderBundleRegistry);
$("#registry-continuity-filter").addEventListener("change", renderBundleRegistry);

document.querySelectorAll("[data-page-link]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    showPage(link.dataset.pageLink);
  });
});

restoreDraftSession();
renderWorkflowState();
renderAuthorityContext();
renderBundleRegistry();
renderOperationsOverview();
renderChangeReview(currentArtifacts, { reviewed: workflowState.impactReviewed });
showPage(window.location.hash.replace("#", "") || "overview");
