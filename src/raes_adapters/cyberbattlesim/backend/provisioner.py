"""CyberBattleSim provisioner over the selected source profile."""

from __future__ import annotations

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
from .driver import CyberBattleSimDriverProtocol

_SUPPORTED_RESOURCE_TYPES = frozenset(
    {
        "network",
        "node",
        "account-placement",
    }
)


class CyberBattleSimProvisioner(object):
    """Realize the selected generated chain while preserving portable intent."""

    def __init__(self, driver: CyberBattleSimDriverProtocol) -> None:
        self._driver = driver

    @staticmethod
    def validate(plan: ProvisioningPlan) -> list[Diagnostic]:
        diagnostics = list(plan.diagnostics)
        for operation in plan.operations:
            if operation.resource_type not in _SUPPORTED_RESOURCE_TYPES:
                diagnostics.append(
                    Diagnostic(
                        code="cyberbattlesim.provisioning.unsupported-resource",
                        domain="provisioning",
                        address=diagnostic_address(operation.address),
                        message=(
                            "The selected CyberBattleSim profile does not realize "
                            "this provisioning resource type."
                        ),
                    )
                )
        return diagnostics

    def apply(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Apply selected-source construction and portable state changes."""

        diagnostics = self.validate(plan)
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
            snapshot=snapshot.with_entries(entries),
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
            return ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=diagnostics,
            )
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
        """Construct the selected source and bound any native failure."""

        try:
            self._driver.construct()
        except Exception:
            diagnostics.append(
                Diagnostic(
                    code="cyberbattlesim.provisioning.construct-failed",
                    domain="provisioning",
                    address="/provision/cyberbattlesim/selected-profile",
                    message=("The selected CyberBattleSim source could not be constructed."),
                )
            )
            return ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=diagnostics,
            )
        return None


__all__ = ["CyberBattleSimProvisioner"]
