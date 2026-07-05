"""Render the viz model into a single self-contained HTML file."""

import json
import os

_VIEWER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "viewer")


def _read(name):
    with open(os.path.join(_VIEWER_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def write_html(viz, out_path):
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
