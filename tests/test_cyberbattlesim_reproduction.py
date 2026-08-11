from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from raes_adapters.cyberbattlesim import reproduction
from raes_adapters.cyberbattlesim.backend import source as source_module

PROJECT_ROOT = Path(__file__).parents[1]
REPRODUCTION_ROOT = PROJECT_ROOT / "packages/cyberbattlesim_adapter/reproduction"


def _native_episode(index: int) -> dict[str, object]:
    steps = 100 + index
    return {
        "steps_to_termination": steps,
        "cumulative_attacker_reward": 5000.0 + index,
        "network_availability": [0.99, 0.97, 0.95],
        "terminal_cause": "attacker-ownership",
    }


def _mediated_episode(index: int) -> dict[str, object]:
    return {
        "steps_to_termination": 105 + index,
        "cumulative_attacker_reward": 5010.0 + index,
        "network_availability": None,
        "terminal_cause": None,
    }


def test_declaration_uses_published_contracts_and_unique_attempts() -> None:
    protocol, source_ledger = reproduction.build_declaration(PROJECT_ROOT)

    reproduction.validate_protocol(protocol, require_oracle=False)
    schedule = protocol["declaration"]["schedule"]
    assert len(schedule) == 20
    assert len({item["run_id"] for item in schedule}) == 20
    assert len({item["attempt_id"] for item in schedule}) == 20
    assert {item["lane"] for item in schedule} == {"source-native", "raes-mediated"}
    assert all(item["run_id"].startswith("cbs-r3-") for item in schedule)
    assert protocol["declaration"]["condition"]["epsilon_schedule_scope"] == (
        "lane-batch-cumulative"
    )
    assert not {item["attempt_id"] for item in schedule} & set(
        protocol["declaration"]["prior_attempts"]["attempt_ids"]
    )
    assert protocol["declaration"]["study"]["schema_version"] == "experiment-study/v1"
    assert source_ledger["source"]["commit"] == ("854d6966607fb68645651f55b0f97221bd293e0d")


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":"x","schema_version":"y"}',
        '{"value": NaN}',
        '{"value": Infinity}',
    ],
)
def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "hostile.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON artifact"):
        reproduction.load_strict_json(path)


def test_protocol_rejects_drift_duplicate_ids_and_unsafe_paths() -> None:
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT)

    drifted = copy.deepcopy(protocol)
    drifted["declaration"]["retry_budget"] = 1
    with pytest.raises(ValueError, match="declaration digest"):
        reproduction.validate_protocol(drifted, require_oracle=False)

    duplicate = copy.deepcopy(protocol)
    duplicate["declaration"]["schedule"][1]["attempt_id"] = duplicate["declaration"]["schedule"][0][
        "attempt_id"
    ]
    duplicate["declaration_sha256"] = reproduction.sha256_payload(duplicate["declaration"])
    with pytest.raises(ValueError, match="attempt identities"):
        reproduction.validate_protocol(duplicate, require_oracle=False)

    unsafe = copy.deepcopy(protocol)
    unsafe["declaration"]["artifacts"][0]["path"] = "../qualification.json"
    unsafe["declaration_sha256"] = reproduction.sha256_payload(unsafe["declaration"])
    with pytest.raises(ValueError, match="relative path"):
        reproduction.validate_protocol(unsafe, require_oracle=False)


def test_aggregation_is_deterministic_and_discloses_missing_metrics() -> None:
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT)
    rows = reproduction.terminal_rows_from_results(
        protocol,
        native_results=[_native_episode(index) for index in range(10)],
        mediated_results=[_mediated_episode(index) for index in range(10)],
        protocol_sha256="a" * 64,
    )

    first = reproduction.compute_aggregates(protocol, rows)
    second = reproduction.compute_aggregates(protocol, list(reversed(rows)))

    assert reproduction.canonical_json_bytes(first) == reproduction.canonical_json_bytes(second)
    assert first["lanes"]["raes-mediated"]["metrics"]["network_availability"]["missing_count"] == 10
    assert first["comparisons"]["network_availability"]["result"] == "unavailable"


