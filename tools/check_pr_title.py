#!/usr/bin/env python3
"""PR title guard for raes-adapters (stdlib only).

Guards against agent-branded PR titles (e.g. ``[codex] ...``) and enforces the
Conventional Commit shape Release Please needs to derive the version and
CHANGELOG (GC-P027 / issue #1399): a single lowercase-subject
``<type>(<scope>)?<!>?: <subject>``. The PR title is untrusted event data, so it
is read from ``$GITHUB_EVENT_PATH`` (never shell-interpolated). When run outside
a pull_request event it is a no-op, so it is safe to run locally.
"""

from __future__ import annotations

import json
import os
import re
import sys

AGENT_BRANDING = re.compile(
    r"\b(codex|claude|cursor|copilot|chatgpt|gpt-?[0-9])\b|generated with|co-authored-by",
    re.IGNORECASE,
)
LEADING_TAG = re.compile(r"^\s*\[[^\]]+\]")
# Conventional Commit types Release Please understands. Type-to-release behavior
# stays Release Please configuration; this only validates the title shape.
CONVENTIONAL_TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)
CONVENTIONAL = re.compile(
    r"^(?:" + "|".join(CONVENTIONAL_TYPES) + r")(?:\([a-z0-9][a-z0-9._-]*\))?!?: (?P<subject>.+)$"
)
MIN_LEN = 10
MAX_LEN = 100


def _title() -> str | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.isfile(event_path):
        return None
    with open(event_path, encoding="utf-8") as fh:
        event = json.load(fh)
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        return None
    return pr.get("title")


def _validate(title: str) -> list[str]:
    errors: list[str] = []
    stripped = title.strip()
    if len(stripped) < MIN_LEN:
        errors.append(f"title too short (< {MIN_LEN} chars)")
    if len(stripped) > MAX_LEN:
        errors.append(f"title too long (> {MAX_LEN} chars)")
    if AGENT_BRANDING.search(stripped):
        errors.append("title contains agent branding / attribution")
    if LEADING_TAG.match(stripped):
        errors.append("title must not start with a bracketed tag like [codex]")
    match = CONVENTIONAL.match(stripped)
    if match is None:
        errors.append(
            "title must be a Conventional Commit '<type>(<scope>)?: <subject>' "
            f"with type one of: {', '.join(CONVENTIONAL_TYPES)}"
        )
    elif match.group("subject").strip()[:1].isupper():
        errors.append("Conventional Commit subject must not start with a capital letter")
    return errors


def main() -> int:
    title = _title()
    if title is None:
        print("PR title check: no pull_request event; skipping (local no-op).")
        return 0
    errors = _validate(title)
    if errors:
        print("PR title check: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(f"  title was: {title!r}", file=sys.stderr)
        return 1
    print("PR title check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
