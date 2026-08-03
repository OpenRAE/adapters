"""Conformance composition and source-protocol evidence for the NASim backend."""

from __future__ import annotations

from dataclasses import dataclass, field

from raes_backend_protocols.manifest import backend_manifest_payload

from raes_adapters.nasim.backend import (
    NasimCleanupReport,
    NasimEvaluation,
    NasimResetReport,
    NasimStep,
    create_nasim_manifest,
    nasim_backend_conformance_payload,
    nasim_declared_weaknesses,
    nasim_manifest_capability_evidence,
    nasim_manifest_capability_evidence_gaps,
    nasim_source_protocol_diagnostics,
    run_nasim_conformance,
)


@dataclass
class ProbeDriver:
    """Dependency-free driver used to run conformance without the simulator."""

    closed: bool = False
    steps: list[str] = field(default_factory=list)

    def construct(self) -> None:
        self.closed = False

    def reset(self, seed: int | None) -> NasimResetReport:
        self.closed = False
        return NasimResetReport(
            operation_ref="driver.reset.1",
            applied_streams=("numpy-global-action-success",),
            unbound_streams=(),
        )

    def step(self, action_kind: str, target_ref: str | None = None) -> NasimStep:
        self.steps.append(action_kind)
        return NasimStep(
            operation_ref=f"driver.step.{len(self.steps)}",
            step_number=len(self.steps),
            source_transition=True,
            processed=True,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def evaluate(self) -> NasimEvaluation:
        return NasimEvaluation(
            step_count=len(self.steps),
            cumulative_reward=0.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def close(self) -> NasimCleanupReport:
        already_closed = self.closed
        self.closed = True
        return NasimCleanupReport(
            operation_ref="driver.close.1",
            closed=True,
            verified=True,
            already_closed=already_closed,
        )

    def verify_closed(self) -> bool:
        return self.closed


def test_target_passes_conformance_and_serializes_a_report() -> None:
    report = run_nasim_conformance(driver=ProbeDriver(), seed=20260802)

    assert report.passed
    assert report.unsupported_contract_gaps == ()
    payload = nasim_backend_conformance_payload(report)
    assert isinstance(payload, dict)


def test_source_protocol_evidence_validates_and_declares_weaknesses() -> None:
    diagnostics = nasim_source_protocol_diagnostics()
    codes = {diagnostic.code for diagnostic in diagnostics}

    assert "nasim.source-protocol.validation-failed" not in codes
    assert "nasim.source-protocol.validated" in codes
    assert "nasim.source-protocol.declared-weakness" in codes

    weaknesses = nasim_declared_weaknesses()
    # The admitted qualification records real limitations (gymnasium pin,
    # unbound action-success RNG, tkinter import, alpha status).
    assert any(item.startswith("limitation:") for item in weaknesses)


def test_manifest_capability_evidence_tracks_probe_backing() -> None:
    driver = ProbeDriver()
    report = run_nasim_conformance(driver=driver, seed=20260802)
    diagnostics = nasim_source_protocol_diagnostics()
    manifest = create_nasim_manifest()
    payload = backend_manifest_payload(manifest)

    evidence = nasim_manifest_capability_evidence(
        payload=payload,
        conformance_report=report,
        source_diagnostics=diagnostics,
    )
    gaps = nasim_manifest_capability_evidence_gaps(
        payload=payload,
        conformance_report=report,
        source_diagnostics=diagnostics,
    )

    # A passed conformance report plus validated source protocol backs the
    # declared affirmative surfaces, leaving no capability without evidence.
    assert evidence
    assert "/capabilities/provisioner/supported_node_types" in evidence
    assert gaps == ()

    # With no probe evidence at all, every affirmative surface is a gap.
    unbacked = nasim_manifest_capability_evidence(payload=payload)
    assert unbacked == {}
    assert nasim_manifest_capability_evidence_gaps(payload=payload)
