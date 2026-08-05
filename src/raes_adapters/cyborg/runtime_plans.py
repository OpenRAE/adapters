"""Shared CAGE-2 plans expressed only through published RAES contracts."""

from __future__ import annotations

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentEpisodeControlModel,
    ExperimentRedVariantSelectionModel,
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

CAGE2_CLOCK = "time.clock.cage2"


def cage2_time_declaration() -> TimeModelDeclarationModel:
    """Return the RAES-owned logical clock used by CAGE-2 executions."""

    return logical_time_declaration(
        clock=CAGE2_CLOCK,
        domain="time.domain.cage2",
        policy="time.progression.cage2",
        authority_ref="cyborg-cage2-participant-runtime",
        domain_description="One tick per validated aggregate CybORG turn.",
        clock_description="RAES-owned CAGE-2 logical step clock.",
        policy_description="Only a committed aggregate turn advances this clock.",
    )


def cage2_orchestration_plan(
    *, workflow: str, name: str, max_steps: int, red_variant: str
) -> OrchestrationPlan:
    """Return a bounded CAGE-2 workflow through the RAES orchestration contract."""

    episode = ExperimentEpisodeControlModel(
        turn_order="scenario-defined",
        termination_rule="admitted-logical-step-limit-or-source-terminal",
        max_steps=max_steps,
        termination_condition_refs=["source-ledger:wrapper-termination-cutoff"],
    )
    variant = ExperimentRedVariantSelectionModel(
        variant_id=red_variant,
        agent_ref=f"participant.implementation.red-{red_variant}",
    )
    return orchestration_plan(
        workflow=workflow,
        name=name,
        episode_control=episode.model_dump(mode="json"),
        extra_payload={"red_variant_selection": variant.model_dump(mode="json")},
    )


def cage2_evaluation_plan(*, include_execution_contract: bool = True) -> EvaluationPlan:
    """Return the CAGE-2 objective plan over projected confidentiality evidence."""

    return objective_evaluation_plan(
        proposition="evaluation.proposition.compromised",
        assertion="evaluation.assertion.compromised",
        objective="evaluation.objective.defend",
        subject_addresses=["provision.node.user-host"],
        evidence_requirement_refs=["source-ledger:reward-components"],
        predicate={"property": "confidentiality", "operator": "lt", "value": 0.0},
        include_execution_contract=include_execution_contract,
    )


__all__ = [
    "CAGE2_CLOCK",
    "cage2_evaluation_plan",
    "cage2_orchestration_plan",
    "cage2_time_declaration",
]
