// Gym Audit Viewer — flat-table layout with Issues/All filter

const el = (id) => document.getElementById(id);
const create = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

let currentSessionData = null;
let rubricIndex = {};
let currentFilter = "issues";    // "issues" or "all"
let currentCategory = null;       // null = all categories, or a category id (incl. "cross_cutting")
let currentView = "session";      // "session" | "checks-md" | "lifecycle"
let expandedRow = null;
let checksMdHtml = null;          // cached after first load

// One unified view: DAG in main, phase/stage sidebar on the left.
// Kept for any legacy reads; toggling is gone.
let currentMode = "pipeline";

// Lifecycle state
let lifecycleData = null;                          // {phases: [...]}
let lifecycleResultsBySession = {};                // session_id → {check_id: {level, failing_tasks, passing_tasks}}
let lifecycleStageId = null;                       // null = show all stages
let lifecycleScopeFilter = "all";                  // all | per-task | per-stage | per-batch | gym-wide
let lifecyclePassFilter = "all";                   // all | pass | fail | unknown
let lifecycleExpandedCheck = null;                 // "stageId.checkId"

// Pipeline view state
let pipelineSelectedStage = null;                  // {phase, stage}
// In Pipeline mode, every check starts collapsed when a node is clicked.
// We track the explicitly-expanded ones; re-renders preserve those choices
// until the user picks a different node (which clears the set).
let pipelineExpandedChecks = new Set();            // keys "stageId.checkId"

// Single source of truth for "is this check expanded right now?"
function isCheckExpanded(stage, check) {
  const key = `${stage.id}.${check.id}`;
  if (currentMode === "pipeline") return pipelineExpandedChecks.has(key);
  return lifecycleExpandedCheck === key;
}

function toggleCheckExpansion(stage, check) {
  const key = `${stage.id}.${check.id}`;
  if (currentMode === "pipeline") {
    if (pipelineExpandedChecks.has(key)) pipelineExpandedChecks.delete(key);
    else pipelineExpandedChecks.add(key);
  } else {
    lifecycleExpandedCheck = lifecycleExpandedCheck === key ? null : key;
  }
}

// ─── Boot ───────────────────────────────────────────────────────────
async function boot() {
  try { lifecycleData = await fetchJSON("/api/lifecycle-rubric"); }
  catch (e) { console.warn("lifecycle rubric unavailable:", e); lifecycleData = null; }
  indexStageCorpus();

  const sessions = await fetchJSON("/api/sessions");
  const select = el("session-select");
  select.innerHTML = "";

  if (!sessions.length) {
    const opt = create("option", null, "— no sessions found —");
    opt.disabled = true;
    select.appendChild(opt);
    el("session-meta").textContent = "No audit sessions yet";
    renderForCurrentMode();
    return;
  }

  sessions.forEach(s => {
    const opt = create("option");
    opt.value = s.id;
    const score = s.overall_score == null ? "—" : s.overall_score.toFixed(2);
    opt.textContent = `${s.id}  ·  ${score}  ·  ${s.audited_at || ""}`;
    select.appendChild(opt);
  });

  select.addEventListener("change", () => loadSession(select.value));
  await loadSession(select.value);
}

// One view: DAG with in-circle counts + evidence panel. No sidebar.
function renderForCurrentMode() {
  renderPipelinePage();
}

async function loadSession(sessionId) {
  currentSessionData = await fetchJSON(`/api/sessions/${sessionId}`);
  currentSessionData.id = sessionId;

  // Pull lifecycle evaluations into the per-session bag.
  // Shape: { "stage_id.check_id": { level, score, evidence, failing_tasks, passing_tasks, remediation } }
  const lcEvals = currentSessionData.lifecycle_evaluations || {};
  lifecycleResultsBySession[sessionId] = lcEvals;
  computeTaskUniverse();

  // Reset filter state on session switch so stage counts are reflected
  lifecycleExpandedCheck = null;
  pipelineSelectedStage = null;
  pipelineExpandedChecks = new Set();

  renderMeta();
  renderForCurrentMode();
}

function renderMeta() {
  const d = currentSessionData;
  if (!d) {
    el("session-meta").textContent = "";
    return;
  }
  const score = d.overall_score == null ? "—" : d.overall_score.toFixed(2);
  const lcCount = Object.keys(d.lifecycle_evaluations || {}).length;
  const lcLabel = lcCount > 0 ? ` · ${lcCount} lifecycle checks evaluated` : " · no lifecycle data yet";
  el("session-meta").textContent = `${d.target_gym || ""} · audited ${d.audited_at || ""} · score ${score}${lcLabel}`;
}

// ─── Page renderer ──────────────────────────────────────────────────
function renderPage() {
  const page = el("page");
  page.innerHTML = "";

  if (currentView === "checks-md") {
    renderChecksMd(page);
    return;
  }

  // Verdict block only at the session-wide view; when scoped to a category,
  // show a smaller "Showing: <category>" header instead.
  if (currentCategory == null) {
    page.appendChild(renderVerdict());
  } else {
    page.appendChild(renderScopeHeader());
  }
  page.appendChild(renderFilter());
  page.appendChild(renderTable());
}

async function renderChecksMd(page) {
  const header = create("div", "checksmd-header");
  header.appendChild(create("div", "scope-eyebrow", "Reference"));
  header.appendChild(create("h2", "scope-title", "Check reference (CHECKS.md)"));
  page.appendChild(header);

  if (checksMdHtml == null) {
    const loading = create("div", "muted", "Loading CHECKS.md…");
    page.appendChild(loading);
    try {
      const data = await fetchJSON("/api/checks-md");
      checksMdHtml = data.html;
    } catch (e) {
      loading.textContent = `Failed to load CHECKS.md: ${e.message}`;
      return;
    }
    loading.remove();
  }
  const body = create("article", "checksmd-body");
  body.innerHTML = checksMdHtml;
  page.appendChild(body);
}

function renderScopeHeader() {
  const cat = currentCategory === "cross_cutting"
    ? { name: "Cross-cutting", score: null }
    : (currentSessionData.categories || []).find(c => c.id === currentCategory);
  const wrap = create("section", "scope-header");
  const left = create("div");
  left.appendChild(create("div", "scope-eyebrow", "Category"));
  left.appendChild(create("h2", "scope-title", cat?.name || currentCategory));
  wrap.appendChild(left);
  if (cat?.score != null) {
    const right = create("div", "scope-score-wrap");
    right.appendChild(create("div", "scope-eyebrow", "Score"));
    right.appendChild(create("div", "scope-score", cat.score.toFixed(2)));
    wrap.appendChild(right);
  }
  return wrap;
}

// ─── Verdict block ──────────────────────────────────────────────────
function renderVerdict() {
  const d = currentSessionData;
  const verdict = create("section", "verdict");
  verdict.appendChild(create("h2", null, "Top-line verdict"));

  const headline = create("div", "verdict-headline");
  headline.textContent = d.verdict || "Audit complete";
  const score = create("span", "verdict-score", `score ${d.overall_score?.toFixed(2) || "—"}`);
  headline.appendChild(score);
  verdict.appendChild(headline);

  if (d.load_bearing) {
    const grid = create("div", "load-bearing-grid");
    const meta = {
      closed_entity_universe: {
        name: "Closed entity universe",
        desc: "The kinds of entities a task can declare (users, resources, files, etc.) are a typed, closed set defined in code — not arbitrary dicts. Without this, no schema-level invariant can be enforced.",
      },
      closed_reward_compiler_universe: {
        name: "Closed reward-compiler universe",
        desc: "Reward / check kinds are an enumerable closed set. Task authors choose from them; they can't invent new kinds without a code change. Required so every kind can be lint-covered.",
      },
      invariants_per_check_kind: {
        name: "Invariants per check kind",
        desc: "Every reward kind has constraints (typed model + lint rules) that catch malformed structures at task-definition time, not at grading time. The mechanism that prevents broken rewards from shipping.",
      },
      golden_solution_per_task: {
        name: "Golden solution per task",
        desc: "Every task has a stored known-good solution proving it's actually solvable and the reward set fully passes for it. Tasks without a golden are unverified theory.",
      },
    };
    Object.entries(d.load_bearing).forEach(([k, v]) => {
      const info = meta[k] || { name: k, desc: "" };
      const cell = create("div", "lb-cell lb-cell-clickable");
      cell.setAttribute("role", "button");
      cell.setAttribute("tabindex", "0");
      cell.title = `Open ${info.name} in the findings table below`;

      const header = create("div", "lb-header");
      header.appendChild(create("span", "lb-name", info.name));
      header.appendChild(create("span", `pill pill-level ${v}`, v));
      cell.appendChild(header);

      if (info.desc) cell.appendChild(create("p", "lb-desc", info.desc));

      // Hint that this is clickable
      cell.appendChild(create("div", "lb-cta", "View check ↓"));

      const onActivate = () => focusCheckInTable(k);
      cell.addEventListener("click", onActivate);
      cell.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          onActivate();
        }
      });
      grid.appendChild(cell);
    });
    verdict.appendChild(grid);
  }
  return verdict;
}

