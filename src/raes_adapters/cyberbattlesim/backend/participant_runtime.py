"""CyberBattleSim participant lifecycle and one-step action execution."""

from __future__ import annotations

from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeTerminalReason,
)

from raes_adapters._gym_backend.participant_runtime import (
    GymParticipantConfig,
    GymParticipantRuntime,
    StepFacts,
)

from .driver import CyberBattleSimDriverProtocol

ACTION_EVIDENCE_REF = "evidence.cyberbattlesim.attacker-action"

_ACTION_KIND_BY_CONTRACT = {
    "participant.action-contract.connect": "connect",
    "participant.action-contract.local-vulnerability": "local-vulnerability",
    "participant.action-contract.remote-vulnerability": "remote-vulnerability",
}
_REDACTED_OBSERVATION_FIELDS = [
    "native-state",
    "native-action-availability",
    "native-credential-material",
    "evaluator-only-facts",
]
_REDACTED_FIELD_REFS = ["native-state", "evaluator-only-facts"]


def _terminal_reason(step: StepFacts) -> ParticipantEpisodeTerminalReason:
    """Truncate on the evaluator cutoff; otherwise complete the episode."""

    return (
        ParticipantEpisodeTerminalReason.TRUNCATED
        if step.truncated or step.terminal_cause == "evaluator-cutoff"
        else ParticipantEpisodeTerminalReason.COMPLETED
    )


class CyberBattleSimParticipantRuntime(GymParticipantRuntime):
    """Bind RAES participant lifecycle to exactly one serialized source action."""

    def __init__(
        self,
        driver: CyberBattleSimDriverProtocol,
        *,
        seed: int | None = None,
    ) -> None:
        super().__init__(
            GymParticipantConfig(
                name="cyberbattlesim",
                action_kind_by_contract=_ACTION_KIND_BY_CONTRACT,
                redacted_observation_fields=_REDACTED_OBSERVATION_FIELDS,
                redacted_field_refs=_REDACTED_FIELD_REFS,
            ),
            reset_driver=driver.reset,
            drive_step=lambda action_kind, _request: driver.step(action_kind),
            terminal_reason=_terminal_reason,
            seed=seed,
        )


__all__ = [
    "ACTION_EVIDENCE_REF",
    "CyberBattleSimParticipantRuntime",
]
