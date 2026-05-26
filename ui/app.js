const form = document.querySelector("#authority-form");
const generateButton = document.querySelector("#generate-button");
const publicationReviewButton = document.querySelector("#publication-review-button");
const exportButton = document.querySelector("#export-button");
const registerButton = document.querySelector("#register-button");
const newDraftButton = document.querySelector("#new-draft-button");
const draftSessionStatus = document.querySelector("#draft-session-status");
let currentArtifacts = null;
let pendingRegistration = null;
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
    escalation_threshold: data.get("escalation_threshold"),
    validity_days: data.get("validity_days"),
    mutation_targets: data.get("mutation_targets"),
    continuity_revalidation: data.get("continuity_revalidation") === "on",
    revocation_invalidates_resume: data.get("revocation_invalidates_resume") === "on",
  };
}

function buildDraftSession(draft) {
  const previous = loadDraftSession();
  const now = new Date().toISOString();
  return {
    schema_version: "draft_authority_session.v1",
    session_id: previous?.session_id || `draft-${crypto.randomUUID()}`,
    created_at: previous?.created_at || now,
    updated_at: now,
    draft,
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

function saveDraftSession() {
  const session = buildDraftSession(readDraft());
  window.localStorage.setItem(DRAFT_SESSION_KEY, JSON.stringify(session));
  draftSessionStatus.textContent = `draft_authority_session.v1 saved locally ${new Date(session.updated_at).toLocaleTimeString()}`;
  workflowTimestamps.draftSaved = session.updated_at;
  updateWorkflowState({ draftReady: true });
  return session;
}

function restoreDraftSession() {
  const session = loadDraftSession();
  if (!session) {
    saveDraftSession();
    return;
  }
  for (const [key, value] of Object.entries(session.draft || {})) {
    const field = form.elements[key];
    if (!field) continue;
    if (field.type === "checkbox") {
      field.checked = Boolean(value);
    } else {
      field.value = value ?? "";
    }
  }
  draftSessionStatus.textContent = `draft_authority_session.v1 restored ${new Date(session.updated_at).toLocaleTimeString()}`;
}

function startNewDraft() {
  window.localStorage.removeItem(DRAFT_SESSION_KEY);
  form.reset();
  currentArtifacts = null;
  pendingRegistration = null;
  workflowTimestamps = {
    draftSaved: null,
    reviewed: null,
    exported: null,
    registered: null,
  };
  exportButton.disabled = true;
  registerButton.disabled = true;
  $("#status-authority-ref").textContent = "not generated";
  $("#status-semantic").textContent = "draft required";
  $("#status-bundle").textContent = "not exported";
  $("#release-registration").textContent = "Bundle not exported.";
  renderPublicationProjection(null);
  $("#receipt-json").textContent = "No publication receipt generated yet.";
  updateWorkflowState({
    draftReady: true,
    impactReviewed: false,
    bundleExported: false,
    receiptGenerated: false,
    authorityRegistered: false,
  });
  draftSessionStatus.textContent = "new draft_authority_session.v1 started locally";
  saveDraftSession();
}

async function generateArtifacts(options = {}) {
  const shouldNavigate = options.navigate === true;
  const isReview = options.review === true || shouldNavigate;
  const isBackground = options.background === true;
  if (!isBackground) {
    setBusy(true);
  }
  try {
    saveDraftSession();
    const response = await fetch("/api/compose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft: readDraft() }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unable to generate semantic artifacts.");
    }
    currentArtifacts = payload;
    pendingRegistration = null;
    if (isReview) {
      workflowTimestamps.reviewed = new Date().toISOString();
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
  generateButton.textContent = isBusy ? "Preparing impact..." : "Review Impact";
  publicationReviewButton.disabled = isBusy;
  publicationReviewButton.textContent = isBusy ? "Reviewing Impact..." : "Review Impact";
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
}

function syncPublicationActions() {
  const hasArtifacts = Boolean(currentArtifacts);
  publicationReviewButton.disabled = reviewBusy || !workflowState.draftReady || workflowState.impactReviewed;
  exportButton.disabled = !hasArtifacts || !workflowState.impactReviewed;
  registerButton.disabled = !pendingRegistration || workflowState.authorityRegistered;
}

function renderOperatorGuidance(title, body) {
  const guidance = $("#operator-guidance");
  if (!guidance) return;
  if (title && body) {
    guidance.querySelector("strong").textContent = title;
    guidance.querySelector("span").textContent = body;
    return;
  }
  if (!workflowState.draftReady) {
    guidance.querySelector("strong").textContent = "Start by defining the authority.";
    guidance.querySelector("span").textContent = "Describe the governed system, action, approvals, escalation, and continuity posture.";
  } else if (!workflowState.impactReviewed) {
    guidance.querySelector("strong").textContent = "Review operational impact next.";
    guidance.querySelector("span").textContent = "Ledger has a draft. Review impact to confirm governance meaning before export.";
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
  const authorityRef = currentArtifacts?.authority_bundle?.authority_ref || `${readDraft().contract_id || "authority"}@${readDraft().contract_version || "draft"}`;
  const registryEntry = currentArtifacts?.authority_bundle ? findRegistryEntry(currentArtifacts.authority_bundle.authority_ref) : null;
  $("#context-authority-ref").textContent = authorityRef;
  $("#context-reviewed-at").textContent = workflowTimestamps.reviewed
    ? relativeTime(workflowTimestamps.reviewed)
    : "not reviewed";
  $("#context-lineage").textContent = registryEntry
    ? `${formatLabel(registryEntry.status)} lineage`
    : "draft lineage";
  setContextChip("#context-draft-state", true, "Draft");
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

function renderArtifacts(payload, options = {}) {
  const reviewed = options.reviewed === true;
  const preview = payload.governance_impact_preview;
  const bundle = payload.authority_bundle;
  const workspaceProjection = authorityWorkspaceProjection(payload);
  $("#status-authority-ref").textContent = bundle.authority_ref;
  $("#status-semantic").textContent = reviewed ? "ready" : "changes need review";
  $("#status-bundle").textContent = reviewed ? "ready to export" : "review impact before export";
  updateWorkflowState({
    draftReady: true,
    impactReviewed: reviewed,
    bundleExported: false,
    receiptGenerated: false,
    authorityRegistered: false,
  });

  $("#preview-summary").textContent = preview.governance_summary;
  renderList("#preview-enforcement", preview.enforcement_behavior);
  renderList("#preview-consequences", preview.operational_consequences);
  renderList("#preview-lifecycle", preview.lifecycle_implications);
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
  const lifecycle = existing?.lifecycle_timeline?.length
    ? existing.lifecycle_timeline
    : [
        lifecycleEvent("drafted", draftSession?.created_at || now, authority.contract_hash, "Authority draft captured locally."),
        lifecycleEvent("reviewed", now, bundle.immutable_inputs.preview_hash, "Semantic artifacts generated by Ledger."),
      ];

  const entry = {
    schema_version: "authority_bundle_registry_entry.v1",
    registry_id: existing?.registry_id || `registry-${crypto.randomUUID()}`,
    authority_ref: bundle.authority_ref,
    status: existing?.status || "registered",
    published_at: existing?.published_at || receipt?.published_at || now,
    superseded_by: existing?.superseded_by || null,
    governed_resource: projection.governed_resource || authority.protected_resource,
    governed_action: projection.governed_action || "unspecified action",
    continuity_posture: projection.continuity_posture || "continuity review recommended",
    escalation_threshold: projection.escalation_threshold || "not defined",
    semantic_integrity_posture: projection.semantic_integrity_posture || "requires review",
    contract_hash: bundle.contract_hash,
    immutable_inputs: bundle.immutable_inputs,
    lineage: bundle.lineage,
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
      diagnostics: currentArtifacts.diagnostics || [],
    },
    lifecycle_timeline: appendLifecycleOnce(
      lifecycle,
      "registered",
      receipt?.published_at || now,
      receipt?.bundle_hash || bundle.contract_hash,
      "Authority registered locally with authority_bundle.v1 and publication_receipt.v1.",
    ),
  };

  registry.authorities = [entry, ...registry.authorities.filter((item) => item.authority_ref !== entry.authority_ref)];
  saveBundleRegistry(registry);
  return entry;
}

function lifecycleEvent(event, timestamp, hash, detail) {
  return {
    event,
    timestamp,
    hash: hash || null,
    detail,
  };
}

function appendLifecycleOnce(timeline, event, timestamp, hash, detail) {
  if (timeline.some((item) => item.event === event && item.hash === hash)) {
    return timeline;
  }
  return [...timeline, lifecycleEvent(event, timestamp, hash, detail)];
}

function renderBundleRegistry() {
  const registry = loadBundleRegistry();
  const summary = $("#bundle-registry-summary");
  const list = $("#bundle-registry");
  const filtered = filterRegistryEntries(registry.authorities);
  summary.innerHTML = "";
  list.innerHTML = "";

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
    text.textContent = "Register an exported bundle to start a local authority lifecycle with lineage, receipts, and replay-ready evidence.";
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
}

function renderOperationsOverview() {
  const registry = loadBundleRegistry();
  const bundle = currentArtifacts?.authority_bundle;
  const registryEntry = bundle ? findRegistryEntry(bundle.authority_ref) : null;
  const diagnostics = currentArtifacts?.diagnostics || [];
  const pendingActions = pendingGovernanceActions(registry, diagnostics);
  const alerts = lifecycleAlerts(registry, diagnostics);

  setText("#overview-authority-state", registryEntry ? formatLabel(registryEntry.status) : workflowState.impactReviewed ? "Reviewed Draft" : "Draft");
  setText("#overview-replay-readiness", workflowState.receiptGenerated || registryEntry?.publication_receipt ? "receipt available" : "receipt pending");
  setText("#overview-continuity-posture", continuityOverviewText(registryEntry, bundle));

  renderTextList("#overview-pending-actions", pendingActions, ["No pending actions", "No current draft, receipt, or registry action requires attention."]);
  renderTextList("#overview-lifecycle-alerts", alerts, ["No lifecycle alerts", "No revocation, supersession, or drift posture currently requires attention."]);
  renderRegistryHealth(registry);
  renderActivityFeed(registry);
  renderRelationshipFeed(registry);
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
  const replayReady = registry.authorities.filter((entry) => entry.publication_receipt?.receipt_hash).length;
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
    for (const event of entry.lifecycle_timeline || []) {
      events.push({
        title: `${formatLabel(event.event)}: ${entry.authority_ref}`,
        text: `${formatDateTime(event.timestamp)} | ${event.detail || "Lifecycle event recorded."}`,
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
      entry.governed_resource,
      entry.governed_action,
      entry.continuity_posture,
      entry.escalation_threshold,
      entry.semantic_integrity_posture,
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
  const article = document.createElement("article");
  article.className = "authority-card";

  const header = document.createElement("div");
  header.className = "authority-card-header";
  const titleBlock = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = entry.authority_ref;
  const subtitle = document.createElement("p");
  subtitle.textContent = `${entry.governed_resource} | ${entry.governed_action}`;
  titleBlock.append(title, subtitle);
  const status = document.createElement("span");
  status.className = `status-badge ${entry.status}`;
  status.textContent = formatLabel(entry.status);
  header.append(titleBlock, status);

  const meta = document.createElement("dl");
  meta.className = "authority-meta";
  appendMeta(meta, "Registered", formatDateTime(entry.published_at));
  appendMeta(meta, "Superseded by", entry.superseded_by || "none");
  appendMeta(meta, "Continuity", entry.continuity_posture);
  appendMeta(meta, "Escalation", entry.escalation_threshold);
  appendMeta(meta, "Integrity", entry.semantic_integrity_posture);
  appendMeta(meta, "Contract hash", entry.contract_hash);

  const timeline = document.createElement("ol");
  timeline.className = "lifecycle-timeline";
  for (const event of entry.lifecycle_timeline || []) {
    const item = document.createElement("li");
    const eventName = document.createElement("strong");
    eventName.textContent = formatLabel(event.event);
    const eventDetail = document.createElement("span");
    eventDetail.textContent = `${formatDateTime(event.timestamp)} | ${event.hash || "no hash"}`;
    item.append(eventName, eventDetail);
    timeline.appendChild(item);
  }

  const relationship = document.createElement("div");
  relationship.className = "authority-relationship";
  const relationshipTitle = document.createElement("strong");
  relationshipTitle.textContent = "Lifecycle relationship";
  const relationshipText = document.createElement("span");
  relationshipText.textContent = relationshipSummary(entry);
  relationship.append(relationshipTitle, relationshipText);

  const actions = document.createElement("div");
  actions.className = "authority-actions";
  for (const action of [
    ["view-bundle", "View bundle"],
    ["open-preview", "Open semantic preview"],
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

  article.append(header, meta, relationship, timeline, actions);
  return article;
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
    empty.textContent = "Register an authority to inspect lifecycle lineage, receipt posture, and immutable inputs.";
    detail.append(title, empty);
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
  const body = document.createElement("pre");
  body.className = "json-view";
  if (mode === "lineage") {
    body.textContent = JSON.stringify({ lineage: entry.lineage, immutable_inputs: entry.immutable_inputs }, null, 2);
  } else if (mode === "receipt") {
    body.textContent = entry.publication_receipt
      ? JSON.stringify(entry.publication_receipt, null, 2)
      : "No publication_receipt.v1 artifact is attached to this registry entry.";
  } else if (mode === "diff") {
    body.textContent = entry.artifacts.authority_diff_impact
      ? JSON.stringify(entry.artifacts.authority_diff_impact, null, 2)
      : "No authority_diff_impact.v1 artifact is attached to this bundle.";
  } else {
    body.textContent = JSON.stringify(entry.bundle, null, 2);
  }
  detail.append(title, text, body);
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

function handleRegistryAction(event) {
  const button = event.target.closest("[data-registry-action]");
  if (!button) return;
  const entry = findRegistryEntry(button.dataset.authorityRef);
  if (!entry) return;
  const action = button.dataset.registryAction;
  if (action === "view-bundle") {
    renderBundleDetail(entry);
  } else if (action === "open-preview") {
    currentArtifacts = entry.artifacts;
    renderArtifacts(currentArtifacts, { reviewed: true });
    exportButton.disabled = false;
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
    const updated = updateRegistryEntry(entry.authority_ref, (item) => ({
      ...item,
      status: "superseded",
      superseded_by: item.superseded_by || supersededBy,
      lifecycle_timeline: appendLifecycleOnce(
        item.lifecycle_timeline || [],
        "superseded",
        new Date().toISOString(),
        item.contract_hash,
        `Superseded by ${item.superseded_by || supersededBy}.`,
      ),
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
      lifecycle_timeline: appendLifecycleOnce(
        item.lifecycle_timeline || [],
        "revoked",
        new Date().toISOString(),
        item.contract_hash,
        "Authority marked revoked in the local registry.",
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
        title: "Review impact before exporting.",
        domain: "publication",
        text: "The authority draft changed after the last reviewed impact.",
        recommendation: "Click Review Impact, then export the authority bundle.",
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

function renderChangeReview(payload, options = {}) {
  const status = $("#change-review-status");
  const narrative = $("#change-narrative");
  const operational = $("#change-operational");
  const continuity = $("#change-continuity");
  const replay = $("#change-replay");
  const lineage = $("#change-lineage");
  if (!status || !narrative || !operational || !continuity || !replay || !lineage) return;
  lineage.innerHTML = "";
  if (!payload?.authority_bundle) {
    status.textContent = "No authority reviewed";
    narrative.querySelector("h3").textContent = "Review a draft or registered authority to see operational change.";
    narrative.querySelector("p").textContent = "Change Review explains threshold posture, continuity implications, replay expectations, and lifecycle context in operator language.";
    operational.textContent = "Review impact to generate the current authority posture.";
    continuity.textContent = "Registered lineage will show supersession path, resumed execution impact, and replay continuity obligations here.";
    replay.textContent = "Replay implications appear after the authority impact has been reviewed.";
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
  replay.textContent = replaySummary(bundle, registryEntry);
  renderLineageChain(lineage, registryEntry, bundle);
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
  if (registryEntry?.lifecycle_timeline?.length) {
    for (const event of registryEntry.lifecycle_timeline) {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = formatLabel(event.event);
      const text = document.createElement("span");
      text.textContent = `${formatDateTime(event.timestamp)} | ${event.detail || event.hash || "lifecycle event recorded"}`;
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
form.addEventListener("input", () => {
  saveDraftSession();
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
  scheduleLivePreview();
});
form.addEventListener("change", () => {
  saveDraftSession();
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
  scheduleLivePreview();
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
scheduleLivePreview();
