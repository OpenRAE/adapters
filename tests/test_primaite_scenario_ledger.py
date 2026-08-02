"""Scenario + pinned source-mapping ledger evidence for PrimAITE (#40).

The authored RAES SDL scenario carries portable topology/objective truth only;
reward, evaluator, fixed-horizon termination, and stochastic controls live in the
companion published experiment contracts. The source ledger records how each
pinned PrimAITE source fact reaches a portable RAES surface, or why it does not,
and every disclosed loss binds the ADR-069 equivalence tier it weakens.

The negative tests below are the fail-closed guarantee: each proves the
deterministic validator rejects one specific corruption (source drift, a missing
category, a duplicate row, an unresolvable target, an undisclosed loss, native
leakage, a stale cross-artifact reference), so CI fails when the checked-in
evidence set drifts into that state.
"""

from __future__ import annotations

import copy
import hashlib
from types import SimpleNamespace
from typing import Any

import pytest
from raes_contracts.contracts import schema_bundle

import raes_adapters.primaite.scenario_ledger as sl

_MAPPED = "topology-network-laydown"
_EXCLUDED = "actions-native-ids"
_LOSS = "stochastic-green-policy"  # loss-unbound-random-streams / deterministic-replay


def _inputs() -> dict[str, Any]:
    return {
        "qualification": sl.load_qualification(),
        "scenario": sl.load_scenario(),
        "bundle": schema_bundle(),
        "disclosures": sl.load_disclosures(),
    }


def _run(rows: list[dict[str, Any]]) -> list[sl.LedgerProblem]:
    return sl.validate_ledger(rows, **_inputs())


def _row(source_id: str) -> dict[str, Any]:
    for row in sl.load_ledger():
        if row["source_id"] == source_id:
            return copy.deepcopy(row)
    raise AssertionError(f"no such ledger row: {source_id}")


def _fields(problems: list[sl.LedgerProblem]) -> set[str]:
    return {problem.field for problem in problems}


# --------------------------------------------------------------------------- #
# positive: the checked-in evidence set validates end to end
# --------------------------------------------------------------------------- #
def test_scenario_parses_instantiates_and_admits() -> None:
    scenario = sl.load_scenario()
    assert scenario.name == "primaite-data-manipulation"
    assert scenario.semantic_validated is True
    digest = sl.instantiated_digest()
    assert digest == sl.PINNED_SCENARIO_DIGEST
    assert digest.startswith("sha256:")


def test_scenario_pipeline_compiles_with_pinned_release() -> None:
    assert sl.validate_scenario_pipeline() == []


def test_companion_experiment_contracts_validate() -> None:
    task = sl.load_experiment_task()
    spec = sl.load_experiment_spec()
    assert task.scenario_ref.ref_digest == sl.PINNED_SCENARIO_DIGEST
    assert sorted(task.evaluation_protocol.metric_definitions) == [
        "cumulative_blue_reward",
        "data_asset_integrity",
        "green_service_penalty",
        "steps_to_truncation",
        "terminal_cause",
    ]
    # Descriptive-only stochastic controls: the broken light-route seed seam and
    # uncontrolled GREEN randomness mean no executable binding is claimed.
    assert spec.run_plan.episode_control.max_steps == 128
    assert spec.run_plan.target_run_count == 3
    assert len(spec.run_plan.stochastic_controls) == 4
    assert all(control.executable_binding is None for control in spec.run_plan.stochastic_controls)


def test_full_evidence_set_is_valid() -> None:
    assert sl.validate_all() == []


def test_selection_joins_and_extension_seam() -> None:
    assert sl.validate_joins() == []
    # The extension seam is a descriptor: a second case is another Selection
    # handed to the same entry point, not a validator edit.
    assert isinstance(sl.DATA_MANIPULATION, sl.Selection)
    assert sl.validate_all(sl.DATA_MANIPULATION) == []


