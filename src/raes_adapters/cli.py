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

EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_OUTPUT = 4
EXIT_RUNTIME = 5
EXIT_ARTIFACT = 6
EXIT_INTERNAL = 70


class _UsageFailure(Exception):
    """Internal parser control flow with no user-controlled payload."""


class _OutputFailure(Exception):
    """Internal output-reservation control flow."""


class _ValidationFailure(Exception):
    """Internal pre-execution validation control flow."""


@dataclass(frozen=True)
class _AdmittedRun:
    pack_digest: str
    scenario: object
    scenario_digest: str
    spec: ExperimentSpecModel
    task: ExperimentTaskModel
    blue_manifest: ParticipantImplementationManifestModel
    blue_selection: ParticipantImplementationSelectionModel
    blue_configuration: ParticipantConfigurationResultModel
    seeds: tuple[int, ...]


class _Parser(argparse.ArgumentParser):
    """Argparse parser that returns the documented usage status."""

    def error(self, message: str) -> NoReturn:
        del message
        raise _UsageFailure


def _relative_output(value: str) -> Path:
    requested = Path(value)
    if requested.is_absolute() or not requested.parts or ".." in requested.parts:
        raise argparse.ArgumentTypeError("output must be an invocation-relative child path")
    return requested


def _parser() -> _Parser:
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
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
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


def _admit_native_run(args: argparse.Namespace) -> _AdmittedRun:
    try:
        pack_contracts = import_module("raes_env_packs")
    except ImportError as error:
        raise _ValidationFailure from error

    if not _native_args_complete(args):
        raise _ValidationFailure
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
    intended = spec.intended_scenario_ref
    plan = spec.run_plan
    declared_seeds = tuple(
        item.value
        for item in plan.stochastic_controls
        if item.role == "seed" and type(item.value) is int
    )
    selections = plan.red_variant_selections
    if (
        scenario_digest != args.scenario_digest
        or intended is None
        or intended.ref_digest != args.scenario_digest
        or intended.ref_path != args.scenario.as_posix()
        or task.scenario_ref.ref_digest != args.scenario_digest
        or task.scenario_ref.ref_path != args.scenario.as_posix()
        or spec.task_ref.ref_id != task.task_id
        or plan.episode_control.max_steps != args.trial_length
        or args.red_variant not in selections
        or not artifact_bindings_admitted
        or args.blue_implementation != blue_manifest.identity.name
        or blue_selection.implementation_identity != blue_manifest.identity
        or blue_configuration.configuration.implementation_identity != blue_manifest.identity
        or blue_selection.manifest_ref != args.blue_manifest.as_posix()
        or blue_configuration.manifest_ref != args.blue_manifest.as_posix()
        or blue_selection.configuration_ref != args.blue_configuration.as_posix()
        or blue_selection.manifest_digest != canonical_contract_digest(blue_manifest)
        or "cyborg-cage2" not in blue_manifest.compatibility.backends
        or blue_selection.selected_decision_surface_mode
        not in blue_manifest.capabilities.supported_decision_surface_modes
        or not set(blue_selection.participant_contract_versions)
        <= set(blue_manifest.capabilities.supported_participant_contracts)
        or not set(blue_selection.exposure_policy.exposure_policy_kinds)
        <= set(blue_manifest.capabilities.exposure_policy_kinds)
        or not 1 <= len(args.run_id) <= 64
        or not args.run_id.replace("-", "").isalnum()
        or any(type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF for seed in args.seed)
    ):
        raise _ValidationFailure
    seeds = tuple(args.seed)
    if args.mode == "smoke":
        if len(seeds) != 1 or seeds[0] not in declared_seeds:
            raise _ValidationFailure
    elif seeds != declared_seeds or plan.target_run_count != len(seeds):
        raise _ValidationFailure
    try:
        from raes_runtime.manager import RuntimeManager  # type: ignore[import-untyped]

        planned = RuntimeManager(create_cyborg_target(seed=seeds[0])).plan(scenario)
    except Exception as error:
        raise _ValidationFailure from error
    if any(item.is_error for item in planned.diagnostics):
        raise _ValidationFailure
    try:
        from raes_adapters.cyborg.researcher import RunControls

        RunControls(
            run_id=args.run_id,
            seed=seeds[0],
            max_steps=args.trial_length,
            red_variant=args.red_variant,
            blue_manifest=blue_manifest,
            blue_selection=blue_selection,
            blue_configuration=blue_configuration,
        )
    except Exception as error:
        raise _ValidationFailure from error
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
    return "application/json" if path.suffix == ".json" else "application/octet-stream"