def test_native_collection_uses_one_upstream_batch_and_never_mediated_runner(
    tmp_path: Path,
) -> None:
    declaration_root = tmp_path / "declaration"
    reproduction.write_declaration(PROJECT_ROOT, declaration_root)
    calls: list[str] = []

    def native_executor() -> list[dict[str, object]]:
        calls.append("native")
        return [_native_episode(index) for index in range(10)]

    output = tmp_path / "native"
    reproduction.collect_native(declaration_root, output, executor=native_executor)

    assert calls == ["native"]
    completed = reproduction.load_strict_json(output / "protocol.json")
    reproduction.validate_protocol(completed, require_oracle=True)
    rows = reproduction.load_terminal_rows(output)
    assert len(rows) == 10
    assert {row["disposition"] for row in rows} == {"valid"}
    notes = reproduction.load_strict_json(output / "bench-notes.json")["notes"]
    assert notes[0]["event_code"] == "protocol-declared"
    assert sum(note["event_code"] == "native-attempt-terminalized" for note in notes) == 10
    assert all(
        datetime.fromisoformat(note["recorded_at"].replace("Z", "+00:00")).tzinfo == UTC
        for note in notes
    )


def test_native_failure_terminalizes_all_preallocated_attempts(tmp_path: Path) -> None:
    declaration_root = tmp_path / "declaration"
    reproduction.write_declaration(PROJECT_ROOT, declaration_root)

    def fail() -> list[dict[str, object]]:
        raise RuntimeError("secret native detail")

    output = tmp_path / "native"
    with pytest.raises(RuntimeError, match="native collection failed"):
        reproduction.collect_native(declaration_root, output, executor=fail)

    rows = reproduction.load_terminal_rows(output)
    assert len(rows) == 10
    assert {row["disposition"] for row in rows} == {"failed"}
    assert "secret native detail" not in json.dumps(rows)
    notes = reproduction.load_strict_json(output / "bench-notes.json")
    assert notes["notes"][-1]["event_code"] == "native-collection-failed"
    assert notes["notes"][-1]["disposition"] == "failed"
    assert "secret native detail" not in json.dumps(notes)


def test_mediated_collection_continues_after_one_attempt_failure(tmp_path: Path) -> None:
    declaration_root = tmp_path / "declaration"
    reproduction.write_declaration(PROJECT_ROOT, declaration_root)
    native_root = tmp_path / "native"
    reproduction.collect_native(
        declaration_root,
        native_root,
        executor=lambda: [_native_episode(index) for index in range(10)],
    )
    calls: list[str] = []
    offsets: list[int] = []

    def runner(schedule: dict[str, object], _run_root: Path) -> dict[str, object]:
        calls.append(str(schedule["attempt_id"]))
        offsets.append(int(schedule["epsilon_step_offset"]))
        if schedule["replicate"] == 3:
            raise RuntimeError("hostile traceback sentinel")
        return _mediated_episode(int(schedule["replicate"]))

    output = tmp_path / "mediated"
    reproduction.collect_mediated(native_root, tmp_path / "pack", output, runner=runner)

    rows = reproduction.load_terminal_rows(output)
    assert len(calls) == 10
    assert offsets[:4] == [0, 106, 213, 213]
    assert len(rows) == 10
    assert sum(row["disposition"] == "failed" for row in rows) == 1
    assert "hostile traceback sentinel" not in json.dumps(rows)
    notes = reproduction.load_strict_json(output / "bench-notes.json")["notes"]
    terminal = [note for note in notes if note["event_code"] == "mediated-attempt-terminalized"]
    assert len(terminal) == 10
    assert sum(note["disposition"] == "failed" for note in terminal) == 1
    assert "hostile traceback sentinel" not in json.dumps(notes)


def test_declaration_and_collection_outputs_are_no_clobber(tmp_path: Path) -> None:
    output = tmp_path / "declaration"
    reproduction.write_declaration(PROJECT_ROOT, output)

    with pytest.raises(FileExistsError):
        reproduction.write_declaration(PROJECT_ROOT, output)


