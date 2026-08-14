"""CybORG composition over published RAES conformance and evidence surfaces."""

from __future__ import annotations

import argparse
import json
import textwrap
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from typing import cast

from raes import parse_sdl  # type: ignore[import-untyped]
from raes_backend_protocols.capabilities import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
)
from raes_conformance.conformance.report import (  # type: ignore[import-untyped]
    backend_conformance_report_payload,
)
from raes_conformance.realization import ExecutionBasis  # type: ignore[import-untyped]
from raes_contracts.contracts.time_model import (  # type: ignore[import-untyped]
    TimeModelDeclarationModel,
)
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    Diagnostic,
    Severity,
    diagnostic_model,
    diagnostic_payload,
)
from raes_contracts.participant_action_arguments import (  # type: ignore[import-untyped]
    ParticipantValidatedActionSelection,
)
from raes_contracts.participant_binding import (  # type: ignore[import-untyped]
    ParticipantActionAdmissionRequest,
)
from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeResetRequest,
    ParticipantEpisodeTerminateRequest,
)
from raes_contracts.planning import (  # type: ignore[import-untyped]
    EvaluationPlan,
    OrchestrationPlan,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
)
from raes_operations.realization_conformance import (  # type: ignore[import-untyped]
    write_backend_conformance_report,
)
from raes_runtime.manager import RuntimeManager  # type: ignore[import-untyped]
from raes_runtime.registry import RuntimeTarget  # type: ignore[import-untyped]
from raes_runtime.registry_probes import (  # type: ignore[import-untyped]
    sample_participant_action_admission_request,
)

from raes_adapters._conformance_support import manifest_capability_gaps
from raes_adapters.base import run_conformance_probe

from ._diagnostics import diagnostic_address
from .driver import (
    _NativeEvaluationContext,
    _NativeEvaluationTurn,
    _NativeParticipantOccurrence,
    _NativeRewardComponent,
    _NativeTurnResult,
)
from .evaluator import CyborgEvaluator
from .manifest import create_cyborg_manifest
from .orchestrator import CyborgOrchestrator
from .participant_runtime import CyborgParticipantRuntime
from .qualification import load_qualification
from .runtime_plans import (
    cage2_evaluation_plan,
    cage2_orchestration_plan,
    cage2_time_declaration,
)
from .scenario import CyborgScenarioDescriptor
from .source_ledger import (
    CAGE2_SOURCE_26CE1C1,
    EvidenceSelection,
    load_loss_disclosures,
    validate_all,
)
from .target import create_cyborg_target

PR_CONFORMANCE_SEEDS = (3,)
FULL_CONFORMANCE_SEEDS = (3, 153)

_BLUE = "participant.behavior.blue"
_GREEN = "participant.behavior.green"
_RED = "participant.behavior.red"
_SLEEP = "participant.action-contract.sleep"
_CLOCK = "time.clock.cage2"
_WORKFLOW = "orchestration.workflow.cage2-probe"


class _HermeticProbeDriver(object):
    """Deterministic, dependency-free driver used only for PR conformance."""

    def __init__(self) -> None:
        self.descriptors: list[CyborgScenarioDescriptor] = []
        self.handles: list[object] = []
        self.cleanup_calls = 0
        self.selections: list[ParticipantValidatedActionSelection] = []

    def construct(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
    ) -> object:
        del seed
        handle = _HostileNativeHandle()
        self.descriptors.append(descriptor)
        self.handles.append(handle)
        return handle

    def construct_execution(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
        red_variant: str,
    ) -> object:
        del red_variant
        return self.construct(descriptor, seed=seed)

    def reset(self, handle: object, *, seed: int | None) -> bool:
        del seed
        return handle in self.handles

    def step(
        self,
        handle: object,
        selection: ParticipantValidatedActionSelection,
    ) -> _NativeTurnResult:
        if handle not in self.handles:
            raise ValueError("The hermetic CybORG probe handle is unavailable.")
        self.selections.append(selection)
        return _NativeTurnResult(
            external_action_succeeded=True,
            source_terminal=False,
            occurrences=(
                _NativeParticipantOccurrence(_BLUE, selection.action_contract_address),
                _NativeParticipantOccurrence(_GREEN, "participant.action-contract.green-port-scan"),
                _NativeParticipantOccurrence(_RED, _SLEEP),
            ),
        )

    def project_evaluation(
        self,
        handle: object,
        context: _NativeEvaluationContext,
    ) -> _NativeEvaluationTurn:
        if handle not in self.handles:
            raise ValueError("The hermetic CybORG probe handle is unavailable.")
        return _NativeEvaluationTurn(
            run_id=context.run_id,
            episode_id=context.episode_id,
            action_instance_id=context.action_instance_id,
            logical_step=context.logical_step,
            terminal_cause=context.terminal_cause,
            rewards=((_BLUE, -0.1), (_GREEN, 0.0), (_RED, 0.1)),
            components=(
                _NativeRewardComponent(
                    _BLUE,
                    "provision.node.user-host",
                    "confidentiality",
                    -0.1,
                    "source-ledger:reward-components",
                ),
            ),
        )

    def cleanup(self, handle: object) -> bool:
        self.cleanup_calls += 1
        if handle in self.handles:
            self.handles.remove(handle)
        return True


