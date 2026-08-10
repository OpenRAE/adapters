"""CybORG conformance composition over published RAES contracts."""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from raes import parse_sdl
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_conformance.conformance.target import profile_for_manifest
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.diagnostics import Diagnostic, diagnostic_model, diagnostic_payload
from raes_contracts.participant_episode import ParticipantEpisodeTerminateRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_operations.realization_conformance import write_backend_conformance_report
from raes_runtime.manager import RuntimeManager
from raes_runtime.registry import BackendRegistry

from raes_adapters.cyborg import (
    CYBORG_BACKEND_NAME,
    FULL_CONFORMANCE_SEEDS,
    PR_CONFORMANCE_SEEDS,
    CyborgParticipantRuntime,
    create_cyborg_target,
    cyborg_adapter_diagnostics,
    cyborg_backend_conformance_payload,
    cyborg_conformance_reproduction_commands,
    cyborg_declared_weaknesses,
    cyborg_manifest_capability_evidence,
    cyborg_manifest_capability_evidence_gaps,
    cyborg_source_diagnostics,
    register_cyborg_backend,
    run_cyborg_conformance,
    run_cyborg_conformance_suite,
)
from raes_adapters.cyborg import conformance as conformance_module


@dataclass
class ProbeDriver:
    """Dependency-free driver for hostile failure-path boundary probes."""

    fail_construct: bool = False
    handle: object | None = None

    def construct(self, descriptor: object, *, seed: int | None) -> object:
        del descriptor, seed
        if self.fail_construct:
            raise RuntimeError("native-secret-sentinel /native/path Traceback token=secret")
        self.handle = object()
        return self.handle

    def cleanup(self, handle: object) -> bool:
        assert handle is self.handle
        self.handle = None
        return True


def _probe_plan(target: object) -> object:
    return (
        RuntimeManager(target)
        .plan(
            parse_sdl(
                textwrap.dedent(
                    """
                name: cyborg-failure-probe
                nodes:
                  user-net: {type: switch}
                  user-host: {type: vm, os: linux}
                infrastructure:
                  user-net:
                    properties: {cidr: 10.20.0.0/24, gateway: 10.20.0.1}
                  user-host: {count: 1, links: [user-net]}
                """
                )
            )
        )
        .provisioning
    )


def test_registry_manifest_selects_the_published_full_profile() -> None:
    registry = BackendRegistry()
    register_cyborg_backend(registry)

    manifest = registry.manifest(CYBORG_BACKEND_NAME, seed=3)
    payload = backend_manifest_payload(manifest)
    model = BackendManifestV2Model.model_validate(payload)

    assert model.schema_version == "backend-manifest/v2"
    assert profile_for_manifest(manifest).value == "full-remote-control-plane"
    assert {
        "participant-control-occurrence-v1",
        "participant-crossing-occurrence-v1",
        "participant-lifecycle-event-v1",
        "workflow-history-event-stream-v1",
        "workflow-result-envelope-v1",
    } <= manifest.supported_contract_versions
    assert manifest.realization_envelope is not None


def test_pr_conformance_uses_the_exact_published_report_shape() -> None:
    report = run_cyborg_conformance(seed=PR_CONFORMANCE_SEEDS[0])

    payload = cyborg_backend_conformance_payload(report)

    unsupported = [case for case in report.cases if not case.passed]

    assert report.passed is False
    assert payload["passed"] is False
    assert payload["profile"] == "full-remote-control-plane"
    assert payload["native_conformance"] is False
    assert payload["cases"]
    assert unsupported
    assert len(unsupported) == 1
    assert unsupported[0].name == "realization-envelope-constructive"
    assert unsupported[0].contract_name == "realization-envelope-v1"
    assert {diagnostic.code for diagnostic in unsupported[0].diagnostics} == {
        "realization-envelope.positive-probe.no-witness",
        "realization-envelope.negative-probe.no-witness",
    }
    assert all(case.outcome == "unsupported" for case in unsupported)
    assert all(
        any(diagnostic.code.endswith("no-witness") for diagnostic in case.diagnostics)
        for case in unsupported
    )
    assert all(case.passed for case in report.cases if case not in unsupported)
    assert report.unsupported_contract_gaps == ()
    assert report.unsupported_capability_gaps == ()