def test_final_bundle_recomputes_offline_and_has_six_cited_tiers(tmp_path: Path) -> None:
    declaration_root = tmp_path / "declaration"
    reproduction.write_declaration(PROJECT_ROOT, declaration_root)
    native_root = tmp_path / "native"
    reproduction.collect_native(
        declaration_root,
        native_root,
        executor=lambda: [_native_episode(index) for index in range(10)],
    )
    mediated_root = tmp_path / "mediated"
    reproduction.collect_mediated(
        native_root,
        tmp_path / "pack",
        mediated_root,
        runner=lambda _schedule, _root: (_ for _ in ()).throw(RuntimeError("bounded")),
    )
    protocol = reproduction.load_strict_json(native_root / "protocol.json")
    bundle = tmp_path / str(protocol["declaration_sha256"])

    reproduction.finalize_bundle(native_root, mediated_root, bundle)
    result = reproduction.verify_bundle(bundle)

    assert result["scheduled_count"] == 20
    assert result["tier_count"] == 6
    tiers = reproduction.load_strict_json(bundle / "tiers.json")["tiers"]
    assert [tier["tier"] for tier in tiers] == [
        "authored-source",
        "contract",
        "execution-control",
        "state-observation",
        "outcome-evaluation",
        "disclosure",
    ]
    assert all(tier["evidence"] for tier in tiers)
    notes = reproduction.load_strict_json(bundle / "bench-notes.json")
    assert notes["notes"][-1]["event_code"] == "offline-verification-passed"
    assert result["bench_note_count"] == len(notes["notes"])
    assert any(
        evidence["path"] == "bench-notes.json"
        for tier in tiers
        if tier["tier"] == "disclosure"
        for evidence in tier["evidence"]
    )


def test_offline_verifier_rejects_invalid_bench_note_timestamp(tmp_path: Path) -> None:
    declaration_root = tmp_path / "declaration"
    reproduction.write_declaration(PROJECT_ROOT, declaration_root)
    native_root = tmp_path / "native"
    reproduction.collect_native(
        declaration_root,
        native_root,
        executor=lambda: [_native_episode(index) for index in range(10)],
    )
    mediated_root = tmp_path / "mediated"
    reproduction.collect_mediated(
        native_root,
        tmp_path / "pack",
        mediated_root,
        runner=lambda _schedule, _root: (_ for _ in ()).throw(RuntimeError("bounded")),
    )
    protocol = reproduction.load_strict_json(native_root / "protocol.json")
    bundle = tmp_path / str(protocol["declaration_sha256"])
    reproduction.finalize_bundle(native_root, mediated_root, bundle)
    notes = reproduction.load_strict_json(bundle / "bench-notes.json")
    notes["notes"][0]["recorded_at"] = "2026-08-10 03:21:16"
    (bundle / "bench-notes.json").write_text(json.dumps(notes), encoding="utf-8")

    with pytest.raises(ValueError, match="bench note timestamp"):
        reproduction.verify_bundle(bundle)


def test_offline_verifier_rejects_forbidden_native_material(tmp_path: Path) -> None:
    declaration_root = tmp_path / "declaration"
    reproduction.write_declaration(PROJECT_ROOT, declaration_root)
    native_root = tmp_path / "native"
    reproduction.collect_native(
        declaration_root,
        native_root,
        executor=lambda: [_native_episode(index) for index in range(10)],
    )
    mediated_root = tmp_path / "mediated"
    reproduction.collect_mediated(
        native_root,
        tmp_path / "pack",
        mediated_root,
        runner=lambda _schedule, _root: (_ for _ in ()).throw(RuntimeError("bounded")),
    )
    protocol = reproduction.load_strict_json(native_root / "protocol.json")
    bundle = tmp_path / str(protocol["declaration_sha256"])
    reproduction.finalize_bundle(native_root, mediated_root, bundle)
    (bundle / "forbidden.txt").write_text(
        'Traceback (most recent call last): "credential_cache_matrix"', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="forbidden native value"):
        reproduction.verify_bundle(bundle)


