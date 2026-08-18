"""Deterministic presentation shell for offline bundle verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from raes_adapters import bundle_verifier

EXIT_VERIFIED = 0
EXIT_USAGE = 2
EXIT_INVALID = 3
EXIT_INTERNAL = 70


class _UsageFailure(Exception):
    """An intentionally detail-free command-line usage failure."""


class _Parser(argparse.ArgumentParser):
    """Argument parser that maps usage errors to the documented exit code."""

    def error(self, message: str) -> NoReturn:
        """Raise a private usage exception without echoing input paths."""

        del message
        raise _UsageFailure


def render_card(card: bundle_verifier.VerificationCard, output_format: str) -> str:
    """Render one deterministic JSON, terminal, or Markdown integrity card."""

    if output_format == "json":
        return json.dumps(card.payload(), sort_keys=True, separators=(",", ":"))
    counts = {
        "entries": card.entries,
        "files": card.files,
        "inventories": card.inventories,
        "unique_bytes": card.unique_bytes,
    }
    if output_format == "markdown":
        return "\n".join(
            (
                "# Bundle integrity card",
                "",
                f"- Status: `{card.status}`",
                f"- Code: `{card.code}`",
                "- Claim: integrity-only",
                f"- Files: {counts['files']}",
                f"- Inventories: {counts['inventories']}",
                f"- Entries: {counts['entries']}",
                f"- Unique bytes: {counts['unique_bytes']}",
                "- Semantic fidelity: not assessed",
                "- Capture completeness: not assessed",
            )
        )
    return "\n".join(
        (
            f"status: {card.status}",
            f"code: {card.code}",
            "claim: integrity-only",
            f"files: {counts['files']}",
            f"inventories: {counts['inventories']}",
            f"entries: {counts['entries']}",
            f"unique-bytes: {counts['unique_bytes']}",
            "semantic-fidelity: not-assessed",
            "capture-completeness: not-assessed",
        )
    )


def _parser() -> _Parser:
    """Build the isolated verifier command-line parser."""

    parser = _Parser(prog="raes-adapters verify-bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "terminal", "markdown"), default="terminal")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the verifier with its stable 0, 2, 3, and 70 exit contract."""

    try:
        args = _parser().parse_args(argv)
        try:
            card = bundle_verifier.verify_bundle(args.bundle)
            result = EXIT_VERIFIED
        except bundle_verifier.BundleInvalid as error:
            card = bundle_verifier.VerificationCard(status="invalid", code=error.code)
            result = EXIT_INVALID
        print(render_card(card, args.format))
        return result
    except _UsageFailure:
        print("verify-bundle.usage.invalid: invalid command line", file=sys.stderr)
        return EXIT_USAGE
    except Exception:
        print("verify-bundle.internal.failure: internal verification failure", file=sys.stderr)
        return EXIT_INTERNAL


__all__ = ["main"]