// ─── Filter bar ─────────────────────────────────────────────────────
function renderFilter() {
  const bar = create("section", "filter-bar");

  const issuesCount = collectAllChecks().filter(c => c.level === "issues" || c.level === "absent" || c.level === "partial").length;
  const allCount = collectAllChecks().length;

  const issuesBtn = create("button", `filter-btn ${currentFilter === "issues" ? "active" : ""}`);
  issuesBtn.type = "button";
  issuesBtn.innerHTML = `Issues <span class="count">${issuesCount}</span>`;
  issuesBtn.addEventListener("click", () => {
    currentFilter = "issues";
    expandedRow = null;
    renderPage();
  });

  const allBtn = create("button", `filter-btn ${currentFilter === "all" ? "active" : ""}`);
  allBtn.type = "button";
  allBtn.innerHTML = `All <span class="count">${allCount}</span>`;
  allBtn.addEventListener("click", () => {
    currentFilter = "all";
    expandedRow = null;
    renderPage();
  });

  bar.appendChild(issuesBtn);
  bar.appendChild(allBtn);
  return bar;
}

// ─── Focus a specific check in the findings table ──────────────────
function focusCheckInTable(checkId) {
  // Stay in the session-wide view so the verdict cells remain visible above.
  currentCategory = null;

  // Find the check across all categories + cross-cutting.
  let found = null;
  for (const cat of currentSessionData.categories || []) {
    found = (cat.checks || []).find(c => c.id === checkId);
    if (found) break;
  }
  if (!found) {
    found = (currentSessionData.cross_cutting || []).find(c => c.id === checkId);
  }
  if (!found) return; // safety: check not in session

  // If the check is present, the Issues filter would hide it — switch to All.
  if (found.level === "present" && currentFilter === "issues") {
    currentFilter = "all";
  }

  expandedRow = checkId;
  renderSidebar();
  renderPage();

  // Scroll the expanded row into view after the re-render.
  setTimeout(() => {
    const row = document.querySelector(`tr.findings-row[data-check-id="${CSS.escape(checkId)}"]`);
    if (row) {
      row.scrollIntoView({ behavior: "smooth", block: "center" });
      row.classList.add("flash");
      setTimeout(() => row.classList.remove("flash"), 1500);
    }
  }, 60);
}

// ─── Sidebar ────────────────────────────────────────────────────────
function renderSidebar() {
  const sb = el("sidebar");
  sb.innerHTML = "";

  const sessionActive = currentView === "session";

  // Build a scope map from the rubric: cat_id → "environment" | "tasks"
  const scopeOf = {};
  for (const v of Object.values(rubricIndex)) {
    if (v.category_id && v.category_scope) scopeOf[v.category_id] = v.category_scope;
  }

  const allCats = currentSessionData.categories || [];
  const envCats  = allCats.filter(c => (scopeOf[c.id] || "environment") === "environment");
  const taskCats = allCats.filter(c => (scopeOf[c.id] || "environment") === "tasks");
  const crossCount = (currentSessionData.cross_cutting || []).length;

  // "All categories" entry — verdict view across everything
  const totalCount = allCats.reduce((n, c) => n + (c.checks?.length || 0), 0) + crossCount;
  const allItem = create("div", `sidebar-item ${sessionActive && currentCategory == null ? "active" : ""}`);
  allItem.appendChild(create("span", "sidebar-label", "All categories"));
  allItem.appendChild(create("span", "sidebar-count", String(totalCount)));
  allItem.addEventListener("click", () => {
    currentView = "session";
    currentCategory = null;
    expandedRow = null;
    renderSidebar();
    renderPage();
  });
  sb.appendChild(allItem);

  // ── ENVIRONMENT section ──────────────────────────────────────────
  if (envCats.length) {
    sb.appendChild(create("div", "sidebar-section", "Environment"));
    envCats.forEach(cat => appendCategoryItem(sb, cat, sessionActive));
  }

  // ── TASKS section ───────────────────────────────────────────────
  if (taskCats.length) {
    sb.appendChild(create("div", "sidebar-section", "Tasks"));
    taskCats.forEach(cat => appendCategoryItem(sb, cat, sessionActive));
  }

  // ── OTHER section (cross-cutting) ───────────────────────────────
  if (crossCount) {
    sb.appendChild(create("div", "sidebar-section", "Other"));
    const item = create("div", `sidebar-item ${sessionActive && currentCategory === "cross_cutting" ? "active" : ""}`);
    item.appendChild(create("span", "sidebar-label", "Cross-cutting"));
    item.appendChild(create("span", "sidebar-count", String(crossCount)));
    item.addEventListener("click", () => {
      currentView = "session";
      currentCategory = "cross_cutting";
      expandedRow = null;
      renderSidebar();
      renderPage();
    });
    sb.appendChild(item);
  }

  // ── REFERENCE section ───────────────────────────────────────────
  sb.appendChild(create("div", "sidebar-section sidebar-section-bottom", "Reference"));
  const refItem = create("div", `sidebar-item ${currentView === "checks-md" ? "active" : ""}`);
  refItem.appendChild(create("span", "sidebar-label", "Check reference"));
  refItem.appendChild(create("span", "sidebar-count", "MD"));
  refItem.addEventListener("click", () => {
    currentView = "checks-md";
    expandedRow = null;
    renderSidebar();
    renderPage();
  });
  sb.appendChild(refItem);
}

function appendCategoryItem(sb, cat, sessionActive) {
  const item = create("div", `sidebar-item ${sessionActive && currentCategory === cat.id ? "active" : ""}`);
  item.appendChild(create("span", "sidebar-label", cat.name || cat.id));
  const score = cat.score == null ? "—" : cat.score.toFixed(2);
  item.appendChild(create("span", "sidebar-score", score));
  item.addEventListener("click", () => {
    currentView = "session";
    currentCategory = cat.id;
    expandedRow = null;
    renderSidebar();
    renderPage();
  });
  sb.appendChild(item);
}

// ─── Collect checks (scoped by current category) ───────────────────
function collectAllChecks() {
  const all = [];

  if (currentCategory == null) {
    for (const cat of currentSessionData.categories || []) {
      for (const c of cat.checks || []) all.push({ ...c, _category: cat.name });
    }
    for (const c of currentSessionData.cross_cutting || []) {
      all.push({ ...c, _category: "Cross-cutting" });
    }
  } else if (currentCategory === "cross_cutting") {
    for (const c of currentSessionData.cross_cutting || []) {
      all.push({ ...c, _category: "Cross-cutting" });
    }
  } else {
    const cat = (currentSessionData.categories || []).find(c => c.id === currentCategory);
    if (cat) {
      for (const c of cat.checks || []) all.push({ ...c, _category: cat.name });
    }
  }
  return all;
}

