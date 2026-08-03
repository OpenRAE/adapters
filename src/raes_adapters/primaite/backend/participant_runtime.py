"""PrimAITE participant lifecycle and one-step BLUE action admission.

The BLUE seat is the RL-controlled participant; the scripted RED and
probabilistic GREEN participants act inside the aggregate source turn and are
never separately admitted here. The broad portable BLUE action contracts have no
qualified single-operation native mapping, so ``_model_action`` admits and
models an action and then reports it unrepresentable — a typed terminal result
joined to one driver operation and the participant/episode identity — rather than
letting a contract silently select one of several native ``Discrete(78)``
operations.
"""

from __future__ import annotations

from datetime import UTC, datetime

from raes_backend_protocols.participant_runtime_base import (  # type: ignore[import-untyped]
    BaseParticipantRuntime,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ParticipantActionEffectResultModel,
    ParticipantActionResultModel,
    ParticipantObservationEnvelopeModel,
    ParticipantObservationLossDescriptorModel,
    ParticipantObservationStochasticContextModel,
    SourceStatusModel,
)
from raes_contracts.diagnostics import Diagnostic, Severity  # type: ignore[import-untyped]
from raes_contracts.participant_binding import (  # type: ignore[import-untyped]
    ParticipantActionAdmissionRequest,
    ParticipantNativeActionExecution,
)
from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeResetRequest,
    ParticipantEpisodeRestartRequest,
    ParticipantEpisodeTerminalReason,
    ParticipantEpisodeTerminateRequest,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
)

from ._diagnostics import diagnostic_address
from .driver import DriverResetReport, DriverStep, PrimaiteDriverProtocol

ACTION_EVIDENCE_REF = "evidence.primaite.blue-action"

_BLUE_ACTION_CONTRACTS = frozenset(
    {
        "participant.action-contract.service-control",
        "participant.action-contract.data-integrity-remediation",
        "participant.action-contract.node-lifecycle",
        "participant.action-contract.network-access-control",
        "participant.action-contract.interface-control",
    }
)

_SEED_STREAM_DISPOSITIONS = (
    ("broken_streams", "primaite.seed.broken", "is broken on the qualified light route"),
    ("absent_streams", "primaite.seed.absent", "is absent on the qualified no-rl route"),
    ("unbound_streams", "primaite.seed.unbound", "is uncontrolled for this scenario"),
)


