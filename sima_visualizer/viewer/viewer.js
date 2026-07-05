"use strict";

/* ---------- tiny DOM helper ---------- */
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") el.className = v;
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined) el.setAttribute(k, v);
    }
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    el.append(c.nodeType ? c : document.createTextNode(c));
  }
  return el;
}

/* ---------- vocabulary ---------- */
const PHASE_LABEL = {
  register: "register", init: "init", timestep_init: "timestep_init",
  run: "run", timestep_final: "timestep_final", final: "final",
};
const INTENT_TITLE = {
  in: "read (intent in)",
  inout: "read & modified (intent inout)",
  out: "produced / overwritten (intent out)",
};
const ORIGIN_META = {
  registry:    { label: "registry",    color: "var(--o-registry)" },
  host:        { label: "host model",  color: "var(--o-host)" },
  namelist:    { label: "namelist",    color: "var(--o-namelist)" },
  scheme:      { label: "scheme",      color: "var(--o-scheme)" },
  constituent: { label: "constituent", color: "var(--o-constituent)" },
  framework:   { label: "framework",   color: "var(--o-framework)" },
  default:     { label: "default",     color: "var(--o-framework)" },
  unknown:     { label: "unknown",     color: "var(--o-framework)" },
};
const STORAGE_LABEL = {
  host: "host", suite: "suite-internal", group_local: "group-local",
  constituent: "constituent array", framework: "framework",
  framework_allocated: "framework-allocated", default: "local default",
  "": "—",
};
const SECTIONS = [
  ["timeloop", "Time loop"],
  ["startup", "Startup"],
  ["shutdown", "Shutdown"],
  ["all", "All phases"],
];

const state = {
  view: "suite",          // 'suite' | 'trace'
  section: "timeloop",
  expanded: new Set(),    // call ids
  varSel: null,
  varQuery: "",
  varFilter: "all",       // origin kind filter in trace list
};

const VARS_SORTED = Object.keys(DATA.variables).sort();

function groupDisplayName(name) {
  const prefix = DATA.meta.suite + "_";
  return name.startsWith(prefix) ? name.slice(prefix.length) : name;
}

function originDetail(origin) {
  switch (origin.kind) {
    case "registry": {
      const bits = [];
      if (origin.ic_names) bits.push("ic input: " + origin.ic_names.join(", "));
      if (origin.init_value) bits.push("initial value = " + origin.init_value);
      if (!bits.length) bits.push("registry variable (module " + origin.module + ")");
      return bits.join(" · ");
    }
    case "host": return "set by host model (module " + origin.module + ")";
    case "namelist": return "namelist parameter of scheme " + origin.scheme;
    case "scheme": return "first produced by " + origin.scheme + " (" + PHASE_LABEL[origin.phase] + ")";
    case "constituent": return "constituent (registered at runtime)";
    case "framework": return "provided by the CCPP framework / host cap";
    case "default": return "scheme default value";
    default: return "";
  }
}

function originBadge(origin) {
  const m = ORIGIN_META[origin.kind] || ORIGIN_META.unknown;
  return h("span", { class: "badge", title: originDetail(origin) },
    h("span", { class: "dot", style: "background:" + m.color }), m.label);
}

function intentBadge(intent) {
  return h("span", { class: "intent " + intent, title: INTENT_TITLE[intent] || intent }, intent);
}

/* ---------- navigation ---------- */
function render() {
  document.getElementById("view-root").replaceChildren(
    state.view === "suite" ? renderSuiteView() : renderTraceView());
  for (const btn of document.querySelectorAll(".tabs button"))
    btn.classList.toggle("active", btn.dataset.view === state.view);
}

function gotoVar(std) {
  state.view = "trace";
  state.varSel = std;
  location.hash = "v/" + encodeURIComponent(std);
  render();
  window.scrollTo({ top: 0 });
  const sel = document.querySelector(".vl-item.sel");
  if (sel) sel.scrollIntoView({ block: "center" });
}

function gotoCall(callId) {
  const call = DATA.calls[callId];
  const group = DATA.groups.find(g => g.name === call.group);
  state.view = "suite";
  if (state.section !== "all" && group && group.section !== state.section)
    state.section = group.section;
  state.expanded.add(callId);
  location.hash = "s/" + encodeURIComponent(call.scheme);
  render();
  const card = document.querySelector('[data-call-id="' + callId + '"]');
  if (card) {
    card.scrollIntoView({ block: "center" });
    card.classList.add("flash");
    setTimeout(() => card.classList.remove("flash"), 1600);
  }
}

function gotoScheme(name) {
  const call = DATA.calls.find(c => c.scheme === name);
  if (call) gotoCall(call.id);
}

