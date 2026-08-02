"""Installed researcher command over published RAES and adapter owners."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module, metadata, resources, util
from pathlib import Path
from typing import NoReturn

import raes  # type: ignore[import-untyped]
from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_contracts.backend_profiles import (  # type: ignore[import-untyped]
    backend_profiles_root,
    load_backend_profile,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentArtifactRefModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
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

from raes_adapters.cyborg import (
    CAGE2_SOURCE_26CE1C1,
    create_cyborg_manifest,
    create_cyborg_target,
    load_qualification,
    run_cyborg_conformance_suite,
    verify_selected_cyborg_source,
)
from raes_adapters.cyborg import researcher as cyborg_researcher

EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_OUTPUT = 4
EXIT_RUNTIME = 5
EXIT_ARTIFACT = 6
EXIT_INTERNAL = 70
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
class _AdmittedRun(object):  # noqa: UP004
    """Validated authoring inputs required for native execution."""

    pack_digest: str
    scenario: object
    scenario_digest: str
    spec: ExperimentSpecModel
    task: ExperimentTaskModel
    blue_manifest: ParticipantImplementationManifestModel
    blue_selection: ParticipantImplementationSelectionModel
    blue_configuration: ParticipantConfigurationResultModel
    seeds: tuple[int, ...]


@dataclass(frozen=True)
class _CompletedRun(object):  # noqa: UP004
    """Portable records produced by one completed native episode."""

    archival: ExperimentRunModel
    summary: dict[str, object]


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


def _parser() -> _Parser:
    """Build the closed researcher command parser."""

    parser = _Parser(prog="raes-adapters", description="Inspect, validate, and run RAES adapters.")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--backend", choices=("cyborg-cage2",), required=True)

    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--mode", choices=("smoke", "study"), default="study")
    _add_admission_arguments(validate_parser)

    run_parser = commands.add_parser("run")
    run_parser.add_argument("--mode", choices=("smoke", "conformance", "study"), required=True)
    run_parser.add_argument("--suite", choices=("pr", "full"), default="pr")
    run_parser.add_argument("--output", type=_relative_output, required=True)
    _add_admission_arguments(run_parser)
    return parser


def _add_admission_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the complete native-run admission surface to a command."""

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


_EXAMPLE_MEMBERS = (
    "pack.yaml",
    "pack.content-manifest.json",
    "docs/attack-path.md",
    "docs/concepts.md",
    "docs/provenance-ledger.yaml",
    "experiment/cage2-research.spec.exp.json",
    "experiment/cage2-research.task.exp.json",
    "participant/cyborg-blue-sleep-policy.configuration.json",
    "participant/cyborg-blue-sleep-policy.manifest.json",
    "participant/cyborg-blue-sleep-policy.selection.json",
    "sdl/cage2-research.sdl.yaml",
)


@contextmanager
def _pack_root(value: str) -> Iterator[Path]:
    """Resolve a named packaged example or caller-selected pack root."""

    if value != "cage2-research":
        yield Path(value)
        return
    package_root = resources.files("raes_adapters.cyborg") / "examples" / value
    with tempfile.TemporaryDirectory(prefix="raes-adapters-pack-") as scratch:
        staged = Path(scratch) / value
        staged.mkdir(mode=0o700)
        for relative in _EXAMPLE_MEMBERS:
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


def _native_args_complete(args: argparse.Namespace) -> bool:
    """Return whether every native admission argument was supplied."""

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
    return all(value is not None for value in required)


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
    with _pack_root(args.pack) as pack:
        try:
            pack_admitted = pack_contracts.validate_pack(pack).ok
            digest_admitted = pack_contracts.verify_pack_content_digest(pack, args.pack_digest)
        except Exception as error:
            raise _ValidationFailure from error
        if not pack_admitted or not digest_admitted:
            raise _ValidationFailure
        scenario_path = _pack_child(pack, args.scenario)
        experiment_path = _pack_child(pack, args.experiment)
        task_path = _pack_child(pack, args.task)
        blue_manifest_path = _pack_child(pack, args.blue_manifest)
        blue_selection_path = _pack_child(pack, args.blue_selection)
        blue_configuration_path = _pack_child(pack, args.blue_configuration)
        try:
            scenario = raes.parse_sdl_file(scenario_path)
            instantiated = raes.instantiate_scenario(scenario)
            scenario_digest = raes.canonical_instantiated_sdl_digest(instantiated).value
            spec = ExperimentSpecModel.model_validate(_strict_json(experiment_path))
            task = ExperimentTaskModel.model_validate(_strict_json(task_path))
            blue_manifest = ParticipantImplementationManifestModel.model_validate(
                _strict_json(blue_manifest_path)
            )
            blue_selection = ParticipantImplementationSelectionModel.model_validate(
                _strict_json(blue_selection_path)
            )
            blue_configuration = ParticipantConfigurationResultModel.model_validate(
                _strict_json(blue_configuration_path)
            )
            validate_participant_configuration_selection(blue_selection, blue_configuration)
        except Exception as error:
            raise _ValidationFailure from error
        artifact_bindings_admitted = all(
            (
                _artifact_declared_by_spec(
                    spec, args.blue_manifest, blue_manifest_path, "manifest"
                ),
                _artifact_declared_by_spec(
                    spec, args.blue_selection, blue_selection_path, "configuration"
                ),
                _artifact_declared_by_spec(
                    spec, args.blue_configuration, blue_configuration_path, "configuration"
                ),
            )
        )
    return (
        scenario,
        scenario_digest,
        spec,
        task,
        blue_manifest,
        blue_selection,
        blue_configuration,
        artifact_bindings_admitted,
    )


