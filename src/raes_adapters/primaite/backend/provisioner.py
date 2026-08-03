"""PrimAITE provisioner over the selected fixed-source scenario."""

from __future__ import annotations

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    RealizationEnvelopeIdentityModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]
from raes_contracts.planning import (  # type: ignore[import-untyped]
    ChangeAction,
    ProvisioningPlan,
    RuntimeDomain,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
    SnapshotEntry,
)

from ._diagnostics import diagnostic_address
from .driver import PrimaiteDriverProtocol

_SUPPORTED_RESOURCE_TYPES = frozenset({"network", "node"})


class PrimaiteProvisioner(object):
    """Realize the fixed selected scenario while preserving portable intent.

    The provisioner is bound to the selected realization envelope. It accepts only
    a plan that joins to that realization (and a baseline snapshot that belongs to
    it), never synthesizes a native topology from SDL, and never stores a native
    handle in the portable target: it records planned RAES state plus the selected
    realization identity and constructs one aggregate native session through the
    private driver.
    """

    def __init__(
        self,
        driver: PrimaiteDriverProtocol,
        realization_envelope: RealizationEnvelopeIdentityModel,
    ) -> None:
        self._driver = driver
        self._realization_envelope = realization_envelope

    def validate(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        diagnostics = list(plan.diagnostics)
        for operation in plan.operations:
            if operation.resource_type not in _SUPPORTED_RESOURCE_TYPES:
                diagnostics.append(
                    Diagnostic(
                        code="primaite.provisioning.unsupported-resource",
                        domain="provisioning",
                        address=diagnostic_address(operation.address),
                        message=(
                            "The selected PrimAITE profile does not realize this "
                            "provisioning resource type."
                        ),
                    )
                )
        return diagnostics

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
                address="/provision/primaite/selected-scenario",
                message="Provisioning plan is missing the selected realization envelope identity.",
            )
        elif plan.realization_envelope != self._realization_envelope:
            diagnostic = Diagnostic(
                code="primaite.provisioning.realization-envelope-mismatch",
                domain="provisioning",
                address="/provision/primaite/selected-scenario",
                message="Provisioning plan does not target the selected PrimAITE realization.",
            )
        elif (
            snapshot.realization_envelope is not None
            and snapshot.realization_envelope != self._realization_envelope
        ) or (snapshot.entries and snapshot.realization_envelope is None):
            diagnostic = Diagnostic(
                code="primaite.provisioning.realization-envelope-baseline-mismatch",
                domain="provisioning",
                address="/provision/primaite/selected-scenario",
                message="Runtime snapshot does not belong to the selected PrimAITE realization.",
            )
        return [] if diagnostic is None else [diagnostic]

    def apply(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Apply the fixed selected construction and portable state changes."""

        diagnostics = self.validate(plan)
        diagnostics.extend(self._identity_diagnostics(plan, snapshot))
        preflight = self._preflight(plan, snapshot, diagnostics)
        if preflight is not None:
            return preflight

        entries = dict(snapshot.entries)
        changed_addresses: list[str] = []
        for operation in plan.operations:
            if operation.action == ChangeAction.UNCHANGED:
                continue
            if operation.action == ChangeAction.DELETE:
                entries.pop(operation.address, None)
                changed_addresses.append(operation.address)
                continue
            entries[operation.address] = SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=operation.payload,
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
                status="applied",
            )
            changed_addresses.append(operation.address)

        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                realization_envelope=self._realization_envelope,
            ),
            diagnostics=diagnostics,
            changed_addresses=changed_addresses,
        )

    def _preflight(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        diagnostics: list[Diagnostic],
    ) -> ApplyResult | None:
        """Return a terminal validation, no-op, or construction result."""

        if any(diagnostic.is_error for diagnostic in diagnostics):
            return ApplyResult(success=False, snapshot=snapshot, diagnostics=diagnostics)
        mutating_operations = [
            operation for operation in plan.operations if operation.action != ChangeAction.UNCHANGED
        ]
        if not mutating_operations:
            return ApplyResult(success=True, snapshot=snapshot, diagnostics=diagnostics)
        should_construct = any(
            operation.action in {ChangeAction.CREATE, ChangeAction.UPDATE}
            for operation in plan.operations
        )
        return self._construct_failure(snapshot, diagnostics) if should_construct else None

    def _construct_failure(
        self,
        snapshot: RuntimeSnapshot,
        diagnostics: list[Diagnostic],
    ) -> ApplyResult | None:
        """Construct the fixed selected source and bound any native failure."""

        try:
            self._driver.construct()
        except Exception:
            diagnostics.append(
                Diagnostic(
                    code="primaite.provisioning.construct-failed",
                    domain="provisioning",
                    address="/provision/primaite/selected-scenario",
                    message="The selected PrimAITE source could not be constructed.",
                )
            )
            return ApplyResult(success=False, snapshot=snapshot, diagnostics=diagnostics)
        return None


__all__ = ["PrimaiteProvisioner"]
