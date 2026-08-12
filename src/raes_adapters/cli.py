"""Installed researcher command over published RAES and adapter owners.

Mode dispatch (inspect, validate, run/smoke/conformance/study) is shared across
backends; every backend-local semantic — inspection payload, native import and
source verification, pack root and example members, participant admission, run
controls, and execution/archival — resolves through a per-backend adapter keyed
on the ``--backend`` value. A new backend registers an adapter here and inherits
no other backend's participant surface, red variants, seeds, or evidence claims.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import sys
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module, metadata, resources, util
from pathlib import Path
from types import ModuleType
from typing import NoReturn, Protocol, cast

import raes  # type: ignore[import-untyped]
from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_contracts.backend_profiles import (  # type: ignore[import-untyped]
    backend_profiles_root,
    load_backend_profile,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentArtifactRefModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationProvenanceModel,
    ParticipantImplementationSelectionModel,
    validate_experiment_run_against_task,
    validate_experiment_study_against_tasks_and_runs,
)
from raes_contracts.diagnostics import DiagnosticModel  # type: ignore[import-untyped]
from raes_contracts.participant_configuration import (  # type: ignore[import-untyped]
    validate_participant_configuration_selection,
)
from raes_contracts.satisfiability import canonical_contract_digest  # type: ignore[import-untyped]
from raes_operations.run_artifacts import (  # type: ignore[import-untyped]
    atomic_write_json_artifact,
)

from raes_adapters.cyberbattlesim import (
    load_qualification as load_cyberbattlesim_qualification,
)
from raes_adapters.cyberbattlesim import researcher as cyberbattlesim_researcher
from raes_adapters.cyberbattlesim.backend import (
    create_cyberbattlesim_manifest,
    create_cyberbattlesim_target,
)
from raes_adapters.cyberbattlesim.backend.driver import (
    verify_selected_cyberbattlesim_source,
)
from raes_adapters.cyborg import (
    CAGE2_SOURCE_26CE1C1,
    create_cyborg_manifest,
    create_cyborg_target,
    load_qualification,
    run_cyborg_conformance_suite,
    verify_selected_cyborg_source,
)
from raes_adapters.cyborg import reproduction as cyborg_reproduction
from raes_adapters.cyborg import researcher as cyborg_researcher
from raes_adapters.nasim import load_qualification as load_nasim_qualification
from raes_adapters.nasim import researcher as nasim_researcher
from raes_adapters.nasim.backend import (
    create_nasim_manifest,
    create_nasim_target,
    verify_selected_nasim_source,
)

_COMMON_EXAMPLE_MEMBERS = (
    "pack.yaml",
    "pack.compatibility.yaml",
    "pack.content-manifest.json",
    "docs/attack-path.md",
    "docs/concepts.md",
    "docs/golden-readiness-checklist.md",
    "docs/provenance-ledger.yaml",
)
_RED_PARTICIPANT_ADDRESS = "participant.behavior.red"


def _single_participant_native_args_complete(args: argparse.Namespace) -> bool:
    """Require one participant's complete native admission surface."""

    required = (
        args.pack,
        args.pack_digest,
        args.scenario,
        args.scenario_digest,
        args.experiment,
        args.task,
        args.participant_implementation,
        args.participant_manifest,
        args.participant_selection,
        args.participant_configuration,
        args.trial_length,
        args.seed,
        args.run_id,
    )
    foreign = (
        args.red_variant,
        args.blue_implementation,
        args.blue_manifest,
        args.blue_selection,
        args.blue_configuration,
    )
    return all(value is not None for value in required) and all(value is None for value in foreign)


def _single_participant_experiment_bindings_match(
    args: argparse.Namespace,
    scenario_digest: str,
    spec: ExperimentSpecModel,
    task: ExperimentTaskModel,
    artifact_bindings_admitted: bool,
) -> bool:
    """Verify common scenario, task, plan, and artifact bindings."""

    intended = spec.intended_scenario_ref
    return all(
        (
            scenario_digest == args.scenario_digest,
            intended is not None,
            intended is not None and intended.ref_digest == args.scenario_digest,
            intended is not None and intended.ref_path == args.scenario.as_posix(),
            task.scenario_ref.ref_digest == args.scenario_digest,
            task.scenario_ref.ref_path == args.scenario.as_posix(),
            spec.task_ref.ref_id == task.task_id,
            spec.run_plan.episode_control.max_steps == args.trial_length,
            artifact_bindings_admitted,
        )
    )


EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_OUTPUT = 4
EXIT_RUNTIME = 5
EXIT_ARTIFACT = 6
EXIT_INTERNAL = 70
_OUTPUT_UNAVAILABLE_CODE = "researcher.output.unavailable"
_OUTPUT_UNAVAILABLE_MESSAGE = "output root is unavailable"
_INVENTORY_NAME = "inventory.json"
_RUNTIME_FAILURE_CODE = "researcher.runtime.failure"
_CONTROLS_INVALID_CODE = "researcher.validation.controls-invalid"
_CONTROLS_INVALID_MESSAGE = "run controls were not admitted"


class _UsageFailure(Exception):
    """Internal parser control flow with no user-controlled payload."""


class _OutputFailure(Exception):
    """Internal output-reservation control flow."""


class _ValidationFailure(Exception):
    """Internal pre-execution validation control flow."""


@dataclass(frozen=True)
class _CommandFailure(Exception):
    """Stable command failure safe to project to standard error."""

    exit_code: int
    code: str
    message: str


@dataclass(frozen=True)
class _AdmittedRun(object):
    """Validated authoring inputs required for native execution."""

    pack_digest: str
    scenario: object
    scenario_digest: str
    spec: ExperimentSpecModel
    task: ExperimentTaskModel
    participant_manifest: ParticipantImplementationManifestModel
    participant_selection: ParticipantImplementationSelectionModel
    participant_configuration: ParticipantConfigurationResultModel
    seeds: tuple[int, ...]


@dataclass(frozen=True)
class _CompletedRun(object):
    """Portable records produced by one completed native episode."""

    archival: ExperimentRunModel
    summary: dict[str, object]


class _EpisodeEvidence(Protocol):
    """The validated RAES evidence every backend episode returns."""

    @property
    def completed_steps(self) -> int: ...

    @property
    def evidence_records(self) -> tuple[ExperimentEvidenceRecordModel, ...]: ...

    @property
    def derived_measures(self) -> tuple[ExperimentDerivedMeasureModel, ...]: ...

    @property
    def diagnostics(self) -> tuple[DiagnosticModel, ...]: ...

    @property
    def cleanup_verified(self) -> bool: ...


