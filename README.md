# sima_visualizer

Visualize how physical quantities flow through a CCPP physics suite
(CAM-SIMA + atmospheric_physics): which schemes run in what order, what each
one reads, modifies, and produces, and where every quantity originates
(registry initial conditions/defaults, host model, namelist, another scheme,
constituents, or the CCPP framework).

The output is a single self-contained HTML file — no server, no external
assets — with two linked views:

- **Suite flow**: scheme call order grouped by phase (startup, time loop,
  shutdown), with groups, subcycles, and per-argument intent tables.
- **Quantity trace**: pick a standard name and follow it through the suite —
  origin badge, then every touch in execution order, distinguishing
  read (`in`), read & modified (`inout`), and produced/overwritten (`out`).

## Quick start

```sh
git clone --recurse-submodules <this repo>
python3 -m sima_visualizer \
    --cam-sima ~/devel/CAM-SIMA \
    --atmospheric-physics ~/devel/atmospheric_physics \
    --suite kessler
open suite_kessler.html
```

Requires Python ≥ 3.9 and the checked-out `capgen-nx` submodule; no other
dependencies. Suite names resolve exactly like CAM-SIMA's
`--physics-suites`: `suite_<name>.xml` in `suites/` or `test/test_suites/`.

Options: `--dycore` (registry generation, default `none`), `-o` output path,
`--workdir` to keep intermediates (generated host metadata, capgen-nx
Fortran, and the `<suite>_ir.json` IR), `-v` for generator chatter.

## How it works

```
hosts/cam_sima.py   CAM-SIMA adapter: interprets registry.xml and scheme
                    namelist XML by importing CAM-SIMA's own generator
                    scripts (gen_registry, gen_namelist_files) from the
                    checkout at runtime — full fidelity, nothing vendored.
resolve.py          Host-agnostic: finds the SDF, discovers scheme .meta
                    files the way cam_autogen does, runs capgen-nx.
analyze.py          Reduces the capgen-nx IR JSON (bindings with provenance,
                    suite topology incl. synthesized phase groups) to the
                    viz model: execution-ordered calls + per-quantity
                    timelines and origins.
emit.py + viewer/   Injects the viz model into the vanilla JS/CSS viewer.
```

All variable-flow analysis comes from capgen-nx's resolver (binding source
kinds: host / suite / group_local / constituent / framework), so the
visualizer shows what the generated caps actually do rather than a
re-implementation's opinion. capgen-nx is bit-for-bit validated against
ccpp-framework's capgen on CAM-SIMA.

Host-model specifics are confined to `hosts/`; the core consumes only meta
files, SDF paths, and the IR. A future host (e.g. UFS) means writing one new
adapter, not touching the core.

Notes:

- CAM-SIMA development trees usually leave the `src/physics/ncar_ccpp`
  submodule unpopulated; the adapter builds a symlinked shadow tree so
  registry references resolve against the atmospheric_physics checkout you
  pass in. Neither checkout is modified.
- Suites whose schemes request variables no host or scheme provides
  (at the time of writing: `cam5`, `cam7`, `beljaars_form_drag`) fail with
  the same unresolved-variable errors the real build would produce.
