"""Shared CAGE-2 plans expressed only through published RAES contracts."""

from __future__ import annotations

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
from raes_contracts.planning import (  # type: ignore[import-untyped]
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationOp,
    OrchestrationPlan,
    PlannedResource,
    RuntimeDomain,
)

CAGE2_CLOCK = "time.clock.cage2"


def cage2_time_declaration() -> TimeModelDeclarationModel:
    """Return the RAES-owned logical clock used by CAGE-2 executions."""

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
            CAGE2_CLOCK: ClockDeclarationModel(
                address=CAGE2_CLOCK,
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
                clock_address=CAGE2_CLOCK,
                advancement_mode="event_driven",
                synchronization_mode="none",
                reset_behavior="new_segment_zero",
                replay_behavior="unsupported",
                description="Only a committed aggregate turn advances this clock.",
            )
        },
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
    payload: dict[str, object] = {
        "name": name,
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
    operation = OrchestrationOp(
        action=ChangeAction.CREATE,
        address=workflow,
        resource_type="workflow",
        payload=payload,
    )
    return OrchestrationPlan(
        resources={
            workflow: PlannedResource(
                address=workflow,
                domain=RuntimeDomain.ORCHESTRATION,
                resource_type="workflow",
                payload=payload,
            )
        },
        operations=[operation],
        startup_order=[workflow],
    )


def cage2_evaluation_plan(*, include_execution_contract: bool = True) -> EvaluationPlan:
    """Return the CAGE-2 objective plan over projected confidentiality evidence."""

    proposition = "evaluation.proposition.compromised"
    assertion = "evaluation.assertion.compromised"
    objective = "evaluation.objective.defend"
    objective_payload: dict[str, object] = {
        "success_addresses": [assertion],
        "spec": {"success": {"mode": "all"}},
        "result_contract": {
            "resource_type": "objective",
            "supports_passed": True,
            "supports_score": False,
        },
    }
    if include_execution_contract:
        objective_payload["execution_contract"] = {
            "resource_type": "objective",
            "allowed_statuses": ["pending", "running", "ready", "failed"],
            "history_event_types": [
                "evaluation_started",
                "evaluation_updated",
                "evaluation_ready",
                "evaluation_failed",
            ],
            "requires_start_event": True,
        }
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
            payload=objective_payload,
        ),
    ]
    return EvaluationPlan(operations=operations, startup_order=[proposition, assertion, objective])


__all__ = [
    "CAGE2_CLOCK",
    "cage2_evaluation_plan",
    "cage2_orchestration_plan",
    "cage2_time_declaration",
]
