"""Host-agnostic suite resolution.

Finds the SDF, discovers scheme metadata the same way CAM-SIMA's build does
(first .meta basename wins, Fortran source required, optional
<name>_namelist.xml), and runs capgen-nx over the assembled inputs.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from . import CAPGEN_NX_ROOT, ensure_capgen_nx

ensure_capgen_nx()

# pylint: disable=wrong-import-position
from capgen_nx.driver import CapgenConfig, capgen
from capgen_nx.frontend.sdf_parser import parse_sdf
from capgen_nx.ir import SchemeRef, Subcycle
from metadata_table import find_scheme_names  # capgen-nx framework shim
# pylint: enable=wrong-import-position

_FORTRAN_EXTENSIONS = [".F90", ".F", ".f", ".f90"]


class ResolveError(Exception):
    """Raised when suite inputs cannot be resolved."""


@dataclass
class ResolvedSuite:
    suite_name: str        # name attribute inside the SDF
    sdf_path: str
    scheme_files: list     # scheme .meta files, SDF traversal order, deduped
    schemes: dict          # scheme name -> .meta file
    xml_files: dict        # scheme name -> namelist definition XML


def find_sdf(suite_name, search_dirs):
    fname = f"suite_{suite_name}.xml"
    for direc in search_dirs:
        candidate = os.path.join(direc, fname)
        if os.path.exists(candidate):
            return candidate
    raise ResolveError(
        f"Unable to find {fname} in: {', '.join(search_dirs)}")


def _index_files(search_dirs):
    """One walk over <search_dirs>: filename -> first path found.

    Equivalent to CAM-SIMA's per-file searches (first hit in directory,
    then walk order, wins) but O(tree) instead of O(files * tree).
    """
    index = {}
    for direc in search_dirs:
        for root, _, files in os.walk(direc):
            if ".git" in root:
                continue
            for fname in files:
                if fname not in index:
                    index[fname] = os.path.join(root, fname)
    return index


def discover_schemes(search_dirs):
    """Map scheme name -> (meta file, Fortran source, namelist XML or None).

    Mirrors cam_autogen._find_metadata_files: every .meta must have a
    same-basename Fortran source; a same-basename <base>_namelist.xml is
    associated if present, and may serve at most one scheme.
    """
    file_index = _index_files(search_dirs)
    meta_files = {}
    missing_source = []
    bad_xml = []
    seen_meta = set()
    for fname, path in sorted(file_index.items()):
        if not fname.endswith(".meta") or fname in seen_meta:
            continue
        seen_meta.add(fname)
        base = os.path.splitext(fname)[0]
        source_file = None
        for ext in _FORTRAN_EXTENSIONS:
            source_file = file_index.get(base + ext)
            if source_file:
                break
        if not source_file:
            missing_source.append(path)
            continue
        xml_file = file_index.get(base + "_namelist.xml")
        schemes = find_scheme_names(path)
        if len(schemes) > 1 and xml_file:
            bad_xml.append(xml_file)
        for scheme in schemes:
            meta_files[scheme.lower()] = (path, source_file, xml_file)
    if missing_source:
        raise ResolveError(
            "No Fortran source found for meta file(s):\n"
            + "\n".join(sorted(missing_source)))
    if bad_xml:
        raise ResolveError(
            "Namelist XML associated with more than one scheme:\n"
            + "\n".join(bad_xml))
    return meta_files


def _schemes_in_suite(suite):
    """Ordered, deduped scheme names from a parsed capgen-nx Suite."""
    names = []

    def walk(items):
        for item in items:
            if isinstance(item, SchemeRef):
                if item.name not in names:
                    names.append(item.name)
            elif isinstance(item, Subcycle):
                walk(item.items)

    for group in suite.groups:
        walk(group.items)
    return names


def resolve_suite(suite_name, sdf_search_dirs, scheme_search_dirs):
    sdf_path = find_sdf(suite_name, sdf_search_dirs)
    suite = parse_sdf(Path(sdf_path),
                      suite_search_dirs=[Path(d) for d in sdf_search_dirs])
    wanted = _schemes_in_suite(suite)

    available = discover_schemes(scheme_search_dirs)
    scheme_files = []
    schemes = {}
    xml_files = {}
    missing = []
    for scheme in wanted:
        entry = available.get(scheme)
        if entry is None:
            missing.append(scheme)
            continue
        meta, _, xml = entry
        schemes[scheme] = meta
        if meta not in scheme_files:
            scheme_files.append(meta)
        if xml:
            xml_files[scheme] = xml
    if missing:
        raise ResolveError(
            "No metadata found for scheme(s): " + ", ".join(missing))

    return ResolvedSuite(suite_name=suite.name, sdf_path=sdf_path,
                         scheme_files=scheme_files, schemes=schemes,
                         xml_files=xml_files)


def run_capgen_nx(resolved, host_inputs, output_dir):
    """Run the capgen-nx pipeline; return the path of the emitted IR JSON.

    The framework's constituent-properties DDT metadata is appended the same
    way capgen-nx's own CAM-SIMA shim does.
    """
    host_files = list(host_inputs.host_files)
    const_meta = os.path.join(CAPGEN_NX_ROOT, "src",
                              "ccpp_constituent_prop_mod.meta")
    if const_meta not in host_files:
        host_files.append(const_meta)

    os.makedirs(output_dir, exist_ok=True)
    config = CapgenConfig(
        host_files=host_files,
        scheme_files=list(resolved.scheme_files),
        suite_files=[resolved.sdf_path],
        output_dir=output_dir,
        host_name=host_inputs.host_name,
        kind_types=list(host_inputs.kind_types),
        datatable_file=os.path.join(output_dir, "ccpp_datatable.xml"),
        emit_ir=True,
    )
    capgen(config, return_db=False)
    ir_path = os.path.join(output_dir, f"{resolved.suite_name}_ir.json")
    if not os.path.exists(ir_path):
        raise ResolveError(f"capgen-nx did not emit expected IR: {ir_path}")
    return ir_path