def test_inventory_and_offline_verification_reject_symlinked_members(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    target = root / "target.json"
    target.write_text("{}", encoding="utf-8")
    (root / "linked.json").symlink_to(target)

    with pytest.raises(ValueError, match="regular non-symlink"):
        reproduction._inventory_payload(root)


def test_portable_scan_distinguishes_withheld_names_from_native_fields(tmp_path: Path) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "provenance.json").write_text(
        json.dumps(
            {"visibility_policy": {"withheld_refs": ["action_mask", "credential_cache_matrix"]}}
        ),
        encoding="utf-8",
    )

    reproduction._scan_portable(safe)

    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    (unsafe / "evidence.json").write_text(json.dumps({"action_mask": [1, 0, 1]}), encoding="utf-8")

    with pytest.raises(ValueError, match="forbidden native value"):
        reproduction._scan_portable(unsafe)

    serialized = tmp_path / "serialized"
    serialized.mkdir()
    (serialized / "payload.json").write_text(
        json.dumps([json.dumps({"credential_cache_matrix": [[1]]})]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="forbidden native value"):
        reproduction._scan_portable(serialized)


def test_rejected_attempt_series_remains_timestamped_and_inventory_bound() -> None:
    root = REPRODUCTION_ROOT / ("825dde3b4cd66f228e0f93157a2add35e3c9a822a7adac1d8ffd322b32116232")
    rejection = reproduction.load_strict_json(root / "rejection.json")

    assert rejection["publication_eligible"] is False
    assert rejection["publication_disposition"] == "rejected"
    assert rejection["terminalized_counts"] == {
        "source-native": 10,
        "raes-mediated": 10,
    }
    assert rejection["scientific_conditions_changed"] is False
    assert rejection["retention_note"].endswith("issuecomment-5235757215")
    assert rejection["superseded_at"] == "2026-08-10T04:33:59.394Z"
    assert rejection["superseded_by"] == (
        "f09ec5759021cf1d5de9b260e0299934bf6f6cc4161b822e8f5f0b76bdb96b53"
    )

    for stage in rejection["retained_stages"]:
        stage_root = root / stage["path"]
        reproduction._verify_inventory(stage_root)
        reproduction._scan_portable(stage_root)
        assert (
            reproduction._sha256_file(stage_root / "inventory.json") == (stage["inventory_sha256"])
        )
        notes = reproduction.load_strict_json(stage_root / "bench-notes.json")["notes"]
        for note in notes:
            parsed = datetime.fromisoformat(note["recorded_at"].replace("Z", "+00:00"))
            assert parsed.tzinfo == UTC

    assert len(reproduction.load_terminal_rows(root / "native-oracle")) == 10
    assert len(reproduction.load_terminal_rows(root / "mediated")) == 10


def test_checked_in_revision_2_bundle_recomputes_with_failed_outcome_tier() -> None:
    root = REPRODUCTION_ROOT / ("f09ec5759021cf1d5de9b260e0299934bf6f6cc4161b822e8f5f0b76bdb96b53")

    result = reproduction.verify_bundle(root)
    aggregates = reproduction.load_strict_json(root / "aggregates.json")
    tiers = reproduction.load_strict_json(root / "tiers.json")["tiers"]

    assert result == {
        "disposition": "verified",
        "scheduled_count": 20,
        "tier_count": 6,
        "bench_note_count": 39,
        "inventory_sha256": ("4653bc5afbf501f005f997df782f73f282cccbe28f9cbe176d5a9c3f5970a292"),
    }
    assert aggregates["comparisons"]["cumulative_attacker_reward"]["result"] == ("bounded")
    assert aggregates["comparisons"]["steps_to_termination"]["result"] == ("outside-tolerance")
    assert aggregates["comparisons"]["network_availability"]["result"] == ("unavailable")
    assert aggregates["comparisons"]["terminal_cause"]["result"] == "unavailable"
    assert {tier["tier"]: tier["result"] for tier in tiers} == {
        "authored-source": "passed",
        "contract": "passed",
        "execution-control": "weakened",
        "state-observation": "weakened",
        "outcome-evaluation": "failed",
        "disclosure": "passed",
    }


def test_terminal_cause_uses_tolerant_frozen_classification() -> None:
    assert reproduction._terminal_cause([], [], 600) is None
    assert reproduction._terminal_cause([5000.0 + 1e-12], [0.7], 600) == "defender-sla"
    assert reproduction._terminal_cause([5000.0], [0.9], 600) == "attacker-ownership"
    assert reproduction._terminal_cause([0.0], [1.0], 2) == "defender-eviction"
    assert reproduction._terminal_cause([1.0, 2.0], [1.0, 1.0], 2) == "evaluator-cutoff"


@pytest.mark.parametrize(
    ("metric", "value"),
    [
        ("steps_to_termination", True),
        ("steps_to_termination", 601),
        ("cumulative_attacker_reward", float("nan")),
        ("cumulative_attacker_reward", False),
        ("network_availability", []),
        ("network_availability", [float("inf")]),
        ("network_availability", [1.1]),
        ("terminal_cause", "unknown"),
    ],
)
def test_metric_validator_rejects_invalid_values(metric: str, value: object) -> None:
    with pytest.raises(ValueError, match="run metric is invalid"):
        reproduction._validate_metric_value(metric, value)


def test_closed_protocol_helpers_reject_malformed_values() -> None:
    protocol, _ledger = reproduction.build_declaration(PROJECT_ROOT)
    declaration = protocol["declaration"]
    prior = declaration["prior_attempts"]

    malformed_artifacts: list[object] = [
        [],
        [None],
        [{"artifact_id": "x", "path": "x", "sha256": "bad"}],
        [
            {"artifact_id": "x", "path": "x", "sha256": "a" * 64},
            {"artifact_id": "x", "path": "y", "sha256": "b" * 64},
        ],
    ]
    for value in malformed_artifacts:
        with pytest.raises(ValueError):
            reproduction._validate_declared_artifacts(value)

    with pytest.raises(ValueError, match="attempt schedule"):
        reproduction._validated_schedule_entry(None)
    with pytest.raises(ValueError, match="attempt schedule"):
        reproduction._validate_attempt_schedule([], prior)
    with pytest.raises(ValueError, match="oracle is required"):
        reproduction._validate_oracle(None, protocol["declaration_sha256"], [], True)
    with pytest.raises(ValueError, match="oracle is invalid"):
        reproduction._validate_oracle([], protocol["declaration_sha256"], [], False)


def test_bench_note_helpers_reject_invalid_controlled_fields() -> None:
    with pytest.raises(ValueError, match="evidence references"):
        reproduction._validate_bench_evidence_refs("not-a-list")
    with pytest.raises(ValueError, match="evidence references"):
        reproduction._validate_bench_evidence_refs([{"path": "x", "extra": True}])

    note = {
        "phase": "invalid",
        "severity": "info",
        "event_code": "protocol-declared",
        "disposition": "passed",
        "summary": "bounded",
        "evidence_refs": [],
    }
    with pytest.raises(ValueError, match="phase"):
        reproduction._validate_bench_note_values(note)
    note["phase"] = "declaration"
    note["summary"] = ""
    with pytest.raises(ValueError, match="summary"):
        reproduction._validate_bench_note_values(note)


def test_portable_file_scan_rejects_size_text_and_host_paths(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.bin"
    oversized.write_bytes(b"x" * (500 * 1024 + 1))
    with pytest.raises(ValueError, match="size limit"):
        reproduction._scan_portable_file(oversized)

    native_text = tmp_path / "native.txt"
    native_text.write_text("action_mask", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden native value"):
        reproduction._scan_portable_file(native_text)

    host_path = tmp_path / "host.txt"
    host_path.write_text("file:///tmp/private", encoding="utf-8")
    with pytest.raises(ValueError, match="host path"):
        reproduction._scan_portable_file(host_path)


def test_pointer_and_mediated_measure_helpers_are_closed(tmp_path: Path) -> None:
    document = {"items": [{"value": 3}]}
    assert reproduction._resolve_pointer(document, "/items/0/value") == 3
    with pytest.raises(ValueError, match="JSON Pointer"):
        reproduction._resolve_pointer(document, "items")
    with pytest.raises(ValueError, match="unresolved"):
        reproduction._resolve_pointer(document, "/missing")

    measure = tmp_path / "measure.json"
    measure.write_text(
        '[{"metric_ref":{"ref_id":"cumulative_attacker_reward"},"value":4.5}]',
        encoding="utf-8",
    )
    assert reproduction._mediated_measure(measure) == 4.5
    measure.write_text(
        '[{"metric_ref":{"ref_id":"cumulative_attacker_reward"},"value":"bad"}]',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="mediated evidence"):
        reproduction._mediated_measure(measure)


def test_installed_source_digest_supports_both_direct_url_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = "a" * 64
    direct = SimpleNamespace(
        read_text=lambda _name: json.dumps({"archive_info": {"hash": f"sha256={digest}"}})
    )
    monkeypatch.setattr(reproduction.importlib.metadata, "distribution", lambda _name: direct)
    assert reproduction._installed_source_artifact_sha256() == digest

    hashes = SimpleNamespace(
        read_text=lambda _name: json.dumps({"archive_info": {"hashes": {"sha256": digest}}})
    )
    monkeypatch.setattr(reproduction.importlib.metadata, "distribution", lambda _name: hashes)
    assert reproduction._installed_source_artifact_sha256() == digest


def test_native_worker_and_batch_projection_are_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Environment:
        identifiers = object()
        closed = False

        def close(self) -> None:
            self.closed = True

    environment = Environment()
    qualification = {
        "protocol": {
            "selection": {
                "attacker": {
                    "environment_bounds": {
                        "maximum_total_credentials": 22,
                        "maximum_node_count": 10,
                    },
                    "episode_count": 10,
                    "iteration_count": 600,
                    "epsilon": 0.9,
                    "epsilon_exponential_decay": 10000,
                    "epsilon_minimum": 0.1,
                }
            }
        }
    }
    learner = SimpleNamespace(
        epsilon_greedy_search=lambda **_kwargs: {
            "all_episodes_rewards": [[1.0] for _ in range(10)],
            "all_episodes_availability": [[0.9] for _ in range(10)],
        }
    )
    wrapper = SimpleNamespace(
        EnvironmentBounds=SimpleNamespace(of_identifiers=lambda **_kwargs: "bounds"),
        Verbosity=SimpleNamespace(Quiet="quiet"),
    )
    modules = {
        "cyberbattle.agents.baseline.learner": learner,
        "cyberbattle.agents.baseline.agent_randomcredlookup": SimpleNamespace(
            CredentialCacheExploiter=lambda: "policy"
        ),
        "cyberbattle.agents.baseline.agent_wrapper": wrapper,
    }
    monkeypatch.setattr(reproduction, "verify_selected_cyberbattlesim_source", lambda: None)
    monkeypatch.setattr(reproduction, "load_qualification", lambda: qualification)
    monkeypatch.setattr(
        reproduction, "construct_selected_cyberbattlesim_environment", lambda: environment
    )
    monkeypatch.setattr(reproduction.importlib, "import_module", modules.__getitem__)
    output = tmp_path / "native-worker.json"

    reproduction._native_worker(output)

    payload = reproduction.load_strict_json(output)
    assert len(payload["episodes"]) == 10
    assert payload["cleanup_verified"] is True
    assert environment.closed is True

    def run_worker(command: list[str], **_kwargs: object) -> SimpleNamespace:
        Path(command[-1]).write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(reproduction.subprocess, "run", run_worker)
    results = reproduction._execute_native_batch()
    assert len(results) == 10
    assert {result["terminal_cause"] for result in results} == {None}


def test_mediated_attempt_projects_only_portable_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_id = "cbs-r2-mediated-01"
    run_root = tmp_path / "run"
    archival = run_root / "portable" / "runs" / f"{run_id}-1"
    archival.mkdir(parents=True)
    portable = run_root / "portable"
    (portable / "summary.json").write_text(
        json.dumps({"disposition": "succeeded"}), encoding="utf-8"
    )
    (archival / "summary.json").write_text(
        json.dumps({"completed_steps": 7, "cleanup_verified": True}), encoding="utf-8"
    )
    (archival / "derived-measures.json").write_text(
        json.dumps(
            [
                {
                    "metric_ref": {"ref_id": "cumulative_attacker_reward"},
                    "value": 42.5,
                }
            ]
        ),
        encoding="utf-8",
    )
    (archival / "episode-outcome.json").write_text(
        json.dumps(
            {
                "schema_version": "cyberbattlesim-sanitized-episode-outcome/v1",
                "network_availability": [1.0, 0.75, 1.0, 1.0, 0.95, 0.9, 0.75],
                "terminal_cause": "defender-sla",
            }
        ),
        encoding="utf-8",
    )
    for name in ("run.json", "evidence-records.json"):
        (archival / name).write_text("{}", encoding="utf-8")
    (portable / "inventory.json").write_text("{}", encoding="utf-8")
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(reproduction.subprocess, "run", run)

    result = reproduction._execute_mediated_attempt(
        {
            "pack_root": (tmp_path / "pack").as_posix(),
            "run_id": run_id,
            "epsilon_step_offset": 141,
        },
        run_root,
    )

    assert result["steps_to_termination"] == 7
    assert result["cumulative_attacker_reward"] == 42.5
    assert result["network_availability"] == [1.0, 0.75, 1.0, 1.0, 0.95, 0.9, 0.75]
    assert result["terminal_cause"] == "defender-sla"
    assert result["cleanup_verified"] is True
    assert len(result["evidence_refs"]) == 5
    command = commands[0]
    assert command[command.index("--epsilon-step-offset") + 1] == "141"


def test_selected_source_helpers_verify_and_construct(monkeypatch: pytest.MonkeyPatch) -> None:
    distribution = object()
    gym_distribution = object()
    numpy_distribution = object()
    origins: list[tuple[str, object, str]] = []
    monkeypatch.setattr(
        source_module._source_admission,
        "verify_runtime_artifacts",
        lambda *_args, **_kwargs: {
            "cyberbattlesim": distribution,
            "gymnasium": gym_distribution,
            "numpy": numpy_distribution,
        },
    )
    monkeypatch.setattr(
        source_module._source_admission,
        "verify_runtime_source_tree",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        source_module._source_admission,
        "verify_selected_source_files",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        source_module._source_admission,
        "verify_package_origin",
        lambda name, selected, path: origins.append((name, selected, path)),
    )
    source_module.verify_selected_source_identity({}, distribution)  # type: ignore[arg-type]
    assert any(item[0] == "gymnasium" and item[1] is gym_distribution for item in origins)
    assert any(item[0] == "numpy" and item[1] is numpy_distribution for item in origins)

    monkeypatch.setattr(
        source_module._source_admission,
        "resolve_selected_distribution",
        lambda package, version: distribution,
    )
    assert (
        source_module.resolve_and_verify_selected_source(
            {}, {"package": "cyberbattlesim", "version": "0.1.0"}
        )
        is distribution
    )

    monkeypatch.setattr(
        source_module, "resolve_and_verify_selected_source", lambda *_args: distribution
    )
    goal = SimpleNamespace(
        AttackerGoal=lambda **kwargs: ("goal", kwargs),
        DefenderConstraint=lambda **kwargs: ("constraint", kwargs),
    )
    defender = SimpleNamespace(
        ScanAndReimageCompromisedMachines=lambda **kwargs: ("defender", kwargs)
    )
    gymnasium = SimpleNamespace(make=lambda *_args, **_kwargs: SimpleNamespace(unwrapped="env"))
    modules = {
        "cyberbattle": object(),
        "gymnasium": gymnasium,
        "numpy": "numpy-module",
        "cyberbattle._env.cyberbattle_env": goal,
        "cyberbattle._env.defender": defender,
    }
    runtime = source_module.construct_selected_environment(
        {},
        {},
        {
            "termination": {
                "attacker_own_atleast": 1,
                "attacker_own_atleast_percent": 1.0,
                "defender_maintain_sla": 0.8,
            },
            "defender": {"probability": 0.6, "scan_capacity": 2, "scan_frequency": 5},
            "scenario": {"gym_id": "id", "size": 10},
        },
        module_loader=modules.__getitem__,
    )
    assert runtime.environment == "env"
    assert runtime.numpy == "numpy-module"
    assert runtime.selected_distribution is distribution
