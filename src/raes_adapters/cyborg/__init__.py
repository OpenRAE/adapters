"""Selected CybORG/CAGE-2 backend adapter and source evidence.

Issue #12 binds one immutable CAGE-2 source closure and its qualification
outcome here. Issue #15 adds the RAES Provisioner, conservative backend
manifest, and target construction for that selected backend.

The native backend is deliberately imported only when the default construction
driver is used. Base-only installations therefore remain independent, while a
user-installed selected CybORG source checkout can be driven through RAES.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast


def load_qualification() -> dict[str, Any]:
    """Load a fresh copy of the selected CAGE-2 qualification record."""
    resource = files(__package__).joinpath("qualification.json")
    return cast(dict[str, Any], json.loads(resource.read_text(encoding="utf-8")))


def read_compatibility_patch() -> str:
    """Read the qualification-only packaging patch verbatim."""
    resource = files(__package__).joinpath("cage2-wheel-package-data.patch")
    return resource.read_text(encoding="utf-8")


from .driver import (  # noqa: E402
    CyborgDriver,
    SourceInstalledCyborgDriver,
)
from .manifest import (  # noqa: E402
    CYBORG_BACKEND_NAME,
    CYBORG_PROFILE_ID,
    create_cyborg_manifest,
    create_cyborg_realization_envelope,
)
from .provisioner import CyborgProvisioner  # noqa: E402
from .scenario import (  # noqa: E402
    CYBORG_SCENARIO_MAPPING_VERSION,
    CyborgScenarioDescriptor,
    CyborgScenarioResource,
    translate_scenario,
)
from .source_ledger import CAGE2_SOURCE_26CE1C1  # noqa: E402
from .target import (  # noqa: E402
    create_cyborg_components,
    create_cyborg_target,
    register_cyborg_backend,
)

__all__ = [
    "CAGE2_SOURCE_26CE1C1",
    "CYBORG_BACKEND_NAME",
    "CYBORG_PROFILE_ID",
    "CYBORG_SCENARIO_MAPPING_VERSION",
    "CyborgDriver",
    "CyborgProvisioner",
    "CyborgScenarioDescriptor",
    "CyborgScenarioResource",
    "SourceInstalledCyborgDriver",
    "create_cyborg_components",
    "create_cyborg_manifest",
    "create_cyborg_realization_envelope",
    "create_cyborg_target",
    "load_qualification",
    "read_compatibility_patch",
    "register_cyborg_backend",
    "translate_scenario",
]
