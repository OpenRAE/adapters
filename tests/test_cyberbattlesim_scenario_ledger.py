"""Scenario + pinned source-mapping ledger evidence for CyberBattleSim (#26).

The authored RAES SDL scenario carries portable topology/objective truth only;
reward, evaluator, termination, and stochastic controls live in the companion
published experiment contracts. The source ledger records how each pinned
CyberBattleSim source fact reaches a portable RAES surface, or why it does not,
and every disclosed loss binds the ADR-069 equivalence tier it weakens.

The negative tests below are the fail-closed guarantee: each one proves the
deterministic validator rejects a specific corruption (source drift, a missing
category, a duplicate row, an unresolvable target, an undisclosed loss, native
leakage), so CI fails when the checked-in evidence set drifts into that state.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
from types import SimpleNamespace
from typing import Any

import pytest
from raes_contracts.contracts import schema_bundle

import raes_adapters.cyberbattlesim.scenario_ledger as sl


def _context() -> dict[str, Any]:
    return {
        "qualification": sl.load_qualification(),
        "scenario": sl.load_scenario(),
        "bundle": schema_bundle(),
        "losses": sl.load_loss_disclosures(),
    }


def _validate(rows: list[dict[str, Any]]) -> list[sl.LedgerProblem]:
    return sl.validate_source_ledger(rows, **_context())


def _row(source_id: str) -> dict[str, Any]:
    for row in sl.load_source_ledger():
        if row["source_id"] == source_id:
            return copy.deepcopy(row)
    raise AssertionError(f"no such row: {source_id}")


# --------------------------------------------------------------------------- #
# positive: the checked-in evidence set validates end to end
# --------------------------------------------------------------------------- #
def test_sdl_scenario_validates_instantiates_and_admits() -> None:
    scenario = sl.load_scenario()
    assert scenario.name == "cyberbattlesim-chain"
    assert scenario.semantic_validated is True
    digest = sl.scenario_canonical_digest()
    assert digest == sl.PINNED_SCENARIO_DIGEST
    assert digest.startswith("sha256:")


def test_scenario_pipeline_compiles_with_pinned_release() -> None:
    # parse -> instantiate -> pinned canonical digest -> compile -> admit.
    assert sl.validate_scenario_pipeline() == []


def test_companion_experiment_contracts_validate() -> None:
    task = sl.load_experiment_task()
    spec = sl.load_experiment_spec()
    assert task.scenario_ref.ref_digest == sl.PINNED_SCENARIO_DIGEST
    assert sorted(task.evaluation_protocol.metric_definitions) == [
        "cumulative_attacker_reward",
        "network_availability",
        "steps_to_termination",
        "terminal_cause",
    ]
    # Stochastic controls stay descriptive: no executable random-stream binding,
    # so the determinism loss is retained rather than silently claimed.
    assert spec.run_plan.target_run_count == 10
    assert spec.run_plan.episode_control.max_steps == 600
    assert len(spec.run_plan.stochastic_controls) == 4
    assert all(c.executable_binding is None for c in spec.run_plan.stochastic_controls)


def test_full_evidence_set_is_valid() -> None:
    assert sl.validate_all() == []


def test_selection_joins_pass_for_the_checked_in_selection() -> None:
    assert sl.validate_selection_joins() == []
    # The extension seam is a descriptor: the parameterized entry point accepts
    # the selection object, so a second scenario is another descriptor, not a
    # validator edit.
    assert isinstance(sl.CYBERBATTLE_CHAIN, sl.EvidenceSelection)
    assert sl.validate_all(sl.CYBERBATTLE_CHAIN) == []


def test_ledger_covers_every_required_category() -> None:
    rows = sl.load_source_ledger()
    assert {row["category"] for row in rows} == set(sl.REQUIRED_CATEGORIES)
    assert {row["disposition"] for row in rows} <= sl.DISPOSITIONS
    assert len({row["source_id"] for row in rows}) == len(rows)


def test_loss_disclosures_bind_recognized_tiers() -> None:
    losses = sl.load_loss_disclosures()
    assert losses == {
        "loss-no-source-artifact": "reproducibility",
        "loss-unbound-random-streams": "deterministic-replay",
        "loss-abstracted-topology": "outcome-equivalence",
        "loss-benchmark-defects": "outcome-equivalence",
    }
    assert set(losses.values()) <= sl.RECOGNIZED_EQUIVALENCE_TIERS


# --------------------------------------------------------------------------- #
# target resolution
# --------------------------------------------------------------------------- #
def test_target_resolution_positive_and_negative() -> None:
    ctx = {"scenario": sl.load_scenario(), "bundle": schema_bundle()}
    assert sl.resolve_target("sdl:nodes", **ctx)
    assert sl.resolve_target("sdl:agents.attacker", **ctx)
    assert sl.resolve_target("contract:ExperimentTaskModel.evaluation_protocol", **ctx)
    assert sl.resolve_target("contract:ExperimentSpecModel.run_plan.episode_control", **ctx)
    assert sl.resolve_target("resource:qualification.json", **ctx)

    assert not sl.resolve_target("sdl:not_a_section", **ctx)
    assert not sl.resolve_target("sdl:agents.ghost", **ctx)
    assert not sl.resolve_target("contract:NotARealModel.foo", **ctx)
    assert not sl.resolve_target("contract:ExperimentTaskModel.nope", **ctx)
    assert not sl.resolve_target("resource:missing-file.json", **ctx)
    assert not sl.resolve_target("mystery:thing", **ctx)


# --------------------------------------------------------------------------- #
# fail-closed negatives
# --------------------------------------------------------------------------- #
def test_duplicate_row_id_is_rejected() -> None:
    rows = sl.load_source_ledger()
    rows.append(_row("topology-chain-pattern"))
    problems = _validate(rows)
    assert any(p.field == "source_id" and "duplicate" in p.reason for p in problems)


def test_unknown_category_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    row["category"] = "not-a-category"
    problems = _validate([row])
    assert any(p.field == "category" and "unknown category" in p.reason for p in problems)


def test_missing_required_category_is_rejected() -> None:
    rows = [r for r in sl.load_source_ledger() if r["category"] != "stochastic"]
    problems = _validate(rows)
    assert any(p.field == "category" and "stochastic" in p.reason for p in problems)


def test_unknown_disposition_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    row["disposition"] = "sort-of-mapped"
    problems = _validate([row])
    assert any(p.field == "disposition" for p in problems)


def test_missing_required_field_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    del row["source_selector"]
    problems = _validate([row])
    assert any(p.field == "source_selector" for p in problems)


def test_unknown_field_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    row["surprise"] = "value"
    problems = _validate([row])
    assert any(p.field == "surprise" for p in problems)


def test_source_drift_digest_mismatch_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    row["source_digest"] = "0" * 64
    problems = _validate([row])
    assert any(p.field == "source_digest" and "drift" in p.reason for p in problems)


def test_source_commit_mismatch_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    row["source_commit"] = "deadbeef" * 5
    problems = _validate([row])
    assert any(p.field == "source_commit" for p in problems)


def test_unqualified_source_path_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    row["source_path"] = "cyberbattle/not/a/real/file.py"
    problems = _validate([row])
    assert any(p.field == "source_path" for p in problems)


def test_omitting_source_digest_does_not_bypass_the_drift_join() -> None:
    # Regression: the qualification join must not be skippable by dropping the
    # optional-looking digest. source_digest is required, so omission fails closed.
    row = _row("topology-chain-pattern")
    del row["source_digest"]
    assert any(p.field == "source_digest" for p in _validate([row]))

    # And the source_path -> qualification join runs independently of the digest
    # value: an unqualified path is caught even when a (wrong) digest is present.
    row = _row("topology-chain-pattern")
    row["source_path"] = "cyberbattle/not/a/real/file.py"
    row["source_digest"] = "0" * 64
    assert any(p.field == "source_path" for p in _validate([row]))


def test_mapped_row_with_unresolvable_target_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    row["raes_target"] = "sdl:not_a_section"
    problems = _validate([row])
    assert any(p.field == "raes_target" and "does not resolve" in p.reason for p in problems)


def test_mapped_row_without_target_is_rejected() -> None:
    row = _row("topology-chain-pattern")
    del row["raes_target"]
    problems = _validate([row])
    assert any(p.field == "raes_target" for p in problems)


def test_excluded_row_with_target_is_rejected() -> None:
    row = _row("credential-cache-native")
    row["raes_target"] = "sdl:nodes"
    problems = _validate([row])
    assert any(p.field == "raes_target" for p in problems)


def test_loss_row_without_loss_ref_is_rejected() -> None:
    row = _row("stochastic-binding-loss")
    del row["loss_ref"]
    problems = _validate([row])
    assert any(p.field == "loss_ref" for p in problems)


def test_loss_row_with_wrong_tier_is_rejected() -> None:
    row = _row("stochastic-binding-loss")
    row["equivalence_tier"] = "outcome-equivalence"  # disclosure says deterministic-replay
    problems = _validate([row])
    assert any(p.field == "equivalence_tier" and "disagrees" in p.reason for p in problems)


def test_loss_row_with_unrecognized_tier_is_rejected() -> None:
    row = _row("stochastic-binding-loss")
    row["equivalence_tier"] = "vibes-equivalence"
    problems = _validate([row])
    assert any(p.field == "equivalence_tier" for p in problems)


def test_unreferenced_disclosure_is_rejected() -> None:
    ctx = _context()
    ctx["losses"] = {**ctx["losses"], "loss-orphan": "reproducibility"}
    problems = sl.validate_source_ledger(sl.load_source_ledger(), **ctx)
    assert any(p.row_id == "loss-orphan" and p.field == "loss_ref" for p in problems)


def test_native_leakage_marker_is_rejected() -> None:
    problems = sl.native_leakage_problems({"scenario": "nodes with credential_cache_matrix leaked"})
    assert any(p.field == "native-leakage" for p in problems)
    assert sl.native_leakage_problems({"scenario": "no native identifiers here"}) == []


# --------------------------------------------------------------------------- #
# strict JSONL parsing
# --------------------------------------------------------------------------- #
def test_strict_jsonl_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        sl.parse_ledger_rows('{"source_id": "a", "source_id": "b"}')


def test_strict_jsonl_rejects_non_object_row() -> None:
    with pytest.raises(ValueError, match="not a JSON object"):
        sl.parse_ledger_rows("[1, 2, 3]")


def test_strict_jsonl_rejects_non_finite_number() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        sl.parse_ledger_rows('{"n": NaN}')


# --------------------------------------------------------------------------- #
# cross-artifact selection joins
# --------------------------------------------------------------------------- #
def test_join_rejects_wrong_pinned_scenario_digest() -> None:
    bad = dataclasses.replace(sl.CYBERBATTLE_CHAIN, pinned_scenario_digest="sha256:" + "0" * 64)
    problems = sl.validate_selection_joins(bad)
    assert any(p.field == "digest" for p in problems)
    assert any(p.row_id in {"task", "spec"} and p.field.endswith("scenario_ref") for p in problems)


def test_join_rejects_stale_task_reference() -> None:
    bad = dataclasses.replace(sl.CYBERBATTLE_CHAIN, task_id="stale-task-id")
    problems = sl.validate_selection_joins(bad)
    assert any(p.row_id == "task" and p.field == "task_id" for p in problems)
    assert any(p.row_id == "spec" and p.field == "task_ref" for p in problems)


def test_join_rejects_wrong_scenario_and_spec_identity() -> None:
    bad = dataclasses.replace(sl.CYBERBATTLE_CHAIN, scenario_id="wrong-scn", spec_id="wrong-spec")
    problems = sl.validate_selection_joins(bad)
    assert any(p.row_id == "scenario" and p.field == "name" for p in problems)
    assert any(p.row_id == "spec" and p.field == "spec_id" for p in problems)


def test_protocol_artifact_join_detects_checksum_and_size_drift() -> None:
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
    assert sl._protocol_artifact_problems(good, body) == []

    drifted = SimpleNamespace(
        artifact_refs=[
            SimpleNamespace(role="protocol", checksum=SimpleNamespace(value="dead"), size_bytes=1)
        ]
    )
    problems = sl._protocol_artifact_problems(drifted, body)
    assert any("checksum" in p.reason for p in problems)
    assert any("size" in p.reason for p in problems)

    missing = SimpleNamespace(artifact_refs=[])
    assert any("no protocol" in p.reason for p in sl._protocol_artifact_problems(missing, body))


# --------------------------------------------------------------------------- #
# native-leakage classes (grounded in qualification provenance)
# --------------------------------------------------------------------------- #
def test_native_identifier_leakage_is_rejected_case_insensitively() -> None:
    assert sl.native_leakage_problems({"a": "leaks credential_cache_matrix here"})
    assert sl.native_leakage_problems({"a": "LEAKS CREDENTIAL_CACHE_MATRIX HERE"})
    assert sl.native_leakage_problems({"a": "nodes_privilegelevel exposed"})


def test_native_representation_leakage_is_rejected() -> None:
    for text in (
        "Traceback (most recent call last):",
        "x = ndarray(3)",
        "y = array([1, 2, 3])",
        "<cyberbattle.env.CyberBattleEnv object>",
        "repr is <foo object at 0x7f00>",
    ):
        assert sl.native_leakage_problems({"a": text}), text


def test_leakage_markers_are_grounded_in_qualification_provenance() -> None:
    markers = sl._native_identifier_markers()
    keys = sl.load_qualification()["runtime"]["smoke"]["observation_keys"]
    assert {key.lower() for key in keys} <= markers
    assert "credential_cache_matrix" in markers


def test_loss_heading_without_tier_is_preserved_and_flagged() -> None:
    # Regression: a disclosure heading with no equivalence-tier line must not be
    # silently dropped; it is preserved with an empty tier and fails closed.
    doc = "# losses\n\n## loss-no-tier\n\nNarrative with no tier line.\n"
    parsed = sl.parse_loss_disclosures(doc)
    assert parsed == {"loss-no-tier": ""}

    # A source row that references it (empty tier) is rejected, and the empty
    # disclosure itself is reported.
    row = _row("stochastic-binding-loss")
    row["loss_ref"] = "loss-no-tier"
    ctx = _context()
    ctx["losses"] = {"loss-no-tier": ""}
    problems = sl.validate_source_ledger([row], **ctx)
    assert any(p.row_id == "loss-no-tier" and p.field == "equivalence_tier" for p in problems)
