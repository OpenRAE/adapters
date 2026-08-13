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
from importlib import metadata
from pathlib import Path
from statistics import NormalDist
from typing import NamedTuple, cast

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
_INVALID_ATTEMPT_SLOT_JOIN = "attempt slot join is invalid"
_INVALID_ATTEMPT_SEQUENCE = "attempt sequence is invalid"
_INVALID_FORBIDDEN_MATERIAL = "forbidden native material"
_INVALID_INVENTORY = "inventory is invalid"
_INVALID_PROTOCOL_SCHEDULE = "protocol schedule is invalid"
_INVALID_SCORE_MEASURE = "score measure is invalid"
_DISPOSITIONS = ("excluded", "failed", "invalid", "valid")
_RED_VARIANTS = ("b-line", "meander", "sleep")
_TRIAL_LENGTHS = (30, 50, 100)
_STATE_OBSERVATION_TIER = "state/observation"
_OUTCOME_EVALUATION_TIER = "outcome/evaluation"
_TIERS = (
    "authored-source",
    "contract",
    "execution-control",
    _STATE_OBSERVATION_TIER,
    _OUTCOME_EVALUATION_TIER,
    "disclosure",
)
_SCORE_METRIC_ID = "cage2-cumulative-blue-reward"
_SOURCE_PROFILE = "cage2-cyborg-2.1-source-26ce1c1"
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
_AGGREGATES_FILE = "aggregates.json"
_ATTEMPT_FILE = "attempt.json.gz"
_CLEANUP_FILE = "cleanup.json"
_ENVIRONMENT_FILE = "environment.json"
_EVIDENCE_INDEX_FILE = "evidence-index.json"
_GZIP_JSON_SUFFIX = ".json.gz"
_INVENTORY_FILE = "inventory.json"
_PROTOCOL_FILE = "protocol.json"
_REFERENCE_FILE = "reference.json"
_RUN_FILE = "run.json.gz"
_SOURCE_LEDGER_FILE = "source-ledger.json"
_TIERS_FILE = "tiers.json"
_VALIDATION_REPORT_FILE = "validation-report.md"


class ReproductionSelection(NamedTuple):
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
        return ReproductionSelection(
            frozen_revision=f"{self.frozen_revision}-test-{episodes}",
            episodes_per_condition=episodes,
            seed=self.seed,
            trial_lengths=self.trial_lengths,
            red_variants=self.red_variants,
            retry_limit=self.retry_limit,
        )


class _AttemptOutcome(NamedTuple):
    """Disposition-dependent fields for one terminal operational attempt."""

    disposition: str
    cleanup_verified: bool
    score_measure: object = None
    evidence_refs: Sequence[str] = ()
    diagnostic_code: str | None = None


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
    """Hash one file as raw bytes."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_constant(_value: str) -> object:
    """Reject non-finite JSON constants."""

    raise ValueError(_INVALID_JSON)


def _closed_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build one JSON object while rejecting duplicate keys."""

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
        if path.name.endswith(_GZIP_JSON_SUFFIX):
            raw = gzip.decompress(raw)
            if len(raw) > _MAX_DECOMPRESSED_JSON_BYTES:
                raise ValueError(_INVALID_JSON)
        value = json.loads(
            raw,
            object_pairs_hook=_closed_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, ValueError) as error:
        raise ValueError(_INVALID_JSON) from error
    return value


def load_strict_json(path: Path) -> dict[str, object]:
    """Load a duplicate-key-free finite JSON object."""

    value = _load_strict_json_value(path)
    if not isinstance(value, dict):
        raise ValueError(_INVALID_JSON)
    return cast(dict[str, object], value)


def _condition_id(trial_length: int, red_variant: str) -> str:
    """Return the stable identifier for one matrix condition."""

    return f"steps-{trial_length:03d}--red-{red_variant}"


