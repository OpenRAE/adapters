"""Scenario + pinned source-mapping ledger evidence for PrimAITE (#40).

The authored RAES SDL scenario carries portable topology/objective truth only;
reward, evaluator, fixed-horizon termination, and stochastic controls live in the
companion published experiment contracts. The source ledger records how each
pinned PrimAITE source fact reaches a portable RAES surface, or why it does not,
and every disclosed loss binds the ADR-069 equivalence tier it weakens.

This module binds the shared
:class:`raes_adapters._scenario_ledger.ScenarioLedger` machinery to the PrimAITE
`data_manipulation` evidence set. The generic loaders and deterministic
validators live in the shared module; only the selection identity (including the
pinned content digests of its companion resources) and the backend's
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
    "DATA_MANIPULATION",
    "EvidenceSelection",
    "LEDGER",
    "PINNED_SCENARIO_DIGEST",
]

DATA_MANIPULATION = EvidenceSelection(
    scenario_id="primaite-data-manipulation",
    scenario_resource=("scenario", "data-manipulation.sdl.yaml"),
    pinned_scenario_digest="sha256:8f4c20885bbc3822587b38dc6c76c77915ecd225a2d753e54a1819c8370c80da",
    task_id="primaite-data-manipulation-task",
    task_resource=("experiment", "data-manipulation.task.exp.yaml"),
    spec_id="primaite-data-manipulation-spec",
    spec_resource=("experiment", "data-manipulation.spec.exp.yaml"),
    ledger_resource=("mapping", "source-ledger.jsonl"),
    losses_resource=("mapping", "loss-disclosures.md"),
    protocol_resource="public-protocol.md",
    # PrimAITE pins the content of every companion resource so a semantically
    # valid edit to a reviewed companion cannot stay green without updating this
    # immutable selection.
    task_digest="sha256:44907d86daf43903bc98ac434492815fbe429a5fcc6b2341d9099b3e0ce5c2ba",
    spec_digest="sha256:46d1bb9e0115045aefbdab0545fc692e809219c433b0be5a48e74cde4dd2e798",
    ledger_digest="sha256:2fb69956b6a4ffedf891f0bda69c5599abf4074518050fa6aa1282a6de79af77",
    losses_digest="sha256:2472dc77ef96f2cf3d08c90d2fffe0d386baa514d160fb84303cabc89e2fb50b",
)

# Pinned instantiated-snapshot digest of the selection's scenario. Any change to
# the scenario source changes this value and fails CI, so the portable scenario
# cannot drift silently from its reviewed form.
PINNED_SCENARIO_DIGEST = DATA_MANIPULATION.pinned_scenario_digest

# PrimAITE's selected BLUE observation is a flattened ``int64`` ``Box(1652,)``
# with no native field-name keys (unlike CyberBattleSim's observation dict), so
# the qualification record carries no observation keys to enumerate. The native
# identifier markers are instead the scripted RED and GREEN participant refs
# recorded under ``protocol.selection.participants`` — distinctive native config
# identities that the portable artifacts rename away from. The generic BLUE
# ``defender`` seat ref is deliberately not a marker: it is a plain defensive
# role token that recurs in legitimate portable vocabulary. These join the common
# object/array/traceback representation markers and the PrimAITE object-repr
# prefix.
_NATIVE_OBJECT_PREFIX = "<primaite"


def _native_markers() -> set[str]:
    """Native markers to reject in portable content, grounded in provenance."""
    participants = load_qualification()["protocol"]["selection"]["participants"]
    markers = {str(participants["red"]["ref"]).lower()}
    markers.update(str(green["ref"]).lower() for green in participants["green"])
    markers.update(COMMON_NATIVE_REPR_MARKERS)
    markers.add(_NATIVE_OBJECT_PREFIX)
    return markers


LEDGER = ScenarioLedger(
    DATA_MANIPULATION,
    package=__package__ or "raes_adapters.primaite",
    load_qualification=load_qualification,
    native_markers=_native_markers,
)

# Selection-bound entry points kept as module-level names for importers.
load_loss_disclosures = LEDGER.load_loss_disclosures
validate_all = LEDGER.validate_all