def test_every_affirmative_manifest_capability_has_passing_evidence() -> None:
    report = run_cyborg_conformance(seed=3)
    diagnostics = cyborg_source_diagnostics()
    adapter_diagnostics = cyborg_adapter_diagnostics(seed=3)

    evidence = cyborg_manifest_capability_evidence(
        conformance_report=report,
        source_diagnostics=diagnostics,
        adapter_diagnostics=adapter_diagnostics,
    )

    assert evidence
    assert (
        cyborg_manifest_capability_evidence_gaps(
            conformance_report=report,
            source_diagnostics=diagnostics,
            adapter_diagnostics=adapter_diagnostics,
        )
        == ()
    )
    assert all(pointer.startswith("/capabilities/") for pointer in evidence)
    assert all(refs for refs in evidence.values())


def test_adapter_probes_cover_every_runtime_surface_with_valid_diagnostics() -> None:
    diagnostics = cyborg_adapter_diagnostics(seed=3)
    payloads = [diagnostic_payload(diagnostic_model(item)) for item in diagnostics]

    expected_suffixes = {
        "pins.validated",
        "seed-clock.validated",
        "lifecycle.validated",
        "action-observation.validated",
        "reward-evaluation.validated",
        "cleanup.validated",
        "portable-output.validated",
        "scenario2-realization.validated",
    }
    assert {str(item["code"]).removeprefix("cyborg.probe.") for item in payloads} == (
        expected_suffixes
    )
    assert all(item["severity"] == "info" for item in payloads)
    rendered = json.dumps(payloads, sort_keys=True)
    assert "native-secret-sentinel" not in rendered
    assert "traceback" not in rendered.lower()


