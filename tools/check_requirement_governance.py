#!/usr/bin/env python3
"""Requirement-governance gate for raes-adapters.

Every change must be attributable to a Ground Control requirement UID so the
cross-repo replication program (ADR-069 §8) stays traceable. The UID is read,
in order, from:

1. ``--requirement-uid <UID>``
2. the ``ACES_REQUIREMENT_UID`` environment variable
3. the current git branch name (first ``[A-Z]{3}-[0-9]{3}`` token)

Pass ``--skip-requirement`` for genuinely requirement-free maintenance runs
(the /implement workflow sets this for bug/refactor/dependency work).

Unknown extra flags are tolerated so the same argv can flow through the whole
``verify`` graph.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

UID_RE = re.compile(r"[A-Z]{3}-[0-9]{3}")


def _branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return out.stdout.strip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--requirement-uid", default=None)
    parser.add_argument("--skip-requirement", action="store_true")
    args, _unknown = parser.parse_known_args(argv)

    if args.skip_requirement:
        print("requirement governance: skipped (--skip-requirement)")
        return 0

    candidate = args.requirement_uid or os.environ.get("ACES_REQUIREMENT_UID") or _branch()
    match = UID_RE.search(candidate or "")
    if match:
        print(f"requirement governance: OK (UID {match.group(0)})")
        return 0

    print(
        "requirement governance: FAIL\n"
        "  No requirement UID found. Provide one of:\n"
        "    - a branch containing a UID, e.g. 12-REP-003-cyborg-scenario\n"
        "    - ACES_REQUIREMENT_UID=REP-003\n"
        "    - --requirement-uid REP-003\n"
        "  or pass --skip-requirement for requirement-free maintenance work.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
