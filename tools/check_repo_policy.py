#!/usr/bin/env python3
"""Repo-structure policy gate for raes-adapters.

Enforces the plan rules in ``.gc/plan-rules.md``:

1. ADRs (authority artifacts) live only under ``docs/decisions/adrs/``.
2. A user-visible source change under ``packages/*/src/`` must ship a towncrier
   changelog fragment (``changelog.d/<...>.<type>.md``) in the same change.
3. ``CHANGELOG.md`` is not hand-edited outside release-collation commits.

The changed-file set is resolved from git: ``--staged`` (index),
``--base-rev <rev>`` (diff rev..HEAD), or the working tree (default). When no
diff is available (fresh repo / clean tree) the source-triggered checks are
inert; the on-disk structural checks (rule 1) always run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_TYPES = ("security", "added", "changed", "deprecated", "removed", "fixed")


def _git(*args: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def _changed(staged: bool, base_rev: str | None) -> list[str]:
    if staged:
        return _git("diff", "--name-only", "--cached")
    if base_rev:
        return _git("diff", "--name-only", base_rev, "HEAD")
    return _git("diff", "--name-only", "HEAD")


def _is_changelog_fragment(path: str) -> bool:
    p = Path(path)
    return (
        p.parent.name == "changelog.d"
        and len(p.suffixes) >= 2
        and p.suffixes[-2].lstrip(".") in CHANGELOG_TYPES
        and p.suffix == ".md"
    )


def _stray_adrs() -> list[str]:
    stray: list[str] = []
    for path in REPO_ROOT.rglob("adr-*.md"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith((".venv", "packages")) or "/.venv/" in rel:
            continue
        if not rel.startswith("docs/decisions/adrs/"):
            stray.append(rel)
    return stray


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--base-rev", default=None)
    args, _unknown = parser.parse_known_args(argv)

    failures: list[str] = []

    stray = _stray_adrs()
    if stray:
        failures.append("ADRs must live under docs/decisions/adrs/; found: " + ", ".join(stray))

    changed = _changed(args.staged, args.base_rev)
    src_changed = [
        c for c in changed if c.startswith("packages/") and "/src/" in c and c.endswith(".py")
    ]
    has_fragment = any(_is_changelog_fragment(c) for c in changed)
    if src_changed and not has_fragment:
        failures.append(
            "source changed under packages/*/src but no changelog fragment added; "
            "add changelog.d/<issue>.<type>.md (see changelog.d/README.md)"
        )

    if "CHANGELOG.md" in changed and not has_fragment:
        failures.append("CHANGELOG.md must not be hand-edited; add a changelog.d/ fragment instead")

    if failures:
        print("repo policy: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("repo policy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