def _experiment_bindings_match(
    args: argparse.Namespace,
    scenario_digest: str,
    spec: ExperimentSpecModel,
    task: ExperimentTaskModel,
    artifact_bindings_admitted: bool,
) -> bool:
    """Verify scenario, task, plan, and artifact bindings."""

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


def _participant_bindings_match(
    args: argparse.Namespace,
    manifest: ParticipantImplementationManifestModel,
    selection: ParticipantImplementationSelectionModel,
    configuration: ParticipantConfigurationResultModel,
) -> bool:
    """Verify participant identity, artifact, and capability bindings."""

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


def _admitted_seeds(args: argparse.Namespace, spec: ExperimentSpecModel) -> tuple[int, ...]:
    """Return seeds only when they exactly satisfy the selected run mode."""

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


def _validate_runtime_plan(scenario: object, seeds: tuple[int, ...]) -> None:
    """Require the published runtime manager to admit the instantiated plan."""

    try:
        from raes_runtime.manager import RuntimeManager  # type: ignore[import-untyped]

        planned = RuntimeManager(create_cyborg_target(seed=seeds[0])).plan(scenario)
    except Exception as error:
        raise _ValidationFailure from error
    if any(item.is_error for item in planned.diagnostics):
        raise _ValidationFailure


def _validate_run_controls(
    args: argparse.Namespace,
    seeds: tuple[int, ...],
    manifest: ParticipantImplementationManifestModel,
    selection: ParticipantImplementationSelectionModel,
    configuration: ParticipantConfigurationResultModel,
) -> None:
    """Construct the final backend-local controls as an admission check."""

    try:
        from raes_adapters.cyborg.researcher import RunControls

        RunControls(
            run_id=args.run_id,
            seed=seeds[0],
            max_steps=args.trial_length,
            red_variant=args.red_variant,
            blue_manifest=manifest,
            blue_selection=selection,
            blue_configuration=configuration,
        )
    except Exception as error:
        raise _ValidationFailure from error


def _admit_native_run(args: argparse.Namespace) -> _AdmittedRun:
    """Admit all authoring, participant, and runtime controls before execution."""

    if not _native_args_complete(args):
        raise _ValidationFailure
    (
        scenario,
        scenario_digest,
        spec,
        task,
        blue_manifest,
        blue_selection,
        blue_configuration,
        artifact_bindings_admitted,
    ) = _load_pack_artifacts(args)
    if not _experiment_bindings_match(
        args, scenario_digest, spec, task, artifact_bindings_admitted
    ) or not _participant_bindings_match(args, blue_manifest, blue_selection, blue_configuration):
        raise _ValidationFailure
    if not 1 <= len(args.run_id) <= 64 or not args.run_id.replace("-", "").isalnum():
        raise _ValidationFailure
    seeds = _admitted_seeds(args, spec)
    _validate_runtime_plan(scenario, seeds)
    _validate_run_controls(args, seeds, blue_manifest, blue_selection, blue_configuration)
    return _AdmittedRun(
        args.pack_digest,
        scenario,
        scenario_digest,
        spec,
        task,
        blue_manifest,
        blue_selection,
        blue_configuration,
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


def _run_conformance(args: argparse.Namespace) -> int:
    """Run the selected hermetic conformance suite and seal its evidence."""

    try:
        output = _reserve_output(args.output)
    except _OutputFailure:
        raise _CommandFailure(
            EXIT_OUTPUT, "researcher.output.unavailable", "output root is unavailable"
        ) from None
    try:
        result = run_cyborg_conformance_suite(suite=args.suite, output_dir=output)
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
                "evidence_basis": "hermetic-live",
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


def _native_environment(args: argparse.Namespace) -> tuple[_AdmittedRun, Path]:
    """Admit native inputs, selected source, and the exclusive output root."""

    try:
        admitted = _admit_native_run(args)
    except _ValidationFailure:
        raise _CommandFailure(
            EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE
        ) from None
    if util.find_spec("CybORG") is None:
        raise _CommandFailure(
            EXIT_RUNTIME,
            "researcher.runtime.native-unavailable",
            "qualified native source is unavailable",
        )
    try:
        verify_selected_cyborg_source()
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
            EXIT_OUTPUT, "researcher.output.unavailable", "output root is unavailable"
        ) from None
    return admitted, output


def _run_controls(
    args: argparse.Namespace, admitted: _AdmittedRun, run_id: str, seed: int
) -> cyborg_researcher.RunControls:
    """Bind one admitted seed and run identity to the selected controls."""

    return cyborg_researcher.RunControls(
        run_id=run_id,
        seed=seed,
        max_steps=args.trial_length,
        red_variant=args.red_variant,
        blue_manifest=admitted.blue_manifest,
        blue_selection=admitted.blue_selection,
        blue_configuration=admitted.blue_configuration,
    )


