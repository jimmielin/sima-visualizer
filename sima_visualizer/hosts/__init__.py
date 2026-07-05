"""Host model adapters.

A host adapter turns a host-model checkout (the data source) into the inputs
capgen-nx needs: host-side .meta files plus origin annotations for the
variables they declare. Host-specific tooling (e.g. CAM-SIMA's registry and
namelist generators) is imported from the checkout itself at runtime, never
vendored here, so the core stays host-agnostic.
"""

from dataclasses import dataclass, field


@dataclass
class HostInputs:
    """Everything a host adapter contributes to a capgen-nx run."""

    host_name: str
    host_files: list          # host-side .meta files, resolution order
    kind_types: list          # CapgenConfig format, e.g. "kind_phys=REAL64"
    # meta file path -> 'registry' | 'namelist' | 'host'
    # ('host' = static .meta shipped with the host model, set at runtime)
    file_categories: dict = field(default_factory=dict)
    # standard_name -> list of ic-file input names (registry <ic_file_input_names>)
    ic_names: dict = field(default_factory=dict)
    # standard_name -> initial value declared in the registry
    init_values: dict = field(default_factory=dict)
    # standard_names registered as constituents by the host
    constituents: list = field(default_factory=list)
