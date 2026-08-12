from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from raes_adapters import cli
from raes_adapters.cyborg import reproduction
from raes_adapters.cyborg.driver import (
    _NativeEvaluationContext,
    _NativeEvaluationTurn,
    _NativeParticipantOccurrence,
    _NativeRewardComponent,
    _NativeTurnResult,
)

PROJECT_ROOT = Path(__file__).parents[1]


class StudyDriver:
    """Bounded native seam for the real scheduler and persistence path."""

    def __init__(self) -> None:
        self.handles: list[object] = []
        self.red_variant = "sleep"
        self.stream = object()

    def begin_ordered_stream(self, seed: int) -> None:
        assert seed == 153

    def ordered_stream_checkpoint(self) -> object:
        return self.stream

    def restore_ordered_stream(self, checkpoint: object) -> None:
        assert checkpoint is self.stream

    def construct(self, descriptor: object, *, seed: int | None) -> object:
        del descriptor
        assert seed is None
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
        self.red_variant = red_variant
        return self.construct(descriptor, seed=seed)

    def reset(self, handle: object, *, seed: int | None) -> bool:
        return handle in self.handles and seed is None

    def step(self, handle: object, selection: object) -> _NativeTurnResult:
        assert handle in self.handles
        red = {
            "b-line": "participant.action-contract.discover-network-services",
            "meander": "participant.action-contract.discover-remote-systems",
            "sleep": "participant.action-contract.sleep",
        }[self.red_variant]
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
                _NativeParticipantOccurrence("participant.behavior.red", red),
            ),
        )

    def project_evaluation(
        self, handle: object, context: _NativeEvaluationContext
    ) -> _NativeEvaluationTurn:
        assert handle in self.handles
        return _NativeEvaluationTurn(
            run_id=context.run_id,
            episode_id=context.episode_id,
            action_instance_id=context.action_instance_id,
            logical_step=context.logical_step,
            terminal_cause=context.terminal_cause,
            rewards=(
                ("participant.behavior.blue", -1.0),
                ("participant.behavior.green", 0.0),
                ("participant.behavior.red", 1.0),
            ),
            components=(
                _NativeRewardComponent(
                    "participant.behavior.blue",
                    "provision.node.op-server-0",
                    "availability",
                    0.0,
                    "source-ledger:reward-components",
                ),
            ),
        )

    def cleanup(self, handle: object) -> bool:
        self.handles.remove(handle)
        return True


class FailingStudyDriver(StudyDriver):
    """Fail after one complete episode so staged evidence must be discarded."""

    def __init__(self) -> None:
        super().__init__()
        self.step_calls = 0

    def step(self, handle: object, selection: object) -> _NativeTurnResult:
        self.step_calls += 1
        if self.step_calls == 31:
            raise RuntimeError("test native failure")
        return super().step(handle, selection)


class ExhaustedRetryStudyDriver(StudyDriver):
    """Exhaust the first condition's retries, then allow later conditions."""

    def __init__(self) -> None:
        super().__init__()
        self.session_count = 0

    def construct_execution(
        self,
        descriptor: object,
        *,
        seed: int | None,
        red_variant: str,
    ) -> object:
        self.session_count += 1
        return super().construct_execution(
            descriptor,
            seed=seed,
            red_variant=red_variant,
        )

    def step(self, handle: object, selection: object) -> _NativeTurnResult:
        if self.session_count <= 2:
            raise RuntimeError("test native failure")
        return super().step(handle, selection)


def _selection(*, episodes: int = 2) -> reproduction.ReproductionSelection:
    return reproduction.FROZEN_SELECTION.with_cardinality_for_test(episodes)


def _valid_attempts(protocol: dict[str, object], *, offset: float = 0.0) -> list[dict[str, object]]:
    declaration = protocol["declaration"]
    assert isinstance(declaration, dict)
    schedule = reproduction.schedule_for_test(protocol)
    return [
        reproduction.attempt_record_for_test(
            protocol,
            slot,
            score=float(index) + offset,
        )
        for index, slot in enumerate(schedule, start=1)
    ]