def _execute_quietly(
    scenario: object, controls: cyborg_researcher.RunControls, output: Path
) -> cyborg_researcher.EpisodeEvidence:
    """Execute one episode while suppressing all native process output."""

    try:
        with (
            Path(os.devnull).open("w", encoding="utf-8") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            return cyborg_researcher.execute_episode(scenario, controls)
    except Exception:
        message = "native execution or cleanup failed"
        _retain_failure(output, _RUNTIME_FAILURE_CODE, message)
        raise _CommandFailure(EXIT_RUNTIME, _RUNTIME_FAILURE_CODE, message) from None


def _write_episode_evidence(
    run_output: Path,
    run_id: str,
    index: int,
    result: cyborg_researcher.EpisodeEvidence,
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
        cyborg_researcher.blue_implementation_provenance(
            result.evidence_records[0].run_ref.ref_id, admitted.blue_selection
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
        source="cyborg-cage2 evaluator projection",
        satisfies_refs=[{"ref_kind": "evidence", "ref_id": "source-ledger:reward-components"}],
        sensitivity="redacted",
    )


def _complete_native_run(
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
    controls = _run_controls(args, admitted, run_id, seed)
    result = _execute_quietly(admitted.scenario, controls, output)
    evidence_artifact = _write_episode_evidence(run_output, run_id, index, result, admitted)
    run_record = cyborg_researcher.archival_run(
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
    args: argparse.Namespace, admitted: _AdmittedRun, output: Path, runs: list[ExperimentRunModel]
) -> None:
    """Write the declared study collection when study mode was selected."""

    if args.mode == "study":
        study = cyborg_researcher.archival_collection(admitted.task, runs, args.run_id)
        validate_experiment_study_against_tasks_and_runs(study, [admitted.task], runs)
        atomic_write_json_artifact(output / "study.json", study.model_dump(mode="json"))


def _write_provenance(args: argparse.Namespace, admitted: _AdmittedRun, output: Path) -> None:
    """Write selected adapter, pack, scenario, source, and control identities."""

    qualification = load_qualification()
    atomic_write_json_artifact(
        output / "provenance.json",
        {
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
        },
    )


def _write_machine_inventory(output: Path) -> None:
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
            "software": {
                "CybORG": _installed_version("CybORG"),
                "raes": _installed_version("raes"),
                "raes-adapters": _installed_version("raes-adapters"),
                "raes-env-packs": _installed_version("raes-env-packs"),
            },
        },
    )


def _write_batch_artifacts(
    args: argparse.Namespace, admitted: _AdmittedRun, output: Path
) -> list[_CompletedRun]:
    """Execute the admitted batch and seal all portable batch artifacts."""

    runs_root = output / "runs"
    os.mkdir(runs_root, 0o700)
    completed = [
        _complete_native_run(args, admitted, runs_root, index, seed, output)
        for index, seed in enumerate(admitted.seeds, start=1)
    ]
    _write_study(args, admitted, output, [item.archival for item in completed])
    _write_provenance(args, admitted, output)
    _write_machine_inventory(output)
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


def _run_native(args: argparse.Namespace) -> int:
    """Execute an admitted native run batch and seal portable evidence."""

    admitted, output = _native_environment(args)
    try:
        completed = _write_batch_artifacts(args, admitted, output)
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


def _validated_admission(args: argparse.Namespace) -> int:
    """Validate native controls and report the admitted run scope."""

    try:
        admitted = _admit_native_run(args)
    except _ValidationFailure:
        raise _CommandFailure(
            EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE
        ) from None
    print(
        json.dumps(
            {
                "disposition": "validated",
                "pack": "admitted",
                "participant": admitted.blue_manifest.identity.name,
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
        args.trial_length,
        args.seed,
        args.run_id,
    )
    return all(value is None for value in native_values)


def _dispatch(args: argparse.Namespace) -> int:
    """Dispatch one parsed command through its closed execution path."""

    if args.command == "inspect":
        print(json.dumps(cyborg_inspection_payload(), sort_keys=True))
        result = 0
    elif args.command == "validate":
        result = _validated_admission(args)
    elif args.mode == "conformance":
        if not _conformance_controls_absent(args):
            raise _CommandFailure(
                EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE
            )
        result = _run_conformance(args)
    else:
        if args.suite != "pr":
            raise _CommandFailure(
                EXIT_VALIDATION, _CONTROLS_INVALID_CODE, _CONTROLS_INVALID_MESSAGE
            )
        result = _run_native(args)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Run the closed command and suppress unexpected exception details."""

    try:
        args = _parser().parse_args(argv)
        return _dispatch(args)
    except _UsageFailure:
        _emit_error("researcher.usage.invalid", "invalid command line")
        return EXIT_USAGE
    except _CommandFailure as error:
        _emit_error(error.code, error.message)
        return error.exit_code
    except Exception:
        _emit_error("researcher.internal.failure", "internal command failure")
        return EXIT_INTERNAL


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
