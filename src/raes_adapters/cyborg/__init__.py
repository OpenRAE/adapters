"""Selected CybORG/CAGE-2 backend adapter and source evidence.

Issue #12 binds one immutable CAGE-2 source closure and its qualification
outcome here. Issue #15 adds the RAES Provisioner, conservative backend
manifest, and target construction for that selected backend.

The native backend is deliberately imported only when the default construction
driver is used. Base-only installations therefore remain independent, while a
user-installed selected CybORG source checkout can be driven through RAES.
"""

from __future__ import annotations

from .driver import (
    CyborgDriver,
    SourceInstalledCyborgDriver,
)
from .manifest import (
    CYBORG_BACKEND_NAME,
    CYBORG_PROFILE_ID,
    create_cyborg_manifest,
    create_cyborg_realization_envelope,
)
from .provisioner import CyborgProvisioner
from .qualification import load_qualification, read_compatibility_patch
from .scenario import (
    CYBORG_SCENARIO_MAPPING_VERSION,
    CyborgScenarioDescriptor,
    CyborgScenarioResource,
    translate_scenario,
)
from .source_ledger import CAGE2_SOURCE_26CE1C1
from .target import (
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
