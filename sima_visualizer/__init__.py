"""sima_visualizer: quantity-flow visualizer for CCPP physics suites.

Pipeline: host adapter resolves data-source inputs (registry, namelist XML),
the host-agnostic core resolves the suite and runs capgen-nx, then the
analyzer reduces the capgen-nx IR to a viz model rendered as a single
self-contained HTML page.
"""

import os
import sys

__version__ = "0.1.0"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPGEN_NX_ROOT = os.path.join(_REPO_ROOT, "capgen-nx")


def ensure_capgen_nx():
    """Make the capgen-nx submodule importable.

    Adds both the capgen_nx package and capgen-nx's ccpp-framework script
    shims (framework_env, parse_tools, metadata_table, fortran_tools, ...);
    the shims are needed by data-source generator scripts that host adapters
    import (e.g. CAM-SIMA's generate_registry_data).
    """
    for sub in ("python", "scripts"):
        path = os.path.join(CAPGEN_NX_ROOT, sub)
        if path not in sys.path:
            sys.path.insert(0, path)
