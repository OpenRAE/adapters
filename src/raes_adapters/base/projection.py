"""Typed, direction-specific projection callables without a simulator model."""

from __future__ import annotations

from collections.abc import Callable


def project_action[PortableActionT, NativeActionT](
    action: PortableActionT,
    projector: Callable[[PortableActionT], NativeActionT],
) -> NativeActionT:
    """Project one admitted portable action into a private native invocation."""

    try:
        return projector(action)
    except Exception:
        pass
    raise ValueError("Action projection failed.")


def project_observation[
    NativeObservationT,
    ObservationCandidateT,
    PortableObservationT,
](
    native_observation: NativeObservationT,
    projector: Callable[[NativeObservationT], ObservationCandidateT],
    validator: Callable[[ObservationCandidateT], PortableObservationT],
) -> PortableObservationT:
    """Project a native result and validate the terminal published RAES value."""

    try:
        candidate = projector(native_observation)
        return validator(candidate)
    except Exception:
        pass
    raise ValueError("Observation projection failed.")


def project_evaluation[
    NativeEvaluationT,
    EvaluationCandidateT,
    PortableEvaluationT,
](
    native_evaluation: NativeEvaluationT,
    projector: Callable[[NativeEvaluationT], EvaluationCandidateT],
    validator: Callable[[EvaluationCandidateT], PortableEvaluationT],
) -> PortableEvaluationT:
    """Project native measures and validate the terminal published RAES value."""

    try:
        candidate = projector(native_evaluation)
        return validator(candidate)
    except Exception:
        pass
    raise ValueError("Evaluation projection failed.")


__all__ = ["project_action", "project_evaluation", "project_observation"]
