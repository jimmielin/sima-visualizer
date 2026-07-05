#!/usr/bin/env python3
"""Personal sweep script: build a static dogfood site of quantity-flow pages
for every physics suite in a local atmospheric_physics checkout.

Not part of sima_visualizer proper — paths below are hardcoded for local use.
Output (./site) is fully static and self-contained, suitable for GitHub Pages:

    index.html          suite index + global standard-name lookup
    suite_<name>.html   per-suite visualizer pages (deep-linkable via #v/<std>)

The standard-name lookup links straight into each suite's trace view using
the pages' #v/<standard_name> hash routing.
"""

import glob
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date

CAM_SIMA = "/Users/hplin/devel/CAM-SIMA"
ATM_PHYS = "/Users/hplin/devel/atmospheric_physics"
REPO = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(REPO, "site")

sys.path.insert(0, REPO)
# pylint: disable=wrong-import-position
from sima_visualizer.analyze import build_viz_model
from sima_visualizer.emit import _git_rev, _read, write_html
from sima_visualizer.hosts.cam_sima import CamSima, CamSimaError
from sima_visualizer.resolve import ResolveError, resolve_suite, run_capgen_nx


def find_sdfs():
    """(suite_name, 'production'|'test') for every local SDF, sorted."""
    out = []
    for label, direc in [
            ("production", os.path.join(ATM_PHYS, "suites")),
            ("test", os.path.join(ATM_PHYS, "test", "test_suites"))]:
        for path in sorted(glob.glob(os.path.join(direc, "suite_*.xml"))):
            name = os.path.basename(path)[len("suite_"):-len(".xml")]
            out.append((name, label))
    return out


def sweep():
    adapter = CamSima(CAM_SIMA, ATM_PHYS)
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="sima_sweep_")
    suites = []
    quantities = {}
    try:
        for name, source in find_sdfs():
            entry = {"name": name, "source": source,
                     "html": f"suite_{name}.html"}
            workdir = os.path.join(tmp, name)
            os.makedirs(workdir)
            try:
                resolved = resolve_suite(name, adapter.sdf_search_dirs,
                                         adapter.scheme_search_dirs)
                host = adapter.host_inputs(workdir, resolved.xml_files)
                ir = run_capgen_nx(resolved, host,
                                   os.path.join(workdir, "ccpp"))
                viz = build_viz_model(ir, resolved, host, display_roots={
                    "atmospheric_physics": ATM_PHYS, "CAM-SIMA": CAM_SIMA})
                write_html(viz, os.path.join(OUT_DIR, entry["html"]))
                entry["ok"] = True
                for key in ("n_schemes", "n_calls", "n_variables"):
                    entry[key] = viz["meta"][key]
                for std, var in viz["variables"].items():
                    q = quantities.setdefault(std, {
                        "units": var["units"],
                        "long_name": var["long_name"], "suites": {}})
                    if not q["long_name"] and var["long_name"]:
                        q["long_name"] = var["long_name"]
                    q["suites"][name] = var["origin"]["kind"]
                print(f"PASS {name} ({entry['n_calls']} calls, "
                      f"{entry['n_variables']} quantities)")
            except (ResolveError, CamSimaError, ValueError) as err:
                entry["ok"] = False
                entry["error"] = str(err)
                print(f"FAIL {name}: {str(err).splitlines()[0][:100]}")
            suites.append(entry)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    write_index(suites, quantities)
    n_ok = sum(1 for s in suites if s["ok"])
    print(f"\n{n_ok}/{len(suites)} suites -> {OUT_DIR}/index.html "
          f"({len(quantities)} standard names indexed)")


def write_index(suites, quantities):
    data = {
        "generated": date.today().isoformat(),
        "tool_rev": _git_rev(REPO),
        "nx_rev": _git_rev(os.path.join(REPO, "capgen-nx")),
        "atm_rev": _git_rev(ATM_PHYS),
        "cam_rev": _git_rev(CAM_SIMA),
        "suites": suites,
        "quantities": quantities,
    }
    page = (_INDEX_TEMPLATE
            .replace("{{CSS}}", _read("viewer.css") + _INDEX_CSS)
            .replace("{{DATA}}",
                     json.dumps(data, separators=(",", ":"))
                     .replace("</", "<\\/"))
            .replace("{{JS}}", _INDEX_JS))
    with open(os.path.join(OUT_DIR, "index.html"), "w",
              encoding="utf-8") as fh:
        fh.write(page)


_INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CCPP suite index · quantity flow</title>
<style>
{{CSS}}
</style>
</head>
<body>
<div id="app"></div>
<script>
const DATA = {{DATA}};
{{JS}}
</script>
</body>
</html>
"""

_INDEX_CSS = """
.qi-input { width: 100%; padding: 8px 12px; font: inherit; font-size: 15px;
  border: 1px solid var(--grid); border-radius: 10px;
  background: var(--surface); color: var(--ink); }
.qi-input:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
.qi-hint { color: var(--muted); font-size: 12px; margin: 6px 2px 0; }
.qi-result { background: var(--surface); border: 1px solid var(--grid);
  border-radius: 10px; padding: 10px 14px; margin: 8px 0; }
.qi-result .std { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px; font-weight: 600; word-break: break-all; }
.qi-result .facts { color: var(--muted); font-size: 12px; margin: 2px 0 6px; }
.qi-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.qi-chips a { display: inline-flex; align-items: center; gap: 5px;
  border: 1px solid var(--grid); border-radius: 999px; padding: 1px 9px;
  font-size: 12px; }
