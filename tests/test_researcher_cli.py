"""Researcher-facing installed command and evidence-output safety."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from importlib import resources, util
from pathlib import Path

import pytest
from raes import parse_sdl
from raes_contracts.contracts import (
    ExperimentRunModel,
    ExperimentStudyModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection

from raes_adapters import cli
from raes_adapters.cyborg.driver import (
    _NativeEvaluationContext,
    _NativeEvaluationTurn,
    _NativeParticipantOccurrence,
    _NativeRewardComponent,
    _NativeTurnResult,
)
from raes_adapters.cyborg.researcher import RunControls, execute_episode

_SDL = """
name: researcher-cage2
nodes:
  user-net: {type: switch}
  user-host: {type: vm, os: linux}
infrastructure:
  user-net:
    properties: {cidr: 10.20.0.0/24, gateway: 10.20.0.1}
  user-host: {count: 1, links: [user-net]}
"""
_PACK_DIGEST = "sha256:99bf6eb0a75bdab8d222689f8c7fadd4594289c255d02c0c904bec734532c752"
_SCENARIO_DIGEST = "sha256:926f13857da070f1ebdc3afbb3193c7c13f4aa9fe324b3eb93e1c2595871abda"
_PACK_VALIDATOR_AVAILABLE = util.find_spec("raes_env_packs") is not None
_EXAMPLE_ROOT = resources.files("raes_adapters.cyborg") / "examples" / "cage2-research"


def _native_run_args(
    output: str, *, mode: str = "smoke", seeds: tuple[int, ...] = (7,)
) -> list[str]:
    args = [
        "run",
        "--mode",
        mode,
        "--pack",
        "cage2-research",
        "--pack-digest",
        _PACK_DIGEST,
        "--scenario",
        "sdl/cage2-research.sdl.yaml",
        "--scenario-digest",
        _SCENARIO_DIGEST,
        "--experiment",
        "experiment/cage2-research.spec.exp.json",
        "--task",
        "experiment/cage2-research.task.exp.json",
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
        "--run-id",
        "research-example",
        "--output",
        output,
    ]
    for seed in seeds:
        args.extend(("--seed", str(seed)))
    return args


def _participant_artifacts() -> tuple[
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantConfigurationResultModel,
]:
    root = resources.files("raes_adapters.cyborg") / "examples" / "cage2-research" / "participant"
    manifest = ParticipantImplementationManifestModel.model_validate_json(
        (root / "cyborg-blue-sleep-policy.manifest.json").read_text(encoding="utf-8")
    )
    selection = ParticipantImplementationSelectionModel.model_validate_json(
        (root / "cyborg-blue-sleep-policy.selection.json").read_text(encoding="utf-8")
    )
    configuration = ParticipantConfigurationResultModel.model_validate_json(
        (root / "cyborg-blue-sleep-policy.configuration.json").read_text(encoding="utf-8")
    )
    return manifest, selection, configuration


def _validate_args() -> list[str]:
    args = _native_run_args("unused", mode="study", seeds=(7, 11))
    args[0] = "validate"
    output_index = args.index("--output")
    del args[output_index : output_index + 2]
    return args


def _copy_and_reseal_pack(tmp_path: Path, relative: str, payload: str) -> tuple[Path, str]:
    from raes_env_packs import derive_pack_content_manifest

    source = resources.files("raes_adapters.cyborg") / "examples" / "cage2-research"
    pack = tmp_path / "hostile-pack"
    shutil.copytree(source, pack)
    (pack / relative).write_text(payload, encoding="utf-8")
    derived = derive_pack_content_manifest(pack)
    (pack / "pack.content-manifest.json").write_text(
        derived.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return pack, derived.set_digest


def _select_pack(args: list[str], pack: Path, digest: str) -> None:
    args[args.index("cage2-research")] = str(pack)
    args[args.index(_PACK_DIGEST)] = digest


@dataclass
class FakeResearchDriver:
    """Private native seam used to prove researcher orchestration."""

    handles: list[object] = field(default_factory=list)
    selections: list[ParticipantValidatedActionSelection] = field(default_factory=list)
    cleanup_calls: int = 0

    def construct(self, descriptor: object, *, seed: int | None) -> object:
        del descriptor, seed
        handle = object()
        self.handles.append(handle)
        return handle

    def construct_execution(
        self,
        descriptor: object,
        *,
        seed: int | None,
        red_variant: str,
    ) -> object:
        del red_variant
        return self.construct(descriptor, seed=seed)

    def reset(self, handle: object, *, seed: int | None) -> bool:
        del seed
        return handle in self.handles

    def step(
        self,
        handle: object,
        selection: ParticipantValidatedActionSelection,
    ) -> _NativeTurnResult:
        assert handle in self.handles
        self.selections.append(selection)
        return _NativeTurnResult(
            external_action_succeeded=True,
            source_terminal=False,
            occurrences=(
                _NativeParticipantOccurrence(
                    "participant.behavior.blue", selection.action_contract_address
                ),
                _NativeParticipantOccurrence(
                    "participant.behavior.green",
                    "participant.action-contract.green-port-scan",
                ),
                _NativeParticipantOccurrence(
                    "participant.behavior.red", "participant.action-contract.sleep"
                ),
            ),
        )

    def project_evaluation(
        self,
        handle: object,
        context: _NativeEvaluationContext,
    ) -> _NativeEvaluationTurn:
        assert handle in self.handles
        return _NativeEvaluationTurn(
            run_id=context.run_id,
            episode_id=context.episode_id,
            action_instance_id=context.action_instance_id,
            logical_step=context.logical_step,
            terminal_cause=context.terminal_cause,
            rewards=(("participant.behavior.blue", -0.1),),
            components=(
                _NativeRewardComponent(
                    "participant.behavior.blue",
                    "provision.node.user-host",
                    "confidentiality",
                    -0.1,
                    "source-ledger:reward-components",
                ),
            ),
        )

    def cleanup(self, handle: object) -> bool:
        self.cleanup_calls += 1
        if handle in self.handles:
            self.handles.remove(handle)
        return True


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

    assert cli.main(["inspect", "--backend", "cyborg-cage2"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["backend"]["name"] == "cyborg-cage2"
    assert payload["backend"]["native_available"] is False
    assert payload["qualification"]["profile_id"] == "cage2-cyborg-2.1-source-26ce1c1"
    assert payload["supported_profiles"]
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
    args[args.index("cage2-research")] = str(pack)
    assert cli.main(args) == cli.EXIT_VALIDATION

    captured = capsys.readouterr()
    assert "researcher.validation.controls-invalid" in captured.err
    assert str(pack) not in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
def test_validate_admits_packaged_example(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(_validate_args()) == 0
    assert json.loads(capsys.readouterr().out) == {
        "disposition": "validated",
        "pack": "admitted",
        "participant": "cyborg-blue-sleep-policy",
        "run_count": 2,
        "scope": "run-admission",
    }


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
@pytest.mark.parametrize(
    ("module", "arguments", "success_marker"),
    (
        (
            "raes_env_packs.content_ci",
            ("--pack", str(_EXAMPLE_ROOT)),
            "ENVIRONMENT-PACK CONTENT CI: PASS",
        ),
        (
            "raes_env_packs.release",
            ("check", "--pack", str(_EXAMPLE_ROOT)),
            "[ok] cage2-research release checks",
        ),
    ),
)
def test_pack_passes_published_validation_and_release_gates(
    module: str,
    arguments: tuple[str, ...],
    success_marker: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter/module and test-owned arguments
        [sys.executable, "-m", module, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert success_marker in result.stdout
    assert "[skip] cage2-research" not in result.stdout


def test_conformance_reserves_output_and_seals_relative_inventory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkey_output = Path("evidence")
    previous = Path.cwd()
    try:
        # The public CLI accepts only invocation-relative output roots.
        import os

        os.chdir(tmp_path)
        assert (
            cli.main(
                [
                    "run",
                    "--mode",
                    "conformance",
                    "--suite",
                    "pr",
                    "--output",
                    monkey_output.as_posix(),
                ]
            )
            == 0
        )
    finally:
        os.chdir(previous)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary == {
        "disposition": "succeeded",
        "evidence_basis": "hermetic-live",
        "inventory": "inventory.json",
        "mode": "conformance",
        "run_count": 1,
    }
    inventory = json.loads((tmp_path / "evidence" / "inventory.json").read_text())
    assert inventory["artifacts"]
    assert all(not Path(item["path"]).is_absolute() for item in inventory["artifacts"])
    assert all(len(item["sha256"]) == 64 for item in inventory["artifacts"])
    assert captured.err == ""


def test_existing_output_is_never_reused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "already-used"
    output.mkdir()
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        result = cli.main(
            ["run", "--mode", "conformance", "--suite", "pr", "--output", output.name]
        )
    finally:
        os.chdir(previous)

    assert result == cli.EXIT_OUTPUT
    captured = capsys.readouterr()
    assert "researcher.output.unavailable" in captured.err
    assert str(output) not in captured.err
    assert captured.out == ""


def test_inventory_failure_uses_artifact_exit_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli, "_seal_inventory", lambda output: (_ for _ in ()).throw(HostileFailure())
    )
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        result = cli.main(["run", "--mode", "conformance", "--suite", "pr", "--output", "unsealed"])
    finally:
        os.chdir(previous)

    assert result == cli.EXIT_ARTIFACT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err.strip() == "researcher.artifact.failure: portable evidence could not be sealed"
    )


def test_unexpected_failure_never_renders_exception_or_traceback(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> dict[str, object]:
        raise HostileFailure()

    monkeypatch.setattr(cli, "cyborg_inspection_payload", fail)

    assert cli.main(["inspect", "--backend", "cyborg-cage2"]) == cli.EXIT_INTERNAL

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "researcher.internal.failure: internal command failure"


def test_usage_errors_use_documented_exit_code_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["run", "--mode", "unknown"]) == cli.EXIT_USAGE

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
        import os

        os.chdir(tmp_path)
        result = cli.main(["run", "--mode", "conformance", "--suite", "pr", "--output", output])
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
        import os

        os.chdir(tmp_path)
        result = cli.main(
            [
                "run",
                "--mode",
                "conformance",
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


def test_native_episode_binds_real_blue_selection_and_retains_raes_evidence() -> None:
    driver = FakeResearchDriver()
    manifest, selection, configuration = _participant_artifacts()
    result = execute_episode(
        parse_sdl(textwrap.dedent(_SDL)),
        RunControls(
            run_id="research-run-1",
            seed=7,
            max_steps=1,
            red_variant="sleep",
            blue_manifest=manifest,
            blue_selection=selection,
            blue_configuration=configuration,
        ),
        driver=driver,
    )

    assert result.completed_steps == 1
    assert result.cleanup_verified
    assert result.evidence_records
    assert result.derived_measures
    # The provisional construction is cleaned when the selected red policy is
    # bound; the selected execution session is cleaned at final teardown.
    assert driver.cleanup_calls == 2
    assert driver.selections[0].action_contract_address == "participant.action-contract.sleep"


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
def test_native_controls_are_admitted_before_output_or_execution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from raes_adapters.cyborg import researcher

    monkeypatch.setattr(cli.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        researcher,
        "execute_episode",
        lambda *args, **kwargs: pytest.fail("execution must follow validation"),
    )
    args = _native_run_args("must-not-exist")
    args[args.index(_PACK_DIGEST)] = "sha256:" + "0" * 64
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert cli.main(args) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
def test_pack_child_escape_is_rejected_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _native_run_args("must-not-exist")
    args[args.index("sdl/cage2-research.sdl.yaml")] = "../../etc/passwd"
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert cli.main(args) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
def test_duplicate_participant_json_key_is_rejected_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative = "participant/cyborg-blue-sleep-policy.selection.json"
    original = resources.files("raes_adapters.cyborg") / "examples" / "cage2-research" / relative
    payload = original.read_text(encoding="utf-8").replace(
        "{", '{\n  "participant_address": "participant.behavior.blue",', 1
    )
    pack, digest = _copy_and_reseal_pack(tmp_path, relative, payload)
    args = _native_run_args("must-not-exist")
    _select_pack(args, pack, digest)
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert cli.main(args) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
def test_tampered_participant_bytes_with_stale_spec_checksum_are_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative = "participant/cyborg-blue-sleep-policy.manifest.json"
    original = resources.files("raes_adapters.cyborg") / "examples" / "cage2-research" / relative
    payload = json.loads(original.read_text(encoding="utf-8"))
    payload["constraints"] = {"tampered": "true"}
    pack, digest = _copy_and_reseal_pack(
        tmp_path, relative, json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    args = _native_run_args("must-not-exist")
    _select_pack(args, pack, digest)
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert cli.main(args) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
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
        import os

        os.chdir(tmp_path)
        assert cli.main(_native_run_args("must-not-exist")) == cli.EXIT_VALIDATION
    finally:
        os.chdir(previous)

    assert not (tmp_path / "must-not-exist").exists()
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
def test_native_output_and_exception_details_are_suppressed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from raes_adapters.cyborg import researcher

    def fail_after_native_output(*args: object, **kwargs: object) -> object:
        del args, kwargs
        print("native secret output")
        import sys

        print("native secret error", file=sys.stderr)
        raise HostileFailure()

    monkeypatch.setattr(cli.util, "find_spec", lambda name: object())
    monkeypatch.setattr(cli, "verify_selected_cyborg_source", lambda: None)
    monkeypatch.setattr(researcher, "execute_episode", fail_after_native_output)
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert cli.main(_native_run_args("failed-evidence")) == cli.EXIT_RUNTIME
    finally:
        os.chdir(previous)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "researcher.runtime.failure: native execution or cleanup failed"
    failure = json.loads((tmp_path / "failed-evidence" / "failure.json").read_text())
    assert failure["code"] == "researcher.runtime.failure"
    assert "native secret" not in json.dumps(failure)


@pytest.mark.skipif(not _PACK_VALIDATOR_AVAILABLE, reason="requires the cyborg extra")
def test_study_run_seals_portable_raes_evidence_and_exact_inventory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from raes_adapters.cyborg import researcher

    def run_with_fake_driver(scenario: object, controls: RunControls) -> object:
        return execute_episode(scenario, controls, driver=FakeResearchDriver())

    monkeypatch.setattr(cli.util, "find_spec", lambda name: object())
    monkeypatch.setattr(cli, "verify_selected_cyborg_source", lambda: None)
    monkeypatch.setattr(researcher, "execute_episode", run_with_fake_driver)
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert cli.main(_native_run_args("evidence", mode="study", seeds=(7, 11))) == 0
    finally:
        os.chdir(previous)

    captured = capsys.readouterr()
    assert json.loads(captured.out)["run_count"] == 2
    output = tmp_path / "evidence"
    inventory = json.loads((output / "inventory.json").read_text())
    paths = {item["path"] for item in inventory["artifacts"]}
    assert {"machine-inventory.json", "provenance.json", "summary.json"} <= paths
    assert "runs/research-example-1/evidence-records.json" in paths
    assert "runs/research-example-2/derived-measures.json" in paths
    assert "runs/research-example-1/run.json" in paths
    assert "study.json" in paths
    ExperimentRunModel.model_validate_json(
        (output / "runs/research-example-1/run.json").read_text()
    )
    ExperimentStudyModel.model_validate_json((output / "study.json").read_text())
    assert not any(Path(path).is_absolute() for path in paths)
    serialized = "\n".join(path.read_text() for path in output.rglob("*.json"))
    assert "RESEARCHER_SECRET_SENTINEL" not in serialized
    assert str(tmp_path) not in serialized
    assert "Traceback" not in serialized
    assert captured.err == ""