def test_ledger_covers_every_required_category() -> None:
    rows = sl.load_ledger()
    assert {row["category"] for row in rows} == set(sl.CATEGORIES)
    assert {row["disposition"] for row in rows} <= sl.DISPOSITIONS
    assert len({row["source_id"] for row in rows}) == len(rows)


def test_loss_disclosures_bind_recognized_tiers() -> None:
    assert sl.load_disclosures() == {
        "loss-no-source-artifact": "reproducibility",
        "loss-unbound-random-streams": "deterministic-replay",
        "loss-abstracted-participant-interface": "outcome-equivalence",
        "loss-abstracted-network-controls": "outcome-equivalence",
        "loss-fixed-horizon-only-termination": "outcome-equivalence",
    }
    assert set(sl.load_disclosures().values()) <= sl.EQUIVALENCE_TIERS


# --------------------------------------------------------------------------- #
# target resolution
# --------------------------------------------------------------------------- #
def test_target_resolution_positive_and_negative() -> None:
    context = {"scenario": sl.load_scenario(), "bundle": schema_bundle()}
    assert sl.resolve_target("sdl:nodes", **context)
    assert sl.resolve_target("sdl:agents.blue-defender", **context)
    assert sl.resolve_target("sdl:objectives.corrupt-data", **context)
    assert sl.resolve_target("contract:ExperimentTaskModel.evaluation_protocol", **context)
    assert sl.resolve_target("contract:ExperimentSpecModel.run_plan.stochastic_controls", **context)
    assert sl.resolve_target("resource:qualification.json", **context)

    assert not sl.resolve_target("sdl:not_a_section", **context)
    assert not sl.resolve_target("sdl:agents.ghost", **context)
    assert not sl.resolve_target("contract:NotAModel.field", **context)
    assert not sl.resolve_target("contract:ExperimentTaskModel.nope", **context)
    assert not sl.resolve_target("resource:missing.json", **context)
    assert not sl.resolve_target("mystery:thing", **context)


# --------------------------------------------------------------------------- #
# fail-closed negatives: row shape and identity
# --------------------------------------------------------------------------- #
def test_duplicate_row_id_is_rejected() -> None:
    rows = sl.load_ledger()
    rows.append(_row(_MAPPED))
    assert any(p.field == "source_id" and "duplicate" in p.reason for p in _run(rows))


def test_unknown_category_is_rejected() -> None:
    row = _row(_MAPPED)
    row["category"] = "not-a-category"
    assert any(p.field == "category" and "unknown category" in p.reason for p in _run([row]))


def test_missing_required_category_is_rejected() -> None:
    rows = [r for r in sl.load_ledger() if r["category"] != "stochastic"]
    assert any(p.field == "category" and "stochastic" in p.reason for p in _run(rows))


def test_unknown_disposition_is_rejected() -> None:
    row = _row(_MAPPED)
    row["disposition"] = "kind-of-mapped"
    assert any(p.field == "disposition" for p in _run([row]))


def test_missing_required_field_is_rejected() -> None:
    row = _row(_MAPPED)
    del row["source_selector"]
    assert any(p.field == "source_selector" for p in _run([row]))


def test_unknown_field_is_rejected() -> None:
    row = _row(_MAPPED)
    row["extra_note"] = "value"
    assert any(p.field == "extra_note" for p in _run([row]))


# --------------------------------------------------------------------------- #
# fail-closed negatives: source-drift join
# --------------------------------------------------------------------------- #
def test_source_digest_drift_is_rejected() -> None:
    row = _row(_MAPPED)
    row["source_digest"] = "0" * 64
    assert any(p.field == "source_digest" and "drift" in p.reason for p in _run([row]))


def test_source_commit_mismatch_is_rejected() -> None:
    row = _row(_MAPPED)
    row["source_commit"] = "cafebabe" * 5
    assert any(p.field == "source_commit" for p in _run([row]))


def test_unqualified_source_path_is_rejected() -> None:
    row = _row(_MAPPED)
    row["source_path"] = "src/primaite/not/a/real/file.py"
    assert any(p.field == "source_path" for p in _run([row]))


