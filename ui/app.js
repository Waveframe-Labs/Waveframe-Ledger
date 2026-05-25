const form = document.querySelector("#authority-form");
const generateButton = document.querySelector("#generate-button");
const exportButton = document.querySelector("#export-button");
const newDraftButton = document.querySelector("#new-draft-button");
const draftSessionStatus = document.querySelector("#draft-session-status");
let currentArtifacts = null;
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
  exportButton.disabled = true;
  $("#status-authority-ref").textContent = "not generated";
  $("#status-semantic").textContent = "draft required";
  $("#status-bundle").textContent = "not exported";
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
    renderArtifacts(payload);
    exportButton.disabled = false;
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
  generateButton.textContent = isBusy ? "Generating..." : "Generate Semantic Artifacts";
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

  renderDiagnostics(payload.diagnostics);
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
  node.innerHTML = "";
  if (!items || items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No diagnostics for the current draft.";
    node.appendChild(empty);
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    row.className = `diagnostic-row ${item.severity || "info"}`;
    const title = document.createElement("strong");
    title.textContent = `${(item.severity || "info").toUpperCase()} ${item.code || "diagnostic"}`;
    const text = document.createElement("span");
    text.textContent = item.text || "";
    row.append(title, text);
    node.appendChild(row);
  }
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

function publishCurrentBundleToRegistry() {
  if (!currentArtifacts) return null;
  const registry = loadBundleRegistry();
  const bundle = currentArtifacts.authority_bundle;
  const authority = currentArtifacts.authority_contract;
  const projection = currentArtifacts.authority_registry_projection || {};
  const now = new Date().toISOString();
  const draftSession = loadDraftSession();
  const existing = registry.authorities.find((entry) => entry.authority_ref === bundle.authority_ref);
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
    status: existing?.status || "published",
    published_at: existing?.published_at || now,
    superseded_by: existing?.superseded_by || null,
    governed_resource: projection.governed_resource || authority.protected_resource,
    governed_action: projection.governed_action || "unspecified action",
    continuity_posture: projection.continuity_posture || "continuity review recommended",
    escalation_threshold: projection.escalation_threshold || "not defined",
    semantic_integrity_posture: projection.semantic_integrity_posture || "requires review",
    contract_hash: bundle.contract_hash,
    immutable_inputs: bundle.immutable_inputs,
    lineage: bundle.lineage,
    bundle,
    artifacts: {
      authority_contract: currentArtifacts.authority_contract,
      governance_impact_preview: currentArtifacts.governance_impact_preview,
      authority_diff_impact: bundle.authority_diff_impact || null,
      governance_review_packet: currentArtifacts.governance_review_packet,
      publication_manifest: currentArtifacts.publication_manifest,
      authority_bundle: bundle,
      authority_registry_projection: projection,
      diagnostics: currentArtifacts.diagnostics || [],
    },
    lifecycle_timeline: appendLifecycleOnce(lifecycle, "published", now, bundle.contract_hash, "authority_bundle.v1 exported to the local registry."),
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
  summary.innerHTML = "";
  list.innerHTML = "";

  const publishedCount = registry.authorities.filter((entry) => entry.status === "published").length;
  const revokedCount = registry.authorities.filter((entry) => entry.status === "revoked").length;
  const supersededCount = registry.authorities.filter((entry) => entry.status === "superseded").length;
  summary.append(
    registryMetric("Authorities", registry.authorities.length),
    registryMetric("Published", publishedCount),
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

  for (const entry of registry.authorities) {
    list.appendChild(authorityRegistryCard(entry));
  }
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
  appendMeta(meta, "Published", formatDateTime(entry.published_at));
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
  title.textContent = mode === "lineage" ? "Lineage" : mode === "diff" ? "Authority diff" : "Authority bundle";
  const text = document.createElement("p");
  text.className = "quiet";
  text.textContent = `${entry.authority_ref} | ${formatLabel(entry.status)}`;
  const body = document.createElement("pre");
  body.className = "json-view";
  if (mode === "lineage") {
    body.textContent = JSON.stringify({ lineage: entry.lineage, immutable_inputs: entry.immutable_inputs }, null, 2);
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

function exportBundle() {
  if (!currentArtifacts) return;
  const bundle = currentArtifacts.authority_bundle;
  downloadBundle(bundle);
  const entry = publishCurrentBundleToRegistry();
  $("#status-bundle").textContent = "exported to local registry";
  renderBundleDetail(entry);
  showPage("bundles");
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