def _seal_inventory(output: Path) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        if path.name == "inventory.json":
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
    atomic_write_json_artifact(output / "inventory.json", inventory)
    return inventory


def _emit_error(code: str, message: str) -> None:
    print(f"{code}: {message}", file=sys.stderr)


def _retain_failure(output: Path, code: str, message: str) -> None:
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
    try:
        output = _reserve_output(args.output)
    except _OutputFailure:
        _emit_error("researcher.output.unavailable", "output root is unavailable")
        return EXIT_OUTPUT
    try:
        result = run_cyborg_conformance_suite(suite=args.suite, output_dir=output)
    except Exception:
        _retain_failure(output, "researcher.runtime.failure", "conformance execution failed")
        _emit_error("researcher.runtime.failure", "conformance execution failed")
        return EXIT_RUNTIME
    try:
        _seal_inventory(output)
    except Exception:
        _emit_error("researcher.artifact.failure", "portable evidence could not be sealed")
        return EXIT_ARTIFACT
    print(
        json.dumps(
            {
                "disposition": "succeeded",
                "evidence_basis": "hermetic-live",
                "inventory": "inventory.json",
                "mode": "conformance",
                "run_count": len(result["reports"]),  # type: ignore[arg-type]
            },
            sort_keys=True,
        )
    )
    return 0


def _installed_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


