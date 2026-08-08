"""NASim tiny plans expressed only through published RAES contracts.

These mirror the CAGE-2 researcher plans but describe a single red attacker with
no red-variant selection: the selected NASim ``tiny`` static benchmark has one
autonomous bruteforce attacker and no defender or second participant. Time is a
RAES-owned logical step clock, and the objective is the attacker's compromise of
the sensitive hosts projected through evaluator-owned evidence.
"""

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

NASIM_CLOCK = "time.clock.nasim-tiny"


def nasim_time_declaration() -> TimeModelDeclarationModel:
    """Return the RAES-owned logical clock used by NASim executions."""

    return logical_time_declaration(
        clock=NASIM_CLOCK,
        domain="time.domain.nasim-tiny",
        policy="time.progression.nasim-tiny",
        authority_ref="nasim-tiny-participant-runtime",
        domain_description="One tick per validated serialized NASim attacker step.",
        clock_description="RAES-owned NASim tiny logical step clock.",
        policy_description="Only a committed serialized attacker step advances this clock.",
    )


def nasim_orchestration_plan(*, workflow: str, name: str, max_steps: int) -> OrchestrationPlan:
    """Return a bounded single-attacker workflow through the RAES contract.

    Unlike CAGE-2 there is no red-variant selection: the selected tiny scenario
    has exactly one attacker and no defender or second participant, so no
    variant, contention, or coordination is declared.
    """

    episode = ExperimentEpisodeControlModel(
        turn_order="sequential",
        termination_rule="admitted-logical-step-limit-or-source-terminal",
        max_steps=max_steps,
        termination_condition_refs=["goal-reached", "step-limit"],
    )
    return orchestration_plan(
        workflow=workflow,
        name=name,
        episode_control=episode.model_dump(mode="json"),
    )


def nasim_evaluation_plan(*, include_execution_contract: bool = True) -> EvaluationPlan:
    """Return the NASim attacker objective plan over projected compromise evidence."""

    return objective_evaluation_plan(
        proposition="evaluation.proposition.sensitive-hosts-owned",
        assertion="evaluation.assertion.sensitive-hosts-owned",
        objective="evaluation.objective.compromise-sensitive-hosts",
        subject_addresses=["provision.node.host-2-0", "provision.node.host-3-0"],
        evidence_requirement_refs=["source-ledger:host-compromise-series"],
        predicate={"property": "ownership.attacker_root", "operator": "gt", "value": 0.0},
        include_execution_contract=include_execution_contract,
    )


__all__ = [
    "NASIM_CLOCK",
    "nasim_evaluation_plan",
    "nasim_orchestration_plan",
    "nasim_time_declaration",
]
