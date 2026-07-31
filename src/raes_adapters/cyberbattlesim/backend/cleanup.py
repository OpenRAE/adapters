"""Verified cleanup execution for the in-process CyberBattleSim driver."""

from __future__ import annotations

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
    return f"evidence.cyberbattlesim.cleanup.{obligation_id}.{disposition}"


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

    def perform(
        obligation: CleanupObligationModel,
    ) -> CleanupObligationResultModel:
        if obligation.action_kind == "destroy":
            report = driver.close()
            if report.closed and report.verified:
                return CleanupObligationResultModel(
                    obligation_id=obligation.obligation_id,
                    status="succeeded",
                    evidence_refs=[_evidence_ref(obligation.obligation_id, "closed")],
                )
            return CleanupObligationResultModel(
                obligation_id=obligation.obligation_id,
                status="unverified",
                evidence_refs=[_evidence_ref(obligation.obligation_id, "unverified")],
            )
        if obligation.action_kind == "verify":
            if driver.verify_closed():
                return CleanupObligationResultModel(
                    obligation_id=obligation.obligation_id,
                    status="succeeded",
                    evidence_refs=[_evidence_ref(obligation.obligation_id, "verified")],
                )
            return CleanupObligationResultModel(
                obligation_id=obligation.obligation_id,
                status="failed",
                evidence_refs=[_evidence_ref(obligation.obligation_id, "not-closed")],
            )
        if obligation.action_kind == "reset":
            driver.reset(None)
            return CleanupObligationResultModel(
                obligation_id=obligation.obligation_id,
                status="succeeded",
                evidence_refs=[_evidence_ref(obligation.obligation_id, "reset")],
            )
        return CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="unsupported",
        )

    def failed(
        obligation: CleanupObligationModel,
    ) -> CleanupObligationResultModel:
        return CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="failed",
            evidence_refs=[_evidence_ref(obligation.obligation_id, "failed")],
        )

    operations = dict.fromkeys(plan.cleanup_obligations, perform)
    return execute_cleanup(
        plan,
        manifest,
        operations,
        failure_result=failed,
        receipt_id=receipt_id,
        execution_attempt_id=execution_attempt_id,
        trial_outcome=trial_outcome,
        clean_state_claim=clean_state_claim,
    )


__all__ = ["execute_cyberbattlesim_cleanup"]
