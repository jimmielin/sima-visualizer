"""Reduce a capgen-nx IR JSON to the visualizer's data model.

The IR already contains everything needed: suite topology (with synthesized
non-run phase groups), per-scheme per-phase argument lists, and resolved
bindings whose source kind classifies provenance (host / suite / group_local /
constituent / framework / default). This module only reshapes it into
execution-ordered calls and per-variable timelines.
"""

import json
import os

# Synthesized group-name suffix -> canonical phase key (capgen_nx.phases).
_GROUP_PHASE_SUFFIX = {
    "register": "register",
    "initialize": "init",
    "timestep_initial": "timestep_init",
    "timestep_final": "timestep_final",
    "finalize": "final",
}

# Execution-order sections for the UI.
_PHASE_SECTION = {
    "register": "startup",
    "init": "startup",
    "timestep_init": "timeloop",
    "run": "timeloop",
    "timestep_final": "timeloop",
    "final": "shutdown",
}

# When a variable resolves differently across groups/phases, report the most
# authoritative storage.
_SOURCE_KIND_RANK = ["host", "constituent", "framework", "suite",
                     "group_local", "framework_allocated", "default"]


def _group_phase(group_name, suite_name):
    suffix = group_name[len(suite_name) + 1:] \
        if group_name.startswith(suite_name + "_") else group_name
    return _GROUP_PHASE_SUFFIX.get(suffix, "run")


def _display_path(path, roots):
    """Shorten an absolute path with symbolic root prefixes for display."""
    real = os.path.realpath(path)
    for label, root in roots.items():
        root_real = os.path.realpath(root)
        if real.startswith(root_real + os.sep):
            return f"{label}/{os.path.relpath(real, root_real)}"
    return path


