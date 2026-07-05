"""CAM-SIMA host adapter.

Treats a CAM-SIMA checkout as a data source: registry.xml (plus the static
.meta files it references) describes host-side variables, and per-scheme
namelist XML describes namelist parameters read on the host side. Both are
interpreted by importing CAM-SIMA's own generator scripts from the checkout
(generate_registry_data.py, create_readnl_files.py), so the result always
matches what CAM-SIMA actually builds. The generators require ccpp-framework
script modules, which are satisfied by capgen-nx's shims.
"""

import glob
import logging
import os
import shutil
import sys
import xml.etree.ElementTree as ET

from .. import ensure_capgen_nx
from . import HostInputs

_LOGGER = logging.getLogger("sima_visualizer.cam_sima")

# Matches CAM-SIMA's build configuration (buildlib gen_indent / COMP_ATM).
_GEN_FORT_INDENT = 3
_HOST_NAME = "cam"
_KIND_TYPES = ["kind_phys=REAL64"]


class CamSimaError(Exception):
    """Raised when the CAM-SIMA checkout cannot be used as a data source."""


class CamSima:
    """Adapter over a CAM-SIMA checkout plus an atmospheric_physics checkout.

    The physics checkout is passed separately because the normal submodule at
    src/physics/ncar_ccpp is typically not populated in development trees.
    """

    host_name = _HOST_NAME
    kind_types = _KIND_TYPES

    def __init__(self, cam_sima_root, physics_root, dycore="none"):
        self.root = os.path.abspath(cam_sima_root)
        self.physics_root = os.path.abspath(physics_root)
        self.dycore = dycore
        self._data_dir = os.path.join(self.root, "src", "data")
        registry = os.path.join(self._data_dir, "registry.xml")
        if not os.path.exists(registry):
            raise CamSimaError(
                f"No registry.xml under {self._data_dir}; "
                "is --cam-sima pointing at a CAM-SIMA checkout?")
        self.registry_file = registry

    @property
    def sdf_search_dirs(self):
        return [os.path.join(self.physics_root, "suites"),
                os.path.join(self.physics_root, "test", "test_suites")]

    @property
    def scheme_search_dirs(self):
        return [os.path.join(self.physics_root, "schemes"),
                os.path.join(self.physics_root, "test", "test_schemes")]

    def _import_generators(self):
        """Import CAM-SIMA's generator scripts from the checkout."""
        ensure_capgen_nx()  # framework-script shims must win over any checkout copy
        for path in (self._data_dir, os.path.join(self.root, "cime_config")):
            if path not in sys.path:
                sys.path.append(path)
        try:
            from generate_registry_data import gen_registry
            from create_readnl_files import gen_namelist_files
        except ImportError as ierr:
            raise CamSimaError(
                f"Cannot import CAM-SIMA generator scripts from {self.root}: "
                f"{ierr}") from ierr
        return gen_registry, gen_namelist_files

    def _make_shadow_root(self, workdir):
        """Symlink a CAM-SIMA tree with the physics submodule populated.

        registry.xml references .meta files as $SRCROOT/src/physics/ncar_ccpp/...
        (the atmospheric_physics submodule path), which development trees leave
        unpopulated. Rebuild the root out of symlinks with ncar_ccpp pointing
        at the provided physics checkout, so both checkouts stay untouched.
        """
        shadow = os.path.abspath(os.path.join(workdir, "cam_sima_root"))
        if os.path.lexists(shadow):
            shutil.rmtree(shadow)
        shadow_phys = os.path.join(shadow, "src", "physics")
        os.makedirs(shadow_phys)
        for entry in os.listdir(self.root):
            if entry != "src":
                os.symlink(os.path.join(self.root, entry),
                           os.path.join(shadow, entry))
        src_real = os.path.join(self.root, "src")
        for entry in os.listdir(src_real):
            if entry != "physics":
                os.symlink(os.path.join(src_real, entry),
                           os.path.join(shadow, "src", entry))
        phys_real = os.path.join(src_real, "physics")
        for entry in os.listdir(phys_real):
            if entry != "ncar_ccpp":
                os.symlink(os.path.join(phys_real, entry),
                           os.path.join(shadow_phys, entry))
        os.symlink(self.physics_root, os.path.join(shadow_phys, "ncar_ccpp"))
        return shadow

    def _registry_initial_values(self):
        """standard_name -> literal <initial_value> text from the registry.

        Display-only echo of the registry attribute; same traversal as
        generate_registry_data._create_variables_with_initial_value_list.
        """
        values = {}
        registry = ET.parse(self.registry_file).getroot()
        for section in registry:
            if section.tag != "file":
                continue
            for obj in section:
                if obj.tag != "variable":
                    continue
                for subobj in obj:
                    if subobj.tag == "initial_value":
                        std = obj.get("standard_name")
                        values[std] = (subobj.text or "").strip()
        return values

    def host_inputs(self, workdir, xml_files):
        """Generate host-side metadata into <workdir> and describe it.

        <xml_files> maps scheme name -> namelist definition XML path for the
        schemes in the suite (from core scheme discovery).
        """
        gen_registry, gen_namelist_files = self._import_generators()

        # Registry -> generated host .meta (+ referenced pre-existing .meta).
        # Mirrors cam_autogen.generate_registry / generate_physics_suites.
        genreg_dir = os.path.join(workdir, "cam_registry")
        src_mods = os.path.join(workdir, "source_mods")  # empty: no case mods
        os.makedirs(genreg_dir, exist_ok=True)
        os.makedirs(src_mods, exist_ok=True)
        shadow_root = self._make_shadow_root(workdir)
        retvals = gen_registry(self.registry_file, self.dycore, genreg_dir,
                               _GEN_FORT_INDENT, src_mods, shadow_root,
                               logger=_LOGGER, schema_paths=[self._data_dir],
                               error_on_no_validate=True)
        retcode, reg_file_list, ic_names, constituents, _ = retvals
        if retcode != 0:
            raise CamSimaError(
                f"gen_registry failed for {self.registry_file}, "
                f"err = {retcode}")
        init_values = self._registry_initial_values()

        # Generated dir first: DDT definitions must be seen before use.
        host_files = sorted(glob.glob(os.path.join(genreg_dir, "*.meta")))
        file_categories = {f: "registry" for f in host_files}
        for reg_file in reg_file_list:
            path = getattr(reg_file, "file_path", None)
            if not path:
                continue
            # Canonicalize through the shadow symlinks back to the real
            # checkouts so paths outlive the workdir.
            path = os.path.realpath(path)
            if path not in host_files:
                host_files.append(path)
                file_categories[path] = "host"

        # Scheme namelist XML -> generated host .meta for namelist parameters.
        if xml_files:
            gennl_dir = os.path.join(workdir, "namelist")
            os.makedirs(gennl_dir, exist_ok=True)
            args = []
            for scheme, xml_file in xml_files.items():
                args.extend(["--namelist-file-arg", f"{scheme}:{xml_file}"])
            args.extend(["--namelist-read-mod", "cam_ccpp_scheme_namelists",
                         "--namelist-read-subname",
                         "cam_read_ccpp_scheme_namelists"])
            namelist_obj = gen_namelist_files(args, gennl_dir, _LOGGER)
            for meta in namelist_obj.meta_files():
                host_files.append(meta)
                file_categories[meta] = "namelist"

        return HostInputs(host_name=self.host_name,
                          host_files=host_files,
                          kind_types=list(self.kind_types),
                          file_categories=file_categories,
                          ic_names=dict(ic_names),
                          init_values=dict(init_values),
                          constituents=list(constituents))