def _run_native(args: argparse.Namespace) -> int:
    try:
        admitted = _admit_native_run(args)
    except _ValidationFailure:
        _emit_error("researcher.validation.controls-invalid", "run controls were not admitted")
        return EXIT_VALIDATION
    if util.find_spec("CybORG") is None:
        _emit_error(
            "researcher.runtime.native-unavailable", "qualified native source is unavailable"
        )
        return EXIT_RUNTIME
    try:
        verify_selected_cyborg_source()
    except Exception:
        _emit_error(
            "researcher.validation.source-invalid", "qualified native source was not admitted"
        )
        return EXIT_VALIDATION
    try:
        output = _reserve_output(args.output)
    except _OutputFailure:
        _emit_error("researcher.output.unavailable", "output root is unavailable")
        return EXIT_OUTPUT

    from raes_adapters.cyborg.researcher import (
        RunControls,
        archival_collection,
        archival_run,
        blue_implementation_provenance,
        execute_episode,
    )

    try:
        runs = output / "runs"
        os.mkdir(runs, 0o700)
        summaries: list[dict[str, object]] = []
        archival_runs: list[ExperimentRunModel] = []
        for index, seed in enumerate(admitted.seeds, start=1):
            run_id = f"{args.run_id}-{index}"
            run_output = runs / run_id
            os.mkdir(run_output, 0o700)
            try:
                with (
                    open(os.devnull, "w", encoding="utf-8") as sink,  # noqa: PTH123
                    contextlib.redirect_stdout(sink),
                    contextlib.redirect_stderr(sink),
                ):
                    result = execute_episode(
                        admitted.scenario,
                        RunControls(
                            run_id=run_id,
                            seed=seed,
                            max_steps=args.trial_length,
                            red_variant=args.red_variant,
                            blue_manifest=admitted.blue_manifest,
                            blue_selection=admitted.blue_selection,
                            blue_configuration=admitted.blue_configuration,
                        ),
                    )
            except Exception:
                _retain_failure(
                    output, "researcher.runtime.failure", "native execution or cleanup failed"
                )
                _emit_error("researcher.runtime.failure", "native execution or cleanup failed")
                return EXIT_RUNTIME
            atomic_write_json_artifact(
                run_output / "evidence-records.json",
                [item.model_dump(mode="json") for item in result.evidence_records],
            )
            evidence_bytes = (run_output / "evidence-records.json").read_bytes()
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
                blue_implementation_provenance(
                    result.evidence_records[0].run_ref.ref_id,
                    admitted.blue_selection,
                ).model_dump(mode="json"),
            )
            evidence_artifact = ExperimentArtifactRefModel(
                artifact_id=f"portable-evidence-{index}",
                role="observation",
                media_type="application/json",
                uri=f"runs/{run_id}/evidence-records.json",
                checksum={
                    "algorithm": "sha256",
                    "value": hashlib.sha256(evidence_bytes).hexdigest(),
                },
                size_bytes=len(evidence_bytes),
                created_at=result.evidence_records[0].captured_at,
                source="cyborg-cage2 evaluator projection",
                satisfies_refs=[
                    {"ref_kind": "evidence", "ref_id": "source-ledger:reward-components"}
                ],
                sensitivity="redacted",
            )
            run_record = archival_run(
                controls=RunControls(
                    run_id=run_id,
                    seed=seed,
                    max_steps=args.trial_length,
                    red_variant=args.red_variant,
                    blue_manifest=admitted.blue_manifest,
                    blue_selection=admitted.blue_selection,
                    blue_configuration=admitted.blue_configuration,
                ),
                scenario_digest=admitted.scenario_digest,
                task=admitted.task,
                episode=result,
                evidence_artifact=evidence_artifact,
            )
            validate_experiment_run_against_task(admitted.task, run_record)
            atomic_write_json_artifact(run_output / "run.json", run_record.model_dump(mode="json"))
            archival_runs.append(run_record)
            summary = {
                "cleanup_verified": result.cleanup_verified,
                "completed_steps": result.completed_steps,
                "derived_measure_count": len(result.derived_measures),
                "evidence_record_count": len(result.evidence_records),
                "run_id": run_id,
                "seed": seed,
            }
            atomic_write_json_artifact(run_output / "summary.json", summary)
            summaries.append(summary)

        if args.mode == "study":
            study = archival_collection(admitted.task, archival_runs, args.run_id)
            validate_experiment_study_against_tasks_and_runs(study, [admitted.task], archival_runs)
            atomic_write_json_artifact(output / "study.json", study.model_dump(mode="json"))

        manifest = create_cyborg_manifest()
        qualification = load_qualification()
        atomic_write_json_artifact(
            output / "provenance.json",
            {
                "adapter": {
                    "distribution": "raes-adapters",
                    "version": metadata.version("raes-adapters"),
                },
                "backend_manifest": backend_manifest_payload(manifest),
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
        atomic_write_json_artifact(
            output / "summary.json",
            {
                "disposition": "succeeded",
                "mode": args.mode,
                "run_count": len(summaries),
                "runs": summaries,
            },
        )
        _seal_inventory(output)
    except Exception:
        _emit_error("researcher.artifact.failure", "portable evidence could not be sealed")
        return EXIT_ARTIFACT
    print(
        json.dumps(
            {
                "disposition": "succeeded",
                "inventory": "inventory.json",
                "mode": args.mode,
                "run_count": len(admitted.seeds),
            },
            sort_keys=True,
        )
    )
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "inspect":
        print(json.dumps(cyborg_inspection_payload(), sort_keys=True))
        return 0
    if args.command == "validate":
        try:
            admitted = _admit_native_run(args)
        except _ValidationFailure:
            _emit_error("researcher.validation.controls-invalid", "run controls were not admitted")
            return EXIT_VALIDATION
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
    if args.mode == "conformance":
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
        if any(value is not None for value in native_values):
            _emit_error("researcher.validation.controls-invalid", "run controls were not admitted")
            return EXIT_VALIDATION
        return _run_conformance(args)
    if args.suite != "pr":
        _emit_error("researcher.validation.controls-invalid", "run controls were not admitted")
        return EXIT_VALIDATION
    return _run_native(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the closed command and suppress unexpected exception details."""

    try:
        args = _parser().parse_args(argv)
        return _dispatch(args)
    except _UsageFailure:
        _emit_error("researcher.usage.invalid", "invalid command line")
        return EXIT_USAGE
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else EXIT_USAGE
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