class _HostileNativeHandle(object):
    """Fail if a portable probe tries to render the injected native handle."""

    def __str__(self) -> str:
        raise AssertionError("native-secret-sentinel was stringified")

    def __repr__(self) -> str:
        raise AssertionError("native-secret-sentinel was represented")


def run_cyborg_conformance(*, seed: int = 3) -> BackendConformanceReport:
    """Run the published RAES target conformance suite for one hermetic seed."""

    if seed not in FULL_CONFORMANCE_SEEDS:
        raise ValueError("CybORG conformance seed is not in a published suite tier.")
    driver = _HermeticProbeDriver()
    target = create_cyborg_target(driver=driver, seed=seed)
    return run_conformance_probe(
        target,
        execution_basis=ExecutionBasis.HERMETIC_LIVE,
        native_conformance=False,
    )


def cyborg_backend_conformance_payload(
    report: BackendConformanceReport,
) -> dict[str, object]:
    """Serialize the canonical report through the published RAES projector."""

    return cast(dict[str, object], backend_conformance_report_payload(report))


def cyborg_source_diagnostics(
    selection: EvidenceSelection = CAGE2_SOURCE_26CE1C1,
) -> tuple[Diagnostic, ...]:
    """Validate selected source evidence and return published RAES diagnostics."""

    problems = validate_all(selection)
    diagnostics = [
        Diagnostic(
            code="cyborg.source-ledger.validation-failed",
            domain="conformance",
            address=diagnostic_address(f"cyborg.source-ledger.{problem.row_id}.{problem.field}"),
            message="The selected CAGE-2 source-ledger evidence failed validation.",
        )
        for problem in problems
    ]
    if not diagnostics:
        diagnostics.append(
            Diagnostic(
                code="cyborg.source-ledger.validated",
                domain="conformance",
                address="/cyborg/source-ledger",
                message="The selected CAGE-2 source-ledger evidence validated.",
                severity=Severity.INFO,
            )
        )
    diagnostics.extend(
        Diagnostic(
            code="cyborg.source-ledger.declared-weakness",
            domain="conformance",
            address=f"/cyborg/source-ledger/weaknesses/{index}",
            message="A declared CAGE-2 source weakness remains in force.",
            severity=Severity.WARNING,
        )
        for index, _weakness in enumerate(cyborg_declared_weaknesses(selection))
    )
    for diagnostic in diagnostics:
        diagnostic_model(diagnostic)
    return tuple(diagnostics)


def cyborg_adapter_diagnostics(*, seed: int = 3) -> tuple[Diagnostic, ...]:
    """Execute bounded adapter-local probes and report through RAES diagnostics."""

    if seed not in FULL_CONFORMANCE_SEEDS:
        raise ValueError("CybORG conformance seed is not in a published suite tier.")
    driver = _HermeticProbeDriver()
    target = create_cyborg_target(driver=driver, seed=seed)
    plan = RuntimeManager(target).plan(
        parse_sdl(
            textwrap.dedent(
                """
                name: cyborg-adapter-probe
                nodes:
                  user-net: {type: switch}
                  user-host: {type: vm, os: linux}
                infrastructure:
                  user-net:
                    properties: {cidr: 10.20.0.0/24, gateway: 10.20.0.1}
                  user-host: {count: 1, links: [user-net]}
                """
            )
        )
    )
    applied = target.provisioner.apply(plan.provisioning, RuntimeSnapshot())
    manifest = target.manifest
    checks = _initial_adapter_checks(target, seed)
    checks["scenario2-realization"] = _scenario2_realization_probe(seed)
    with suppress(Exception):
        runtime_checks = _execute_runtime_probes(target, driver, applied)
        runtime_checks["seed-clock"] = bool(
            checks["seed-clock"] and runtime_checks.get("seed-clock", False)
        )
        checks.update(runtime_checks)
    cleaned = target.provisioner.cleanup()
    checks["cleanup"] = applied.success and cleaned and not driver.handles
    checks["portable-output"] = _portable_probe_output_is_safe(manifest, applied)
    diagnostics = tuple(_probe_diagnostic(name, passed) for name, passed in checks.items())
    for diagnostic in diagnostics:
        diagnostic_model(diagnostic)
    return diagnostics


