"""Frozen CAGE-2 outcome-reproduction study and offline derivation.

This module is deliberately backend-local.  RAES models remain the authority
for experiment evidence and runs; the dictionaries here are immutable indexes
for the issue-22 research export rather than another portable contract family.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import platform
import statistics
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout, suppress
from dataclasses import dataclass, replace
from importlib import metadata
from pathlib import Path
from statistics import NormalDist
from typing import cast

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentArtifactRefModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    validate_experiment_run_against_task,
)
from raes_contracts.participant_configuration import (  # type: ignore[import-untyped]
    validate_participant_configuration_selection,
)
from raes_operations.run_artifacts import (  # type: ignore[import-untyped]
    atomic_write_json_artifact,
)

from .driver import CyborgDriver, SourceInstalledCyborgDriver
from .researcher import (
    EpisodeEvidence,
    RunControls,
    archival_run,
    execute_episode_series,
)

_INVALID_JSON = "invalid JSON artifact"
_DISPOSITIONS = ("excluded", "failed", "invalid", "valid")
_RED_VARIANTS = ("b-line", "meander", "sleep")
_TRIAL_LENGTHS = (30, 50, 100)
_TIERS = (
    "authored-source",
    "contract",
    "execution-control",
    "state/observation",
    "outcome/evaluation",
    "disclosure",
)
_SCORE_METRIC_ID = "cage2-cumulative-blue-reward"
_SOURCE_COMMIT = "26ce1c1253fa9e2e73f25e6a7f2da32860c11257"
_PAPER_SHA256 = "45a6e564da6dff67453ec75585e847228a7f407641f250f4abe28d1f29406f29"
_PRIVATE_KEY_MARKERS = (
    " ".join(("BEGIN", "OPENSSH", "PRIVATE", "KEY")),
    " ".join(("BEGIN", "PRIVATE", "KEY")),
)
_FORBIDDEN_TEXT = (
    "Traceback (most recent call last):",
    *_PRIVATE_KEY_MARKERS,
    "/home/",
)
_FORBIDDEN_FIELDS = frozenset(
    {
        "action_id",
        "action_mask",
        "hidden_truth",
        "native_observation",
        "native_state",
        "random_state",
        "reward_vector",
    }
)
_MAX_PUBLIC_FILE_BYTES = 500 * 1024
_MAX_DECOMPRESSED_JSON_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ReproductionSelection:
    """One immutable backend-local study selection."""

    frozen_revision: str
    episodes_per_condition: int
    seed: int
    trial_lengths: tuple[int, ...]
    red_variants: tuple[str, ...]
    retry_limit: int

    def with_cardinality_for_test(self, episodes: int) -> ReproductionSelection:
        """Return a reduced-cardinality selection for the identical test path."""

        if type(episodes) is not int or episodes < 1:
            raise ValueError("test cardinality is invalid")
        return replace(
            self,
            frozen_revision=f"{self.frozen_revision}-test-{episodes}",
            episodes_per_condition=episodes,
        )


FROZEN_SELECTION = ReproductionSelection(
    frozen_revision="cage2-26ce1c1-ccs-sleeper-v1",
    episodes_per_condition=1000,
    seed=153,
    trial_lengths=_TRIAL_LENGTHS,
    red_variants=_RED_VARIANTS,
    retry_limit=1,
)

_PUBLISHED_CONDITION_MEANS: dict[tuple[int, str], tuple[float, int]] = {
    (30, "b-line"): (-218.65, 2),
    (30, "meander"): (-39.31, 2),
    (30, "sleep"): (0.0, 0),
    (50, "b-line"): (-480.17, 2),
    (50, "meander"): (-267.6, 1),
    (50, "sleep"): (0.0, 0),
    (100, "b-line"): (-1134.03, 2),
    (100, "meander"): (-972.43, 2),
    (100, "sleep"): (0.0, 0),
}

_INPUT_PATHS: dict[str, str] = {
    "authored-scenario": "src/raes_adapters/cyborg/scenario/cage2-scenario2.sdl.yaml",
    "module-lock": "src/raes_adapters/cyborg/scenario/raes.lock.json",
    "pack-manifest": (
        "src/raes_adapters/cyborg/examples/cage2-research/pack.content-manifest.json"
    ),
    "experiment-authoring-input": (
        "src/raes_adapters/cyborg/examples/cage2-research/experiment/cage2-research.spec.exp.json"
    ),
    "experiment-task": (
        "src/raes_adapters/cyborg/examples/cage2-research/experiment/cage2-research.task.exp.json"
    ),
    "blue-manifest": (
        "src/raes_adapters/cyborg/examples/cage2-research/participant/"
        "cyborg-blue-sleep-policy.manifest.json"
    ),
    "blue-selection": (
        "src/raes_adapters/cyborg/examples/cage2-research/participant/"
        "cyborg-blue-sleep-policy.selection.json"
    ),
    "blue-configuration": (
        "src/raes_adapters/cyborg/examples/cage2-research/participant/"
        "cyborg-blue-sleep-policy.configuration.json"
    ),
    "qualification": "src/raes_adapters/cyborg/qualification.json",
    "mapping-ledger": "src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl",
    "loss-disclosures": "src/raes_adapters/cyborg/mapping/cage2-loss-disclosures.md",
}
_FROZEN_ARTIFACT_FACTS: dict[str, tuple[str, int]] = {
    "authored-scenario": (
        "14da37a9e4c4e09136fe7d6fc10a75d515ac29243bfe2b98cf81839847b3a544",
        27339,
    ),
    "blue-configuration": (
        "c31948db14751cf80dd66726c34d7471786eabf3d934658f1d40248fb065f918",
        997,
    ),
    "blue-manifest": (
        "73cf1016f04ead0741755dd98dd1a1e4cc2927b14e948246294a7bd1a28cd26b",
        2271,
    ),
    "blue-selection": (
        "e5a8dfb2134a708bac9b479fd23661948d6c617f7bc0b8855683445645ec3791",
        1166,
    ),
    "experiment-authoring-input": (
        "7a0140d85ae0114d76b4248197d391661d3596dffcd82464022e31b83b1caa0e",
        3102,
    ),
    "experiment-task": (
        "e04872ff2c8308741cd149b7403c968b0cf64d9a46c6f5ba55c8c73c21f000ae",
        2621,
    ),
    "loss-disclosures": (
        "cb0ebf48ae406140d4ca8657498107e825879c4002e0ae7394cabde1196fbf58",
        3166,
    ),
    "mapping-ledger": (
        "e3ab5e419ecc1aed4b7277188fd67a0a12c2228dbd0b5e67396fa955affadb8f",
        37320,
    ),
    "module-lock": (
        "783160e17db156bc5d7e7dedd5844d3f38767a483e1b9b5988ed7149e196916e",
        56,
    ),
    "pack-manifest": (
        "27d6a1bc57ca89194a27d873179654b424f25c9c65a00c4e19ad32f87b3c9c8e",
        7169,
    ),
    "qualification": (
        "8dd70165e8f0dbf4a804cb287058dd7a5fddaefc50144d3e4c21b04530a958a4",
        19427,
    ),
}
_FROZEN_CONTRACT_DIGESTS = {
    "experiment_spec": "f0ed630c86d997e889fb9e57d76383c5b0fa8fda8ae61c2b83b9572d1dd8e88b",
    "experiment_task": "d5f317677eb481fcb7f60d7e2eae4a9ce93253b4e87a59f06ba85543b6efdafc",
    "participant_manifest": "bb8bd43edff6d011808b8c09b72bcf63e759cc761d2e1807e259cdbd790cf43e",
    "participant_selection": "fa84715499b4e91814b3da7898718dd2a61ffc239c7c4e010bdcd1ea8f335740",
    "participant_configuration": (
        "a4c3e209b784123250d72a454f369f093a11987ad3782e690ca9e17c6e342d0c"
    ),
}


def canonical_json_bytes(payload: object) -> bytes:
    """Return the sole issue-local canonical JSON byte representation."""

    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def sha256_payload(payload: object) -> str:
    """Hash one issue-local payload canonically."""

    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_constant(_value: str) -> object:
    raise ValueError(_INVALID_JSON)


def _closed_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_INVALID_JSON)
        result[key] = value
    return result


def _load_strict_json_value(path: Path) -> object:
    """Load duplicate-key-free finite JSON, including deterministic gzip JSON."""

    try:
        raw = path.read_bytes()
        if path.name.endswith(".json.gz"):
            raw = gzip.decompress(raw)
            if len(raw) > _MAX_DECOMPRESSED_JSON_BYTES:
                raise ValueError(_INVALID_JSON)
        value = json.loads(
            raw,
            object_pairs_hook=_closed_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, ValueError, gzip.BadGzipFile) as error:
        raise ValueError(_INVALID_JSON) from error
    return value


def load_strict_json(path: Path) -> dict[str, object]:
    """Load a duplicate-key-free finite JSON object."""

    value = _load_strict_json_value(path)
    if not isinstance(value, dict):
        raise ValueError(_INVALID_JSON)
    return cast(dict[str, object], value)


def _condition_id(trial_length: int, red_variant: str) -> str:
    return f"steps-{trial_length:03d}--red-{red_variant}"


def _schedule(selection: ReproductionSelection) -> list[dict[str, object]]:
    schedule: list[dict[str, object]] = []
    ordinal = 0
    for trial_length in selection.trial_lengths:
        for red_variant in selection.red_variants:
            condition_id = _condition_id(trial_length, red_variant)
            for episode in range(1, selection.episodes_per_condition + 1):
                ordinal += 1
                slot_id = f"cage2-slot-{ordinal:05d}"
                schedule.append(
                    {
                        "slot_id": slot_id,
                        "condition_id": condition_id,
                        "trial_length": trial_length,
                        "red_variant": red_variant,
                        "episode_ordinal": episode,
                        "study_stream_ordinal": ordinal,
                        "eligibility": "scheduled",
                        "run_id": f"{slot_id}-attempt-01",
                        "attempt_sequence": 1,
                    }
                )
    return schedule


def _schedule_partitions(selection: ReproductionSelection) -> list[dict[str, object]]:
    schedule = _schedule(selection)
    partitions: list[dict[str, object]] = []
    offset = 0
    for trial_length in selection.trial_lengths:
        for red_variant in selection.red_variants:
            entries = schedule[offset : offset + selection.episodes_per_condition]
            condition_id = _condition_id(trial_length, red_variant)
            partitions.append(
                {
                    "condition_id": condition_id,
                    "path": f"plans/{condition_id}.json",
                    "slot_count": len(entries),
                    "first_slot_id": entries[0]["slot_id"],
                    "last_slot_id": entries[-1]["slot_id"],
                    "sha256": sha256_payload(entries),
                }
            )
            offset += selection.episodes_per_condition
    return partitions


def _artifact_refs(repo_root: Path) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for artifact_id, relative in sorted(_INPUT_PATHS.items()):
        path = repo_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError("frozen input is unavailable")
        digest = _sha256_file(path)
        size = path.stat().st_size
        if (digest, size) != _FROZEN_ARTIFACT_FACTS[artifact_id]:
            raise ValueError("frozen input identity is invalid")
        refs.append(
            {
                "artifact_id": artifact_id,
                "path": relative,
                "sha256": digest,
                "size_bytes": size,
            }
        )
    return refs


def _contract_payloads(repo_root: Path) -> dict[str, object]:
    contracts: dict[str, object] = {
        "experiment_spec": load_strict_json(repo_root / _INPUT_PATHS["experiment-authoring-input"]),
        "experiment_task": load_strict_json(repo_root / _INPUT_PATHS["experiment-task"]),
        "participant_manifest": load_strict_json(repo_root / _INPUT_PATHS["blue-manifest"]),
        "participant_selection": load_strict_json(repo_root / _INPUT_PATHS["blue-selection"]),
        "participant_configuration": load_strict_json(
            repo_root / _INPUT_PATHS["blue-configuration"]
        ),
    }
    if {
        name: sha256_payload(payload) for name, payload in contracts.items()
    } != _FROZEN_CONTRACT_DIGESTS:
        raise ValueError("frozen contract identity is invalid")
    return contracts


def _expected_artifact_refs() -> list[dict[str, object]]:
    return [
        {
            "artifact_id": artifact_id,
            "path": _INPUT_PATHS[artifact_id],
            "sha256": _FROZEN_ARTIFACT_FACTS[artifact_id][0],
            "size_bytes": _FROZEN_ARTIFACT_FACTS[artifact_id][1],
        }
        for artifact_id in sorted(_INPUT_PATHS)
    ]


def _source_ledger(artifacts: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "source": {
            "repository": "https://github.com/cage-challenge/cage-challenge-2",
            "commit": _SOURCE_COMMIT,
            "profile_id": "cage2-cyborg-2.1-source-26ce1c1",
        },
        "protocol_source_facts": {
            "qualified_evaluator": {
                "artifact_ref": "qualification",
                "path": "CybORG/CybORG/Evaluation/evaluation.py",
                "episode_count": 100,
                "trial_lengths": [30, 50, 100],
                "red_variants": ["B_lineAgent", "RedMeanderAgent", "SleepAgent"],
                "seed_binding": None,
            },
            "public_validation": {
                "artifact_ref": "qualification",
                "path": "README.md",
                "episode_count": 1000,
                "seed_statement": "random.seed(153)",
                "confidence_interval_statement": "95-percent-confidence-intervals",
            },
            "paper": {
                "identifier": "arXiv:2309.07388v1",
                "url": "https://arxiv.org/pdf/2309.07388v1",
                "sha256": _PAPER_SHA256,
            },
        },
        "artifact_refs": [dict(item) for item in artifacts],
        "loss_refs": [
            "loss-blue-policy-artifact-unbound",
            "loss-evaluation-seed-unbound",
            "loss-native-observation-boundary",
            "loss-remove-success-misreport",
            "loss-wrapper-termination-cutoff",
        ],
        "exclusions": [
            "BlueLoadAgent-without-model-bytes",
            "private-or-unpublished-submitted-agent-artifacts",
        ],
    }


def _published_results() -> dict[str, object]:
    conditions = []
    for trial_length in _TRIAL_LENGTHS:
        for red_variant in _RED_VARIANTS:
            value, decimals = _PUBLISHED_CONDITION_MEANS[(trial_length, red_variant)]
            conditions.append(
                {
                    "condition_id": _condition_id(trial_length, red_variant),
                    "mean": value,
                    "display_decimals": decimals,
                    "bounded_margin": max(1.0, abs(value) * 0.01),
                }
            )
    return {
        "result_identity": "cage2-readme-leaderboard-ccs-sleeper",
        "agent_label": "CCS Sleeper",
        "technique_label": "Sleeping Agent",
        "agent_artifact_identity": "unavailable",
        "conditions": conditions,
        "primary_total": -3112.2,
        "primary_total_interval_95": [-3118.87, -3105.53],
        "reported_interval_half_width": 6.67,
    }


def _declaration(
    selection: ReproductionSelection,
    artifacts: list[dict[str, object]],
    contracts: Mapping[str, object],
) -> dict[str, object]:
    return {
        "frozen_revision": selection.frozen_revision,
        "source_profile": "cage2-cyborg-2.1-source-26ce1c1",
        "source_commit": _SOURCE_COMMIT,
        "baseline": {
            "observed_implementation": "cyborg-blue-sleep-policy",
            "observed_behavior": "participant.action-contract.sleep",
            "published_result_identity": "cage2-readme-leaderboard-ccs-sleeper",
            "identity_relation": "behavioral-reconstruction-not-agent-artifact-identity",
            "loss_ref": "loss-blue-policy-artifact-unbound",
        },
        "artifacts": artifacts,
        "published_contracts": dict(contracts),
        "trial_lengths": list(selection.trial_lengths),
        "red_variants": list(selection.red_variants),
        "episodes_per_condition": selection.episodes_per_condition,
        "schedule_partitions": _schedule_partitions(selection),
        "seed_policy": {
            "api": "random.seed",
            "initialization_scope": "study",
            "owner": "python-random",
            "reset_behavior": "continue-stream-across-episode-reset",
            "seed": selection.seed,
            "serialization": "trial-length-then-red-variant-then-episode",
        },
        "attempt_policy": {
            "retry_limit": selection.retry_limit,
            "selection": "first-valid-attempt-in-attempt-sequence",
            "terminal_dispositions": list(_DISPOSITIONS),
            "missing_scores": "never-imputed",
        },
        "aggregation": {
            "score_metric_id": _SCORE_METRIC_ID,
            "condition_estimator": "arithmetic-mean",
            "sample_variance_divisor": "n-1",
            "interval": "two-sided-normal-approximation-95-percent",
            "critical_value": NormalDist().inv_cdf(0.975),
            "primary_estimand": "sum-of-nine-condition-means",
            "primary_standard_error": "sqrt-sum-of-independent-condition-mean-variances",
            "finite_values_required": True,
            "minimum_eligible_per_condition": selection.episodes_per_condition,
            "rounding": "binary64-calculation-json-number-output-published-display-only",
            "method_authority": "adapter-study-predeclared-method-not-attributed-to-paper",
        },
        "comparison": {
            "published": _published_results(),
            "exact": "all-condition-means-equal-after-published-display-rounding",
            "bounded": (
                "all-condition-means-within-predeclared-margins-and-primary-95-percent-"
                "intervals-mutually-cover-the-point-estimates"
            ),
            "failed": "neither-exact-nor-bounded",
        },
        "tier_policy": list(_TIERS),
        "explicit_non_claims": [
            "deterministic-replay",
            "backend-identity",
            "submitted-agent-artifact-identity",
            "exact-native-state-equivalence",
            "state-or-observation-equivalence-from-score",
            "conformance-from-score",
            "scientific-reproducibility-beyond-retained-evidence",
        ],
    }


def build_declaration(
    repo_root: Path,
    *,
    selection: ReproductionSelection = FROZEN_SELECTION,
) -> tuple[dict[str, object], dict[str, object]]:
    """Build the frozen protocol and its source-owner index."""

    root = repo_root.resolve()
    artifacts = _artifact_refs(root)
    contracts = _contract_payloads(root)
    declaration = _declaration(selection, artifacts, contracts)
    protocol: dict[str, object] = {
        "declaration_sha256": sha256_payload(declaration),
        "declaration": declaration,
    }
    source_ledger = _source_ledger(artifacts)
    validate_protocol(protocol, selection=selection)
    _validate_source_ledger(source_ledger, protocol)
    return protocol, source_ledger


def _require_exact_keys(value: Mapping[str, object], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ValueError(f"{label} has unknown or missing fields")


def _validate_schedule(value: object, selection: ReproductionSelection) -> None:
    if not isinstance(value, list) or len(value) != (
        len(selection.trial_lengths)
        * len(selection.red_variants)
        * selection.episodes_per_condition
    ):
        raise ValueError("attempt schedule is invalid")
    run_ids = [item["run_id"] for item in value]
    slot_ids = [item["slot_id"] for item in value]
    if len(set(run_ids)) != len(run_ids) or len(set(slot_ids)) != len(slot_ids):
        raise ValueError("attempt identities are not unique")
    expected = _schedule(selection)
    if value != expected:
        raise ValueError("attempt schedule is invalid")


def validate_protocol(
    payload: Mapping[str, object],
    *,
    selection: ReproductionSelection | None = None,
) -> None:
    """Validate the closed frozen protocol and its content digest."""

    _require_exact_keys(
        payload,
        {"declaration_sha256", "declaration"},
        "protocol",
    )
    declaration = payload["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError("protocol declaration is invalid")
    if payload["declaration_sha256"] != sha256_payload(declaration):
        raise ValueError("protocol declaration digest is invalid")
    artifacts = declaration.get("artifacts")
    if not isinstance(artifacts, list) or artifacts != _expected_artifact_refs():
        raise ValueError("protocol artifacts are invalid")
    if selection is None:
        selection = _selection_from_declaration(declaration)
    contracts = declaration.get("published_contracts")
    if not isinstance(contracts, dict):
        raise ValueError("published contracts are invalid")
    if {
        name: sha256_payload(contract) for name, contract in contracts.items()
    } != _FROZEN_CONTRACT_DIGESTS:
        raise ValueError("published contract identity is invalid")
    try:
        spec = ExperimentSpecModel.model_validate(contracts["experiment_spec"])
        task = ExperimentTaskModel.model_validate(contracts["experiment_task"])
        manifest = ParticipantImplementationManifestModel.model_validate(
            contracts["participant_manifest"]
        )
        participant_selection = ParticipantImplementationSelectionModel.model_validate(
            contracts["participant_selection"]
        )
        configuration = ParticipantConfigurationResultModel.model_validate(
            contracts["participant_configuration"]
        )
        validate_participant_configuration_selection(participant_selection, configuration)
        if (
            spec.task_ref.ref_id != task.task_id
            or participant_selection.implementation_identity != manifest.identity
        ):
            raise ValueError
    except Exception as error:
        raise ValueError("published contracts are invalid") from error
    expected = _declaration(
        selection,
        cast(list[dict[str, object]], artifacts),
        contracts,
    )
    if declaration.get("seed_policy") != expected["seed_policy"]:
        raise ValueError("seed policy is invalid")
    if declaration.get("attempt_policy") != expected["attempt_policy"]:
        raise ValueError("attempt policy is invalid")
    if declaration.get("aggregation") != expected["aggregation"]:
        raise ValueError("aggregation method is invalid")
    if declaration.get("comparison") != expected["comparison"]:
        raise ValueError("comparison method is invalid")
    for key, value in expected.items():
        if key not in {"artifacts", "published_contracts"} and declaration.get(key) != value:
            raise ValueError("protocol declaration is invalid")
    _validate_schedule(_schedule(selection), selection)


def _validate_source_ledger(payload: Mapping[str, object], protocol: Mapping[str, object]) -> None:
    declaration = protocol["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError("source ledger artifact join is invalid")
    artifacts = declaration.get("artifacts")
    if not isinstance(artifacts, list) or dict(payload) != _source_ledger(
        cast(list[dict[str, object]], artifacts)
    ):
        raise ValueError("source ledger is invalid")


def _score_measure(run_id: str, score: float) -> dict[str, object]:
    if not math.isfinite(score):
        raise ValueError("score measure is invalid")
    payload = ExperimentDerivedMeasureModel(
        schema_version="experiment-derived-measure/v1",
        derived_measure_id=f"derived-measure.{run_id}.cumulative-blue-reward",
        measure_version="1.0.0",
        measure_kind="score",
        metric_ref={
            "ref_kind": "metric-definition",
            "ref_id": _SCORE_METRIC_ID,
            "ref_version": "1.0.0",
        },
        method={
            "method_id": "cyborg-cumulative-blue-reward-v1",
            "method_version": "1.0.0",
            "name": "Sum committed per-step Blue rewards",
            "parameters": [],
        },
        source_evidence_refs=[
            {
                "ref_kind": "evidence-record",
                "ref_id": f"evidence-record.{run_id}.test",
                "ref_version": "1.0.0",
            }
        ],
        generated_at="2026-01-01T00:00:00Z",
        value_status="reported",
        value=score,
        limitations=["Test projection; production uses CyborgEvaluator output."],
        provenance_refs=[
            {
                "ref_kind": "profile",
                "ref_id": "cage2-cyborg-2.1-source-26ce1c1",
                "ref_version": _SOURCE_COMMIT,
            }
        ],
    ).model_dump(mode="json")
    return cast(dict[str, object], payload)


def attempt_record_for_test(
    protocol: Mapping[str, object], slot: Mapping[str, object], *, score: float
) -> dict[str, object]:
    """Construct reduced-cardinality canonical score input for unit tests."""

    return {
        "declaration_sha256": protocol["declaration_sha256"],
        "slot_id": slot["slot_id"],
        "run_id": slot["run_id"],
        "predecessor_run_id": None,
        "attempt_sequence": slot["attempt_sequence"],
        "condition_id": slot["condition_id"],
        "trial_length": slot["trial_length"],
        "red_variant": slot["red_variant"],
        "episode_ordinal": slot["episode_ordinal"],
        "disposition": "valid",
        "diagnostic_code": None,
        "cleanup_verified": True,
        "score_measure": _score_measure(cast(str, slot["run_id"]), score),
        "evidence_refs": [f"runs/{slot['run_id']}/evidence.json"],
    }


def retry_record_for_test(original: Mapping[str, object], *, score: float) -> dict[str, object]:
    """Construct a valid second attempt for retry-policy tests."""

    retry = dict(original)
    run_id = f"{original['slot_id']}-attempt-02"
    retry.update(
        run_id=run_id,
        predecessor_run_id=original["run_id"],
        attempt_sequence=2,
        disposition="valid",
        diagnostic_code=None,
        cleanup_verified=True,
        score_measure=_score_measure(run_id, score),
        evidence_refs=[f"runs/{run_id}/evidence.json"],
    )
    return retry


def _validate_score_measure(value: object) -> float:
    try:
        measure = ExperimentDerivedMeasureModel.model_validate(value)
    except Exception as error:
        raise ValueError("score measure is invalid") from error
    score = measure.value
    if (
        measure.measure_kind != "score"
        or measure.metric_ref.ref_id != _SCORE_METRIC_ID
        or measure.value_status != "reported"
        or isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
    ):
        raise ValueError("score measure is invalid")
    return float(score)


def _validate_attempt(
    value: Mapping[str, object], protocol: Mapping[str, object], slot: Mapping[str, object]
) -> None:
    expected_keys = {
        "declaration_sha256",
        "slot_id",
        "run_id",
        "predecessor_run_id",
        "attempt_sequence",
        "condition_id",
        "trial_length",
        "red_variant",
        "episode_ordinal",
        "disposition",
        "diagnostic_code",
        "cleanup_verified",
        "score_measure",
        "evidence_refs",
    }
    _require_exact_keys(value, expected_keys, "attempt record")
    if value["declaration_sha256"] != protocol["declaration_sha256"]:
        raise ValueError("attempt protocol join is invalid")
    for key in (
        "slot_id",
        "condition_id",
        "trial_length",
        "red_variant",
        "episode_ordinal",
    ):
        if value[key] != slot[key]:
            raise ValueError("attempt slot join is invalid")
    sequence = value["attempt_sequence"]
    declaration = protocol["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError("attempt protocol join is invalid")
    retry_limit = cast(dict[str, object], declaration["attempt_policy"])["retry_limit"]
    if (
        type(sequence) is not int
        or type(retry_limit) is not int
        or not 1 <= sequence <= retry_limit + 1
    ):
        raise ValueError("attempt sequence is invalid")
    expected_run_id = f"{slot['slot_id']}-attempt-{sequence:02d}"
    predecessor = None if sequence == 1 else f"{slot['slot_id']}-attempt-{sequence - 1:02d}"
    if value["run_id"] != expected_run_id or value["predecessor_run_id"] != predecessor:
        raise ValueError("attempt identities are invalid")
    disposition = value["disposition"]
    if disposition not in _DISPOSITIONS:
        raise ValueError("attempt disposition is invalid")
    if disposition == "valid":
        if value["cleanup_verified"] is not True:
            raise ValueError("valid attempt cleanup is invalid")
        _validate_score_measure(value["score_measure"])
    elif value["score_measure"] is not None:
        raise ValueError("ineligible attempt has a score measure")


def _selection_from_declaration(declaration: Mapping[str, object]) -> ReproductionSelection:
    try:
        selection = ReproductionSelection(
            frozen_revision=cast(str, declaration["frozen_revision"]),
            episodes_per_condition=cast(int, declaration["episodes_per_condition"]),
            seed=cast(int, cast(dict[str, object], declaration["seed_policy"])["seed"]),
            trial_lengths=tuple(cast(list[int], declaration["trial_lengths"])),
            red_variants=tuple(cast(list[str], declaration["red_variants"])),
            retry_limit=cast(
                int, cast(dict[str, object], declaration["attempt_policy"])["retry_limit"]
            ),
        )
        if declaration["schedule_partitions"] != _schedule_partitions(selection):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("protocol schedule is invalid") from None
    return selection


def _slot_index(protocol: Mapping[str, object]) -> dict[str, dict[str, object]]:
    declaration = protocol["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError("protocol schedule is invalid")
    selection = _selection_from_declaration(declaration)
    schedule = _schedule(selection)
    if declaration["schedule_partitions"] != _schedule_partitions(selection):
        raise ValueError("protocol schedule is invalid")
    return {cast(str, item["slot_id"]): item for item in schedule if isinstance(item, dict)}


def schedule_for_test(protocol: Mapping[str, object]) -> list[dict[str, object]]:
    """Return the validated generated schedule for reduced-cardinality tests."""

    return list(_slot_index(protocol).values())


def select_eligible_attempts(
    protocol: Mapping[str, object], attempts: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    """Validate every attempt and select the first valid attempt per slot."""

    slots = _slot_index(protocol)
    by_slot: dict[str, list[dict[str, object]]] = {key: [] for key in slots}
    run_ids: set[str] = set()
    for raw in attempts:
        record = dict(raw)
        slot_id = record.get("slot_id")
        if not isinstance(slot_id, str) or slot_id not in slots:
            raise ValueError("attempt slot join is invalid")
        _validate_attempt(record, protocol, slots[slot_id])
        run_id = cast(str, record["run_id"])
        if run_id in run_ids:
            raise ValueError("scheduled attempts are duplicated")
        run_ids.add(run_id)
        by_slot[slot_id].append(record)
    if any(not records for records in by_slot.values()):
        raise ValueError("scheduled attempts are missing")
    selected: list[dict[str, object]] = []
    for slot_id in slots:
        ordered = sorted(by_slot[slot_id], key=lambda item: cast(int, item["attempt_sequence"]))
        if [item["attempt_sequence"] for item in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError("attempt sequence is invalid")
        valid = next((item for item in ordered if item["disposition"] == "valid"), None)
        if valid is not None:
            selected.append(valid)
    return selected


def _interval(values: Sequence[float], critical_value: float) -> dict[str, object]:
    count = len(values)
    if count == 0:
        return {"eligible_n": 0, "mean": None, "sample_variance": None, "interval_95": None}
    mean = math.fsum(values) / count
    if count == 1:
        return {
            "eligible_n": count,
            "mean": mean,
            "sample_variance": None,
            "interval_95": None,
        }
    variance = statistics.variance(values, xbar=mean)
    half_width = critical_value * math.sqrt(variance / count)
    return {
        "eligible_n": count,
        "mean": mean,
        "sample_variance": variance,
        "interval_95": [mean - half_width, mean + half_width],
    }


def _finite_float(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("finite numeric value is required")
    return float(value)


def _comparison(
    declaration: Mapping[str, object], conditions: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    published = cast(
        dict[str, object], cast(dict[str, object], declaration["comparison"])["published"]
    )
    published_by_id = {
        cast(str, item["condition_id"]): item
        for item in cast(list[dict[str, object]], published["conditions"])
    }
    minimum = cast(dict[str, object], declaration["aggregation"])["minimum_eligible_per_condition"]
    complete = all(item["eligible_n"] == minimum for item in conditions)
    exact = complete
    bounded = complete
    for observed in conditions:
        oracle = published_by_id[cast(str, observed["condition_id"])]
        mean = observed["mean"]
        if not isinstance(mean, (int, float)) or isinstance(mean, bool):
            exact = bounded = False
            continue
        decimals = cast(int, oracle["display_decimals"])
        exact = exact and round(float(mean), decimals) == _finite_float(oracle["mean"])
        bounded = bounded and abs(float(mean) - _finite_float(oracle["mean"])) <= _finite_float(
            oracle["bounded_margin"]
        )
    total_mean = math.fsum(cast(float, item["mean"]) for item in conditions) if complete else None
    total_variance = None
    total_interval = None
    if complete and all(item["sample_variance"] is not None for item in conditions):
        total_variance = math.fsum(
            cast(float, item["sample_variance"]) / cast(int, item["eligible_n"])
            for item in conditions
        )
        critical = _finite_float(
            cast(dict[str, object], declaration["aggregation"])["critical_value"]
        )
        half_width = critical * math.sqrt(total_variance)
        total_interval = [
            cast(float, total_mean) - half_width,
            cast(float, total_mean) + half_width,
        ]
        published_interval = cast(list[float], published["primary_total_interval_95"])
        bounded = bounded and (
            total_interval[0] <= _finite_float(published["primary_total"]) <= total_interval[1]
            and published_interval[0] <= cast(float, total_mean) <= published_interval[1]
        )
    else:
        bounded = False
    classification = (
        "exact" if exact else "bounded" if bounded else "failed" if complete else "unavailable"
    )
    return {
        "classification": classification,
        "published_result_identity": published["result_identity"],
        "observed_primary_total": total_mean,
        "observed_primary_variance": total_variance,
        "observed_primary_interval_95": total_interval,
        "published_primary_total": published["primary_total"],
        "published_primary_interval_95": published["primary_total_interval_95"],
    }


def compute_aggregates(
    protocol: Mapping[str, object], attempts: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """Derive the sole deterministic aggregate projection from attempt records."""

    selected = select_eligible_attempts(protocol, attempts)
    slots = _slot_index(protocol)
    selected_by_condition: dict[str, list[float]] = {}
    for item in selected:
        selected_by_condition.setdefault(cast(str, item["condition_id"]), []).append(
            _validate_score_measure(item["score_measure"])
        )
    declaration = cast(dict[str, object], protocol["declaration"])
    aggregation = cast(dict[str, object], declaration["aggregation"])
    critical = _finite_float(aggregation["critical_value"])
    conditions: list[dict[str, object]] = []
    for trial_length in cast(list[int], declaration["trial_lengths"]):
        for red_variant in cast(list[str], declaration["red_variants"]):
            condition_id = _condition_id(trial_length, red_variant)
            summary = _interval(sorted(selected_by_condition.get(condition_id, [])), critical)
            conditions.append(
                {
                    "condition_id": condition_id,
                    "trial_length": trial_length,
                    "red_variant": red_variant,
                    **summary,
                }
            )
    counts = Counter(cast(str, item["disposition"]) for item in attempts)
    payload: dict[str, object] = {
        "declaration_sha256": protocol["declaration_sha256"],
        "scheduled_slot_count": len(slots),
        "attempt_count": len(attempts),
        "selected_valid_count": len(selected),
        "disposition_counts": {key: counts.get(key, 0) for key in _DISPOSITIONS},
        "conditions": conditions,
        "comparison": _comparison(declaration, conditions),
        "method": aggregation,
    }
    return payload


def build_tiers(
    protocol: Mapping[str, object],
    aggregates: Mapping[str, object],
    reference: Mapping[str, object],
) -> dict[str, object]:
    """Project the six independent subjects without a bundle-wide pass bit."""

    comparison = cast(dict[str, object], aggregates["comparison"])
    outcome_class = comparison["classification"]
    cyborg_results = {
        "authored-source": ("pass", ["protocol.json", "source-ledger.json"]),
        "contract": ("pass", ["protocol.json", "runs/"]),
        "execution-control": (
            "weakened",
            ["source-ledger.json#loss-evaluation-seed-unbound", "protocol.json#seed_policy"],
        ),
        "state/observation": (
            "weakened",
            ["source-ledger.json#loss-native-observation-boundary"],
        ),
        "outcome/evaluation": (
            "pass"
            if outcome_class in {"exact", "bounded"}
            else "fail"
            if outcome_class == "failed"
            else "weakened",
            ["aggregates.json#comparison"],
        ),
        "disclosure": ("pass", ["source-ledger.json#loss_refs", "validation-report.md"]),
    }
    reference_keys = {
        "authored-source": "authored_source",
        "contract": "contract",
        "execution-control": "execution_control",
        "state/observation": "state_observation",
        "outcome/evaluation": "outcome_evaluation",
        "disclosure": "disclosure",
    }
    tier_rows = []
    for tier in _TIERS:
        cyborg_result, cyborg_evidence = cyborg_results[tier]
        reference_result = reference.get(reference_keys[tier])
        if reference_result not in {"pass", "fail", "weakened"}:
            raise ValueError("reference tier result is invalid")
        tier_rows.append(
            {
                "tier": tier,
                "subjects": {
                    "cyborg": {
                        "result": cyborg_result,
                        "rule": "issue-22-frozen-tier-rule",
                        "evidence_refs": cyborg_evidence,
                    },
                    "raes-reference": {
                        "result": reference_result,
                        "rule": "reference-processor-supported-surface-only",
                        "evidence_refs": list(cast(Sequence[str], reference["evidence_refs"])),
                    },
                },
            }
        )
    if outcome_class in {"exact", "bounded"}:
        strongest = (
            "behavioral-baseline-outcome-reproduction-without-submitted-agent-or-state-equivalence"
        )
        research_20 = "usable-behavioral-baseline-outcome-reproduction-evidence"
    elif outcome_class == "failed":
        strongest = "failed-outcome-reproduction-with-retained-negative-result"
        research_20 = "usable-negative-reproduction-result"
    else:
        strongest = "insufficient-outcome-evidence"
        research_20 = "insufficient-for-reproduction-result"
    return {
        "declaration_sha256": protocol["declaration_sha256"],
        "tiers": tier_rows,
        "strongest_supported_claim": strongest,
        "research_consumers": {
            "OpenRAE/research#14": (
                "apparatus-evidence-with-explicit-control-and-observation-losses"
            ),
            "OpenRAE/research#20": research_20,
        },
        "explicit_non_claims": cast(dict[str, object], protocol["declaration"])[
            "explicit_non_claims"
        ],
    }


def _scan_value(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _FORBIDDEN_FIELDS:
                raise ValueError("forbidden native material")
            _scan_value(item)
    elif isinstance(value, list):
        for item in value:
            _scan_value(item)
    elif isinstance(value, str) and any(token in value for token in _FORBIDDEN_TEXT):
        raise ValueError("forbidden native material")


def scan_public_tree(root: Path) -> None:
    """Reject native, host, traceback, symlink, and special-file material."""

    if root.is_symlink() or not root.is_dir():
        raise ValueError("public tree is invalid")
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("public tree is invalid")
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if any(token.encode() in raw for token in _FORBIDDEN_TEXT):
            raise ValueError("forbidden native material")
        if path.suffix == ".json" or path.name.endswith(".json.gz"):
            try:
                if path.name.endswith(".json.gz"):
                    raw = gzip.decompress(raw)
                    if len(raw) > _MAX_DECOMPRESSED_JSON_BYTES:
                        raise ValueError(_INVALID_JSON)
                value = json.loads(
                    raw,
                    object_pairs_hook=_closed_pairs,
                    parse_constant=_reject_constant,
                )
            except (UnicodeError, ValueError, gzip.BadGzipFile) as error:
                raise ValueError(_INVALID_JSON) from error
            _scan_value(value)


def _reserve_directory(path: Path) -> Path:
    """Reserve one fresh mode-0700 output root without parent discovery."""

    resolved = path.resolve()
    os.mkdir(resolved, 0o700)
    return resolved


def _write_json(path: Path, payload: object) -> None:
    atomic_write_json_artifact(path, payload)


def _write_gzip_json(path: Path, payload: object) -> None:
    """Atomically write deterministic compressed canonical JSON."""

    compressed = gzip.compress(canonical_json_bytes(payload), compresslevel=9, mtime=0)
    if len(compressed) >= _MAX_PUBLIC_FILE_BYTES:
        raise ValueError("compressed public artifact exceeds the file-size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(compressed)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise


def _write_text(path: Path, value: str) -> None:
    """Atomically write one bounded UTF-8 public text artifact."""

    content = value.encode("utf-8")
    if len(content) >= _MAX_PUBLIC_FILE_BYTES:
        raise ValueError("public text artifact exceeds the file-size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise


def _media_type(path: Path) -> str:
    if path.suffix == ".gz":
        return "application/gzip"
    return "application/json" if path.suffix == ".json" else "text/markdown"


def _inventory_entry(root: Path, path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("inventory member is invalid")
    content = path.read_bytes()
    if len(content) >= _MAX_PUBLIC_FILE_BYTES:
        raise ValueError("public artifact exceeds the file-size limit")
    return {
        "path": path.relative_to(root).as_posix(),
        "media_type": _media_type(path),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _seal_inventory(root: Path, members: Sequence[Path]) -> dict[str, object]:
    inventory: dict[str, object] = {
        "artifacts": [
            _inventory_entry(root, path)
            for path in sorted(members, key=lambda item: item.relative_to(root).as_posix())
        ]
    }
    _write_json(root / "inventory.json", inventory)
    return inventory


def _verify_inventory(root: Path, *, expected_members: set[str] | None = None) -> dict[str, object]:
    inventory = load_strict_json(root / "inventory.json")
    if set(inventory) != {"artifacts"} or not isinstance(inventory["artifacts"], list):
        raise ValueError("inventory is invalid")
    seen: set[str] = set()
    for item in inventory["artifacts"]:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "media_type",
            "sha256",
            "size_bytes",
        }:
            raise ValueError("inventory is invalid")
        relative = item["path"]
        if not isinstance(relative, str):
            raise ValueError("inventory is invalid")
        source = root / relative
        candidate = source.resolve()
        if (
            relative in seen
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not candidate.is_relative_to(root.resolve())
            or source.is_symlink()
            or not candidate.is_file()
        ):
            raise ValueError("inventory is invalid")
        seen.add(relative)
        expected = _inventory_entry(root, candidate)
        if item != expected:
            raise ValueError("inventory digest is invalid")
    direct_files = {
        path.name for path in root.iterdir() if path.is_file() and path.name != "inventory.json"
    }
    inventoried_direct_files = {
        Path(relative).name for relative in seen if len(Path(relative).parts) == 1
    }
    if direct_files != inventoried_direct_files:
        raise ValueError("inventory membership is incomplete")
    if expected_members is not None and seen != expected_members:
        raise ValueError("inventory membership is incomplete")
    return inventory


def _write_schedule_partitions(
    root: Path, protocol: Mapping[str, object], selection: ReproductionSelection
) -> list[Path]:
    plans = root / "plans"
    os.mkdir(plans, 0o700)
    by_condition: dict[str, list[dict[str, object]]] = {}
    for item in _schedule(selection):
        by_condition.setdefault(cast(str, item["condition_id"]), []).append(item)
    declaration = cast(dict[str, object], protocol["declaration"])
    written: list[Path] = []
    for declared in cast(list[dict[str, object]], declaration["schedule_partitions"]):
        path = root / cast(str, declared["path"])
        entries = by_condition[cast(str, declared["condition_id"])]
        if sha256_payload(entries) != declared["sha256"]:
            raise ValueError("schedule partition digest is invalid")
        _write_json(path, entries)
        written.append(path)
    return written


def write_declaration(
    repo_root: Path,
    output: Path,
    *,
    selection: ReproductionSelection = FROZEN_SELECTION,
) -> Path:
    """Write one immutable declaration stage with partitioned schedule files."""

    root = _reserve_directory(output)
    protocol, source_ledger = build_declaration(repo_root, selection=selection)
    protocol_path = root / "protocol.json"
    ledger_path = root / "source-ledger.json"
    _write_json(protocol_path, protocol)
    _write_json(ledger_path, source_ledger)
    plans = _write_schedule_partitions(root, protocol, selection)
    _seal_inventory(root, [protocol_path, ledger_path, *plans])
    return root


def _load_study_inputs(
    repo_root: Path,
) -> tuple[
    object,
    ExperimentTaskModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantConfigurationResultModel,
]:
    from raes import parse_sdl  # type: ignore[import-untyped]

    scenario = parse_sdl(
        (repo_root / _INPUT_PATHS["authored-scenario"]).read_text(encoding="utf-8")
    )
    task = ExperimentTaskModel.model_validate(
        load_strict_json(repo_root / _INPUT_PATHS["experiment-task"])
    )
    manifest = ParticipantImplementationManifestModel.model_validate(
        load_strict_json(repo_root / _INPUT_PATHS["blue-manifest"])
    )
    selection = ParticipantImplementationSelectionModel.model_validate(
        load_strict_json(repo_root / _INPUT_PATHS["blue-selection"])
    )
    configuration = ParticipantConfigurationResultModel.model_validate(
        load_strict_json(repo_root / _INPUT_PATHS["blue-configuration"])
    )
    return scenario, task, manifest, selection, configuration


def capture_reference_path(repo_root: Path) -> dict[str, object]:
    """Exercise only the authored and contract surfaces of the reference processor."""

    from raes import parse_sdl
    from raes_processor.reference import ReferenceProcessor  # type: ignore[import-untyped]

    from .manifest import create_cyborg_manifest

    scenario = parse_sdl(
        (repo_root / _INPUT_PATHS["authored-scenario"]).read_text(encoding="utf-8")
    )
    result = ReferenceProcessor.realize(
        scenario,
        create_cyborg_manifest(),
        target_name="cyborg-cage2",
    )
    errors = sorted({item.code for item in result.diagnostics if item.is_error})
    return {
        "processor": "raes-processor-reference",
        "scenario_name": result.scenario_name,
        "target_manifest": "cyborg-cage2",
        "authored_source": "pass" if not errors else "fail",
        "contract": "pass" if not errors else "fail",
        "execution_control": "weakened",
        "state_observation": "weakened",
        "outcome_evaluation": "weakened",
        "disclosure": "pass",
        "planning_error_codes": errors,
        "planned_operation_counts": {
            "provisioning": len(result.execution_plan.provisioning.operations),
            "orchestration": len(result.execution_plan.orchestration.operations),
            "evaluation": len(result.execution_plan.evaluation.operations),
        },
        "evidence_refs": [
            "reference.json",
            "protocol.json#explicit_non_claims",
        ],
        "limitations": [
            "The reference processor realizes authored contracts and a target plan only.",
            "It does not execute CybORG transitions, observations, rewards, or terminal behavior.",
        ],
    }


def _validate_reference(reference: Mapping[str, object]) -> None:
    """Validate the bounded reference-processor evidence surface."""

    _require_exact_keys(
        reference,
        {
            "processor",
            "scenario_name",
            "target_manifest",
            "authored_source",
            "contract",
            "execution_control",
            "state_observation",
            "outcome_evaluation",
            "disclosure",
            "planning_error_codes",
            "planned_operation_counts",
            "evidence_refs",
            "limitations",
        },
        "reference evidence",
    )
    if (
        reference["processor"] != "raes-processor-reference"
        or reference["scenario_name"] != "cage2-research"
        or reference["target_manifest"] != "cyborg-cage2"
        or reference["execution_control"] != "weakened"
        or reference["state_observation"] != "weakened"
        or reference["outcome_evaluation"] != "weakened"
        or reference["evidence_refs"] != ["reference.json", "protocol.json#explicit_non_claims"]
    ):
        raise ValueError("reference evidence identity is invalid")
    if any(reference[key] not in {"pass", "fail"} for key in ("authored_source", "contract")):
        raise ValueError("reference evidence result is invalid")
    if reference["disclosure"] != "pass":
        raise ValueError("reference evidence result is invalid")
    codes = reference["planning_error_codes"]
    if not isinstance(codes, list) or any(not isinstance(code, str) or not code for code in codes):
        raise ValueError("reference diagnostics are invalid")
    counts = reference["planned_operation_counts"]
    if (
        not isinstance(counts, dict)
        or set(counts) != {"provisioning", "orchestration", "evaluation"}
        or any(type(value) is not int or value < 0 for value in counts.values())
    ):
        raise ValueError("reference operation counts are invalid")
    limitations = reference["limitations"]
    if not isinstance(limitations, list) or limitations != [
        "The reference processor realizes authored contracts and a target plan only.",
        "It does not execute CybORG transitions, observations, rewards, or terminal behavior.",
    ]:
        raise ValueError("reference limitations are invalid")


def _evidence_step(record: ExperimentEvidenceRecordModel) -> int:
    for ref in record.source_refs:
        if ref.ref_id.startswith("logical-step:"):
            return int(ref.ref_id.removeprefix("logical-step:"))
    raise ValueError("evidence logical-step join is missing")


def _write_evidence_chunks(
    run_root: Path, records: Sequence[ExperimentEvidenceRecordModel]
) -> list[dict[str, object]]:
    """Write the exact referenced record closure in bounded deterministic chunks."""

    payloads = [record.model_dump(mode="json") for record in records]
    ordered_steps = [_evidence_step(record) for record in records]
    if not payloads or ordered_steps != sorted(ordered_steps):
        raise ValueError("episode evidence order is invalid")
    evidence_chunks: list[dict[str, object]] = []
    pending: list[tuple[list[dict[str, object]], int, int]] = [
        (payloads, min(ordered_steps), max(ordered_steps))
    ]
    chunk_number = 0
    while pending:
        chunk_records, first_step, last_step = pending.pop(0)
        compressed = gzip.compress(canonical_json_bytes(chunk_records), compresslevel=9, mtime=0)
        if len(compressed) >= _MAX_PUBLIC_FILE_BYTES:
            if len(chunk_records) < 2:
                raise ValueError("one evidence record exceeds the file-size limit")
            midpoint = len(chunk_records) // 2
            left = chunk_records[:midpoint]
            right = chunk_records[midpoint:]
            pending[0:0] = [
                (
                    left,
                    first_step,
                    _evidence_step(ExperimentEvidenceRecordModel.model_validate(left[-1])),
                ),
                (
                    right,
                    _evidence_step(ExperimentEvidenceRecordModel.model_validate(right[0])),
                    last_step,
                ),
            ]
            continue
        chunk_number += 1
        path = run_root / f"evidence-{chunk_number:03d}.json.gz"
        _write_gzip_json(path, chunk_records)
        evidence_chunks.append(
            {
                "path": path.relative_to(run_root).as_posix(),
                "sha256": _sha256_file(path),
                "record_count": len(chunk_records),
                "first_logical_step": first_step,
                "last_logical_step": last_step,
            }
        )
    return evidence_chunks


def _write_episode_evidence(
    run_root: Path,
    artifact_uri: str,
    controls: RunControls,
    episode: EpisodeEvidence,
    task: ExperimentTaskModel,
    scenario_digest: str,
) -> dict[str, object]:
    evidence_records = episode.evidence_records
    measures = episode.derived_measures
    referenced = {ref.ref_id for measure in measures for ref in measure.source_evidence_refs}
    retained = [record for record in evidence_records if record.evidence_record_id in referenced]
    retained_ids = {item.evidence_record_id for item in retained}
    if not retained or referenced != retained_ids:
        raise ValueError("episode has no retained evidence closure")
    evidence_chunks = _write_evidence_chunks(run_root, retained)
    episode_summary = run_root / "episode-summary.json.gz"
    _write_gzip_json(
        episode_summary,
        {
            "derived_measures": [item.model_dump(mode="json") for item in measures],
            "proposition_truth": episode.proposition_truth_results,
            "objective_results": episode.objective_results,
            "diagnostics": [item.model_dump(mode="json") for item in episode.diagnostics],
        },
    )
    evidence_index = run_root / "evidence-index.json"
    _write_json(
        evidence_index,
        {
            "record_count": len(retained),
            "chunks": evidence_chunks,
            "episode_summary": {
                "path": episode_summary.relative_to(run_root).as_posix(),
                "sha256": _sha256_file(episode_summary),
            },
        },
    )
    index_bytes = evidence_index.read_bytes()
    artifact = ExperimentArtifactRefModel(
        artifact_id=f"portable-evidence-{controls.run_id}",
        role="observation",
        media_type="application/json",
        uri=artifact_uri,
        checksum={"algorithm": "sha256", "value": hashlib.sha256(index_bytes).hexdigest()},
        size_bytes=len(index_bytes),
        created_at=retained[0].captured_at,
        source="cyborg-cage2 evaluator projection",
        satisfies_refs=[
            {"ref_kind": "evidence", "ref_id": "operational-service-state"},
            {"ref_kind": "evidence", "ref_id": "source-ledger:reward-components"},
        ],
        sensitivity="redacted",
    )
    run = archival_run(
        controls=controls,
        scenario_digest=scenario_digest,
        task=task,
        episode=replace(episode, evidence_records=tuple(retained)),
        evidence_artifact=artifact,
    )
    validate_experiment_run_against_task(task, run)
    _write_gzip_json(run_root / "run.json.gz", run.model_dump(mode="json"))
    score = next(
        (
            item
            for item in measures
            if item.metric_ref.ref_id == _SCORE_METRIC_ID
            and item.measure_kind == "score"
            and item.value_status == "reported"
        ),
        None,
    )
    if score is None:
        raise ValueError("episode score measure is missing")
    _validate_score_measure(score.model_dump(mode="json"))
    return {
        "score_measure": score.model_dump(mode="json"),
        "evidence_refs": [
            "evidence-index.json",
            "episode-summary.json.gz",
            "run.json.gz",
        ],
    }


def _attempt_record(
    protocol: Mapping[str, object],
    slot: Mapping[str, object],
    *,
    attempt_sequence: int,
    disposition: str,
    cleanup_verified: bool,
    score_measure: object = None,
    evidence_refs: Sequence[str] = (),
    diagnostic_code: str | None = None,
) -> dict[str, object]:
    slot_id = cast(str, slot["slot_id"])
    run_id = f"{slot_id}-attempt-{attempt_sequence:02d}"
    record = {
        "declaration_sha256": protocol["declaration_sha256"],
        "slot_id": slot_id,
        "run_id": run_id,
        "predecessor_run_id": (
            None if attempt_sequence == 1 else f"{slot_id}-attempt-{attempt_sequence - 1:02d}"
        ),
        "attempt_sequence": attempt_sequence,
        "condition_id": slot["condition_id"],
        "trial_length": slot["trial_length"],
        "red_variant": slot["red_variant"],
        "episode_ordinal": slot["episode_ordinal"],
        "disposition": disposition,
        "diagnostic_code": diagnostic_code,
        "cleanup_verified": cleanup_verified,
        "score_measure": score_measure,
        "evidence_refs": list(evidence_refs),
    }
    _validate_attempt(record, protocol, slot)
    return record


def _slot_for_attempt(slot: Mapping[str, object], attempt_sequence: int) -> dict[str, object]:
    """Bind one frozen logical slot to a never-reused execution identity."""

    attempt_slot = dict(slot)
    attempt_slot["run_id"] = f"{slot['slot_id']}-attempt-{attempt_sequence:02d}"
    attempt_slot["attempt_sequence"] = attempt_sequence
    return attempt_slot


def _condition_controls(
    slots: Sequence[Mapping[str, object]],
    protocol: Mapping[str, object],
    manifest: ParticipantImplementationManifestModel,
    selection: ParticipantImplementationSelectionModel,
    configuration: ParticipantConfigurationResultModel,
) -> tuple[RunControls, ...]:
    declaration = cast(dict[str, object], protocol["declaration"])
    seed = cast(int, cast(dict[str, object], declaration["seed_policy"])["seed"])
    return tuple(
        RunControls(
            run_id=cast(str, slot["run_id"]),
            seed=seed,
            max_steps=cast(int, slot["trial_length"]),
            red_variant=cast(str, slot["red_variant"]),
            blue_manifest=manifest,
            blue_selection=selection,
            blue_configuration=configuration,
        )
        for slot in slots
    )


def _write_environment(protocol: Mapping[str, object]) -> dict[str, object]:
    def version(name: str) -> str:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return "not-installed"

    declaration = cast(dict[str, object], protocol["declaration"])
    artifacts = cast(list[dict[str, object]], declaration["artifacts"])
    pack_manifest = next(item for item in artifacts if item["artifact_id"] == "pack-manifest")
    contracts = cast(dict[str, object], declaration["published_contracts"])
    task = ExperimentTaskModel.model_validate(contracts["experiment_task"])
    aggregation = cast(dict[str, object], declaration["aggregation"])
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "operating_system": platform.system(),
        "architecture": platform.machine(),
        "distributions": {
            "raes": version("raes"),
            "raes-adapters": version("raes-adapters"),
            "CybORG": version("CybORG"),
            "gym": version("gym"),
            "numpy": version("numpy"),
        },
        "source_profile": declaration["source_profile"],
        "source_commit": declaration["source_commit"],
        "frozen_revision": declaration["frozen_revision"],
        "declaration_sha256": protocol["declaration_sha256"],
        "pack": {
            "content_manifest_sha256": pack_manifest["sha256"],
            "scenario_ref_digest": task.scenario_ref.ref_digest,
        },
        "method": {
            "score_metric_id": aggregation["score_metric_id"],
            "condition_estimator": aggregation["condition_estimator"],
            "interval": aggregation["interval"],
            "seed_policy_sha256": sha256_payload(declaration["seed_policy"]),
        },
        "limitations": [
            "No hostname, username, absolute path, argv, environment mapping, or "
            "provider log is retained.",
            "The qualified source installation is separately acquired and is not bundled.",
        ],
    }


def _validate_environment(
    environment: Mapping[str, object], protocol: Mapping[str, object]
) -> None:
    """Validate bounded apparatus provenance and its frozen-protocol joins."""

    expected = _write_environment(protocol)
    _require_exact_keys(environment, set(expected), "environment")
    for key in (
        "python",
        "implementation",
        "operating_system",
        "architecture",
    ):
        if not isinstance(environment[key], str) or not environment[key]:
            raise ValueError("environment identity is invalid")
    distributions = environment["distributions"]
    if not isinstance(distributions, dict) or set(distributions) != set(
        cast(dict[str, object], expected["distributions"])
    ):
        raise ValueError("environment distributions are invalid")
    if any(not isinstance(value, str) or not value for value in distributions.values()):
        raise ValueError("environment distributions are invalid")
    for key in (
        "source_profile",
        "source_commit",
        "frozen_revision",
        "declaration_sha256",
        "pack",
        "method",
        "limitations",
    ):
        if environment[key] != expected[key]:
            raise ValueError("environment protocol join is invalid")


def _validation_report_text(tiers: Mapping[str, object]) -> str:
    return (
        "# CAGE-2 protocol reproduction validation\n\n"
        f"Frozen claim: `{tiers['strongest_supported_claim']}`.\n\n"
        "Recompute from a clean installed environment without CybORG or network access:\n\n"
        "```shell\n"
        "raes-adapters reproduce --phase verify --bundle <frozen-bundle> "
        "--output cage2-recomputed\n"
        "```\n\n"
        "The output is evidence for OpenRAE/research#14 and OpenRAE/research#20. "
        "It does not claim deterministic replay, backend identity, submitted-agent "
        "artifact identity, state/observation equivalence from score, or scientific "
        "reproducibility beyond the retained evidence.\n"
    )


def _write_validation_report(root: Path, tiers: Mapping[str, object]) -> Path:
    path = root / "validation-report.md"
    _write_text(path, _validation_report_text(tiers))
    return path


def _condition_inventory(condition_root: Path) -> Path:
    members = [condition_root / "cleanup.json"]
    members.extend(sorted(condition_root.glob("*/inventory.json")))
    _seal_inventory(condition_root, members)
    return condition_root / "inventory.json"


def run_full_study(
    repo_root: Path,
    output: Path,
    *,
    selection: ReproductionSelection = FROZEN_SELECTION,
    driver: object | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> Path:
    """Execute, retain, derive, and seal the complete frozen native study."""

    source_root = repo_root.resolve()
    root = _reserve_directory(output)
    protocol, source_ledger = build_declaration(source_root, selection=selection)
    protocol_path = root / "protocol.json"
    ledger_path = root / "source-ledger.json"
    _write_json(protocol_path, protocol)
    _write_json(ledger_path, source_ledger)
    plan_paths = _write_schedule_partitions(root, protocol, selection)
    scenario, task, manifest, participant_selection, configuration = _load_study_inputs(source_root)
    reference = capture_reference_path(source_root)
    reference_path = root / "reference.json"
    _write_json(reference_path, reference)
    environment_path = root / "environment.json"
    _write_json(environment_path, _write_environment(protocol))
    runtime_driver = cast(
        CyborgDriver,
        driver if driver is not None else SourceInstalledCyborgDriver(expected_version="2.1"),
    )
    begin_stream_value = getattr(runtime_driver, "begin_ordered_stream", None)
    checkpoint_stream_value = getattr(runtime_driver, "ordered_stream_checkpoint", None)
    restore_stream_value = getattr(runtime_driver, "restore_ordered_stream", None)
    if not all(
        callable(item)
        for item in (begin_stream_value, checkpoint_stream_value, restore_stream_value)
    ):
        raise ValueError("study driver has no recoverable ordered stream")
    begin_stream = cast(Callable[[int], None], begin_stream_value)
    checkpoint_stream = cast(Callable[[], object], checkpoint_stream_value)
    restore_stream = cast(Callable[[object], None], restore_stream_value)
    begin_stream(selection.seed)
    runs_root = root / "runs"
    os.mkdir(runs_root, 0o700)
    all_attempts: list[dict[str, object]] = []
    condition_inventories: list[Path] = []
    schedule = _schedule(selection)
    scenario_digest = task.scenario_ref.ref_digest
    if not isinstance(scenario_digest, str):
        raise ValueError("task scenario digest is unavailable")
    for partition in _schedule_partitions(selection):
        condition_id = cast(str, partition["condition_id"])
        condition_root = runs_root / condition_id
        os.mkdir(condition_root, 0o700)
        slots = [item for item in schedule if item["condition_id"] == condition_id]
        condition_checkpoint = checkpoint_stream()
        cleanup_attempts: list[dict[str, object]] = []
        condition_completed = False
        for attempt_sequence in range(1, selection.retry_limit + 2):
            if attempt_sequence > 1:
                restore_stream(condition_checkpoint)
            attempt_slots = [_slot_for_attempt(slot, attempt_sequence) for slot in slots]
            staged: dict[str, dict[str, object]] = {}
            run_roots: dict[str, Path] = {}
            for attempt_slot in attempt_slots:
                run_id = cast(str, attempt_slot["run_id"])
                run_root = condition_root / run_id
                os.mkdir(run_root, 0o700)
                run_roots[run_id] = run_root

            def consume(
                controls: RunControls,
                episode: EpisodeEvidence,
                *,
                _staged: dict[str, dict[str, object]] = staged,
                _run_roots: dict[str, Path] = run_roots,
                _condition_id: str = condition_id,
                _slot_count: int = len(slots),
            ) -> None:
                _staged[controls.run_id] = _write_episode_evidence(
                    _run_roots[controls.run_id],
                    (_run_roots[controls.run_id] / "evidence-index.json")
                    .relative_to(root)
                    .as_posix(),
                    controls,
                    episode,
                    task,
                    scenario_digest,
                )
                if progress is not None:
                    progress(_condition_id, len(_staged), _slot_count)

            controls = _condition_controls(
                attempt_slots,
                protocol,
                manifest,
                participant_selection,
                configuration,
            )
            condition_success = False
            try:
                with (
                    Path(os.devnull).open("w", encoding="utf-8") as sink,
                    redirect_stdout(sink),
                    redirect_stderr(sink),
                ):
                    execute_episode_series(
                        scenario,
                        controls,
                        driver=runtime_driver,
                        episode_consumer=consume,
                        retain_evidence=False,
                    )
                condition_success = len(staged) == len(slots)
            except Exception:
                condition_success = False
            cleanup_attempts.append(
                {
                    "attempt_sequence": attempt_sequence,
                    "run_count": len(attempt_slots),
                    "verified": condition_success,
                }
            )
            for slot, attempt_slot in zip(slots, attempt_slots, strict=True):
                run_id = cast(str, attempt_slot["run_id"])
                run_root = run_roots[run_id]
                if condition_success:
                    stage = staged[run_id]
                    record = _attempt_record(
                        protocol,
                        slot,
                        attempt_sequence=attempt_sequence,
                        disposition="valid",
                        cleanup_verified=True,
                        score_measure=stage["score_measure"],
                        evidence_refs=cast(list[str], stage["evidence_refs"]),
                    )
                else:
                    for artifact in run_root.iterdir():
                        if artifact.is_symlink() or not artifact.is_file():
                            raise ValueError("failed attempt artifact boundary is invalid")
                        artifact.unlink()
                    record = _attempt_record(
                        protocol,
                        slot,
                        attempt_sequence=attempt_sequence,
                        disposition="failed",
                        cleanup_verified=False,
                        diagnostic_code="cyborg-reproduction.condition-session-failed",
                    )
                attempt_path = run_root / "attempt.json.gz"
                _write_gzip_json(attempt_path, record)
                members = [item for item in run_root.rglob("*") if item.is_file()]
                _seal_inventory(run_root, members)
                all_attempts.append(record)
            if condition_success:
                condition_completed = True
                break
        _write_json(
            condition_root / "cleanup.json",
            {
                "condition_id": condition_id,
                "completed": condition_completed,
                "attempts": cleanup_attempts,
            },
        )
        condition_inventories.append(_condition_inventory(condition_root))
    aggregates = compute_aggregates(protocol, all_attempts)
    aggregates_path = root / "aggregates.json"
    _write_json(aggregates_path, aggregates)
    tiers = build_tiers(protocol, aggregates, reference)
    tiers_path = root / "tiers.json"
    _write_json(tiers_path, tiers)
    report_path = _write_validation_report(root, tiers)
    scan_public_tree(root)
    root_members = [
        protocol_path,
        ledger_path,
        reference_path,
        environment_path,
        aggregates_path,
        tiers_path,
        report_path,
        *plan_paths,
        *condition_inventories,
    ]
    _seal_inventory(root, root_members)
    return root


def compact_bundle_evidence(
    root: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Rewrite a sealed pre-closure bundle to its exact referenced evidence set.

    This deterministic migration exists for a native study that began under the
    earlier retain-all implementation.  It never changes attempts, measures,
    scores, controls, or provenance; it removes only evidence records that no
    retained derived measure references, recomputes the deterministic result
    projections, then reseals and validates the complete bundle.
    """

    bundle = root.resolve()
    protocol = load_strict_json(bundle / "protocol.json")
    selection = _selection_from_declaration(cast(dict[str, object], protocol["declaration"]))
    validate_protocol(protocol, selection=selection)
    _verify_inventory(bundle)
    contracts = cast(
        dict[str, object], cast(dict[str, object], protocol["declaration"])["published_contracts"]
    )
    task = ExperimentTaskModel.model_validate(contracts["experiment_task"])
    slots = _slot_index(protocol)
    root_inventory = load_strict_json(bundle / "inventory.json")
    inventory_artifacts = cast(list[dict[str, object]], root_inventory["artifacts"])
    root_members = [bundle / cast(str, item["path"]) for item in inventory_artifacts]
    condition_roots = sorted(path for path in (bundle / "runs").iterdir() if path.is_dir())
    run_roots = [
        run_root
        for condition_root in condition_roots
        for run_root in sorted(path for path in condition_root.iterdir() if path.is_dir())
    ]
    total = len(run_roots)
    completed = 0
    all_attempts: list[dict[str, object]] = []
    for condition_root in condition_roots:
        condition_run_roots = sorted(path for path in condition_root.iterdir() if path.is_dir())
        _verify_inventory(
            condition_root,
            expected_members={"cleanup.json"}
            | {f"{run_root.name}/inventory.json" for run_root in condition_run_roots},
        )
        for run_root in condition_run_roots:
            _verify_inventory(run_root)
            attempt = load_strict_json(run_root / "attempt.json.gz")
            slot_id = attempt.get("slot_id")
            if not isinstance(slot_id, str) or slot_id not in slots:
                raise ValueError("attempt slot join is invalid")
            _validate_attempt(attempt, protocol, slots[slot_id])
            all_attempts.append(attempt)
            if attempt["disposition"] == "valid":
                index = load_strict_json(run_root / "evidence-index.json")
                summary_ref = cast(dict[str, object], index["episode_summary"])
                summary_path = run_root / cast(str, summary_ref["path"])
                if _sha256_file(summary_path) != summary_ref["sha256"]:
                    raise ValueError("episode summary digest is invalid")
                summary = load_strict_json(summary_path)
                measures = [
                    ExperimentDerivedMeasureModel.model_validate(item)
                    for item in cast(list[dict[str, object]], summary["derived_measures"])
                ]
                referenced = {
                    ref.ref_id for measure in measures for ref in measure.source_evidence_refs
                }
                records: list[ExperimentEvidenceRecordModel] = []
                for chunk in cast(list[dict[str, object]], index["chunks"]):
                    chunk_path = run_root / cast(str, chunk["path"])
                    if _sha256_file(chunk_path) != chunk["sha256"]:
                        raise ValueError("evidence chunk digest is invalid")
                    values = _load_strict_json_value(chunk_path)
                    if not isinstance(values, list) or len(values) != chunk["record_count"]:
                        raise ValueError("evidence chunk is invalid")
                    chunk_records = [
                        ExperimentEvidenceRecordModel.model_validate(item) for item in values
                    ]
                    steps = [_evidence_step(record) for record in chunk_records]
                    if (
                        not steps
                        or steps != sorted(steps)
                        or min(steps) != chunk["first_logical_step"]
                        or max(steps) != chunk["last_logical_step"]
                    ):
                        raise ValueError("evidence chunk ordering is invalid")
                    records.extend(chunk_records)
                if len(records) != index["record_count"]:
                    raise ValueError("evidence record closure is invalid")
                retained = [record for record in records if record.evidence_record_id in referenced]
                if {record.evidence_record_id for record in retained} != referenced:
                    raise ValueError("derived-measure evidence closure is invalid")
                for path in run_root.glob("evidence-*.json.gz"):
                    path.unlink()
                chunks = _write_evidence_chunks(run_root, retained)
                _write_json(
                    run_root / "evidence-index.json",
                    {
                        "record_count": len(retained),
                        "chunks": chunks,
                        "episode_summary": {
                            "path": summary_path.relative_to(run_root).as_posix(),
                            "sha256": _sha256_file(summary_path),
                        },
                    },
                )
                index_bytes = (run_root / "evidence-index.json").read_bytes()
                run_payload = load_strict_json(run_root / "run.json.gz")
                artifacts = cast(list[dict[str, object]], run_payload["evidence_artifacts"])
                if len(artifacts) != 1:
                    raise ValueError("run evidence artifacts are invalid")
                artifacts[0]["checksum"] = {
                    "algorithm": "sha256",
                    "value": hashlib.sha256(index_bytes).hexdigest(),
                }
                artifacts[0]["size_bytes"] = len(index_bytes)
                traceability = cast(dict[str, object], run_payload["traceability"])
                traceability["evidence_record_refs"] = [
                    item
                    for item in cast(list[dict[str, object]], traceability["evidence_record_refs"])
                    if item["ref_id"] in referenced
                ]
                run = ExperimentRunModel.model_validate(run_payload)
                validate_experiment_run_against_task(task, run)
                _write_gzip_json(run_root / "run.json.gz", run.model_dump(mode="json"))
                _seal_inventory(
                    run_root,
                    [
                        path
                        for path in run_root.iterdir()
                        if path.is_file() and path.name != "inventory.json"
                    ],
                )
            completed += 1
            if progress is not None:
                progress(completed, total)
        _condition_inventory(condition_root)
    aggregates = compute_aggregates(protocol, all_attempts)
    _write_json(bundle / "aggregates.json", aggregates)
    reference = load_strict_json(bundle / "reference.json")
    _validate_reference(reference)
    tiers = build_tiers(protocol, aggregates, reference)
    _write_json(bundle / "tiers.json", tiers)
    _write_validation_report(bundle, tiers)
    _seal_inventory(bundle, root_members)
    verify_bundle(bundle, selection=selection)
    return bundle


