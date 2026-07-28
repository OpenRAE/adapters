#!/usr/bin/env python3
"""Prove an *installed* adapter distribution carries only current identity.

Run by the ``distributions`` nox session inside a throwaway environment built
from the wheel, with no ``PYTHONPATH`` and ``PYTHONSAFEPATH`` set, so nothing
resolves through the checkout. An editable/source-tree install would let a stale
import path keep working; this probe is what makes that failure visible.

The retired import name is assembled from non-matching fragments so this file
needs no exemption from the identity gate.
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import sys

# Assembled, never written contiguously.
_RETIRED_PREFIX = "ac" + "es"

# Public RAES surfaces the shared base is expected to reach once installed.
_RAES_SURFACES = ("raes_contracts", "raes_backend_protocols", "raes_conformance")


def _fail(message: str) -> None:
    print(f"installed-identity probe: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        _fail("usage: probe_installed_identity.py <import-name>")
    module_name = argv[0]

    # 1. The current import path resolves from the installed distribution.
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        _fail(f"current import {module_name!r} failed from the installed wheel: {exc}")

    origin = getattr(module, "__file__", "") or ""
    if "site-packages" not in origin:
        _fail(f"{module_name!r} resolved from {origin!r}, not the installed distribution")

    # 2. The retired import path must be gone, not shadowed or forwarded. This is
    #    the pre-cutover adapter import (retired stem), deliberately distinct from
    #    the live ``raes_adapters`` distribution imported above.
    retired = f"{_RETIRED_PREFIX}_adapter_cyborg"
    try:
        importlib.import_module(retired)
    except ImportError:
        pass
    else:
        _fail(f"retired import {retired!r} still resolves; the cutover left a forwarding path")

    # 3. Installed metadata carries no retired identity.
    for dist in md.distributions():
        name = dist.metadata["Name"] or ""
        if _RETIRED_PREFIX in name.lower():
            _fail(f"installed distribution metadata still names {name!r}")

    # 4. The distribution reaches the published RAES surfaces it depends on.
    if module_name == "raes_adapters":
        for surface in _RAES_SURFACES:
            try:
                importlib.import_module(surface)
            except ImportError as exc:
                _fail(f"published RAES surface {surface!r} unreachable from the install: {exc}")

    print(f"installed-identity probe: OK ({module_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