def _scenario2_realization_probe(seed: int) -> bool:
    """Prove the packaged full scenario reaches the dependency-free driver seam."""

    driver = _HermeticProbeDriver()
    try:
        source = (
            files(__package__)
            .joinpath("scenario", "cage2-scenario2.sdl.yaml")
            .read_text(encoding="utf-8")
        )
        scenario = parse_sdl(source)
        target = create_cyborg_target(driver=driver, scenario=scenario, seed=seed)
        manager = RuntimeManager(target)
        plan = manager.plan(scenario)
        applied = manager.apply(plan)
        descriptor = driver.descriptors[-1] if driver.descriptors else None
        resource_types = (
            {resource.resource_type for resource in descriptor.resources}
            if descriptor is not None
            else set()
        )
        realized = bool(
            not plan.diagnostics
            and applied.success
            and descriptor is not None
            and len(descriptor.resources) == 38
            and resource_types == {"account-placement", "network", "node"}
        )
        destroyed = RuntimeManager(target, initial_snapshot=applied.snapshot).destroy()
        return realized and destroyed.success and not driver.handles
    except Exception:
        with suppress(Exception):
            target.provisioner.cleanup()
        return False


def _initial_adapter_checks(target: RuntimeTarget, seed: int) -> dict[str, bool]:
    """Return static source-pin and clock-claim dispositions."""

    qualification = load_qualification()
    manifest = target.manifest
    return {
        "pins": (
            qualification.get("profile_id") == CAGE2_SOURCE_26CE1C1.qualification_profile_id
            and manifest.constraints.get("profile") == CAGE2_SOURCE_26CE1C1.qualification_profile_id
        ),
        "seed-clock": (
            manifest.time is not None
            and target.time_runtime is not None
            and manifest.realization_envelope is not None
            and f"seed={seed}" in manifest.realization_envelope.configuration.network_policy
        ),
        "lifecycle": False,
        "action-observation": False,
        "reward-evaluation": False,
    }


def _execute_runtime_probes(
    target: RuntimeTarget,
    driver: _HermeticProbeDriver,
    applied: ApplyResult,
) -> dict[str, bool]:
    """Execute the bounded lifecycle, action, observation, and evaluation flow."""

    if not applied.success or any(
        component is None
        for component in (
            target.time_runtime,
            target.orchestrator,
            target.participant_runtime,
            target.evaluator,
        )
    ):
        return {}
    time_runtime = target.time_runtime
    orchestrator = cast(CyborgOrchestrator, target.orchestrator)
    participant = cast(CyborgParticipantRuntime, target.participant_runtime)
    evaluator = cast(CyborgEvaluator, target.evaluator)
    timed = time_runtime.initialize(_probe_time_declaration(), applied.snapshot)
    started = orchestrator.start(_probe_orchestration_plan(), timed.snapshot)
    initialized_snapshot, initialized = _initialize_probe_participants(
        participant, started.snapshot
    )
    action = participant.admit_action(_probe_action_request(), initialized_snapshot)
    observations = tuple(participant.observations(address) for address in (_BLUE, _GREEN, _RED))
    evaluated = evaluator.start(_probe_evaluation_plan(), action.snapshot)
    evaluation = evaluator.results().get("evaluation.objective.defend", {})
    reset = participant.reset_many(_probe_reset_requests(), evaluated.snapshot)
    terminated_snapshot, terminated = _terminate_probe_participants(participant, reset.snapshot)
    stopped = orchestrator.stop(terminated_snapshot)
    manifest = target.manifest
    return {
        "seed-clock": _probe_clock_advanced(action.snapshot),
        "lifecycle": _probe_lifecycle_succeeded(
            timed.success,
            started.success,
            initialized,
            reset.success,
            terminated,
            stopped.success,
        ),
        "action-observation": _probe_action_observation_succeeded(
            action.success,
            driver,
            observations,
            manifest,
        ),
        "reward-evaluation": _probe_evaluation_succeeded(
            evaluated.success,
            evaluation,
            evaluator,
            manifest,
        ),
    }


