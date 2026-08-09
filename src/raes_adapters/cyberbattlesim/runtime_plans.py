"""CyberBattleSim chain plans expressed through published RAES contracts."""

from __future__ import annotations

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentEpisodeControlModel,
)
from raes_contracts.contracts.time_model import (  # type: ignore[import-untyped]
    TimeModelDeclarationModel,
)
from raes_contracts.planning import (  # type: ignore[import-untyped]
    EvaluationPlan,
    OrchestrationPlan,
)

from raes_adapters._researcher_support import (
    logical_time_declaration,
    objective_evaluation_plan,
    orchestration_plan,
)

CYBERBATTLESIM_CLOCK = "time.clock.cyberbattlesim-chain"


def cyberbattlesim_time_declaration() -> TimeModelDeclarationModel:
    """Return the RAES-owned logical clock used by CyberBattleSim executions."""

    return logical_time_declaration(
        clock=CYBERBATTLESIM_CLOCK,
        domain="time.domain.cyberbattlesim-chain",
        policy="time.progression.cyberbattlesim-chain",
        authority_ref="cyberbattlesim-chain-participant-runtime",
        domain_description="One tick per validated serialized CyberBattleSim attacker step.",
        clock_description="RAES-owned CyberBattleSim chain logical step clock.",
        policy_description="Only a committed serialized attacker step advances this clock.",
    )


def cyberbattlesim_orchestration_plan(
    *, workflow: str, name: str, max_steps: int
) -> OrchestrationPlan:
    """Return a bounded single-attacker workflow through the RAES contract.

    The exact source policy proposes one serialized red action at a time. The
    source-internal defender remains disclosed interaction, not another admitted
    participant.
    """

    episode = ExperimentEpisodeControlModel(
        turn_order="sequential",
        termination_rule="admitted-logical-step-limit-or-source-terminal",
        max_steps=max_steps,
        termination_condition_refs=[
            "attacker-ownership",
            "defender-sla",
            "defender-eviction",
            "evaluator-cutoff",
        ],
    )
    return orchestration_plan(
        workflow=workflow,
        name=name,
        episode_control=episode.model_dump(mode="json"),
    )


def cyberbattlesim_evaluation_plan(*, include_execution_contract: bool = True) -> EvaluationPlan:
    """Return the CyberBattleSim attacker objective plan over projected compromise evidence."""

    return objective_evaluation_plan(
        proposition="evaluation.proposition.network-owned",
        assertion="evaluation.assertion.network-owned",
        objective="evaluation.objective.own-network",
        subject_addresses=["provision.node.customer-data"],
        evidence_requirement_refs=["source-ledger:attacker-action-log"],
        predicate={"property": "ownership.attacker", "operator": "exists"},
        include_execution_contract=include_execution_contract,
    )


__all__ = [
    "CYBERBATTLESIM_CLOCK",
    "cyberbattlesim_evaluation_plan",
    "cyberbattlesim_orchestration_plan",
    "cyberbattlesim_time_declaration",
]
