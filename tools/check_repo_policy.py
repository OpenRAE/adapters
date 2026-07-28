#!/usr/bin/env python3
"""Repo-structure policy gate for raes-adapters.

Enforces the plan rules in ``.gc/plan-rules.md``:

1. ADRs (authority artifacts) live only under ``docs/decisions/adrs/``.
2. Release Please owns ``CHANGELOG.md`` and the version (ADR-003):
   - the retired towncrier convention stays removed (no ``changelog.d/``,
     no ``towncrier.toml``);
   - ``[project].version`` matches the Release Please manifest (they are bumped
     together, so a mismatch means a feature PR desynced package metadata from
     the release manifest and the tags/artifacts derived from it);
   - ``CHANGELOG.md`` is not hand-edited outside a release — a real release
     updates it together with ``.release-please-manifest.json``.

The changed-file set is resolved from git: ``--staged`` (index),
``--base-rev <rev>`` (diff rev..HEAD), or the working tree (default).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = "CHANGELOG.md"
MANIFEST = ".release-please-manifest.json"
PYPROJECT = "pyproject.toml"


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


def _stray_adrs() -> list[str]:
    stray: list[str] = []
    for path in REPO_ROOT.rglob("adr-*.md"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith(".venv") or "/.venv/" in rel:
            continue
        if not rel.startswith("docs/decisions/adrs/"):
            stray.append(rel)
    return stray


def _retired_changelog_tooling() -> list[str]:
    retired: list[str] = []
    if (REPO_ROOT / "changelog.d").exists():
        retired.append("changelog.d/")
    if (REPO_ROOT / "towncrier.toml").is_file():
        retired.append("towncrier.toml")
    return retired


def _pyproject_version(root: Path) -> str:
    data = tomllib.loads((root / PYPROJECT).read_text(encoding="utf-8"))
    return str(data.get("project", {}).get("version", ""))


def _manifest_version(root: Path) -> str:
    data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    return str(data.get(".", ""))


def version_consistency_failures(pyproject_version: str, manifest_version: str) -> list[str]:
    """``[project].version`` and the Release Please manifest must agree.

    Release Please bumps both together; a change that edits one without the other
    desyncs package metadata from the release manifest and everything derived from
    it (tags, GitHub Release, published artifact).
    """
    if pyproject_version and manifest_version and pyproject_version != manifest_version:
        return [
            f"[project].version ({pyproject_version}) != "
            f'.release-please-manifest.json ".": ({manifest_version}); Release Please '
            "owns both and they must stay in lockstep"
        ]
    return []


def changelog_ownership_failures(changed: list[str]) -> list[str]:
    """``CHANGELOG.md`` is Release-Please-owned; edit it only within a release.

    A real release updates ``CHANGELOG.md`` together with the manifest, so a diff
    that touches ``CHANGELOG.md`` without also touching
    ``.release-please-manifest.json`` is a hand-edit that will desync from — or
    conflict with — Release Please.
    """
    if CHANGELOG in changed and MANIFEST not in changed:
        return [
            "CHANGELOG.md is owned by Release Please; do not hand-edit it — a real "
            "release updates it together with .release-please-manifest.json"
        ]
    return []


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--base-rev", default=None)
    args, _unknown = parser.parse_known_args(argv)

    failures: list[str] = []

    stray = _stray_adrs()
    if stray:
        failures.append("ADRs must live under docs/decisions/adrs/; found: " + ", ".join(stray))

    retired = _retired_changelog_tooling()
    if retired:
        failures.append(
            "Release Please owns CHANGELOG.md (ADR-003); the retired towncrier "
            "convention must stay removed: " + ", ".join(retired)
        )

    failures.extend(
        version_consistency_failures(_pyproject_version(REPO_ROOT), _manifest_version(REPO_ROOT))
    )
    failures.extend(changelog_ownership_failures(_changed(args.staged, args.base_rev)))

    if failures:
        print("repo policy: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("repo policy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