def test_dropping_digest_does_not_bypass_the_drift_join() -> None:
    # source_digest is required, so omission fails closed.
    row = _row(_MAPPED)
    del row["source_digest"]
    assert any(p.field == "source_digest" for p in _run([row]))
    # The path -> qualification join runs independently of the digest value.
    row = _row(_MAPPED)
    row["source_path"] = "src/primaite/not/a/real/file.py"
    row["source_digest"] = "0" * 64
    assert any(p.field == "source_path" for p in _run([row]))


# --------------------------------------------------------------------------- #
# fail-closed negatives: disposition rules
# --------------------------------------------------------------------------- #
def test_mapped_row_with_unresolvable_target_is_rejected() -> None:
    row = _row(_MAPPED)
    row["raes_target"] = "sdl:not_a_section"
    assert any(p.field == "raes_target" and "does not resolve" in p.reason for p in _run([row]))


def test_mapped_row_without_target_is_rejected() -> None:
    row = _row(_MAPPED)
    del row["raes_target"]
    assert any(p.field == "raes_target" for p in _run([row]))


def test_excluded_row_with_target_is_rejected() -> None:
    row = _row(_EXCLUDED)
    row["raes_target"] = "sdl:nodes"
    assert any(p.field == "raes_target" for p in _run([row]))


def test_loss_row_without_loss_ref_is_rejected() -> None:
    row = _row(_LOSS)
    del row["loss_ref"]
    assert any(p.field == "loss_ref" for p in _run([row]))


def test_loss_row_with_disagreeing_tier_is_rejected() -> None:
    row = _row(_LOSS)  # disclosure says deterministic-replay
    row["equivalence_tier"] = "outcome-equivalence"
    assert any(p.field == "equivalence_tier" and "disagrees" in p.reason for p in _run([row]))


def test_loss_row_with_unrecognized_tier_is_rejected() -> None:
    row = _row(_LOSS)
    row["equivalence_tier"] = "vibes-equivalence"
    assert any(p.field == "equivalence_tier" for p in _run([row]))


def test_unreferenced_disclosure_is_rejected() -> None:
    inputs = _inputs()
    inputs["disclosures"] = {**inputs["disclosures"], "loss-orphan": "reproducibility"}
    problems = sl.validate_ledger(sl.load_ledger(), **inputs)
    assert any(p.row_id == "loss-orphan" and p.field == "loss_ref" for p in problems)


# --------------------------------------------------------------------------- #
# strict JSONL parsing
# --------------------------------------------------------------------------- #
def test_strict_jsonl_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        sl.parse_ledger('{"source_id": "a", "source_id": "b"}')


def test_strict_jsonl_rejects_non_object_row() -> None:
    with pytest.raises(ValueError, match="not a JSON object"):
        sl.parse_ledger("[1, 2, 3]")


def test_strict_jsonl_rejects_non_finite_number() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        sl.parse_ledger('{"weight": NaN}')


def test_loss_heading_without_tier_is_preserved_and_flagged() -> None:
    document = "# losses\n\n## loss-no-tier\n\nNarrative with no tier line.\n"
    assert sl.parse_disclosures(document) == {"loss-no-tier": ""}
    row = _row(_LOSS)
    row["loss_ref"] = "loss-no-tier"
    inputs = _inputs()
    inputs["disclosures"] = {"loss-no-tier": ""}
    problems = sl.validate_ledger([row], **inputs)
    assert any(p.row_id == "loss-no-tier" and p.field == "equivalence_tier" for p in problems)


# --------------------------------------------------------------------------- #
# cross-artifact selection joins
# --------------------------------------------------------------------------- #
def test_join_rejects_wrong_pinned_scenario_digest() -> None:
    drifted = sl.DATA_MANIPULATION._replace(scenario_digest="sha256:" + "0" * 64)
    problems = sl.validate_joins(drifted)
    assert any(p.field == "digest" for p in problems)
    assert any(p.row_id in {"task", "spec"} and "scenario_ref" in p.field for p in problems)