def _verify_schedule_partitions(root: Path, protocol: Mapping[str, object]) -> None:
    declaration = cast(dict[str, object], protocol["declaration"])
    expected = _slot_index(protocol)
    observed: list[dict[str, object]] = []
    expected_paths = {
        cast(str, partition["path"])
        for partition in cast(list[dict[str, object]], declaration["schedule_partitions"])
    }
    plans_root = root / "plans"
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in plans_root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if actual_paths != expected_paths or any(not path.is_file() for path in plans_root.iterdir()):
        raise ValueError("schedule partition membership is invalid")
    for partition in cast(list[dict[str, object]], declaration["schedule_partitions"]):
        path = root / cast(str, partition["path"])
        value = _load_strict_json_value(path)
        if not isinstance(value, list) or sha256_payload(value) != partition["sha256"]:
            raise ValueError("schedule partition digest is invalid")
        observed.extend(cast(list[dict[str, object]], value))
    if observed != list(expected.values()):
        raise ValueError("schedule partitions do not join the protocol")


def _valid_run_evidence(
    bundle: Path,
    run_root: Path,
    attempt: Mapping[str, object],
    task: ExperimentTaskModel,
) -> None:
    """Validate the sealed portable evidence closure for one eligible attempt."""

    index_path = run_root / "evidence-index.json"
    index = load_strict_json(index_path)
    _require_exact_keys(index, {"record_count", "chunks", "episode_summary"}, "evidence index")
    chunks = index["chunks"]
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("evidence index is invalid")
    record_ids: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError("evidence index is invalid")
        _require_exact_keys(
            chunk,
            {
                "path",
                "sha256",
                "record_count",
                "first_logical_step",
                "last_logical_step",
            },
            "evidence chunk",
        )
        relative = chunk["path"]
        if not isinstance(relative, str) or Path(relative).name != relative:
            raise ValueError("evidence chunk path is invalid")
        path = run_root / relative
        if _sha256_file(path) != chunk["sha256"]:
            raise ValueError("evidence chunk digest is invalid")
        values = _load_strict_json_value(path)
        if not isinstance(values, list) or len(values) != chunk["record_count"]:
            raise ValueError("evidence chunk is invalid")
        records = [ExperimentEvidenceRecordModel.model_validate(item) for item in values]
        steps = [_evidence_step(record) for record in records]
        if (
            not steps
            or steps != sorted(steps)
            or min(steps) != chunk["first_logical_step"]
            or max(steps) != chunk["last_logical_step"]
        ):
            raise ValueError("evidence chunk ordering is invalid")
        record_ids.extend(record.evidence_record_id for record in records)
    if len(record_ids) != index["record_count"] or len(record_ids) != len(set(record_ids)):
        raise ValueError("evidence record closure is invalid")

    summary_ref = index["episode_summary"]
    if not isinstance(summary_ref, dict):
        raise ValueError("episode summary reference is invalid")
    _require_exact_keys(summary_ref, {"path", "sha256"}, "episode summary reference")
    summary_relative = summary_ref["path"]
    if not isinstance(summary_relative, str) or Path(summary_relative).name != summary_relative:
        raise ValueError("episode summary path is invalid")
    summary_path = run_root / summary_relative
    if _sha256_file(summary_path) != summary_ref["sha256"]:
        raise ValueError("episode summary digest is invalid")
    summary = load_strict_json(summary_path)
    _require_exact_keys(
        summary,
        {"derived_measures", "proposition_truth", "objective_results", "diagnostics"},
        "episode summary",
    )
    measure_values = summary["derived_measures"]
    if not isinstance(measure_values, list) or not measure_values:
        raise ValueError("derived measures are invalid")
    measures = [ExperimentDerivedMeasureModel.model_validate(item) for item in measure_values]
    known_records = set(record_ids)
    referenced_records = {
        ref.ref_id for measure in measures for ref in measure.source_evidence_refs
    }
    if referenced_records != known_records:
        raise ValueError("derived-measure evidence closure is invalid")
    score = next(
        (
            item
            for item in measures
            if item.metric_ref.ref_id == _SCORE_METRIC_ID
            and item.measure_kind == "score"
            and item.value_status == "reported"
        ),
        None,
    )
    if score is None or canonical_json_bytes(score.model_dump(mode="json")) != canonical_json_bytes(
        attempt["score_measure"]
    ):
        raise ValueError("attempt score does not join the episode evidence")

    run_path = run_root / "run.json.gz"
    run_payload = load_strict_json(run_path)
    run = ExperimentRunModel.model_validate(run_payload)
    validate_experiment_run_against_task(task, run)
    traceability = cast(dict[str, object], run_payload["traceability"])
    trace_record_refs = cast(list[dict[str, object]], traceability["evidence_record_refs"])
    trace_measure_refs = cast(list[dict[str, object]], traceability["derived_measure_refs"])
    if {cast(str, item["ref_id"]) for item in trace_record_refs} != known_records:
        raise ValueError("run evidence traceability is incomplete")
    if {cast(str, item["ref_id"]) for item in trace_measure_refs} != {
        item.derived_measure_id for item in measures
    }:
        raise ValueError("run measure traceability is incomplete")
    artifact_relative = index_path.relative_to(bundle).as_posix()
    artifacts = cast(list[dict[str, object]], run_payload["evidence_artifacts"])
    if len(artifacts) != 1 or artifacts[0].get("uri") != artifact_relative:
        raise ValueError("run evidence artifact path is invalid")
    checksum = artifacts[0].get("checksum")
    if not isinstance(checksum, dict) or checksum.get("value") != _sha256_file(index_path):
        raise ValueError("run evidence artifact digest is invalid")
    result_summaries = cast(dict[str, dict[str, object]], run_payload["result_summaries"])
    result = result_summaries.get("cage2-cumulative-blue-reward-result")
    if result is None or float(cast(float, result.get("value"))) != _validate_score_measure(
        attempt["score_measure"]
    ):
        raise ValueError("run score summary is invalid")


