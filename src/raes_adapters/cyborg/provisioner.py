"""Aggregate RAES Provisioner for the selected CybORG/CAGE-2 backend."""

from __future__ import annotations

import copy
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import NamedTuple

from raes_backend_protocols.protocols import Provisioner  # type: ignore[import-untyped]
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

from ._diagnostics import diagnostic_address
from .driver import (
    CyborgDriver,
    _NativeEvaluationContext,
    _NativeEvaluationTurn,
    _NativeTurnResult,
    validate_action_selection,
)
from .scenario import (
    CYBORG_SCENARIO_MAPPING_VERSION,
    CyborgScenarioDescriptor,
    copied_resource,
    translate_scenario,
    validate_scenario_resources,
)

_DOMAIN = "runtime"
_SUPPORTED_RESOURCE_TYPES = frozenset({"network", "node"})


class _Reconciliation(NamedTuple):
    """Portable desired-state entries and addresses changed by one plan."""

    entries: dict[str, SnapshotEntry]
    changed_addresses: list[str]


class CyborgProvisioner(Provisioner):  # type: ignore[misc]
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
        self._active_descriptor: CyborgScenarioDescriptor | None = None
        self._active_hostnames: frozenset[str] = frozenset()
        self._active_host_addresses: dict[str, str] = {}
        self._execution_generation = 0
        self._pending_evaluation: _NativeEvaluationTurn | None = None
        self._committed_evaluation: list[_NativeEvaluationTurn] = []
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
            failure = self._apply_precondition_failure(plan, snapshot)
            if failure is not None:
                return failure
            assert isinstance(plan, ProvisioningPlan)
            reconciliation = _reconcile(plan)
            return self._apply_reconciliation(plan, snapshot, reconciliation)

    def cleanup(self) -> bool:
        """Release all owned and pending native state; repeated calls are safe."""

        with self._lock:
            succeeded = self._retry_pending_cleanup()
            if self._active is not None:
                handle = self._active
                if self._cleanup_handle(handle):
                    self._active = None
                    self._active_available = False
                    self._active_descriptor = None
                    self._active_hostnames = frozenset()
                    self._active_host_addresses = {}
                    self._clear_evaluation()
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
        """Construct the desired backend before retiring the current handle."""

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
        self._active_descriptor = descriptor
        self._active_hostnames = frozenset(translate_scenario(descriptor)["Hosts"])
        self._active_host_addresses = _host_address_map(descriptor)
        self._clear_evaluation()
        return _success(snapshot, reconciliation, self._realization_envelope)

    @contextmanager
    def execution_transaction(self) -> Iterator[None]:
        """Serialize one complete native-and-portable session transition."""

        with self._lock:
            yield

    def configure_execution(self, red_variant: str) -> bool:
        """Reconstruct the private session with one exact admitted red policy."""

        with self._lock:
            candidate = self._execution_candidate(red_variant)
            configured = candidate is not None
            if (
                candidate is not None
                and self._active is not None
                and not self._cleanup_handle(self._active)
            ):
                self._active_available = False
                if not self._cleanup_handle(candidate):
                    self._pending_cleanup.append(candidate)
                configured = False
            elif candidate is not None:
                self._active = candidate
                self._active_available = True
                self._clear_evaluation()
            return configured

    def _execution_candidate(self, red_variant: str) -> object | None:
        """Construct a candidate for one exact admitted red policy."""

        descriptor = self._active_descriptor
        construct = getattr(self._driver, "construct_execution", None)
        if descriptor is None or not callable(construct):
            return None
        try:
            candidate: object = construct(
                descriptor,
                seed=self._seed,
                red_variant=red_variant,
            )
            return candidate
        except Exception:
            return None

    def execute_turn(
        self,
        selection: object,
        *,
        run_id: str,
        episode_id: str,
        action_instance_id: str,
        logical_step: int,
        logical_step_limit: int,
    ) -> object:
        """Execute at most one aggregate native turn under the session lock."""

        with self._lock:
            step = getattr(self._driver, "step", None)
            if (
                self._active is None
                or not self._active_available
                or not callable(step)
                or not validate_action_selection(selection)
            ):
                raise RuntimeError("CybORG execution session is unavailable.")
            try:
                result = step(self._active, selection)
                if not isinstance(result, _NativeTurnResult):
                    raise ValueError
                terminal_cause = None
                if result.source_terminal:
                    terminal_cause = "source-terminal"
                elif logical_step == logical_step_limit:
                    terminal_cause = "logical-step-limit"
                project = getattr(self._driver, "project_evaluation", None)
                if not callable(project):
                    raise ValueError
                evaluation = project(
                    self._active,
                    _NativeEvaluationContext(
                        external_address=selection.action_contract_address,
                        host_addresses=dict(self._active_host_addresses),
                        run_id=run_id,
                        episode_id=episode_id,
                        action_instance_id=action_instance_id,
                        logical_step=logical_step,
                        terminal_cause=terminal_cause,
                    ),
                )
                if not isinstance(evaluation, _NativeEvaluationTurn):
                    raise ValueError
                self._pending_evaluation = evaluation
                self._execution_generation += 1
                return result
            except Exception:
                self._pending_evaluation = None
                self._active_available = False
                raise RuntimeError("CybORG aggregate turn failed.") from None

    def commit_evaluation(self, action_instance_id: str) -> None:
        """Publish only the staged facts belonging to the accepted portable turn."""

        with self._lock:
            pending = self._pending_evaluation
            if pending is not None and pending.action_instance_id == action_instance_id:
                self._committed_evaluation.append(pending)
            self._pending_evaluation = None

    def committed_evaluation(self) -> tuple[_NativeEvaluationTurn, ...]:
        """Return immutable backend-private facts for evaluator projection."""

        with self._lock:
            return tuple(self._committed_evaluation)

    def quarantine_execution(self) -> None:
        """Prevent reuse after an unprojectable post-effect native result."""

        with self._lock:
            self._active_available = False
            self._pending_evaluation = None

    def execution_available(self) -> bool:
        """Report only whether an owned session may safely accept another turn."""

        with self._lock:
            return self._active is not None and self._active_available

    def execution_generation(self) -> int:
        """Return a private monotonic marker for completed effectful calls."""

        with self._lock:
            return self._execution_generation

    def selection_targets_are_realized(self, selection: object) -> bool:
        """Require target-bearing bindings to resolve in the active host closure."""

        with self._lock:
            if not validate_action_selection(selection):
                return False
            arguments = selection.argument_map
            hostname = arguments.get("hostname")
            return hostname is None or hostname in self._active_hostnames

    def reset_execution(self) -> bool:
        """Reset the owned aggregate session exactly once for a coordinated reset."""

        with self._lock:
            reset = getattr(self._driver, "reset", None)
            if self._active is None or not self._active_available or not callable(reset):
                return False
            try:
                succeeded = reset(self._active, seed=self._seed) is True
            except Exception:
                succeeded = False
            if not succeeded:
                self._active_available = False
            else:
                self._clear_evaluation()
            return succeeded

    def _clear_evaluation(self) -> None:
        """Drop pending and episode-scoped evaluation facts."""

        self._pending_evaluation = None
        self._committed_evaluation = []

    def _descriptor(self, plan: ProvisioningPlan) -> CyborgScenarioDescriptor:
        """Copy the complete desired state into a private driver descriptor."""

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
        """Validate plan and baseline realization identities."""

        diagnostic: Diagnostic | None = None
        if plan.realization_envelope is None:
            diagnostic = _diagnostic(
                "cyborg-backend.realization-envelope.missing",
                "Provisioning plan is missing realization envelope identity.",
            )
        elif plan.realization_envelope != self._realization_envelope:
            diagnostic = _diagnostic(
                "cyborg-backend.realization-envelope.mismatch",
                "Provisioning plan does not target the configured CybORG realization.",
            )
        elif (
            snapshot.realization_envelope is not None
            and snapshot.realization_envelope != self._realization_envelope
        ) or (snapshot.entries and snapshot.realization_envelope is None):
            diagnostic = _diagnostic(
                "cyborg-backend.realization-envelope.baseline-mismatch",
                "Runtime snapshot does not belong to the configured CybORG realization.",
            )
        return [] if diagnostic is None else [diagnostic]

    def _retry_pending_cleanup(self) -> bool:
        """Retry every candidate cleanup that previously could not be confirmed."""

        pending: list[object] = []
        for handle in self._pending_cleanup:
            if not self._cleanup_handle(handle):
                pending.append(handle)
        self._pending_cleanup = pending
        return not pending

    def _cleanup_handle(self, handle: object) -> bool:
        """Convert native cleanup exceptions into a bounded failure result."""

        try:
            return self._driver.cleanup(handle) is True
        except Exception:
            return False

    def _apply_precondition_failure(
        self,
        plan: object,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult | None:
        """Return a bounded failure when apply cannot safely begin."""

        failure: ApplyResult | None = None
        if not isinstance(plan, ProvisioningPlan):
            failure = _failure(
                snapshot,
                _diagnostic(
                    "cyborg-backend.invalid-plan",
                    "CybORG provisioner accepts only published RAES provisioning plans.",
                ),
            )
        else:
            diagnostics = [
                *plan.diagnostics,
                *self._identity_diagnostics(plan, snapshot),
                *_resource_diagnostics(plan),
            ]
            if any(item.is_error for item in diagnostics):
                failure = ApplyResult(
                    success=False,
                    snapshot=snapshot,
                    diagnostics=diagnostics,
                )
            elif not self._retry_pending_cleanup():
                failure = _failure(snapshot, _cleanup_failed_diagnostic())
        return failure

    def _apply_reconciliation(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        reconciliation: _Reconciliation,
    ) -> ApplyResult:
        """Route a validated complete-state reconciliation by lifecycle shape."""

        if not reconciliation.changed_addresses:
            return self._apply_unchanged(plan, snapshot, reconciliation)
        if not reconciliation.entries:
            return self._apply_empty(snapshot, reconciliation)
        return self._replace_backend(plan, snapshot, reconciliation)

    def _apply_unchanged(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        reconciliation: _Reconciliation,
    ) -> ApplyResult:
        """Preserve a healthy backend or reconstruct an unavailable realization."""

        if reconciliation.entries and not self._active_available:
            return self._recover_unavailable(plan, snapshot, reconciliation)
        return _success(snapshot, reconciliation, self._realization_envelope)

    def _recover_unavailable(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        reconciliation: _Reconciliation,
    ) -> ApplyResult:
        """Conclude cleanup of an uncertain handle before reconstructing state."""

        if self._active is not None and not self._cleanup_handle(self._active):
            return _failure(snapshot, _cleanup_failed_diagnostic())
        self._active = None
        return self._replace_backend(plan, snapshot, reconciliation)

    def _apply_empty(
        self,
        snapshot: RuntimeSnapshot,
        reconciliation: _Reconciliation,
    ) -> ApplyResult:
        """Clean all native state before publishing an empty desired snapshot."""

        if not self.cleanup():
            return _failure(snapshot, _cleanup_failed_diagnostic())
        return _success(snapshot, reconciliation, self._realization_envelope)


def _host_address_map(descriptor: CyborgScenarioDescriptor) -> dict[str, str]:
    """Map generated native host labels back to admitted node addresses."""

    result: dict[str, str] = {}
    for resource in descriptor.resources:
        if resource.resource_type != "node":
            continue
        name = resource.payload["name"]
        count = resource.payload["count"]
        if not isinstance(name, str) or type(count) is not int or count < 1:
            raise ValueError
        native_names = (name,) if count == 1 else tuple(f"{name}-{index}" for index in range(count))
        result.update(dict.fromkeys(native_names, resource.address))
    return result


def _resource_diagnostics(
    plan: ProvisioningPlan,
) -> list[Diagnostic]:
    """Validate complete projection and backend representability."""

    diagnostic: Diagnostic | None = None
    if not _plan_matches_complete_desired_state(plan):
        diagnostic = _diagnostic(
            "cyborg-backend.plan.inconsistent-projection",
            "Provisioning operations do not match the complete desired RAES resource set.",
        )
    elif any(
        operation.resource_type not in _SUPPORTED_RESOURCE_TYPES for operation in plan.operations
    ):
        diagnostic = _diagnostic(
            "cyborg-backend.plan.unsupported-resource",
            "The provisioning plan contains a resource CybORG cannot represent.",
        )
    else:
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
        issue = validate_scenario_resources(resources) if resources else None
        if issue is not None:
            diagnostic = _diagnostic(issue.code, issue.message)
    return [] if diagnostic is None else [diagnostic]


def _plan_matches_complete_desired_state(plan: ProvisioningPlan) -> bool:
    """Prove operations and resources describe the same complete desired state."""

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
    """Copy a validated plan into a portable runtime snapshot projection."""

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
    """Build a successful apply result from portable reconciliation state."""

    return ApplyResult(
        success=True,
        snapshot=snapshot.with_entries(
            reconciliation.entries,
            realization_envelope=identity,
        ),
        changed_addresses=reconciliation.changed_addresses,
    )


def _failure(snapshot: RuntimeSnapshot, diagnostic: Diagnostic) -> ApplyResult:
    """Build a bounded failed apply result without altering the snapshot."""

    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[diagnostic],
    )


def _cleanup_failed_diagnostic() -> Diagnostic:
    """Return the stable diagnostic for inconclusive native cleanup."""

    return _diagnostic(
        "cyborg-backend.driver.cleanup-failed",
        "The CybORG backend could not confirm cleanup of all owned state.",
    )


def _diagnostic(code: str, message: str) -> Diagnostic:
    """Construct one backend-local bounded error diagnostic."""

    return Diagnostic(
        code=code,
        domain=_DOMAIN,
        address=diagnostic_address("runtime.cyborg.provisioning"),
        message=message,
        severity=Severity.ERROR,
    )


__all__ = ["CyborgProvisioner"]
