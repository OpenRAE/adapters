"""The distribution exposes a single version derived from installed metadata."""

from __future__ import annotations

from importlib.metadata import version

import raes_adapters


def test_version_is_derived_from_installed_metadata() -> None:
    # __version__ is not an independently edited authority; it reads back the
    # installed distribution metadata that Release Please bumps in pyproject.toml.
    assert raes_adapters.__version__ == version("raes-adapters")


def test_public_api_is_explicit() -> None:
    assert raes_adapters.__all__ == ["__version__"]