def test_declaration_freezes_full_matrix_and_separates_source_facts() -> None:
    protocol, source_ledger = reproduction.build_declaration(PROJECT_ROOT, selection=_selection())

    reproduction.validate_protocol(protocol, selection=_selection())
    declaration = protocol["declaration"]
    assert isinstance(declaration, dict)
    schedule = reproduction.schedule_for_test(protocol)
    assert len(schedule) == 18
    assert len({item["slot_id"] for item in schedule}) == 18
    assert len({item["run_id"] for item in schedule}) == 18
    assert {item["trial_length"] for item in schedule} == {30, 50, 100}
    assert {item["red_variant"] for item in schedule} == {
        "b-line",
        "meander",
        "sleep",
    }
    assert declaration["seed_policy"] == {
        "api": "random.seed",
        "initialization_scope": "study",
        "owner": "python-random",
        "reset_behavior": "continue-stream-across-episode-reset",
        "seed": 153,
        "serialization": "trial-length-then-red-variant-then-episode",
    }
    source_facts = source_ledger["protocol_source_facts"]
    assert source_facts["qualified_evaluator"]["episode_count"] == 100
    assert source_facts["public_validation"]["episode_count"] == 1000
    assert source_facts["qualified_evaluator"]["seed_binding"] is None
    assert source_facts["public_validation"]["seed_statement"] == "random.seed(153)"
    assert "schema_version" not in protocol
    assert "schema_version" not in source_ledger


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":"x","schema_version":"y"}',
        '{"value":NaN}',
        '{"value":Infinity}',
    ],
)
def test_strict_json_rejects_duplicates_and_nonfinite_values(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "hostile.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON artifact"):
        reproduction.load_strict_json(path)


def test_protocol_rejects_drift_duplicate_attempts_and_per_episode_seed_scope() -> None:
    selection = _selection()
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT, selection=selection)

    drifted = copy.deepcopy(protocol)
    drifted["declaration"]["seed_policy"]["initialization_scope"] = "episode"
    drifted["declaration_sha256"] = reproduction.sha256_payload(drifted["declaration"])
    with pytest.raises(ValueError, match="seed policy"):
        reproduction.validate_protocol(drifted, selection=selection)

    duplicate = copy.deepcopy(protocol)
    duplicate["declaration"]["schedule_partitions"][1]["first_slot_id"] = duplicate["declaration"][
        "schedule_partitions"
    ][0]["first_slot_id"]
    duplicate["declaration_sha256"] = reproduction.sha256_payload(duplicate["declaration"])
    with pytest.raises(ValueError, match="protocol declaration"):
        reproduction.validate_protocol(duplicate, selection=selection)


def test_aggregation_is_deterministic_and_counts_every_disposition() -> None:
    selection = _selection()
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT, selection=selection)
    attempts = _valid_attempts(protocol)
    attempts[0]["disposition"] = "failed"
    attempts[0]["score_measure"] = None
    attempts[1]["disposition"] = "invalid"
    attempts[1]["score_measure"] = None
    attempts[2]["disposition"] = "excluded"
    attempts[2]["score_measure"] = None

    first = reproduction.compute_aggregates(protocol, attempts)
    second = reproduction.compute_aggregates(protocol, list(reversed(attempts)))

    assert reproduction.canonical_json_bytes(first) == reproduction.canonical_json_bytes(second)
    totals = first["disposition_counts"]
    assert totals == {"excluded": 1, "failed": 1, "invalid": 1, "valid": 15}
    assert "schema_version" not in first
    condition = first["conditions"][0]
    assert condition["eligible_n"] in {0, 1, 2}
    assert math.isfinite(condition["mean"]) if condition["mean"] is not None else True


def test_aggregate_rejects_missing_duplicate_cross_condition_and_nonfinite_scores() -> None:
    selection = _selection()
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT, selection=selection)
    attempts = _valid_attempts(protocol)

    with pytest.raises(ValueError, match="scheduled attempts"):
        reproduction.compute_aggregates(protocol, attempts[:-1])

    duplicated = [*attempts, copy.deepcopy(attempts[0])]
    with pytest.raises(ValueError, match="scheduled attempts"):
        reproduction.compute_aggregates(protocol, duplicated)

    crossed = copy.deepcopy(attempts)
    crossed[0]["condition_id"] = crossed[2]["condition_id"]
    with pytest.raises(ValueError, match="slot join"):
        reproduction.compute_aggregates(protocol, crossed)

    nonfinite = copy.deepcopy(attempts)
    nonfinite[0]["score_measure"]["value"] = float("nan")
    with pytest.raises(ValueError, match="score measure"):
        reproduction.compute_aggregates(protocol, nonfinite)