def test_lifecycle_probe_fails_when_an_earlier_participant_termination_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = CyborgParticipantRuntime.terminate

    def fail_blue_termination(
        self: CyborgParticipantRuntime,
        request: ParticipantEpisodeTerminateRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        if getattr(request, "participant_address", None) == "participant.behavior.blue":
            return ApplyResult(success=False, snapshot=snapshot)
        return original(self, request, snapshot)

    monkeypatch.setattr(CyborgParticipantRuntime, "terminate", fail_blue_termination)

    diagnostics = cyborg_adapter_diagnostics(seed=3)

    lifecycle = next(item for item in diagnostics if ".lifecycle." in item.code)
    assert lifecycle.code == "cyborg.probe.lifecycle.failed"
    assert lifecycle.severity.value == "error"


def test_source_probe_diagnostics_are_valid_json_pointer_payloads() -> None:
    diagnostics = cyborg_source_diagnostics()

    payloads = [diagnostic_payload(diagnostic_model(item)) for item in diagnostics]

    assert payloads
    assert all(str(payload["address"]).startswith("/") for payload in payloads)
    assert not any(payload["code"].endswith("validation-failed") for payload in payloads)


def test_seed_tiers_weaknesses_and_reproduction_commands_are_fixed() -> None:
    assert PR_CONFORMANCE_SEEDS == (3,)
    assert FULL_CONFORMANCE_SEEDS == (3, 153)
    assert any("evaluation-seed" in item for item in cyborg_declared_weaknesses())
    assert cyborg_conformance_reproduction_commands("pr") == (
        (
            "python",
            "-m",
            "raes_adapters.cyborg.conformance",
            "--suite",
            "pr",
            "--output-dir",
            "artifacts/cyborg-conformance",
        ),
    )
    assert cyborg_conformance_reproduction_commands("full")[0][4] == "full"


def test_cli_rejects_output_paths_outside_the_invocation_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invocation = tmp_path / "invocation"
    invocation.mkdir()
    monkeypatch.chdir(invocation)

    with pytest.raises(SystemExit):
        conformance_module.main(["--suite", "pr", "--output-dir", "../outside-conformance"])
    with pytest.raises(ValueError, match="beneath the invocation directory"):
        run_cyborg_conformance_suite(
            suite="pr",
            output_dir=tmp_path / "outside-conformance",
        )

    assert not (tmp_path / "outside-conformance").exists()


def test_canonical_report_writer_persists_the_projected_payload(tmp_path: Path) -> None:
    report = run_cyborg_conformance(seed=3)
    payload = cyborg_backend_conformance_payload(report)

    path = write_backend_conformance_report(
        payload,
        output_dir=tmp_path,
        run_id="cyborg-pr-seed-3",
    )

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted == payload
    assert path.name == "backend-conformance.json"


def test_invalid_component_inputs_emit_valid_raes_diagnostics() -> None:
    target = create_cyborg_target(driver=ProbeDriver())
    snapshot = RuntimeSnapshot()
    assert target.orchestrator is not None
    assert target.evaluator is not None
    assert target.participant_runtime is not None
    results = (
        target.provisioner.apply(object(), snapshot),
        target.orchestrator.start(object(), snapshot),
        target.evaluator.start(object(), snapshot),
        target.participant_runtime.reset(object(), snapshot),
    )

    payloads = [
        diagnostic_payload(diagnostic_model(diagnostic))
        for result in results
        for diagnostic in result.diagnostics
    ]

    assert payloads
    assert all(str(payload["address"]).startswith("/") for payload in payloads)
    assert {payload["domain"] for payload in payloads} == {
        "evaluation",
        "orchestration",
        "participant",
        "runtime",
    }


def test_hostile_construction_failure_never_leaks_to_portable_output() -> None:
    target = create_cyborg_target(driver=ProbeDriver(fail_construct=True))
    result = target.provisioner.apply(_probe_plan(target), RuntimeSnapshot())

    payloads = [diagnostic_payload(diagnostic_model(item)) for item in result.diagnostics]
    rendered = json.dumps(payloads, sort_keys=True)

    assert not result.success
    assert result.snapshot == RuntimeSnapshot()
    assert "native-secret-sentinel" not in rendered
    assert "/native/path" not in rendered
    assert "traceback" not in rendered.lower()
    assert "token=secret" not in rendered


def test_suite_index_preserves_canonical_reports_and_non_claims(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path.parent)
    index = run_cyborg_conformance_suite(suite="pr", output_dir=tmp_path)

    assert index["suite"] == "pr"
    assert index["seeds"] == [3]
    assert "passed" not in index
    assert index["explicit_non_claims"]
    adapter_runs = index["adapter_diagnostics"]
    assert isinstance(adapter_runs, list)
    assert adapter_runs[0]["seed"] == 3
    assert all(
        diagnostic["code"].endswith(".validated") for diagnostic in adapter_runs[0]["diagnostics"]
    )
    reports = index["reports"]
    assert isinstance(reports, list)
    assert len(reports) == 1
    report_path = tmp_path / str(reports[0]["report_path"])
    assert report_path.is_file()
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["profile"] == "full-remote-control-plane"
    assert persisted["native_conformance"] is False
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8")) == index


def test_suite_refuses_failed_adapter_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setattr(
        conformance_module,
        "cyborg_adapter_diagnostics",
        lambda *, seed: (
            Diagnostic(
                code="cyborg.probe.lifecycle.failed",
                domain="conformance",
                address="/cyborg/probes/lifecycle",
                message="The CybORG lifecycle probe failed.",
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="adapter-local conformance probes failed"):
        run_cyborg_conformance_suite(suite="pr", output_dir=tmp_path)

    assert not (tmp_path / "index.json").exists()


def test_suite_refuses_an_unexpected_published_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path.parent)
    report = run_cyborg_conformance(seed=3)
    passing = next(case for case in report.cases if case.passed)
    failed = replace(passing, passed=False, outcome="failed")
    # raes>=3 validates the report before the suite inspects it: every cited case
    # must be present and a passing report may not carry a failed case. Keep the
    # full case set (complete evidence) and mark the report failed so the suite
    # still refuses it for the genuinely-failed published case, not for an
    # upstream-invalid payload.
    unexpected = replace(
        report,
        passed=False,
        cases=tuple(failed if case is passing else case for case in report.cases),
    )
    monkeypatch.setattr(
        conformance_module,
        "run_cyborg_conformance",
        lambda *, seed: unexpected,
    )

    with pytest.raises(RuntimeError, match="published conformance cases failed"):
        run_cyborg_conformance_suite(suite="pr", output_dir=tmp_path)

    assert not (tmp_path / "index.json").exists()


def test_suite_refuses_manifest_capability_evidence_gaps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setattr(
        conformance_module,
        "cyborg_manifest_capability_evidence_gaps",
        lambda *args, **kwargs: ("/capabilities/provisioner/supported_node_types",),
    )

    with pytest.raises(RuntimeError, match="manifest capability evidence is incomplete"):
        run_cyborg_conformance_suite(suite="pr", output_dir=tmp_path)

    assert not (tmp_path / "index.json").exists()
