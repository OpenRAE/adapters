from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from raes_adapters.cyberbattlesim import reproduction

PROJECT_ROOT = Path(__file__).parents[1]


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

    def runner(schedule: dict[str, object], _run_root: Path) -> dict[str, object]:
        calls.append(str(schedule["attempt_id"]))
        if schedule["replicate"] == 3:
            raise RuntimeError("hostile traceback sentinel")
        return _mediated_episode(int(schedule["replicate"]))

    output = tmp_path / "mediated"
    reproduction.collect_mediated(native_root, tmp_path / "pack", output, runner=runner)

    rows = reproduction.load_terminal_rows(output)
    assert len(calls) == 10
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
