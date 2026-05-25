const form = document.querySelector("#authority-form");
const generateButton = document.querySelector("#generate-button");
const exportButton = document.querySelector("#export-button");
const newDraftButton = document.querySelector("#new-draft-button");
const draftSessionStatus = document.querySelector("#draft-session-status");
let currentArtifacts = null;
let exportedBundles = [];
let livePreviewTimer = null;
const DRAFT_SESSION_KEY = "governance-ledger:draft-authority-session:v1";

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
  const authority = payload.authority_contract;
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
  renderBundleRegistryPreview(bundle, authority);
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

function renderBundleRegistryPreview(bundle, authority) {
  const node = $("#bundle-registry");
  node.innerHTML = "";
  const row = document.createElement("div");
  row.className = "bundle-row";
  const title = document.createElement("strong");
  title.textContent = bundle.authority_ref;
  const detail = document.createElement("span");
  detail.textContent = `${authority.protected_resource} | ${bundle.contract_hash}`;
  row.append(title, detail);
  node.appendChild(row);
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
  const fileName = `${bundle.authority_ref.replace("@", "-").replaceAll(".", "-")}.authority-bundle.json`;
  const blob = new Blob([JSON.stringify(bundle, null, 2) + "\n"], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
  exportedBundles = [{ ...bundle, exported_at: new Date().toISOString() }, ...exportedBundles].slice(0, 6);
  $("#status-bundle").textContent = "exported locally";
}

function formatLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
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

document.querySelectorAll("[data-page-link]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    showPage(link.dataset.pageLink);
  });
});

restoreDraftSession();
showPage(window.location.hash.replace("#", "") || "draft");
scheduleLivePreview();