def _load_attempts(root: Path, protocol: Mapping[str, object]) -> list[dict[str, object]]:
    attempts: list[dict[str, object]] = []
    slots = _slot_index(protocol)
    declaration = cast(dict[str, object], protocol["declaration"])
    contracts = cast(dict[str, object], declaration["published_contracts"])
    task = ExperimentTaskModel.model_validate(contracts["experiment_task"])
    runs_root = root / "runs"
    expected_conditions = {cast(str, slot["condition_id"]) for slot in slots.values()}
    condition_roots = sorted(path for path in runs_root.iterdir() if path.is_dir())
    if (
        any(path.is_symlink() or not path.is_dir() for path in runs_root.iterdir())
        or {path.name for path in condition_roots} != expected_conditions
    ):
        raise ValueError("run condition membership is invalid")
    for condition_root in condition_roots:
        run_roots = sorted(path for path in condition_root.iterdir() if path.is_dir())
        _verify_inventory(
            condition_root,
            expected_members={"cleanup.json"}
            | {f"{run_root.name}/inventory.json" for run_root in run_roots},
        )
        for run_root in run_roots:
            if run_root.is_symlink() or any(path.is_dir() for path in run_root.iterdir()):
                raise ValueError("run artifact membership is invalid")
            _verify_inventory(run_root)
            attempt = load_strict_json(run_root / "attempt.json.gz")
            slot_id = attempt.get("slot_id")
            if not isinstance(slot_id, str) or slot_id not in slots:
                raise ValueError("attempt slot join is invalid")
            _validate_attempt(attempt, protocol, slots[slot_id])
            if attempt["disposition"] == "valid":
                _valid_run_evidence(root, run_root, attempt, task)
            attempts.append(attempt)
    return attempts


