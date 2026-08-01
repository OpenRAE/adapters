"""CyberBattleSim participant lifecycle and one-step action execution."""

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
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    Diagnostic,
    Severity,
)
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
from .driver import (
    CyberBattleSimDriverProtocol,
    DriverResetReport,
    DriverStep,
)

ACTION_EVIDENCE_REF = "evidence.cyberbattlesim.attacker-action"

_ACTION_KIND_BY_CONTRACT = {
    "participant.action-contract.connect": "connect",
    "participant.action-contract.local-vulnerability": "local-vulnerability",
    "participant.action-contract.remote-vulnerability": "remote-vulnerability",
}


def _now_iso() -> str:
    """Return a portable UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class CyberBattleSimParticipantRuntime(BaseParticipantRuntime):  # type: ignore[misc]
    """Bind RAES participant lifecycle to exactly one serialized source action."""

    def __init__(
        self,
        driver: CyberBattleSimDriverProtocol,
        *,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self._driver = driver
        self._seed = seed
        self._observations: dict[
            str,
            list[ParticipantObservationEnvelopeModel],
        ] = {}
        self._driver_operation_refs: dict[str, str] = {}

    def initialize(
        self,
        request: ParticipantEpisodeInitializeRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        portable = super().initialize(request, snapshot)
        return self._reset_source_after_portable(
            request.participant_address,
            portable,
            snapshot,
        )

    def reset(
        self,
        request: ParticipantEpisodeResetRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        portable = super().reset(request, snapshot)
        return self._reset_source_after_portable(
            request.participant_address,
            portable,
            snapshot,
        )

    def restart(
        self,
        request: ParticipantEpisodeRestartRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        portable = super().restart(request, snapshot)
        return self._reset_source_after_portable(
            request.participant_address,
            portable,
            snapshot,
        )

    def _reset_source_after_portable(
        self,
        participant_address: str,
        portable: ApplyResult,
        predecessor: RuntimeSnapshot,
    ) -> ApplyResult:
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
                        code="cyberbattlesim.participant.reset-failed",
                        domain="participant",
                        address=diagnostic_address(participant_address),
                        message=("The selected CyberBattleSim episode could not be reset."),
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
        self._results = {
            address: dict(result)
            for address, result in snapshot.participant_episode_results.items()
        }
        self._history = {
            address: [dict(event) for event in events]
            for address, events in snapshot.participant_episode_history.items()
        }

    @staticmethod
    def _reset_diagnostics(
        participant_address: str,
        report: DriverResetReport,
    ) -> list[Diagnostic]:
        diagnostics = [
            Diagnostic(
                code="cyberbattlesim.seed.applied",
                domain="participant",
                address=diagnostic_address(participant_address),
                message=("The adapter applied a selected stochastic-control binding."),
                severity=Severity.INFO,
            )
            for _stream in report.applied_streams
        ]
        diagnostics.extend(
            Diagnostic(
                code="cyberbattlesim.seed.unbound",
                domain="participant",
                address=diagnostic_address(participant_address),
                message=("A selected CyberBattleSim random stream remains unbound."),
                severity=Severity.WARNING,
            )
            for _stream in report.unbound_streams
        )
        return diagnostics

    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        """Validate the portable action kind before native execution."""

        action_kind = _ACTION_KIND_BY_CONTRACT.get(request.action_contract_address)
        if action_kind is None or request.validated_selection is None:
            return self._rejected_action(
                request,
                snapshot,
                episode_id=episode_id,
                failure_class="unsupported_action",
                code="cyberbattlesim.participant.unsupported-action",
                message=(
                    "The selected CyberBattleSim profile does not support this participant action."
                ),
            )
        return self._execute_supported_action(
            request,
            snapshot,
            episode_id=episode_id,
            action_kind=action_kind,
        )

    def _execute_supported_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
        action_kind: str,
    ) -> ParticipantNativeActionExecution:
        """Execute one supported action and bound native failures."""

        try:
            step = self._driver.step(action_kind)
        except Exception:
            return self._rejected_action(
                request,
                snapshot,
                episode_id=episode_id,
                failure_class="backend_error",
                code="cyberbattlesim.participant.action-failed",
                message=(
                    "The CyberBattleSim driver could not complete the admitted participant action."
                ),
                status="failed",
            )

        self._driver_operation_refs[request.action_instance_id] = step.operation_ref
        if not step.source_transition:
            return self._rejected_action(
                request,
                snapshot,
                episode_id=episode_id,
                failure_class="target_unavailable",
                code="cyberbattlesim.participant.action-unavailable",
                message=("No source transition was available for the admitted participant action."),
            )
        return self._accepted_action(
            request,
            snapshot,
            episode_id=episode_id,
            step=step,
        )

    def _accepted_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
        step: DriverStep,
    ) -> ParticipantNativeActionExecution:
        """Build portable results for one completed source transition."""

        observation = self._observation(
            request,
            episode_id=episode_id,
            step=step,
        )
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
                    effect_id=f"{request.action_instance_id}.source-transition",
                    effect_class="unknown_effect",
                    description=(
                        "The selected source processed one participant action; "
                        "the native effect remains outside this projection."
                    ),
                    target_refs=list(step.portable_target_refs),
                    evidence_refs=evidence_refs,
                )
            ],
            failure_class=failure_class,
            observations=[observation.observation_ref],
            evidence_refs=evidence_refs,
        )

        modeled = ApplyResult(success=True, snapshot=snapshot)
        if step.terminal_cause is not None:
            terminal_reason = (
                ParticipantEpisodeTerminalReason.TRUNCATED
                if step.truncated or step.terminal_cause == "evaluator-cutoff"
                else ParticipantEpisodeTerminalReason.COMPLETED
            )
            modeled = BaseParticipantRuntime.terminate(
                self,
                ParticipantEpisodeTerminateRequest(
                    participant_address=request.participant_address,
                    terminal_reason=terminal_reason,
                    detail=("The selected source reached a terminal episode condition."),
                ),
                snapshot,
            )
        return ParticipantNativeActionExecution(
            apply_result=modeled,
            action_result=action_result,
        )

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
        observation_point = (
            f"observation.cyberbattlesim.{episode_id}.{request.action_instance_id}.withheld"
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
        now = _now_iso()
        observation_ref = (
            f"observation.cyberbattlesim.{episode_id}."
            f"{step.step_number}.{request.action_instance_id}"
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
                status_detail=("The selected source processed one participant action."),
                source_status_label="selected-source-action",
                source_status_mapping="raes.participant-action.terminal",
            ),
            participant_address=request.participant_address,
            episode_id=episode_id,
            sequence_number=step.step_number,
            occurred_at=now,
            recorded_at=now,
            ingested_at=now,
            clock_authority="cyberbattlesim-serialized-source-order",
            ordering_basis="serialized_backend_order",
            actor_ref=request.participant_address,
            producer_ref="backend.cyberbattlesim.participant-runtime",
            source_system_ref="qualification.cyberbattlesim.selected-source",
            provenance_refs=[
                "qualification.cyberbattlesim.selected-source",
                "mapping.cyberbattlesim.loss-disclosures",
            ],
            evidence_refs=evidence_refs,
            redaction_policy_ref="redaction.cyberbattlesim.participant-view",
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
                    "native-state",
                    "native-action-availability",
                    "native-credential-material",
                    "evaluator-only-facts",
                ],
            ),
            stochastic_context=ParticipantObservationStochasticContextModel(
                seed_ref=("seed.cyberbattlesim.public" if self._seed is not None else None),
                randomization_policy_ref=(
                    "qualification.cyberbattlesim.partial-stochastic-control"
                ),
            ),
            redacted_field_refs=[
                "native-state",
                "evaluator-only-facts",
            ],
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


__all__ = [
    "ACTION_EVIDENCE_REF",
    "CyberBattleSimParticipantRuntime",
]