def _probe_clock_advanced(snapshot: RuntimeSnapshot) -> bool:
    """Return whether the runtime advanced the declared logical clock once."""

    return bool(
        snapshot.time_model_state is not None
        and snapshot.time_model_state.clocks[_CLOCK].coordinate.tick == 1
    )


def _probe_lifecycle_succeeded(*dispositions: bool) -> bool:
    """Return whether every lifecycle transition succeeded."""

    return all(dispositions)


def _probe_action_observation_succeeded(
    action_succeeded: bool,
    driver: _HermeticProbeDriver,
    observations: Sequence[object],
    manifest: BackendManifest,
) -> bool:
    """Return whether action admission produced all portable observations."""

    return bool(
        action_succeeded
        and len(driver.selections) == 1
        and all(observations)
        and "participant-observation-envelope-v1" in manifest.supported_contract_versions
    )


def _probe_evaluation_succeeded(
    evaluation_succeeded: bool,
    evaluation: Mapping[str, object],
    evaluator: CyborgEvaluator,
    manifest: BackendManifest,
) -> bool:
    """Return whether evaluation produced ready portable evidence and measures."""

    return bool(
        evaluation_succeeded
        and evaluation.get("status") == "ready"
        and evaluation.get("passed") is True
        and evaluator.evidence_records()
        and evaluator.derived_measures()
        and "evaluation-result-envelope-v1" in manifest.supported_contract_versions
    )


def _initialize_probe_participants(
    participant: CyborgParticipantRuntime,
    snapshot: RuntimeSnapshot,
) -> tuple[RuntimeSnapshot, bool]:
    """Initialize every aggregate participant and return the final snapshot."""

    dispositions: list[bool] = []
    for address in (_BLUE, _GREEN, _RED):
        result = participant.initialize(
            ParticipantEpisodeInitializeRequest(
                participant_address=address,
                episode_id=f"{address}-episode-1",
            ),
            snapshot,
        )
        dispositions.append(result.success)
        snapshot = result.snapshot
    return snapshot, all(dispositions)


def _probe_reset_requests() -> tuple[ParticipantEpisodeResetRequest, ...]:
    """Return one complete aggregate reset request set."""

    return tuple(
        ParticipantEpisodeResetRequest(
            participant_address=address,
            episode_id=f"{address}-episode-2",
        )
        for address in (_BLUE, _GREEN, _RED)
    )


def _terminate_probe_participants(
    participant: CyborgParticipantRuntime,
    snapshot: RuntimeSnapshot,
) -> tuple[RuntimeSnapshot, bool]:
    """Terminate every aggregate participant and retain every disposition."""

    dispositions: list[bool] = []
    for address in (_BLUE, _GREEN, _RED):
        result = participant.terminate(
            ParticipantEpisodeTerminateRequest(participant_address=address),
            snapshot,
        )
        dispositions.append(result.success)
        snapshot = result.snapshot
    return snapshot, all(dispositions)


def _probe_time_declaration() -> TimeModelDeclarationModel:
    """Return the RAES-owned logical clock used by the runtime probe."""

    return cage2_time_declaration()


def _probe_orchestration_plan() -> OrchestrationPlan:
    """Return the bounded one-turn workflow used by the runtime probe."""

    return cage2_orchestration_plan(
        workflow=_WORKFLOW,
        name="cage2-probe",
        max_steps=1,
        red_variant="sleep",
    )


def _probe_action_request() -> ParticipantActionAdmissionRequest:
    """Return one published sleep-action admission request."""

    sample = sample_participant_action_admission_request()
    selection = sample.implementation_selection.model_copy(update={"participant_address": _BLUE})
    validated = ParticipantValidatedActionSelection(
        action_contract_address=_SLEEP,
        argument_shape_ref="participant.action-argument-shape.cage2",
        proposal_ref="proposal:cyborg-conformance-action-1",
        normalized_arguments=(),
    )
    return replace(
        sample,
        participant_address=_BLUE,
        action_contract_address=_SLEEP,
        observation_boundary_address="participant.observation-boundary.blue",
        action_instance_id="cyborg-conformance-action-1",
        implementation_selection=selection,
        validated_selection=validated,
        requires_terminal_outcome=True,
    )


