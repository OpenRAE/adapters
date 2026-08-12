"""NASim conformance composition over published RAES report shapes."""

from __future__ import annotations

from collections.abc import Mapping

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
)
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    Diagnostic,
    diagnostic_payload,
)

from raes_adapters._gym_backend import conformance as gym
from raes_adapters._gym_backend.conformance import GymConformanceConfig
from raes_adapters.nasim import load_qualification
from raes_adapters.nasim.scenario_ledger import (
    NASIM_TINY,
    EvidenceSelection,
    load_loss_disclosures,
    validate_all,
)

from .driver import NasimDriverProtocol
from .manifest import create_nasim_manifest
from .target import create_nasim_target

# The single public seed for the deterministic PR conformance lane. The suite
# never derives seed or case order from time, PR number, hashing, environment,
# or global random state (see nasim-conformance-guardrails.md).
PR_CONFORMANCE_SEED = 20260802

_SOURCE_FAILED = "nasim.source-protocol.validation-failed"
_CONFIG = GymConformanceConfig(
    name="nasim",
    source_validation_failed=_SOURCE_FAILED,
    default_selection=NASIM_TINY,
    create_target=create_nasim_target,
    create_manifest=create_nasim_manifest,
    load_qualification=load_qualification,
    validate_all=validate_all,
    load_loss_disclosures=load_loss_disclosures,
)


def run_nasim_conformance(
    *,
    driver: NasimDriverProtocol | None = None,
    seed: int | None = None,
) -> BackendConformanceReport:
    """Run the published RAES target conformance probe for NASim."""

    return gym.run_conformance(_CONFIG, driver, seed)


def nasim_backend_conformance_payload(
    report: BackendConformanceReport,
) -> dict[str, object]:
    """Serialize the canonical report through the published RAES projector."""

    return gym.conformance_payload(report)


def nasim_manifest_capability_gaps(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Return every affirmative manifest leaf as unresolved inventory."""

    return gym.capability_gaps(_CONFIG, manifest, payload)


def nasim_declared_weaknesses(
    selection: EvidenceSelection = NASIM_TINY,
) -> tuple[str, ...]:
    """Return declared source-protocol limitations and loss disclosures."""

    return gym.declared_weaknesses(_CONFIG, selection)


def nasim_source_protocol_diagnostics(
    selection: EvidenceSelection = NASIM_TINY,
) -> tuple[Diagnostic, ...]:
    """Validate source-protocol evidence and emit RAES diagnostics."""

    return gym.source_protocol_diagnostics(_CONFIG, selection)


def run_nasim_pr_conformance(
    *,
    driver: NasimDriverProtocol,
    seed: int = PR_CONFORMANCE_SEED,
) -> dict[str, object]:
    """Compose the deterministic PR conformance evidence bundle for one driver.

    Runs the published profile/corpus conformance for the profile inferred from
    the live manifest — which drives the supplied driver through the constructed
    ``RuntimeTarget``'s four surfaces on the published fixtures — then collects
    source-protocol diagnostics, inventories unresolved manifest claims, and gathers
    declared weaknesses into a single validated portable bundle. The three claims
    stay distinct: ``backend_conformance`` is the exact published report payload,
    ``source_diagnostics`` are RAES source evidence, and ``declared_weaknesses``
    bound the research/readiness claim.

    ``driver`` is required: the caller selects the lane explicitly (a
    deterministic injected driver for the PR/clean-install lane, a real
    ``NasimDriver`` for the manual-live lane). No broad pass result is promoted
    into per-leaf capability evidence.

    The hostile-failure and portable-output-leakage probes over the four
    surfaces are injected-driver constructs — they need drivers that raise on a
    chosen surface, which a real ``NasimDriver`` cannot do — so they live in the
    deterministic PR test suite (``tests/test_nasim_conformance.py``), not this
    callable. This bundle is the machine-readable success-path evidence both the
    clean-install proof and the manual-live gate run.
    """

    report = run_nasim_conformance(driver=driver, seed=seed)
    diagnostics = nasim_source_protocol_diagnostics()
    payload = backend_manifest_payload(create_nasim_manifest())
    gaps = nasim_manifest_capability_gaps(payload=payload)
    return {
        "seed": seed,
        "native_conformance": report.native_conformance,
        "backend_conformance": nasim_backend_conformance_payload(report),
        "source_diagnostics": [diagnostic_payload(item) for item in diagnostics],
        "capability_gaps": list(gaps),
        "declared_weaknesses": list(nasim_declared_weaknesses()),
    }


__all__ = [
    "PR_CONFORMANCE_SEED",
    "nasim_backend_conformance_payload",
    "nasim_declared_weaknesses",
    "nasim_manifest_capability_gaps",
    "nasim_source_protocol_diagnostics",
    "run_nasim_conformance",
    "run_nasim_pr_conformance",
]
