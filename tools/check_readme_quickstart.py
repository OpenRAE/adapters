#!/usr/bin/env python3
"""Validate and optionally execute the closed README quickstart contract."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_EXPECTED_INSTALL_ARGV = (
    "python",
    "-m",
    "pip",
    "install",
    "raes-adapters[cyborg]",
)
_EXPECTED_RUN_PREFIX = (
    "raes-adapters",
    "run",
    "--mode",
    "conformance",
    "--suite",
    "pr",
    "--output",
)
_EXPECTED_OUTPUT: dict[str, object] = {
    "disposition": "succeeded",
    "evidence_basis": "hermetic-live",
    "inventory": "inventory.json",
    "mode": "conformance",
    "run_count": 1,
}
_REPORT_PATH = "runs/cyborg-pr-seed-3/conformance/backend-conformance.json"
_MARKERS = {
    "install": "shell",
    "run": "shell",
    "output": "json",
    "artifacts": "text",
}


class ContractError(ValueError):
    """The README quickstart is absent, ambiguous, or unsafe to execute."""


@dataclass(frozen=True)
class QuickstartContract:
    """Closed command, result, and artifact contract extracted from the README."""

    install_argv: tuple[str, ...]
    run_argv: tuple[str, ...]
    expected_output: dict[str, object]
    expected_artifacts: tuple[str, ...]
    output_root: PurePosixPath


def _marked_block(text: str, name: str, language: str) -> str:
    marker = f"<!-- readme-quickstart:{name} -->"
    if text.count(marker) != 1:
        raise ContractError(f"README must contain exactly one {name} quickstart marker")
    pattern = re.compile(
        rf"{re.escape(marker)}[ \t]*\n```{re.escape(language)}[ \t]*\n"
        rf"(?P<body>.*?)\n```",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise ContractError(f"README {name} marker must be followed by one {language} block")
    return match.group("body").strip()


def _single_command(block: str, name: str) -> tuple[str, ...]:
    lines = tuple(line.strip() for line in block.splitlines() if line.strip())
    if len(lines) != 1:
        raise ContractError(f"README {name} block must contain exactly one command")
    try:
        return tuple(shlex.split(lines[0], posix=True))
    except ValueError as error:
        raise ContractError(f"README {name} command is not valid closed argv") from error


def _relative_path(value: str, *, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError(f"README {label} must be a confined relative path")
    return path


def parse_quickstart_contract(text: str) -> QuickstartContract:
    """Parse and validate only the four explicitly marked README blocks."""

    blocks = {name: _marked_block(text, name, language) for name, language in _MARKERS.items()}
    install_argv = _single_command(blocks["install"], "install")
    if install_argv != _EXPECTED_INSTALL_ARGV:
        raise ContractError("README install command is outside the admitted published extra")

    run_argv = _single_command(blocks["run"], "run")
    if len(run_argv) != len(_EXPECTED_RUN_PREFIX) + 1:
        raise ContractError("README run command has an unexpected argument shape")
    if run_argv[: len(_EXPECTED_RUN_PREFIX)] != _EXPECTED_RUN_PREFIX:
        raise ContractError("README run command is outside the admitted conformance route")
    output_root = _relative_path(run_argv[-1], label="output root")
    if len(output_root.parts) != 1:
        raise ContractError("README output root must be one invocation-relative directory")

    try:
        expected_output: Any = json.loads(blocks["output"])
    except json.JSONDecodeError as error:
        raise ContractError("README expected output must be one JSON object") from error
    if expected_output != _EXPECTED_OUTPUT:
        raise ContractError("README expected output does not match the bounded CLI contract")

    artifacts = tuple(line.strip() for line in blocks["artifacts"].splitlines() if line.strip())
    expected_artifacts = (
        f"{output_root.as_posix()}/index.json",
        f"{output_root.as_posix()}/inventory.json",
        f"{output_root.as_posix()}/{_REPORT_PATH}",
    )
    if artifacts != expected_artifacts:
        raise ContractError("README artifact list does not match the conformance bundle")
    for artifact in artifacts:
        _relative_path(artifact, label="artifact")

    return QuickstartContract(
        install_argv=install_argv,
        run_argv=run_argv,
        expected_output=dict(expected_output),
        expected_artifacts=artifacts,
        output_root=output_root,
    )


def load_quickstart_contract(path: Path) -> QuickstartContract:
    """Load the README contract from an explicit path."""

    return parse_quickstart_contract(path.read_text(encoding="utf-8"))


def execute_quickstart(
    contract: QuickstartContract,
    *,
    runner: Path,
    workdir: Path,
) -> None:
    """Execute the admitted command without a shell and verify its exact result."""

    if not runner.is_file():
        raise ContractError("installed quickstart runner is missing")
    workdir.mkdir(parents=True, exist_ok=True)
    output = workdir / contract.output_root.as_posix()
    if output.exists():
        raise ContractError("quickstart output root already exists")

    env = {
        "PATH": f"{runner.parent}{os.pathsep}{os.defpath}",
        "PYTHONPATH": "",
        "PYTHONSAFEPATH": "1",
    }
    completed = subprocess.run(
        [str(runner), *contract.run_argv[1:]],
        cwd=workdir,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise ContractError(f"installed quickstart exited {completed.returncode}")
    if completed.stderr:
        raise ContractError("installed quickstart wrote unexpected stderr")
    try:
        actual_output: Any = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ContractError("installed quickstart did not emit JSON") from error
    if actual_output != contract.expected_output:
        raise ContractError("installed quickstart output differs from README")

    actual_artifacts = tuple(
        sorted(path.relative_to(workdir).as_posix() for path in output.rglob("*") if path.is_file())
    )
    if actual_artifacts != contract.expected_artifacts:
        raise ContractError("installed quickstart artifact tree differs from README")

    inventory_path = output / "inventory.json"
    inventory: Any = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory_paths = tuple(item["path"] for item in inventory["artifacts"])
    if inventory_paths != ("index.json", _REPORT_PATH):
        raise ContractError("installed quickstart inventory does not seal the documented evidence")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", type=Path, required=True)
    parser.add_argument("--runner", type=Path)
    parser.add_argument("--workdir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate statically, and execute when both installed-run arguments are given."""

    args = _parser().parse_args(argv)
    if (args.runner is None) != (args.workdir is None):
        print(
            "README quickstart check: --runner and --workdir are required together", file=sys.stderr
        )
        return 2
    try:
        contract = load_quickstart_contract(args.readme)
        if args.runner is not None and args.workdir is not None:
            execute_quickstart(contract, runner=args.runner, workdir=args.workdir)
    except (ContractError, OSError, KeyError, TypeError) as error:
        print(f"README quickstart check: FAIL: {error}", file=sys.stderr)
        return 1
    print("README quickstart check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