def test_tiers_keep_subjects_separate_and_do_not_turn_score_into_equivalence() -> None:
    selection = _selection()
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT, selection=selection)
    aggregates = reproduction.compute_aggregates(protocol, _valid_attempts(protocol))
    reference = {
        "authored_source": "pass",
        "contract": "pass",
        "execution_control": "weakened",
        "state_observation": "weakened",
        "outcome_evaluation": "weakened",
        "disclosure": "pass",
        "evidence_refs": ["reference.json"],
    }

    tiers = reproduction.build_tiers(protocol, aggregates, reference)

    assert "passed" not in tiers
    assert "schema_version" not in tiers
    assert [item["tier"] for item in tiers["tiers"]] == [
        "authored-source",
        "contract",
        "execution-control",
        "state/observation",
        "outcome/evaluation",
        "disclosure",
    ]
    assert all(set(item["subjects"]) == {"cyborg", "raes-reference"} for item in tiers["tiers"])
    state = next(item for item in tiers["tiers"] if item["tier"] == "state/observation")
    assert state["subjects"]["raes-reference"]["result"] == "weakened"
    assert tiers["strongest_supported_claim"] != "state-or-semantic-equivalence"
    assert "state" not in tiers["strongest_supported_claim"]

    bounded = copy.deepcopy(aggregates)
    bounded["comparison"]["classification"] = "bounded"
    bounded_tiers = reproduction.build_tiers(protocol, bounded, reference)
    assert bounded_tiers["strongest_supported_claim"] == (
        "behavioral-baseline-outcome-reproduction-without-submitted-agent-or-state-equivalence"
    )
    assert bounded_tiers["research_consumers"]["OpenRAE/research#20"] == (
        "usable-behavioral-baseline-outcome-reproduction-evidence"
    )


def test_retry_keeps_original_attempt_and_requires_a_new_identity() -> None:
    selection = _selection()
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT, selection=selection)
    attempts = _valid_attempts(protocol)
    original = attempts[0]
    original["disposition"] = "failed"
    original["score_measure"] = None
    retry = reproduction.retry_record_for_test(original, score=4.0)

    selected = reproduction.select_eligible_attempts(protocol, [*attempts, retry])

    assert "schema_version" not in original
    assert "schema_version" not in retry
    assert retry["run_id"] != original["run_id"]
    assert retry["predecessor_run_id"] == original["run_id"]
    assert any(item["run_id"] == retry["run_id"] for item in selected)
    assert any(item["run_id"] == original["run_id"] for item in [*attempts, retry])


def test_public_selection_is_the_complete_9000_slot_study() -> None:
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT)
    declaration = protocol["declaration"]
    assert isinstance(declaration, dict)
    assert sum(item["slot_count"] for item in declaration["schedule_partitions"]) == 9000
    assert len(declaration["schedule_partitions"]) == 9
    assert declaration["episodes_per_condition"] == 1000


def test_environment_provenance_joins_pack_scenario_and_method() -> None:
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT, selection=_selection())

    environment = reproduction._write_environment(protocol)
    reproduction._validate_environment(environment, protocol)

    assert "schema_version" not in environment
    assert set(environment["distributions"]) == {
        "CybORG",
        "gym",
        "numpy",
        "raes",
        "raes-adapters",
    }
    assert environment["pack"]["scenario_ref_digest"].startswith("sha256:")
    assert environment["method"]["score_metric_id"] == "cage2-cumulative-blue-reward"


def test_reference_evidence_rejects_unreviewed_claim_fields() -> None:
    reference = reproduction.capture_reference_path(PROJECT_ROOT)
    reproduction._validate_reference(reference)
    assert "schema_version" not in reference
    reference["equivalent"] = True

    with pytest.raises(ValueError, match="reference evidence"):
        reproduction._validate_reference(reference)


