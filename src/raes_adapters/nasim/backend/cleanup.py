"""Verified cleanup execution for the in-process NASim driver."""

from __future__ import annotations

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    CleanStateClaimModel,
    TrialCleanupPlanModel,
    TrialCleanupReceiptModel,
)
from raes_contracts.contracts.trial_cleanup import (  # type: ignore[import-untyped]
    TrialOutcome,
)

from raes_adapters._gym_backend.cleanup import CleanupExecution, execute_gym_cleanup

from .driver import NasimDriverProtocol


def execute_nasim_cleanup(
    plan: TrialCleanupPlanModel,
    manifest: BackendManifest,
    driver: NasimDriverProtocol,
    *,
    receipt_id: str,
    execution_attempt_id: str,
    trial_outcome: TrialOutcome,
    clean_state_claim: CleanStateClaimModel | None = None,
) -> TrialCleanupReceiptModel:
    """Execute one admitted cleanup plan without exposing native failures."""

    return execute_gym_cleanup(
        plan,
        manifest,
        driver,
        "nasim",
        CleanupExecution(
            receipt_id=receipt_id,
            execution_attempt_id=execution_attempt_id,
            trial_outcome=trial_outcome,
            clean_state_claim=clean_state_claim,
        ),
    )


__all__ = ["execute_nasim_cleanup"]