/* ---------- suite view ---------- */
function schemeCard(node) {
  if (node.call === null) {
    return h("div", { class: "scheme-card ghost" },
      h("div", { class: "card-head" },
        h("span", { class: "tw" }, ""),
        h("span", { class: "sname" }, node.name),
        h("span", { class: "ghost-note" }, "no body in this phase")));
  }
  const call = DATA.calls[node.call];
  const open = state.expanded.has(call.id);
  const counts = { in: 0, inout: 0, out: 0 };
  for (const a of call.args) counts[a.intent] = (counts[a.intent] || 0) + 1;

  const head = h("button", {
    class: "card-head",
    onclick: () => { open ? state.expanded.delete(call.id) : state.expanded.add(call.id); render(); },
    "aria-expanded": String(open),
  },
    h("span", { class: "tw" }, open ? "▼" : "▶"),
    h("span", { class: "sname" }, call.scheme),
    h("span", { class: "ghost-note" }, call.subroutine !== call.scheme ? call.subroutine : ""),
    h("span", { class: "counts" },
      ...["in", "inout", "out"].filter(i => counts[i]).map(i =>
        h("span", { class: "chip-count", title: counts[i] + " × intent " + i },
          h("span", { class: "sw", style: "background:var(--" + (i === "in" ? "read" : i === "inout" ? "modified" : "produced") + ")" }),
          String(counts[i])))));

  const card = h("div", { class: "scheme-card", dataset: { callId: String(call.id) } }, head);
  if (open) {
    card.append(h("table", { class: "args-table" },
      h("thead", null, h("tr", null,
        h("th", null, "intent"), h("th", null, "local name"),
        h("th", null, "standard name"), h("th", null, "units"))),
      h("tbody", null, ...call.args.map(a =>
        h("tr", null,
          h("td", null, intentBadge(a.intent)),
          h("td", null, h("span", { class: "local" }, a.local)),
          h("td", { class: "std" },
            h("span", { class: "link", onclick: () => gotoVar(a.std) }, a.std)),
          h("td", { class: "units" }, DATA.variables[a.std] ? DATA.variables[a.std].units : ""))))));
  }
  return card;
}

function renderItems(items) {
  return items.map(node =>
    node.kind === "subcycle"
      ? h("div", { class: "subcycle-box" },
          h("p", { class: "sub-label" }, "subcycle ×" + node.loop),
          ...renderItems(node.items))
      : schemeCard(node));
}

function groupBox(group) {
  const nCalls = DATA.calls.filter(c => c.group === group.name).length;
  return h("div", { class: "group-box" },
    h("div", { class: "group-head" },
      h("span", { class: "phase-chip" }, PHASE_LABEL[group.phase]),
      h("span", { class: "gname" }, groupDisplayName(group.name)),
      h("span", { class: "gcount" }, nCalls + " scheme call" + (nCalls === 1 ? "" : "s"))),
    h("div", { class: "group-body" },
      group.items.length ? renderItems(group.items)
                         : h("p", { class: "empty" }, "no schemes in this phase")));
}

function renderSuiteView() {
  const root = h("div", null);
  const filter = h("div", { class: "section-filter" },
    ...SECTIONS.map(([key, label]) =>
      h("button", {
        class: state.section === key ? "active" : "",
        onclick: () => { state.section = key; render(); },
      }, label)));
  const visibleCalls = DATA.groups
    .filter(g => state.section === "all" || g.section === state.section)
    .flatMap(g => DATA.calls.filter(c => c.group === g.name).map(c => c.id));
  const tools = h("div", { class: "expand-tools" },
    h("button", { onclick: () => { visibleCalls.forEach(id => state.expanded.add(id)); render(); } }, "expand all"),
    h("button", { onclick: () => { state.expanded.clear(); render(); } }, "collapse all"));
  root.append(h("div", null, tools, filter));

  const bySection = { startup: [], timeloop: [], shutdown: [] };
  for (const g of DATA.groups) bySection[g.section].push(g);
  const sectionOrder = ["startup", "timeloop", "shutdown"];
  for (const sec of sectionOrder) {
    if (state.section !== "all" && state.section !== sec) continue;
    if (!bySection[sec].length) continue;
    const label = sec === "startup" ? "startup — once at model start"
                : sec === "timeloop" ? "time loop"
                : "shutdown — once at model end";
    const boxes = bySection[sec].map(groupBox);
    root.append(h("section", { class: "exec-section" },
      h("p", { class: "sec-label" }, label),
      sec === "timeloop" ? h("div", { class: "timeloop-frame" }, ...boxes) : h("div", null, ...boxes)));
  }
  root.append(renderLegend());
  return root;
}