def _probe_evaluation_plan() -> EvaluationPlan:
    """Return a bounded objective plan over projected confidentiality evidence."""

    return cage2_evaluation_plan(include_execution_contract=False)


def _portable_probe_output_is_safe(manifest: BackendManifest, applied: ApplyResult) -> bool:
    """Serialize only allowlisted portable projections from the probe result."""

    try:
        snapshot = applied.snapshot
        payload = {
            "manifest": backend_manifest_payload(manifest),
            "changed_addresses": list(applied.changed_addresses),
            "diagnostics": [diagnostic_payload(item) for item in applied.diagnostics],
            "entries": {
                address: {
                    "domain": entry.domain.value,
                    "resource_type": entry.resource_type,
                    "payload": dict(entry.payload),
                    "status": entry.status,
                }
                for address, entry in snapshot.entries.items()
            },
        }
        rendered = json.dumps(payload, sort_keys=True)
    except (AttributeError, TypeError, ValueError):
        return False
    forbidden = ("native-secret-sentinel", "traceback", "__cause__", "argv", "environment")
    lowered = rendered.lower()
    return all(item not in lowered for item in forbidden)


def _probe_diagnostic(name: str, passed: bool) -> Diagnostic:
    """Return one stable local-probe disposition through the RAES envelope."""

    disposition = "validated" if passed else "failed"
    return Diagnostic(
        code=f"cyborg.probe.{name}.{disposition}",
        domain="conformance",
        address=f"/cyborg/probes/{name}",
        message=(
            f"The CybORG {name} probe validated." if passed else f"The CybORG {name} probe failed."
        ),
        severity=Severity.INFO if passed else Severity.ERROR,
    )


