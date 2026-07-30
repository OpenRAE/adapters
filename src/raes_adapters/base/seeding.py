"""Ordered driver-local seed application with RAES diagnostic reporting."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentStochasticControlModel,
    RandomStreamControlBindingModel,
)
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    Diagnostic,
    Severity,
    diagnostic_model,
)

SeedApplier = Callable[[RandomStreamControlBindingModel], None]


def _seed_diagnostic(
    *,
    index: int,
    disposition: str,
    message: str,
    severity: Severity,
) -> Diagnostic:
    """Build and validate one published RAES seed diagnostic."""

    diagnostic = Diagnostic(
        code=f"adapter.seed.{disposition}",
        domain="adapter",
        address=f"/stochastic_controls/{index}",
        message=message,
        severity=severity,
    )
    diagnostic_model(diagnostic)
    return diagnostic


def apply_seed_controls(
    controls: Sequence[ExperimentStochasticControlModel],
    appliers: Mapping[str, SeedApplier],
) -> tuple[Diagnostic, ...]:
    """Apply controls in declared order and report every disposition.

    Each applier receives the complete published executable binding, preserving
    its profile, namespace, and public/governed entropy distinction. Governed
    entropy resolution remains inside the authorized driver callback. A
    successful callback means only that the binding was applied; it does not
    claim deterministic replay or outcome equivalence.
    """

    control_ids = [control.control_id for control in controls]
    if len(control_ids) != len(set(control_ids)):
        raise ValueError("Stochastic control ids must be unique.")

    diagnostics: list[Diagnostic] = []
    for index, control in enumerate(controls):
        binding = control.executable_binding
        if binding is None:
            diagnostics.append(
                _seed_diagnostic(
                    index=index,
                    disposition="unbound",
                    message="The stochastic control has no executable binding.",
                    severity=Severity.WARNING,
                )
            )
            continue
        applier = appliers.get(control.control_id)
        if applier is None:
            diagnostics.append(
                _seed_diagnostic(
                    index=index,
                    disposition="unsupported",
                    message="The adapter has no applier for this executable binding.",
                    severity=Severity.WARNING,
                )
            )
            continue
        try:
            applier(binding)
        except Exception:
            diagnostics.append(
                _seed_diagnostic(
                    index=index,
                    disposition="failed",
                    message="The adapter could not apply this executable binding.",
                    severity=Severity.ERROR,
                )
            )
            continue
        diagnostics.append(
            _seed_diagnostic(
                index=index,
                disposition="applied",
                message="The adapter applied this executable binding.",
                severity=Severity.INFO,
            )
        )
    return tuple(diagnostics)


__all__ = ["apply_seed_controls"]