@dataclass(frozen=True)
class _BackendAdapter(object):
    """Closed per-backend resolution of every backend-local semantic."""

    name: str
    participant_address: str
    pack_example_id: str
    pack_package: str
    packaged_example: bool
    expected_pack_digest: str | None
    example_members: tuple[str, ...]
    native_module: str
    inspection_payload: Callable[[], dict[str, object]]
    verify_source: Callable[[], None]
    create_target: Callable[..., object]
    researcher: ModuleType
    backend_manifest: Callable[[], BackendManifest]
    conformance_suite: Callable[..., dict[str, object]]
    conformance_evidence_basis: str
    native_args_complete: Callable[[argparse.Namespace], bool]
    participant_paths: Callable[[argparse.Namespace], tuple[str, Path, Path, Path]]
    experiment_bindings_match: Callable[
        [argparse.Namespace, str, ExperimentSpecModel, ExperimentTaskModel, bool], bool
    ]
    participant_bindings_match: Callable[
        [
            argparse.Namespace,
            ParticipantImplementationManifestModel,
            ParticipantImplementationSelectionModel,
            ParticipantConfigurationResultModel,
        ],
        bool,
    ]
    admitted_seeds: Callable[[argparse.Namespace, ExperimentSpecModel], tuple[int, ...]]
    build_controls: Callable[[argparse.Namespace, _AdmittedRun, str, int], object]
    episode_provenance: Callable[
        [str, ParticipantImplementationSelectionModel], ParticipantImplementationProvenanceModel
    ]
    evidence_source_label: str
    evidence_satisfies_refs: tuple[str, ...]
    provenance_payload: Callable[[argparse.Namespace, _AdmittedRun], dict[str, object]]
    machine_software: Callable[[], dict[str, str]]


class _Parser(argparse.ArgumentParser):
    """Argparse parser that returns the documented usage status."""

    def error(self, message: str) -> NoReturn:
        del message
        raise _UsageFailure


def _relative_output(value: str) -> Path:
    """Parse an invocation-relative output child path."""

    requested = Path(value)
    if requested.is_absolute() or not requested.parts or ".." in requested.parts:
        raise argparse.ArgumentTypeError("output must be an invocation-relative child path")
    return requested


_BACKEND_CHOICES = ("cyborg-cage2", "cyberbattlesim-chain", "nasim-tiny")


def _parser() -> _Parser:
    """Build the closed researcher command parser."""

    parser = _Parser(prog="raes-adapters", description="Inspect, validate, and run RAES adapters.")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--backend", choices=_BACKEND_CHOICES, required=True)

    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--mode", choices=("smoke", "study"), default="study")
    _add_admission_arguments(validate_parser)

    run_parser = commands.add_parser("run")
    run_parser.add_argument("--mode", choices=("smoke", "conformance", "study"), required=True)
    run_parser.add_argument("--suite", choices=("pr", "full"), default="pr")
    run_parser.add_argument("--output", type=_relative_output, required=True)
    _add_admission_arguments(run_parser)

    reproduce_parser = commands.add_parser("reproduce")
    reproduce_parser.add_argument("--phase", choices=("declare", "run", "verify"), required=True)
    reproduce_parser.add_argument("--output", type=_relative_output, required=True)
    reproduce_parser.add_argument("--source-root", type=Path)
    reproduce_parser.add_argument("--bundle", type=Path)
    return parser