def cyborg_declared_weaknesses(
    selection: EvidenceSelection = CAGE2_SOURCE_26CE1C1,
) -> tuple[str, ...]:
    """Return stable references to qualification limitations, defects, and losses."""

    qualification = load_qualification()
    admission = qualification.get("admission")
    limitations = admission.get("limitations", []) if isinstance(admission, dict) else []
    defects = qualification.get("known_defects", [])
    refs = [f"limitation:{value}" for value in limitations if isinstance(value, str)]
    refs.extend(
        f"defect:{item['id']}"
        for item in defects
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    refs.extend(
        f"loss:{loss_id}:{','.join(sorted(tiers))}"
        for loss_id, tiers in load_loss_disclosures(selection).items()
    )
    return tuple(sorted(refs))


def cyborg_manifest_capability_gaps(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Return every affirmative manifest leaf as unresolved inventory."""

    resolved = (
        payload
        if payload is not None
        else cast(
            Mapping[str, object],
            backend_manifest_payload(manifest or create_cyborg_manifest()),
        )
    )
    return manifest_capability_gaps(resolved)


def cyborg_conformance_reproduction_commands(
    suite: str,
) -> tuple[tuple[str, ...], ...]:
    """Return fixed, shell-free repository-relative reproduction argv."""

    if suite not in {"pr", "full"}:
        raise ValueError("CybORG conformance suite must be 'pr' or 'full'.")
    return (
        (
            "python",
            "-m",
            "raes_adapters.cyborg.conformance",
            "--suite",
            suite,
            "--output-dir",
            "artifacts/cyborg-conformance",
        ),
    )


def run_cyborg_conformance_suite(
    *,
    suite: str,
    output_dir: Path,
) -> dict[str, object]:
    """Run one deterministic tier and return a machine-readable evidence index."""

    seeds = PR_CONFORMANCE_SEEDS if suite == "pr" else FULL_CONFORMANCE_SEEDS
    if suite not in {"pr", "full"}:
        raise ValueError("CybORG conformance suite must be 'pr' or 'full'.")
    invocation_root = Path.cwd().resolve()
    output_dir = output_dir.resolve()
    if output_dir == invocation_root or not output_dir.is_relative_to(invocation_root):
        raise ValueError("CybORG conformance output must be beneath the invocation directory.")
    reports: list[dict[str, object]] = []
    adapter_probe_runs: list[dict[str, object]] = []
    diagnostics = cyborg_source_diagnostics()
    for seed in seeds:
        adapter_diagnostics = cyborg_adapter_diagnostics(seed=seed)
        if any(not item.code.endswith(".validated") for item in adapter_diagnostics):
            raise RuntimeError("CybORG adapter-local conformance probes failed.")
        adapter_probe_runs.append(
            {
                "seed": seed,
                "diagnostics": [diagnostic_payload(item) for item in adapter_diagnostics],
            }
        )
        report = run_cyborg_conformance(seed=seed)
        payload = cyborg_backend_conformance_payload(report)
        if not _report_has_only_passing_or_published_unsupported_cases(report):
            raise RuntimeError("CybORG published conformance cases failed.")
        capability_gaps = cyborg_manifest_capability_gaps()
        report_path = write_backend_conformance_report(
            payload,
            output_dir=output_dir,
            run_id=f"cyborg-{suite}-seed-{seed}",
        )
        reports.append(
            {
                "seed": seed,
                "execution_basis": ExecutionBasis.HERMETIC_LIVE.value,
                "native_conformance": report.native_conformance,
                "report_path": report_path.relative_to(output_dir).as_posix(),
                "capability_gaps": list(capability_gaps),
            }
        )
    index: dict[str, object] = {
        "suite": suite,
        "seeds": list(seeds),
        "reports": reports,
        "diagnostics": [diagnostic_payload(item) for item in diagnostics],
        "adapter_diagnostics": adapter_probe_runs,
        "declared_weaknesses": list(cyborg_declared_weaknesses()),
        "reproduction_commands": [
            list(command) for command in cyborg_conformance_reproduction_commands(suite)
        ],
        "explicit_non_claims": [
            "Finite conformance does not establish deterministic replay.",
            "Finite conformance does not establish scientific equivalence.",
            "Hermetic execution is not native-live conformance.",
        ],
    }
    index = cast(dict[str, object], json.loads(json.dumps(index, sort_keys=True)))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.json").write_text(
        json.dumps(index, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index


def _report_has_only_passing_or_published_unsupported_cases(
    report: BackendConformanceReport,
) -> bool:
    """Admit only passing cases or the runner's bounded no-witness disposition."""

    unsupported = tuple(case for case in report.cases if not case.passed)
    if len(unsupported) != 1:
        return False
    case = unsupported[0]
    return (
        case.name == "realization-envelope-constructive"
        and case.contract_name == "realization-envelope-v1"
        and case.outcome == "unsupported"
        and {diagnostic.code for diagnostic in case.diagnostics}
        == {
            "realization-envelope.positive-probe.no-witness",
            "realization-envelope.negative-probe.no-witness",
        }
        and all(item.passed for item in report.cases if item is not case)
    )


def _cli_output_directory(value: str) -> Path:
    """Resolve a relative artifact directory beneath the invocation directory."""

    requested = Path(value)
    if requested.is_absolute() or not requested.parts or ".." in requested.parts:
        raise argparse.ArgumentTypeError("output directory must be a relative child path")
    root = Path.cwd().resolve()
    resolved = (root / requested).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "output directory must remain beneath the invocation directory"
        ) from error
    if not relative.parts:
        raise argparse.ArgumentTypeError("output directory must not be the invocation directory")
    return resolved


def _parser() -> argparse.ArgumentParser:
    """Build the closed command-line parser for deterministic suite execution."""

    parser = argparse.ArgumentParser(description="Run CybORG conformance evidence.")
    parser.add_argument("--suite", choices=("pr", "full"), default="pr")
    parser.add_argument("--output-dir", type=_cli_output_directory, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected suite and emit its machine-readable evidence index."""

    args = _parser().parse_args(argv)
    result = run_cyborg_conformance_suite(suite=args.suite, output_dir=args.output_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FULL_CONFORMANCE_SEEDS",
    "PR_CONFORMANCE_SEEDS",
    "cyborg_adapter_diagnostics",
    "cyborg_backend_conformance_payload",
    "cyborg_conformance_reproduction_commands",
    "cyborg_declared_weaknesses",
    "cyborg_manifest_capability_gaps",
    "cyborg_source_diagnostics",
    "run_cyborg_conformance",
    "run_cyborg_conformance_suite",
]
