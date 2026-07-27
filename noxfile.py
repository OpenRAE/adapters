# ruff: noqa: E402, I001
"""Canonical verification graph for the aces-adapters monorepo.

This repository is a monorepo of *independent* per-simulator adapter projects
(ADR-069 §5). Each adapter under ``packages/`` owns its own ``pyproject.toml``
and ``uv.lock`` and is synced/tested in an isolated environment so that one
simulator's dependency pins cannot constrain another's. Repo-level tooling
(ruff, mypy, the pre-commit hooks, the governance gates) runs from the root
tooling project (``pyproject.toml`` + root ``uv.lock``), which locks tooling
only -- never adapter dependencies.

Sessions:

- ``hygiene``    file-level pre-commit hooks (whitespace, eol, yaml/json, ...)
- ``lint``       ruff format --check + ruff check across the repo
- ``typecheck``  mypy against each adapter's ``src`` in that adapter's env
- ``tests``      pytest + coverage against each adapter in its isolated env
- ``tool-tests`` stdlib unit tests for repository tooling and policy
- ``docs``       strict MkDocs build used by CI and Read the Docs
- ``policy``     requirement-governance, repo-policy, and ADR-immutability gates
- ``verify``     the full graph (test_command / completion_command)
- ``hook-pre-commit`` / ``hook-pre-push`` drive the git hooks
"""

from __future__ import annotations

from pathlib import Path
import sys

import nox

REPO_ROOT = Path(__file__).resolve().parent
PACKAGES_DIR = REPO_ROOT / "packages"
MAX_LARGE_FILE_KB = "500"
COVERAGE_FAIL_UNDER = "80"
PRIVATE_KEY_EXCLUDE = ("tests/",)

nox.options.default_venv_backend = "none"
nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["verify"]


def _adapters() -> list[Path]:
    """Every adapter project: a ``packages/*`` dir with a ``pyproject.toml``."""
    return sorted(p.parent for p in PACKAGES_DIR.glob("*/pyproject.toml"))


def _run(session: nox.Session, *args: str) -> None:
    session.run(*args, external=True)


def _uv_run_root(session: nox.Session, *args: str) -> None:
    """Run a tool from the root tooling env (locked by the root uv.lock)."""
    _run(session, "uv", "run", "--frozen", "--project", str(REPO_ROOT), *args)


def _tracked(session: nox.Session) -> list[str]:
    out = session.run(
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        external=True,
        silent=True,
    )
    return [line.strip() for line in (out or "").splitlines() if line.strip()]


def _is_text(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:8192]
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #
def _hygiene(session: nox.Session, paths: list[str]) -> None:
    files = [p for p in paths if (REPO_ROOT / p).is_file()]
    text = [p for p in files if _is_text(REPO_ROOT / p)]
    yaml = [p for p in text if p.endswith((".yaml", ".yml"))]
    json = [p for p in text if p.endswith(".json")]
    priv = [p for p in files if not p.startswith(PRIVATE_KEY_EXCLUDE)]
    if not files:
        session.log("hygiene: no files selected; skipping")
        return
    if text:
        _uv_run_root(session, "trailing-whitespace-fixer", *text)
        _uv_run_root(session, "end-of-file-fixer", *text)
        _uv_run_root(session, "check-merge-conflict", *text)
    if yaml:
        _uv_run_root(session, "check-yaml", "--unsafe", *yaml)
    if json:
        _uv_run_root(session, "check-json", *json)
    _uv_run_root(session, "check-added-large-files", "--maxkb", MAX_LARGE_FILE_KB, *files)
    if priv:
        _uv_run_root(session, "detect-private-key", *priv)


def _lint(session: nox.Session) -> None:
    _uv_run_root(session, "ruff", "format", "--check", ".")
    _uv_run_root(session, "ruff", "check", ".")


def _typecheck(session: nox.Session) -> None:
    for adapter in _adapters():
        session.log(f"typecheck: {adapter.name}")
        with session.chdir(adapter):
            _run(session, "uv", "sync", "--frozen")
            _run(session, "uv", "run", "--frozen", "mypy", "src")


