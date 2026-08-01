"""CybORG composition over published RAES conformance and evidence surfaces."""

from __future__ import annotations

import argparse
import json
import textwrap
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import replace
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
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentEpisodeControlModel,
    ExperimentRedVariantSelectionModel,
)
from raes_contracts.contracts.time_model import (  # type: ignore[import-untyped]
    ClockDeclarationModel,
    ExactRatioModel,
    TimeDomainDeclarationModel,
    TimeModelDeclarationModel,
    TimeProgressionPolicyDeclarationModel,
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
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationOp,
    OrchestrationPlan,
    PlannedResource,
    RuntimeDomain,
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

_PUBLISHED_CONFORMANCE_EVIDENCE = "evidence.cyborg.published-conformance.disclosed"
_SOURCE_LEDGER_EVIDENCE = "evidence.cyborg.source-ledger.validated"
_ADAPTER_RUNTIME_EVIDENCE = "evidence.cyborg.adapter-runtime.validated"
_ALL_EVIDENCE = (
    _PUBLISHED_CONFORMANCE_EVIDENCE,
    _SOURCE_LEDGER_EVIDENCE,
    _ADAPTER_RUNTIME_EVIDENCE,
)
_CAPABILITY_PROBE_REQUIREMENTS: Mapping[str, tuple[str, ...]] = {
    "/capabilities/evaluator/preserves_binding_provenance": _ALL_EVIDENCE,
    "/capabilities/evaluator/supported_evidence_channels": _ALL_EVIDENCE,
    "/capabilities/evaluator/supported_predicate_families": _ALL_EVIDENCE,
    "/capabilities/evaluator/supported_quantifiers": _ALL_EVIDENCE,
    "/capabilities/evaluator/supported_sections": _ALL_EVIDENCE,
    "/capabilities/evaluator/supported_time_domains": _ALL_EVIDENCE,
    "/capabilities/evaluator/supported_truth_outcomes": _ALL_EVIDENCE,
    "/capabilities/evaluator/supports_objectives": _ALL_EVIDENCE,
    "/capabilities/evaluator/supports_scoring": _ALL_EVIDENCE,
    "/capabilities/orchestrator/supported_sections": _ALL_EVIDENCE,
    "/capabilities/orchestrator/supported_workflow_features": _ALL_EVIDENCE,
    "/capabilities/orchestrator/supports_workflows": _ALL_EVIDENCE,
    "/capabilities/participant_runtime/supported_behavior_features": _ALL_EVIDENCE,
    "/capabilities/participant_runtime/supported_interaction_features": _ALL_EVIDENCE,
    "/capabilities/participant_runtime/supported_participant_roles": _ALL_EVIDENCE,
    "/capabilities/provisioner/supported_node_types": _ALL_EVIDENCE,
    "/capabilities/provisioner/supported_os_families": _ALL_EVIDENCE,
    "/capabilities/time/max_clocks": _ALL_EVIDENCE,
    "/capabilities/time/max_time_domains": _ALL_EVIDENCE,
    "/capabilities/time/supported_advancement_modes": _ALL_EVIDENCE,
    "/capabilities/time/supported_authority_kinds": _ALL_EVIDENCE,
    "/capabilities/time/supported_constraint_kinds": _ALL_EVIDENCE,
    "/capabilities/time/supported_contract_versions": _ALL_EVIDENCE,
    "/capabilities/time/supported_domain_kinds": _ALL_EVIDENCE,
    "/capabilities/time/supported_mapping_kinds": _ALL_EVIDENCE,
    "/capabilities/time/supported_replay_behaviors": _ALL_EVIDENCE,
    "/capabilities/time/supported_reset_behaviors": _ALL_EVIDENCE,
    "/capabilities/time/supported_synchronization_modes": _ALL_EVIDENCE,
    "/capabilities/time/supports_append_only_history": _ALL_EVIDENCE,
    "/capabilities/time/supports_exact_rational_mappings": _ALL_EVIDENCE,
    "/capabilities/time/supports_pause": _ALL_EVIDENCE,
    "/capabilities/time/supports_run_provenance": _ALL_EVIDENCE,
}
_NON_CAPABILITY_KEYS = frozenset({"constraints", "name"})


class _HermeticProbeDriver(object):  # noqa: UP004 - Sonar's profile requires explicit base
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


class _HostileNativeHandle(object):  # noqa: UP004 - Sonar's profile requires explicit base
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
        "seed-clock": bool(
            action.snapshot.time_model_state is not None
            and action.snapshot.time_model_state.clocks[_CLOCK].coordinate.tick == 1
        ),
        "lifecycle": all(
            (
                timed.success,
                started.success,
                initialized,
                reset.success,
                terminated,
                stopped.success,
            )
        ),
        "action-observation": bool(
            action.success
            and len(driver.selections) == 1
            and all(observations)
            and "participant-observation-envelope-v1" in manifest.supported_contract_versions
        ),
        "reward-evaluation": bool(
            evaluated.success
            and evaluation.get("status") == "ready"
            and evaluation.get("passed") is True
            and evaluator.evidence_records()
            and evaluator.derived_measures()
            and "evaluation-result-envelope-v1" in manifest.supported_contract_versions
        ),
    }


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

    domain = "time.domain.cage2"
    policy = "time.progression.cage2"
    return TimeModelDeclarationModel(
        domains={
            domain: TimeDomainDeclarationModel(
                address=domain,
                kind="logical",
                tick_period_seconds=ExactRatioModel(numerator=1, denominator=1),
                epoch="run_start",
                visibility="runtime_only",
                description="One tick per validated aggregate CybORG turn.",
            )
        },
        clocks={
            _CLOCK: ClockDeclarationModel(
                address=_CLOCK,
                time_domain_address=domain,
                authority_kind="runtime",
                authority_ref="cyborg-cage2-participant-runtime",
                monotonicity="non_decreasing",
                supports_pause=True,
                supports_reset=True,
                supports_jump=False,
                description="RAES-owned CAGE-2 logical step clock.",
            )
        },
        progression_policies={
            policy: TimeProgressionPolicyDeclarationModel(
                address=policy,
                clock_address=_CLOCK,
                advancement_mode="event_driven",
                synchronization_mode="none",
                reset_behavior="new_segment_zero",
                replay_behavior="unsupported",
                description="Only a committed aggregate turn advances this clock.",
            )
        },
    )