def test_join_rejects_stale_task_reference() -> None:
    drifted = sl.DATA_MANIPULATION._replace(task_id="stale-task-id")
    problems = sl.validate_joins(drifted)
    assert any(p.row_id == "task" and p.field == "task_id" for p in problems)
    assert any(p.row_id == "spec" and p.field == "task_ref" for p in problems)


def test_join_rejects_wrong_scenario_and_spec_identity() -> None:
    drifted = sl.DATA_MANIPULATION._replace(scenario_id="wrong-scn", spec_id="wrong-spec")
    problems = sl.validate_joins(drifted)
    assert any(p.row_id == "scenario" and p.field == "name" for p in problems)
    assert any(p.row_id == "spec" and p.field == "spec_id" for p in problems)


def test_companion_resource_pins_match_and_reject_drift() -> None:
    # Every companion resource's current content digest matches its pin.
    assert sl._resource_pin_problems(sl.DATA_MANIPULATION) == []
    assert sl.content_digest(*sl.DATA_MANIPULATION.task_parts) == sl.DATA_MANIPULATION.task_digest
    # A silently edited companion (drifted pin) fails closed for each resource.
    for field in ("task_digest", "spec_digest", "ledger_digest", "losses_digest"):
        drifted = sl.DATA_MANIPULATION._replace(**{field: "sha256:" + "0" * 64})
        problems = sl._resource_pin_problems(drifted)
        assert any(p.field == "content_digest" for p in problems), field
        # The join is wired into validate_joins, so drift also fails there.
        assert any(p.field == "content_digest" for p in sl.validate_joins(drifted))


def test_protocol_join_detects_checksum_and_size_drift() -> None:
    body = b"protocol bytes"
    good = SimpleNamespace(
        artifact_refs=[
            SimpleNamespace(
                role="protocol",
                checksum=SimpleNamespace(value=hashlib.sha256(body).hexdigest()),
                size_bytes=len(body),
            )
        ]
    )
    assert sl._protocol_join(good, body) == []

    drifted = SimpleNamespace(
        artifact_refs=[
            SimpleNamespace(role="protocol", checksum=SimpleNamespace(value="dead"), size_bytes=1)
        ]
    )
    problems = sl._protocol_join(drifted, body)
    assert any("checksum" in p.reason for p in problems)
    assert any("size" in p.reason for p in problems)

    missing = SimpleNamespace(artifact_refs=[])
    assert any("no protocol" in p.reason for p in sl._protocol_join(missing, body))


# --------------------------------------------------------------------------- #
# native-leakage scan (grounded in qualification provenance)
# --------------------------------------------------------------------------- #
def test_native_identifier_leakage_is_rejected_case_insensitively() -> None:
    assert sl.native_leakage_problems({"a": "leaks data_manipulation_attacker here"})
    assert sl.native_leakage_problems({"a": "LEAKS CLIENT_1_GREEN_USER HERE"})
    assert sl.native_leakage_problems({"a": "client_2_green_user exposed"}) != []
    assert sl.native_leakage_problems({"a": "no native identifiers here"}) == []


def test_native_representation_leakage_is_rejected() -> None:
    for text in (
        "Traceback (most recent call last):",
        "obs = ndarray(1652)",
        "vector = array([0, 1, 0])",
        "dtype('int64')",
        "<primaite.session.environment.PrimaiteGymEnv object>",
        "repr is <foo object at 0x7f00>",
    ):
        assert sl.native_leakage_problems({"a": text}), text


def test_leakage_markers_are_grounded_in_qualification_provenance() -> None:
    markers = sl._native_markers()
    participants = sl.load_qualification()["protocol"]["selection"]["participants"]
    assert participants["red"]["ref"].lower() in markers
    for green in participants["green"]:
        assert green["ref"].lower() in markers
    # The generic BLUE seat ref is intentionally not a marker (it recurs in
    # legitimate portable defensive vocabulary).
    assert "defender" not in markers