def verify_bundle(
    root: Path,
    *,
    selection: ReproductionSelection = FROZEN_SELECTION,
) -> dict[str, object]:
    """Offline-verify every transitive inventory and recompute the frozen result."""

    bundle = root.resolve()
    expected_root_directories = {"plans", "runs"}
    if (
        bundle.is_symlink()
        or {path.name for path in bundle.iterdir() if path.is_dir()} != expected_root_directories
    ):
        raise ValueError("bundle directory membership is invalid")
    protocol = load_strict_json(bundle / "protocol.json")
    validate_protocol(protocol, selection=selection)
    declaration = cast(dict[str, object], protocol["declaration"])
    conditions = {cast(str, slot["condition_id"]) for slot in _slot_index(protocol).values()}
    _verify_inventory(
        bundle,
        expected_members={
            "protocol.json",
            "source-ledger.json",
            "reference.json",
            "environment.json",
            "aggregates.json",
            "tiers.json",
            "validation-report.md",
            *{
                cast(str, partition["path"])
                for partition in cast(list[dict[str, object]], declaration["schedule_partitions"])
            },
            *{f"runs/{condition}/inventory.json" for condition in conditions},
        },
    )
    ledger = load_strict_json(bundle / "source-ledger.json")
    _validate_source_ledger(ledger, protocol)
    _validate_environment(load_strict_json(bundle / "environment.json"), protocol)
    _verify_schedule_partitions(bundle, protocol)
    attempts = _load_attempts(bundle, protocol)
    aggregates = compute_aggregates(protocol, attempts)
    if canonical_json_bytes(aggregates) != canonical_json_bytes(
        load_strict_json(bundle / "aggregates.json")
    ):
        raise ValueError("aggregate recomputation does not match")
    reference = load_strict_json(bundle / "reference.json")
    _validate_reference(reference)
    tiers = build_tiers(protocol, aggregates, reference)
    if canonical_json_bytes(tiers) != canonical_json_bytes(load_strict_json(bundle / "tiers.json")):
        raise ValueError("tier recomputation does not match")
    try:
        report = (bundle / "validation-report.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError("validation report is invalid") from error
    if report != _validation_report_text(tiers):
        raise ValueError("validation report does not match")
    scan_public_tree(bundle)
    return {
        "declaration_sha256": protocol["declaration_sha256"],
        "scheduled_slot_count": aggregates["scheduled_slot_count"],
        "attempt_count": aggregates["attempt_count"],
        "classification": cast(dict[str, object], aggregates["comparison"])["classification"],
        "strongest_supported_claim": tiers["strongest_supported_claim"],
    }


def recompute_bundle(
    bundle: Path,
    output: Path,
    *,
    selection: ReproductionSelection = FROZEN_SELECTION,
) -> Path:
    """Verify a frozen bundle and write a fresh clean-environment result."""

    result = verify_bundle(bundle, selection=selection)
    root = _reserve_directory(output)
    result_path = root / "verification.json"
    _write_json(result_path, result)
    _seal_inventory(root, [result_path])
    return root


__all__ = [
    "FROZEN_SELECTION",
    "ReproductionSelection",
    "attempt_record_for_test",
    "build_declaration",
    "build_tiers",
    "canonical_json_bytes",
    "compute_aggregates",
    "compact_bundle_evidence",
    "load_strict_json",
    "capture_reference_path",
    "recompute_bundle",
    "retry_record_for_test",
    "scan_public_tree",
    "schedule_for_test",
    "select_eligible_attempts",
    "sha256_payload",
    "run_full_study",
    "validate_protocol",
    "verify_bundle",
    "write_declaration",
]
