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
import shutil
import sys
import tomllib

import nox

REPO_ROOT = Path(__file__).resolve().parent
IMPORT_PACKAGE = "raes_adapters"
DISTRIBUTION = "raes-adapters"
MAX_LARGE_FILE_KB = "500"
COVERAGE_FAIL_UNDER = "80"
PRIVATE_KEY_EXCLUDE = ("tests/",)
CYBERBATTLESIM_CONFORMANCE_PROBE = r"""
import sys
from pathlib import Path

from raes_contracts.contracts import (
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_adapters.cyberbattlesim.backend import (
    DriverCleanupReport,
    DriverEvaluation,
    DriverResetReport,
    DriverStep,
    cyberbattlesim_backend_conformance_payload,
    run_cyberbattlesim_conformance,
)
from raes_adapters.cyberbattlesim.scenario_ledger import validate_all


class Driver:
    def __init__(self):
        self.closed = False
        self.step_count = 0

    def construct(self):
        self.closed = False

    def reset(self, seed):
        self.closed = False
        self.step_count = 0
        return DriverResetReport(
            operation_ref="driver.reset.clean-install",
            applied_streams=("gym-environment", "gym-action-space") if seed is not None else (),
            unbound_streams=("python-random", "numpy-global"),
        )

    def step(self, action_kind):
        self.step_count += 1
        return DriverStep(
            operation_ref=f"driver.step.{self.step_count}",
            step_number=self.step_count,
            source_transition=True,
            processed=True,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def evaluate(self):
        return DriverEvaluation(
            execution_ref="driver.reset.clean-install",
            projection_ref="driver.reset.clean-install.evaluation.1",
            step_count=self.step_count,
            cumulative_reward=0.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def close(self):
        already_closed = self.closed
        self.closed = True
        return DriverCleanupReport(
            operation_ref="driver.close.clean-install",
            closed=True,
            verified=True,
            already_closed=already_closed,
        )

    def verify_closed(self):
        return self.closed


assert validate_all() == []
participant_root = Path(sys.argv[1]) / "participant"
participant_manifest = ParticipantImplementationManifestModel.model_validate_json(
    (participant_root / "cyberbattlesim-red-credential-cache.manifest.json").read_text()
)
participant_selection = ParticipantImplementationSelectionModel.model_validate_json(
    (participant_root / "cyberbattlesim-red-credential-cache.selection.json").read_text()
)
participant_configuration = ParticipantConfigurationResultModel.model_validate_json(
    (participant_root / "cyberbattlesim-red-credential-cache.configuration.json").read_text()
)
report = run_cyberbattlesim_conformance(
    driver=Driver(),
    seed=20260729,
    participant_manifest=participant_manifest,
    participant_selection=participant_selection,
    participant_configuration=participant_configuration,
)
payload = cyberbattlesim_backend_conformance_payload(report)
assert payload["passed"] is True
assert payload["native_conformance"] is False
assert payload["cases"]
"""

