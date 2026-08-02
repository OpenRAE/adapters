"""NASim qualification evidence.

This module carries the immutable source qualification and selected public
experiment protocol for issue #32.  It does not implement an adapter, backend
manifest, conformance profile, or RAES semantic model.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast

__all__ = ["load_qualification", "read_public_protocol"]


def load_qualification() -> dict[str, Any]:
    """Load a fresh copy of the backend-local qualification record."""
    resource = files(__package__).joinpath("qualification.json")
    return cast(dict[str, Any], json.loads(resource.read_text(encoding="utf-8")))


def read_public_protocol() -> str:
    """Read the selected public experiment protocol verbatim."""
    resource = files(__package__).joinpath("public-protocol.md")
    return resource.read_text(encoding="utf-8")
