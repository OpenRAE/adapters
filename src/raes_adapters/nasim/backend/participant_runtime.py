"""NASim participant lifecycle and one-step action execution."""

from __future__ import annotations

from raes_contracts.participant_binding import (  # type: ignore[import-untyped]
    ParticipantActionAdmissionRequest,
)
from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeTerminalReason,
)

from raes_adapters._gym_backend.participant_runtime import (
    GymParticipantConfig,
    GymParticipantRuntime,
    StepFacts,
)

from .driver import NasimDriverProtocol

ACTION_EVIDENCE_REF = "evidence.nasim.attacker-action"

_ACTION_KIND_BY_CONTRACT = {
    "participant.action-contract.service-exploit": "service-exploit",
    "participant.action-contract.privilege-escalation": "privilege-escalation",
    "participant.action-contract.service-discovery": "service-discovery",
    "participant.action-contract.subnet-discovery": "subnet-discovery",
}
# The native source is fully observed; the portable participant view withholds
# every native fact by default.
_REDACTED_OBSERVATION_FIELDS = [
    "native-fully-observed-state",
    "flat-observation-vector",
    "flat-action-index",
    "native-host-state",
    "evaluator-only-goal-truth",
    "native-info",
]
_REDACTED_FIELD_REFS = ["native-fully-observed-state", "evaluator-only-goal-truth"]


def _terminal_reason(step: StepFacts) -> ParticipantEpisodeTerminalReason:
    """Goal takes precedence for participant completion; truncation is retained."""

    return (
        ParticipantEpisodeTerminalReason.COMPLETED
        if step.terminated
        else ParticipantEpisodeTerminalReason.TRUNCATED
    )


def _target_ref(request: ParticipantActionAdmissionRequest) -> str | None:
    """Pass the admitted portable target through for private native resolution."""

    return request.target_addresses[0] if request.target_addresses else None


class NasimParticipantRuntime(GymParticipantRuntime):
    """Bind RAES participant lifecycle to exactly one serialized source action."""

    def __init__(
        self,
        driver: NasimDriverProtocol,
        *,
        seed: int | None = None,
    ) -> None:
        super().__init__(
            GymParticipantConfig(
                name="nasim",
                action_kind_by_contract=_ACTION_KIND_BY_CONTRACT,
                redacted_observation_fields=_REDACTED_OBSERVATION_FIELDS,
                redacted_field_refs=_REDACTED_FIELD_REFS,
            ),
            reset_driver=driver.reset,
            drive_step=lambda action_kind, request: driver.step(action_kind, _target_ref(request)),
            terminal_reason=_terminal_reason,
            seed=seed,
        )


__all__ = [
    "ACTION_EVIDENCE_REF",
    "NasimParticipantRuntime",
]
