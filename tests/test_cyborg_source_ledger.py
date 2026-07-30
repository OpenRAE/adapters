"""Pinned CAGE-2 source-ledger evidence and fail-closed validation."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest
from raes_contracts.contracts import schema_bundle

import raes_adapters.cyborg.source_ledger as sl


def _context() -> dict[str, Any]:
    return {
        "qualification": sl.load_qualification(),
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


def test_checked_in_evidence_set_is_complete_and_valid() -> None:
    assert sl.validate_all() == []

    rows = sl.load_source_ledger()
    assert {row["source_family"] for row in rows} == set(sl.REQUIRED_SOURCE_FAMILIES)
    assert {row["fact_facet"] for row in rows} == set(sl.REQUIRED_FACT_FACETS)
    assert {row["disposition"] for row in rows} <= sl.DISPOSITIONS
    assert len({row["source_id"] for row in rows}) == len(rows)


def test_losses_bind_exactly_to_adr_069_equivalence_tiers() -> None:
    losses = sl.load_loss_disclosures()
    assert losses
    assert set().union(*losses.values()) <= sl.RECOGNIZED_EQUIVALENCE_TIERS

    referenced = {
        row["loss_disclosure"]
        for row in sl.load_source_ledger()
        if row["disposition"] == "loss-disclosed"
    }
    assert referenced == set(losses)


def test_legal_and_attribution_rows_are_reusable_qualification_evidence() -> None:
    legal_rows = [
        row for row in sl.load_source_ledger() if row["source_family"] == "provenance-licensing"
    ]
    assert legal_rows
    assert all(row["disposition"] == "out-of-scope" for row in legal_rows)
    assert all(
        row["qualification_ref"].startswith("qualification.json#/legal") for row in legal_rows
    )
    assert all("raes_target" not in row for row in legal_rows)


def test_strict_jsonl_rejects_duplicate_keys_non_objects_and_non_finite_numbers() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        sl.parse_ledger_rows('{"source_id": "a", "source_id": "b"}')
    with pytest.raises(ValueError, match="not a JSON object"):
        sl.parse_ledger_rows("[1, 2, 3]")
    with pytest.raises(ValueError, match="non-finite"):
        sl.parse_ledger_rows('{"n": NaN}')


def test_duplicate_id_unknown_field_and_blank_required_value_are_rejected() -> None:
    rows = sl.load_source_ledger()
    rows.append(copy.deepcopy(rows[0]))
    assert any(
        problem.field == "source_id" and "duplicate" in problem.reason
        for problem in _validate(rows)
    )

    row = _row("scenario-topology")
    row["metadata"] = {"hidden": "semantics"}
    assert any(
        problem.field == "metadata" and "unknown" in problem.reason for problem in _validate([row])
    )

    row = _row("scenario-topology")
    row["source_selector"] = " "
    assert any(problem.field == "source_selector" for problem in _validate([row]))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_family", "other-simulator"),
        ("fact_facet", "vibes"),
        ("disposition", "mostly-mapped"),
    ],
)
def test_unknown_classification_is_rejected(field: str, value: str) -> None:
    row = _row("scenario-topology")
    row[field] = value
    assert any(problem.field == field for problem in _validate([row]))


def test_missing_source_family_and_fact_facet_are_rejected() -> None:
    rows = [row for row in sl.load_source_ledger() if row["source_family"] != "observations"]
    assert any(
        problem.field == "source_family" and "observations" in problem.reason
        for problem in _validate(rows)
    )

    rows = [row for row in sl.load_source_ledger() if row["fact_facet"] != "admissibility"]
    assert any(
        problem.field == "fact_facet" and "admissibility" in problem.reason
        for problem in _validate(rows)
    )


def test_source_profile_path_and_digest_drift_are_rejected() -> None:
    row = _row("scenario-topology")
    row["source_repo"] = "https://example.invalid/not-the-qualified-source"
    assert any(problem.field == "source_repo" for problem in _validate([row]))

    row = _row("scenario-topology")
    row["source_version"] = "deadbeef" * 5
    assert any(problem.field == "source_version" for problem in _validate([row]))

    row = _row("scenario-topology")
    row["source_path"] = "not/qualified.py"
    assert any(problem.field == "source_path" for problem in _validate([row]))

    row = _row("scenario-topology")
    row["source_digest"] = "0" * 64
    assert any(problem.field == "source_digest" for problem in _validate([row]))


def test_raes_targets_resolve_only_through_the_published_schema_bundle() -> None:
    bundle = schema_bundle()
    assert sl.resolve_raes_target(
        "sdl-authoring-input-v1#/properties/nodes",
        bundle,
    )
    assert sl.resolve_raes_target(
        "experiment-authoring-input-v1#/properties/run_plan",
        bundle,
    )
    assert sl.resolve_raes_target("experiment-derived-measure-v1#", bundle)
    assert not sl.resolve_raes_target("not-a-contract#/properties/nodes", bundle)
    assert not sl.resolve_raes_target("sdl-authoring-input-v1#/properties/not_real", bundle)
    assert not sl.resolve_raes_target("sdl-authoring-input-v1#not-a-pointer", bundle)


def test_mapped_out_of_scope_and_loss_disclosed_shapes_fail_closed() -> None:
    row = _row("scenario-topology")
    del row["raes_target"]
    assert any(problem.field == "raes_target" for problem in _validate([row]))

    row = _row("scenario-topology")
    row["loss_disclosure"] = "loss-native-observation-boundary"
    row["equivalence_tiers"] = ["state/observation"]
    assert any(
        problem.field == "loss_disclosure" and "mapped row cannot declare a loss" in problem.reason
        for problem in _validate([row])
    )

    row = _row("legal-root-license")
    row["raes_target"] = "sdl-authoring-input-v1#/properties/nodes"
    assert any(problem.field == "raes_target" for problem in _validate([row]))

    row = _row("legal-root-license")
    row["loss_disclosure"] = "loss-native-observation-boundary"
    row["equivalence_tiers"] = ["state/observation"]
    assert any(
        problem.field == "loss_disclosure"
        and "out-of-scope row cannot declare a loss" in problem.reason
        for problem in _validate([row])
    )

    row = _row("evaluation-unbound-seed")
    del row["loss_disclosure"]
    assert any(problem.field == "loss_disclosure" for problem in _validate([row]))

    row = _row("evaluation-unbound-seed")
    row["equivalence_tiers"] = ["outcome/evaluation"]
    assert any(problem.field == "equivalence_tiers" for problem in _validate([row]))


def test_optional_fields_are_closed_and_typed() -> None:
    row = _row("legal-root-license")
    row["qualification_ref"] = 42
    assert any(problem.field == "qualification_ref" for problem in _validate([row]))

    row = _row("evaluation-unbound-seed")
    row["equivalence_tiers"] = "execution-control"
    assert any(problem.field == "equivalence_tiers" for problem in _validate([row]))

    row = _row("scenario-topology")
    row["loss_disclosure"] = []
    assert any(problem.field == "loss_disclosure" for problem in _validate([row]))


def test_loss_tier_disagreement_and_orphan_disclosure_are_rejected() -> None:
    row = _row("evaluation-unbound-seed")
    row["equivalence_tiers"] = ["outcome/evaluation"]
    problems = _validate([row])
    assert any(
        problem.field == "equivalence_tiers" and "disagrees" in problem.reason
        for problem in problems
    )

    context = _context()
    context["losses"] = {**context["losses"], "loss-orphan": {"contract"}}
    problems = sl.validate_source_ledger(sl.load_source_ledger(), **context)
    assert any(
        problem.row_id == "loss-orphan" and problem.field == "loss_disclosure"
        for problem in problems
    )


def test_qualification_json_pointers_are_machine_resolvable() -> None:
    qualification = sl.load_qualification()
    assert sl.resolve_qualification_ref("qualification.json#/legal", qualification)
    assert sl.resolve_qualification_ref(
        "qualification.json#/admissibility/decision",
        qualification,
    )
    assert not sl.resolve_qualification_ref("qualification.json#/not-there", qualification)
    assert not sl.resolve_qualification_ref("../qualification.json#/legal", qualification)


def _checkout_row(path: Path, selector: str) -> dict[str, str]:
    return {
        "source_id": path.stem,
        "source_path": path.name,
        "source_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_selector": selector,
    }


def test_source_checkout_verifies_python_line_and_text_selectors(tmp_path: Path) -> None:
    python_source = tmp_path / "source.py"
    python_source.write_text(
        "class Example:\n    def method(self) -> None:\n        pass\n",
        encoding="utf-8",
    )
    yaml_source = tmp_path / "scenario.yaml"
    yaml_source.write_text("Agents:\n  Blue:\n    actions:\n      - Sleep\n", encoding="utf-8")
    text_source = tmp_path / "README.md"
    text_source.write_text("# CAGE Challenge 2\n\nAttribution facts.\n", encoding="utf-8")

    rows = [
        _checkout_row(python_source, "python:Example.method"),
        _checkout_row(yaml_source, "lines:1-4"),
        _checkout_row(text_source, "text:CAGE Challenge 2"),
    ]
    assert sl.validate_source_checkout(tmp_path, rows) == []


def test_source_checkout_rejects_unreachable_selector_digest_drift_and_escape(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("class Example:\n    pass\n", encoding="utf-8")

    row = _checkout_row(source, "python:Missing")
    assert any(
        problem.field == "source_selector"
        for problem in sl.validate_source_checkout(tmp_path, [row])
    )

    row = _checkout_row(source, "python:Example")
    row["source_digest"] = "0" * 64
    assert any(
        problem.field == "source_digest" for problem in sl.validate_source_checkout(tmp_path, [row])
    )

    row = _checkout_row(source, "python:Example")
    row["source_path"] = "../source.py"
    assert any(
        problem.field == "source_path" for problem in sl.validate_source_checkout(tmp_path, [row])
    )


def test_native_payload_fields_cannot_be_added_to_rows() -> None:
    for field in ("native_state", "observation_values", "reward_vector", "action_id"):
        row = _row("scenario-topology")
        row[field] = "forbidden"
        assert any(
            problem.field == field and "unknown" in problem.reason for problem in _validate([row])
        )