def build_viz_model(ir_path, resolved, host_inputs, display_roots=None):
    """Build the JSON-serializable viz model from an emitted IR file.

    <display_roots> maps display label -> absolute root path, used only to
    shorten file paths shown in the UI.
    """
    with open(ir_path, encoding="utf-8") as fh:
        ir = json.load(fh)

    suite_name = ir["suite"]["name"]
    schemes_ir = ir["schemes"]
    roots = display_roots or {}

    # Bindings index: (scheme, phase, arg std name) -> source dict,
    # plus std name -> host module for host-resolved variables.
    bind_index = {}
    host_module_of = {}
    for bind in ir["bindings"]:
        key = (bind["scheme"], bind["phase"], bind["argument_standard_name"])
        bind_index[key] = bind["source"]
        if bind["source"]["kind"] == "host" and bind["source"]["module"]:
            host_module_of.setdefault(bind["argument_standard_name"],
                                      bind["source"]["module"])

    # Walk suite topology: flat execution-ordered calls + per-group item tree.
    calls = []
    groups_out = []
    for group in ir["suite"]["groups"]:
        phase = _group_phase(group["name"], suite_name)

        def walk(items, subcycle_depth, phase):
            nodes = []
            for item in items:
                if item["kind"] == "subcycle":
                    nodes.append({
                        "kind": "subcycle",
                        "loop": item["loop"],
                        "items": walk(item["items"], subcycle_depth + 1,
                                      phase),
                    })
                    continue
                scheme_name = item["name"]
                scheme = schemes_ir.get(scheme_name, {})
                sphase = scheme.get("phases", {}).get(phase)
                call_id = None
                if sphase is not None:
                    call_id = len(calls)
                    args = []
                    for arg in sphase["arguments"]:
                        source = bind_index.get(
                            (scheme_name, phase, arg["standard_name"]), {})
                        args.append({
                            "std": arg["standard_name"],
                            "local": arg["local_name"],
                            "intent": arg["intent"],
                            "source_kind": source.get("kind", ""),
                            "access": source.get("access_path", ""),
                        })
                    calls.append({
                        "id": call_id,
                        "scheme": scheme_name,
                        "phase": phase,
                        "group": group["name"],
                        "subcycle": subcycle_depth,
                        "subroutine": sphase["subroutine_name"],
                        "args": args,
                    })
                nodes.append({"kind": "scheme", "name": scheme_name,
                              "call": call_id})
            return nodes

        groups_out.append({
            "name": group["name"],
            "phase": phase,
            "section": _PHASE_SECTION[phase],
            "items": walk(group["items"], 0, phase),
        })

    # Per-variable records with execution-ordered touches.
    host_vars = ir["host_model"]["variables"]
    variables = {}
    for call in calls:
        for arg in call["args"]:
            std = arg["std"]
            rec = variables.get(std)
            if rec is None:
                # Prefer host metadata for descriptive fields; fall back to
                # the first scheme argument that references the variable.
                meta = host_vars.get(std)
                declared_by_host = meta is not None
                if meta is None:
                    scheme = schemes_ir[call["scheme"]]
                    meta = next(
                        a for a in
                        scheme["phases"][call["phase"]]["arguments"]
                        if a["standard_name"] == std)
                rec = variables[std] = {
                    "std": std,
                    "units": meta.get("units") or "",
                    "type": meta.get("type") or "",
                    "kind": meta.get("kind") or "",
                    "dims": meta.get("dimensions") or [],
                    "long_name": meta.get("long_name") or "",
                    "host_declared": declared_by_host,
                    "source_kinds": [],
                    "touches": [],
                }
            if arg["source_kind"] and \
                    arg["source_kind"] not in rec["source_kinds"]:
                rec["source_kinds"].append(arg["source_kind"])
            rec["touches"].append({
                "call": call["id"],
                "intent": arg["intent"],
                "local": arg["local"],
            })

    # Storage classification + origin per variable.
    module_category = {}
    for path, category in host_inputs.file_categories.items():
        module = os.path.splitext(os.path.basename(path))[0]
        module_category[module] = category
    constituent_stds = set(ir.get("constituents", {}))
    constituent_stds.update(host_inputs.constituents)

    for std, rec in variables.items():
        kinds = rec.pop("source_kinds")
        storage = next((k for k in _SOURCE_KIND_RANK if k in kinds), "")
        rec["storage"] = storage

        origin = {"kind": "unknown"}
        host_module = host_module_of.get(std)
        if std in constituent_stds or storage == "constituent":
            origin = {"kind": "constituent"}
        elif storage == "host" and host_module:
            category = module_category.get(host_module, "host")
            origin = {"kind": category, "module": host_module}
            if category == "registry":
                if std in host_inputs.ic_names:
                    origin["ic_names"] = host_inputs.ic_names[std]
                if std in host_inputs.init_values:
                    origin["init_value"] = host_inputs.init_values[std]
            elif category == "namelist":
                # create_readnl_files names the module <scheme>_namelist
                origin["scheme"] = host_module.removesuffix("_namelist")
        elif storage == "host":
            # Host binding without a module: provided by the host cap itself
            # (framework-managed state, e.g. the constituents object).
            origin = {"kind": "framework"}
        elif storage == "framework":
            origin = {"kind": "framework"}
        elif storage in ("suite", "group_local", "framework_allocated", ""):
            producer = next((t for t in rec["touches"]
                             if t["intent"] == "out"), None)
            if producer is not None:
                origin = {"kind": "scheme",
                          "scheme": calls[producer["call"]]["scheme"],
                          "phase": calls[producer["call"]]["phase"]}
        elif storage == "default":
            origin = {"kind": "default"}
        rec["origin"] = origin

        # Written by some scheme but never read afterwards within the suite
        # (may still be consumed by the host model, e.g. state for the dycore).
        last_read = max((i for i, t in enumerate(rec["touches"])
                         if t["intent"] in ("in", "inout")), default=-1)
        last_write = max((i for i, t in enumerate(rec["touches"])
                          if t["intent"] in ("out", "inout")), default=-1)
        rec["unread_after_write"] = last_write > last_read

    schemes_out = {}
    for name, scheme in schemes_ir.items():
        schemes_out[name] = {
            "module": scheme["module"],
            "source_file": _display_path(scheme.get("source_file", ""),
                                         roots),
            "meta_file": _display_path(resolved.schemes.get(name, ""), roots),
            "phases": {ph: sp["subroutine_name"]
                       for ph, sp in scheme["phases"].items()},
        }

    return {
        "meta": {
            "suite": suite_name,
            "sdf": _display_path(resolved.sdf_path, roots),
            "host": host_inputs.host_name,
            "n_schemes": len(schemes_out),
            "n_calls": len(calls),
            "n_variables": len(variables),
        },
        "groups": groups_out,
        "calls": calls,
        "variables": variables,
        "schemes": schemes_out,
    }