def _now_iso() -> str:
    """Return a portable UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class PrimaiteParticipantRuntime(BaseParticipantRuntime):  # type: ignore[misc]
    """Bind RAES participant lifecycle to the single aggregate source action."""

    def __init__(self, driver: PrimaiteDriverProtocol, *, seed: int | None = None) -> None:
        super().__init__()
        self._driver = driver
        self._seed = seed
        self._observations: dict[str, list[ParticipantObservationEnvelopeModel]] = {}
        self._driver_operation_refs: dict[str, str] = {}

    def initialize(
        self,
        request: ParticipantEpisodeInitializeRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        portable = super().initialize(request, snapshot)
        return self._reset_source_after_portable(request.participant_address, portable, snapshot)

    def reset(
        self,
        request: ParticipantEpisodeResetRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        portable = super().reset(request, snapshot)
        return self._reset_source_after_portable(request.participant_address, portable, snapshot)

    def restart(
        self,
        request: ParticipantEpisodeRestartRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        portable = super().restart(request, snapshot)
        return self._reset_source_after_portable(request.participant_address, portable, snapshot)

    def _reset_source_after_portable(
        self,
        participant_address: str,
        portable: ApplyResult,
        predecessor: RuntimeSnapshot,
    ) -> ApplyResult:
        """Reset the aggregate source after the portable lifecycle succeeds."""

        if not portable.success:
            return portable
        try:
            report = self._driver.reset(self._seed)
        except Exception:
            self._restore_portable_mirror(predecessor)
            return ApplyResult(
                success=False,
                snapshot=predecessor,
                diagnostics=[
                    Diagnostic(
                        code="primaite.participant.reset-failed",
                        domain="participant",
                        address=diagnostic_address(participant_address),
                        message="The selected PrimAITE source could not be reset.",
                    )
                ],
            )
        self._observations[participant_address] = []
        return ApplyResult(
            success=True,
            snapshot=portable.snapshot,
            diagnostics=[
                *portable.diagnostics,
                *self._reset_diagnostics(participant_address, report),
            ],
            changed_addresses=list(portable.changed_addresses),
            details=dict(portable.details),
        )

    def _restore_portable_mirror(self, snapshot: RuntimeSnapshot) -> None:
        """Rebuild the portable episode mirror from the predecessor snapshot."""

        self._results = {
            address: dict(result)
            for address, result in snapshot.participant_episode_results.items()
        }
        self._history = {
            address: [dict(event) for event in events]
            for address, events in snapshot.participant_episode_history.items()
        }

    @classmethod
    def _reset_diagnostics(
        cls,
        participant_address: str,
        report: DriverResetReport,
    ) -> list[Diagnostic]:
        """Emit one diagnostic per distinct stochastic-stream disposition."""

        address = diagnostic_address(participant_address)
        diagnostics = [
            Diagnostic(
                code="primaite.seed.applied",
                domain="participant",
                address=address,
                message=f"Stochastic stream '{stream}' was applied.",
                severity=Severity.INFO,
            )
            for stream in report.applied_streams
        ]
        for attribute, code, clause in _SEED_STREAM_DISPOSITIONS:
            diagnostics.extend(
                Diagnostic(
                    code=code,
                    domain="participant",
                    address=address,
                    message=f"Stochastic stream '{stream}' {clause}.",
                    severity=Severity.WARNING,
                )
                for stream in getattr(report, attribute)
            )
        return diagnostics

    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        """Admit and model one BLUE action, then drive or reject it natively."""

        contract = request.action_contract_address
        if contract not in _BLUE_ACTION_CONTRACTS or request.validated_selection is None:
            return self._rejected_action(
                request,
                snapshot,
                episode_id=episode_id,
                failure_class="unsupported_action",
                code="primaite.participant.unsupported-action",
                message="The PrimAITE backend does not support this participant action contract.",
            )
        return self._execute_admitted_action(
            request, snapshot, episode_id=episode_id, contract=contract
        )

    def _execute_admitted_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
        contract: str,
    ) -> ParticipantNativeActionExecution:
        """Resolve native representability for one admitted BLUE action."""

        try:
            step = self._driver.step(contract)
        except Exception:
            return self._rejected_action(
                request,
                snapshot,
                episode_id=episode_id,
                failure_class="backend_error",
                code="primaite.participant.action-failed",
                message="The selected PrimAITE source failed while executing an action.",
                status="failed",
            )
        self._driver_operation_refs[request.action_instance_id] = step.operation_ref
        if not step.representable:
            return self._rejected_action(
                request,
                snapshot,
                episode_id=episode_id,
                failure_class="unsupported_action",
                code="primaite.participant.unrepresentable-action",
                message=(
                    "No qualified deterministic mapping selects one native operation for this "
                    "broad BLUE action contract, so it is rejected before source mutation."
                ),
            )
        if not step.source_transition:
            return self._rejected_action(
                request,
                snapshot,
                episode_id=episode_id,
                failure_class="target_unavailable",
                code="primaite.participant.action-unavailable",
                message="No source transition was available for the admitted participant action.",
            )
        return self._accepted_action(request, snapshot, episode_id=episode_id, step=step)

    def _accepted_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
        step: DriverStep,
    ) -> ParticipantNativeActionExecution:
        """Model a representable aggregate source transition and its observation."""

        observation = self._observation(request, episode_id=episode_id, step=step)
        self._observations.setdefault(request.participant_address, []).append(observation)
        status = "succeeded" if step.processed else "failed"
        failure_class = None if step.processed else "unknown"
        evidence_refs = (
            [ACTION_EVIDENCE_REF]
            if ACTION_EVIDENCE_REF in request.observation_boundary_evidence_refs
            else []
        )
        action_result = ParticipantActionResultModel(
            status=status,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_point=observation.observation_ref,
            effects=[
                ParticipantActionEffectResultModel(
                    effect_id=f"{request.action_instance_id}.aggregate-transition",
                    effect_class="unknown_effect",
                    description=(
                        "The selected source processed one aggregate participant action; "
                        "the native effect remains outside this projection."
                    ),
                    target_refs=[],
                    evidence_refs=evidence_refs,
                )
            ],
            failure_class=failure_class,
            observations=[observation.observation_ref],
            evidence_refs=evidence_refs,
        )

        modeled = ApplyResult(success=True, snapshot=snapshot)
        if step.terminal_cause is not None:
            modeled = BaseParticipantRuntime.terminate(
                self,
                ParticipantEpisodeTerminateRequest(
                    participant_address=request.participant_address,
                    terminal_reason=ParticipantEpisodeTerminalReason.TRUNCATED,
                    detail="The selected source reached fixed-horizon truncation.",
                ),
                snapshot,
            )
        return ParticipantNativeActionExecution(apply_result=modeled, action_result=action_result)

    def _rejected_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
        failure_class: str,
        code: str,
        message: str,
        status: str = "rejected",
    ) -> ParticipantNativeActionExecution:
        """Model an admitted-then-rejected action with a typed terminal result."""

        observation_point = (
            f"observation.primaite.{episode_id}.{request.action_instance_id}.withheld"
        )
        action_result = ParticipantActionResultModel(
            status=status,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_point=observation_point,
            failure_class=failure_class,
        )
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=[
                    Diagnostic(
                        code=code,
                        domain="participant",
                        address=diagnostic_address(request.participant_address),
                        message=message,
                    )
                ],
            ),
            action_result=action_result,
        )

    def _observation(
        self,
        request: ParticipantActionAdmissionRequest,
        *,
        episode_id: str,
        step: DriverStep,
    ) -> ParticipantObservationEnvelopeModel:
        """Build a bounded participant-relative observation envelope."""

        now = _now_iso()
        observation_ref = (
            f"observation.primaite.{episode_id}.{step.step_number}.{request.action_instance_id}"
        )
        evidence_refs = (
            [ACTION_EVIDENCE_REF]
            if ACTION_EVIDENCE_REF in request.observation_boundary_evidence_refs
            else []
        )
        return ParticipantObservationEnvelopeModel(
            event_id=f"event.{observation_ref}",
            schema_name="raes.participant_runtime.observation",
            schema_version="1.0.0",
            event_type="observation_emission",
            extension_policy="reject_unknown_required",
            source_status=SourceStatusModel(
                status_id=1 if step.processed else 2,
                status="success" if step.processed else "failure",
                status_code=(
                    "participant_action_processed"
                    if step.processed
                    else "participant_action_failed"
                ),
                status_detail="The selected source processed one aggregate participant action.",
                source_status_label="selected-source-action",
                source_status_mapping="raes.participant-action.terminal",
            ),
            participant_address=request.participant_address,
            episode_id=episode_id,
            sequence_number=step.step_number,
            occurred_at=now,
            recorded_at=now,
            ingested_at=now,
            clock_authority="primaite-serialized-source-order",
            ordering_basis="serialized_backend_order",
            actor_ref=request.participant_address,
            producer_ref="backend.primaite.participant-runtime",
            source_system_ref="qualification.primaite.selected-source",
            provenance_refs=[
                "qualification.primaite.selected-source",
                "mapping.primaite.loss-disclosures",
            ],
            evidence_refs=evidence_refs,
            redaction_policy_ref="redaction.primaite.participant-view",
            authorization_scope=f"participant:{request.participant_address}",
            observation_ref=observation_ref,
            visibility_projection_ref=request.observation_boundary_address,
            information_guarantee="lossy_projection",
            delivery_basis="emission_is_delivery",
            delivered_at=now,
            hidden_state_refs=[],
            centralized_state_refs=[],
            loss_descriptor=ParticipantObservationLossDescriptorModel(
                kind="bounded-source-projection",
                fields_redacted=[
                    "native-observation-vector",
                    "native-action-availability",
                    "native-info",
                    "evaluator-only-facts",
                ],
            ),
            stochastic_context=ParticipantObservationStochasticContextModel(
                seed_ref=None,
                randomization_policy_ref="qualification.primaite.partial-stochastic-control",
            ),
            redacted_field_refs=["native-observation-vector", "evaluator-only-facts"],
        )

    def observations(
        self,
        participant_address: str,
    ) -> tuple[ParticipantObservationEnvelopeModel, ...]:
        """Return only the requested participant's sealed observation models."""

        return tuple(self._observations.get(participant_address, ()))

    def driver_operation_ref(self, action_instance_id: str) -> str | None:
        """Return the adapter-generated join for one action, never native data."""

        return self._driver_operation_refs.get(action_instance_id)


__all__ = ["ACTION_EVIDENCE_REF", "PrimaiteParticipantRuntime"]
