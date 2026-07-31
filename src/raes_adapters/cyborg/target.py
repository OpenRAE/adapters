"""RAES target construction for the selected CybORG backend."""

from __future__ import annotations

from typing import Any, cast

from raes_backend_protocols.capabilities import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_runtime.registry import (  # type: ignore[import-untyped]
    BackendRegistry,
    RuntimeTarget,
    RuntimeTargetComponents,
)

from raes_adapters.base import build_runtime_target

from . import load_qualification
from .driver import CyborgDriver, SourceInstalledCyborgDriver
from .manifest import CYBORG_BACKEND_NAME, create_cyborg_manifest
from .provisioner import CyborgProvisioner
from .source_ledger import CAGE2_SOURCE_26CE1C1

_CONFIG_KEYS = {
    "driver",
    "mapping_ledger_resource",
    "qualification_profile_id",
    "seed",
    "simulator_version",
    "source_commit",
}


def _normalized_config(config: dict[str, object]) -> dict[str, object]:
    unknown = sorted(set(config) - _CONFIG_KEYS)
    if unknown:
        raise ValueError("unknown CybORG target configuration: " + ", ".join(unknown))
    qualification = load_qualification()
    normalized = {
        "qualification_profile_id": config.get(
            "qualification_profile_id",
            qualification["profile_id"],
        ),
        "source_commit": config.get(
            "source_commit",
            qualification["source"]["commit"],
        ),
        "simulator_version": config.get(
            "simulator_version",
            qualification["source"]["version"],
        ),
        "mapping_ledger_resource": config.get(
            "mapping_ledger_resource",
            CAGE2_SOURCE_26CE1C1.ledger_resource,
        ),
        "seed": config.get("seed"),
        "driver": config.get("driver"),
    }
    _validate_selection(normalized, qualification)
    return normalized


def _validate_selection(
    config: dict[str, object],
    qualification: dict[str, Any],
) -> None:
    checks = (
        (
            "qualification_profile_id",
            qualification["profile_id"],
            "qualification profile",
        ),
        ("source_commit", qualification["source"]["commit"], "source commit"),
        (
            "simulator_version",
            qualification["source"]["version"],
            "simulator version",
        ),
        (
            "mapping_ledger_resource",
            CAGE2_SOURCE_26CE1C1.ledger_resource,
            "mapping ledger",
        ),
    )
    for key, expected, label in checks:
        if config[key] != expected:
            raise ValueError(f"CybORG {label} does not match the selected backend.")
    seed = config["seed"]
    if seed is not None and (type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF):
        raise ValueError("CybORG seed must be an unsigned 32-bit integer.")
    driver = config["driver"]
    if driver is not None and (
        not callable(getattr(driver, "construct", None))
        or not callable(getattr(driver, "cleanup", None))
    ):
        raise ValueError("CybORG driver does not implement construction and cleanup.")


def create_cyborg_components(
    *,
    manifest: BackendManifest,
    **config: object,
) -> RuntimeTargetComponents:
    """Build the Provisioner component for one selected backend."""

    normalized = _normalized_config(config)
    if manifest.has_orchestrator or manifest.has_evaluator or manifest.has_participant_runtime:
        raise ValueError("Issue #15 CybORG target is provisioning-only.")
    if manifest.realization_envelope is None:
        raise ValueError("CybORG manifest requires a realization envelope.")
    expected = create_cyborg_manifest(seed=normalized["seed"])
    if manifest.realization_envelope != expected.realization_envelope:
        raise ValueError("CybORG manifest realization envelope is not selected.")
    raw_driver = normalized["driver"]
    driver: CyborgDriver = (
        cast(CyborgDriver, raw_driver)
        if raw_driver is not None
        else SourceInstalledCyborgDriver(expected_version=str(normalized["simulator_version"]))
    )
    return RuntimeTargetComponents(
        provisioner=CyborgProvisioner(
            driver,
            realization_envelope=manifest.realization_envelope.identity,
            profile_id=str(normalized["qualification_profile_id"]),
            source_commit=str(normalized["source_commit"]),
            seed=normalized["seed"] if isinstance(normalized["seed"], int) else None,
        )
    )


def create_cyborg_target(**config: object) -> RuntimeTarget:
    """Return the RAES target that constructs the selected CybORG backend."""

    normalized = _normalized_config(config)
    manifest = create_cyborg_manifest(**normalized)
    components = create_cyborg_components(manifest=manifest, **normalized)
    return build_runtime_target(CYBORG_BACKEND_NAME, manifest, components)


def register_cyborg_backend(registry: BackendRegistry) -> None:
    """Register the selected backend through the published RAES registry."""

    registry.register(
        CYBORG_BACKEND_NAME,
        create_cyborg_manifest,
        create_cyborg_components,
    )


__all__ = [
    "create_cyborg_components",
    "create_cyborg_target",
    "register_cyborg_backend",
]