def _tests(session: nox.Session) -> None:
    for adapter in _adapters():
        session.log(f"tests: {adapter.name}")
        with session.chdir(adapter):
            _run(session, "uv", "sync", "--frozen")
            _run(session, "uv", "run", "--frozen", "coverage", "erase")
            _run(session, "uv", "run", "--frozen", "coverage", "run", "-m", "pytest")
            _run(session, "uv", "run", "--frozen", "coverage", "xml")
            _run(
                session,
                "uv",
                "run",
                "--frozen",
                "coverage",
                "report",
                f"--fail-under={COVERAGE_FAIL_UNDER}",
            )


def _tool_tests(session: nox.Session) -> None:
    _uv_run_root(session, "python", "-m", "unittest", "discover", "-s", "tools/tests")


def _docs(session: nox.Session) -> None:
    site_dir = Path(session.create_tmp()) / "site"
    _uv_run_root(
        session,
        "--group",
        "docs",
        "mkdocs",
        "build",
        "--strict",
        "--site-dir",
        str(site_dir),
    )


def _policy(session: nox.Session, *args: str) -> None:
    # Each gate parses only the flags it recognizes (argparse.parse_known_args),
    # so the same posargs (--base-rev / --staged / --requirement-uid /
    # --skip-requirement) flow through all three harmlessly.
    _uv_run_root(session, "python", "tools/check_repo_policy.py", *args)
    _uv_run_root(session, "python", "tools/check_requirement_governance.py", *args)
    _uv_run_root(session, "python", "tools/check_adr_immutability.py")
    _uv_run_root(session, "python", "tools/check_project_services.py")


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #
@nox.session
def hygiene(session: nox.Session) -> None:
    _hygiene(session, _tracked(session))


@nox.session
def lint(session: nox.Session) -> None:
    _lint(session)


@nox.session
def typecheck(session: nox.Session) -> None:
    _typecheck(session)


@nox.session
def tests(session: nox.Session) -> None:
    _tests(session)


@nox.session(name="tool-tests")
def tool_tests(session: nox.Session) -> None:
    _tool_tests(session)


@nox.session
def docs(session: nox.Session) -> None:
    _docs(session)


@nox.session
def policy(session: nox.Session) -> None:
    _policy(session, *session.posargs)


@nox.session
def verify(session: nox.Session) -> None:
    _hygiene(session, _tracked(session))
    _policy(session, *session.posargs)
    _lint(session)
    _tool_tests(session)
    _typecheck(session)
    _tests(session)
    _docs(session)


@nox.session(name="ci-adapter")
def ci_adapter(session: nox.Session) -> None:
    """Typecheck + test a single adapter in isolation (per-adapter CI matrix).

    Pass the adapter directory name(s) as posargs, e.g.
    ``nox -s ci-adapter -- cyborg_adapter``. With no posargs, runs every
    adapter (useful locally).
    """
    names = [a for a in session.posargs if not a.startswith("-")]
    targets = [PACKAGES_DIR / n for n in names] if names else _adapters()
    for adapter in targets:
        if not (adapter / "pyproject.toml").is_file():
            session.error(f"no adapter project at {adapter}")
        session.log(f"ci-adapter: {adapter.name}")
        with session.chdir(adapter):
            _run(session, "uv", "sync", "--frozen")
            _run(session, "uv", "run", "--frozen", "mypy", "src")
            _run(session, "uv", "run", "--frozen", "coverage", "erase")
            _run(session, "uv", "run", "--frozen", "coverage", "run", "-m", "pytest")
            _run(session, "uv", "run", "--frozen", "coverage", "xml")
            _run(
                session,
                "uv",
                "run",
                "--frozen",
                "coverage",
                "report",
                f"--fail-under={COVERAGE_FAIL_UNDER}",
            )


@nox.session(name="hook-pre-commit")
def hook_pre_commit(session: nox.Session) -> None:
    changed = [a for a in session.posargs if not a.startswith("-")]
    _hygiene(session, changed or _tracked(session))
    _lint(session)
    policy_args = ["--staged"]
    if "--skip-requirement" in session.posargs:
        policy_args.append("--skip-requirement")
    _policy(session, *policy_args)


@nox.session(name="hook-pre-push")
def hook_pre_push(session: nox.Session) -> None:
    _hygiene(session, _tracked(session))
    _policy(session, *session.posargs)
    _lint(session)
    _typecheck(session)
    _tests(session)


if __name__ == "__main__":
    sys.exit("Run via `nox` / `uv tool run --from 'nox[uv]==2026.4.10' nox`.")