/* ---------- trace view ---------- */
function varListItem(std) {
  const v = DATA.variables[std];
  const m = ORIGIN_META[v.origin.kind] || ORIGIN_META.unknown;
  return h("button", {
    class: "vl-item" + (state.varSel === std ? " sel" : ""),
    onclick: () => gotoVar(std),
  },
    h("span", { class: "dot", style: "background:" + m.color, title: m.label }),
    std);
}

function renderTimeline(v) {
  const wrap = h("div", { class: "timeline" });
  wrap.append(h("div", { class: "tl-row origin-row" },
    h("span", { class: "marker origin" }),
    h("span", null, originDetail(v.origin) || "origin unknown")));
  let lastKey = null;
  for (const t of v.touches) {
    const call = DATA.calls[t.call];
    const key = call.group;
    if (key !== lastKey) {
      // Synthesized non-run groups are named after their phase; only run
      // groups carry an SDF-given name worth repeating.
      const gname = groupDisplayName(call.group);
      wrap.append(h("p", { class: "tl-phase" },
        call.phase === "run"
          ? PHASE_LABEL[call.phase] + " · " + gname
          : PHASE_LABEL[call.phase]));
      lastKey = key;
    }
    wrap.append(h("div", { class: "tl-row" },
      h("span", { class: "marker " + t.intent, title: INTENT_TITLE[t.intent] }),
      h("span", { class: "tl-scheme" },
        h("span", { class: "link", onclick: () => gotoCall(call.id) }, call.scheme)),
      h("span", { class: "tl-local" }, "as ", h("code", null, t.local)),
      intentBadge(t.intent),
      call.subcycle ? h("span", { class: "tl-sub" }, "(in subcycle)") : null));
  }
  return wrap;
}

function renderVarDetail(std) {
  if (!std || !DATA.variables[std])
    return h("div", { class: "var-detail" },
      h("p", { class: "placeholder" }, "Select a quantity to trace its flow through the suite."));
  const v = DATA.variables[std];
  const dims = v.dims.length ? "(" + v.dims.join(", ") + ")" : "scalar";
  const typeStr = v.type + (v.kind ? "(" + v.kind + ")" : "");
  const detail = h("div", { class: "var-detail" },
    h("h2", null, std),
    v.long_name ? h("p", { class: "longname" }, v.long_name) : null,
    h("div", { class: "fact-row" },
      h("span", null, "units ", h("b", null, v.units || "—")),
      h("span", null, "type ", h("b", null, typeStr)),
      h("span", null, "dims ", h("b", { class: "mono" }, dims)),
      h("span", null, "storage ", h("b", null, STORAGE_LABEL[v.storage] ?? v.storage))),
    h("div", { class: "origin-line" }, originBadge(v.origin),
      h("span", null, originDetail(v.origin))));
  if (v.unread_after_write) {
    detail.append(h("div", { class: "note" },
      "Last write is not read again within the suite — the final value is " +
      "consumed by the host model (state for the dycore, history/restart output) or unused."));
  }
  detail.append(renderTimeline(v));
  return detail;
}

function renderTraceView() {
  const q = state.varQuery.toLowerCase();
  const originKinds = [...new Set(VARS_SORTED.map(s => DATA.variables[s].origin.kind))];
  const visible = VARS_SORTED.filter(std => {
    const v = DATA.variables[std];
    if (state.varFilter !== "all" && v.origin.kind !== state.varFilter) return false;
    return !q || std.includes(q) || (v.long_name || "").toLowerCase().includes(q);
  });
  const searchBox = h("input", {
    type: "search", placeholder: "filter quantities…", value: state.varQuery,
    oninput: e => {
      state.varQuery = e.target.value;
      const parent = document.querySelector(".var-list");
      const fresh = renderVarList();
      parent.replaceWith(fresh);
      fresh.querySelector("input").focus();
      const val = fresh.querySelector("input").value;
      fresh.querySelector("input").setSelectionRange(val.length, val.length);
    },
  });

  function renderVarList() {
    return h("div", { class: "var-list" },
      h("div", { class: "vl-tools" }, searchBox),
      h("div", { class: "vl-filters" },
        h("button", {
          class: state.varFilter === "all" ? "active" : "",
          onclick: () => { state.varFilter = "all"; render(); },
        }, "all"),
        ...originKinds.map(k => {
          const m = ORIGIN_META[k] || ORIGIN_META.unknown;
          return h("button", {
            class: state.varFilter === k ? "active" : "",
            onclick: () => { state.varFilter = k; render(); },
          }, h("span", { class: "dot", style: "background:" + m.color }), m.label);
        })),
      h("div", { class: "vl-items" }, ...visible.map(varListItem)),
      h("p", { class: "vl-count" },
        visible.length + " / " + VARS_SORTED.length + " quantities"));
  }

  return h("div", null,
    h("div", { class: "trace-layout" }, renderVarList(), renderVarDetail(state.varSel)),
    renderLegend());
}

