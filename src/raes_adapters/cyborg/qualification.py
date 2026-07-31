"""Accessors for the selected CybORG/CAGE-2 qualification evidence."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast


def load_qualification() -> dict[str, Any]:
    """Load a fresh copy of the selected CAGE-2 qualification record."""

    resource = files(__package__).joinpath("qualification.json")
    return cast(dict[str, Any], json.loads(resource.read_text(encoding="utf-8")))


def read_compatibility_patch() -> str:
    """Read the qualification-only packaging patch verbatim."""

    resource = files(__package__).joinpath("cage2-wheel-package-data.patch")
    return resource.read_text(encoding="utf-8")


__all__ = ["load_qualification", "read_compatibility_patch"]