// ─── Findings table ─────────────────────────────────────────────────
function renderTable() {
  const section = create("section", "findings-section");

  const all = collectAllChecks();
  const rows = currentFilter === "issues"
    ? all.filter(c => c.level === "absent" || c.level === "partial")
    : all;

  // Sort: absent first, then partial, then present; load-bearing first within each tier
  const levelOrder = { absent: 0, partial: 1, present: 2, skipped: 3 };
  rows.sort((a, b) => {
    const la = levelOrder[a.level] ?? 9;
    const lb = levelOrder[b.level] ?? 9;
    if (la !== lb) return la - lb;
    const lba = a.load_bearing ? 0 : 1;
    const lbb = b.load_bearing ? 0 : 1;
    if (lba !== lbb) return lba - lbb;
    return (a.name || a.id).localeCompare(b.name || b.id);
  });

  if (!rows.length) {
    section.appendChild(create("div", "empty muted",
      currentFilter === "issues" ? "No issues — every check is present." : "No checks in this session."));
    return section;
  }

  const table = create("table", "findings-table");
  const thead = create("thead");
  const trh = create("tr");
  ["Name", "Verdict", ""].forEach(h => trh.appendChild(create("th", null, h)));
  thead.appendChild(trh);
  table.appendChild(thead);

  const tbody = create("tbody");
  rows.forEach((c, i) => {
    const tr = create("tr", "findings-row");
    tr.dataset.checkId = c.id;

    // Name column (category as small subtitle)
    const nameCell = create("td", "name-cell");
    nameCell.appendChild(create("div", "row-name", c.name || c.id));
    nameCell.appendChild(create("div", "row-category", c._category || ""));
    if (c.load_bearing) nameCell.appendChild(create("span", "row-flag flag-lb", "load-bearing"));
    tr.appendChild(nameCell);

    // Verdict
    const vCell = create("td", "verdict-cell");
    vCell.appendChild(create("span", `pill pill-level ${c.level}`, c.level));
    tr.appendChild(vCell);

    // View link
    const aCell = create("td", "action-cell");
    const link = create("a", "view-link", expandedRow === c.id ? "Hide" : "View");
    link.href = "#";
    link.addEventListener("click", (ev) => {
      ev.preventDefault();
      expandedRow = expandedRow === c.id ? null : c.id;
      renderPage();
      // Scroll the expanded row into view after re-render
      setTimeout(() => {
        const expanded = document.querySelector(".findings-row.expanded");
        if (expanded) expanded.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 50);
    });
    aCell.appendChild(link);
    tr.appendChild(aCell);

    tbody.appendChild(tr);

    // Expanded detail row
    if (expandedRow === c.id) {
      tr.classList.add("expanded");
      const detailTr = create("tr", "details-row");
      const detailTd = document.createElement("td");
      detailTd.colSpan = 3;
      detailTd.appendChild(renderCheckDetails(c));
      detailTr.appendChild(detailTd);
      tbody.appendChild(detailTr);
    }
  });

  table.appendChild(tbody);
  section.appendChild(table);
  return section;
}

// ─── Inline check detail (was the expandable card panel) ───────────
function renderCheckDetails(c) {
  const rubric = rubricIndex[c.id] || {};
  const wrap = create("div", "check-detail");

  // Header strip with ID and any flags
  const idLine = create("div", "detail-id", c.id);
  wrap.appendChild(idLine);

  const principle = c.principle || rubric.principle;
  if (principle) {
    wrap.appendChild(create("div", "details-section-title", "What is checked"));
    wrap.appendChild(create("p", "details-text", principle));
  }

  // How it is checked (from rubric)
  if (rubric.detector) {
    wrap.appendChild(create("div", "details-section-title", "How it is checked"));
    if (rubric.detector.method) {
      const meth = create("div", "details-text");
      const strong = create("strong", null, "Method: ");
      meth.appendChild(strong);
      meth.appendChild(document.createTextNode(rubric.detector.method));
      wrap.appendChild(meth);
    }
    if (rubric.detector.steps?.length) {
      const ol = create("ol", "details-steps");
      rubric.detector.steps.forEach(s => ol.appendChild(create("li", null, s)));
      wrap.appendChild(ol);
    }
  }

  // Level meanings
  if (rubric.levels) {
    wrap.appendChild(create("div", "details-section-title", "What each level means"));
    const lg = create("div", "level-grid");
    ["present", "partial", "absent"].forEach(lv => {
      if (rubric.levels[lv]) {
        const row = create("div", `level-row level-${lv}`);
        row.appendChild(create("span", `pill pill-level ${lv}`, lv));
        row.appendChild(create("span", "level-desc", rubric.levels[lv]));
        lg.appendChild(row);
      }
    });
    wrap.appendChild(lg);
  }

  // Evidence
  if (c.evidence?.length) {
    wrap.appendChild(create("div", "details-section-title", "Evidence"));
    const ul = create("ul", "check-evidence");
    c.evidence.forEach(e => ul.appendChild(create("li", null, e)));
    wrap.appendChild(ul);
  }

  // Failing tasks (collapsible)
  if (Array.isArray(c.failing_tasks) && c.failing_tasks.length) {
    const ids = c.failing_tasks;
    const det = document.createElement("details");
    det.className = "failing-tasks";
    const sum = document.createElement("summary");
    sum.className = "failing-tasks-summary";
    sum.textContent = `Failing tasks (${ids.length}) — click to expand`;
    det.appendChild(sum);
    const list = create("ul", "failing-tasks-list");
    ids.forEach(t => list.appendChild(create("li", "failing-task-id", t)));
    det.appendChild(list);
    wrap.appendChild(det);
  }

  // Remediation
  if (c.remediation) {
    wrap.appendChild(create("div", "details-section-title", "Remediation"));
    wrap.appendChild(create("p", "details-text", c.remediation));
  }

  // Flags / notes
  const whyParts = [];
  if (rubric.load_bearing || c.load_bearing) {
    whyParts.push("This is a load-bearing meta-check — if absent, the gym cannot enforce structural invariants regardless of how well other checks score.");
  }
  if (whyParts.length) {
    wrap.appendChild(create("div", "details-section-title", "Why it matters"));
    whyParts.forEach(p => wrap.appendChild(create("p", "details-text", p)));
  }
  if (rubric.note) {
    wrap.appendChild(create("div", "details-section-title", "Note"));
    wrap.appendChild(create("p", "details-text muted", rubric.note));
  }
  if (rubric.baseline_status) {
    wrap.appendChild(create("div", "details-section-title", "Baseline status"));
    wrap.appendChild(create("p", "details-text muted",
      `In the baseline gym (gym-cua-anthropic) this check scores: ${rubric.baseline_status}.`));
  }

  // Baseline reference
  const baselineExample = c.baseline_example || rubric.baseline_example || rubric.baseline_rule;
  if (baselineExample) {
    wrap.appendChild(create("div", "details-section-title", "Baseline reference"));
    wrap.appendChild(create("p", "details-text mono muted", baselineExample));
  }
  if (rubric.example_defect) {
    wrap.appendChild(create("div", "details-section-title", "Example defect this would catch"));
    wrap.appendChild(create("p", "details-text mono", rubric.example_defect));
  }

  return wrap;
}

// ───────────────────────────────────────────────────────────────────
// Lifecycle view — phase → stage navigation, scope tags, filters,
// collapsible per-task passing/failing lists.
// ───────────────────────────────────────────────────────────────────

function getLifecycleResultForCheck(stageId, checkId) {
  // Returns {level, failing_tasks, passing_tasks} for the active session, or null.
  if (!currentSessionData) return null;
  const sessionId = currentSessionData.id || (el("session-select") && el("session-select").value);
  const bag = lifecycleResultsBySession[sessionId];
  if (!bag) return null;
  return bag[`${stageId}.${checkId}`] || null;
}

// Distinct task IDs ever mentioned in this session's per-task checks — split
// by corpus so a draft check never "sees" shipped tasks and vice versa.
// Each corpus has its own universe set; checks pick the right one via the
// corpus declared on their parent phase.
const lifecycleUniversesByCorpus = { draft: new Set(), shipped: new Set() };

// stage_id → { corpus, corpus_path }, built when the rubric loads
let stageInfo = {};
function indexStageCorpus() {
  stageInfo = {};
  if (!lifecycleData || !lifecycleData.phases) return;
  for (const ph of lifecycleData.phases) {
    const corpus = ph.corpus || "draft";
    const corpus_path = ph.corpus_path || "";
    for (const s of ph.stages || []) {
      stageInfo[s.id] = { corpus, corpus_path };
    }
  }
}
// Backwards-compat shim for the few callers that just want the corpus string
const stageCorpus = new Proxy({}, { get: (_, k) => stageInfo[k]?.corpus });

// Backwards-compat accessors (rest of code still calls these);
// they default to the union of both corpora.
let lifecycleTaskUniverse = 0;
let lifecycleTaskUniverseSet = new Set();

function computeTaskUniverse() {
  lifecycleUniversesByCorpus.draft = new Set();
  lifecycleUniversesByCorpus.shipped = new Set();
  if (!currentSessionData) {
    lifecycleTaskUniverse = 0;
    lifecycleTaskUniverseSet = new Set();
    return;
  }
  const sessionId = currentSessionData.id || el("session-select")?.value;
  const bag = lifecycleResultsBySession[sessionId] || {};
  for (const [key, r] of Object.entries(bag)) {
    const stageId = key.split(".", 1)[0];
    const corpus = stageCorpus[stageId] || "draft";
    const set = lifecycleUniversesByCorpus[corpus] || lifecycleUniversesByCorpus.draft;
    (r.passing_tasks || []).forEach(t => set.add(t));
    (r.failing_tasks || []).forEach(t => set.add(t));
  }
  // Union view for any caller that still wants both
  lifecycleTaskUniverseSet = new Set([
    ...lifecycleUniversesByCorpus.draft,
    ...lifecycleUniversesByCorpus.shipped,
  ]);
  lifecycleTaskUniverse = lifecycleTaskUniverseSet.size;
}

// Pick the right universe set for a given stage
function universeForStage(stageId) {
  const corpus = stageCorpus[stageId] || "draft";
  return lifecycleUniversesByCorpus[corpus] || new Set();
}

// Coverage classification for a per-task check.
//   "full"      — passing + failing covers (close to) the whole task universe
//   "partial"   — only a fraction of the universe was evaluable (e.g. coverage gap)
//   "none"      — no per-task data at all (treat as N/A for per-task scope)
function coverageFor(result, stageId) {
  const universeSet = stageId ? universeForStage(stageId) : lifecycleTaskUniverseSet;
  const universe = universeSet.size;
  const pass = (result?.passing_tasks || []).length;
  const fail = (result?.failing_tasks || []).length;
  const evaluated = pass + fail;
  if (evaluated === 0) return { kind: "none", evaluated: 0, universe };
  if (universe > 0 && evaluated < universe * 0.5) {
    return { kind: "partial", evaluated, universe };
  }
  return { kind: "full", evaluated, universe };
}

function renderLifecycleSidebar() {
  const sb = el("sidebar");
  sb.innerHTML = "";
  if (!lifecycleData || !lifecycleData.phases) {
    sb.appendChild(create("div", "empty muted", "lifecycle_rubric.yaml not loaded"));
    return;
  }

  // Overall counts across all stages
  const allStages = lifecycleData.phases.flatMap(p => p.stages || []);
  const overall = aggregateStageStatus(allStages);

  // "Overview" — clears the selected stage so the evidence panel collapses
  // back to its "click any stage…" prompt, leaving just the DAG.
  const allItem = create("div", `sidebar-item ${pipelineSelectedStage == null ? "active" : ""}`);
  allItem.appendChild(create("span", "sidebar-label", "Overview"));
  allItem.appendChild(stageStatusBadge(overall));
  allItem.addEventListener("click", () => {
    pipelineSelectedStage = null;
    pipelineExpandedChecks = new Set();
    renderForCurrentMode();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  sb.appendChild(allItem);

  for (const phase of lifecycleData.phases) {
    sb.appendChild(create("div", "sidebar-section", phase.name));
    for (const stage of phase.stages || []) {
      const isActive = pipelineSelectedStage && pipelineSelectedStage.stage.id === stage.id;
      const item = create("div", `sidebar-item ${isActive ? "active" : ""}`);
      const labelRow = create("div", "sidebar-label");
      if (stage.code) labelRow.appendChild(create("span", "sidebar-stage-code", stage.code + " "));
      labelRow.appendChild(document.createTextNode(stage.name));
      item.appendChild(labelRow);
      const agg = aggregateStageStatus([stage]);
      item.appendChild(stageStatusBadge(agg));
      // Stage summary as a small second line below the label
      if (stage.summary) {
        const sum = create("div", "sidebar-stage-summary", stage.summary);
        sum.style.gridColumn = "1 / -1";
        item.appendChild(sum);
      }
      item.addEventListener("click", () => {
        pipelineSelectedStage = { phase, stage };
        pipelineExpandedChecks = new Set();  // start with all checks collapsed
        renderForCurrentMode();
        setTimeout(() => {
          const ev = el("pipeline-evidence");
          if (ev) ev.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 0);
      });
      sb.appendChild(item);
    }
  }
}

function aggregateStageStatus(stages) {
  let pass = 0, fail = 0, mixed = 0, na = 0, unknown = 0;
  for (const stage of stages) {
    for (const check of stage.checks || []) {
      const r = getLifecycleResultForCheck(stage.id, check.id);
      const s = deriveStatus(check, r);
      if (s === "pass") pass++;
      else if (s === "fail") fail++;
      else if (s === "partial-split") mixed++;
      else if (s === "partial-coverage" || s === "na") na++;
      else unknown++;
    }
  }
  return { pass, fail, mixed, na, unknown, total: pass + fail + mixed + na + unknown };
}

function stageStatusBadge(agg) {
  const wrap = create("span", "sidebar-stage-badge");
  if (agg.unknown === agg.total) {
    wrap.appendChild(create("span", "stage-badge-mini status-unknown", String(agg.total)));
    return wrap;
  }
  if (agg.pass)    wrap.appendChild(create("span", "stage-badge-mini status-pass", `${agg.pass}✓`));
  if (agg.mixed)   wrap.appendChild(create("span", "stage-badge-mini status-partial", `${agg.mixed}~`));
  if (agg.fail)    wrap.appendChild(create("span", "stage-badge-mini status-fail", `${agg.fail}✗`));
  if (agg.na)      wrap.appendChild(create("span", "stage-badge-mini status-na", `${agg.na} n/a`));
  if (agg.unknown && (agg.pass || agg.fail || agg.mixed || agg.na)) {
    wrap.appendChild(create("span", "stage-badge-mini status-unknown", `${agg.unknown}?`));
  }
  return wrap;
}

function renderLifecyclePage() {
  const page = el("page");
  page.innerHTML = "";
  if (!lifecycleData || !lifecycleData.phases) {
    page.appendChild(create("div", "empty muted", "lifecycle_rubric.yaml not loaded"));
    return;
  }

  page.appendChild(renderLifecycleFilters());

  // Build (phase, stage, filteredChecks) tuples; only render stages whose
  // filtered check list is non-empty — keeps the screen focused on matches.
  const filtersActive = lifecycleScopeFilter !== "all"
    || lifecyclePassFilter !== "all"
    || lifecycleStageId != null;

  const stageBlocks = [];
  for (const phase of lifecycleData.phases) {
    for (const stage of phase.stages || []) {
      if (lifecycleStageId != null && lifecycleStageId !== stage.id) continue;
      const checks = filterChecks(stage.checks || [], stage.id);
      if (filtersActive && checks.length === 0) continue;  // hide non-matching stages
      stageBlocks.push({ phase, stage, checks });
    }
  }

  if (!stageBlocks.length) {
    page.appendChild(create("div", "empty muted", "No checks match the current filters."));
    return;
  }

  for (const { phase, stage, checks } of stageBlocks) {
    page.appendChild(renderStageBlock(phase, stage, checks));
  }
}

function filterChecks(checks, stageId) {
  return (checks || []).filter(c => {
    if (lifecycleScopeFilter !== "all" && c.scope !== lifecycleScopeFilter) return false;
    if (lifecyclePassFilter !== "all") {
      const result = getLifecycleResultForCheck(stageId, c.id);
      const status = deriveStatus(c, result);
      return status === lifecyclePassFilter;
    }
    return true;
  });
}

function renderLifecycleFilters() {
  const bar = create("div", "lc-filterbar");

  // Scope filter chips
  const scopeWrap = create("div", "lc-filter-group");
  scopeWrap.appendChild(create("span", "lc-filter-label", "Scope:"));
  ["all", "per-task", "per-stage", "per-batch", "gym-wide"].forEach(s => {
    const chip = create("button", `lc-chip ${lifecycleScopeFilter === s ? "active" : ""}`, s);
    chip.addEventListener("click", () => {
      lifecycleScopeFilter = s;
      renderLifecyclePage();
    });
    scopeWrap.appendChild(chip);
  });
  bar.appendChild(scopeWrap);

  // Pass/Fail filter (operates on the derived rich status)
  const passWrap = create("div", "lc-filter-group");
  passWrap.appendChild(create("span", "lc-filter-label", "Status:"));
  [
    ["all", "All"],
    ["pass", "Passing"],
    ["partial-split", "Mixed"],
    ["partial-coverage", "Partial coverage"],
    ["fail", "Failing"],
    ["na", "N/A"],
    ["unknown", "Not evaluated"],
  ].forEach(([val, lbl]) => {
    const chip = create("button", `lc-chip ${lifecyclePassFilter === val ? "active" : ""}`, lbl);
    chip.addEventListener("click", () => {
      lifecyclePassFilter = val;
      renderLifecyclePage();
    });
    passWrap.appendChild(chip);
  });
  bar.appendChild(passWrap);

  return bar;
}

function renderStageBlock(phase, stage, checks) {
  const block = create("section", "lc-stage-block");

  const header = create("div", "lc-stage-header");
  header.appendChild(create("div", "lc-stage-phase", phase.name));
  const nameRow = create("div", "lc-stage-name-row");
  if (stage.code) nameRow.appendChild(create("span", "lc-stage-code", stage.code));
  nameRow.appendChild(create("h2", "lc-stage-name", stage.name));
  header.appendChild(nameRow);
  if (stage.summary) header.appendChild(create("p", "lc-stage-summary", stage.summary));
  block.appendChild(header);

  for (const check of checks) {
    block.appendChild(renderCheckCard(stage, check));
  }
  return block;
}

function renderCheckCard(stage, check) {
  const card = create("div", "lc-check-card");
  const result = getLifecycleResultForCheck(stage.id, check.id);
  const status = deriveStatus(check, result);
  const coverage = check.scope === "per-task" ? coverageFor(result, stage.id) : null;

  // Status pill (with tooltip)
  const statusPill = create("span", `lc-status-pill ${statusClass(status)}`, statusLabel(status));
  statusPill.title = statusTooltip(status, result, coverage);

  // Scope tag
  const scopeTag = create("span", `lc-scope-tag scope-${check.scope}`, check.scope);

  // Header (clickable, expandable)
  const header = create("div", "lc-check-header");
  if (check.code) {
    const codeBadge = create("span", "lc-check-code", check.code);
    codeBadge.title = `Stage code: ${check.code} — derived from stage position + check index`;
    header.appendChild(codeBadge);
  }
  // Deterministic marker — check is scored by a Python script under audit/scripts/
  if (check.script) {
    const det = create("span", "lc-check-script", "⚙");
    det.title = `Deterministic — evaluated by ${check.script}. No LLM judgment used.`;
    header.appendChild(det);
  }
  header.appendChild(statusPill);
  header.appendChild(scopeTag);
  header.appendChild(create("span", "lc-check-what", check.what));

  // Task-count badge: "N✓ M✗ + K n/a" — visible at a glance.
  // Only render for per-task scope WHERE the auditor enumerated tasks.
  // Corpus-wide-evaluated checks (passing_tasks/failing_tasks both null) skip
  // the badge — the level/status pill already says everything.
  if (check.scope === "per-task" && coverage) {
    const enumerated = result && (result.passing_tasks != null || result.failing_tasks != null);
    if (enumerated) {
      const universeSet = universeForStage(stage.id);
      const universeN = universeSet.size;
      const passN = (result.passing_tasks || []).length;
      const failN = (result.failing_tasks || []).length;
      const naN = Math.max(0, universeN - passN - failN);
      const badge = create("span", "lc-task-counts");
      if (passN) badge.appendChild(create("span", "task-count task-count-pass", `${passN}✓`));
      if (failN) badge.appendChild(create("span", "task-count task-count-fail", `${failN}✗`));
      if (naN && universeN > 0) {
        const naBadge = create("span", "task-count task-count-na", `${naN} n/a`);
        naBadge.title = "Not applicable — tasks excluded from this check's evaluation";
        badge.appendChild(naBadge);
      }
      if (passN || failN || naN) header.appendChild(badge);
    }
  }

  const expandKey = `${stage.id}.${check.id}`;
  const expanded = isCheckExpanded(stage, check);
  const caret = create("span", "lc-check-caret", expanded ? "▾" : "▸");
  header.appendChild(caret);
  header.addEventListener("click", () => {
    toggleCheckExpansion(stage, check);
    renderForCurrentMode();  // stay in whichever view (Checks or Pipeline) the user is in
  });
  card.appendChild(header);

  // Expanded detail
  if (expanded) {
    const detail = create("div", "lc-check-detail");

    // Coverage banner — explains what the status means in plain English
    const banner = renderCoverageBanner(check, result, status, coverage, stage.id);
    if (banner) detail.appendChild(banner);

    if (check.script) {
      const sb = create("div", "lc-script-banner",
        `⚙ Deterministic — evaluated by `);
      const code = create("code", null, check.script);
      sb.appendChild(code);
      sb.appendChild(document.createTextNode(". This result is reproducible from the gym filesystem; no LLM judgment was used."));
      detail.appendChild(sb);
    }

    if (check.why) {
      detail.appendChild(create("div", "lc-detail-title", "Why it matters"));
      detail.appendChild(create("p", "lc-detail-body", check.why));
    }
    if (check.suggestion) {
      detail.appendChild(create("div", "lc-detail-title", "Suggestion when failing"));
      detail.appendChild(create("p", "lc-detail-body", check.suggestion));
    }

    // Task lists block — always three lists (passing/not passing/N/A) for
    // per-task checks; only non-empty lists for other scopes.
    if (check.scope === "per-task" || (result && (result.failing_tasks?.length || result.passing_tasks?.length))) {
      detail.appendChild(renderTaskListsBlock(result, check, stage.id));
    }

    if (!result) {
      const note = create("div", "lc-note muted", "Not yet evaluated against this rubric. Run an audit to populate pass/fail data.");
      detail.appendChild(note);
    }
    card.appendChild(detail);
  }

  return card;
}

function renderCoverageBanner(check, result, status, coverage, stageId) {
  // Render a single explanatory line so the reader isn't left guessing what
  // the status pill actually means. Only meaningful for per-task checks —
  // for per-stage / per-batch / gym-wide the level alone says everything.
  if (!result) return null;
  if (check.scope !== "per-task") return null;

  // Corpus-wide evaluation (auditor didn't enumerate tasks)
  const enumerated = result.passing_tasks != null || result.failing_tasks != null;
  if (!enumerated) {
    const lvlMsg = ({
      pass: "Auditor evaluated this corpus-wide and the invariant holds — no per-task enumeration was produced.",
      fail: "Auditor evaluated this corpus-wide and the invariant fails. No per-task list of offenders is available.",
      "partial-coverage": "Auditor evaluated this corpus-wide; the result is partial and no per-task list was produced.",
    })[status];
    return create("div", `lc-banner banner-${status}`, lvlMsg || "Evaluated corpus-wide.");
  }
  const passing = result.passing_tasks || [];
  const failing = result.failing_tasks || [];
  const passN = passing.length;
  const failN = failing.length;
  // Use the corpus-scoped universe (already in `coverage.universe`) rather
  // than the union — draft-corpus checks should not count shipped tasks
  // as N/A and vice versa.
  const uni = coverage?.universe ?? lifecycleTaskUniverse;
  const evaluated = passN + failN;
  const notApplicable = Math.max(0, uni - evaluated);

  // Detect phantom relabels: drafts that appear in the universe under two
  // labels (e.g. `task_003` and bare `003`), because the Stage 4 audit
  // agent emitted bare-numeric IDs while every other stage used the
  // `task_NNN` form. The de-duplication never happened at synthesis time.
  const phantomInfo = computePhantomCounts(passing, failing, result);

  let msg;
  switch (status) {
    case "pass":
      msg = `All ${passN} applicable tasks passed.`;
      if (notApplicable) msg += ` ${notApplicable} tasks landed in Not Applicable.`;
      break;
    case "fail":
      msg = `All ${failN} applicable tasks failed.`;
      if (notApplicable) msg += ` ${notApplicable} tasks landed in Not Applicable.`;
      break;
    case "partial-split":
      msg = `Mixed result — ${passN} of ${evaluated} applicable tasks passed; ${failN} failed.`;
      if (notApplicable) msg += ` ${notApplicable} additional tasks landed in Not Applicable.`;
      break;
    case "partial-coverage":
      msg = `Could only evaluate ${evaluated} of ~${uni} tasks for this check — coverage gap, not a true pass/fail split. The ${evaluated} task(s) it did evaluate: ${passN} passed, ${failN} failed.`;
      break;
    case "na":
      msg = `Not applicable: this check has no evaluable tasks in the current corpus.`;
      break;
    default:
      msg = "Not yet evaluated.";
  }

  const wrap = create("div", `lc-banner banner-${status}`);

  // Origin line — names the corpus + folder the evaluated tasks come from.
  // Lets the reader know whether they are looking at drafts mid-build or
  // shipped tasks past Phase 4.
  const info = stageId && stageInfo[stageId];
  if (info) {
    const corpusLabel = info.corpus === "shipped" ? "shipped tasks" : "draft tasks";
    const origin = create("p", "lc-banner-line lc-banner-origin");
    origin.innerHTML =
      `<strong>Where these tasks come from:</strong> this check evaluates ${corpusLabel} under ` +
      `<code>${info.corpus_path}</code>. Every ID below (passing, not passing, or N/A) refers to a folder ` +
      `or YAML file at that path.`;
    wrap.appendChild(origin);
  }

  wrap.appendChild(create("p", "lc-banner-line", msg));

  // Phantom explanation paragraph — only when the N/A bucket has phantoms.
  if (notApplicable > 0 && phantomInfo.phantomCount > 0) {
    const expl = create("p", "lc-banner-line lc-banner-note");
    expl.innerHTML =
      `<strong>About the Not Applicable count:</strong> of the ${notApplicable} tasks listed as N/A, ` +
      `<strong>${phantomInfo.phantomCount}</strong> are <em>phantom relabels</em>, not truly missing data. ` +
      `The Stage 4 audit agent (re-runs <code>_has_cycle</code> on the edges DAG) recorded task IDs as bare numerics like <code>003</code>, ` +
      `while every other audit step used the canonical <code>task_003</code> form. Both labels point to the same draft on disk under ` +
      `<code>task-designer/drafts/task_003/</code>, but the audit synthesis didn't deduplicate them — so the same draft appears in the ` +
      `universe twice under different labels. ` +
      `After collapsing phantoms, the real N/A count for this check is <strong>${phantomInfo.trueNa}</strong> ` +
      `(tasks that genuinely never reached this stage). Phantom examples: ${phantomInfo.examples.slice(0, 3).map(e => `<code>${e}</code>`).join(", ")}${phantomInfo.examples.length > 3 ? ', …' : ''}.`;
    wrap.appendChild(expl);
  }

  return wrap;
}

// For a per-task check, walk the N/A list and figure out how many entries
// are phantom relabels of tasks that ARE in the evaluated set under a
// different ID convention.
function computePhantomCounts(passing, failing, result) {
  // Build evaluated set
  const evaluated = new Set([...passing, ...failing]);
  // We need the stage ID's universe — caller already scoped it via coverageFor,
  // but we recompute the same set here for the N/A list.
  // Heuristic for "phantom sibling": numeric ↔ `task_<numeric>`.
  const universeSet = lifecycleTaskUniverseSet;  // safe upper bound — even if a phantom isn't in the stage's corpus, it doesn't count
  // Actually we want the stage's corpus universe; the caller passes `coverage`
  // which we don't have direct access to here. Fall back to scanning the
  // universe and just classifying any ID that has an evaluated sibling.
  let phantomCount = 0;
  let trueNa = 0;
  const examples = [];
  for (const t of universeSet) {
    if (evaluated.has(t)) continue;  // not in N/A
    const sibling = phantomSibling(t);
    if (sibling && evaluated.has(sibling)) {
      phantomCount++;
      if (examples.length < 6) examples.push(`${t} ↔ ${sibling}`);
    } else {
      trueNa++;
    }
  }
  return { phantomCount, trueNa, examples };
}

function phantomSibling(taskId) {
  // bare-numeric → task_<id>
  if (/^\d+$/.test(taskId)) return `task_${taskId}`;
  // task_<numeric> → bare <numeric>
  const m = taskId.match(/^task_(\d+)$/);
  if (m) return m[1];
  return null;
}

function renderTaskListsBlock(result, check, stageId) {
  const wrap = create("div", "lc-task-lists");
  const passing = result?.passing_tasks || [];
  const failing = result?.failing_tasks || [];

  // N/A list = (corpus-scoped universe) − passing − failing. Using the
  // per-corpus universe prevents draft-corpus checks from listing shipped
  // tasks as N/A and vice versa.
  const universeSet = stageId ? universeForStage(stageId) : lifecycleTaskUniverseSet;
  const evaluated = new Set([...passing, ...failing]);
  const naTasks = [...universeSet].filter(t => !evaluated.has(t)).sort();

  // Per-task scope → always render all three lists, even when empty, so the
  // reader sees what's missing rather than having to guess.
  if (check && check.scope === "per-task") {
    // Corpus-wide evaluation (no per-task enumeration) — task lists are misleading.
    const enumerated = result && (result.passing_tasks != null || result.failing_tasks != null);
    if (!enumerated) {
      wrap.appendChild(create("div", "muted",
        "No per-task list available — auditor evaluated this check at the corpus level. See the evidence section above."));
      return wrap;
    }
    wrap.appendChild(renderTaskList(
      "Passing tasks", passing, "passing",
      "tasks that satisfied this check"
    ));
    wrap.appendChild(renderTaskList(
      "Not passing tasks", failing, "failing",
      "tasks that violated this check"
    ));
    const naReason = (check.na_reason || "tasks excluded from this check (no relevant entity, no grounding, wrong type, etc.)").trim();
    wrap.appendChild(renderTaskList(
      "Not applicable", naTasks, "na", naReason
    ));
    return wrap;
  }

  // Non-per-task scope — only show non-empty lists, no synthesized N/A
  if (passing.length) wrap.appendChild(renderTaskList("Passing tasks", passing, "passing", "tasks that satisfied this check"));
  if (failing.length) wrap.appendChild(renderTaskList("Not passing tasks", failing, "failing", "tasks that violated this check"));
  if (!passing.length && !failing.length) {
    wrap.appendChild(create("div", "muted", "This check is gym-wide, not per-task — no task list applies."));
  }
  return wrap;
}

function renderTaskList(label, ids, kind, explanation) {
  const det = document.createElement("details");
  det.className = `lc-tasklist lc-tasklist-${kind}`;
  det.open = true;  // expand by default
  const sum = document.createElement("summary");
  sum.className = "lc-tasklist-summary";
  sum.innerHTML = "";
  sum.appendChild(create("span", "lc-tasklist-title", `${label} (${ids.length})`));
  if (explanation) sum.appendChild(create("span", "lc-tasklist-help", ` — ${explanation}`));
  det.appendChild(sum);
  if (ids.length === 0) {
    det.appendChild(create("div", "lc-tasklist-empty muted", "(none)"));
  } else {
    const list = create("ul", "lc-tasklist-list");
    ids.forEach(t => list.appendChild(create("li", "lc-task-id", t)));
    det.appendChild(list);
  }
  return det;
}

// Derive a richer status from the raw level + scope + coverage signal.
// Returns one of: pass | partial-split | partial-coverage | fail | na | unknown.
// "partial-split"    → some tasks passed AND some tasks failed
// "partial-coverage" → not enough applicable tasks to evaluate fully
// "na"               → no result OR explicit skipped OR per-task check with zero applicable tasks
function deriveStatus(check, result) {
  if (!result || result.level == null) return "unknown";
  if (result.level === "skipped") return "na";

  if (check.scope === "per-task") {
    const passList = result.passing_tasks;
    const failList = result.failing_tasks;
    // Auditor evaluated corpus-wide (didn't enumerate either list) — trust the level.
    const enumerated = passList != null || failList != null;
    if (!enumerated) {
      if (result.level === "present") return "pass";
      if (result.level === "absent") return "fail";
      if (result.level === "partial") return "partial-coverage";
    }
    const pass = (passList || []).length;
    const fail = (failList || []).length;
    if (pass === 0 && fail === 0) return "na";              // no applicable tasks
    if (pass > 0 && fail > 0) return "partial-split";       // genuine mix
    if (result.level === "partial") return "partial-coverage";  // partial label, but no split
  }
  if (result.level === "present") return "pass";
  if (result.level === "partial") return "partial-split";
  return "fail";  // absent
}

function statusClass(status) {
  return ({
    pass: "status-pass",
    "partial-split": "status-partial",
    "partial-coverage": "status-na",
    fail: "status-fail",
    na: "status-na",
    unknown: "status-unknown",
  })[status] || "status-unknown";
}
function statusLabel(status) {
  return ({
    pass: "pass",
    "partial-split": "mixed",
    "partial-coverage": "partial coverage",
    fail: "fail",
    na: "n/a",
    unknown: "not evaluated",
  })[status] || status;
}
function statusTooltip(status, result, coverage) {
  const ev = coverage?.evaluated ?? 0;
  const uni = coverage?.universe ?? 0;
  switch (status) {
    case "pass":             return `All ${ev} evaluated tasks passed`;
    case "partial-split":    return `Mixed: some tasks passed, some failed`;
    case "partial-coverage": return `Only ${ev} of ~${uni} tasks were evaluable; not a true pass/fail split`;
    case "fail":             return `All evaluated tasks failed`;
    case "na":               return `Not applicable to any task in this corpus`;
    case "unknown":          return `Not yet evaluated for this session`;
  }
  return "";
}

// ───────────────────────────────────────────────────────────────────
// Pipeline view — phases-as-columns swimlane with clickable stages.
// Selected stage opens an evidence panel below the graph.
// ───────────────────────────────────────────────────────────────────

function renderPipelineSidebar() {
  // Compact sidebar in pipeline mode: just a legend.
  const sb = el("sidebar");
  sb.innerHTML = "";

  sb.appendChild(create("div", "sidebar-section", "Pipeline legend"));
  const legend = create("div", "pipeline-legend");
  [
    { cls: "stage-pass",    label: "All checks pass" },
    { cls: "stage-mixed",   label: "Mixed (some pass / some fail)" },
    { cls: "stage-fail",    label: "Has failing checks" },
    { cls: "stage-na",      label: "Only N/A or partial coverage" },
    { cls: "stage-unknown", label: "Not evaluated" },
  ].forEach(row => {
    const item = create("div", "pipeline-legend-row");
    item.appendChild(create("span", `pipeline-legend-swatch ${row.cls}`));
    item.appendChild(create("span", null, row.label));
    legend.appendChild(item);
  });
  sb.appendChild(legend);

  sb.appendChild(create("div", "sidebar-section sidebar-section-bottom", "Tip"));
  const tip = create("div", "pipeline-sidebar-tip muted");
  tip.textContent = "Click any stage to inspect its checks + evidence below the graph.";
  sb.appendChild(tip);
}

function renderPipelinePage() {
  const page = el("page");
  page.innerHTML = "";
  if (!lifecycleData || !lifecycleData.phases) {
    page.appendChild(create("div", "empty muted", "lifecycle_rubric.yaml not loaded"));
    return;
  }

  const header = create("div", "pipeline-header");
  header.appendChild(create("h2", "pipeline-title", "Pipeline DAG"));
  header.appendChild(create("p", "pipeline-subtitle muted",
    "Each circle is one lifecycle stage; color = aggregate status. Click any node to inspect its checks below."));
  page.appendChild(header);

  page.appendChild(renderPipelineDAG());
  page.appendChild(renderPipelineEvidence());
}

function renderPipelineDAG() {
  // ── Layout constants ──────────────────────────────────────────────
  const LANE_H = 110;        // height per phase row
  const PAD_Y  = 12;         // top/bottom padding
  const LABEL_W = 150;       // left gutter for phase labels (two-line)
  const CIRCLE_R = 30;
  const SPACING_X = 100;     // horizontal distance between circle centres

  const phases = lifecycleData.phases;
  const maxStages = Math.max(...phases.map(p => (p.stages || []).length));
  const SVG_W = LABEL_W + maxStages * SPACING_X + 24;
  const SVG_H = phases.length * LANE_H + 2 * PAD_Y;

  // Position lookup
  const positions = new Map();
  phases.forEach((phase, phaseIdx) => {
    const stages = phase.stages || [];
    const cy = PAD_Y + phaseIdx * LANE_H + LANE_H / 2 - 8;  // a bit higher to leave label room
    stages.forEach((stage, idx) => {
      const cx = LABEL_W + idx * SPACING_X + SPACING_X / 2;
      positions.set(stage.id, { cx, cy, phase, stage, phaseIdx, idx });
    });
  });

  const NS = "http://www.w3.org/2000/svg";
  const wrap = create("div", "pipeline-dag-wrap");
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${SVG_W} ${SVG_H}`);
  svg.setAttribute("class", "pipeline-dag");
  svg.setAttribute("width", "100%");
  svg.setAttribute("preserveAspectRatio", "xMidYMin meet");

  // Arrowhead defs
  const defs = document.createElementNS(NS, "defs");
  defs.innerHTML = `
    <marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#565f89" />
    </marker>
    <marker id="arrowhead-cross" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#bb9af7" />
    </marker>
  `;
  svg.appendChild(defs);

  // Phase row backgrounds + labels (two lines: short tag + descriptive subtitle)
  phases.forEach((phase, idx) => {
    const y = PAD_Y + idx * LANE_H;
    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("x", 0);
    rect.setAttribute("y", y);
    rect.setAttribute("width", SVG_W);
    rect.setAttribute("height", LANE_H);
    rect.setAttribute("class", `pipeline-dag-lane ${idx % 2 ? "lane-alt" : ""}`);
    svg.appendChild(rect);

    // Vertical divider between label gutter and the DAG
    const div = document.createElementNS(NS, "line");
    div.setAttribute("x1", LABEL_W - 8);
    div.setAttribute("y1", y + 8);
    div.setAttribute("x2", LABEL_W - 8);
    div.setAttribute("y2", y + LANE_H - 8);
    div.setAttribute("class", "pipeline-dag-divider");
    svg.appendChild(div);

    const [tag, subtitle] = phaseLabelLines(phase.name);

    const tagText = document.createElementNS(NS, "text");
    tagText.setAttribute("x", 14);
    tagText.setAttribute("y", y + LANE_H / 2 - 10);
    tagText.setAttribute("class", "pipeline-dag-phase-tag");
    tagText.textContent = tag;
    svg.appendChild(tagText);

    if (subtitle) {
      const subText = document.createElementNS(NS, "text");
      subText.setAttribute("x", 14);
      subText.setAttribute("y", y + LANE_H / 2 + 8);
      subText.setAttribute("class", "pipeline-dag-phase-subtitle");
      subText.textContent = subtitle;
      svg.appendChild(subText);
    }

    // Corpus folder-path badge below the subtitle
    if (phase.corpus_path) {
      const corpusText = document.createElementNS(NS, "text");
      corpusText.setAttribute("x", 14);
      corpusText.setAttribute("y", y + LANE_H / 2 + 24);
      corpusText.setAttribute("class", `pipeline-dag-corpus-path corpus-${phase.corpus || "draft"}`);
      corpusText.textContent = phase.corpus_path;
      // Native SVG tooltip
      const tip = document.createElementNS(NS, "title");
      tip.textContent = `Corpus: ${phase.corpus || "draft"}\nFolder: ${phase.corpus_path}`;
      corpusText.appendChild(tip);
      svg.appendChild(corpusText);
    }
  });

  // Within-phase straight arrows
  phases.forEach(phase => {
    const stages = phase.stages || [];
    for (let i = 0; i < stages.length - 1; i++) {
      const a = positions.get(stages[i].id);
      const b = positions.get(stages[i + 1].id);
      const line = document.createElementNS(NS, "line");
      line.setAttribute("x1", a.cx + CIRCLE_R);
      line.setAttribute("y1", a.cy);
      line.setAttribute("x2", b.cx - CIRCLE_R);
      line.setAttribute("y2", b.cy);
      line.setAttribute("class", "pipeline-dag-edge");
      line.setAttribute("marker-end", "url(#arrowhead)");
      svg.appendChild(line);
    }
  });

  // Cross-phase curved arrows (last stage of phase N → first stage of phase N+1)
  for (let i = 0; i < phases.length - 1; i++) {
    const last = (phases[i].stages || []).slice(-1)[0];
    const first = (phases[i + 1].stages || [])[0];
    if (!last || !first) continue;
    const a = positions.get(last.id);
    const b = positions.get(first.id);
    // S-curve from right-edge of `a` down to left-edge of `b`
    const ax = a.cx + CIRCLE_R, ay = a.cy;
    const bx = b.cx - CIRCLE_R, by = b.cy;
    const midY = (ay + by) / 2;
    const d = `M ${ax} ${ay} C ${ax + 80} ${midY}, ${bx - 80} ${midY}, ${bx} ${by}`;
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", d);
    path.setAttribute("class", "pipeline-dag-edge cross-phase");
    path.setAttribute("fill", "none");
    path.setAttribute("marker-end", "url(#arrowhead-cross)");
    svg.appendChild(path);
  }

  // Stage nodes (circles + inside-code + below-label)
  phases.forEach(phase => {
    for (const stage of phase.stages || []) {
      const pos = positions.get(stage.id);
      const agg = aggregateStageStatus([stage]);
      const status = derivePipelineStageStatus(agg);

      const g = document.createElementNS(NS, "g");
      const isSelected = pipelineSelectedStage && pipelineSelectedStage.stage.id === stage.id;
      g.setAttribute("class", `pipeline-dag-node stage-${status}${isSelected ? " selected" : ""}`);
      g.setAttribute("data-stage-id", stage.id);
      g.style.cursor = "pointer";

      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", pos.cx);
      c.setAttribute("cy", pos.cy);
      c.setAttribute("r", CIRCLE_R);
      g.appendChild(c);

      // Stage code on top half of the circle
      const code = document.createElementNS(NS, "text");
      code.setAttribute("x", pos.cx);
      code.setAttribute("y", pos.cy - 7);
      code.setAttribute("dy", "0.35em");
      code.setAttribute("class", "pipeline-dag-code");
      code.textContent = shortStageCode(stage);
      g.appendChild(code);

      // Counts on the bottom half of the circle — pass/mixed/fail/na, colored
      const countsText = document.createElementNS(NS, "text");
      countsText.setAttribute("x", pos.cx);
      countsText.setAttribute("y", pos.cy + 10);
      countsText.setAttribute("dy", "0.35em");
      countsText.setAttribute("class", "pipeline-dag-counts");
      let firstSegment = true;
      const addSeg = (n, sym, klass) => {
        if (!n) return;
        if (!firstSegment) {
          countsText.appendChild(document.createTextNode(" "));
        }
        const t = document.createElementNS(NS, "tspan");
        t.setAttribute("class", klass);
        t.textContent = `${n}${sym}`;
        countsText.appendChild(t);
        firstSegment = false;
      };
      addSeg(agg.pass,  "✓", "count-pass");
      addSeg(agg.mixed, "~", "count-mixed");
      addSeg(agg.fail,  "✗", "count-fail");
      if (firstSegment) {
        // Nothing evaluated at all — show a placeholder
        const t = document.createElementNS(NS, "tspan");
        t.setAttribute("class", "count-na");
        t.textContent = "—";
        countsText.appendChild(t);
      }
      g.appendChild(countsText);

      // Stage name under the circle
      const label = document.createElementNS(NS, "text");
      label.setAttribute("x", pos.cx);
      label.setAttribute("y", pos.cy + CIRCLE_R + 14);
      label.setAttribute("class", "pipeline-dag-label");
      label.textContent = shortStageName(stage.name);
      g.appendChild(label);

      // Hover tooltip with full name + counts + na
      const tip = document.createElementNS(NS, "title");
      tip.textContent = `${stage.name}\n${agg.pass}✓ ${agg.mixed}~ ${agg.fail}✗ ${agg.na} n/a`;
      g.appendChild(tip);

      g.addEventListener("click", () => {
        pipelineSelectedStage = { phase, stage };
        pipelineExpandedChecks = new Set();  // start with all checks collapsed
        renderPipelinePage();
        setTimeout(() => {
          const ev = el("pipeline-evidence");
          if (ev) ev.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 0);
      });

      svg.appendChild(g);
    }
  });

  wrap.appendChild(svg);
  return wrap;
}

function shortPhaseName(name) {
  // Kept for any non-DAG callers; the DAG uses phaseLabelLines() below.
  const m = name.match(/^(Phase \d+|Runtime)/);
  return m ? m[1] : name.slice(0, 16);
}

// Split a full phase name into a two-line label for the DAG gutter.
//   "Phase 1 — Skeleton (procedural)" → ["PHASE 1", "Skeleton (procedural)"]
//   "Runtime — In-container instantiation" → ["RUNTIME", "In-container"]
function phaseLabelLines(name) {
  const parts = name.split("—").map(s => s.trim());
  const head = (parts[0] || "").toUpperCase();
  let sub = parts[1] || "";
  if (sub.length > 22) sub = sub.slice(0, 22).replace(/\s+\S*$/, "") + "…";
  return [head, sub];
}

function shortStageCode(stage) {
  const id = stage.id || "";
  if (id.startsWith("substages_5b_5e")) return "5b-e";
  if (id.startsWith("post_hydration_hint_gate")) return "Hint";
  if (id.startsWith("reward_lint_fix_loop")) return "Lint";
  if (id.startsWith("final_audit_opus")) return "Final";
  if (/^stage_/.test(id)) {
    const m = id.match(/^stage_(\d+[a-z]?)/);
    if (m) return "S" + m[1];
  }
  if (/^r\d/.test(id)) {
    const m = id.match(/^r(\d+)/);
    if (m) return "R" + m[1];
  }
  return stage.name.slice(0, 4);
}

function shortStageName(name) {
  // "Stage 1 — Objective" → "Objective" (trim leading "Stage N —")
  const m = name.match(/^[^—]*—\s*(.+)$/);
  const s = m ? m[1] : name;
  return s.length > 18 ? s.slice(0, 18) + "…" : s;
}

function derivePipelineStageStatus(agg) {
  // Aggregate stage status — drives the card's border color.
  if (agg.fail > 0) return "fail";
  if (agg.mixed > 0) return "mixed";
  if (agg.pass > 0) return "pass";
  if (agg.na > 0) return "na";
  return "unknown";
}

function renderPipelineEvidence() {
  const panel = create("section", "pipeline-evidence");
  panel.id = "pipeline-evidence";

  if (!pipelineSelectedStage) {
    panel.appendChild(create("div", "pipeline-evidence-empty muted",
      "Click any stage above to inspect its checks and evidence."));
    return panel;
  }

  const { phase, stage } = pipelineSelectedStage;
  const header = create("div", "pipeline-evidence-header");
  header.appendChild(create("div", "pipeline-evidence-phase", phase.name));
  const nameRow = create("div", "lc-stage-name-row");
  if (stage.code) nameRow.appendChild(create("span", "lc-stage-code", stage.code));
  nameRow.appendChild(create("h2", "pipeline-evidence-stage", stage.name));
  header.appendChild(nameRow);
  if (stage.summary) header.appendChild(create("p", "pipeline-evidence-summary muted", stage.summary));
  panel.appendChild(header);

  // Pipeline mode: every check starts collapsed when a node is picked. The
  // user expands the specific checks they want; their choices persist until
  // a different stage is selected.
  for (const check of stage.checks || []) {
    panel.appendChild(renderCheckCard(stage, check));
  }
  return panel;
}

// ─── helpers ────────────────────────────────────────────────────────
async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

boot();
