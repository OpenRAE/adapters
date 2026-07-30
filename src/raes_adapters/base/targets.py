"""Runtime-target construction over the published RAES registry contract."""

from __future__ import annotations

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_runtime.registry import (  # type: ignore[import-untyped]
    RuntimeTarget,
    RuntimeTargetComponents,
)


def build_runtime_target(
    name: str,
    manifest: BackendManifest,
    components: RuntimeTargetComponents,
) -> RuntimeTarget:
    """Construct a RAES runtime target and delegate every shape check to RAES.

    The helper deliberately does not catch or reinterpret validation failures:
    :class:`raes_runtime.registry.RuntimeTarget` remains the authority for
    manifest/component presence and callable signatures.
    """

    return RuntimeTarget(
        name=name,
        manifest=manifest,
        provisioner=components.provisioner,
        orchestrator=components.orchestrator,
        evaluator=components.evaluator,
        participant_runtime=components.participant_runtime,
        time_runtime=components.time_runtime,
    )


__all__ = ["build_runtime_target"]
