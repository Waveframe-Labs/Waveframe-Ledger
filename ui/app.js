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
let workflowInvalidation = {
  active: false,
  reason: null,
  updated_at: null,
  invalidated_projections: [],
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
  clearWorkflowInvalidation();
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
      clearWorkflowInvalidation();
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
  renderPublicationProjection(authorityWorkspaceProjection());
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
  const preserveWorkflow = options.preserveWorkflow === true;
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
    continuity_risk: "Continuity Risk",
    replay_risk: "Replay Risk",
    authority_conflict: "Authority Conflict",
  }[posture] || formatLabel(posture);
}

function coherenceSummary({ posture, continuityRisks, replayRisks, authorityConflicts, staleProjections }) {
  if (posture === "healthy") return "Registry coherence is valid across lifecycle, replay, continuity, and state freshness.";
  if (authorityConflicts) return `${authorityConflicts} authority conflict${authorityConflicts === 1 ? "" : "s"} require lifecycle reconciliation.`;
  if (continuityRisks) return `${continuityRisks} continuity risk${continuityRisks === 1 ? "" : "s"} present in local authority lineage.`;
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
    coherenceMetric("Continuity Risk", coherence.counts.continuity_risk, coherence.counts.continuity_risk ? "continuity_risk" : "healthy"),
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
    body.textContent = entry.artifacts?.authority_diff_impact
      ? JSON.stringify(entry.artifacts.authority_diff_impact, null, 2)
      : "No authority_diff_impact.v1 artifact is attached to this bundle.";
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
    registryDetailMetric("Continuity", entry.continuity_posture || "review recommended", coherence.severity === "continuity_risk" ? "Continuity review advised" : "Continuity posture recorded"),
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
  const blocks = document.createElement("div");
  blocks.className = "registry-detail-blocks";
  blocks.append(
    registryDetailBlock("Identity", identitySummary(entry, summary)),
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
  reasonText.textContent = causality?.reason || "No continuity risk is indicated by the current local registry state.";
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
    const updated = updateRegistryEntry(entry.authority_ref, (item) => ({
      ...item,
      status: "superseded",
      updated_at: new Date().toISOString(),
      superseded_by: item.superseded_by || supersededBy,
      lifecycle_events: appendLifecycleOnce(
        registryLifecycleEvents(item),
        "superseded",
        new Date().toISOString(),
        { bundle_hash: item.latest_bundle_hash || item.contract_hash },
        `Superseded by ${item.superseded_by || supersededBy}.`,
        item.authority_ref,
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
    renderReplayPosture(replay, null, null);
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
form.addEventListener("input", () => {
  saveDraftSession();
  pendingRegistration = null;
  markDraftInvalidated();
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
  markDraftInvalidated();
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
