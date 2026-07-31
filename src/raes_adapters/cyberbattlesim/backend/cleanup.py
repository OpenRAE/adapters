"""Verified cleanup execution for the in-process CyberBattleSim driver."""

from __future__ import annotations

from functools import partial

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

from .driver import CyberBattleSimDriverProtocol


def _evidence_ref(obligation_id: str, disposition: str) -> str:
    """Build one portable cleanup evidence reference."""

    return f"evidence.cyberbattlesim.cleanup.{obligation_id}.{disposition}"


def _result(
    obligation: CleanupObligationModel,
    status: str,
    disposition: str | None = None,
) -> CleanupObligationResultModel:
    """Build a bounded cleanup result without native details."""

    evidence_refs = (
        [_evidence_ref(obligation.obligation_id, disposition)] if disposition is not None else []
    )
    return CleanupObligationResultModel(
        obligation_id=obligation.obligation_id,
        status=status,
        evidence_refs=evidence_refs,
    )


def _destroy(
    driver: CyberBattleSimDriverProtocol,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    """Close and verify the selected driver resource."""

    report = driver.close()
    status = "succeeded" if report.closed and report.verified else "unverified"
    disposition = "closed" if status == "succeeded" else "unverified"
    return _result(obligation, status, disposition)


def _verify(
    driver: CyberBattleSimDriverProtocol,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    """Probe the selected driver clean-state boundary."""

    verified = driver.verify_closed()
    return _result(
        obligation,
        "succeeded" if verified else "failed",
        "verified" if verified else "not-closed",
    )


def _reset(
    driver: CyberBattleSimDriverProtocol,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    """Reset the selected driver without claiming deterministic replay."""

    driver.reset(None)
    return _result(obligation, "succeeded", "reset")


def _perform(
    driver: CyberBattleSimDriverProtocol,
    obligation: CleanupObligationModel,
) -> CleanupObligationResultModel:
    """Dispatch one admitted cleanup obligation."""

    handlers = {
        "destroy": _destroy,
        "verify": _verify,
        "reset": _reset,
    }
    handler = handlers.get(obligation.action_kind)
    return _result(obligation, "unsupported") if handler is None else handler(driver, obligation)


def _failed(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
    """Project any native cleanup exception as a generic failure."""

    return _result(obligation, "failed", "failed")


def execute_cyberbattlesim_cleanup(
    plan: TrialCleanupPlanModel,
    manifest: BackendManifest,
    driver: CyberBattleSimDriverProtocol,
    *,
    receipt_id: str,
    execution_attempt_id: str,
    trial_outcome: TrialOutcome,
    clean_state_claim: CleanStateClaimModel | None = None,
) -> TrialCleanupReceiptModel:
    """Execute one admitted cleanup plan without exposing native failures."""

    operations = dict.fromkeys(plan.cleanup_obligations, partial(_perform, driver))
    return execute_cleanup(
        plan,
        manifest,
        operations,
        failure_result=_failed,
        receipt_id=receipt_id,
        execution_attempt_id=execution_attempt_id,
        trial_outcome=trial_outcome,
        clean_state_claim=clean_state_claim,
    )


__all__ = ["execute_cyberbattlesim_cleanup"]