def _add_admission_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the complete native-run admission surface to a command.

    The participant surface is a closed union: CybORG selects a red variant and a
    blue implementation, NASim selects only its red attacker. Each backend admits
    exactly its own participant arguments and requires the other's absent, so a
    new backend never inherits another's participant surface.
    """

    parser.add_argument("--backend", choices=_BACKEND_CHOICES, default="cyborg-cage2")
    parser.add_argument("--pack")
    parser.add_argument("--pack-digest")
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--scenario-digest")
    parser.add_argument("--experiment", type=Path)
    parser.add_argument("--task", type=Path)
    parser.add_argument("--red-variant", choices=("b-line", "meander", "sleep"))
    parser.add_argument("--blue-implementation")
    parser.add_argument("--blue-manifest", type=Path)
    parser.add_argument("--blue-selection", type=Path)
    parser.add_argument("--blue-configuration", type=Path)
    parser.add_argument("--participant-implementation")
    parser.add_argument("--participant-manifest", type=Path)
    parser.add_argument("--participant-selection", type=Path)
    parser.add_argument("--participant-configuration", type=Path)
    parser.add_argument("--trial-length", type=int)
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument("--run-id")


def _supported_profiles() -> list[str]:
    """Return installed profiles fully supported by the CybORG manifest."""

    manifest = create_cyborg_manifest()
    profiles: list[str] = []
    for path in sorted(backend_profiles_root().glob("*.json")):
        profile = load_backend_profile(path.stem)
        if set(profile.required_contracts) <= set(manifest.supported_contract_versions):
            profiles.append(profile.profile)
    return profiles


def cyborg_inspection_payload() -> dict[str, object]:
    """Project installed identities without constructing the native backend."""

    manifest = create_cyborg_manifest()
    manifest_payload = backend_manifest_payload(manifest)
    qualification = load_qualification()
    try:
        verify_selected_cyborg_source()
        native_verified = True
    except Exception:
        native_verified = False
    return {
        "adapter": {
            "distribution": "raes-adapters",
            "version": metadata.version("raes-adapters"),
        },
        "backend": {
            "name": manifest.name,
            "version": manifest.version,
            "manifest_contract": manifest_payload["schema_version"],
            "native_available": native_verified,
        },
        "qualification": {
            "profile_id": qualification["profile_id"],
            "source_commit": qualification["source"]["commit"],
            "source_version": qualification["source"]["version"],
            "source_ledger": "/".join(CAGE2_SOURCE_26CE1C1.ledger_resource),
        },
        "supported_profiles": _supported_profiles(),
        "examples": ["cage2-research"],
    }


# --- CybORG backend adapter --------------------------------------------------

_CYBORG_EXAMPLE_MEMBERS = (
    *_COMMON_EXAMPLE_MEMBERS,
    "experiment/cage2-research.spec.exp.json",
    "experiment/cage2-research.task.exp.json",
    "participant/cyborg-blue-sleep-policy.configuration.json",
    "participant/cyborg-blue-sleep-policy.manifest.json",
    "participant/cyborg-blue-sleep-policy.selection.json",
    "sdl/cage2-research.sdl.yaml",
)


def _cyborg_native_args_complete(args: argparse.Namespace) -> bool:
    """Return whether every CybORG native admission argument was supplied."""

    required = (
        args.pack,
        args.pack_digest,
        args.scenario,
        args.scenario_digest,
        args.experiment,
        args.task,
        args.red_variant,
        args.blue_implementation,
        args.blue_manifest,
        args.blue_selection,
        args.blue_configuration,
        args.trial_length,
        args.seed,
        args.run_id,
    )
    foreign = (
        args.participant_implementation,
        args.participant_manifest,
        args.participant_selection,
        args.participant_configuration,
    )
    return all(value is not None for value in required) and all(value is None for value in foreign)


def _cyborg_participant_paths(args: argparse.Namespace) -> tuple[str, Path, Path, Path]:
    """Return the CybORG blue participant implementation and artifact paths."""

    return (
        args.blue_implementation,
        args.blue_manifest,
        args.blue_selection,
        args.blue_configuration,
    )


def _cyborg_experiment_bindings_match(
    args: argparse.Namespace,
    scenario_digest: str,
    spec: ExperimentSpecModel,
    task: ExperimentTaskModel,
    artifact_bindings_admitted: bool,
) -> bool:
    """Verify scenario, task, plan, and artifact bindings for CybORG."""

    intended = spec.intended_scenario_ref
    plan = spec.run_plan
    return all(
        (
            scenario_digest == args.scenario_digest,
            intended is not None,
            intended is not None and intended.ref_digest == args.scenario_digest,
            intended is not None and intended.ref_path == args.scenario.as_posix(),
            task.scenario_ref.ref_digest == args.scenario_digest,
            task.scenario_ref.ref_path == args.scenario.as_posix(),
            spec.task_ref.ref_id == task.task_id,
            plan.episode_control.max_steps == args.trial_length,
            args.red_variant in plan.red_variant_selections,
            artifact_bindings_admitted,
        )
    )


def _cyborg_participant_bindings_match(
    args: argparse.Namespace,
    manifest: ParticipantImplementationManifestModel,
    selection: ParticipantImplementationSelectionModel,
    configuration: ParticipantConfigurationResultModel,
) -> bool:
    """Verify CybORG blue participant identity, artifact, and capability bindings."""

    capabilities = manifest.capabilities
    return all(
        (
            args.blue_implementation == manifest.identity.name,
            selection.implementation_identity == manifest.identity,
            configuration.configuration.implementation_identity == manifest.identity,
            selection.manifest_ref == args.blue_manifest.as_posix(),
            configuration.manifest_ref == args.blue_manifest.as_posix(),
            selection.configuration_ref == args.blue_configuration.as_posix(),
            selection.manifest_digest == canonical_contract_digest(manifest),
            "cyborg-cage2" in manifest.compatibility.backends,
            selection.selected_decision_surface_mode
            in capabilities.supported_decision_surface_modes,
            set(selection.participant_contract_versions)
            <= set(capabilities.supported_participant_contracts),
            set(selection.exposure_policy.exposure_policy_kinds)
            <= set(capabilities.exposure_policy_kinds),
        )
    )


def _cyborg_admitted_seeds(args: argparse.Namespace, spec: ExperimentSpecModel) -> tuple[int, ...]:
    """Return seeds only when they exactly satisfy the selected CybORG run mode."""

    plan = spec.run_plan
    declared_seeds = tuple(
        item.value
        for item in plan.stochastic_controls
        if item.role == "seed" and type(item.value) is int
    )
    if any(type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF for seed in args.seed):
        raise _ValidationFailure
    seeds = tuple(args.seed)
    if args.mode == "smoke":
        if len(seeds) != 1 or seeds[0] not in declared_seeds:
            raise _ValidationFailure
    elif seeds != declared_seeds or plan.target_run_count != len(seeds):
        raise _ValidationFailure
    return seeds


def _cyborg_build_controls(
    args: argparse.Namespace, admitted: _AdmittedRun, run_id: str, seed: int
) -> object:
    """Bind one admitted seed and run identity to the CybORG controls."""

    return cyborg_researcher.RunControls(
        run_id=run_id,
        seed=seed,
        max_steps=args.trial_length,
        red_variant=args.red_variant,
        blue_manifest=admitted.participant_manifest,
        blue_selection=admitted.participant_selection,
        blue_configuration=admitted.participant_configuration,
    )


def _cyborg_provenance_payload(
    args: argparse.Namespace, admitted: _AdmittedRun
) -> dict[str, object]:
    """Return the CybORG selected adapter, pack, scenario, source, and controls."""

    qualification = load_qualification()
    return {
        "adapter": {
            "distribution": "raes-adapters",
            "version": metadata.version("raes-adapters"),
        },
        "backend_manifest": backend_manifest_payload(create_cyborg_manifest()),
        "configuration": {
            "blue_implementation": args.blue_implementation,
            "blue_manifest": args.blue_manifest.as_posix(),
            "blue_selection": args.blue_selection.as_posix(),
            "blue_configuration": args.blue_configuration.as_posix(),
            "experiment_id": admitted.spec.spec_id,
            "experiment_version": admitted.spec.spec_version,
            "mode": args.mode,
            "red_variant": args.red_variant,
            "run_id": args.run_id,
            "seeds": list(admitted.seeds),
            "trial_length": args.trial_length,
        },
        "environment_pack": {"digest": admitted.pack_digest, "identity": args.pack},
        "scenario": {
            "digest": admitted.scenario_digest,
            "identity": args.scenario.as_posix(),
        },
        "source": {
            "commit": qualification["source"]["commit"],
            "version": qualification["source"]["version"],
        },
    }


def _cyborg_machine_software() -> dict[str, str]:
    """Return the CybORG-relevant installed distribution identities."""

    return {
        "CybORG": _installed_version("CybORG"),
        "raes": _installed_version("raes"),
        "raes-adapters": _installed_version("raes-adapters"),
        "raes-env-packs": _installed_version("raes-env-packs"),
    }


# --- NASim backend adapter ---------------------------------------------------

_NASIM_EXAMPLE_MEMBERS = (
    *_COMMON_EXAMPLE_MEMBERS,
    "experiment/nasim-tiny.spec.exp.json",
    "experiment/nasim-tiny.task.exp.json",
    "participant/nasim-red-bruteforce.configuration.json",
    "participant/nasim-red-bruteforce.manifest.json",
    "participant/nasim-red-bruteforce.selection.json",
    "sdl/nasim-tiny.sdl.yaml",
)


def _nasim_native_args_complete(args: argparse.Namespace) -> bool:
    """Return whether every NASim native admission argument was supplied."""

    return _single_participant_native_args_complete(args)


def _nasim_participant_paths(args: argparse.Namespace) -> tuple[str, Path, Path, Path]:
    """Return the NASim red participant implementation and artifact paths."""

    return (
        args.participant_implementation,
        args.participant_manifest,
        args.participant_selection,
        args.participant_configuration,
    )


def _nasim_experiment_bindings_match(
    args: argparse.Namespace,
    scenario_digest: str,
    spec: ExperimentSpecModel,
    task: ExperimentTaskModel,
    artifact_bindings_admitted: bool,
) -> bool:
    """Verify scenario, task, plan, and artifact bindings for NASim.

    NASim declares no red variant; its single autonomous attacker is fixed by the
    admitted participant implementation.
    """

    return _single_participant_experiment_bindings_match(
        args,
        scenario_digest,
        spec,
        task,
        artifact_bindings_admitted,
    )


def _nasim_participant_bindings_match(
    args: argparse.Namespace,
    manifest: ParticipantImplementationManifestModel,
    selection: ParticipantImplementationSelectionModel,
    configuration: ParticipantConfigurationResultModel,
) -> bool:
    """Verify NASim red participant identity, artifact, and capability bindings."""

    capabilities = manifest.capabilities
    return all(
        (
            args.participant_implementation == manifest.identity.name,
            selection.participant_address == _RED_PARTICIPANT_ADDRESS,
            selection.implementation_identity == manifest.identity,
            configuration.configuration.implementation_identity == manifest.identity,
            selection.manifest_ref == args.participant_manifest.as_posix(),
            configuration.manifest_ref == args.participant_manifest.as_posix(),
            selection.configuration_ref == args.participant_configuration.as_posix(),
            selection.manifest_digest == canonical_contract_digest(manifest),
            "nasim-tiny" in manifest.compatibility.backends,
            selection.selected_decision_surface_mode
            in capabilities.supported_decision_surface_modes,
            set(selection.participant_contract_versions)
            <= set(capabilities.supported_participant_contracts),
            set(selection.exposure_policy.exposure_policy_kinds)
            <= set(capabilities.exposure_policy_kinds),
        )
    )


def _nasim_admitted_seeds(args: argparse.Namespace, spec: ExperimentSpecModel) -> tuple[int, ...]:
    """Return seeds only when they satisfy the NASim run mode.

    NASim's stochastic controls are descriptive strings: the selected static
    benchmark binds action success through the unbound global NumPy stream, not
    the gym reset seed (ADR-069). The operator seed must equal a declared control
    value and satisfy the mode cardinality; binding it is never a replay claim.
    """

    plan = spec.run_plan
    declared = tuple(
        str(item.value)
        for item in plan.stochastic_controls
        if item.role in {"seed", "randomization"}
    )
    if any(type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF for seed in args.seed):
        raise _ValidationFailure
    seeds = tuple(args.seed)
    if any(str(seed) not in declared for seed in seeds):
        raise _ValidationFailure
    if args.mode == "smoke":
        if len(seeds) != 1:
            raise _ValidationFailure
    elif plan.target_run_count != len(seeds):
        raise _ValidationFailure
    return seeds


def _nasim_build_controls(
    args: argparse.Namespace, admitted: _AdmittedRun, run_id: str, seed: int
) -> object:
    """Bind one admitted seed and run identity to the NASim red controls."""

    return nasim_researcher.RunControls(
        run_id=run_id,
        seed=seed,
        max_steps=args.trial_length,
        red_manifest=admitted.participant_manifest,
        red_selection=admitted.participant_selection,
        red_configuration=admitted.participant_configuration,
    )


def _nasim_provenance_payload(
    args: argparse.Namespace, admitted: _AdmittedRun
) -> dict[str, object]:
    """Return the NASim selected adapter, pack, scenario, source, and controls."""

    qualification = load_nasim_qualification()
    source = qualification["source"]
    return {
        "adapter": {
            "distribution": "raes-adapters",
            "version": metadata.version("raes-adapters"),
        },
        "backend_manifest": backend_manifest_payload(create_nasim_manifest()),
        "configuration": {
            "participant_implementation": args.participant_implementation,
            "participant_manifest": args.participant_manifest.as_posix(),
            "participant_selection": args.participant_selection.as_posix(),
            "participant_configuration": args.participant_configuration.as_posix(),
            "experiment_id": admitted.spec.spec_id,
            "experiment_version": admitted.spec.spec_version,
            "mode": args.mode,
            "run_id": args.run_id,
            "seeds": list(admitted.seeds),
            "trial_length": args.trial_length,
        },
        "environment_pack": {"digest": admitted.pack_digest, "identity": args.pack},
        "scenario": {
            "digest": admitted.scenario_digest,
            "identity": args.scenario.as_posix(),
        },
        "source": {
            "commit": source["commit"],
            "version": source["version"],
        },
    }


def _nasim_machine_software() -> dict[str, str]:
    """Return the NASim-relevant installed distribution identities."""

    return {
        "nasim": _installed_version("nasim"),
        "gymnasium": _installed_version("gymnasium"),
        "raes": _installed_version("raes"),
        "raes-adapters": _installed_version("raes-adapters"),
        "raes-env-packs": _installed_version("raes-env-packs"),
    }


# --- CyberBattleSim backend adapter -----------------------------------------

_CYBERBATTLESIM_EXAMPLE_MEMBERS = (
    *_COMMON_EXAMPLE_MEMBERS,
    "experiment/cyberbattlesim-chain.spec.exp.json",
    "experiment/cyberbattlesim-chain.task.exp.json",
    "participant/cyberbattlesim-red-credential-cache.configuration.json",
    "participant/cyberbattlesim-red-credential-cache.manifest.json",
    "participant/cyberbattlesim-red-credential-cache.selection.json",
    "sdl/cyberbattlesim-chain.sdl.yaml",
)
_CYBERBATTLESIM_PACK_DIGEST = (
    "sha256:08ae7e997b50bb396c290c4a5537a65e9e7d8b8e6abc97d1ff65022c4258e417"
)


def _cyberbattlesim_native_args_complete(args: argparse.Namespace) -> bool:
    """Require the complete chain pack surface and reject foreign arguments."""

    return _single_participant_native_args_complete(args)


def _cyberbattlesim_participant_paths(
    args: argparse.Namespace,
) -> tuple[str, Path, Path, Path]:
    """Return the admitted credential-cache policy artifact paths."""

    return (
        args.participant_implementation,
        args.participant_manifest,
        args.participant_selection,
        args.participant_configuration,
    )


def _cyberbattlesim_experiment_bindings_match(
    args: argparse.Namespace,
    scenario_digest: str,
    spec: ExperimentSpecModel,
    task: ExperimentTaskModel,
    artifact_bindings_admitted: bool,
) -> bool:
    """Verify the exact selected chain scenario, protocol, and participant bytes."""

    return _single_participant_experiment_bindings_match(
        args,
        scenario_digest,
        spec,
        task,
        artifact_bindings_admitted,
    )


def _cyberbattlesim_participant_bindings_match(
    args: argparse.Namespace,
    manifest: ParticipantImplementationManifestModel,
    selection: ParticipantImplementationSelectionModel,
    configuration: ParticipantConfigurationResultModel,
) -> bool:
    """Verify the selected policy identity and its published configuration."""

    capabilities = manifest.capabilities
    values = {
        item.target_id: item.value.value
        for item in configuration.configuration.values
        if item.value.kind == "literal"
    }
    return all(
        (
            args.participant_implementation == manifest.identity.name,
            selection.participant_address == _RED_PARTICIPANT_ADDRESS,
            selection.implementation_identity == manifest.identity,
            configuration.configuration.implementation_identity == manifest.identity,
            selection.manifest_ref == args.participant_manifest.as_posix(),
            configuration.manifest_ref == args.participant_manifest.as_posix(),
            selection.configuration_ref == args.participant_configuration.as_posix(),
            selection.manifest_digest == canonical_contract_digest(manifest),
            "cyberbattlesim-chain" in manifest.compatibility.backends,
            selection.selected_decision_surface_mode
            in capabilities.supported_decision_surface_modes,
            set(selection.participant_contract_versions)
            <= set(capabilities.supported_participant_contracts),
            set(selection.exposure_policy.exposure_policy_kinds)
            <= set(capabilities.exposure_policy_kinds),
            values.get("red-policy-identity") == "CredentialCacheExploiter",
        )
    )


def _cyberbattlesim_admitted_seeds(
    args: argparse.Namespace, spec: ExperimentSpecModel
) -> tuple[int, ...]:
    """Bind the one documented seed without claiming deterministic replay."""

    declared = {
        str(item.value)
        for item in spec.run_plan.stochastic_controls
        if item.role in {"seed", "sampling", "randomization"}
    }
    if any(type(seed) is not int or str(seed) not in declared for seed in args.seed):
        raise _ValidationFailure
    seeds = tuple(args.seed)
    if args.mode == "smoke":
        if len(seeds) != 1:
            raise _ValidationFailure
    elif len(seeds) != spec.run_plan.target_run_count:
        raise _ValidationFailure
    return seeds


def _cyberbattlesim_build_controls(
    args: argparse.Namespace, admitted: _AdmittedRun, run_id: str, seed: int
) -> object:
    """Bind one admitted episode to the exact source policy and controls."""

    return cyberbattlesim_researcher.RunControls(
        run_id=run_id,
        seed=seed,
        max_steps=args.trial_length,
        red_manifest=admitted.participant_manifest,
        red_selection=admitted.participant_selection,
        red_configuration=admitted.participant_configuration,
    )


def _cyberbattlesim_provenance_payload(
    args: argparse.Namespace, admitted: _AdmittedRun
) -> dict[str, object]:
    """Return selected adapter, pack, scenario, source, policy, and controls."""

    qualification = load_cyberbattlesim_qualification()
    source = qualification["source"]
    return {
        "adapter": {
            "distribution": "raes-adapters",
            "version": metadata.version("raes-adapters"),
        },
        "backend_manifest": backend_manifest_payload(create_cyberbattlesim_manifest()),
        "configuration": {
            "participant_implementation": args.participant_implementation,
            "participant_manifest": args.participant_manifest.as_posix(),
            "participant_selection": args.participant_selection.as_posix(),
            "participant_configuration": args.participant_configuration.as_posix(),
            "experiment_id": admitted.spec.spec_id,
            "experiment_version": admitted.spec.spec_version,
            "mode": args.mode,
            "run_id": args.run_id,
            "seeds": list(admitted.seeds),
            "trial_length": args.trial_length,
        },
        "environment_pack": {
            "digest": admitted.pack_digest,
            "identity": "cyberbattlesim-chain",
        },
        "scenario": {
            "digest": admitted.scenario_digest,
            "identity": args.scenario.as_posix(),
        },
        "source": {"commit": source["commit"], "version": source["version"]},
    }


def _cyberbattlesim_machine_software() -> dict[str, str]:
    """Return CyberBattleSim-relevant installed distribution identities."""

    return {
        "cyberbattlesim": _installed_version("cyberbattlesim"),
        "gymnasium": _installed_version("gymnasium"),
        "numpy": _installed_version("numpy"),
        "raes": _installed_version("raes"),
        "raes-adapters": _installed_version("raes-adapters"),
        "raes-env-packs": _installed_version("raes-env-packs"),
    }


_BACKENDS: dict[str, _BackendAdapter] = {
    "cyborg-cage2": _BackendAdapter(
        name="cyborg-cage2",
        participant_address="participant.behavior.blue",
        pack_example_id="cage2-research",
        pack_package="raes_adapters.cyborg",
        packaged_example=True,
        expected_pack_digest=None,
        example_members=_CYBORG_EXAMPLE_MEMBERS,
        native_module="CybORG",
        inspection_payload=lambda: cyborg_inspection_payload(),
        verify_source=lambda: verify_selected_cyborg_source(),
        create_target=create_cyborg_target,
        researcher=cyborg_researcher,
        backend_manifest=create_cyborg_manifest,
        conformance_suite=run_cyborg_conformance_suite,
        conformance_evidence_basis="hermetic-live",
        native_args_complete=_cyborg_native_args_complete,
        participant_paths=_cyborg_participant_paths,
        experiment_bindings_match=_cyborg_experiment_bindings_match,
        participant_bindings_match=_cyborg_participant_bindings_match,
        admitted_seeds=_cyborg_admitted_seeds,
        build_controls=_cyborg_build_controls,
        episode_provenance=cyborg_researcher.blue_implementation_provenance,
        evidence_source_label="cyborg-cage2 evaluator projection",
        evidence_satisfies_refs=("source-ledger:reward-components",),
        provenance_payload=_cyborg_provenance_payload,
        machine_software=_cyborg_machine_software,
    ),
    "nasim-tiny": _BackendAdapter(
        name="nasim-tiny",
        participant_address=_RED_PARTICIPANT_ADDRESS,
        pack_example_id="nasim-tiny",
        pack_package="raes_adapters.nasim",
        packaged_example=True,
        expected_pack_digest=None,
        example_members=_NASIM_EXAMPLE_MEMBERS,
        native_module="nasim",
        inspection_payload=nasim_researcher.nasim_inspection_payload,
        verify_source=verify_selected_nasim_source,
        create_target=create_nasim_target,
        researcher=nasim_researcher,
        backend_manifest=create_nasim_manifest,
        conformance_suite=nasim_researcher.nasim_conformance_suite,
        conformance_evidence_basis="installed-source-probe",
        native_args_complete=_nasim_native_args_complete,
        participant_paths=_nasim_participant_paths,
        experiment_bindings_match=_nasim_experiment_bindings_match,
        participant_bindings_match=_nasim_participant_bindings_match,
        admitted_seeds=_nasim_admitted_seeds,
        build_controls=_nasim_build_controls,
        episode_provenance=nasim_researcher.red_implementation_provenance,
        evidence_source_label="nasim-tiny evaluator projection",
        evidence_satisfies_refs=("attacker-action-log", "host-compromise-series"),
        provenance_payload=_nasim_provenance_payload,
        machine_software=_nasim_machine_software,
    ),
    "cyberbattlesim-chain": _BackendAdapter(
        name="cyberbattlesim-chain",
        participant_address=_RED_PARTICIPANT_ADDRESS,
        pack_example_id="cyberbattlesim-chain",
        pack_package="raes_adapters.cyberbattlesim",
        packaged_example=False,
        expected_pack_digest=_CYBERBATTLESIM_PACK_DIGEST,
        example_members=_CYBERBATTLESIM_EXAMPLE_MEMBERS,
        native_module="cyberbattle",
        inspection_payload=cyberbattlesim_researcher.cyberbattlesim_inspection_payload,
        verify_source=verify_selected_cyberbattlesim_source,
        create_target=create_cyberbattlesim_target,
        researcher=cyberbattlesim_researcher,
        backend_manifest=create_cyberbattlesim_manifest,
        conformance_suite=cyberbattlesim_researcher.cyberbattlesim_conformance_suite,
        conformance_evidence_basis="installed-source-probe",
        native_args_complete=_cyberbattlesim_native_args_complete,
        participant_paths=_cyberbattlesim_participant_paths,
        experiment_bindings_match=_cyberbattlesim_experiment_bindings_match,
        participant_bindings_match=_cyberbattlesim_participant_bindings_match,
        admitted_seeds=_cyberbattlesim_admitted_seeds,
        build_controls=_cyberbattlesim_build_controls,
        episode_provenance=cyberbattlesim_researcher.red_implementation_provenance,
        evidence_source_label="cyberbattlesim-chain evaluator projection",
        evidence_satisfies_refs=("attacker-action-log", "availability-series"),
        provenance_payload=_cyberbattlesim_provenance_payload,
        machine_software=_cyberbattlesim_machine_software,
    ),
}


def _adapter(args: argparse.Namespace) -> _BackendAdapter:
    """Resolve the closed backend adapter for one parsed command."""

    return _BACKENDS[args.backend]


@contextmanager
def _pack_root(adapter: _BackendAdapter, value: str) -> Iterator[Path]:
    """Resolve a named packaged example or caller-selected pack root."""

    if value != adapter.pack_example_id or not adapter.packaged_example:
        yield Path(value)
        return
    package_root = resources.files(adapter.pack_package) / "examples" / value
    with tempfile.TemporaryDirectory(prefix="raes-adapters-pack-") as scratch:
        staged = Path(scratch) / value
        staged.mkdir(mode=0o700)
        for relative in adapter.example_members:
            target = staged / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.write_bytes(package_root.joinpath(*Path(relative).parts).read_bytes())
        yield staged


def _pack_child(pack: Path, relative: Path) -> Path:
    """Resolve an existing pack child without permitting traversal."""

    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise _ValidationFailure
    root = pack.resolve()
    child = (root / relative).resolve()
    try:
        child.relative_to(root)
    except ValueError as error:
        raise _ValidationFailure from error
    if not child.is_file():
        raise _ValidationFailure
    return child


def _strict_json(path: Path) -> object:
    """Load JSON while rejecting duplicate keys and invalid text."""

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        """Construct a mapping only when every key is unique."""

        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _ValidationFailure
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _ValidationFailure from error


def _artifact_declared_by_spec(
    spec: ExperimentSpecModel, relative: Path, path: Path, role: str
) -> bool:
    """Verify that an exact artifact byte sequence is declared by the spec."""

    payload = path.read_bytes()
    expected_uri = f"pack:/{relative.as_posix()}"
    expected_checksum = hashlib.sha256(payload).hexdigest()
    return any(
        artifact.uri == expected_uri
        and artifact.role == role
        and artifact.checksum.algorithm == "sha256"
        and artifact.checksum.value == expected_checksum
        and artifact.size_bytes == len(payload)
        for artifact in spec.artifact_refs
    )


def _load_pack_artifacts(
    adapter: _BackendAdapter,
    args: argparse.Namespace,
) -> tuple[
    object,
    str,
    ExperimentSpecModel,
    ExperimentTaskModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantConfigurationResultModel,
    bool,
]:
    """Validate a pack and load its byte-bound RAES authoring artifacts."""

    try:
        pack_contracts = import_module("raes_env_packs")
    except ImportError as error:
        raise _ValidationFailure from error
    _implementation, manifest_arg, selection_arg, configuration_arg = adapter.participant_paths(
        args
    )
    with _pack_root(adapter, args.pack) as pack:
        try:
            if (
                adapter.expected_pack_digest is not None
                and args.pack_digest != adapter.expected_pack_digest
            ):
                raise _ValidationFailure
            pack_admitted = pack_contracts.validate_pack(pack).ok
            digest_admitted = pack_contracts.verify_pack_content_digest(pack, args.pack_digest)
        except Exception as error:
            raise _ValidationFailure from error
        if not pack_admitted or not digest_admitted:
            raise _ValidationFailure
        scenario_path = _pack_child(pack, args.scenario)
        experiment_path = _pack_child(pack, args.experiment)
        task_path = _pack_child(pack, args.task)
        manifest_path = _pack_child(pack, manifest_arg)
        selection_path = _pack_child(pack, selection_arg)
        configuration_path = _pack_child(pack, configuration_arg)
        try:
            scenario = raes.parse_sdl_file(scenario_path)
            instantiated = raes.instantiate_scenario(scenario)
            scenario_digest = raes.canonical_instantiated_sdl_digest(instantiated).value
            spec = ExperimentSpecModel.model_validate(_strict_json(experiment_path))
            task = ExperimentTaskModel.model_validate(_strict_json(task_path))
            participant_manifest = ParticipantImplementationManifestModel.model_validate(
                _strict_json(manifest_path)
            )
            participant_selection = ParticipantImplementationSelectionModel.model_validate(
                _strict_json(selection_path)
            )
            participant_configuration = ParticipantConfigurationResultModel.model_validate(
                _strict_json(configuration_path)
            )
            validate_participant_configuration_selection(
                participant_selection, participant_configuration
            )
        except Exception as error:
            raise _ValidationFailure from error
        artifact_bindings_admitted = all(
            (
                _artifact_declared_by_spec(spec, manifest_arg, manifest_path, "manifest"),
                _artifact_declared_by_spec(spec, selection_arg, selection_path, "configuration"),
                _artifact_declared_by_spec(
                    spec, configuration_arg, configuration_path, "configuration"
                ),
            )
        )
    return (
        scenario,
        scenario_digest,
        spec,
        task,
        participant_manifest,
        participant_selection,
        participant_configuration,
        artifact_bindings_admitted,
    )


def _validate_runtime_plan(
    adapter: _BackendAdapter, scenario: object, seeds: tuple[int, ...]
) -> None:
    """Require the published runtime manager to admit the instantiated plan."""

    try:
        from raes_runtime.manager import RuntimeManager  # type: ignore[import-untyped]

        planned = RuntimeManager(adapter.create_target(seed=seeds[0])).plan(scenario)
    except Exception as error:
        raise _ValidationFailure from error
    if any(item.is_error for item in planned.diagnostics):
        raise _ValidationFailure


def _admit_native_run(adapter: _BackendAdapter, args: argparse.Namespace) -> _AdmittedRun:
    """Admit all authoring, participant, and runtime controls before execution."""

    if not adapter.native_args_complete(args):
        raise _ValidationFailure
    (
        scenario,
        scenario_digest,
        spec,
        task,
        participant_manifest,
        participant_selection,
        participant_configuration,
        artifact_bindings_admitted,
    ) = _load_pack_artifacts(adapter, args)
    if not adapter.experiment_bindings_match(
        args, scenario_digest, spec, task, artifact_bindings_admitted
    ) or not adapter.participant_bindings_match(
        args, participant_manifest, participant_selection, participant_configuration
    ):
        raise _ValidationFailure
    if not 1 <= len(args.run_id) <= 64 or not args.run_id.replace("-", "").isalnum():
        raise _ValidationFailure
    seeds = adapter.admitted_seeds(args, spec)
    _validate_runtime_plan(adapter, scenario, seeds)
    try:
        adapter.build_controls(
            args,
            _AdmittedRun(
                args.pack_digest,
                scenario,
                scenario_digest,
                spec,
                task,
                participant_manifest,
                participant_selection,
                participant_configuration,
                seeds,
            ),
            args.run_id,
            seeds[0],
        )
    except Exception as error:
        raise _ValidationFailure from error
    return _AdmittedRun(
        args.pack_digest,
        scenario,
        scenario_digest,
        spec,
        task,
        participant_manifest,
        participant_selection,
        participant_configuration,
        seeds,
    )


def _reserve_output(requested: Path) -> Path:
    """Create an exclusive invocation-local output directory."""

    root = Path.cwd().resolve()
    resolved = (root / requested).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise _OutputFailure from error
    if not relative.parts:
        raise _OutputFailure
    try:
        os.mkdir(resolved, 0o700)
    except OSError as error:
        raise _OutputFailure from error
    return resolved


def _media_type(path: Path) -> str:
    """Return the portable media type used in the artifact inventory."""

    return "application/json" if path.suffix == ".json" else "application/octet-stream"


def _seal_inventory(output: Path) -> dict[str, object]:
    """Hash every portable artifact and atomically seal the inventory."""

    artifacts: list[dict[str, object]] = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        if path.name == _INVENTORY_NAME:
            continue
        payload = path.read_bytes()
        artifacts.append(
            {
                "media_type": _media_type(path),
                "path": path.relative_to(output).as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        )
    inventory: dict[str, object] = {"artifacts": artifacts}
    atomic_write_json_artifact(output / _INVENTORY_NAME, inventory)
    return inventory


def _emit_error(code: str, message: str) -> None:
    """Emit one stable diagnostic without exception or native details."""

    print(f"{code}: {message}", file=sys.stderr)


def _retain_failure(output: Path, code: str, message: str) -> None:
    """Best-effort retain a portable failure artifact in a reserved output."""

    diagnostic = DiagnosticModel(
        code=code,
        domain="orchestration",
        address="",
        message=message,
        severity="error",
    )
    with contextlib.suppress(Exception):
        atomic_write_json_artifact(output / "failure.json", diagnostic.model_dump(mode="json"))


def _run_conformance(adapter: _BackendAdapter, args: argparse.Namespace) -> int:
    """Run the selected backend conformance suite and seal its evidence."""

    admitted: _AdmittedRun | None = None
    if adapter.expected_pack_digest is not None:
        try:
            admitted = _admit_native_run(adapter, args)
        except _ValidationFailure:
            raise _CommandFailure(
                EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE
            ) from None
        if util.find_spec(adapter.native_module) is None:
            raise _CommandFailure(
                EXIT_RUNTIME,
                "researcher.runtime.native-unavailable",
                "qualified native source is unavailable",
            )
        try:
            adapter.verify_source()
        except Exception:
            raise _CommandFailure(
                EXIT_VALIDATION,
                "researcher.validation.source-invalid",
                "qualified native source was not admitted",
            ) from None
    try:
        output = _reserve_output(args.output)
    except _OutputFailure:
        raise _CommandFailure(
            EXIT_OUTPUT, _OUTPUT_UNAVAILABLE_CODE, _OUTPUT_UNAVAILABLE_MESSAGE
        ) from None
    try:
        conformance_args: dict[str, object] = {
            "suite": args.suite,
            "output_dir": output,
        }
        if admitted is not None:
            conformance_args.update(
                {
                    "participant_manifest": admitted.participant_manifest,
                    "participant_selection": admitted.participant_selection,
                    "participant_configuration": admitted.participant_configuration,
                }
            )
        result = adapter.conformance_suite(**conformance_args)
    except Exception:
        _retain_failure(output, _RUNTIME_FAILURE_CODE, "conformance execution failed")
        raise _CommandFailure(
            EXIT_RUNTIME, _RUNTIME_FAILURE_CODE, "conformance execution failed"
        ) from None
    try:
        _seal_inventory(output)
    except Exception:
        raise _CommandFailure(
            EXIT_ARTIFACT,
            "researcher.artifact.failure",
            "portable evidence could not be sealed",
        ) from None
    print(
        json.dumps(
            {
                "disposition": "succeeded",
                "evidence_basis": adapter.conformance_evidence_basis,
                "inventory": _INVENTORY_NAME,
                "mode": "conformance",
                "run_count": len(result["reports"]),  # type: ignore[arg-type]
            },
            sort_keys=True,
        )
    )
    return 0


def _installed_version(name: str) -> str:
    """Return an installed distribution version or a stable absence marker."""

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


def _native_environment(
    adapter: _BackendAdapter, args: argparse.Namespace
) -> tuple[_AdmittedRun, Path]:
    """Admit native inputs, selected source, and the exclusive output root."""

    try:
        admitted = _admit_native_run(adapter, args)
    except _ValidationFailure:
        raise _CommandFailure(
            EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE
        ) from None
    if util.find_spec(adapter.native_module) is None:
        raise _CommandFailure(
            EXIT_RUNTIME,
            "researcher.runtime.native-unavailable",
            "qualified native source is unavailable",
        )
    try:
        adapter.verify_source()
    except Exception:
        raise _CommandFailure(
            EXIT_VALIDATION,
            "researcher.validation.source-invalid",
            "qualified native source was not admitted",
        ) from None
    try:
        output = _reserve_output(args.output)
    except _OutputFailure:
        raise _CommandFailure(
            EXIT_OUTPUT, _OUTPUT_UNAVAILABLE_CODE, _OUTPUT_UNAVAILABLE_MESSAGE
        ) from None
    return admitted, output


def _execute_quietly(
    adapter: _BackendAdapter, scenario: object, controls: object, output: Path
) -> _EpisodeEvidence:
    """Execute one episode while suppressing all native process output."""

    try:
        with (
            Path(os.devnull).open("w", encoding="utf-8") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            return cast(_EpisodeEvidence, adapter.researcher.execute_episode(scenario, controls))
    except Exception:
        message = "native execution or cleanup failed"
        _retain_failure(output, _RUNTIME_FAILURE_CODE, message)
        raise _CommandFailure(EXIT_RUNTIME, _RUNTIME_FAILURE_CODE, message) from None


def _write_episode_evidence(
    adapter: _BackendAdapter,
    run_output: Path,
    run_id: str,
    index: int,
    result: _EpisodeEvidence,
    admitted: _AdmittedRun,
) -> ExperimentArtifactRefModel:
    """Write portable episode projections and return their archival reference."""

    evidence_path = run_output / "evidence-records.json"
    atomic_write_json_artifact(
        evidence_path, [item.model_dump(mode="json") for item in result.evidence_records]
    )
    evidence_bytes = evidence_path.read_bytes()
    atomic_write_json_artifact(
        run_output / "derived-measures.json",
        [item.model_dump(mode="json") for item in result.derived_measures],
    )
    atomic_write_json_artifact(
        run_output / "diagnostics.json",
        [item.model_dump(mode="json") for item in result.diagnostics],
    )
    atomic_write_json_artifact(
        run_output / "participant-provenance.json",
        adapter.episode_provenance(
            result.evidence_records[0].run_ref.ref_id, admitted.participant_selection
        ).model_dump(mode="json"),
    )
    return ExperimentArtifactRefModel(
        artifact_id=f"portable-evidence-{index}",
        role="observation",
        media_type="application/json",
        uri=f"runs/{run_id}/evidence-records.json",
        checksum={"algorithm": "sha256", "value": hashlib.sha256(evidence_bytes).hexdigest()},
        size_bytes=len(evidence_bytes),
        created_at=result.evidence_records[0].captured_at,
        source=adapter.evidence_source_label,
        satisfies_refs=[
            {"ref_kind": "evidence", "ref_id": ref} for ref in adapter.evidence_satisfies_refs
        ],
        sensitivity="redacted",
    )


def _complete_native_run(
    adapter: _BackendAdapter,
    args: argparse.Namespace,
    admitted: _AdmittedRun,
    runs: Path,
    index: int,
    seed: int,
    output: Path,
) -> _CompletedRun:
    """Execute and archive one admitted native episode."""

    run_id = f"{args.run_id}-{index}"
    run_output = runs / run_id
    os.mkdir(run_output, 0o700)
    controls = adapter.build_controls(args, admitted, run_id, seed)
    result = _execute_quietly(adapter, admitted.scenario, controls, output)
    evidence_artifact = _write_episode_evidence(
        adapter, run_output, run_id, index, result, admitted
    )
    run_record = adapter.researcher.archival_run(
        controls=controls,
        scenario_digest=admitted.scenario_digest,
        task=admitted.task,
        episode=result,
        evidence_artifact=evidence_artifact,
    )
    validate_experiment_run_against_task(admitted.task, run_record)
    atomic_write_json_artifact(run_output / "run.json", run_record.model_dump(mode="json"))
    summary = {
        "cleanup_verified": result.cleanup_verified,
        "completed_steps": result.completed_steps,
        "derived_measure_count": len(result.derived_measures),
        "evidence_record_count": len(result.evidence_records),
        "run_id": run_id,
        "seed": seed,
    }
    atomic_write_json_artifact(run_output / "summary.json", summary)
    return _CompletedRun(run_record, summary)


def _write_study(
    adapter: _BackendAdapter,
    args: argparse.Namespace,
    admitted: _AdmittedRun,
    output: Path,
    runs: list[ExperimentRunModel],
) -> None:
    """Write the declared study collection when study mode was selected."""

    if args.mode == "study":
        study = adapter.researcher.archival_collection(admitted.task, runs, args.run_id)
        validate_experiment_study_against_tasks_and_runs(study, [admitted.task], runs)
        atomic_write_json_artifact(output / "study.json", study.model_dump(mode="json"))


def _write_provenance(
    adapter: _BackendAdapter, args: argparse.Namespace, admitted: _AdmittedRun, output: Path
) -> None:
    """Write selected adapter, pack, scenario, source, and control identities."""

    atomic_write_json_artifact(
        output / "provenance.json", adapter.provenance_payload(args, admitted)
    )


def _write_machine_inventory(adapter: _BackendAdapter, output: Path) -> None:
    """Write bounded platform and installed-distribution identities."""

    atomic_write_json_artifact(
        output / "machine-inventory.json",
        {
            "architecture": platform.machine(),
            "operating_system": platform.system(),
            "operating_system_release": platform.release(),
            "python": {
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
            },
            "software": adapter.machine_software(),
        },
    )


def _write_batch_artifacts(
    adapter: _BackendAdapter, args: argparse.Namespace, admitted: _AdmittedRun, output: Path
) -> list[_CompletedRun]:
    """Execute the admitted batch and seal all portable batch artifacts."""

    runs_root = output / "runs"
    os.mkdir(runs_root, 0o700)
    completed = [
        _complete_native_run(adapter, args, admitted, runs_root, index, seed, output)
        for index, seed in enumerate(admitted.seeds, start=1)
    ]
    _write_study(adapter, args, admitted, output, [item.archival for item in completed])
    _write_provenance(adapter, args, admitted, output)
    _write_machine_inventory(adapter, output)
    atomic_write_json_artifact(
        output / "summary.json",
        {
            "disposition": "succeeded",
            "mode": args.mode,
            "run_count": len(completed),
            "runs": [item.summary for item in completed],
        },
    )
    _seal_inventory(output)
    return completed


def _run_native(adapter: _BackendAdapter, args: argparse.Namespace) -> int:
    """Execute an admitted native run batch and seal portable evidence."""

    admitted, output = _native_environment(adapter, args)
    try:
        completed = _write_batch_artifacts(adapter, args, admitted, output)
    except _CommandFailure:
        raise
    except Exception:
        raise _CommandFailure(
            EXIT_ARTIFACT,
            "researcher.artifact.failure",
            "portable evidence could not be sealed",
        ) from None
    print(
        json.dumps(
            {
                "disposition": "succeeded",
                "inventory": _INVENTORY_NAME,
                "mode": args.mode,
                "run_count": len(completed),
            },
            sort_keys=True,
        )
    )
    return 0


def _validated_admission(adapter: _BackendAdapter, args: argparse.Namespace) -> int:
    """Validate native controls and report the admitted run scope."""

    try:
        admitted = _admit_native_run(adapter, args)
    except _ValidationFailure:
        raise _CommandFailure(
            EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE
        ) from None
    print(
        json.dumps(
            {
                "disposition": "validated",
                "pack": "admitted",
                "participant": admitted.participant_manifest.identity.name,
                "run_count": len(admitted.seeds),
                "scope": "run-admission",
            },
            sort_keys=True,
        )
    )
    return 0


def _conformance_controls_absent(args: argparse.Namespace) -> bool:
    """Return whether no native-run controls accompanied conformance mode."""

    native_values = (
        args.pack,
        args.pack_digest,
        args.scenario,
        args.scenario_digest,
        args.experiment,
        args.task,
        args.red_variant,
        args.blue_implementation,
        args.blue_manifest,
        args.blue_selection,
        args.blue_configuration,
        args.participant_implementation,
        args.participant_manifest,
        args.participant_selection,
        args.participant_configuration,
        args.trial_length,
        args.seed,
        args.run_id,
    )
    return all(value is None for value in native_values)


def _dispatch(args: argparse.Namespace) -> int:
    """Dispatch one parsed command through its closed execution path."""

    if args.command == "reproduce":
        result = _reproduce(args)
    elif args.command == "inspect":
        print(json.dumps(_adapter(args).inspection_payload(), sort_keys=True))
        result = 0
    else:
        adapter = _adapter(args)
        result = (
            _validated_admission(adapter, args)
            if args.command == "validate"
            else _run_command(adapter, args)
        )
    return result


def _reproduce(args: argparse.Namespace) -> int:
    """Dispatch the frozen CAGE-2 study and offline recomputation paths."""

    source_root = args.source_root
    bundle = args.bundle
    if args.phase in {"declare", "run"}:
        if source_root is None or bundle is not None:
            raise _CommandFailure(
                EXIT_VALIDATION,
                _CONTROLS_INVALID_CODE,
                _CONTROLS_INVALID_MESSAGE,
            )
    elif bundle is None or source_root is not None:
        raise _CommandFailure(
            EXIT_VALIDATION,
            _CONTROLS_INVALID_CODE,
            _CONTROLS_INVALID_MESSAGE,
        )
    invocation_root = Path.cwd().resolve()
    output = (invocation_root / args.output).resolve()
    try:
        relative_output = output.relative_to(invocation_root)
    except ValueError:
        relative_output = None
    if relative_output is None or not relative_output.parts:
        raise _CommandFailure(
            EXIT_OUTPUT,
            _OUTPUT_UNAVAILABLE_CODE,
            _OUTPUT_UNAVAILABLE_MESSAGE,
        )
    result: dict[str, object]
    try:
        if args.phase == "declare":
            cyborg_reproduction.write_declaration(source_root, output)
            result = {
                "disposition": "declared",
                "frozen_revision": cyborg_reproduction.FROZEN_SELECTION.frozen_revision,
                "inventory": _INVENTORY_NAME,
            }
        elif args.phase == "run":
            cyborg_reproduction.run_full_study(source_root, output)
            verified = cyborg_reproduction.verify_bundle(output)
            result = {"disposition": "completed", "inventory": _INVENTORY_NAME, **verified}
        else:
            cyborg_reproduction.recompute_bundle(bundle, output)
            result = {
                "disposition": "verified",
                "inventory": _INVENTORY_NAME,
            }
    except FileExistsError:
        raise _CommandFailure(
            EXIT_OUTPUT,
            _OUTPUT_UNAVAILABLE_CODE,
            _OUTPUT_UNAVAILABLE_MESSAGE,
        ) from None
    except ValueError:
        raise _CommandFailure(
            EXIT_VALIDATION,
            "researcher.validation.reproduction-invalid",
            "reproduction evidence is invalid",
        ) from None
    except Exception:
        raise _CommandFailure(
            EXIT_RUNTIME,
            _RUNTIME_FAILURE_CODE,
            "reproduction execution failed",
        ) from None
    print(json.dumps(result, sort_keys=True))
    return 0


def _run_command(adapter: _BackendAdapter, args: argparse.Namespace) -> int:
    """Dispatch the ``run`` command through its conformance or native path."""

    if args.mode == "conformance":
        if not _conformance_controls_absent(args):
            raise _CommandFailure(
                EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE
            )
        return _run_conformance(adapter, args)
    if args.suite != "pr":
        raise _CommandFailure(EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE)
    return _run_native(adapter, args)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the closed command and suppress unexpected exception details."""

    try:
        args = _parser().parse_args(argv)
        result = _dispatch(args)
    except _UsageFailure:
        _emit_error("researcher.usage.invalid", "invalid command line")
        result = EXIT_USAGE
    except _CommandFailure as error:
        _emit_error(error.code, error.message)
        result = error.exit_code
    except Exception:
        _emit_error("researcher.internal.failure", "internal command failure")
        result = EXIT_INTERNAL
    return result


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXIT_ARTIFACT",
    "EXIT_INTERNAL",
    "EXIT_OUTPUT",
    "EXIT_RUNTIME",
    "EXIT_USAGE",
    "EXIT_VALIDATION",
    "cyborg_inspection_payload",
    "main",
]
