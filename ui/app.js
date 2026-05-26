const form = document.querySelector("#authority-form");
const generateButton = document.querySelector("#generate-button");
const exportButton = document.querySelector("#export-button");
const registerButton = document.querySelector("#register-button");
const newDraftButton = document.querySelector("#new-draft-button");
const draftSessionStatus = document.querySelector("#draft-session-status");
let currentArtifacts = null;
let pendingRegistration = null;
let livePreviewTimer = null;
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
  exportButton.disabled = true;
  registerButton.disabled = true;
  $("#status-authority-ref").textContent = "not generated";
  $("#status-semantic").textContent = "draft required";
  $("#status-bundle").textContent = "not exported";
  $("#release-registration").textContent = "Bundle not exported.";
  draftSessionStatus.textContent = "new draft_authority_session.v1 started locally";
  saveDraftSession();
}

async function generateArtifacts(options = {}) {
  const shouldNavigate = options.navigate === true;
  setBusy(true);
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
    renderArtifacts(payload);
    exportButton.disabled = false;
    registerButton.disabled = true;
    if (shouldNavigate) {
      showPage("preview");
    }
  } catch (error) {
    renderDiagnostics([{ severity: "error", code: "ui_generation_error", text: error.message }]);
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy) {
  generateButton.disabled = isBusy;
  generateButton.textContent = isBusy ? "Preparing impact..." : "Review Impact";
}

function scheduleLivePreview() {
  window.clearTimeout(livePreviewTimer);
  livePreviewTimer = window.setTimeout(() => {
    generateArtifacts();
  }, 450);
}

function renderArtifacts(payload) {
  const preview = payload.governance_impact_preview;
  const bundle = payload.authority_bundle;
  $("#status-authority-ref").textContent = bundle.authority_ref;
  $("#status-semantic").textContent = "ready";
  $("#status-bundle").textContent = "ready to export";
  $("#release-registration").textContent = "Bundle ready to export. Authority not registered locally.";

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
  $("#receipt-json").textContent = "{}";
  renderReleaseNarrative(payload.authority_release_narrative);

  renderDiagnostics(payload.diagnostics);
}

function renderReleaseNarrative(narrative) {
  $("#release-headline").textContent = narrative?.headline || "Review impact before publishing.";
  $("#release-summary").textContent = narrative?.publication_summary || "Create or restore an authority draft to see what publishing changes operationally.";
  $("#release-operational").textContent = narrative?.operational_change || "Pending impact review.";
  $("#release-continuity").textContent = narrative?.continuity_summary || "Pending impact review.";
  $("#release-lifecycle").textContent = narrative?.lifecycle_summary || "Pending impact review.";
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
    empty.textContent = "No advisory diagnostics for the current draft.";
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
    technical_detail: diagnostic.code ? `${diagnostic.code}: ${diagnostic.type || "diagnostic"}` : "",
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
    empty.textContent = "No authority bundles have been exported to the local registry.";
    list.appendChild(empty);
    renderBundleDetail(null);
    return;
  }

  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No authorities match the current registry filters.";
    list.appendChild(empty);
    renderBundleDetail(null);
    return;
  }

  for (const entry of filtered) {
    list.appendChild(authorityRegistryCard(entry));
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

  article.append(header, meta, timeline, actions);
  return article;
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
    empty.textContent = "Export an authority bundle to inspect its publication lineage and immutable inputs.";
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
    renderArtifacts(currentArtifacts);
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
  try {
    const bundle = currentArtifacts.authority_bundle;
    const publishedAt = new Date().toISOString();
    const readiness = readReadinessConfirmations();
    const notes = readPublicationNotes(publishedAt);
    const receipt = await buildPublicationReceipt(bundle, publishedAt, readiness, notes);
    $("#receipt-json").textContent = JSON.stringify(receipt, null, 2);
    downloadBundle(bundle);
    pendingRegistration = { receipt, notes };
    registerButton.disabled = false;
    $("#status-bundle").textContent = "bundle exported";
    $("#release-registration").textContent = "Bundle exported. Authority is not registered locally yet.";
  } catch (error) {
    pendingRegistration = null;
    registerButton.disabled = true;
    $("#release-registration").textContent = "Bundle export did not complete. Authority is not registered locally.";
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
  if (!currentArtifacts || !pendingRegistration) return;
  const entry = publishCurrentBundleToRegistry(pendingRegistration.receipt, pendingRegistration.notes);
  $("#status-bundle").textContent = "registered locally";
  $("#release-registration").textContent = "Authority registered locally. Registry lifecycle now has a registered authority event.";
  registerButton.disabled = true;
  renderBundleDetail(entry, "receipt");
  showPage("bundles");
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

generateButton.addEventListener("click", () => generateArtifacts({ navigate: true }));
exportButton.addEventListener("click", exportBundle);
registerButton.addEventListener("click", registerAuthorityLocally);
newDraftButton.addEventListener("click", startNewDraft);
form.addEventListener("input", () => {
  saveDraftSession();
  scheduleLivePreview();
});
form.addEventListener("change", () => {
  saveDraftSession();
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
renderBundleRegistry();
showPage(window.location.hash.replace("#", "") || "overview");
scheduleLivePreview();
