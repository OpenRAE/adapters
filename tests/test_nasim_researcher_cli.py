"""Researcher-facing installed command and evidence-output safety for NASim.

Mirrors the CybORG acceptance suite for the selected ``nasim-tiny`` static
benchmark. Every native episode is driven by an injected fake driver so the
standard ``tests`` job covers the full researcher surface without importing the
real ``nasim`` package (and therefore without requiring the Tk system
libraries). The single autonomous red bruteforce attacker has no red-variant,
no defender, and no second participant.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from importlib import resources, util
from pathlib import Path

import pytest
import raes
from raes_contracts.contracts import (
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)

from raes_adapters import cli
from raes_adapters.nasim import researcher as nasim_researcher
from raes_adapters.nasim.backend import driver as nasim_driver
from raes_adapters.nasim.backend.driver import (
    NasimCleanupReport,
    NasimEvaluation,
    NasimResetReport,
    NasimStep,
)
from raes_adapters.nasim.researcher import RunControls, execute_episode

_PACK_DIGEST = "sha256:4b96181c34eeead6a02f31517a313becdb352899a209046efedc8e2637d1c5f2"
_SCENARIO_DIGEST = "sha256:a826fd8f812a447dd4c8d346179163f4c5274176ca739bc2802756913a195e2d"
_SEED = 20260802
_RUN_ID = "nasim-research-example"
_PACK_VALIDATOR_AVAILABLE = util.find_spec("raes_env_packs") is not None
_EXAMPLE_ROOT = resources.files("raes_adapters.nasim") / "examples" / "nasim-tiny"


def _native_run_args(
    output: str, *, mode: str = "smoke", seeds: tuple[int, ...] = (_SEED,)
) -> list[str]:
    args = [
        "run",
        "--mode",
        mode,
        "--backend",
        "nasim-tiny",
        "--pack",
        "nasim-tiny",
        "--pack-digest",
        _PACK_DIGEST,
        "--scenario",
        "sdl/nasim-tiny.sdl.yaml",
        "--scenario-digest",
        _SCENARIO_DIGEST,
        "--experiment",
        "experiment/nasim-tiny.spec.exp.json",
        "--task",
        "experiment/nasim-tiny.task.exp.json",
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
        "--run-id",
        _RUN_ID,
        "--output",
        output,
    ]
    for seed in seeds:
        args.extend(("--seed", str(seed)))
    return args


def _validate_args() -> list[str]:
    args = _native_run_args("unused", mode="study", seeds=(_SEED,))
    args[0] = "validate"
    output_index = args.index("--output")
    del args[output_index : output_index + 2]
    return args


def _participant_artifacts() -> tuple[
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantConfigurationResultModel,
]:
    root = _EXAMPLE_ROOT / "participant"
    manifest = ParticipantImplementationManifestModel.model_validate_json(
        (root / "nasim-red-bruteforce.manifest.json").read_text(encoding="utf-8")
    )
    selection = ParticipantImplementationSelectionModel.model_validate_json(
        (root / "nasim-red-bruteforce.selection.json").read_text(encoding="utf-8")
    )
    configuration = ParticipantConfigurationResultModel.model_validate_json(
        (root / "nasim-red-bruteforce.configuration.json").read_text(encoding="utf-8")
    )
    return manifest, selection, configuration


def _selected_scenario() -> object:
    return raes.parse_sdl(
        (_EXAMPLE_ROOT / "sdl" / "nasim-tiny.sdl.yaml").read_text(encoding="utf-8")
    )


def _copy_and_reseal_pack(tmp_path: Path, relative: str, payload: str) -> tuple[Path, str]:
    from raes_env_packs import derive_pack_content_manifest

    pack = tmp_path / "hostile-pack"
    shutil.copytree(_EXAMPLE_ROOT, pack)
    (pack / relative).write_text(payload, encoding="utf-8")
    derived = derive_pack_content_manifest(pack)
    (pack / "pack.content-manifest.json").write_text(
        derived.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return pack, derived.set_digest


def _select_pack(args: list[str], pack: Path, digest: str) -> None:
    args[args.index("--pack") + 1] = str(pack)
    args[args.index(_PACK_DIGEST)] = digest


def _bypass_native(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admit the native gate without importing NASim or requiring Tk.

    The backend adapter binds ``verify_selected_nasim_source`` by identity, so
    every step that function resolves dynamically is neutralized at its own
    module seam: the installed-distribution resolution (which would raise when
    NASim is not installed — e.g. under the cyborg-only test env) and the
    byte/Tk pre-import verification. The native-module presence check is
    satisfied without an import. The fake driver stands in for every native
    operation, exactly as the CybORG suite's fake driver does for CybORG. This
    keeps the suite hermetic in the base and cyborg test envs, not only nasim.
    """

    monkeypatch.setattr(cli.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        nasim_driver._source_admission,
        "resolve_selected_distribution",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(nasim_driver, "_verify_pre_import_source", lambda *args, **kwargs: None)


@dataclass
class FakeNasimDriver:
    """Injected NASim seam that retains deliberately private native state.

    A source transition reaches the goal on the first step so the bounded
    episode terminates immediately; the evaluator reads a distinct cumulative
    reward. The private ``native_state`` must never cross into a projection.
    """

    reward: float = 5.0
    construct_calls: int = 0
    reset_calls: list[int | None] = field(default_factory=list)
    step_calls: list[tuple[str, str | None]] = field(default_factory=list)
    evaluate_calls: int = 0
    close_calls: int = 0
    closed: bool = False
    native_state: object = field(
        default_factory=lambda: {
            "flat_action_index": "must-not-cross",
            "flat_observation_vector": "must-not-cross",
            "native_host_state": "must-not-cross",
        }
    )

    def construct(self) -> None:
        self.construct_calls += 1
        self.closed = False

    def reset(self, seed: int | None) -> NasimResetReport:
        self.reset_calls.append(seed)
        self.closed = False
        return NasimResetReport(
            operation_ref=f"driver.reset.{len(self.reset_calls)}",
            applied_streams=("numpy-global-action-success", "gym-environment-reset"),
            unbound_streams=(),
        )

    def step(self, action_kind: str, target_ref: str | None = None) -> NasimStep:
        self.step_calls.append((action_kind, target_ref))
        return NasimStep(
            operation_ref=f"driver.step.{len(self.step_calls)}",
            step_number=len(self.step_calls),
            source_transition=True,
            processed=True,
            terminated=True,
            truncated=False,
            terminal_cause="goal",
        )

    def evaluate(self) -> NasimEvaluation:
        self.evaluate_calls += 1
        return NasimEvaluation(
            step_count=1,
            cumulative_reward=self.reward,
            terminated=True,
            truncated=False,
            terminal_cause="goal",
        )

    def close(self) -> NasimCleanupReport:
        self.close_calls += 1
        already_closed = self.closed
        self.closed = True
        return NasimCleanupReport(
            operation_ref=f"driver.close.{self.close_calls}",
            closed=True,
            verified=True,
            already_closed=already_closed,
        )

    def verify_closed(self) -> bool:
        return self.closed


class HostileFailure(Exception):
    """Fail the test if the command renders an unexpected exception."""

    def __str__(self) -> str:
        raise AssertionError("hostile exception was rendered")

    def __repr__(self) -> str:
        raise AssertionError("hostile exception was represented")


def test_inspect_reports_installed_identities_without_host_context(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEARCHER_SECRET_SENTINEL", "must-not-appear")

    assert cli.main(["inspect", "--backend", "nasim-tiny"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["backend"]["name"] == "nasim-tiny"
    # Native admission is environment-dependent (Tk plus a byte-verified source);
    # the projection must be a stable boolean regardless of what is installed.
    assert isinstance(payload["backend"]["native_available"], bool)
    assert payload["qualification"]["source_ledger"]
    assert payload["qualification"]["source_commit"]
    assert payload["supported_profiles"]
    assert payload["examples"] == ["nasim-tiny"]
    assert "must-not-appear" not in captured.out
    assert str(Path.cwd()) not in captured.out
    assert captured.err == ""


def test_validate_rejects_invalid_pack_with_bounded_code_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack = tmp_path / "private-pack-name"
    pack.mkdir()

    args = _validate_args()
    args[args.index("--pack") + 1] = str(pack)
    assert cli.main(args) == cli.EXIT_VALIDATION

    captured = capsys.readouterr()
    assert "researcher.validation.controls-invalid" in captured.err
    assert str(pack) not in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_validate_rejects_task_with_unverifiable_semantic_evidence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(_validate_args()) == cli.EXIT_VALIDATION
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "researcher.validation.evidence-unverifiable" in captured.err


def test_existing_output_is_never_reused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "already-used"
    output.mkdir()
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = cli.main(
            [
                "run",
                "--mode",
                "conformance",
                "--backend",
                "nasim-tiny",
                "--suite",
                "pr",
                "--output",
                output.name,
            ]
        )
    finally:
        os.chdir(previous)

    assert result == cli.EXIT_OUTPUT
    captured = capsys.readouterr()
    assert "researcher.output.unavailable" in captured.err
    assert str(output) not in captured.err
    assert captured.out == ""


def test_unexpected_failure_never_renders_exception_or_traceback(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> object:
        raise HostileFailure()

    # The adapter binds ``nasim_inspection_payload`` by identity; force its
    # internal manifest construction to fail so the whole payload raises.
    monkeypatch.setattr(nasim_researcher, "create_nasim_manifest", fail)

    assert cli.main(["inspect", "--backend", "nasim-tiny"]) == cli.EXIT_INTERNAL

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "researcher.internal.failure: internal command failure"


def test_usage_errors_use_documented_exit_code_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["run", "--mode", "unknown", "--backend", "nasim-tiny"]) == cli.EXIT_USAGE

    captured = capsys.readouterr()
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("output", ("../escape", "/tmp/absolute-escape"))
def test_output_path_escape_is_rejected_by_closed_usage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output: str,
) -> None:
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = cli.main(
            [
                "run",
                "--mode",
                "conformance",
                "--backend",
                "nasim-tiny",
                "--suite",
                "pr",
                "--output",
                output,
            ]
        )
    finally:
        os.chdir(previous)

    assert result == cli.EXIT_USAGE
    assert not (tmp_path.parent / "escape").exists()
    assert "researcher.usage.invalid" in capsys.readouterr().err


def test_resolved_output_symlink_escape_is_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = cli.main(
            [
                "run",
                "--mode",
                "conformance",
                "--backend",
                "nasim-tiny",
                "--suite",
                "pr",
                "--output",
                "linked/evidence",
            ]
        )
    finally:
        os.chdir(previous)

    assert result == cli.EXIT_OUTPUT
    assert not (outside / "evidence").exists()
    assert "researcher.output.unavailable" in capsys.readouterr().err


def test_native_episode_binds_real_red_selection_and_retains_raes_evidence() -> None:
    driver = FakeNasimDriver()
    manifest, selection, configuration = _participant_artifacts()
    result = execute_episode(
        _selected_scenario(),
        RunControls(
            run_id="research-run-1",
            seed=_SEED,
            max_steps=1000,
            red_manifest=manifest,
            red_selection=selection,
            red_configuration=configuration,
        ),
        driver=driver,
    )

    assert result.completed_steps == 1
    assert result.cleanup_verified
    assert result.evidence_records
    assert result.derived_measures
    # The single admitted red action is the installed service-exploit behavior.
    assert driver.step_calls
    assert driver.step_calls[0][0] == "service-exploit"


def test_partial_startup_failure_still_attempts_verified_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A start that partially allocates the target and then fails must still reach
    # destroy() — the researcher contract always attempts cleanup. Before the fix,
    # _start_runtime ran outside the try/finally, so its failure bypassed cleanup.
    destroy_calls: list[bool] = []

    class _SpyManager(nasim_researcher.RuntimeManager):  # type: ignore[misc, name-defined]
        def destroy(self) -> object:
            destroy_calls.append(True)
            return super().destroy()

    def _fail_start(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("provisioning admission failed")

    monkeypatch.setattr(nasim_researcher, "RuntimeManager", _SpyManager)
    monkeypatch.setattr(nasim_researcher, "_start_runtime", _fail_start)

    manifest, selection, configuration = _participant_artifacts()
    controls = RunControls(
        run_id="partial-start",
        seed=_SEED,
        max_steps=1000,
        red_manifest=manifest,
        red_selection=selection,
        red_configuration=configuration,
    )
    scenario = _selected_scenario()
    driver = FakeNasimDriver()
    with pytest.raises(RuntimeError):
        execute_episode(scenario, controls, driver=driver)  # type: ignore[arg-type]
    assert destroy_calls, "cleanup was not attempted after a partial-start failure"


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_native_controls_are_admitted_before_output_or_execution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        nasim_researcher,
        "execute_episode",
        lambda *args, **kwargs: pytest.fail("execution must follow validation"),
    )
    args = _native_run_args("must-not-exist")
    args[args.index(_PACK_DIGEST)] = "sha256:" + "0" * 64
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert cli.main(args) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_pack_child_escape_is_rejected_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _native_run_args("must-not-exist")
    args[args.index("sdl/nasim-tiny.sdl.yaml")] = "../../etc/passwd"
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert cli.main(args) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_duplicate_participant_json_key_is_rejected_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative = "participant/nasim-red-bruteforce.selection.json"
    original = _EXAMPLE_ROOT / relative
    payload = original.read_text(encoding="utf-8").replace(
        "{", '{\n  "participant_address": "participant.behavior.red",', 1
    )
    pack, digest = _copy_and_reseal_pack(tmp_path, relative, payload)
    args = _native_run_args("must-not-exist")
    _select_pack(args, pack, digest)
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert cli.main(args) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_tampered_participant_bytes_with_stale_spec_checksum_are_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative = "participant/nasim-red-bruteforce.manifest.json"
    original = _EXAMPLE_ROOT / relative
    payload = json.loads(original.read_text(encoding="utf-8"))
    payload["constraints"] = {"tampered": "true"}
    pack, digest = _copy_and_reseal_pack(
        tmp_path, relative, json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    args = _native_run_args("must-not-exist")
    _select_pack(args, pack, digest)
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert cli.main(args) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_participant_artifact_mismatch_is_rejected_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cli._strict_json

    def mismatched_selection(path: Path) -> object:
        payload = original(path)
        if path.name.endswith(".selection.json"):
            assert isinstance(payload, dict)
            payload["manifest_digest"] = "sha256:" + "0" * 64
        return payload

    monkeypatch.setattr(cli, "_strict_json", mismatched_selection)
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert cli.main(_native_run_args("must-not-exist")) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_native_output_and_exception_details_are_suppressed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_after_native_output(*args: object, **kwargs: object) -> object:
        del args, kwargs
        print("native secret output")
        print("native secret error", file=sys.stderr)
        raise HostileFailure()

    monkeypatch.setattr(nasim_researcher, "execute_episode", fail_after_native_output)
    output = tmp_path / "failed-evidence"
    output.mkdir()
    adapter = cli._BACKENDS["nasim-tiny"]
    with pytest.raises(cli._CommandFailure) as failure:
        cli._execute_quietly(adapter, object(), object(), output)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert failure.value.exit_code == cli.EXIT_RUNTIME
    retained = json.loads((output / "failure.json").read_text())
    assert retained["code"] == "researcher.runtime.failure"
    assert "native secret" not in json.dumps(retained)


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_capture_admission_preempts_execution_and_inventory_writes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        nasim_researcher,
        "execute_episode",
        lambda *args, **kwargs: pytest.fail("execution must not start"),
    )
    monkeypatch.setattr(
        cli,
        "_seal_inventory",
        lambda output: pytest.fail("inventory must not be written"),
    )
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = cli.main(_native_run_args("unsealed", mode="study", seeds=(_SEED,)))
    finally:
        os.chdir(previous)

    assert result == cli.EXIT_VALIDATION
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "researcher.validation.evidence-unverifiable" in captured.err
    assert not (tmp_path / "unsealed").exists()


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the nasim extra")
def test_study_run_rejects_unverifiable_evidence_before_execution_or_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_execution(scenario: object, controls: object) -> object:
        del scenario, controls
        pytest.fail("unverifiable evidence must be rejected before execution")

    monkeypatch.setattr(cli.util, "find_spec", lambda name: object())
    monkeypatch.setattr(nasim_researcher, "execute_episode", reject_execution)
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert (
            cli.main(_native_run_args("evidence", mode="study", seeds=(_SEED,)))
            == cli.EXIT_VALIDATION
        )
    finally:
        os.chdir(previous)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "researcher.validation.evidence-unverifiable" in captured.err
    assert not (tmp_path / "evidence").exists()
