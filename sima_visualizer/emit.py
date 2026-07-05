"""Render the viz model into a single self-contained HTML file."""

import json
import os
import subprocess

_VIEWER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "viewer")
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(_VIEWER_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def _git_rev(path):
    try:
        return subprocess.run(
            ["git", "-C", path, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
            timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def write_html(viz, out_path):
    # Footer provenance: this tool's revision and the pinned capgen-nx.
    viz["meta"]["tool_rev"] = _git_rev(_REPO_ROOT)
    viz["meta"]["capgen_nx_rev"] = _git_rev(
        os.path.join(_REPO_ROOT, "capgen-nx"))
    # "</" would terminate the embedding <script> tag early.
    data = json.dumps(viz, separators=(",", ":")).replace("</", "<\\/")
    html = _read("template.html")
    html = html.replace("{{TITLE}}",
                        f"{viz['meta']['suite']} · quantity flow")
    html = html.replace("{{CSS}}", _read("viewer.css"))
    html = html.replace("{{JS}}", _read("viewer.js"))
    html = html.replace("{{DATA}}", data)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path
