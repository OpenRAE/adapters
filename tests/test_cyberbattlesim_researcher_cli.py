"""Researcher command coverage for the external CyberBattleSim chain pack."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import raes
from raes_contracts.contracts import (
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)

from raes_adapters import cli
from raes_adapters.cyberbattlesim import researcher
from raes_adapters.cyberbattlesim.backend.driver import (
    AutonomousActionProposal,
    DriverCleanupReport,
    DriverEvaluation,
    DriverResetReport,
    DriverStep,
)

pytest.importorskip("raes_env_packs")

PACK_ROOT = Path(__file__).parents[1] / "environments" / "cyberbattlesim-chain"
PACK_DIGEST = "sha256:08ae7e997b50bb396c290c4a5537a65e9e7d8b8e6abc97d1ff65022c4258e417"
SCENARIO_DIGEST = "sha256:9d696ea7fa23a1e7cf4c1cbc145a7989370dc4e9afff2cd5a17d6d1af887b528"
SEED = 20260729


def _args(command: str = "validate", *, output: str = "evidence") -> list[str]:
    args = [
        command,
        "--mode",
        "smoke",
        "--backend",
        "cyberbattlesim-chain",
        "--pack",
        str(PACK_ROOT),
        "--pack-digest",
        PACK_DIGEST,
        "--scenario",
        "sdl/cyberbattlesim-chain.sdl.yaml",
        "--scenario-digest",
        SCENARIO_DIGEST,
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
        str(SEED),
        "--run-id",
        "cyberbattlesim-smoke",
    ]
    if command == "run":
        args.extend(("--output", output))
    return args


def _participant_artifacts() -> tuple[
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantConfigurationResultModel,
]:
    root = PACK_ROOT / "participant"
    return (
        ParticipantImplementationManifestModel.model_validate_json(
            (root / "cyberbattlesim-red-credential-cache.manifest.json").read_text()
        ),
        ParticipantImplementationSelectionModel.model_validate_json(
            (root / "cyberbattlesim-red-credential-cache.selection.json").read_text()
        ),
        ParticipantConfigurationResultModel.model_validate_json(
            (root / "cyberbattlesim-red-credential-cache.configuration.json").read_text()
        ),
    )


@dataclass
class FakeDriver:
    """One-step source seam whose private proposal must pass RAES admission."""

    proposal_epsilons: list[float] = field(default_factory=list)
    step_calls: list[str] = field(default_factory=list)
    reset_calls: list[int | None] = field(default_factory=list)
    close_calls: int = 0
    closed: bool = False

    def construct(self) -> None:
        self.closed = False

    def reset(self, seed: int | None) -> DriverResetReport:
        self.reset_calls.append(seed)
        self.closed = False
        return DriverResetReport(
            operation_ref=f"driver.reset.{len(self.reset_calls)}",
            applied_streams=("gym-environment", "gym-action-space"),
            unbound_streams=("python-random", "numpy-global"),
        )

    def propose_autonomous_action(self, *, epsilon: float) -> AutonomousActionProposal:
        self.proposal_epsilons.append(epsilon)
        return AutonomousActionProposal(
            action_kind="connect",
            target_address="provision.node.customer-data",
            proposal_ref=f"driver.proposal.{len(self.proposal_epsilons)}",
        )

    def step(
        self,
        action_kind: str,
        *,
        target_address: str | None = None,
        proposal_ref: str | None = None,
    ) -> DriverStep:
        assert target_address == "provision.node.customer-data"
        assert proposal_ref == f"driver.proposal.{len(self.proposal_epsilons)}"
        self.step_calls.append(action_kind)
        return DriverStep(
            operation_ref=f"driver.step.{len(self.step_calls)}",
            step_number=len(self.step_calls),
            source_transition=True,
            processed=True,
            terminated=True,
            truncated=False,
            terminal_cause="attacker-ownership",
        )

    def evaluate(self) -> DriverEvaluation:
        return DriverEvaluation(
            step_count=len(self.step_calls),
            cumulative_reward=5000.0,
            terminated=True,
            truncated=False,
            terminal_cause="attacker-ownership",
        )

    def close(self) -> DriverCleanupReport:
        self.close_calls += 1
        already_closed = self.closed
        self.closed = True
        return DriverCleanupReport(
            operation_ref=f"driver.close.{self.close_calls}",
            closed=True,
            verified=True,
            already_closed=already_closed,
        )

    def verify_closed(self) -> bool:
        return self.closed


def test_inspect_reports_external_pack_without_native_import(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["inspect", "--backend", "cyberbattlesim-chain"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["backend"]["name"] == "cyberbattlesim"
    assert isinstance(payload["backend"]["native_available"], bool)
    assert payload["examples"] == ["cyberbattlesim-chain (external release asset)"]


def test_validate_rejects_task_with_unverifiable_semantic_evidence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(_args()) == cli.EXIT_VALIDATION
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "researcher.validation.evidence-unverifiable" in captured.err


def test_validate_rejects_any_resealed_pack_digest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _args()
    args[args.index(PACK_DIGEST)] = "sha256:" + "0" * 64
    assert cli.main(args) == cli.EXIT_VALIDATION
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


def test_bare_example_name_is_not_resolved_as_installed_package_data(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _args()
    args[args.index(str(PACK_ROOT))] = "cyberbattlesim-chain"
    assert cli.main(args) == cli.EXIT_VALIDATION
    assert "researcher.validation.controls-invalid" in capsys.readouterr().err


def test_episode_uses_source_policy_proposal_then_raes_admission() -> None:
    manifest, selection, configuration = _participant_artifacts()
    scenario = raes.parse_sdl_file(PACK_ROOT / "sdl" / "cyberbattlesim-chain.sdl.yaml")
    driver = FakeDriver()
    result = researcher.execute_episode(
        scenario,
        researcher.RunControls(
            run_id="policy-admission",
            seed=SEED,
            max_steps=600,
            red_manifest=manifest,
            red_selection=selection,
            red_configuration=configuration,
        ),
        driver=driver,
    )
    assert result.completed_steps == 1
    assert result.cleanup_verified
    assert result.evidence_records
    assert driver.proposal_epsilons == [0.9]
    assert driver.step_calls == ["connect"]
    assert driver.closed


def test_run_rejects_unverifiable_evidence_before_execution_or_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.util, "find_spec", lambda _name: object())
    adapter = cli._BACKENDS["cyberbattlesim-chain"]
    monkeypatch.setitem(
        cli._BACKENDS,
        "cyberbattlesim-chain",
        cli._BackendAdapter(
            **{
                **adapter.__dict__,
                "verify_source": lambda: None,
            }
        ),
    )

    monkeypatch.setattr(
        researcher,
        "execute_episode",
        lambda *args, **kwargs: pytest.fail("unverifiable evidence must not execute"),
    )
    before = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert cli.main(_args("run")) == cli.EXIT_VALIDATION
    finally:
        os.chdir(before)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "researcher.validation.evidence-unverifiable" in captured.err
    assert not (tmp_path / "evidence").exists()