def test_persisted_scan_rejects_native_and_traceback_material(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "bad.json").write_text(
        json.dumps({"native_observation": "Traceback (most recent call last):"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="forbidden native material"):
        reproduction.scan_public_tree(root)


def test_cli_declares_partitioned_full_protocol_without_native_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = cli.main(
        [
            "reproduce",
            "--phase",
            "declare",
            "--source-root",
            str(PROJECT_ROOT),
            "--output",
            "declaration",
        ]
    )

    assert result == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["disposition"] == "declared"
    protocol = reproduction.load_strict_json(tmp_path / "declaration" / "protocol.json")
    assert (
        sum(item["slot_count"] for item in protocol["declaration"]["schedule_partitions"]) == 9000
    )
    assert (
        max(path.stat().st_size for path in (tmp_path / "declaration").rglob("*") if path.is_file())
        < 500 * 1024
    )


def test_reproduction_output_symlink_escape_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    result = cli.main(
        [
            "reproduce",
            "--phase",
            "declare",
            "--source-root",
            str(PROJECT_ROOT),
            "--output",
            "linked/evidence",
        ]
    )

    assert result == cli.EXIT_OUTPUT
    assert not (outside / "evidence").exists()
    assert "researcher.output.unavailable" in capsys.readouterr().err


def test_reduced_study_seals_every_attempt_and_recomputes_offline(tmp_path: Path) -> None:
    selection = _selection(episodes=1)
    bundle = tmp_path / "bundle"

    reproduction.run_full_study(
        PROJECT_ROOT,
        bundle,
        selection=selection,
        driver=StudyDriver(),
    )
    result = reproduction.verify_bundle(bundle, selection=selection)

    assert result["scheduled_slot_count"] == 9
    assert result["attempt_count"] == 9
    assert result["classification"] == "failed"
    attempts = list(bundle.glob("runs/*/*/attempt.json.gz"))
    assert len(attempts) == 9
    assert all(reproduction.load_strict_json(path)["disposition"] == "valid" for path in attempts)
    stale_tiers = reproduction.load_strict_json(bundle / "tiers.json")
    stale_tiers["strongest_supported_claim"] = "stale-pre-migration-projection"
    reproduction._write_json(bundle / "tiers.json", stale_tiers)
    root_inventory = reproduction.load_strict_json(bundle / "inventory.json")
    reproduction._seal_inventory(
        bundle,
        [bundle / item["path"] for item in root_inventory["artifacts"]],
    )
    reproduction.compact_bundle_evidence(bundle)
    assert reproduction.verify_bundle(bundle, selection=selection)["attempt_count"] == 9
    assert reproduction.load_strict_json(bundle / "tiers.json")["strongest_supported_claim"] == (
        "failed-outcome-reproduction-with-retained-negative-result"
    )
    output = tmp_path / "recomputed"
    reproduction.recompute_bundle(bundle, output, selection=selection)
    assert (output / "verification.json").is_file()


def test_failed_condition_keeps_only_validated_terminal_attempts(tmp_path: Path) -> None:
    selection = _selection(episodes=2)
    bundle = tmp_path / "failed-bundle"

    reproduction.run_full_study(
        PROJECT_ROOT,
        bundle,
        selection=selection,
        driver=FailingStudyDriver(),
    )
    result = reproduction.verify_bundle(bundle, selection=selection)

    assert result["classification"] == "failed"
    attempts = list(bundle.glob("runs/*/*/attempt.json.gz"))
    records = [reproduction.load_strict_json(path) for path in attempts]
    assert len(records) == 20
    assert [record["disposition"] for record in records].count("failed") == 2
    assert [record["disposition"] for record in records].count("valid") == 18
    retries = [record for record in records if record["attempt_sequence"] == 2]
    assert len(retries) == 2
    assert all(record["predecessor_run_id"].endswith("attempt-01") for record in retries)
    assert all(
        {path.name for path in attempt.parent.iterdir()} == {"attempt.json.gz", "inventory.json"}
        for attempt in attempts
        if reproduction.load_strict_json(attempt)["disposition"] == "failed"
    )


def test_exhausted_retry_does_not_skip_later_conditions(tmp_path: Path) -> None:
    selection = _selection(episodes=2)
    bundle = tmp_path / "exhausted-bundle"

    reproduction.run_full_study(
        PROJECT_ROOT,
        bundle,
        selection=selection,
        driver=ExhaustedRetryStudyDriver(),
    )
    result = reproduction.verify_bundle(bundle, selection=selection)

    records = [
        reproduction.load_strict_json(path) for path in bundle.glob("runs/*/*/attempt.json.gz")
    ]
    first_condition = [
        record for record in records if record["condition_id"] == "steps-030--red-b-line"
    ]
    later_conditions = [
        record for record in records if record["condition_id"] != "steps-030--red-b-line"
    ]
    assert result["classification"] == "unavailable"
    assert len(first_condition) == 4
    assert all(record["disposition"] == "failed" for record in first_condition)
    assert len(later_conditions) == 16
    assert all(record["disposition"] == "valid" for record in later_conditions)


def test_offline_verifier_requires_complete_transitive_inventories(tmp_path: Path) -> None:
    selection = _selection(episodes=1)
    bundle = tmp_path / "bundle"
    reproduction.run_full_study(
        PROJECT_ROOT,
        bundle,
        selection=selection,
        driver=StudyDriver(),
    )
    condition = next((bundle / "runs").iterdir())
    inventory = reproduction.load_strict_json(condition / "inventory.json")
    inventory["artifacts"] = [
        item for item in inventory["artifacts"] if not item["path"].endswith("/inventory.json")
    ]
    reproduction._write_json(condition / "inventory.json", inventory)
    root_inventory = reproduction.load_strict_json(bundle / "inventory.json")
    root_members = [bundle / item["path"] for item in root_inventory["artifacts"]]
    reproduction._seal_inventory(bundle, root_members)

    with pytest.raises(ValueError, match="inventory membership is incomplete"):
        reproduction.verify_bundle(bundle, selection=selection)
