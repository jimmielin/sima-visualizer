"""CLI: resolve a CCPP suite and emit the quantity-flow visualizer HTML."""

import argparse
import logging
import os
import shutil
import sys
import tempfile

from .analyze import build_viz_model
from .emit import write_html
from .hosts.cam_sima import CamSima, CamSimaError
from .resolve import ResolveError, resolve_suite, run_capgen_nx


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="sima-viz",
        description="Visualize quantity flow through a CCPP physics suite "
                    "(CAM-SIMA + atmospheric_physics).")
    parser.add_argument("--cam-sima", required=True,
                        help="path to a CAM-SIMA checkout (registry, "
                             "host-side metadata, generator scripts)")
    parser.add_argument("--atmospheric-physics", required=True,
                        help="path to an atmospheric_physics checkout "
                             "(suites and scheme metadata)")
    parser.add_argument("--suite", required=True,
                        help="suite name as in --physics-suites "
                             "(resolves suite_<name>.xml in suites/ or "
                             "test/test_suites/)")
    parser.add_argument("--dycore", default="none",
                        help="dycore for registry generation "
                             "(default: none)")
    parser.add_argument("--output", "-o", default=None,
                        help="output HTML path "
                             "(default: suite_<name>.html)")
    parser.add_argument("--workdir", default=None,
                        help="keep intermediate files (generated metadata, "
                             "capgen-nx output, IR JSON) in this directory; "
                             "default is a temporary directory")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s")

    workdir = args.workdir or tempfile.mkdtemp(prefix="sima_viz_")
    os.makedirs(workdir, exist_ok=True)
    try:
        adapter = CamSima(args.cam_sima, args.atmospheric_physics,
                          dycore=args.dycore)
        resolved = resolve_suite(args.suite, adapter.sdf_search_dirs,
                                 adapter.scheme_search_dirs)
        host_inputs = adapter.host_inputs(workdir, resolved.xml_files)
        ir_path = run_capgen_nx(resolved, host_inputs,
                                os.path.join(workdir, "ccpp"))
        viz = build_viz_model(ir_path, resolved, host_inputs, display_roots={
            "atmospheric_physics": adapter.physics_root,
            "CAM-SIMA": adapter.root,
        })
        out = args.output or f"suite_{args.suite}.html"
        write_html(viz, out)
    except (ResolveError, CamSimaError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    finally:
        if not args.workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    print(f"wrote {out}  "
          f"({viz['meta']['n_calls']} calls, "
          f"{viz['meta']['n_variables']} quantities)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