/* ---------- legend ---------- */
function renderLegend() {
  return h("div", { class: "legend" },
    h("span", { class: "item" }, intentBadge("in"), "read"),
    h("span", { class: "item" }, intentBadge("inout"), "read & modified"),
    h("span", { class: "item" }, intentBadge("out"), "produced / overwritten"),
    ...Object.entries(ORIGIN_META)
      .filter(([k]) => !["unknown", "default"].includes(k))
      .map(([k, m]) => h("span", { class: "item" },
        h("span", { class: "dot", style: "background:" + m.color + ";width:8px;height:8px;border-radius:50%" }),
        "origin: " + m.label)));
}

/* ---------- global search ---------- */
function setupSearch() {
  const input = document.getElementById("search");
  const results = document.getElementById("search-results");
  const schemeNames = Object.keys(DATA.schemes).sort();

  function close() { results.replaceChildren(); results.style.display = "none"; }
  function show(q) {
    q = q.trim().toLowerCase();
    if (!q) { close(); return; }
    const schemes = schemeNames.filter(s => s.includes(q)).slice(0, 12);
    const vars = VARS_SORTED.filter(s =>
      s.includes(q) || (DATA.variables[s].long_name || "").toLowerCase().includes(q)).slice(0, 25);
    results.replaceChildren();
    if (schemes.length) {
      results.append(h("p", { class: "sr-head" }, "schemes"));
      for (const s of schemes)
        results.append(h("button", { class: "sr-item", onclick: () => { close(); input.value = ""; gotoScheme(s); } },
          s, h("small", null, DATA.schemes[s].module)));
    }
    if (vars.length) {
      results.append(h("p", { class: "sr-head" }, "quantities"));
      for (const s of vars)
        results.append(h("button", { class: "sr-item", onclick: () => { close(); input.value = ""; gotoVar(s); } },
          s, h("small", null, DATA.variables[s].units)));
    }
    if (!schemes.length && !vars.length)
      results.append(h("p", { class: "sr-head" }, "no matches"));
    results.style.display = "block";
  }
  input.addEventListener("input", () => show(input.value));
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") { close(); input.blur(); }
    if (e.key === "Enter") { const first = results.querySelector(".sr-item"); if (first) first.click(); }
  });
  document.addEventListener("click", e => {
    if (!e.target.closest(".search-wrap")) close();
  });
}

/* ---------- boot ---------- */
function boot() {
  const saved = localStorage.getItem("sima-viz-theme");
  if (saved) document.documentElement.dataset.theme = saved;
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches)
    document.documentElement.dataset.theme = "dark";

  const app = document.getElementById("app");
  app.append(
    h("header", null,
      h("h1", null, "quantity flow · ", h("span", { class: "suite-name" }, DATA.meta.suite)),
      h("span", { class: "meta-line" },
        DATA.meta.sdf + " · host: " + DATA.meta.host + " · " +
        DATA.meta.n_schemes + " schemes · " + DATA.meta.n_calls + " calls · " +
        DATA.meta.n_variables + " quantities"),
      h("span", { class: "spacer" }),
      h("nav", { class: "tabs" },
        h("button", { dataset: { view: "suite" }, onclick: () => { state.view = "suite"; render(); } }, "Suite flow"),
        h("button", { dataset: { view: "trace" }, onclick: () => { state.view = "trace"; render(); } }, "Quantity trace")),
      h("span", { class: "search-wrap" },
        h("input", { id: "search", type: "search", placeholder: "search schemes & quantities…" }),
        h("div", { id: "search-results", style: "display:none" })),
      h("button", {
        id: "theme-toggle", title: "toggle light/dark",
        onclick: () => {
          const cur = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
          document.documentElement.dataset.theme = cur;
          localStorage.setItem("sima-viz-theme", cur);
        },
      }, "◑")),
    h("main", null, h("div", { id: "view-root" })));

  setupSearch();

  const m = location.hash.match(/^#(v|s)\/(.+)$/);
  if (m) {
    const target = decodeURIComponent(m[2]);
    if (m[1] === "v" && DATA.variables[target]) { state.view = "trace"; state.varSel = target; }
    else if (m[1] === "s") { render(); gotoScheme(target); return; }
  }
  render();
}

boot();
