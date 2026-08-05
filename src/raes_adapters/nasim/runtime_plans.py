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

NASIM_CLOCK = "time.clock.nasim-tiny"


def nasim_time_declaration() -> TimeModelDeclarationModel:
    """Return the RAES-owned logical clock used by NASim executions."""

    domain = "time.domain.nasim-tiny"
    policy = "time.progression.nasim-tiny"
    return TimeModelDeclarationModel(
        domains={
            domain: TimeDomainDeclarationModel(
                address=domain,
                kind="logical",
                tick_period_seconds=ExactRatioModel(numerator=1, denominator=1),
                epoch="run_start",
                visibility="runtime_only",
                description="One tick per validated serialized NASim attacker step.",
            )
        },
        clocks={
            NASIM_CLOCK: ClockDeclarationModel(
                address=NASIM_CLOCK,
                time_domain_address=domain,
                authority_kind="runtime",
                authority_ref="nasim-tiny-participant-runtime",
                monotonicity="non_decreasing",
                supports_pause=True,
                supports_reset=True,
                supports_jump=False,
                description="RAES-owned NASim tiny logical step clock.",
            )
        },
        progression_policies={
            policy: TimeProgressionPolicyDeclarationModel(
                address=policy,
                clock_address=NASIM_CLOCK,
                advancement_mode="event_driven",
                synchronization_mode="none",
                reset_behavior="new_segment_zero",
                replay_behavior="unsupported",
                description="Only a committed serialized attacker step advances this clock.",
            )
        },
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
    payload: dict[str, object] = {
        "name": name,
        "episode_control": episode.model_dump(mode="json"),
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


def nasim_evaluation_plan(*, include_execution_contract: bool = True) -> EvaluationPlan:
    """Return the NASim attacker objective plan over projected compromise evidence."""

    proposition = "evaluation.proposition.sensitive-hosts-owned"
    assertion = "evaluation.assertion.sensitive-hosts-owned"
    objective = "evaluation.objective.compromise-sensitive-hosts"
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
                "subject_addresses": ["provision.node.host-2-0", "provision.node.host-3-0"],
                "evidence_requirement_refs": ["source-ledger:host-compromise-series"],
                "spec": {
                    "predicate": {
                        "property": "ownership.attacker_root",
                        "operator": "gt",
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
    "NASIM_CLOCK",
    "nasim_evaluation_plan",
    "nasim_orchestration_plan",
    "nasim_time_declaration",
]
