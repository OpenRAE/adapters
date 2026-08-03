"""PrimAITE provisioner over the selected fixed-source scenario."""

from __future__ import annotations

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    RealizationEnvelopeIdentityModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]
from raes_contracts.planning import (  # type: ignore[import-untyped]
    ChangeAction,
    ProvisioningPlan,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
)

from raes_adapters._gym_backend.provisioner import GymProvisioner

from .driver import PrimaiteDriverProtocol

_SELECTED_SCENARIO_ADDRESS = "/provision/primaite/selected-scenario"


class PrimaiteProvisioner(GymProvisioner):
    """Realize the fixed selected scenario, bound to its realization envelope.

    The neutral :class:`GymProvisioner` realizes the selected source and preserves
    ownership on failure. PrimAITE additionally binds every plan and baseline to
    the selected realization envelope identity: a plan that omits or mismatches
    the realization, or a baseline that does not belong to it, is refused before
    any construction, and a successful apply stamps the selected realization onto
    the snapshot. The profile realizes a network/node topology; the shared
    provisioner's wider supported-resource set is harmless because the selected
    fixed SDL never emits other resource types.
    """

    def __init__(
        self,
        driver: PrimaiteDriverProtocol,
        realization_envelope: RealizationEnvelopeIdentityModel,
    ) -> None:
        super().__init__(driver, "primaite")
        self._realization_envelope = realization_envelope

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Realize the plan, then stamp the selected realization on a mutating success."""

        result = super().apply(plan, snapshot)
        mutated = any(operation.action != ChangeAction.UNCHANGED for operation in plan.operations)
        if not (result.success and mutated):
            return result
        return ApplyResult(
            success=True,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries),
                realization_envelope=self._realization_envelope,
            ),
            diagnostics=result.diagnostics,
            changed_addresses=result.changed_addresses,
        )

    def _preflight(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        diagnostics: list[Diagnostic],
    ) -> ApplyResult | None:
        """Refuse a plan or baseline that does not join the selected realization first."""

        diagnostics.extend(self._identity_diagnostics(plan, snapshot))
        return super()._preflight(plan, snapshot, diagnostics)

    def _identity_diagnostics(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> list[Diagnostic]:
        """Reject a plan or baseline that does not join to the selected realization."""

        diagnostic: Diagnostic | None = None
        if plan.realization_envelope is None:
            diagnostic = Diagnostic(
                code="primaite.provisioning.realization-envelope-missing",
                domain="provisioning",
                address=_SELECTED_SCENARIO_ADDRESS,
                message="Provisioning plan is missing the selected realization envelope identity.",
            )
        elif plan.realization_envelope != self._realization_envelope:
            diagnostic = Diagnostic(
                code="primaite.provisioning.realization-envelope-mismatch",
                domain="provisioning",
                address=_SELECTED_SCENARIO_ADDRESS,
                message="Provisioning plan does not target the selected PrimAITE realization.",
            )
        elif (
            snapshot.realization_envelope is not None
            and snapshot.realization_envelope != self._realization_envelope
        ) or (snapshot.entries and snapshot.realization_envelope is None):
            diagnostic = Diagnostic(
                code="primaite.provisioning.realization-envelope-baseline-mismatch",
                domain="provisioning",
                address=_SELECTED_SCENARIO_ADDRESS,
                message="Runtime snapshot does not belong to the selected PrimAITE realization.",
            )
        return [] if diagnostic is None else [diagnostic]


__all__ = ["PrimaiteProvisioner"]
