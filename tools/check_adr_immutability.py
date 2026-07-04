#!/usr/bin/env python3
"""ADR acceptance-content pin gate for aces-adapters (mirrors ACES ADR-059).

An ``accepted`` ADR's content is pinned: its canonical-content sha256 is
recorded in ``docs/decisions/adrs/adr-index.yaml`` and enforced here. A
substantive change to an accepted ADR is legitimate only as a new superseding
ADR, or as a recorded amendment (a ``## Amendments`` row plus an updated pin in
the same change).

Canonical content = the ADR file with its ``## Amendments`` section removed and
each line's trailing whitespace trimmed.

Usage:
    check_adr_immutability.py            # verify pins (CI / verify)
    check_adr_immutability.py --update   # rewrite pins from current content
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "docs" / "decisions" / "adrs" / "adr-index.yaml"


def _canonical(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.strip().lower().startswith("## amendments"):
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if skipping:
            continue
        out.append(line.rstrip())
    return "\n".join(out)


def _pin(path: Path) -> str:
    return hashlib.sha256(_canonical(path.read_text(encoding="utf-8")).encode("utf-8")).hexdigest()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--update", action="store_true")
    args, _unknown = parser.parse_known_args(argv)

    if not INDEX_PATH.exists():
        print(f"ADR immutability: FAIL (missing {INDEX_PATH})", file=sys.stderr)
        return 1

    index = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8")) or {}
    entries = index.get("adrs", [])

    if args.update:
        for entry in entries:
            entry["pin"] = _pin(REPO_ROOT / entry["path"])
        INDEX_PATH.write_text(yaml.safe_dump(index, sort_keys=False), encoding="utf-8")
        print(f"ADR immutability: updated {len(entries)} pin(s)")
        return 0

    failures: list[str] = []
    for entry in entries:
        adr_path = REPO_ROOT / entry["path"]
        if not adr_path.exists():
            failures.append(f"{entry['id']}: file missing ({entry['path']})")
            continue
        actual = _pin(adr_path)
        if actual != entry.get("pin"):
            failures.append(
                f"{entry['id']}: content pin drift\n"
                f"    expected {entry.get('pin')}\n    actual   {actual}\n"
                f"    Add a ## Amendments row + `--update` the pin, or supersede the ADR."
            )
    if failures:
        print("ADR immutability: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"ADR immutability: OK ({len(entries)} pinned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
