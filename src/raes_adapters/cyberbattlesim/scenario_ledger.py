"""Scenario + pinned source-mapping ledger evidence for CyberBattleSim (#26).

The authored RAES SDL scenario carries portable topology/objective truth only;
reward, evaluator, termination, and stochastic controls live in the companion
published experiment contracts. The source ledger records how each pinned
CyberBattleSim source fact reaches a portable RAES surface, or why it does not,
and every disclosed loss binds the ADR-069 equivalence tier it weakens.

This module binds the shared :class:`raes_adapters._scenario_ledger.ScenarioLedger`
machinery to the CyberBattleSim evidence set. The generic loaders and
deterministic validators live in the shared module; only the selection identity
and the backend's native-leakage markers are backend-specific.
"""

from __future__ import annotations

from raes_adapters._scenario_ledger import (
    COMMON_NATIVE_REPR_MARKERS,
    EvidenceSelection,
    ScenarioLedger,
)

from . import load_qualification

__all__ = [
    "CYBERBATTLE_CHAIN",
    "EvidenceSelection",
    "LEDGER",
    "PINNED_SCENARIO_DIGEST",
]

CYBERBATTLE_CHAIN = EvidenceSelection(
    scenario_id="cyberbattlesim-chain",
    scenario_resource=("scenario", "cyberbattle-chain.sdl.yaml"),
    pinned_scenario_digest="sha256:9d696ea7fa23a1e7cf4c1cbc145a7989370dc4e9afff2cd5a17d6d1af887b528",
    task_id="cyberbattlesim-chain-task",
    task_resource=("experiment", "cyberbattle-chain.task.exp.yaml"),
    spec_id="cyberbattlesim-chain-spec",
    spec_resource=("experiment", "cyberbattle-chain.spec.exp.yaml"),
    ledger_resource=("mapping", "source-ledger.jsonl"),
    losses_resource=("mapping", "loss-disclosures.md"),
    protocol_resource="public-protocol.md",
)

# Pinned instantiated-snapshot digest of the default selection's scenario. Any
# change to the scenario source changes this value and fails CI, so the portable
# scenario cannot drift silently from its reviewed form.
PINNED_SCENARIO_DIGEST = CYBERBATTLE_CHAIN.pinned_scenario_digest

# The native observation-field identifiers are not hand-listed: they are read
# from the qualification record's recorded ``smoke.observation_keys`` at scan
# time, joined with the common object/array/traceback representation markers and
# the CyberBattleSim object-repr prefix.
_NATIVE_OBJECT_PREFIX = "<cyberbattle"


def _native_markers() -> set[str]:
    """Native markers to reject in portable content, grounded in provenance."""
    observation_keys = load_qualification()["runtime"]["smoke"]["observation_keys"]
    markers = {str(key).lower() for key in observation_keys}
    markers.update(COMMON_NATIVE_REPR_MARKERS)
    markers.add(_NATIVE_OBJECT_PREFIX)
    return markers


LEDGER = ScenarioLedger(
    CYBERBATTLE_CHAIN,
    package=__package__ or "raes_adapters.cyberbattlesim",
    load_qualification=load_qualification,
    native_markers=_native_markers,
)

# Backend importers (``backend/conformance.py``, ``backend/evaluator.py``) use
# these selection-bound entry points; keep them as module-level names.
load_loss_disclosures = LEDGER.load_loss_disclosures
validate_all = LEDGER.validate_all
