"""Driver-local cleanup sequencing over published RAES cleanup contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.capability_admission import (  # type: ignore[import-untyped]
    require_cleanup_plan_capability,
)
from raes_contracts.contracts.trial_cleanup import (  # type: ignore[import-untyped]
    CleanStateClaimModel,
    CleanupObligationModel,
    CleanupObligationResultModel,
    CleanupOutcome,
    CleanupTrigger,
    TrialCleanupPlanModel,
    TrialCleanupReceiptModel,
    TrialOutcome,
    validate_trial_cleanup_receipt,
)

CleanupOperation = Callable[[CleanupObligationModel], CleanupObligationResultModel]
CleanupFailureResultFactory = Callable[[CleanupObligationModel], CleanupObligationResultModel]

_TRIGGER_BY_OUTCOME: dict[TrialOutcome, CleanupTrigger] = {
    "succeeded": "success",
    "failed": "failure",
    "cancelled": "cancellation",
    "timed-out": "timeout",
    "aborted": "abort",
}


def _dependency_order(plan: TrialCleanupPlanModel) -> tuple[CleanupObligationModel, ...]:
    ordered: list[CleanupObligationModel] = []
    visited: set[str] = set()

    def visit(obligation_id: str) -> None:
        if obligation_id in visited:
            return
        obligation = plan.cleanup_obligations[obligation_id]
        for dependency in obligation.depends_on:
            visit(dependency)
        visited.add(obligation_id)
        ordered.append(obligation)

    for obligation_id in plan.cleanup_obligations:
        visit(obligation_id)
    return tuple(ordered)


def _checked_result(
    result: object,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    if not isinstance(result, CleanupObligationResultModel):
        raise ValueError("Cleanup callback did not return a published RAES obligation result.")
    if result.obligation_id != obligation.obligation_id:
        raise ValueError("Cleanup callback result does not match its published obligation.")
    return result


def _failure_result_without_native_context(
    factory: CleanupFailureResultFactory,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    try:
        return factory(obligation)
    except Exception:
        pass
    raise ValueError("Cleanup failure reporting failed.")


def _validated_failure_result(
    factory: CleanupFailureResultFactory,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    result = _failure_result_without_native_context(factory, obligation)
    try:
        return _checked_result(result, obligation)
    except Exception:
        pass
    raise ValueError("Cleanup failure reporting returned an invalid RAES result.")


def _checked_result_or_failure(
    result: object,
    obligation: CleanupObligationModel,
    failure_result: CleanupFailureResultFactory,
) -> CleanupObligationResultModel:
    try:
        return _checked_result(result, obligation)
    except Exception:
        pass
    return _validated_failure_result(failure_result, obligation)


def _cleanup_status(
    results: Mapping[str, CleanupObligationResultModel],
) -> CleanupOutcome:
    if not results:
        return "not-required"
    statuses = [result.status for result in results.values()]
    if all(status == "succeeded" for status in statuses):
        return "succeeded"
    if all(status == "unsupported" for status in statuses):
        return "unsupported"
    if all(status == "unverified" for status in statuses):
        return "unverified"
    if any(status == "succeeded" for status in statuses):
        return "partial"
    if any(status in {"failed", "skipped"} for status in statuses):
        return "failed"
    return "partial"


def execute_cleanup(
    plan: TrialCleanupPlanModel,
    manifest: BackendManifest,
    operations: Mapping[str, CleanupOperation],
    *,
    failure_result: CleanupFailureResultFactory,
    receipt_id: str,
    execution_attempt_id: str,
    trial_outcome: TrialOutcome,
    clean_state_claim: CleanStateClaimModel | None = None,
) -> TrialCleanupReceiptModel:
    """Execute triggered obligations and return a validated RAES receipt.

    RAES admits the plan before any native callback runs. Callbacks execute
    synchronously in dependency order and remain responsible for their declared
    timeout and native verification mechanics; this helper does not start
    threads or claim preemptive cancellation. If a callback raises, its native
    exception is never inspected or rendered. ``failure_result`` receives only
    the portable obligation and supplies the published, evidence-bounded failure
    result.
    """

    require_cleanup_plan_capability(manifest, plan)
    trigger = _TRIGGER_BY_OUTCOME[trial_outcome]
    results: dict[str, CleanupObligationResultModel] = {}

    for obligation in _dependency_order(plan):
        if trigger not in obligation.triggers:
            continue
        blocking_dependency = any(
            dependency in results and results[dependency].status != "succeeded"
            for dependency in obligation.depends_on
        )
        if blocking_dependency:
            results[obligation.obligation_id] = CleanupObligationResultModel(
                obligation_id=obligation.obligation_id,
                status="skipped",
            )
            continue

        operation = operations.get(obligation.obligation_id)
        if operation is None:
            results[obligation.obligation_id] = CleanupObligationResultModel(
                obligation_id=obligation.obligation_id,
                status="unsupported",
            )
            continue
        operation_failed = False
        result: object = None
        try:
            result = operation(obligation)
        except Exception:
            operation_failed = True
        if operation_failed:
            checked_result = _validated_failure_result(failure_result, obligation)
        else:
            checked_result = _checked_result_or_failure(result, obligation, failure_result)
        results[obligation.obligation_id] = checked_result

    receipt = TrialCleanupReceiptModel(
        receipt_id=receipt_id,
        cleanup_plan_ref=plan.plan_id,
        plan_entry_id=plan.plan_entry_id,
        run_id=plan.run_id,
        execution_attempt_id=execution_attempt_id,
        trial_outcome=trial_outcome,
        cleanup_status=_cleanup_status(results),
        obligation_results=results,
        clean_state_claim=clean_state_claim,
    )
    validate_trial_cleanup_receipt(plan, receipt)
    return receipt


__all__ = ["execute_cleanup"]
