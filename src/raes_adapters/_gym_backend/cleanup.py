"""Neutral verified cleanup execution for an in-process gym-backend driver."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Protocol

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    CleanStateClaimModel,
    CleanupObligationModel,
    CleanupObligationResultModel,
    TrialCleanupPlanModel,
    TrialCleanupReceiptModel,
)
from raes_contracts.contracts.trial_cleanup import (  # type: ignore[import-untyped]
    TrialOutcome,
)

from raes_adapters.base import execute_cleanup


class _CloseReport(Protocol):
    """The sanitized close facts cleanup reads from a driver."""

    @property
    def closed(self) -> bool: ...

    @property
    def verified(self) -> bool: ...


class _CleanupDriver(Protocol):
    """The driver close/verify/reset surface cleanup dispatches over."""

    def close(self) -> _CloseReport: ...

    def verify_closed(self) -> bool: ...

    def reset(self, seed: int | None) -> object: ...


def _result(
    name: str,
    obligation: CleanupObligationModel,
    status: str,
    disposition: str | None = None,
) -> CleanupObligationResultModel:
    """Build a bounded cleanup result without native details."""

    evidence_refs = (
        [f"evidence.{name}.cleanup.{obligation.obligation_id}.{disposition}"]
        if disposition is not None
        else []
    )
    return CleanupObligationResultModel(
        obligation_id=obligation.obligation_id,
        status=status,
        evidence_refs=evidence_refs,
    )


def _destroy(
    name: str,
    driver: _CleanupDriver,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    """Close and verify the selected driver resource."""

    report = driver.close()
    status = "succeeded" if report.closed and report.verified else "unverified"
    disposition = "closed" if status == "succeeded" else "unverified"
    return _result(name, obligation, status, disposition)


def _verify(
    name: str,
    driver: _CleanupDriver,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    """Probe the selected driver clean-state boundary."""

    verified = driver.verify_closed()
    return _result(
        name,
        obligation,
        "succeeded" if verified else "failed",
        "verified" if verified else "not-closed",
    )


def _reset(
    name: str,
    driver: _CleanupDriver,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    """Reset the selected driver without claiming deterministic replay."""

    driver.reset(None)
    return _result(name, obligation, "succeeded", "reset")


def _perform(
    name: str,
    driver: _CleanupDriver,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    """Dispatch one admitted cleanup obligation."""

    handlers = {"destroy": _destroy, "verify": _verify, "reset": _reset}
    handler = handlers.get(obligation.action_kind)
    return (
        _result(name, obligation, "unsupported")
        if handler is None
        else handler(name, driver, obligation)
    )


@dataclass(frozen=True)
class CleanupExecution(object):
    """The per-attempt receipt identity and outcome for one cleanup run."""

    receipt_id: str
    execution_attempt_id: str
    trial_outcome: TrialOutcome
    clean_state_claim: CleanStateClaimModel | None = None


def execute_gym_cleanup(
    plan: TrialCleanupPlanModel,
    manifest: BackendManifest,
    driver: _CleanupDriver,
    name: str,
    execution: CleanupExecution,
) -> TrialCleanupReceiptModel:
    """Execute one admitted cleanup plan without exposing native failures."""

    operations = dict.fromkeys(plan.cleanup_obligations, partial(_perform, name, driver))
    return execute_cleanup(
        plan,
        manifest,
        operations,
        failure_result=partial(_result, name, status="failed", disposition="failed"),
        receipt_id=execution.receipt_id,
        execution_attempt_id=execution.execution_attempt_id,
        trial_outcome=execution.trial_outcome,
        clean_state_claim=execution.clean_state_claim,
    )


__all__ = ["CleanupExecution", "execute_gym_cleanup"]