def _probe_orchestration_plan() -> OrchestrationPlan:
    """Return the bounded one-turn workflow used by the runtime probe."""

    episode = ExperimentEpisodeControlModel(
        turn_order="scenario-defined",
        termination_rule="admitted-logical-step-limit-or-source-terminal",
        max_steps=1,
        termination_condition_refs=["source-ledger:wrapper-termination-cutoff"],
    )
    variant = ExperimentRedVariantSelectionModel(
        variant_id="sleep",
        agent_ref="participant.implementation.red-sleep",
    )
    payload: dict[str, object] = {
        "name": "cage2-probe",
        "episode_control": episode.model_dump(mode="json"),
        "red_variant_selection": variant.model_dump(mode="json"),
        "result_contract": {
            "state_schema_version": "workflow-step-state/v1",
            "observable_steps": {},
        },
        "execution_contract": {
            "state_schema_version": "workflow-step-state/v1",
            "start_step": "",
            "steps": {},
            "step_types": {},
            "control_edges": {},
            "join_owners": {},
            "call_steps": {},
            "observable_steps": [],
        },
    }
    resource = PlannedResource(
        address=_WORKFLOW,
        domain=RuntimeDomain.ORCHESTRATION,
        resource_type="workflow",
        payload=payload,
    )
    operation = OrchestrationOp(
        action=ChangeAction.CREATE,
        address=_WORKFLOW,
        resource_type="workflow",
        payload=payload,
    )
    return OrchestrationPlan(
        resources={_WORKFLOW: resource},
        operations=[operation],
        startup_order=[_WORKFLOW],
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

    proposition = "evaluation.proposition.compromised"
    assertion = "evaluation.assertion.compromised"
    objective = "evaluation.objective.defend"
    operations = [
        EvaluationOp(
            action=ChangeAction.CREATE,
            address=proposition,
            resource_type="proposition",
            payload={
                "evaluation_basis": "observed_state",
                "subject_addresses": ["provision.node.user-host"],
                "evidence_requirement_refs": ["source-ledger:reward-components"],
                "spec": {
                    "predicate": {
                        "property": "confidentiality",
                        "operator": "lt",
                        "value": 0.0,
                    }
                },
            },
        ),
        EvaluationOp(
            action=ChangeAction.CREATE,
            address=assertion,
            resource_type="assertion",
            payload={"proposition_address": proposition, "polarity": "positive"},
        ),
        EvaluationOp(
            action=ChangeAction.CREATE,
            address=objective,
            resource_type="objective",
            payload={
                "success_addresses": [assertion],
                "spec": {"success": {"mode": "all"}},
                "result_contract": {
                    "resource_type": "objective",
                    "supports_passed": True,
                    "supports_score": False,
                },
            },
        ),
    ]
    return EvaluationPlan(
        operations=operations,
        startup_order=[proposition, assertion, objective],
    )


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


def cyborg_manifest_capability_evidence(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
    conformance_report: BackendConformanceReport | None = None,
    source_diagnostics: Iterable[Diagnostic] = (),
    adapter_diagnostics: Iterable[Diagnostic] = (),
) -> dict[str, tuple[str, ...]]:
    """Return evidence references for declared affirmative manifest surfaces."""

    passed_refs = set(
        _passed_probe_evidence_refs(
            conformance_report,
            source_diagnostics,
            adapter_diagnostics,
        )
    )
    evidence: dict[str, tuple[str, ...]] = {}
    for pointer in _affirmative_capability_pointers(_manifest_payload(manifest, payload)):
        required = _CAPABILITY_PROBE_REQUIREMENTS.get(pointer)
        if required is not None and set(required) <= passed_refs:
            evidence[pointer] = required
    return evidence


def cyborg_manifest_capability_evidence_gaps(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
    conformance_report: BackendConformanceReport | None = None,
    source_diagnostics: Iterable[Diagnostic] = (),
    adapter_diagnostics: Iterable[Diagnostic] = (),
) -> tuple[str, ...]:
    """Return affirmative capability pointers lacking passing evidence."""

    manifest_payload = _manifest_payload(manifest, payload)
    evidence = cyborg_manifest_capability_evidence(
        manifest,
        payload=payload,
        conformance_report=conformance_report,
        source_diagnostics=source_diagnostics,
        adapter_diagnostics=adapter_diagnostics,
    )
    return tuple(
        pointer
        for pointer in _affirmative_capability_pointers(manifest_payload)
        if pointer not in evidence
    )


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
        capability_evidence = cyborg_manifest_capability_evidence(
            conformance_report=report,
            source_diagnostics=diagnostics,
            adapter_diagnostics=adapter_diagnostics,
        )
        if cyborg_manifest_capability_evidence_gaps(
            conformance_report=report,
            source_diagnostics=diagnostics,
            adapter_diagnostics=adapter_diagnostics,
        ):
            raise RuntimeError("CybORG manifest capability evidence is incomplete.")
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
                "capability_evidence": capability_evidence,
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


def _manifest_payload(
    manifest: BackendManifest | None,
    payload: Mapping[str, object] | None,
) -> Mapping[str, object]:
    """Return the provided payload or project the live CybORG manifest."""

    if payload is not None:
        return payload
    return cast(
        Mapping[str, object], backend_manifest_payload(manifest or create_cyborg_manifest())
    )


def _passed_probe_evidence_refs(
    report: BackendConformanceReport | None,
    source_diagnostics: Iterable[Diagnostic],
    adapter_diagnostics: Iterable[Diagnostic],
) -> tuple[str, ...]:
    """Return only evidence references whose owning probes passed."""

    refs: list[str] = []
    if (
        report is not None
        and not report.unsupported_contract_gaps
        and not report.unsupported_capability_gaps
        and _report_has_only_passing_or_published_unsupported_cases(report)
    ):
        refs.append(_PUBLISHED_CONFORMANCE_EVIDENCE)
    models = [diagnostic_model(item) for item in source_diagnostics]
    if models and all(not model.code.endswith("validation-failed") for model in models):
        refs.append(_SOURCE_LEDGER_EVIDENCE)
    adapter_models = [diagnostic_model(item) for item in adapter_diagnostics]
    if adapter_models and all(model.code.endswith(".validated") for model in adapter_models):
        refs.append(_ADAPTER_RUNTIME_EVIDENCE)
    return tuple(refs)


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


def _affirmative_capability_pointers(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Derive JSON Pointers for every affirmative manifest capability."""

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return ()
    pointers: list[str] = []
    for name, value in sorted(capabilities.items(), key=lambda item: str(item[0])):
        if not _is_affirmative_capability_value(value):
            continue
        surface = f"/capabilities/{_escape_pointer_token(str(name))}"
        if isinstance(value, Mapping):
            nested = tuple(
                _iter_affirmative_capability_pointers(cast(Mapping[object, object], value), surface)
            )
            pointers.extend(nested or (surface,))
        else:
            pointers.append(surface)
    return tuple(pointers)


def _iter_affirmative_capability_pointers(
    value: Mapping[object, object],
    base_pointer: str,
) -> Iterable[str]:
    """Yield affirmative leaves below one manifest capability mapping."""

    for key, child in sorted(value.items(), key=lambda item: str(item[0])):
        if key in _NON_CAPABILITY_KEYS or not _is_affirmative_capability_value(child):
            continue
        pointer = f"{base_pointer}/{_escape_pointer_token(str(key))}"
        if isinstance(child, Mapping):
            nested = tuple(
                _iter_affirmative_capability_pointers(cast(Mapping[object, object], child), pointer)
            )
            yield from nested or (pointer,)
        else:
            yield pointer


def _is_affirmative_capability_value(value: object) -> bool:
    """Return whether a manifest capability value makes an affirmative claim."""

    affirmative = False
    if value is True:
        affirmative = True
    elif isinstance(value, str | int | float) and value is not False:
        affirmative = bool(value)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        affirmative = any(_is_affirmative_capability_value(item) for item in value)
    elif isinstance(value, Mapping):
        affirmative = any(
            _is_affirmative_capability_value(child)
            for key, child in value.items()
            if key not in _NON_CAPABILITY_KEYS
        )
    return affirmative


def _escape_pointer_token(token: str) -> str:
    """Escape one JSON Pointer token."""

    return token.replace("~", "~0").replace("/", "~1")


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


# Exercised by the clean-install subprocess.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "FULL_CONFORMANCE_SEEDS",
    "PR_CONFORMANCE_SEEDS",
    "cyborg_adapter_diagnostics",
    "cyborg_backend_conformance_payload",
    "cyborg_conformance_reproduction_commands",
    "cyborg_declared_weaknesses",
    "cyborg_manifest_capability_evidence",
    "cyborg_manifest_capability_evidence_gaps",
    "cyborg_source_diagnostics",
    "run_cyborg_conformance",
    "run_cyborg_conformance_suite",
]
