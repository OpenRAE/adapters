"""Shared readers for backend-local qualification evidence.

Each simulator module ships an immutable ``qualification.json`` and
``public-protocol.md`` in its own package tree (ADR-003). This defines the two
per-package readers once so the loader body is not copied into every backend's
``__init__``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib.resources import files
from typing import Any, cast


def backend_evidence_loaders(
    package: str,
) -> tuple[Callable[[], dict[str, Any]], Callable[[], str]]:
    """Build ``(load_qualification, read_public_protocol)`` bound to ``package``."""

    def load_qualification() -> dict[str, Any]:
        """Load a fresh copy of the backend-local qualification record."""
        resource = files(package).joinpath("qualification.json")
        return cast(dict[str, Any], json.loads(resource.read_text(encoding="utf-8")))

    def read_public_protocol() -> str:
        """Read the selected public experiment protocol verbatim."""
        resource = files(package).joinpath("public-protocol.md")
        return resource.read_text(encoding="utf-8")

    return load_qualification, read_public_protocol