NASIM_CONFORMANCE_PROBE = r"""
import json

from raes_adapters.nasim.backend import (
    NasimCleanupReport,
    NasimEvaluation,
    NasimResetReport,
    NasimStep,
    run_nasim_pr_conformance,
)
from raes_adapters.nasim.scenario_ledger import validate_all


class Driver:
    def __init__(self):
        self.closed = False
        self.step_count = 0

    def construct(self):
        self.closed = False

    def reset(self, seed):
        self.closed = False
        self.step_count = 0
        return NasimResetReport(
            operation_ref="driver.reset.clean-install",
            applied_streams=(
                ("numpy-global-action-success", "gym-environment-reset") if seed is not None else ()
            ),
            unbound_streams=(
                () if seed is not None else ("numpy-global-action-success", "gym-environment-reset")
            ),
        )

    def step(self, action_kind, target_ref=None):
        self.step_count += 1
        return NasimStep(
            operation_ref=f"driver.step.{self.step_count}",
            step_number=self.step_count,
            source_transition=True,
            processed=True,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def evaluate(self):
        return NasimEvaluation(
            execution_ref="driver.reset.clean-install",
            projection_ref="driver.reset.clean-install.evaluation.1",
            step_count=self.step_count,
            cumulative_reward=0.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def close(self):
        already_closed = self.closed
        self.closed = True
        return NasimCleanupReport(
            operation_ref="driver.close.clean-install",
            closed=True,
            verified=True,
            already_closed=already_closed,
        )

    def verify_closed(self):
        return self.closed


# Compose the PR conformance evidence bundle from the installed wheel: the
# published report projection (which drives this injected driver through the
# constructed target's four surfaces on the published fixtures), source-protocol
# diagnostics, fail-closed capability evidence, and declared weaknesses. The
# hostile-failure / leakage probes are injected-driver test constructs and live
# in the PR test suite, not this happy-path installed-package proof.
assert validate_all() == []
bundle = run_nasim_pr_conformance(driver=Driver())
assert bundle["native_conformance"] is False
assert bundle["backend_conformance"]["passed"] is True
assert bundle["backend_conformance"]["cases"]
assert bundle["source_diagnostics"]
assert bundle["capability_evidence"]
assert bundle["declared_weaknesses"]
# Serializable to the portable JSON the evidence bundle claims to be.
json.dumps(bundle, sort_keys=True)
"""
CYBORG_CONFORMANCE_PROBE = r"""
import json
import sys
from pathlib import Path

from raes_adapters.cyborg import run_cyborg_conformance_suite

index = run_cyborg_conformance_suite(
    suite="pr",
    output_dir=Path(sys.argv[1]),
)
assert index["seeds"] == [3]
assert "passed" not in index
assert index["reports"]
assert index["adapter_diagnostics"]
assert index["adapter_diagnostics"][0]["seed"] == 3
assert all(report["native_conformance"] is False for report in index["reports"])
assert (Path(sys.argv[1]) / "index.json").is_file()
json.dumps(index, sort_keys=True)
"""
PRIMAITE_CONFORMANCE_PROBE = r"""
import json

from raes_adapters.primaite.backend import (
    DriverCleanupReport,
    DriverEvaluation,
    DriverResetReport,
    DriverStep,
    run_primaite_pr_conformance,
)
from raes_adapters.primaite.scenario_ledger import validate_all


class Driver:
    def __init__(self):
        self.closed = False
        self.step_count = 0

    def construct(self):
        self.closed = False

    def reset(self, seed):
        self.closed = False
        self.step_count = 0
        return DriverResetReport(
            operation_ref="driver.reset.clean-install",
            applied_streams=(),
            broken_streams=(
                ("gym-reset-seam", "python-random") if seed is not None else ("gym-reset-seam",)
            ),
            absent_streams=("torch",),
            unbound_streams=("numpy-global",),
        )

    def step(self, action_contract):
        self.step_count += 1
        return DriverStep(
            operation_ref=f"driver.step.{self.step_count}",
            step_number=0,
            representable=False,
            source_transition=False,
            processed=False,
            terminated=False,
            truncated=False,
            terminal_cause=None,
            rejection_reason="unrepresentable-action",
        )

    def evaluate(self):
        return DriverEvaluation(
            execution_ref="driver.reset.clean-install",
            projection_ref="driver.reset.clean-install.evaluation.1",
            step_count=self.step_count,
            cumulative_reward=0.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def close(self):
        already_closed = self.closed
        self.closed = True
        return DriverCleanupReport(
            operation_ref="driver.close.clean-install",
            closed=True,
            verified=True,
            already_closed=already_closed,
            workspace_removed=True,
        )

    def verify_closed(self):
        return self.closed


# Compose the PR conformance disclosure bundle from the installed wheel. PrimAITE
# is fail-closed: the live driver is non-runnable in-process, so an injected
# driver keeps native_conformance false, the canonical report keeps its single
# published no-witness case, capability evidence stays empty, and every
# affirmative capability is disclosed as a gap rather than certified.
assert validate_all() == []
bundle = run_primaite_pr_conformance(driver=Driver())
assert bundle["native_conformance"] is False
assert bundle["backend_conformance"]["native_conformance"] is False
assert bundle["backend_conformance"]["cases"]
assert bundle["source_diagnostics"]
assert bundle["capability_evidence"] == {}
assert bundle["capability_gaps"]
assert bundle["declared_weaknesses"]
# Serializable to the portable JSON the evidence bundle claims to be.
json.dumps(bundle, sort_keys=True)
"""

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
        if label == "cyborg":
            _uv_run_root(session, "python", "tools/verify_cyborg_qualification.py")
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
    workdir = Path(session.create_tmp()).resolve()
    dist = workdir / "dist"
    if dist.exists():
        shutil.rmtree(dist)

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
    probe_cwd = workdir / "probe-cwd"
    if probe_cwd.exists():
        shutil.rmtree(probe_cwd)
    probe_cwd.mkdir()
    with session.chdir(probe_cwd):
        _run(
            session,
            str(venv / "bin" / "python"),
            str(REPO_ROOT / "tools" / "probe_installed_identity.py"),
            IMPORT_PACKAGE,
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )

    session.log("clean install: cyberbattlesim extra conformance")
    conformance_venv = workdir / "venv-cyberbattlesim"
    _run(session, "uv", "venv", "--quiet", "--clear", str(conformance_venv))
    _run(
        session,
        "uv",
        "pip",
        "install",
        "--quiet",
        "--python",
        str(conformance_venv),
        "--find-links",
        str(dist),
        f"{wheels[0]}[cyberbattlesim]",
    )
    with session.chdir(probe_cwd):
        _run(
            session,
            str(conformance_venv / "bin" / "python"),
            "-I",
            "-c",
            CYBERBATTLESIM_CONFORMANCE_PROBE,
            str(REPO_ROOT / "environments" / "cyberbattlesim-chain"),
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(conformance_venv / "bin" / "raes-adapters"),
            "inspect",
            "--backend",
            "cyberbattlesim-chain",
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(conformance_venv / "bin" / "raes-adapters"),
            "validate",
            "--mode",
            "smoke",
            "--backend",
            "cyberbattlesim-chain",
            "--pack",
            str(REPO_ROOT / "environments" / "cyberbattlesim-chain"),
            "--pack-digest",
            "sha256:66493882579d5cba87248c5722782ff5ded5f0d7423f4e559f15bfb61712a905",
            "--scenario",
            "sdl/cyberbattlesim-chain.sdl.yaml",
            "--scenario-digest",
            "sha256:9d696ea7fa23a1e7cf4c1cbc145a7989370dc4e9afff2cd5a17d6d1af887b528",
            "--experiment",
            "experiment/cyberbattlesim-chain.spec.exp.json",
            "--task",
            "experiment/cyberbattlesim-chain.task.exp.json",
            "--participant-implementation",
            "cyberbattlesim-red-credential-cache",
            "--participant-manifest",
            "participant/cyberbattlesim-red-credential-cache.manifest.json",
            "--participant-selection",
            "participant/cyberbattlesim-red-credential-cache.selection.json",
            "--participant-configuration",
            "participant/cyberbattlesim-red-credential-cache.configuration.json",
            "--trial-length",
            "600",
            "--seed",
            "20260729",
            "--run-id",
            "distribution-validation",
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(conformance_venv / "bin" / "raes-pack-validate"),
            "--pack",
            str(REPO_ROOT / "environments" / "cyberbattlesim-chain"),
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(conformance_venv / "bin" / "raes-pack-release"),
            "check",
            "--pack",
            str(REPO_ROOT / "environments" / "cyberbattlesim-chain"),
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )

    session.log("clean install: nasim extra conformance + researcher + pack gates")
    nasim_venv = workdir / "venv-nasim"
    # Pin the qualified runtime's Python. NASim's admitted runtime (numpy 1.26.4)
    # and installed-source admission are qualified for 3.12; on a 3.13 default the
    # native source cannot be verified (native_available false), so the researcher
    # conformance run would fail. CI pins 3.12 (setup-python); pin it here too so
    # the clean-install proof reproduces the qualified environment.
    _run(session, "uv", "venv", "--quiet", "--clear", "--python", "3.12", str(nasim_venv))
    _run(
        session,
        "uv",
        "pip",
        "install",
        "--quiet",
        "--python",
        str(nasim_venv),
        "--find-links",
        str(dist),
        f"{wheels[0]}[nasim]",
    )
    nasim_pack_source = REPO_ROOT / "src" / "raes_adapters" / "nasim" / "examples" / "nasim-tiny"
    with session.chdir(probe_cwd):
        _run(
            session,
            str(nasim_venv / "bin" / "python"),
            "-I",
            "-c",
            NASIM_CONFORMANCE_PROBE,
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(nasim_venv / "bin" / "raes-adapters"),
            "inspect",
            "--backend",
            "nasim-tiny",
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(nasim_venv / "bin" / "raes-adapters"),
            "validate",
            "--backend",
            "nasim-tiny",
            "--mode",
            "study",
            "--pack",
            "nasim-tiny",
            "--pack-digest",
            "sha256:4b96181c34eeead6a02f31517a313becdb352899a209046efedc8e2637d1c5f2",
            "--scenario",
            "sdl/nasim-tiny.sdl.yaml",
            "--scenario-digest",
            "sha256:a826fd8f812a447dd4c8d346179163f4c5274176ca739bc2802756913a195e2d",
            "--task",
            "experiment/nasim-tiny.task.exp.json",
            "--experiment",
            "experiment/nasim-tiny.spec.exp.json",
            "--participant-implementation",
            "nasim-red-bruteforce",
            "--participant-manifest",
            "participant/nasim-red-bruteforce.manifest.json",
            "--participant-selection",
            "participant/nasim-red-bruteforce.selection.json",
            "--participant-configuration",
            "participant/nasim-red-bruteforce.configuration.json",
            "--trial-length",
            "1000",
            "--seed",
            "20260802",
            "--run-id",
            "distribution-validation",
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(nasim_venv / "bin" / "raes-adapters"),
            "run",
            "--backend",
            "nasim-tiny",
            "--mode",
            "conformance",
            "--suite",
            "pr",
            "--output",
            "researcher-conformance-nasim",
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        # The environment-pack content and release gates run over the source pack
        # (always present in the checkout) using the env-packs console scripts the
        # nasim extra now ships.
        _run(
            session,
            str(nasim_venv / "bin" / "raes-pack-validate"),
            "--pack",
            str(nasim_pack_source),
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(nasim_venv / "bin" / "raes-pack-release"),
            "check",
            "--pack",
            str(nasim_pack_source),
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )

    session.log("clean install: cyborg extra conformance")
    cyborg_venv = workdir / "venv-cyborg"
    _run(session, "uv", "venv", "--quiet", "--clear", str(cyborg_venv))
    _run(
        session,
        "uv",
        "pip",
        "install",
        "--quiet",
        "--python",
        str(cyborg_venv),
        "--find-links",
        str(dist),
        f"{wheels[0]}[cyborg]",
    )
    with session.chdir(probe_cwd):
        _run(
            session,
            str(cyborg_venv / "bin" / "python"),
            "-I",
            "-c",
            CYBORG_CONFORMANCE_PROBE,
            str(probe_cwd / "cyborg-conformance"),
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(cyborg_venv / "bin" / "raes-adapters"),
            "inspect",
            "--backend",
            "cyborg-cage2",
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(cyborg_venv / "bin" / "raes-adapters"),
            "validate",
            "--mode",
            "study",
            "--pack",
            "cage2-research",
            "--pack-digest",
            "sha256:72925d81fdc570b7b8bfa884b4b85a642f38f97d2cef8939856933439541deab",
            "--scenario",
            "sdl/cage2-research.sdl.yaml",
            "--scenario-digest",
            "sha256:58aa6b438c38bb53a5d6636e11835e44ebd6e57b48561e48aa80f0f14bfa6bf2",
            "--task",
            "experiment/cage2-research.task.exp.json",
            "--experiment",
            "experiment/cage2-research.spec.exp.json",
            "--red-variant",
            "sleep",
            "--blue-implementation",
            "cyborg-blue-sleep-policy",
            "--blue-manifest",
            "participant/cyborg-blue-sleep-policy.manifest.json",
            "--blue-selection",
            "participant/cyborg-blue-sleep-policy.selection.json",
            "--blue-configuration",
            "participant/cyborg-blue-sleep-policy.configuration.json",
            "--trial-length",
            "2",
            "--seed",
            "7",
            "--seed",
            "11",
            "--run-id",
            "distribution-validation",
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )
        _run(
            session,
            str(cyborg_venv / "bin" / "raes-adapters"),
            "run",
            "--mode",
            "conformance",
            "--suite",
            "pr",
            "--output",
            "researcher-conformance",
            env={"PYTHONPATH": "", "PYTHONSAFEPATH": "1"},
        )

    session.log("clean install: primaite extra conformance")
    primaite_venv = workdir / "venv-primaite"
    _run(session, "uv", "venv", "--quiet", "--clear", str(primaite_venv))
    _run(
        session,
        "uv",
        "pip",
        "install",
        "--quiet",
        "--python",
        str(primaite_venv),
        "--find-links",
        str(dist),
        f"{wheels[0]}[primaite]",
    )
    with session.chdir(probe_cwd):
        _run(
            session,
            str(primaite_venv / "bin" / "python"),
            "-I",
            "-c",
            PRIMAITE_CONFORMANCE_PROBE,
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