def _schedule(selection: ReproductionSelection) -> list[dict[str, object]]:
    """Expand one selection into its ordered logical slots."""

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
    """Describe the condition-level partitions of one ordered schedule."""

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
    """Resolve and verify every frozen adapter input."""

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
    """Load and content-bind the published RAES contract inputs."""

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
    """Return the predeclared adapter-input references."""

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
    """Project source facts and known losses for this study."""

    return {
        "source": {
            "repository": "https://github.com/cage-challenge/cage-challenge-2",
            "commit": _SOURCE_COMMIT,
            "profile_id": _SOURCE_PROFILE,
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
    """Return the frozen published comparison values."""

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
    """Build the immutable study selection and method declaration."""

    return {
        "frozen_revision": selection.frozen_revision,
        "source_profile": _SOURCE_PROFILE,
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
    """Reject unknown or missing operational-index fields."""

    if set(value) != keys:
        raise ValueError(f"{label} has unknown or missing fields")


def _validate_schedule(value: object, selection: ReproductionSelection) -> None:
    """Validate an ordered slot schedule against its selection."""

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


def _validated_protocol_declaration(payload: Mapping[str, object]) -> dict[str, object]:
    """Return the digest-verified declaration from a protocol index."""

    _require_exact_keys(payload, {"declaration_sha256", "declaration"}, "protocol")
    declaration = payload["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError("protocol declaration is invalid")
    if payload["declaration_sha256"] != sha256_payload(declaration):
        raise ValueError("protocol declaration digest is invalid")
    return declaration


def _validated_protocol_contracts(
    declaration: Mapping[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Validate and return the frozen artifacts and published contracts."""

    artifacts = declaration.get("artifacts")
    if not isinstance(artifacts, list) or artifacts != _expected_artifact_refs():
        raise ValueError("protocol artifacts are invalid")
    contracts = declaration.get("published_contracts")
    if not isinstance(contracts, dict):
        raise ValueError("published contracts are invalid")
    digests = {name: sha256_payload(contract) for name, contract in contracts.items()}
    if digests != _FROZEN_CONTRACT_DIGESTS:
        raise ValueError("published contract identity is invalid")
    return cast(list[dict[str, object]], artifacts), contracts


def _validate_contract_relationships(contracts: Mapping[str, object]) -> None:
    """Validate the RAES-owned contracts and their required identity joins."""

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
        valid_join = (
            spec.task_ref.ref_id == task.task_id
            and participant_selection.implementation_identity == manifest.identity
        )
        if not valid_join:
            raise ValueError
    except Exception as error:
        raise ValueError("published contracts are invalid") from error


def _validate_declaration_methods(
    declaration: Mapping[str, object], expected: Mapping[str, object]
) -> None:
    """Validate the predeclared seed, attempt, aggregation, and comparison methods."""

    labels = {
        "seed_policy": "seed policy is invalid",
        "attempt_policy": "attempt policy is invalid",
        "aggregation": "aggregation method is invalid",
        "comparison": "comparison method is invalid",
    }
    for key, message in labels.items():
        if declaration.get(key) != expected[key]:
            raise ValueError(message)
    for key, value in expected.items():
        if key not in {"artifacts", "published_contracts"} and declaration.get(key) != value:
            raise ValueError("protocol declaration is invalid")


def validate_protocol(
    payload: Mapping[str, object],
    *,
    selection: ReproductionSelection | None = None,
) -> None:
    """Validate the closed frozen protocol and its content digest."""

    declaration = _validated_protocol_declaration(payload)
    artifacts, contracts = _validated_protocol_contracts(declaration)
    if selection is None:
        selection = _selection_from_declaration(declaration)
    _validate_contract_relationships(contracts)
    expected = _declaration(selection, artifacts, contracts)
    _validate_declaration_methods(declaration, expected)
    _validate_schedule(_schedule(selection), selection)


def _validate_source_ledger(payload: Mapping[str, object], protocol: Mapping[str, object]) -> None:
    """Validate source facts against the frozen declaration."""

    declaration = protocol["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError("source ledger artifact join is invalid")
    artifacts = declaration.get("artifacts")
    if not isinstance(artifacts, list) or dict(payload) != _source_ledger(
        cast(list[dict[str, object]], artifacts)
    ):
        raise ValueError("source ledger is invalid")


def _score_measure(run_id: str, score: float) -> dict[str, object]:
    """Build a RAES-owned derived score measure for a test projection."""

    if not math.isfinite(score):
        raise ValueError(_INVALID_SCORE_MEASURE)
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
                "ref_id": _SOURCE_PROFILE,
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
    """Validate and return one finite RAES-owned score value."""

    try:
        measure = ExperimentDerivedMeasureModel.model_validate(value)
    except Exception as error:
        raise ValueError(_INVALID_SCORE_MEASURE) from error
    score = measure.value
    if (
        measure.measure_kind != "score"
        or measure.metric_ref.ref_id != _SCORE_METRIC_ID
        or measure.value_status != "reported"
        or isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
    ):
        raise ValueError(_INVALID_SCORE_MEASURE)
    return float(score)


def _validate_attempt_slot_fields(value: Mapping[str, object], slot: Mapping[str, object]) -> None:
    """Validate the immutable logical-slot fields on one attempt."""

    for key in (
        "slot_id",
        "condition_id",
        "trial_length",
        "red_variant",
        "episode_ordinal",
    ):
        if value[key] != slot[key]:
            raise ValueError(_INVALID_ATTEMPT_SLOT_JOIN)


def _attempt_retry_limit(protocol: Mapping[str, object]) -> int:
    """Return the validated retry limit joined through the protocol."""

    declaration = protocol["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError("attempt protocol join is invalid")
    retry_limit = cast(dict[str, object], declaration["attempt_policy"])["retry_limit"]
    if type(retry_limit) is not int:
        raise ValueError(_INVALID_ATTEMPT_SEQUENCE)
    return retry_limit


def _validate_attempt_identity(
    value: Mapping[str, object], slot: Mapping[str, object], retry_limit: int
) -> None:
    """Validate one attempt's sequence and predecessor-linked identity."""

    sequence = value["attempt_sequence"]
    if type(sequence) is not int or not 1 <= sequence <= retry_limit + 1:
        raise ValueError(_INVALID_ATTEMPT_SEQUENCE)
    expected_run_id = f"{slot['slot_id']}-attempt-{sequence:02d}"
    predecessor = None
    if sequence > 1:
        predecessor = f"{slot['slot_id']}-attempt-{sequence - 1:02d}"
    if value["run_id"] != expected_run_id or value["predecessor_run_id"] != predecessor:
        raise ValueError("attempt identities are invalid")


def _validate_attempt_outcome(value: Mapping[str, object]) -> None:
    """Validate disposition-dependent cleanup and score fields."""

    disposition = value["disposition"]
    if disposition not in _DISPOSITIONS:
        raise ValueError("attempt disposition is invalid")
    if disposition == "valid":
        if value["cleanup_verified"] is not True:
            raise ValueError("valid attempt cleanup is invalid")
        _validate_score_measure(value["score_measure"])
    elif value["score_measure"] is not None:
        raise ValueError("ineligible attempt has a score measure")


def _validate_attempt(
    value: Mapping[str, object], protocol: Mapping[str, object], slot: Mapping[str, object]
) -> None:
    """Validate one operational attempt against its logical slot."""

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
    _validate_attempt_slot_fields(value, slot)
    _validate_attempt_identity(value, slot, _attempt_retry_limit(protocol))
    _validate_attempt_outcome(value)


def _selection_from_declaration(declaration: Mapping[str, object]) -> ReproductionSelection:
    """Recover the immutable selection from a validated declaration."""

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
        raise ValueError(_INVALID_PROTOCOL_SCHEDULE) from None
    return selection


def _slot_index(protocol: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Index every declared logical slot by identifier."""

    declaration = protocol["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError(_INVALID_PROTOCOL_SCHEDULE)
    selection = _selection_from_declaration(declaration)
    schedule = _schedule(selection)
    if declaration["schedule_partitions"] != _schedule_partitions(selection):
        raise ValueError(_INVALID_PROTOCOL_SCHEDULE)
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
            raise ValueError(_INVALID_ATTEMPT_SLOT_JOIN)
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
            raise ValueError(_INVALID_ATTEMPT_SEQUENCE)
        valid = next((item for item in ordered if item["disposition"] == "valid"), None)
        if valid is not None:
            selected.append(valid)
    return selected


def _interval(values: Sequence[float], critical_value: float) -> dict[str, object]:
    """Compute the predeclared normal-approximation interval."""

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
    """Return one finite non-boolean numeric value."""

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("finite numeric value is required")
    return float(value)


def _reproduction_classification(*, exact: bool, bounded: bool, complete: bool) -> str:
    """Return the predeclared result class without nested conditional expressions."""

    if exact:
        return "exact"
    if bounded:
        return "bounded"
    return "failed" if complete else "unavailable"


def _outcome_tier_result(outcome_class: object) -> str:
    """Map the aggregate result class to the CybORG outcome tier."""

    if outcome_class in {"exact", "bounded"}:
        return "pass"
    if outcome_class == "failed":
        return "fail"
    return "weakened"


def _condition_comparison_flags(
    conditions: Sequence[Mapping[str, object]],
    published_by_id: Mapping[str, Mapping[str, object]],
    minimum: object,
) -> tuple[bool, bool, bool]:
    """Return completeness plus exact and bounded condition-level flags."""

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
        difference = abs(float(mean) - _finite_float(oracle["mean"]))
        bounded = bounded and difference <= _finite_float(oracle["bounded_margin"])
    return complete, exact, bounded


def _primary_comparison(
    declaration: Mapping[str, object],
    conditions: Sequence[Mapping[str, object]],
    published: Mapping[str, object],
    *,
    complete: bool,
    bounded: bool,
) -> tuple[float | None, float | None, list[float] | None, bool]:
    """Compute the primary total and its interval-level bounded check."""

    total_mean = None
    if complete:
        total_mean = math.fsum(cast(float, item["mean"]) for item in conditions)
    total_variance = None
    total_interval = None
    variances_available = complete and all(
        item["sample_variance"] is not None for item in conditions
    )
    if variances_available:
        total_variance = math.fsum(
            cast(float, item["sample_variance"]) / cast(int, item["eligible_n"])
            for item in conditions
        )
        critical = _finite_float(
            cast(dict[str, object], declaration["aggregation"])["critical_value"]
        )
        half_width = critical * math.sqrt(total_variance)
        mean = cast(float, total_mean)
        total_interval = [mean - half_width, mean + half_width]
        published_interval = cast(list[float], published["primary_total_interval_95"])
        intervals_cover = (
            total_interval[0] <= _finite_float(published["primary_total"]) <= total_interval[1]
            and published_interval[0] <= mean <= published_interval[1]
        )
        bounded = bounded and intervals_cover
    else:
        bounded = False
    return total_mean, total_variance, total_interval, bounded


def _comparison(
    declaration: Mapping[str, object], conditions: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """Compare observed conditions with the frozen published values."""

    published = cast(
        dict[str, object], cast(dict[str, object], declaration["comparison"])["published"]
    )
    published_by_id = {
        cast(str, item["condition_id"]): item
        for item in cast(list[dict[str, object]], published["conditions"])
    }
    minimum = cast(dict[str, object], declaration["aggregation"])["minimum_eligible_per_condition"]
    complete, exact, bounded = _condition_comparison_flags(conditions, published_by_id, minimum)
    total_mean, total_variance, total_interval, bounded = _primary_comparison(
        declaration,
        conditions,
        published,
        complete=complete,
        bounded=bounded,
    )
    classification = _reproduction_classification(
        exact=exact,
        bounded=bounded,
        complete=complete,
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
        "authored-source": ("pass", [_PROTOCOL_FILE, _SOURCE_LEDGER_FILE]),
        "contract": ("pass", [_PROTOCOL_FILE, "runs/"]),
        "execution-control": (
            "weakened",
            ["source-ledger.json#loss-evaluation-seed-unbound", "protocol.json#seed_policy"],
        ),
        _STATE_OBSERVATION_TIER: (
            "weakened",
            ["source-ledger.json#loss-native-observation-boundary"],
        ),
        _OUTCOME_EVALUATION_TIER: (
            _outcome_tier_result(outcome_class),
            ["aggregates.json#comparison"],
        ),
        "disclosure": (
            "pass",
            [f"{_SOURCE_LEDGER_FILE}#loss_refs", _VALIDATION_REPORT_FILE],
        ),
    }
    reference_keys = {
        "authored-source": "authored_source",
        "contract": "contract",
        "execution-control": "execution_control",
        _STATE_OBSERVATION_TIER: "state_observation",
        _OUTCOME_EVALUATION_TIER: "outcome_evaluation",
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
    """Recursively reject forbidden native or host material."""

    if isinstance(value, dict):
        for key, item in value.items():
            if key in _FORBIDDEN_FIELDS:
                raise ValueError(_INVALID_FORBIDDEN_MATERIAL)
            _scan_value(item)
    elif isinstance(value, list):
        for item in value:
            _scan_value(item)
    elif isinstance(value, str) and any(token in value for token in _FORBIDDEN_TEXT):
        raise ValueError(_INVALID_FORBIDDEN_MATERIAL)


def _strict_public_json(path: Path, raw: bytes) -> object:
    """Decode one bounded public JSON or gzip-compressed JSON artifact."""

    if path.name.endswith(_GZIP_JSON_SUFFIX):
        raw = gzip.decompress(raw)
        if len(raw) > _MAX_DECOMPRESSED_JSON_BYTES:
            raise ValueError(_INVALID_JSON)
    return json.loads(
        raw,
        object_pairs_hook=_closed_pairs,
        parse_constant=_reject_constant,
    )


def _scan_public_file(path: Path) -> None:
    """Scan one regular public file for forbidden material and JSON fields."""

    raw = path.read_bytes()
    if any(token.encode() in raw for token in _FORBIDDEN_TEXT):
        raise ValueError(_INVALID_FORBIDDEN_MATERIAL)
    if path.suffix != ".json" and not path.name.endswith(_GZIP_JSON_SUFFIX):
        return
    try:
        value = _strict_public_json(path, raw)
    except ValueError as error:
        raise ValueError(_INVALID_JSON) from error
    _scan_value(value)


def scan_public_tree(root: Path) -> None:
    """Reject native, host, traceback, symlink, and special-file material."""

    if root.is_symlink() or not root.is_dir():
        raise ValueError("public tree is invalid")
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("public tree is invalid")
        if path.is_file():
            _scan_public_file(path)


def _reserve_directory(path: Path) -> Path:
    """Reserve one fresh mode-0700 output root without parent discovery."""

    resolved = path.resolve()
    os.mkdir(resolved, 0o700)
    return resolved


def _write_json(path: Path, payload: object) -> None:
    """Atomically write one canonical JSON object."""

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
    """Return the allowlisted media type for one exported file."""

    if path.suffix == ".gz":
        return "application/gzip"
    return "application/json" if path.suffix == ".json" else "text/markdown"


def _inventory_entry(root: Path, path: Path) -> dict[str, object]:
    """Build one bounded relative inventory entry."""

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
    """Write an inventory after all of its members are final."""

    inventory: dict[str, object] = {
        "artifacts": [
            _inventory_entry(root, path)
            for path in sorted(members, key=lambda item: item.relative_to(root).as_posix())
        ]
    }
    _write_json(root / _INVENTORY_FILE, inventory)
    return inventory


def _inventory_item_mapping(item: object) -> tuple[dict[str, object], str]:
    """Return one shape-validated inventory entry and relative path."""

    expected_keys = {"path", "media_type", "sha256", "size_bytes"}
    if not isinstance(item, dict) or set(item) != expected_keys:
        raise ValueError(_INVALID_INVENTORY)
    relative = item["path"]
    if not isinstance(relative, str):
        raise ValueError(_INVALID_INVENTORY)
    return item, relative


def _inventory_candidate(root: Path, relative: str, seen: set[str]) -> Path:
    """Resolve one safe, unique, regular inventory member path."""

    source = root / relative
    candidate = source.resolve()
    invalid_path = (
        relative in seen
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or not candidate.is_relative_to(root.resolve())
        or source.is_symlink()
        or not candidate.is_file()
    )
    if invalid_path:
        raise ValueError(_INVALID_INVENTORY)
    return candidate


def _validated_inventory_member(root: Path, item: object, seen: set[str]) -> str:
    """Validate one inventory member and return its relative path."""

    mapping, relative = _inventory_item_mapping(item)
    candidate = _inventory_candidate(root, relative, seen)
    if mapping != _inventory_entry(root, candidate):
        raise ValueError("inventory digest is invalid")
    return relative


def _verify_direct_inventory_members(root: Path, seen: set[str]) -> None:
    """Require the inventory to cover every direct regular file."""

    direct_files = {
        path.name for path in root.iterdir() if path.is_file() and path.name != _INVENTORY_FILE
    }
    inventoried = {Path(relative).name for relative in seen if len(Path(relative).parts) == 1}
    if direct_files != inventoried:
        raise ValueError("inventory membership is incomplete")


def _verify_inventory(root: Path, *, expected_members: set[str] | None = None) -> dict[str, object]:
    """Verify one sealed inventory and its exact membership."""

    inventory = load_strict_json(root / _INVENTORY_FILE)
    if set(inventory) != {"artifacts"} or not isinstance(inventory["artifacts"], list):
        raise ValueError(_INVALID_INVENTORY)
    seen: set[str] = set()
    for item in inventory["artifacts"]:
        relative = _validated_inventory_member(root, item, seen)
        seen.add(relative)
    _verify_direct_inventory_members(root, seen)
    if expected_members is not None and seen != expected_members:
        raise ValueError("inventory membership is incomplete")
    return inventory


def _write_schedule_partitions(
    root: Path, protocol: Mapping[str, object], selection: ReproductionSelection
) -> list[Path]:
    """Write the bounded per-condition schedule files."""

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
    protocol_path = root / _PROTOCOL_FILE
    ledger_path = root / _SOURCE_LEDGER_FILE
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
    """Load the authored scenario and published run contracts."""

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
            _REFERENCE_FILE,
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
    _validate_reference_identity(reference)
    _validate_reference_diagnostics(reference)
    _validate_reference_counts(reference)
    _validate_reference_limitations(reference)


def _validate_reference_identity(reference: Mapping[str, object]) -> None:
    """Validate the fixed reference-processor identity and tier results."""

    if (
        reference["processor"] != "raes-processor-reference"
        or reference["scenario_name"] != "cage2-research"
        or reference["target_manifest"] != "cyborg-cage2"
        or reference["evidence_refs"] != [_REFERENCE_FILE, f"{_PROTOCOL_FILE}#explicit_non_claims"]
    ):
        raise ValueError("reference evidence identity is invalid")
    _validate_reference_tiers(reference)


def _validate_reference_tiers(reference: Mapping[str, object]) -> None:
    """Validate the fixed reference-path tier strengths."""

    weakened = ("execution_control", "state_observation", "outcome_evaluation")
    if any(reference[key] != "weakened" for key in weakened):
        raise ValueError("reference evidence identity is invalid")
    if any(reference[key] not in {"pass", "fail"} for key in ("authored_source", "contract")):
        raise ValueError("reference evidence result is invalid")
    if reference["disclosure"] != "pass":
        raise ValueError("reference evidence result is invalid")


def _validate_reference_diagnostics(reference: Mapping[str, object]) -> None:
    """Validate the bounded planning diagnostic code list."""

    codes = reference["planning_error_codes"]
    if not isinstance(codes, list) or any(not isinstance(code, str) or not code for code in codes):
        raise ValueError("reference diagnostics are invalid")


def _validate_reference_counts(reference: Mapping[str, object]) -> None:
    """Validate the three non-negative planned-operation counts."""

    counts = reference["planned_operation_counts"]
    if (
        not isinstance(counts, dict)
        or set(counts) != {"provisioning", "orchestration", "evaluation"}
        or any(type(value) is not int or value < 0 for value in counts.values())
    ):
        raise ValueError("reference operation counts are invalid")


def _validate_reference_limitations(reference: Mapping[str, object]) -> None:
    """Validate the fixed reference-path limitations statement."""

    limitations = reference["limitations"]
    if not isinstance(limitations, list) or limitations != [
        "The reference processor realizes authored contracts and a target plan only.",
        "It does not execute CybORG transitions, observations, rewards, or terminal behavior.",
    ]:
        raise ValueError("reference limitations are invalid")


def _evidence_step(record: ExperimentEvidenceRecordModel) -> int:
    """Return the logical step bound to one evidence record."""

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
    """Persist one valid episode's exact RAES evidence closure."""

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
    evidence_index = run_root / _EVIDENCE_INDEX_FILE
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
    retained_episode = EpisodeEvidence(
        completed_steps=episode.completed_steps,
        evidence_records=tuple(retained),
        derived_measures=episode.derived_measures,
        proposition_truth_results=episode.proposition_truth_results,
        objective_results=episode.objective_results,
        diagnostics=episode.diagnostics,
        cleanup_verified=episode.cleanup_verified,
    )
    run = archival_run(
        controls=controls,
        scenario_digest=scenario_digest,
        task=task,
        episode=retained_episode,
        evidence_artifact=artifact,
    )
    validate_experiment_run_against_task(task, run)
    _write_gzip_json(run_root / _RUN_FILE, run.model_dump(mode="json"))
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
            _EVIDENCE_INDEX_FILE,
            "episode-summary.json.gz",
            _RUN_FILE,
        ],
    }


def _attempt_record(
    protocol: Mapping[str, object],
    slot: Mapping[str, object],
    attempt_sequence: int,
    outcome: _AttemptOutcome,
) -> dict[str, object]:
    """Build one immutable terminal operational attempt record."""

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
        "disposition": outcome.disposition,
        "diagnostic_code": outcome.diagnostic_code,
        "cleanup_verified": outcome.cleanup_verified,
        "score_measure": outcome.score_measure,
        "evidence_refs": list(outcome.evidence_refs),
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
    """Bind one condition's logical slots to RAES run controls."""

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
    """Project bounded apparatus provenance without host-sensitive values."""

    def version(name: str) -> str:
        """Return one installed distribution version or an absence marker."""

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
    """Render the stable human-readable validation summary."""

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
    """Write the stable validation summary."""

    path = root / _VALIDATION_REPORT_FILE
    _write_text(path, _validation_report_text(tiers))
    return path


def _condition_inventory(condition_root: Path) -> Path:
    """Seal one condition from its cleanup and attempt inventories."""

    members = [condition_root / _CLEANUP_FILE]
    members.extend(sorted(condition_root.glob(f"*/{_INVENTORY_FILE}")))
    _seal_inventory(condition_root, members)
    return condition_root / _INVENTORY_FILE


class _StudyContext(NamedTuple):
    """Immutable dependencies shared across every condition attempt."""

    root: Path
    protocol: Mapping[str, object]
    scenario: object
    task: ExperimentTaskModel
    manifest: ParticipantImplementationManifestModel
    participant_selection: ParticipantImplementationSelectionModel
    configuration: ParticipantConfigurationResultModel
    driver: CyborgDriver
    checkpoint_stream: Callable[[], object]
    restore_stream: Callable[[object], None]
    scenario_digest: str
    progress: Callable[[str, int, int], None] | None


class _ConditionAttemptResult(NamedTuple):
    """Execution state needed to seal one complete condition attempt."""

    sequence: int
    succeeded: bool
    attempt_slots: list[dict[str, object]]
    staged: dict[str, dict[str, object]]
    run_roots: dict[str, Path]


def _recoverable_study_driver(
    driver: object | None, selection: ReproductionSelection
) -> tuple[CyborgDriver, Callable[[], object], Callable[[object], None]]:
    """Initialize and return a driver with recoverable ordered-stream controls."""

    runtime_driver = cast(
        CyborgDriver,
        driver if driver is not None else SourceInstalledCyborgDriver(expected_version="2.1"),
    )
    begin_value = getattr(runtime_driver, "begin_ordered_stream", None)
    checkpoint_value = getattr(runtime_driver, "ordered_stream_checkpoint", None)
    restore_value = getattr(runtime_driver, "restore_ordered_stream", None)
    if not all(callable(item) for item in (begin_value, checkpoint_value, restore_value)):
        raise ValueError("study driver has no recoverable ordered stream")
    begin_stream = cast(Callable[[int], None], begin_value)
    checkpoint_stream = cast(Callable[[], object], checkpoint_value)
    restore_stream = cast(Callable[[object], None], restore_value)
    begin_stream(selection.seed)
    return runtime_driver, checkpoint_stream, restore_stream


def _condition_attempt_roots(
    condition_root: Path, attempt_slots: Sequence[Mapping[str, object]]
) -> dict[str, Path]:
    """Reserve one private directory for every run in a condition attempt."""

    roots: dict[str, Path] = {}
    for attempt_slot in attempt_slots:
        run_id = cast(str, attempt_slot["run_id"])
        run_root = condition_root / run_id
        os.mkdir(run_root, 0o700)
        roots[run_id] = run_root
    return roots


def _execute_condition_attempt(
    context: _StudyContext,
    condition_id: str,
    slots: Sequence[Mapping[str, object]],
    sequence: int,
) -> _ConditionAttemptResult:
    """Execute one full condition attempt and retain its per-run evidence."""

    attempt_slots = [_slot_for_attempt(slot, sequence) for slot in slots]
    condition_root = context.root / "runs" / condition_id
    run_roots = _condition_attempt_roots(condition_root, attempt_slots)
    staged: dict[str, dict[str, object]] = {}

    def consume(controls: RunControls, episode: EpisodeEvidence) -> None:
        """Persist one episode and report bounded condition progress."""

        run_root = run_roots[controls.run_id]
        staged[controls.run_id] = _write_episode_evidence(
            run_root,
            (run_root / _EVIDENCE_INDEX_FILE).relative_to(context.root).as_posix(),
            controls,
            episode,
            context.task,
            context.scenario_digest,
        )
        if context.progress is not None:
            context.progress(condition_id, len(staged), len(slots))

    controls = _condition_controls(
        attempt_slots,
        context.protocol,
        context.manifest,
        context.participant_selection,
        context.configuration,
    )
    succeeded = False
    try:
        with (
            Path(os.devnull).open("w", encoding="utf-8") as sink,
            redirect_stdout(sink),
            redirect_stderr(sink),
        ):
            execute_episode_series(
                context.scenario,
                controls,
                driver=context.driver,
                episode_consumer=consume,
                retain_evidence=False,
            )
        succeeded = len(staged) == len(slots)
    except Exception:
        succeeded = False
    return _ConditionAttemptResult(sequence, succeeded, attempt_slots, staged, run_roots)


def _discard_failed_run(run_root: Path) -> None:
    """Delete incomplete portable artifacts after validating their boundary."""

    for artifact in run_root.iterdir():
        if artifact.is_symlink() or not artifact.is_file():
            raise ValueError("failed attempt artifact boundary is invalid")
        artifact.unlink()


def _condition_attempt_records(
    protocol: Mapping[str, object],
    slots: Sequence[Mapping[str, object]],
    result: _ConditionAttemptResult,
) -> list[dict[str, object]]:
    """Seal and return every operational record from one condition attempt."""

    records: list[dict[str, object]] = []
    for slot, attempt_slot in zip(slots, result.attempt_slots, strict=True):
        run_id = cast(str, attempt_slot["run_id"])
        run_root = result.run_roots[run_id]
        if result.succeeded:
            stage = result.staged[run_id]
            outcome = _AttemptOutcome(
                disposition="valid",
                cleanup_verified=True,
                score_measure=stage["score_measure"],
                evidence_refs=cast(list[str], stage["evidence_refs"]),
            )
        else:
            _discard_failed_run(run_root)
            outcome = _AttemptOutcome(
                disposition="failed",
                cleanup_verified=False,
                diagnostic_code="cyborg-reproduction.condition-session-failed",
            )
        record = _attempt_record(protocol, slot, result.sequence, outcome)
        _write_gzip_json(run_root / _ATTEMPT_FILE, record)
        _seal_inventory(run_root, [item for item in run_root.rglob("*") if item.is_file()])
        records.append(record)
    return records


def _run_study_condition(
    context: _StudyContext,
    condition_id: str,
    slots: Sequence[Mapping[str, object]],
    retry_limit: int,
) -> tuple[list[dict[str, object]], Path]:
    """Execute the retry-bounded lifecycle for one independent condition."""

    condition_root = context.root / "runs" / condition_id
    os.mkdir(condition_root, 0o700)
    checkpoint = context.checkpoint_stream()
    attempts: list[dict[str, object]] = []
    cleanup_attempts: list[dict[str, object]] = []
    completed = False
    for sequence in range(1, retry_limit + 2):
        if sequence > 1:
            context.restore_stream(checkpoint)
        result = _execute_condition_attempt(context, condition_id, slots, sequence)
        cleanup_attempts.append(
            {
                "attempt_sequence": sequence,
                "run_count": len(result.attempt_slots),
                "verified": result.succeeded,
            }
        )
        attempts.extend(_condition_attempt_records(context.protocol, slots, result))
        if result.succeeded:
            completed = True
            break
    _write_json(
        condition_root / _CLEANUP_FILE,
        {
            "condition_id": condition_id,
            "completed": completed,
            "attempts": cleanup_attempts,
        },
    )
    return attempts, _condition_inventory(condition_root)


def _execute_study_schedule(
    context: _StudyContext, selection: ReproductionSelection
) -> tuple[list[dict[str, object]], list[Path]]:
    """Execute all frozen conditions in their declared stream order."""

    os.mkdir(context.root / "runs", 0o700)
    schedule = _schedule(selection)
    all_attempts: list[dict[str, object]] = []
    inventories: list[Path] = []
    for partition in _schedule_partitions(selection):
        condition_id = cast(str, partition["condition_id"])
        slots = [item for item in schedule if item["condition_id"] == condition_id]
        attempts, inventory = _run_study_condition(
            context, condition_id, slots, selection.retry_limit
        )
        all_attempts.extend(attempts)
        inventories.append(inventory)
    return all_attempts, inventories


def _finalize_study_bundle(
    root: Path,
    protocol: Mapping[str, object],
    reference: Mapping[str, object],
    attempts: Sequence[Mapping[str, object]],
    members: Sequence[Path],
) -> None:
    """Write the deterministic projections and seal the completed study."""

    aggregates = compute_aggregates(protocol, attempts)
    aggregates_path = root / _AGGREGATES_FILE
    _write_json(aggregates_path, aggregates)
    tiers = build_tiers(protocol, aggregates, reference)
    tiers_path = root / _TIERS_FILE
    _write_json(tiers_path, tiers)
    report_path = _write_validation_report(root, tiers)
    scan_public_tree(root)
    _seal_inventory(root, [*members, aggregates_path, tiers_path, report_path])


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
    protocol_path = root / _PROTOCOL_FILE
    ledger_path = root / _SOURCE_LEDGER_FILE
    _write_json(protocol_path, protocol)
    _write_json(ledger_path, source_ledger)
    plan_paths = _write_schedule_partitions(root, protocol, selection)
    scenario, task, manifest, participant_selection, configuration = _load_study_inputs(source_root)
    reference = capture_reference_path(source_root)
    reference_path = root / _REFERENCE_FILE
    _write_json(reference_path, reference)
    environment_path = root / _ENVIRONMENT_FILE
    _write_json(environment_path, _write_environment(protocol))
    runtime_driver, checkpoint_stream, restore_stream = _recoverable_study_driver(driver, selection)
    scenario_digest = task.scenario_ref.ref_digest
    if not isinstance(scenario_digest, str):
        raise ValueError("task scenario digest is unavailable")
    context = _StudyContext(
        root,
        protocol,
        scenario,
        task,
        manifest,
        participant_selection,
        configuration,
        runtime_driver,
        checkpoint_stream,
        restore_stream,
        scenario_digest,
        progress,
    )
    all_attempts, condition_inventories = _execute_study_schedule(context, selection)
    root_members = (
        protocol_path,
        ledger_path,
        reference_path,
        environment_path,
        *plan_paths,
        *condition_inventories,
    )
    _finalize_study_bundle(root, protocol, reference, all_attempts, root_members)
    return root


def _validated_evidence_index(run_root: Path) -> dict[str, object]:
    """Load and validate the top-level evidence index shape."""

    index = load_strict_json(run_root / _EVIDENCE_INDEX_FILE)
    _require_exact_keys(index, {"record_count", "chunks", "episode_summary"}, "evidence index")
    chunks = index["chunks"]
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("evidence index is invalid")
    return index


def _evidence_chunk_mapping(chunk: object) -> dict[str, object]:
    """Return one shape-validated evidence chunk entry."""

    if not isinstance(chunk, dict):
        raise ValueError("evidence index is invalid")
    _require_exact_keys(
        chunk,
        {"path", "sha256", "record_count", "first_logical_step", "last_logical_step"},
        "evidence chunk",
    )
    return chunk


def _chunk_records(
    run_root: Path, chunk: Mapping[str, object]
) -> list[ExperimentEvidenceRecordModel]:
    """Load and validate the contents of one evidence chunk."""

    relative = chunk["path"]
    if not isinstance(relative, str) or Path(relative).name != relative:
        raise ValueError("evidence chunk path is invalid")
    path = run_root / relative
    if _sha256_file(path) != chunk["sha256"]:
        raise ValueError("evidence chunk digest is invalid")
    values = _load_strict_json_value(path)
    if not isinstance(values, list) or len(values) != chunk["record_count"]:
        raise ValueError("evidence chunk is invalid")
    return [ExperimentEvidenceRecordModel.model_validate(item) for item in values]


def _validate_chunk_order(
    records: Sequence[ExperimentEvidenceRecordModel], chunk: Mapping[str, object]
) -> None:
    """Validate monotonic steps and the declared evidence-chunk bounds."""

    steps = [_evidence_step(record) for record in records]
    valid_order = (
        bool(steps)
        and steps == sorted(steps)
        and min(steps) == chunk["first_logical_step"]
        and max(steps) == chunk["last_logical_step"]
    )
    if not valid_order:
        raise ValueError("evidence chunk ordering is invalid")


def _validated_chunk_records(run_root: Path, chunk: object) -> list[ExperimentEvidenceRecordModel]:
    """Load and validate one ordered evidence chunk."""

    mapping = _evidence_chunk_mapping(chunk)
    records = _chunk_records(run_root, mapping)
    _validate_chunk_order(records, mapping)
    return records


def _validated_evidence_records(
    run_root: Path, index: Mapping[str, object]
) -> list[ExperimentEvidenceRecordModel]:
    """Return the complete unique record sequence declared by an index."""

    records = [
        record
        for chunk in cast(list[dict[str, object]], index["chunks"])
        for record in _validated_chunk_records(run_root, chunk)
    ]
    record_ids = [record.evidence_record_id for record in records]
    if len(record_ids) != index["record_count"] or len(record_ids) != len(set(record_ids)):
        raise ValueError("evidence record closure is invalid")
    return records


def _validated_episode_summary(
    run_root: Path, index: Mapping[str, object]
) -> tuple[Path, dict[str, object], list[ExperimentDerivedMeasureModel]]:
    """Load the digest-bound episode summary and its derived measures."""

    summary_ref = index["episode_summary"]
    if not isinstance(summary_ref, dict):
        raise ValueError("episode summary reference is invalid")
    _require_exact_keys(summary_ref, {"path", "sha256"}, "episode summary reference")
    relative = summary_ref["path"]
    if not isinstance(relative, str) or Path(relative).name != relative:
        raise ValueError("episode summary path is invalid")
    summary_path = run_root / relative
    if _sha256_file(summary_path) != summary_ref["sha256"]:
        raise ValueError("episode summary digest is invalid")
    summary = load_strict_json(summary_path)
    _require_exact_keys(
        summary,
        {"derived_measures", "proposition_truth", "objective_results", "diagnostics"},
        "episode summary",
    )
    values = summary["derived_measures"]
    if not isinstance(values, list) or not values:
        raise ValueError("derived measures are invalid")
    measures = [ExperimentDerivedMeasureModel.model_validate(item) for item in values]
    return summary_path, summary, measures


def _referenced_record_ids(
    measures: Sequence[ExperimentDerivedMeasureModel],
) -> set[str]:
    """Return the exact record identifiers referenced by derived measures."""

    return {ref.ref_id for measure in measures for ref in measure.source_evidence_refs}


def _retained_evidence_records(
    records: Sequence[ExperimentEvidenceRecordModel], referenced: set[str]
) -> list[ExperimentEvidenceRecordModel]:
    """Select and validate the exact referenced evidence closure."""

    retained = [record for record in records if record.evidence_record_id in referenced]
    if {record.evidence_record_id for record in retained} != referenced:
        raise ValueError("derived-measure evidence closure is invalid")
    return retained


def _rewrite_compacted_index(
    run_root: Path,
    summary_path: Path,
    retained: Sequence[ExperimentEvidenceRecordModel],
) -> bytes:
    """Replace evidence chunks and return the rewritten index bytes."""

    for path in run_root.glob("evidence-*.json.gz"):
        path.unlink()
    chunks = _write_evidence_chunks(run_root, retained)
    index_path = run_root / _EVIDENCE_INDEX_FILE
    _write_json(
        index_path,
        {
            "record_count": len(retained),
            "chunks": chunks,
            "episode_summary": {
                "path": summary_path.relative_to(run_root).as_posix(),
                "sha256": _sha256_file(summary_path),
            },
        },
    )
    return index_path.read_bytes()


def _rewrite_compacted_run(
    run_root: Path,
    task: ExperimentTaskModel,
    referenced: set[str],
    index_bytes: bytes,
) -> None:
    """Rebind one run contract to its compacted evidence index and reseal it."""

    run_payload = load_strict_json(run_root / _RUN_FILE)
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
    _write_gzip_json(run_root / _RUN_FILE, run.model_dump(mode="json"))
    members = [
        path for path in run_root.iterdir() if path.is_file() and path.name != _INVENTORY_FILE
    ]
    _seal_inventory(run_root, members)


def _compact_valid_run_evidence(run_root: Path, task: ExperimentTaskModel) -> None:
    """Reduce one valid run to records referenced by retained measures."""

    index = _validated_evidence_index(run_root)
    summary_path, _, measures = _validated_episode_summary(run_root, index)
    referenced = _referenced_record_ids(measures)
    records = _validated_evidence_records(run_root, index)
    retained = _retained_evidence_records(records, referenced)
    index_bytes = _rewrite_compacted_index(run_root, summary_path, retained)
    _rewrite_compacted_run(run_root, task, referenced, index_bytes)


def _validated_attempt_from_root(
    run_root: Path,
    protocol: Mapping[str, object],
    slots: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Load and validate one attempt joined to a declared logical slot."""

    attempt = load_strict_json(run_root / _ATTEMPT_FILE)
    slot_id = attempt.get("slot_id")
    if not isinstance(slot_id, str) or slot_id not in slots:
        raise ValueError(_INVALID_ATTEMPT_SLOT_JOIN)
    _validate_attempt(attempt, protocol, slots[slot_id])
    return attempt


def _condition_run_roots(condition_root: Path) -> list[Path]:
    """Return the ordered direct run directories for one condition."""

    return sorted(path for path in condition_root.iterdir() if path.is_dir())


def _verify_condition_inventory(condition_root: Path, run_roots: Sequence[Path]) -> None:
    """Verify one condition inventory against its direct run inventories."""

    _verify_inventory(
        condition_root,
        expected_members={_CLEANUP_FILE}
        | {f"{run_root.name}/{_INVENTORY_FILE}" for run_root in run_roots},
    )


def _refresh_bundle_projections(
    bundle: Path,
    protocol: Mapping[str, object],
    attempts: Sequence[Mapping[str, object]],
    root_members: Sequence[Path],
) -> None:
    """Recompute and reseal deterministic projections after compaction."""

    aggregates = compute_aggregates(protocol, attempts)
    _write_json(bundle / _AGGREGATES_FILE, aggregates)
    reference = load_strict_json(bundle / _REFERENCE_FILE)
    _validate_reference(reference)
    tiers = build_tiers(protocol, aggregates, reference)
    _write_json(bundle / _TIERS_FILE, tiers)
    _write_validation_report(bundle, tiers)
    _seal_inventory(bundle, root_members)


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
    protocol = load_strict_json(bundle / _PROTOCOL_FILE)
    selection = _selection_from_declaration(cast(dict[str, object], protocol["declaration"]))
    validate_protocol(protocol, selection=selection)
    _verify_inventory(bundle)
    contracts = cast(
        dict[str, object], cast(dict[str, object], protocol["declaration"])["published_contracts"]
    )
    task = ExperimentTaskModel.model_validate(contracts["experiment_task"])
    slots = _slot_index(protocol)
    root_inventory = load_strict_json(bundle / _INVENTORY_FILE)
    inventory_artifacts = cast(list[dict[str, object]], root_inventory["artifacts"])
    root_members = [bundle / cast(str, item["path"]) for item in inventory_artifacts]
    condition_roots = sorted(path for path in (bundle / "runs").iterdir() if path.is_dir())
    run_roots = [
        run_root
        for condition_root in condition_roots
        for run_root in _condition_run_roots(condition_root)
    ]
    total = len(run_roots)
    completed = 0
    all_attempts: list[dict[str, object]] = []
    for condition_root in condition_roots:
        condition_run_roots = _condition_run_roots(condition_root)
        _verify_condition_inventory(condition_root, condition_run_roots)
        for run_root in condition_run_roots:
            _verify_inventory(run_root)
            attempt = _validated_attempt_from_root(run_root, protocol, slots)
            all_attempts.append(attempt)
            if attempt["disposition"] == "valid":
                _compact_valid_run_evidence(run_root, task)
            completed += 1
            if progress is not None:
                progress(completed, total)
        _condition_inventory(condition_root)
    _refresh_bundle_projections(bundle, protocol, all_attempts, root_members)
    verify_bundle(bundle, selection=selection)
    return bundle


def _verify_schedule_partitions(root: Path, protocol: Mapping[str, object]) -> None:
    """Verify every condition plan against the frozen declaration."""

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


def _reported_score_measure(
    measures: Sequence[ExperimentDerivedMeasureModel],
) -> ExperimentDerivedMeasureModel | None:
    """Return the retained reported score measure when present."""

    return next(
        (
            item
            for item in measures
            if item.metric_ref.ref_id == _SCORE_METRIC_ID
            and item.measure_kind == "score"
            and item.value_status == "reported"
        ),
        None,
    )


def _validate_attempt_episode_score(
    attempt: Mapping[str, object], measures: Sequence[ExperimentDerivedMeasureModel]
) -> None:
    """Require an attempt score to equal its retained episode score measure."""

    score = _reported_score_measure(measures)
    if score is None:
        raise ValueError("attempt score does not join the episode evidence")
    observed = canonical_json_bytes(score.model_dump(mode="json"))
    if observed != canonical_json_bytes(attempt["score_measure"]):
        raise ValueError("attempt score does not join the episode evidence")


def _validate_run_traceability(
    run_payload: Mapping[str, object],
    known_records: set[str],
    measures: Sequence[ExperimentDerivedMeasureModel],
) -> None:
    """Validate the run's exact evidence-record and measure reference closure."""

    traceability = cast(dict[str, object], run_payload["traceability"])
    record_refs = cast(list[dict[str, object]], traceability["evidence_record_refs"])
    measure_refs = cast(list[dict[str, object]], traceability["derived_measure_refs"])
    if {cast(str, item["ref_id"]) for item in record_refs} != known_records:
        raise ValueError("run evidence traceability is incomplete")
    expected_measures = {item.derived_measure_id for item in measures}
    if {cast(str, item["ref_id"]) for item in measure_refs} != expected_measures:
        raise ValueError("run measure traceability is incomplete")


def _validate_run_artifact(
    bundle: Path,
    run_payload: Mapping[str, object],
    index_path: Path,
) -> None:
    """Validate the run's sole portable evidence artifact reference."""

    relative = index_path.relative_to(bundle).as_posix()
    artifacts = cast(list[dict[str, object]], run_payload["evidence_artifacts"])
    if len(artifacts) != 1 or artifacts[0].get("uri") != relative:
        raise ValueError("run evidence artifact path is invalid")
    checksum = artifacts[0].get("checksum")
    if not isinstance(checksum, dict) or checksum.get("value") != _sha256_file(index_path):
        raise ValueError("run evidence artifact digest is invalid")


def _validate_run_score_summary(
    run_payload: Mapping[str, object], attempt: Mapping[str, object]
) -> None:
    """Validate the archival run's primary score summary."""

    summaries = cast(dict[str, dict[str, object]], run_payload["result_summaries"])
    result = summaries.get("cage2-cumulative-blue-reward-result")
    if result is None:
        raise ValueError("run score summary is invalid")
    expected = _validate_score_measure(attempt["score_measure"])
    if float(cast(float, result.get("value"))) != expected:
        raise ValueError("run score summary is invalid")


def _validate_run_evidence_contract(
    bundle: Path,
    run_root: Path,
    attempt: Mapping[str, object],
    task: ExperimentTaskModel,
    known_records: set[str],
    measures: Sequence[ExperimentDerivedMeasureModel],
) -> None:
    """Validate the RAES run and every retained evidence join."""

    run_payload = load_strict_json(run_root / _RUN_FILE)
    run = ExperimentRunModel.model_validate(run_payload)
    validate_experiment_run_against_task(task, run)
    _validate_run_traceability(run_payload, known_records, measures)
    _validate_run_artifact(bundle, run_payload, run_root / _EVIDENCE_INDEX_FILE)
    _validate_run_score_summary(run_payload, attempt)


def _valid_run_evidence(
    bundle: Path,
    run_root: Path,
    attempt: Mapping[str, object],
    task: ExperimentTaskModel,
) -> None:
    """Validate the sealed portable evidence closure for one eligible attempt."""

    index = _validated_evidence_index(run_root)
    records = _validated_evidence_records(run_root, index)
    _, _, measures = _validated_episode_summary(run_root, index)
    known_records = {record.evidence_record_id for record in records}
    if _referenced_record_ids(measures) != known_records:
        raise ValueError("derived-measure evidence closure is invalid")
    _validate_attempt_episode_score(attempt, measures)
    _validate_run_evidence_contract(bundle, run_root, attempt, task, known_records, measures)


def _validated_condition_roots(runs_root: Path, expected: set[str]) -> list[Path]:
    """Return direct condition directories after exact membership validation."""

    entries = list(runs_root.iterdir())
    roots = sorted(path for path in entries if path.is_dir())
    invalid_membership = (
        any(path.is_symlink() or not path.is_dir() for path in entries)
        or {path.name for path in roots} != expected
    )
    if invalid_membership:
        raise ValueError("run condition membership is invalid")
    return roots


def _validate_run_root_membership(run_root: Path) -> None:
    """Reject links and nested directories inside one sealed run."""

    if run_root.is_symlink() or any(path.is_dir() for path in run_root.iterdir()):
        raise ValueError("run artifact membership is invalid")


def _load_condition_attempts(
    bundle: Path,
    condition_root: Path,
    protocol: Mapping[str, object],
    slots: Mapping[str, Mapping[str, object]],
    task: ExperimentTaskModel,
) -> list[dict[str, object]]:
    """Load every sealed attempt under one condition."""

    attempts: list[dict[str, object]] = []
    run_roots = _condition_run_roots(condition_root)
    _verify_condition_inventory(condition_root, run_roots)
    for run_root in run_roots:
        _validate_run_root_membership(run_root)
        _verify_inventory(run_root)
        attempt = _validated_attempt_from_root(run_root, protocol, slots)
        if attempt["disposition"] == "valid":
            _valid_run_evidence(bundle, run_root, attempt, task)
        attempts.append(attempt)
    return attempts


def _load_attempts(root: Path, protocol: Mapping[str, object]) -> list[dict[str, object]]:
    """Load and validate every sealed operational attempt."""

    attempts: list[dict[str, object]] = []
    slots = _slot_index(protocol)
    declaration = cast(dict[str, object], protocol["declaration"])
    contracts = cast(dict[str, object], declaration["published_contracts"])
    task = ExperimentTaskModel.model_validate(contracts["experiment_task"])
    runs_root = root / "runs"
    expected_conditions = {cast(str, slot["condition_id"]) for slot in slots.values()}
    condition_roots = _validated_condition_roots(runs_root, expected_conditions)
    attempts.extend(
        attempt
        for condition_root in condition_roots
        for attempt in _load_condition_attempts(root, condition_root, protocol, slots, task)
    )
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
    protocol = load_strict_json(bundle / _PROTOCOL_FILE)
    validate_protocol(protocol, selection=selection)
    declaration = cast(dict[str, object], protocol["declaration"])
    conditions = {cast(str, slot["condition_id"]) for slot in _slot_index(protocol).values()}
    _verify_inventory(
        bundle,
        expected_members={
            _PROTOCOL_FILE,
            _SOURCE_LEDGER_FILE,
            _REFERENCE_FILE,
            _ENVIRONMENT_FILE,
            _AGGREGATES_FILE,
            _TIERS_FILE,
            _VALIDATION_REPORT_FILE,
            *{
                cast(str, partition["path"])
                for partition in cast(list[dict[str, object]], declaration["schedule_partitions"])
            },
            *{f"runs/{condition}/inventory.json" for condition in conditions},
        },
    )
    ledger = load_strict_json(bundle / _SOURCE_LEDGER_FILE)
    _validate_source_ledger(ledger, protocol)
    _validate_environment(load_strict_json(bundle / _ENVIRONMENT_FILE), protocol)
    _verify_schedule_partitions(bundle, protocol)
    attempts = _load_attempts(bundle, protocol)
    aggregates = compute_aggregates(protocol, attempts)
    if canonical_json_bytes(aggregates) != canonical_json_bytes(
        load_strict_json(bundle / _AGGREGATES_FILE)
    ):
        raise ValueError("aggregate recomputation does not match")
    reference = load_strict_json(bundle / _REFERENCE_FILE)
    _validate_reference(reference)
    tiers = build_tiers(protocol, aggregates, reference)
    if canonical_json_bytes(tiers) != canonical_json_bytes(load_strict_json(bundle / _TIERS_FILE)):
        raise ValueError("tier recomputation does not match")
    try:
        report = (bundle / _VALIDATION_REPORT_FILE).read_text(encoding="utf-8")
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