.qi-chips a:hover { border-color: var(--accent); text-decoration: none; }
.suite-table { width: 100%; border-collapse: collapse;
  background: var(--surface); border: 1px solid var(--grid);
  border-radius: 10px; overflow: hidden; }
.suite-table th { text-align: left; color: var(--muted); font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.04em; padding: 8px 12px 4px;
  border-bottom: 1px solid var(--grid); }
.suite-table td { padding: 6px 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--grid) 55%, transparent); }
.suite-table tr:last-child td { border-bottom: none; }
.suite-table td.num { text-align: right; color: var(--ink-2);
  font-variant-numeric: tabular-nums; }
.suite-table .err { color: var(--muted); font-size: 12px; font-style: italic; }
.src-chip { font-size: 10.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; border-radius: 5px; padding: 0 6px;
  border: 1px solid var(--grid); color: var(--ink-2); margin: 0 2px; }
h2.idx { font-size: 13px; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.06em; margin: 26px 0 8px; }
"""

_INDEX_JS = """
"use strict";
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    el.append(c.nodeType ? c : document.createTextNode(c));
  }
  return el;
}
const ORIGIN_COLOR = {
  registry: "var(--o-registry)", host: "var(--o-host)",
  namelist: "var(--o-namelist)", scheme: "var(--o-scheme)",
  constituent: "var(--o-constituent)", framework: "var(--o-framework)",
  default: "var(--o-framework)", unknown: "var(--o-framework)",
};
const QSTDS = Object.keys(DATA.quantities).sort();

function suiteTable() {
  const okName = s => h("a", { href: s.html }, s.name);
  const rows = DATA.suites.map(s => h("tr", null,
    h("td", null, s.ok ? okName(s) : s.name + " ",
      h("span", { class: "src-chip" }, s.source)),
    s.ok
      ? [h("td", { class: "num" }, String(s.n_schemes)),
         h("td", { class: "num" }, String(s.n_calls)),
         h("td", { class: "num" }, String(s.n_variables))]
      : h("td", { colspan: "3", class: "err",
                  title: s.error }, (s.error || "").split("\\n")[0])));
  return h("table", { class: "suite-table" },
    h("thead", null, h("tr", null, h("th", null, "suite"),
      h("th", null, "schemes"), h("th", null, "calls"),
      h("th", null, "quantities"))),
    h("tbody", null, ...rows));
}

function lookupResults(q) {
  q = q.trim().toLowerCase();
  if (q.length < 2) return null;
  const hits = QSTDS.filter(s => {
    const e = DATA.quantities[s];
    return s.includes(q) || (e.long_name || "").toLowerCase().includes(q);
  }).slice(0, 100);
  if (!hits.length) return [h("p", { class: "qi-hint" }, "no matches")];
  return hits.map(std => {
    const e = DATA.quantities[std];
    const suites = Object.keys(e.suites).sort();
    return h("div", { class: "qi-result" },
      h("div", { class: "std" }, std),
      h("div", { class: "facts" },
        (e.units || "—") + (e.long_name ? " · " + e.long_name : "") +
        " · in " + suites.length + " suite" + (suites.length === 1 ? "" : "s")),
      h("div", { class: "qi-chips" }, ...suites.map(name =>
        h("a", { href: "suite_" + name + ".html#v/" +
                       encodeURIComponent(std),
                 title: "origin: " + e.suites[name] },
          h("span", { style: "width:7px;height:7px;border-radius:50%;" +
                             "background:" + ORIGIN_COLOR[e.suites[name]] }),
          name))));
  });
}

function boot() {
  const saved = localStorage.getItem("sima-viz-theme");
  if (saved) document.documentElement.dataset.theme = saved;
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches)
    document.documentElement.dataset.theme = "dark";

  const results = h("div", null);
  const input = h("input", {
    class: "qi-input", type: "search",
    placeholder: "look up a standard name across all suites\\u2026",
    oninput: () => {
      const r = lookupResults(input.value);
      results.replaceChildren(...(r || []));
      table.style.display = r ? "none" : "";
      tableHead.style.display = r ? "none" : "";
    },
  });
  const table = suiteTable();
  const tableHead = h("h2", { class: "idx" },
    DATA.suites.filter(s => s.ok).length + " / " + DATA.suites.length +
    " suites");
  const nQ = QSTDS.length;

  document.getElementById("app").append(
    h("header", null,
      h("div", { class: "hdr-row" },
        h("h1", null, "SIMA visualizer"),
        h("span", { class: "spacer" }),
        h("button", {
          id: "theme-toggle", title: "toggle light/dark",
          onclick: () => {
            const cur = document.documentElement.dataset.theme === "dark"
              ? "light" : "dark";
            document.documentElement.dataset.theme = cur;
            localStorage.setItem("sima-viz-theme", cur);
          },
        }, "\\u25D1")),
      h("div", { class: "hdr-row meta-row" },
        h("span", { class: "suite-name" }, "suite index"),
        h("span", { class: "meta-line" },
          "atmospheric_physics @ " + DATA.atm_rev + " · CAM-SIMA @ " +
          DATA.cam_rev + " · " + nQ + " standard names indexed"))),
    h("main", null,
      input,
      h("p", { class: "qi-hint" },
        "type ≥ 2 characters to search " + nQ + " standard names; " +
        "suite chips link straight into that suite's trace view"),
      results, tableHead, table),
    h("footer", null,
      "SIMA suite visualizer rev. " + DATA.tool_rev +
      " · powered by capgen-", h("span", { class: "nx" }, "nx"),
      " " + DATA.nx_rev + " · generated " + DATA.generated));
}
boot();
"""

if __name__ == "__main__":
    sweep()
