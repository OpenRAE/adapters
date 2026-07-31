"""Aggregate RAES Provisioner for the selected CybORG/CAGE-2 backend."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    RealizationEnvelopeIdentityModel,
)
from raes_contracts.diagnostics import Diagnostic, Severity  # type: ignore[import-untyped]
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

from .driver import (
    CyborgDriver,
)
from .scenario import (
    CYBORG_SCENARIO_MAPPING_VERSION,
    CyborgScenarioDescriptor,
    copied_resource,
    validate_scenario_resources,
)

_DOMAIN = "runtime"
_SUPPORTED_RESOURCE_TYPES = frozenset({"network", "node"})


@dataclass
class _Reconciliation:
    entries: dict[str, SnapshotEntry]
    changed_addresses: list[str]


class CyborgProvisioner:
    """Construct one private CybORG scenario from an admitted RAES plan."""

    def __init__(
        self,
        driver: CyborgDriver,
        *,
        realization_envelope: RealizationEnvelopeIdentityModel,
        profile_id: str,
        source_commit: str,
        seed: int | None,
    ) -> None:
        self._driver = driver
        self._realization_envelope = realization_envelope
        self._profile_id = profile_id
        self._source_commit = source_commit
        self._seed = seed
        self._active: object | None = None
        self._active_available = False
        self._pending_cleanup: list[object] = []
        self._lock = threading.RLock()

    def validate(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        """Validate backend-specific construction facts before native effects."""

        if not isinstance(plan, ProvisioningPlan):
            return [
                _diagnostic(
                    "cyborg-backend.invalid-plan",
                    "CybORG provisioner accepts only published RAES provisioning plans.",
                )
            ]
        diagnostics = list(plan.diagnostics)
        diagnostics.extend(self._identity_diagnostics(plan, RuntimeSnapshot()))
        diagnostics.extend(_resource_diagnostics(plan))
        return diagnostics

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Reconcile a complete desired state and atomically own one backend."""

        with self._lock:
            if not isinstance(plan, ProvisioningPlan):
                return _failure(
                    snapshot,
                    _diagnostic(
                        "cyborg-backend.invalid-plan",
                        "CybORG provisioner accepts only published RAES provisioning plans.",
                    ),
                )
            diagnostics = [
                *plan.diagnostics,
                *self._identity_diagnostics(plan, snapshot),
                *_resource_diagnostics(plan),
            ]
            if any(item.is_error for item in diagnostics):
                return ApplyResult(
                    success=False,
                    snapshot=snapshot,
                    diagnostics=diagnostics,
                )
            if not self._retry_pending_cleanup():
                return _failure(snapshot, _cleanup_failed_diagnostic())

            reconciliation = _reconcile(plan)
            if not reconciliation.changed_addresses:
                if reconciliation.entries and not self._active_available:
                    if self._active is not None:
                        if not self._cleanup_handle(self._active):
                            return _failure(snapshot, _cleanup_failed_diagnostic())
                        self._active = None
                    return self._replace_backend(plan, snapshot, reconciliation)
                return _success(snapshot, reconciliation, self._realization_envelope)

            if not reconciliation.entries:
                if not self.cleanup():
                    return _failure(snapshot, _cleanup_failed_diagnostic())
                return _success(snapshot, reconciliation, self._realization_envelope)

            return self._replace_backend(plan, snapshot, reconciliation)

    def cleanup(self) -> bool:
        """Release all owned and pending native state; repeated calls are safe."""

        with self._lock:
            succeeded = self._retry_pending_cleanup()
            if self._active is not None:
                handle = self._active
                if self._cleanup_handle(handle):
                    self._active = None
                    self._active_available = False
                else:
                    self._active_available = False
                    succeeded = False
            return succeeded

    def _replace_backend(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        reconciliation: _Reconciliation,
    ) -> ApplyResult:
        descriptor = self._descriptor(plan)
        try:
            candidate = self._driver.construct(descriptor, seed=self._seed)
        except Exception:
            return _failure(
                snapshot,
                _diagnostic(
                    "cyborg-backend.driver.construction-failed",
                    "The CybORG backend could not be constructed.",
                ),
            )

        if self._active is not None and not self._cleanup_handle(self._active):
            self._active_available = False
            if not self._cleanup_handle(candidate):
                self._pending_cleanup.append(candidate)
            return _failure(snapshot, _cleanup_failed_diagnostic())

        self._active = candidate
        self._active_available = True
        return _success(snapshot, reconciliation, self._realization_envelope)

    def _descriptor(self, plan: ProvisioningPlan) -> CyborgScenarioDescriptor:
        resources = tuple(
            copied_resource(
                address=resource.address,
                resource_type=resource.resource_type,
                payload=resource.payload,
                ordering_dependencies=resource.ordering_dependencies,
                refresh_dependencies=resource.refresh_dependencies,
            )
            for resource in sorted(plan.resources.values(), key=lambda item: item.address)
        )
        return CyborgScenarioDescriptor(
            profile_id=self._profile_id,
            source_commit=self._source_commit,
            mapping_version=CYBORG_SCENARIO_MAPPING_VERSION,
            resources=resources,
        )

    def _identity_diagnostics(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> list[Diagnostic]:
        if plan.realization_envelope is None:
            return [
                _diagnostic(
                    "cyborg-backend.realization-envelope.missing",
                    "Provisioning plan is missing realization envelope identity.",
                )
            ]
        if plan.realization_envelope != self._realization_envelope:
            return [
                _diagnostic(
                    "cyborg-backend.realization-envelope.mismatch",
                    "Provisioning plan does not target the configured CybORG realization.",
                )
            ]
        if (
            snapshot.realization_envelope is not None
            and snapshot.realization_envelope != self._realization_envelope
        ) or (snapshot.entries and snapshot.realization_envelope is None):
            return [
                _diagnostic(
                    "cyborg-backend.realization-envelope.baseline-mismatch",
                    "Runtime snapshot does not belong to the configured CybORG realization.",
                )
            ]
        return []

    def _retry_pending_cleanup(self) -> bool:
        pending: list[object] = []
        for handle in self._pending_cleanup:
            if not self._cleanup_handle(handle):
                pending.append(handle)
        self._pending_cleanup = pending
        return not pending

    def _cleanup_handle(self, handle: object) -> bool:
        try:
            return self._driver.cleanup(handle) is True
        except Exception:
            return False


def _resource_diagnostics(
    plan: ProvisioningPlan,
) -> list[Diagnostic]:
    if not _plan_matches_complete_desired_state(plan):
        return [
            _diagnostic(
                "cyborg-backend.plan.inconsistent-projection",
                "Provisioning operations do not match the complete desired RAES resource set.",
            )
        ]
    if any(
        operation.resource_type not in _SUPPORTED_RESOURCE_TYPES for operation in plan.operations
    ):
        return [
            _diagnostic(
                "cyborg-backend.plan.unsupported-resource",
                "The provisioning plan contains a resource CybORG cannot represent.",
            )
        ]
    resources = tuple(
        copied_resource(
            address=resource.address,
            resource_type=resource.resource_type,
            payload=resource.payload,
            ordering_dependencies=resource.ordering_dependencies,
            refresh_dependencies=resource.refresh_dependencies,
        )
        for resource in sorted(plan.resources.values(), key=lambda item: item.address)
    )
    if not resources:
        return []
    issue = validate_scenario_resources(resources)
    if issue is None:
        return []
    return [_diagnostic(issue.code, issue.message)]


def _plan_matches_complete_desired_state(plan: ProvisioningPlan) -> bool:
    active_operations = {
        operation.address: operation
        for operation in plan.operations
        if operation.action is not ChangeAction.DELETE
    }
    if set(active_operations) != set(plan.resources):
        return False
    for address, resource in plan.resources.items():
        operation = active_operations[address]
        if (
            operation.resource_type != resource.resource_type
            or operation.payload != resource.payload
            or operation.ordering_dependencies != resource.ordering_dependencies
            or operation.refresh_dependencies != resource.refresh_dependencies
        ):
            return False
    return all(
        operation.address not in plan.resources
        for operation in plan.operations
        if operation.action is ChangeAction.DELETE
    )


def _reconcile(plan: ProvisioningPlan) -> _Reconciliation:
    action_by_address = {operation.address: operation.action for operation in plan.operations}
    entries = {
        resource.address: SnapshotEntry(
            address=resource.address,
            domain=RuntimeDomain.PROVISIONING,
            resource_type=resource.resource_type,
            payload=copy.deepcopy(resource.payload),
            ordering_dependencies=resource.ordering_dependencies,
            refresh_dependencies=resource.refresh_dependencies,
            status=(
                "unchanged"
                if action_by_address.get(resource.address) is ChangeAction.UNCHANGED
                else "applied"
            ),
        )
        for resource in plan.resources.values()
    }
    changed_addresses = [
        operation.address
        for operation in plan.operations
        if operation.action is not ChangeAction.UNCHANGED
    ]
    return _Reconciliation(
        entries=entries,
        changed_addresses=changed_addresses,
    )


def _success(
    snapshot: RuntimeSnapshot,
    reconciliation: _Reconciliation,
    identity: RealizationEnvelopeIdentityModel,
) -> ApplyResult:
    return ApplyResult(
        success=True,
        snapshot=snapshot.with_entries(
            reconciliation.entries,
            realization_envelope=identity,
        ),
        changed_addresses=reconciliation.changed_addresses,
    )


def _failure(snapshot: RuntimeSnapshot, diagnostic: Diagnostic) -> ApplyResult:
    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[diagnostic],
    )


def _cleanup_failed_diagnostic() -> Diagnostic:
    return _diagnostic(
        "cyborg-backend.driver.cleanup-failed",
        "The CybORG backend could not confirm cleanup of all owned state.",
    )


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain=_DOMAIN,
        address="runtime.cyborg.provisioning",
        message=message,
        severity=Severity.ERROR,
    )


__all__ = ["CyborgProvisioner"]
