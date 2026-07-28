# ruff: noqa: E402, I001
"""Canonical verification graph for the raes-adapters distribution.

``raes-adapters`` is a single published distribution: shared adapter plumbing
(``raes_adapters.base``) plus one module per simulator backend
(``raes_adapters.cyborg``, ...), with simulator-specific dependencies exposed as
optional extras. One ``pyproject.toml`` + one ``uv.lock`` own the whole tree.

Packaging boundary: RAES owns the contracts an adapter must honor, not this
repo's packaging (RAES ADR-069 as amended, RAESystem/rae#949; ADR-003). A second
simulator with a mutually-incompatible stack is isolated with uv's ``conflicts``
extras declaration in the one lock, not a separate lockfile.

Sessions:

- ``hygiene``    file-level pre-commit hooks (whitespace, eol, yaml/json, ...)
- ``lint``       ruff format --check + ruff check across the repo
- ``typecheck``  mypy against ``src`` in the project env (all extras)
- ``tests``      pytest + coverage against ``tests`` in the project env
- ``tool-tests`` stdlib unit tests for repository tooling and policy
- ``docs``       strict MkDocs build used by CI and Read the Docs
- ``policy``     requirement-governance, repo-policy, and ADR-immutability gates
- ``distributions`` build the wheel/sdist, clean-install it, prove identity
- ``verify``     the full graph (test_command / completion_command)
- ``hook-pre-commit`` / ``hook-pre-push`` drive the git hooks
"""

from __future__ import annotations

from pathlib import Path
import sys
import tomllib

import nox

REPO_ROOT = Path(__file__).resolve().parent
IMPORT_PACKAGE = "raes_adapters"
DISTRIBUTION = "raes-adapters"
MAX_LARGE_FILE_KB = "500"
COVERAGE_FAIL_UNDER = "80"
PRIVATE_KEY_EXCLUDE = ("tests/",)

nox.options.default_venv_backend = "none"
nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["verify"]


def _run(session: nox.Session, *args: str, **kwargs: object) -> None:
    session.run(*args, external=True, **kwargs)


def _uv_run_root(session: nox.Session, *args: str) -> None:
    """Run a tool from the project env (locked by the root uv.lock)."""
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


def _extras() -> list[str]:
    """Optional-dependency extras the distribution declares."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return sorted(data.get("project", {}).get("optional-dependencies", {}))


def _verification_envs() -> list[tuple[list[str], str]]:
    """The base install, then each extra ALONE.

    Simulator extras may carry mutually-incompatible stacks (isolated with uv's
    ``conflicts`` declaration in the one lock), so they are never activated
    together: ``--all-extras`` would make the graph unresolvable the day a
    conflicting simulator lands. Verifying base + each extra separately keeps the
    single project and lockfile while honoring that contract.
    """
    return [([], "base"), *((["--extra", extra], extra) for extra in _extras())]


def _typecheck(session: nox.Session) -> None:
    for sync_args, label in _verification_envs():
        session.log(f"typecheck: {label}")
        _run(session, "uv", "sync", "--frozen", *sync_args)
        _run(session, "uv", "run", "--frozen", "mypy", "src")


def _tests(session: nox.Session) -> None:
    _run(session, "uv", "sync", "--frozen")
    _run(session, "uv", "run", "--frozen", "coverage", "erase")
    for sync_args, label in _verification_envs():
        session.log(f"tests: {label}")
        _run(session, "uv", "sync", "--frozen", *sync_args)
        _run(session, "uv", "run", "--frozen", "coverage", "run", "--parallel-mode", "-m", "pytest")
    _run(session, "uv", "run", "--frozen", "coverage", "combine")
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
    _uv_run_root(session, "python", "tools/check_identity_policy.py")


def _distributions(session: nox.Session) -> None:
    """Build the distribution and prove its artifacts carry only current identity.

    Editable installs resolve through the source tree, so they hide packaging
    defects: a stale import path keeps working because the checkout is on
    ``sys.path``. This builds a wheel and an sdist, installs the wheel into a
    throwaway environment *outside* the checkout with no ``PYTHONPATH``, and
    checks identity there -- in the artifacts and in the installed metadata.
    """
    workdir = Path(session.create_tmp())
    dist = workdir / "dist"

    _run(session, "uv", "build", "--out-dir", str(dist))

    archives = sorted(dist.glob("*.whl")) + sorted(dist.glob("*.tar.gz"))
    if not archives:
        session.error("no distributions were built")
    archive_args: list[str] = []
    for archive in archives:
        archive_args += ["--archive", str(archive)]

    wheels = sorted(dist.glob(f"{IMPORT_PACKAGE}-*.whl"))
    if not wheels:
        session.error(f"no wheel built for {DISTRIBUTION}")

    session.log(f"clean install: {DISTRIBUTION}")
    venv = workdir / "venv"
    _run(session, "uv", "venv", "--quiet", "--clear", str(venv))
    _run(
        session,
        "uv",
        "pip",
        "install",
        "--quiet",
        "--python",
        str(venv),
        "--find-links",
        str(dist),
        str(wheels[0]),
    )

    # Probe from a clean working directory with no PYTHONPATH, so nothing
    # resolves through the checkout.
    _run(
        session,
        str(venv / "bin" / "python"),
        str(REPO_ROOT / "tools" / "probe_installed_identity.py"),
        IMPORT_PACKAGE,
        env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
    )

    site_packages = next(iter((venv / "lib").glob("python3.*/site-packages")))
    _uv_run_root(
        session,
        "python",
        "tools/check_identity_policy.py",
        *archive_args,
        "--site-packages",
        str(site_packages),
        "--distribution",
        IMPORT_PACKAGE,
    )


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
def distributions(session: nox.Session) -> None:
    """Build, clean-install, and identity-check the distribution."""
    _distributions(session)


@nox.session
def verify(session: nox.Session) -> None:
    _hygiene(session, _tracked(session))
    _policy(session, *session.posargs)
    _lint(session)
    _tool_tests(session)
    _typecheck(session)
    _tests(session)
    _distributions(session)
    _docs(session)


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
