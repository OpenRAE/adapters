"""Scenario + pinned source-mapping ledger evidence, shared across backends.

The CyberBattleSim (#26) and NASim (#33) evidence sets are validated by the same
deterministic machinery in :mod:`raes_adapters._scenario_ledger`. Each backend
authors an RAES SDL scenario carrying portable topology/objective truth only;
reward, evaluator, termination, and stochastic controls live in the companion
published experiment contracts. Each source ledger records how each pinned source
fact reaches a portable RAES surface, or why it does not, and every disclosed
loss binds the ADR-069 equivalence tier it weakens.

This suite is parameterized over both backends off their bound
``ScenarioLedger`` objects, so a second backend is a new ``Case`` rather than a
copied test file. The negative tests are the fail-closed guarantee: each proves
the validator rejects a specific corruption (source drift, a missing category, a
duplicate row, an unresolvable target, an undisclosed loss, native leakage), so
CI fails when a checked-in evidence set drifts into that state.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from raes_adapters import _scenario_ledger as core
from raes_adapters.cyberbattlesim import scenario_ledger as csl
from raes_adapters.nasim import scenario_ledger as nsl


@dataclass(frozen=True)
class Case:
    """Backend-specific expectations for the shared scenario-ledger contract."""

    name: str
    ledger: core.ScenarioLedger
    scenario_name: str
    pinned_digest: str
    losses: dict[str, str]
    metrics: list[str]
    target_run_count: int
    max_steps: int
    stochastic_controls: int
    mapped_row: str
    excluded_row: str
    loss_row: str
    loss_row_wrong_tier: str
    missing_category: str
    native_symbol_example: str
    native_object_prefix: str


CYBERBATTLE = Case(
    name="cyberbattlesim",
    ledger=csl.LEDGER,
    scenario_name="cyberbattlesim-chain",
    pinned_digest=csl.PINNED_SCENARIO_DIGEST,
    losses={
        "loss-no-source-artifact": "reproducibility",
        "loss-unbound-random-streams": "deterministic-replay",
        "loss-abstracted-topology": "outcome-equivalence",
        "loss-benchmark-defects": "outcome-equivalence",
    },
    metrics=[
        "cumulative_attacker_reward",
        "network_availability",
        "steps_to_termination",
        "terminal_cause",
    ],
    target_run_count=10,
    max_steps=600,
    stochastic_controls=4,
    mapped_row="topology-chain-pattern",
    excluded_row="credential-cache-native",
    loss_row="stochastic-binding-loss",
    loss_row_wrong_tier="outcome-equivalence",
    missing_category="stochastic",
    native_symbol_example="credential_cache_matrix",
    native_object_prefix="<cyberbattle",
)

NASIM = Case(
    name="nasim",
    ledger=nsl.LEDGER,
    scenario_name="nasim-tiny",
    pinned_digest=nsl.PINNED_SCENARIO_DIGEST,
    losses={
        "loss-unbound-action-rng": "deterministic-replay",
        "loss-apparatus-reconstruction": "reproducibility",
    },
    metrics=[
        "cumulative_attacker_reward",
        "goal_reached",
        "steps_to_termination",
        "terminal_cause",
    ],
    target_run_count=1,
    max_steps=1000,
    stochastic_controls=2,
    mapped_row="topology-hosts",
    excluded_row="identity-native-host-state",
    loss_row="stochastic-binding-loss",
    loss_row_wrong_tier="outcome-equivalence",
    missing_category="stochastic",
    native_symbol_example="FlatActionSpace",
    native_object_prefix="<nasim",
)

CASES = [CYBERBATTLE, NASIM]


@pytest.fixture(params=CASES, ids=[c.name for c in CASES])
def case(request: pytest.FixtureRequest) -> Case:
    return request.param


def _row(case: Case, source_id: str) -> dict[str, Any]:
    for row in case.ledger.load_source_ledger():
        if row["source_id"] == source_id:
            return copy.deepcopy(row)
    raise AssertionError(f"no such row: {source_id}")


def _validate(
    case: Case, rows: list[dict[str, Any]], losses: dict[str, str] | None = None
) -> list[core.LedgerProblem]:
    return case.ledger.validate_source_ledger(
        rows,
        scenario=case.ledger.load_scenario(),
        losses=case.ledger.load_loss_disclosures() if losses is None else losses,
    )


# --------------------------------------------------------------------------- #
# positive: the checked-in evidence set validates end to end
# --------------------------------------------------------------------------- #
def test_sdl_scenario_validates_instantiates_and_admits(case: Case) -> None:
    scenario = case.ledger.load_scenario()
    assert scenario.name == case.scenario_name
    assert scenario.semantic_validated is True
    digest = case.ledger.scenario_canonical_digest()
    assert digest == case.pinned_digest
    assert digest.startswith("sha256:")


def test_scenario_pipeline_compiles_with_pinned_release(case: Case) -> None:
    # parse -> instantiate -> pinned canonical digest -> compile -> admit.
    assert case.ledger.validate_scenario_pipeline() == []


def test_companion_experiment_contracts_validate(case: Case) -> None:
    task = case.ledger.load_experiment_task()
    spec = case.ledger.load_experiment_spec()
    assert task.scenario_ref.ref_digest == case.pinned_digest
    assert sorted(task.evaluation_protocol.metric_definitions) == sorted(case.metrics)
    # Stochastic controls stay descriptive: no executable random-stream binding,
    # so the determinism loss is retained rather than silently claimed.
    assert spec.run_plan.target_run_count == case.target_run_count
    assert spec.run_plan.episode_control.max_steps == case.max_steps
    assert len(spec.run_plan.stochastic_controls) == case.stochastic_controls
    assert all(c.executable_binding is None for c in spec.run_plan.stochastic_controls)


def test_full_evidence_set_is_valid(case: Case) -> None:
    assert case.ledger.validate_all() == []


def test_selection_joins_pass_for_the_checked_in_selection(case: Case) -> None:
    assert case.ledger.validate_selection_joins() == []
    # The extension seam is a descriptor: the parameterized entry point accepts
    # the selection object, so a second scenario is another descriptor, not a
    # validator edit.
    assert isinstance(case.ledger.selection, core.EvidenceSelection)
    assert case.ledger.validate_all(case.ledger.selection) == []


def test_ledger_covers_every_required_category(case: Case) -> None:
    rows = case.ledger.load_source_ledger()
    assert {row["category"] for row in rows} == set(core.REQUIRED_CATEGORIES)
    assert {row["disposition"] for row in rows} <= core.DISPOSITIONS
    assert len({row["source_id"] for row in rows}) == len(rows)


def test_loss_disclosures_bind_recognized_tiers(case: Case) -> None:
    losses = case.ledger.load_loss_disclosures()
    assert losses == case.losses
    assert set(losses.values()) <= core.RECOGNIZED_EQUIVALENCE_TIERS


# --------------------------------------------------------------------------- #
# target resolution
# --------------------------------------------------------------------------- #
def test_target_resolution_positive_and_negative(case: Case) -> None:
    scenario = case.ledger.load_scenario()

    def resolves(target: str) -> bool:
        return case.ledger.resolve_target(target, scenario=scenario)

    assert resolves("sdl:nodes")
    assert resolves("sdl:agents.attacker")
    assert resolves("contract:ExperimentTaskModel.evaluation_protocol")
    assert resolves("contract:ExperimentSpecModel.run_plan.episode_control")
    assert resolves("resource:qualification.json")

    assert not resolves("sdl:not_a_section")
    assert not resolves("sdl:agents.ghost")
    assert not resolves("contract:NotARealModel.foo")
    assert not resolves("contract:ExperimentTaskModel.nope")
    assert not resolves("resource:missing-file.json")
    assert not resolves("mystery:thing")


# --------------------------------------------------------------------------- #
# fail-closed negatives
# --------------------------------------------------------------------------- #
def test_duplicate_row_id_is_rejected(case: Case) -> None:
    rows = case.ledger.load_source_ledger()
    rows.append(_row(case, case.mapped_row))
    problems = _validate(case, rows)
    assert any(p.field == "source_id" and "duplicate" in p.reason for p in problems)


def test_unknown_category_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    row["category"] = "not-a-category"
    problems = _validate(case, [row])
    assert any(p.field == "category" and "unknown category" in p.reason for p in problems)


def test_missing_required_category_is_rejected(case: Case) -> None:
    rows = [r for r in case.ledger.load_source_ledger() if r["category"] != case.missing_category]
    problems = _validate(case, rows)
    assert any(p.field == "category" and case.missing_category in p.reason for p in problems)


def test_unknown_disposition_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    row["disposition"] = "sort-of-mapped"
    problems = _validate(case, [row])
    assert any(p.field == "disposition" for p in problems)


def test_missing_required_field_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    del row["source_selector"]
    problems = _validate(case, [row])
    assert any(p.field == "source_selector" for p in problems)


def test_unknown_field_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    row["surprise"] = "value"
    problems = _validate(case, [row])
    assert any(p.field == "surprise" for p in problems)


def test_source_drift_digest_mismatch_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    row["source_digest"] = "0" * 64
    problems = _validate(case, [row])
    assert any(p.field == "source_digest" and "drift" in p.reason for p in problems)


def test_source_commit_mismatch_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    row["source_commit"] = "deadbeef" * 5
    problems = _validate(case, [row])
    assert any(p.field == "source_commit" for p in problems)


def test_unqualified_source_path_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    row["source_path"] = "not/a/real/file.py"
    problems = _validate(case, [row])
    assert any(p.field == "source_path" for p in problems)


def test_omitting_source_digest_does_not_bypass_the_drift_join(case: Case) -> None:
    # Regression: the qualification join must not be skippable by dropping the
    # optional-looking digest. source_digest is required, so omission fails closed.
    row = _row(case, case.mapped_row)
    del row["source_digest"]
    assert any(p.field == "source_digest" for p in _validate(case, [row]))

    # And the source_path -> qualification join runs independently of the digest
    # value: an unqualified path is caught even when a (wrong) digest is present.
    row = _row(case, case.mapped_row)
    row["source_path"] = "not/a/real/file.py"
    row["source_digest"] = "0" * 64
    assert any(p.field == "source_path" for p in _validate(case, [row]))


def test_mapped_row_with_unresolvable_target_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    row["raes_target"] = "sdl:not_a_section"
    problems = _validate(case, [row])
    assert any(p.field == "raes_target" and "does not resolve" in p.reason for p in problems)


def test_mapped_row_without_target_is_rejected(case: Case) -> None:
    row = _row(case, case.mapped_row)
    del row["raes_target"]
    problems = _validate(case, [row])
    assert any(p.field == "raes_target" for p in problems)


def test_excluded_row_with_target_is_rejected(case: Case) -> None:
    row = _row(case, case.excluded_row)
    row["raes_target"] = "sdl:nodes"
    problems = _validate(case, [row])
    assert any(p.field == "raes_target" for p in problems)


def test_loss_row_without_loss_ref_is_rejected(case: Case) -> None:
    row = _row(case, case.loss_row)
    del row["loss_ref"]
    problems = _validate(case, [row])
    assert any(p.field == "loss_ref" for p in problems)


def test_loss_row_with_wrong_tier_is_rejected(case: Case) -> None:
    row = _row(case, case.loss_row)
    row["equivalence_tier"] = case.loss_row_wrong_tier
    problems = _validate(case, [row])
    assert any(p.field == "equivalence_tier" and "disagrees" in p.reason for p in problems)


def test_loss_row_with_unrecognized_tier_is_rejected(case: Case) -> None:
    row = _row(case, case.loss_row)
    row["equivalence_tier"] = "vibes-equivalence"
    problems = _validate(case, [row])
    assert any(p.field == "equivalence_tier" for p in problems)


def test_unreferenced_disclosure_is_rejected(case: Case) -> None:
    losses = {**case.ledger.load_loss_disclosures(), "loss-orphan": "reproducibility"}
    problems = _validate(case, case.ledger.load_source_ledger(), losses=losses)
    assert any(p.row_id == "loss-orphan" and p.field == "loss_ref" for p in problems)


def test_native_leakage_marker_is_rejected(case: Case) -> None:
    text = f"portable text that leaks {case.native_symbol_example} into content"
    assert any(
        p.field == "native-leakage" for p in case.ledger.native_leakage_problems({"a": text})
    )
    assert case.ledger.native_leakage_problems({"a": "no native identifiers here"}) == []


# --------------------------------------------------------------------------- #
# strict JSONL parsing
# --------------------------------------------------------------------------- #
def test_strict_jsonl_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        core.parse_ledger_rows('{"source_id": "a", "source_id": "b"}')


def test_strict_jsonl_rejects_non_object_row() -> None:
    with pytest.raises(ValueError, match="not a JSON object"):
        core.parse_ledger_rows("[1, 2, 3]")


def test_strict_jsonl_rejects_non_finite_number() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        core.parse_ledger_rows('{"n": NaN}')


# --------------------------------------------------------------------------- #
# cross-artifact selection joins
# --------------------------------------------------------------------------- #
def test_join_rejects_wrong_pinned_scenario_digest(case: Case) -> None:
    bad = case.ledger.selection._replace(pinned_scenario_digest="sha256:" + "0" * 64)
    problems = case.ledger.validate_selection_joins(bad)
    assert any(p.field == "digest" for p in problems)
    assert any(p.row_id in {"task", "spec"} and p.field.endswith("scenario_ref") for p in problems)


def test_join_rejects_stale_task_reference(case: Case) -> None:
    bad = case.ledger.selection._replace(task_id="stale-task-id")
    problems = case.ledger.validate_selection_joins(bad)
    assert any(p.row_id == "task" and p.field == "task_id" for p in problems)
    assert any(p.row_id == "spec" and p.field == "task_ref" for p in problems)


def test_join_rejects_wrong_scenario_and_spec_identity(case: Case) -> None:
    bad = case.ledger.selection._replace(scenario_id="wrong-scn", spec_id="wrong-spec")
    problems = case.ledger.validate_selection_joins(bad)
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
    assert core._protocol_artifact_problems(good, body) == []

    drifted = SimpleNamespace(
        artifact_refs=[
            SimpleNamespace(role="protocol", checksum=SimpleNamespace(value="dead"), size_bytes=1)
        ]
    )
    problems = core._protocol_artifact_problems(drifted, body)
    assert any("checksum" in p.reason for p in problems)
    assert any("size" in p.reason for p in problems)

    missing = SimpleNamespace(artifact_refs=[])
    assert any("no protocol" in p.reason for p in core._protocol_artifact_problems(missing, body))


def test_protocol_join_follows_the_selection_resource(case: Case) -> None:
    # The protocol artifact is validated against selection.protocol_resource, not
    # a fixed backend default, so a second selection carrying its own protocol is
    # checked against that protocol. Pointing the resource at a different file
    # (whose bytes do not match the task's pinned protocol checksum/size) must
    # fail the join, proving the extension seam is honored.
    bad = case.ledger.selection._replace(protocol_resource="qualification.json")
    problems = case.ledger.validate_selection_joins(bad)
    assert any(p.row_id == "task" and p.field == "artifact_refs" for p in problems)


# --------------------------------------------------------------------------- #
# native-leakage classes (grounded in provenance)
# --------------------------------------------------------------------------- #
def test_native_identifier_leakage_is_rejected_case_insensitively(case: Case) -> None:
    example = case.native_symbol_example
    assert case.ledger.native_leakage_problems({"a": f"leaks {example} here"})
    assert case.ledger.native_leakage_problems({"a": f"LEAKS {example.upper()} HERE"})


def test_native_representation_leakage_is_rejected(case: Case) -> None:
    for text in (
        "Traceback (most recent call last):",
        "x = ndarray(3)",
        "y = array([1, 2, 3])",
        f"{case.native_object_prefix}.env.Env object>",
        "repr is <foo object at 0x7f00>",
    ):
        assert case.ledger.native_leakage_problems({"a": text}), text


def test_cyberbattlesim_markers_grounded_in_observation_keys() -> None:
    markers = CYBERBATTLE.ledger.native_identifier_markers()
    keys = CYBERBATTLE.ledger.load_qualification()["runtime"]["smoke"]["observation_keys"]
    assert {key.lower() for key in keys} <= markers
    assert "credential_cache_matrix" in markers


def test_nasim_markers_are_grounded_without_observation_keys() -> None:
    # NASim's selected observation is a keyless flat Box, so the qualification
    # record carries no observation keys; the scan grounds in native action-class
    # symbols plus the common representation markers instead.
    smoke = NASIM.ledger.load_qualification()["runtime"]["smoke"]
    assert "observation_keys" not in smoke
    markers = NASIM.ledger.native_identifier_markers()
    assert {"servicescan", "flatactionspace", "privilegeescalation"} <= markers


def test_loss_heading_without_tier_is_preserved_and_flagged(case: Case) -> None:
    # Regression: a disclosure heading with no equivalence-tier line must not be
    # silently dropped; it is preserved with an empty tier and fails closed.
    doc = "# losses\n\n## loss-no-tier\n\nNarrative with no tier line.\n"
    parsed = core.parse_loss_disclosures(doc)
    assert parsed == {"loss-no-tier": ""}

    # A source row that references it (empty tier) is rejected, and the empty
    # disclosure itself is reported.
    row = _row(case, case.loss_row)
    row["loss_ref"] = "loss-no-tier"
    problems = _validate(case, [row], losses={"loss-no-tier": ""})
    assert any(p.row_id == "loss-no-tier" and p.field == "equivalence_tier" for p in problems)
