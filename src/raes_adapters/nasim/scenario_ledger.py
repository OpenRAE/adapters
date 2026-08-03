"""Scenario + pinned source-mapping ledger evidence for NASim (#33).

The authored RAES SDL scenario carries portable topology/objective truth only;
reward, evaluator, termination, and stochastic controls live in the companion
published experiment contracts. The source ledger records how each pinned NASim
source fact reaches a portable RAES surface, or why it does not, and every
disclosed loss binds the ADR-069 equivalence tier it weakens.

This module binds the shared
:class:`raes_adapters._scenario_ledger.ScenarioLedger` machinery to the NASim
`tiny` evidence set. Only the selection identity and the backend's
native-leakage markers are backend-specific.
"""

from __future__ import annotations

from raes_adapters._scenario_ledger import (
    COMMON_NATIVE_REPR_MARKERS,
    EvidenceSelection,
    ScenarioLedger,
)

from . import load_qualification

__all__ = [
    "LEDGER",
    "NASIM_TINY",
    "PINNED_SCENARIO_DIGEST",
    "EvidenceSelection",
    "load_loss_disclosures",
    "validate_all",
]

NASIM_TINY = EvidenceSelection(
    scenario_id="nasim-tiny",
    scenario_resource=("scenario", "nasim-tiny.sdl.yaml"),
    pinned_scenario_digest="sha256:a826fd8f812a447dd4c8d346179163f4c5274176ca739bc2802756913a195e2d",
    task_id="nasim-tiny-task",
    task_resource=("experiment", "nasim-tiny.task.exp.yaml"),
    spec_id="nasim-tiny-spec",
    spec_resource=("experiment", "nasim-tiny.spec.exp.yaml"),
    ledger_resource=("mapping", "source-ledger.jsonl"),
    losses_resource=("mapping", "loss-disclosures.md"),
    protocol_resource="public-protocol.md",
)

# Pinned instantiated-snapshot digest of the selection's scenario. Any change to
# the scenario source changes this value and fails CI, so the portable scenario
# cannot drift silently from its reviewed form.
PINNED_SCENARIO_DIGEST = NASIM_TINY.pinned_scenario_digest

# NASim's selected observation is a flat ``float32`` ``Box(56,)`` with no native
# field-name keys (unlike CyberBattleSim's observation dict), so there are no
# native observation keys to enumerate from the qualification record. The native
# identifier markers are instead the NASim action-class symbols
# (``nasim/envs/action.py``) that must never appear in portable content; the
# portable SDL names its actions with abstract hyphenated contract ids. These
# join the common object/array/traceback representation markers and the NASim
# object-repr prefix. Generic words such as "exploit" are deliberately excluded
# because they legitimately appear in portable vulnerability prose.
_NATIVE_SYMBOL_MARKERS: tuple[str, ...] = (
    "servicescan",
    "osscan",
    "subnetscan",
    "processscan",
    "privilegeescalation",
    "flatactionspace",
    "<nasim",
)


def _native_markers() -> set[str]:
    """Native markers to reject in portable content, grounded in provenance."""
    markers = {marker.lower() for marker in _NATIVE_SYMBOL_MARKERS}
    markers.update(COMMON_NATIVE_REPR_MARKERS)
    return markers


LEDGER = ScenarioLedger(
    NASIM_TINY,
    package=__package__ or "raes_adapters.nasim",
    load_qualification=load_qualification,
    native_markers=_native_markers,
)

# Backend importers (``backend/conformance.py``, ``backend/evaluator.py``) use
# these selection-bound entry points; keep them as module-level names.
load_loss_disclosures = LEDGER.load_loss_disclosures
validate_all = LEDGER.validate_all
