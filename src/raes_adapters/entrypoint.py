"""Lazy command dispatcher preserving offline verifier isolation."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the offline verifier without importing simulator adapters."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["verify-bundle"]:
        from raes_adapters._bundle_command import main as verify_main

        return verify_main(arguments[1:])
    from raes_adapters.cli import main as researcher_main

    return researcher_main(arguments)


__all__ = ["main"]
