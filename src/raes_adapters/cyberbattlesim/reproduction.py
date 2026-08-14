"""Frozen CyberBattleSim source-native/RAES baseline reproduction.

The module is intentionally backend-local.  It owns the issue-30 data gap
(lane, terminal disposition, comparison intervals, and six tier projections)
while validating and embedding the published RAES task, spec, and study
contracts that own experiment meaning.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Never, Protocol, cast

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    ParticipantImplementationProvenanceModel,
)
from raes_contracts.diagnostics import DiagnosticModel  # type: ignore[import-untyped]
from raes_operations.run_artifacts import (  # type: ignore[import-untyped]
    atomic_write_json_artifact,
)

from raes_adapters.cyberbattlesim import load_qualification
from raes_adapters.cyberbattlesim.backend.driver import (
    construct_selected_cyberbattlesim_environment,
    verify_selected_cyberbattlesim_source,
)
from raes_adapters.cyberbattlesim.termination import (
    LOSING_REWARD,
    WINNING_REWARD,
    classify_terminal_cause,
)

_SCHEMA = "cyberbattlesim-baseline-reproduction/v2"
_SOURCE_LEDGER_SCHEMA = "cyberbattlesim-baseline-source-ledger/v1"
_RUN_SCHEMA = "cyberbattlesim-baseline-run/v1"
_AGGREGATE_SCHEMA = "cyberbattlesim-baseline-aggregates/v1"
_BENCH_NOTES_SCHEMA = "cyberbattlesim-baseline-bench-notes/v1"
_INVENTORY_NAME = "inventory.json"
_PROTOCOL_FILE = "protocol.json"
_SOURCE_LEDGER_FILE = "source-ledger.json"
_ENVIRONMENT_FILE = "environment.json"
_COLLECTION_FILE = "collection.json"
_AGGREGATES_FILE = "aggregates.json"
_TIERS_FILE = "tiers.json"
_BENCH_NOTES_FILE = "bench-notes.json"
_EVIDENCE_RECORDS_FILE = "evidence-records.json"
_EPISODE_OUTCOME_FILE = "episode-outcome.json"
_INVALID_JSON = "invalid JSON artifact"
_INVALID_BENCH_TIMESTAMP = "bench note timestamp is invalid"
_INVALID_ARTIFACT_REFS = "artifact references are invalid"
_INVALID_ATTEMPT_SCHEDULE = "attempt schedule is invalid"
_INVALID_ORACLE = "source-native oracle is invalid"
_INVALID_RUN_METRIC = "run metric is invalid"
_INVALID_NATIVE_RESULT = "native evaluator returned an unsupported result"
_INVALID_MEDIATED_EVIDENCE = "mediated evidence is invalid"
_FORBIDDEN_PORTABLE_VALUE = "portable artifact contains a forbidden native value"
_UTC_OFFSET = "+00:00"
_LANES = ("source-native", "raes-mediated")
_DISPOSITIONS = frozenset({"valid", "invalid", "failed", "excluded"})
_METRICS = (
    "steps_to_termination",
    "cumulative_attacker_reward",
    "network_availability",
    "terminal_cause",
)
_TIERS = (
    "authored-source",
    "contract",
    "execution-control",
    "state-observation",
    "outcome-evaluation",
    "disclosure",
)
_ATTEMPTS_PER_LANE = 10
_SEED_LABEL = 20260729
_ATTEMPT_SERIES = "cbs-r3"
_REJECTED_DECLARATION_SHA256 = "825dde3b4cd66f228e0f93157a2add35e3c9a822a7adac1d8ffd322b32116232"
_FAILED_DECLARATION_SHA256 = "f09ec5759021cf1d5de9b260e0299934bf6f6cc4161b822e8f5f0b76bdb96b53"
_FAILED_INVENTORY_SHA256 = "4653bc5afbf501f005f997df782f73f282cccbe28f9cbe176d5a9c3f5970a292"
_BENCH_PHASES = frozenset({"declaration", "native", "mediated", "finalize", "verify"})
_BENCH_SEVERITIES = frozenset({"info", "warning", "error"})
_BENCH_DISPOSITIONS = frozenset({"observed", "passed", "failed", "weakened"})
_BENCH_EVENT_CODES = frozenset(
    {
        "protocol-declared",
        "native-collection-started",
        "native-attempt-terminalized",
        "native-collection-passed",
        "native-collection-failed",
        "mediated-collection-started",
        "mediated-attempt-started",
        "mediated-attempt-terminalized",
        "mediated-collection-completed",
        "bundle-finalization-started",
        "bundle-finalized",
        "offline-verification-started",
        "offline-verification-passed",
        "offline-verification-failed",
    }
)
_PRIVATE_KEY_MARKER = "BEGIN OPENSSH " + "PRIVATE KEY"
_FORBIDDEN_PORTABLE_TOKENS = (
    _PRIVATE_KEY_MARKER,
    "Traceback (most recent call last)",
)
_FORBIDDEN_NATIVE_FIELD_NAMES = frozenset(
    {"action_mask", "credential_cache_matrix", "_explored_network"}
)


class _NativeEvaluatorEnvironment(Protocol):
    """Minimal native evaluator surface used by the isolated worker."""

    identifiers: object

    def close(self) -> None: ...


def canonical_json_bytes(payload: object) -> bytes:
    """Return the byte representation used by every issue-local digest."""

    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_payload(payload: object) -> str:
    """Hash one canonical issue-local JSON payload."""

    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    """Hash one artifact without exposing its content."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_constant(_value: str) -> object:
    """Reject non-finite JSON constants."""

    raise ValueError(_INVALID_JSON)


def _closed_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object while rejecting duplicate keys."""

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_INVALID_JSON)
        result[key] = value
    return result


def _load_strict_value(path: Path) -> object:
    """Load one strict JSON value from disk."""

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_closed_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, ValueError) as error:
        raise ValueError(_INVALID_JSON) from error


def load_strict_json(path: Path) -> dict[str, object]:
    """Load a duplicate-key-free, finite JSON object."""

    value = _load_strict_value(path)
    if not isinstance(value, dict):
        raise ValueError(_INVALID_JSON)
    return value


def _require_keys(value: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    """Require an exact closed set of object keys."""

    if set(value) != expected:
        raise ValueError(f"{label} has unknown or missing fields")


def _safe_relative_path(value: object) -> str:
    """Return a normalized safe relative POSIX path."""

    if not isinstance(value, str):
        raise ValueError("artifact relative path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or path.as_posix() != value:
        raise ValueError("artifact relative path is invalid")
    return value


def _bench_note_policy() -> dict[str, object]:
    """Return the frozen timestamped bench-note publication policy."""

    return {
        "artifact": _BENCH_NOTES_FILE,
        "schema_version": _BENCH_NOTES_SCHEMA,
        "timestamp_profile": "RFC3339 UTC with millisecond precision",
        "required_fields": [
            "note_id",
            "recorded_at",
            "phase",
            "severity",
            "event_code",
            "summary",
            "disposition",
            "evidence_refs",
        ],
        "publication_policy": (
            "Record controlled observations and dispositions as work occurs; exclude raw "
            "native output, exception text, host paths, credentials, and provider identifiers."
        ),
    }


def _utc_timestamp() -> str:
    """Return the current UTC time at the frozen millisecond precision."""

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace(_UTC_OFFSET, "Z")


def _validate_bench_timestamp(value: object) -> str:
    """Validate one canonical RFC3339 UTC bench timestamp."""

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(_INVALID_BENCH_TIMESTAMP)
    try:
        parsed = datetime.fromisoformat(value[:-1] + _UTC_OFFSET)
    except ValueError as error:
        raise ValueError(_INVALID_BENCH_TIMESTAMP) from error
    normalized = parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace(_UTC_OFFSET, "Z")
    if parsed.utcoffset() != UTC.utcoffset(None) or normalized != value:
        raise ValueError(_INVALID_BENCH_TIMESTAMP)
    return value


def _validate_bench_evidence_refs(value: object) -> None:
    """Validate the closed relative-path evidence projection of one note."""

    if not isinstance(value, list):
        raise ValueError("bench note evidence references are invalid")
    for ref in value:
        if not isinstance(ref, dict) or set(ref) != {"path"}:
            raise ValueError("bench note evidence references are invalid")
        _safe_relative_path(ref["path"])


def _validate_bench_note_values(note: Mapping[str, object]) -> None:
    """Validate one note's bounded controlled vocabulary and prose."""

    allowed_values = (
        ("phase", _BENCH_PHASES),
        ("severity", _BENCH_SEVERITIES),
        ("event_code", _BENCH_EVENT_CODES),
        ("disposition", _BENCH_DISPOSITIONS),
    )
    for field, allowed in allowed_values:
        if note[field] not in allowed:
            raise ValueError(f"bench note {field.replace('_', ' ')} is invalid")
    summary = note["summary"]
    if not isinstance(summary, str) or not summary or len(summary) > 240 or "\n" in summary:
        raise ValueError("bench note summary is invalid")
    _validate_bench_evidence_refs(note["evidence_refs"])


def _validate_bench_note(value: object, note_ids: set[str], previous_timestamp: str) -> str:
    """Validate one note and return its ordered canonical timestamp."""

    if not isinstance(value, dict):
        raise ValueError("bench note is invalid")
    note = cast(dict[str, object], value)
    _require_keys(
        note,
        frozenset(cast(list[str], _bench_note_policy()["required_fields"])),
        "bench note",
    )
    note_id = note["note_id"]
    if not isinstance(note_id, str) or note_id in note_ids:
        raise ValueError("bench note identity is invalid")
    note_ids.add(note_id)
    recorded_at = _validate_bench_timestamp(note["recorded_at"])
    if recorded_at < previous_timestamp:
        raise ValueError("bench note timestamps are not ordered")
    _validate_bench_note_values(note)
    return recorded_at


def _validate_bench_notes(payload: Mapping[str, object], protocol: Mapping[str, object]) -> None:
    """Validate one declaration-bound, timestamp-ordered bench-note ledger."""

    _require_keys(
        payload,
        frozenset({"schema_version", "declaration_sha256", "notes"}),
        "bench notes",
    )
    if (
        payload["schema_version"] != _BENCH_NOTES_SCHEMA
        or payload["declaration_sha256"] != protocol["declaration_sha256"]
    ):
        raise ValueError("bench notes binding is invalid")
    notes = payload["notes"]
    if not isinstance(notes, list) or not notes:
        raise ValueError("bench notes are invalid")
    note_ids: set[str] = set()
    previous_timestamp = ""
    for note in notes:
        previous_timestamp = _validate_bench_note(note, note_ids, previous_timestamp)


def _new_bench_notes(
    protocol: Mapping[str, object], notes: Sequence[Mapping[str, object]] = ()
) -> dict[str, object]:
    """Create a declaration-bound bench-note ledger."""

    return {
        "schema_version": _BENCH_NOTES_SCHEMA,
        "declaration_sha256": protocol["declaration_sha256"],
        "notes": [dict(note) for note in notes],
    }


def _append_bench_note(
    payload: dict[str, object],
    *,
    phase: str,
    severity: str,
    event_code: str,
    summary: str,
    disposition: str,
    evidence_paths: Sequence[str],
) -> None:
    """Append and validate one timestamped controlled bench observation."""

    notes = cast(list[dict[str, object]], payload["notes"])
    phase_count = sum(note.get("phase") == phase for note in notes)
    notes.append(
        {
            "note_id": f"{phase}-{phase_count + 1:03d}",
            "recorded_at": _utc_timestamp(),
            "phase": phase,
            "severity": severity,
            "event_code": event_code,
            "summary": summary,
            "disposition": disposition,
            "evidence_refs": [{"path": path} for path in evidence_paths],
        }
    )
    _validate_bench_notes(payload, {"declaration_sha256": payload["declaration_sha256"]})


def _write_bench_notes(root: Path, payload: Mapping[str, object]) -> None:
    """Write the current bench-note ledger atomically."""

    atomic_write_json_artifact(root / _BENCH_NOTES_FILE, dict(payload))


def _load_bench_notes(root: Path, protocol: Mapping[str, object]) -> dict[str, object]:
    """Load and validate a declaration-bound bench-note ledger."""

    payload = load_strict_json(root / _BENCH_NOTES_FILE)
    _validate_bench_notes(payload, protocol)
    return payload


def _artifact(repo_root: Path, artifact_id: str, relative: str) -> dict[str, object]:
    """Describe one exact repository artifact in the declaration."""

    path = repo_root / relative
    return {"artifact_id": artifact_id, "path": relative, "sha256": _sha256_file(path)}


def _behavioral_claim() -> dict[str, object]:
    """Return the finite-case empirical-adequacy claim and its non-claims."""

    return {
        "taxonomy_id": "raes-behavioral-relations",
        "taxonomy_revision": "rev12",
        "relation_id": "empirical-adequacy",
        "subject": "The fixed CyberBattleSim credential-cache baseline selection",
        "left_carrier_ref": "condition:source-native",
        "right_carrier_ref": "condition:raes-mediated",
        "observation_projection_ref": "experiment-study-v1",
        "observation_projection_revision": "rev1",
        "quantifier_scope": "finite-cases",
        "evidence_scope": "finite",
        "assurance_axis": "bounded-test",
        "evidence_boundary": (
            "Exactly ten preallocated terminal attempts per lane under the frozen "
            "issue-30 comparison and missingness rules."
        ),
        "assurance_status": "tested",
        "limitations": ["The lanes have different stochastic bindings and evaluator paths."],
        "explicit_non_claims": [
            "No trace, state, observation, deterministic-replay, or outcome-equivalence "
            "claim is made."
        ],
    }


def _analysis_plan(metrics: list[object]) -> dict[str, object]:
    """Return the frozen descriptive analysis and missingness policy."""

    return {
        "analysis_id": "cyberbattlesim-baseline-comparison-v1",
        "description": "Lane summaries and predeclared bounded differences.",
        "metrics": metrics,
        "primary_metric": "cumulative_attacker_reward",
        "statistical_method": {
            "method": "descriptive lane summaries and difference in means",
            "estimand": "RAES-mediated lane mean minus source-native lane mean",
            "unit_of_analysis": "episode",
            "comparison_family": "four predeclared task metrics",
            "assumptions": [
                "Attempts are the fixed scheduled episodes and are not replaced after failure."
            ],
        },
        "uncertainty_method": {
            "method": "deterministic percentile bootstrap",
            "interval_level": 0.95,
            "procedure": (
                "10,000 counter-addressed SHA-256 resamples bound to the declaration digest."
            ),
        },
        "multiple_comparison_policy": {
            "family": "four descriptive metric comparisons",
            "correction": "none",
            "rationale": "No hypothesis-test or general population claim is made.",
        },
        "missing_data_policy": {
            "missingness_assumption": "Missingness is apparatus- or failure-induced, not random.",
            "handling": (
                "Retain all terminal attempts in denominators; do not impute or silently drop."
            ),
            "sensitivity_analysis": "Unavailable declared metrics weaken the applicable tier.",
        },
    }


def _study(task: ExperimentTaskModel) -> dict[str, object]:
    """Build and validate the published RAES study projection."""

    metrics = list(task.evaluation_protocol.metric_definitions)
    payload = {
        "schema_version": "experiment-study/v1",
        "study_id": "cyberbattlesim-chain-baseline-reproduction",
        "study_version": "1.0.0",
        "study_kind": "study",
        "title": "CyberBattleSim chain source-native and RAES-mediated reproduction",
        "owner": "OpenRAE",
        "description": (
            "Frozen two-lane reproduction of the selected public credential-cache baseline."
        ),
        "purpose": (
            "Retain bounded readiness and reproduction evidence for OpenRAE/research#14 "
            "and OpenRAE/research#20 without asserting deterministic replay or outcome "
            "equivalence."
        ),
        "research_questions": [
            "Which authored, contract, control, observation, outcome, and disclosure facts "
            "survive the selected RAES-mediated execution?"
        ],
        "behavioral_claims": [_behavioral_claim()],
        "membership": {
            "primary-task": {
                "target_ref": {"ref_kind": "task", "ref_id": task.task_id},
                "role": "primary-task",
                "inclusion_rationale": "The qualified public task owns all measured constructs.",
            }
        },
        "inclusion_criteria": [
            "Only preallocated terminal attempts from the exact qualified selection are included."
        ],
        "factors": {
            "execution-lane": {
                "name": "Execution lane",
                "factor_kind": "apparatus",
                "levels": list(_LANES),
            }
        },
        "run_allocation": {
            "allocation_unit": "episode",
            "allocation_method": "preallocated fixed condition matrix",
            "compared_conditions": list(_LANES),
            "condition_assignments": {
                lane: {
                    "condition_id": lane,
                    "factor_levels": {"execution-lane": lane},
                    "required_parameters": [
                        {"name": "execution-lane", "value": lane, "value_kind": "apparatus"}
                    ],
                }
                for lane in _LANES
            },
            "target_runs_per_condition": _ATTEMPTS_PER_LANE,
            "blocking_factors": [],
            "replication_policy": "Ten fixed scheduled episodes per lane; retry budget zero.",
            "stopping_rule": "Terminalize every scheduled attempt; do not replace failures.",
        },
        "analysis_plan": _analysis_plan(metrics),
        "validity_notes": [
            {
                "category": "reproducibility",
                "note": "The source evaluator leaves four random streams unbound.",
                "mitigation": (
                    "Record actual lane-specific binding dispositions and make no replay claim."
                ),
            }
        ],
    }
    return cast(
        dict[str, object],
        ExperimentStudyModel.model_validate(payload).model_dump(mode="json"),
    )


def _schedule(series: str) -> list[dict[str, object]]:
    """Return the frozen two-lane attempt schedule for one identity series."""

    rows: list[dict[str, object]] = []
    for lane in _LANES:
        short = "native" if lane == "source-native" else "mediated"
        for replicate in range(1, _ATTEMPTS_PER_LANE + 1):
            rows.append(
                {
                    "lane": lane,
                    "replicate": replicate,
                    "run_id": f"{series}-{short}-{replicate:02d}",
                    "attempt_id": f"{series}-{short}-{replicate:02d}-attempt-01",
                    "seed_label": _SEED_LABEL,
                }
            )
    return rows


def _prior_attempt_disclosure() -> dict[str, object]:
    """Return the retained disclosure for the rejected first collection."""

    prior_schedule = _schedule("cbs")
    return {
        "declaration_sha256": _REJECTED_DECLARATION_SHA256,
        "publication_disposition": "rejected",
        "reason_code": "withheld-ref-scanner-false-positive",
        "reason": (
            "The byte-oriented leak gate could not distinguish RAES withheld_refs field "
            "names from native values; the bound scanner was not changed in place."
        ),
        "run_ids": [entry["run_id"] for entry in prior_schedule],
        "attempt_ids": [entry["attempt_id"] for entry in prior_schedule],
        "terminalized_counts": {"source-native": 10, "raes-mediated": 10},
        "durable_note": ("https://github.com/OpenRAE/adapters/issues/30#issuecomment-5235719750"),
    }


def _declared_artifacts(
    repo_root: Path, task_path: Path, spec_path: Path
) -> list[dict[str, object]]:
    """Describe every repository artifact bound into a new declaration."""

    relative_artifacts = (
        ("qualification", "src/raes_adapters/cyberbattlesim/qualification.json"),
        ("public-protocol", "src/raes_adapters/cyberbattlesim/public-protocol.md"),
        ("source-ledger", "src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl"),
        ("loss-disclosures", "src/raes_adapters/cyberbattlesim/mapping/loss-disclosures.md"),
        ("reproduction-runner", "src/raes_adapters/cyberbattlesim/reproduction.py"),
        ("mediated-researcher", "src/raes_adapters/cyberbattlesim/researcher.py"),
        ("mediated-driver", "src/raes_adapters/cyberbattlesim/backend/driver.py"),
        ("mediated-evaluator", "src/raes_adapters/cyberbattlesim/backend/evaluator.py"),
        ("terminal-classifier", "src/raes_adapters/cyberbattlesim/termination.py"),
        ("researcher-cli", "src/raes_adapters/cli.py"),
        ("researcher-support", "src/raes_adapters/_researcher_support.py"),
        ("experiment-evidence", "src/raes_adapters/_experiment_evidence.py"),
        ("selected-source-helper", "src/raes_adapters/cyberbattlesim/backend/source.py"),
        ("task", task_path.relative_to(repo_root).as_posix()),
        ("spec", spec_path.relative_to(repo_root).as_posix()),
        ("pack-manifest", "environments/cyberbattlesim-chain/pack.content-manifest.json"),
        (
            "participant-manifest",
            "environments/cyberbattlesim-chain/participant/"
            "cyberbattlesim-red-credential-cache.manifest.json",
        ),
        (
            "participant-selection",
            "environments/cyberbattlesim-chain/participant/"
            "cyberbattlesim-red-credential-cache.selection.json",
        ),
        (
            "participant-configuration",
            "environments/cyberbattlesim-chain/participant/"
            "cyberbattlesim-red-credential-cache.configuration.json",
        ),
    )
    return [_artifact(repo_root, artifact_id, path) for artifact_id, path in relative_artifacts]


def _source_ledger_payload(
    artifacts: Sequence[Mapping[str, object]],
    source: Mapping[str, object],
    runtime_tree: Mapping[str, object],
    benchmark: Mapping[str, object],
) -> dict[str, object]:
    """Build the closed source and loss index joined to a declaration."""

    return {
        "schema_version": _SOURCE_LEDGER_SCHEMA,
        "source": {
            "repository": source["repository"],
            "commit": source["commit"],
            "tree": source["tree"],
            "version": source["version"],
            "runtime_tree_sha256": runtime_tree["sha256"],
            "notebook_path": "notebooks/notebook_withdefender.py",
            "notebook_sha256": benchmark["source_notebook_sha256"],
        },
        "artifact_refs": list(artifacts),
        "adapter": {
            "distribution": "raes-adapters",
            "version": _installed_version("raes-adapters"),
            "runner_artifact_ids": [
                "reproduction-runner",
                "mediated-researcher",
                "mediated-driver",
                "mediated-evaluator",
                "terminal-classifier",
                "researcher-cli",
                "researcher-support",
                "experiment-evidence",
                "selected-source-helper",
            ],
        },
        "loss_refs": [
            "loss-abstracted-topology",
            "loss-benchmark-defects",
            "loss-no-source-artifact",
            "loss-observation-abstraction",
            "loss-unbound-random-streams",
        ],
        "exclusions": [
            "historical benchmark output from a different commit",
            (
                "native observations, action coordinates, credentials, hidden state, "
                "and reward vectors"
            ),
            "provider logs, credentials, environment dumps, and tracebacks",
        ],
        "compatibility_patches": [],
    }


def _declaration_payload(
    task: ExperimentTaskModel,
    artifacts: Sequence[Mapping[str, object]],
    source_selection: Mapping[str, object],
) -> dict[str, object]:
    """Build the complete frozen scientific declaration payload."""

    return {
        "study": _study(task),
        "artifacts": list(artifacts),
        "source_selection": dict(source_selection),
        "condition": {
            "gym_id": "CyberBattleChain-v0",
            "size": 10,
            "attacker": "CredentialCacheExploiter",
            "defender": "ScanAndReimageCompromisedMachines(0.6,2,5)",
            "episode_count_per_lane": _ATTEMPTS_PER_LANE,
            "maximum_steps": 600,
            "epsilon": 0.9,
            "epsilon_exponential_decay": 10000,
            "epsilon_minimum": 0.1,
            "epsilon_schedule_scope": "lane-batch-cumulative",
            "predecessor_failed_bundle": {
                "declaration_sha256": _FAILED_DECLARATION_SHA256,
                "inventory_sha256": _FAILED_INVENTORY_SHA256,
            },
        },
        "attempt_series": _ATTEMPT_SERIES,
        "prior_attempts": _prior_attempt_disclosure(),
        "schedule": _schedule(_ATTEMPT_SERIES),
        "retry_budget": 0,
        "terminal_dispositions": sorted(_DISPOSITIONS),
        "bench_notes": _bench_note_policy(),
        "metrics": list(_METRICS),
        "stochastic_controls": {
            "source-native": {
                "applied": [],
                "unbound": [
                    "gym-environment",
                    "gym-action-space",
                    "python-random",
                    "numpy-global",
                ],
            },
            "raes-mediated": {
                "applied": ["gym-environment", "gym-action-space"],
                "unbound": ["python-random", "numpy-global"],
            },
        },
        "aggregation": {
            "numeric_statistics": [
                "count",
                "mean",
                "median",
                "sample-standard-deviation",
                "minimum",
                "maximum",
            ],
            "uncertainty": "95% deterministic percentile bootstrap interval of the mean",
            "bootstrap_resamples": 10000,
            "missingness": "No imputation; every terminal attempt remains in denominators.",
        },
        "comparison": {
            "exact": "Complete ordered per-run vectors and control dispositions match.",
            "bounded": {
                "steps_to_termination": 60.0,
                "cumulative_attacker_reward": 500.0,
                "network_availability": 0.05,
                "terminal_cause": 0.10,
            },
            "failed": "A complete interval lies outside its bound.",
            "unavailable": (
                "A declared metric is absent from either lane; no tolerance is inferred."
            ),
        },
        "tier_policy": list(_TIERS),
        "explicit_non_claims": [
            "deterministic replay",
            "exact state or observation equivalence",
            "cross-simulator equality",
            "agent ranking",
            "benchmark comparability",
            "outcome equivalence",
            "general scientific reproducibility",
        ],
    }


def build_declaration(repo_root: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Build and validate the frozen declaration and its source index."""

    task_path = repo_root / (
        "environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.task.exp.json"
    )
    spec_path = repo_root / (
        "environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.spec.exp.json"
    )
    task = ExperimentTaskModel.model_validate(load_strict_json(task_path))
    spec = ExperimentSpecModel.model_validate(load_strict_json(spec_path))
    if spec.task_ref.ref_id != task.task_id:
        raise ValueError("published task and spec do not join")
    qualification = cast(dict[str, object], load_qualification())
    source = cast(dict[str, object], qualification["source"])
    runtime_tree = cast(dict[str, object], qualification["runtime_source_tree"])
    benchmark = cast(dict[str, object], qualification["benchmark_snapshot"])
    artifacts = _declared_artifacts(repo_root, task_path, spec_path)
    source_selection = {
        "repository": source["repository"],
        "commit": source["commit"],
        "tree": source["tree"],
        "version": source["version"],
        "runtime_tree_sha256": runtime_tree["sha256"],
        "notebook_path": "notebooks/notebook_withdefender.py",
        "notebook_sha256": benchmark["source_notebook_sha256"],
        "evaluator": qualification["protocol"]["selection"]["evaluator"],  # type: ignore[index]
    }
    declaration = _declaration_payload(task, artifacts, source_selection)
    protocol: dict[str, object] = {
        "schema_version": _SCHEMA,
        "declaration_sha256": sha256_payload(declaration),
        "declaration": declaration,
        "oracle": None,
    }
    source_ledger = _source_ledger_payload(artifacts, source, runtime_tree, benchmark)
    validate_protocol(protocol, require_oracle=False)
    validate_source_ledger(source_ledger, protocol)
    return protocol, source_ledger


def _validate_ledger_source(value: object) -> None:
    """Validate the source identity projection in a source ledger."""

    if not isinstance(value, dict):
        raise ValueError("source ledger source is invalid")
    _require_keys(
        value,
        frozenset(
            {
                "repository",
                "commit",
                "tree",
                "version",
                "runtime_tree_sha256",
                "notebook_path",
                "notebook_sha256",
            }
        ),
        "source ledger source",
    )
    if any(not _is_sha256(value[key]) for key in ("runtime_tree_sha256", "notebook_sha256")):
        raise ValueError("source ledger digest is invalid")
    _safe_relative_path(value["notebook_path"])


def _validate_ledger_adapter(value: object) -> None:
    """Validate the adapter identity projection in a source ledger."""

    if not isinstance(value, dict):
        raise ValueError("source ledger adapter is invalid")
    _require_keys(
        value,
        frozenset({"distribution", "version", "runner_artifact_ids"}),
        "source ledger adapter",
    )
    runner_ids = value["runner_artifact_ids"]
    if not isinstance(runner_ids, list) or len(set(runner_ids)) != len(runner_ids):
        raise ValueError("source ledger adapter is invalid")


def validate_source_ledger(payload: Mapping[str, object], protocol: Mapping[str, object]) -> None:
    """Validate the closed source index and its declaration join."""

    _require_keys(
        payload,
        frozenset(
            {
                "schema_version",
                "source",
                "artifact_refs",
                "adapter",
                "loss_refs",
                "exclusions",
                "compatibility_patches",
            }
        ),
        "source ledger",
    )
    if payload["schema_version"] != _SOURCE_LEDGER_SCHEMA:
        raise ValueError("source ledger schema is invalid")
    _validate_ledger_source(payload["source"])
    declaration = cast(dict[str, object], protocol["declaration"])
    if payload["artifact_refs"] != declaration["artifacts"]:
        raise ValueError("source ledger artifact join is invalid")
    _validate_ledger_adapter(payload["adapter"])
    for field in ("loss_refs", "exclusions", "compatibility_patches"):
        value = payload[field]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("source ledger disclosure is invalid")


def _validate_declaration_fields(declaration: Mapping[str, object]) -> Mapping[str, object]:
    """Validate frozen scalar and contract projections of a declaration."""

    expected_keys = frozenset(
        {
            "study",
            "artifacts",
            "source_selection",
            "condition",
            "attempt_series",
            "prior_attempts",
            "schedule",
            "retry_budget",
            "terminal_dispositions",
            "bench_notes",
            "metrics",
            "stochastic_controls",
            "aggregation",
            "comparison",
            "tier_policy",
            "explicit_non_claims",
        }
    )
    _require_keys(declaration, expected_keys, "protocol declaration")
    ExperimentStudyModel.model_validate(declaration["study"])
    expected_values = (
        ("retry_budget", 0, "retry policy is invalid"),
        ("prior_attempts", _prior_attempt_disclosure(), "prior attempt disclosure is invalid"),
        ("bench_notes", _bench_note_policy(), "bench note policy is invalid"),
        ("metrics", list(_METRICS), "metric declaration is invalid"),
        ("tier_policy", list(_TIERS), "tier policy is invalid"),
    )
    for field, expected, message in expected_values:
        if declaration[field] != expected:
            raise ValueError(message)
    if declaration["attempt_series"] not in {"cbs-r2", "cbs-r3"}:
        raise ValueError("attempt series is invalid")
    if set(cast(list[object], declaration["terminal_dispositions"])) != _DISPOSITIONS:
        raise ValueError("terminal dispositions are invalid")
    return cast(Mapping[str, object], declaration["prior_attempts"])


def _validate_declared_artifacts(value: object) -> None:
    """Validate unique content-addressed declaration artifact references."""

    if not isinstance(value, list) or not value:
        raise ValueError(_INVALID_ARTIFACT_REFS)
    artifact_ids: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(_INVALID_ARTIFACT_REFS)
        _require_keys(item, frozenset({"artifact_id", "path", "sha256"}), "artifact reference")
        artifact_id = item["artifact_id"]
        if not isinstance(artifact_id, str) or artifact_id in artifact_ids:
            raise ValueError(_INVALID_ARTIFACT_REFS)
        artifact_ids.add(artifact_id)
        _safe_relative_path(item["path"])
        if not _is_sha256(item["sha256"]):
            raise ValueError("artifact digest is invalid")


def _validated_schedule_entry(value: object) -> tuple[str, str, str]:
    """Validate one schedule entry and return its lane and identities."""

    if not isinstance(value, dict):
        raise ValueError(_INVALID_ATTEMPT_SCHEDULE)
    _require_keys(
        value,
        frozenset({"lane", "replicate", "run_id", "attempt_id", "seed_label"}),
        "schedule entry",
    )
    lane, run_id, attempt_id = value["lane"], value["run_id"], value["attempt_id"]
    if lane not in _LANES or type(value["replicate"]) is not int:
        raise ValueError(_INVALID_ATTEMPT_SCHEDULE)
    if not isinstance(run_id, str) or not isinstance(attempt_id, str):
        raise ValueError(_INVALID_ATTEMPT_SCHEDULE)
    return cast(str, lane), run_id, attempt_id


def _validate_attempt_schedule(
    value: object,
    prior_attempts: Mapping[str, object],
    attempt_series: str = _ATTEMPT_SERIES,
) -> list[dict[str, object]]:
    """Validate the complete disjoint two-lane schedule."""

    if not isinstance(value, list) or len(value) != 2 * _ATTEMPTS_PER_LANE:
        raise ValueError(_INVALID_ATTEMPT_SCHEDULE)
    schedule = cast(list[dict[str, object]], value)
    run_ids: set[str] = set()
    attempt_ids: set[str] = set()
    counts = dict.fromkeys(_LANES, 0)
    for entry in schedule:
        lane, run_id, attempt_id = _validated_schedule_entry(entry)
        if run_id in run_ids or attempt_id in attempt_ids:
            raise ValueError("attempt identities are not unique")
        run_ids.add(run_id)
        attempt_ids.add(attempt_id)
        counts[lane] += 1
    prior_run_ids = set(cast(list[str], prior_attempts["run_ids"]))
    prior_attempt_ids = set(cast(list[str], prior_attempts["attempt_ids"]))
    if set(counts.values()) != {_ATTEMPTS_PER_LANE}:
        raise ValueError(_INVALID_ATTEMPT_SCHEDULE)
    if run_ids & prior_run_ids or attempt_ids & prior_attempt_ids:
        raise ValueError("attempt identities overlap the rejected series")
    if any(not value.startswith(f"{attempt_series}-") for value in run_ids | attempt_ids):
        raise ValueError("attempt schedule series is invalid")
    return schedule


def _native_schedule_run_ids(schedule: Sequence[Mapping[str, object]]) -> list[object]:
    """Return the source-native run identities in declared order."""

    return [entry["run_id"] for entry in schedule if entry["lane"] == "source-native"]


def _oracle_result_run_ids(results: object) -> list[object]:
    """Validate and return the ordered oracle result identities."""

    if not isinstance(results, list):
        raise ValueError(_INVALID_ORACLE)
    run_ids: list[object] = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError(_INVALID_ORACLE)
        run_ids.append(item.get("run_id"))
    return run_ids


def _validate_oracle(
    oracle: object,
    declaration_sha256: object,
    schedule: Sequence[Mapping[str, object]],
    require_oracle: bool,
) -> None:
    """Validate the optional frozen source-native result projection."""

    if oracle is None:
        if require_oracle:
            raise ValueError("source-native oracle is required")
        return
    if not isinstance(oracle, dict):
        raise ValueError(_INVALID_ORACLE)
    _require_keys(
        oracle,
        frozenset({"lane", "declaration_sha256", "native_result_set_sha256", "ordered_results"}),
        "source-native oracle",
    )
    if oracle["lane"] != "source-native" or oracle["declaration_sha256"] != declaration_sha256:
        raise ValueError(_INVALID_ORACLE)
    if not _is_sha256(oracle["native_result_set_sha256"]):
        raise ValueError(_INVALID_ORACLE)
    native_ids = _native_schedule_run_ids(schedule)
    if _oracle_result_run_ids(oracle["ordered_results"]) != native_ids:
        raise ValueError(_INVALID_ORACLE)


def validate_protocol(payload: Mapping[str, object], *, require_oracle: bool) -> None:
    """Validate the closed issue-local protocol around published contracts."""

    _require_keys(
        payload,
        frozenset({"schema_version", "declaration_sha256", "declaration", "oracle"}),
        "protocol",
    )
    if payload["schema_version"] != _SCHEMA:
        raise ValueError("protocol schema is invalid")
    declaration = payload["declaration"]
    if not isinstance(declaration, dict):
        raise ValueError("protocol declaration is invalid")
    if payload["declaration_sha256"] != sha256_payload(declaration):
        raise ValueError("protocol declaration digest is invalid")
    prior_attempts = _validate_declaration_fields(declaration)
    _validate_declared_artifacts(declaration["artifacts"])
    schedule = _validate_attempt_schedule(
        declaration["schedule"],
        prior_attempts,
        cast(str, declaration["attempt_series"]),
    )
    _validate_oracle(payload["oracle"], payload["declaration_sha256"], schedule, require_oracle)


def _is_sha256(value: object) -> bool:
    """Return whether a value is one lowercase SHA-256 digest."""

    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _reserve_directory(path: Path) -> Path:
    """Atomically reserve one private output directory."""

    resolved = path.resolve()
    os.mkdir(resolved, 0o700)
    return resolved


def _require_regular_tree(root: Path) -> None:
    """Reject symlinks and non-regular members before reading archival data."""

    if root.is_symlink() or not root.is_dir():
        raise ValueError("artifact tree must contain regular non-symlink members")
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("artifact tree must contain regular non-symlink members")


def _media_type(path: Path) -> str:
    """Return the closed media type used by artifact inventories."""

    return "application/json" if path.suffix == ".json" else "text/markdown"


def _seal_inventory(root: Path) -> dict[str, object]:
    """Write the content-addressed inventory for one immutable stage."""

    _require_regular_tree(root)
    artifacts = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == _INVENTORY_NAME:
            continue
        content = path.read_bytes()
        artifacts.append(
            {
                "path": path.relative_to(root).as_posix(),
                "media_type": _media_type(path),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    inventory: dict[str, object] = {"artifacts": artifacts}
    atomic_write_json_artifact(root / _INVENTORY_NAME, inventory)
    return inventory


def write_declaration(repo_root: Path, output: Path) -> Path:
    """Reserve and write one immutable declaration collection."""

    root = _reserve_directory(output)
    protocol, source_ledger = build_declaration(repo_root.resolve())
    atomic_write_json_artifact(root / _PROTOCOL_FILE, protocol)
    atomic_write_json_artifact(root / _SOURCE_LEDGER_FILE, source_ledger)
    bench_notes = _new_bench_notes(protocol)
    _append_bench_note(
        bench_notes,
        phase="declaration",
        severity="info",
        event_code="protocol-declared",
        summary=(
            "The declaration and 20 never-reused attempt identities were written before "
            "experiment effects."
        ),
        disposition="passed",
        evidence_paths=(_PROTOCOL_FILE, _SOURCE_LEDGER_FILE),
    )
    _write_bench_notes(root, bench_notes)
    _seal_inventory(root)
    return root


def _control_disposition(protocol: Mapping[str, object], lane: str) -> dict[str, object]:
    """Project the predeclared stochastic-control disposition for one lane."""

    declaration = cast(dict[str, object], protocol["declaration"])
    controls = cast(dict[str, object], declaration["stochastic_controls"])
    return cast(dict[str, object], controls[lane])


def _terminal_row(
    protocol: Mapping[str, object],
    scheduled: Mapping[str, object],
    *,
    result: Mapping[str, object] | None,
    disposition: str,
    protocol_sha256: str | None,
    diagnostic_code: str | None = None,
) -> dict[str, object]:
    """Build one closed terminal row from a scheduled attempt."""

    if disposition not in _DISPOSITIONS:
        raise ValueError("run disposition is invalid")
    metrics: dict[str, object] = dict.fromkeys(_METRICS)
    evidence_refs: list[dict[str, object]] = []
    cleanup_verified = False
    if result is not None:
        for metric in _METRICS:
            metrics[metric] = result.get(metric)
        raw_refs = result.get("evidence_refs", [])
        if isinstance(raw_refs, list):
            evidence_refs = [
                cast(dict[str, object], item) for item in raw_refs if isinstance(item, dict)
            ]
        cleanup_verified = bool(result.get("cleanup_verified", disposition == "valid"))
    if disposition == "valid" and not cleanup_verified:
        raise ValueError("valid run has no verified cleanup")
    metric_status = {
        metric: "available" if value is not None else "unavailable"
        for metric, value in metrics.items()
    }
    diagnostics = (
        []
        if diagnostic_code is None
        else [
            {
                "schema_version": "diagnostic/v1",
                "code": diagnostic_code,
                "domain": "orchestration",
                "address": "/reproduction/attempt",
                "message": "The scheduled reproduction attempt did not produce valid evidence.",
                "severity": "error",
            }
        ]
    )
    return {
        "schema_version": _RUN_SCHEMA,
        "run_id": scheduled["run_id"],
        "attempt_id": scheduled["attempt_id"],
        "lane": scheduled["lane"],
        "replicate": scheduled["replicate"],
        "seed_label": scheduled["seed_label"],
        "disposition": disposition,
        "declaration_sha256": protocol["declaration_sha256"],
        "protocol_sha256": protocol_sha256,
        "stochastic_controls": _control_disposition(protocol, cast(str, scheduled["lane"])),
        "metrics": metrics,
        "metric_status": metric_status,
        "cleanup": {
            "attempted": True,
            "verified": cleanup_verified,
            "receipt_ref": f"cleanup.{scheduled['attempt_id']}",
        },
        "evidence_refs": evidence_refs,
        "diagnostics": diagnostics,
    }


def terminal_rows_from_results(
    protocol: Mapping[str, object],
    *,
    native_results: Sequence[Mapping[str, object]],
    mediated_results: Sequence[Mapping[str, object]],
    protocol_sha256: str,
) -> list[dict[str, object]]:
    """Project two complete result vectors onto the preallocated schedule."""

    declaration = cast(dict[str, object], protocol["declaration"])
    schedule = cast(list[dict[str, object]], declaration["schedule"])
    by_lane = {
        "source-native": native_results,
        "raes-mediated": mediated_results,
    }
    rows: list[dict[str, object]] = []
    positions = dict.fromkeys(_LANES, 0)
    for scheduled in schedule:
        lane = cast(str, scheduled["lane"])
        index = positions[lane]
        values = by_lane[lane]
        if index >= len(values):
            raise ValueError("result vector does not match the frozen schedule")
        rows.append(
            _terminal_row(
                protocol,
                scheduled,
                result=values[index],
                disposition="valid",
                protocol_sha256=protocol_sha256,
            )
        )
        positions[lane] += 1
    if any(positions[lane] != len(by_lane[lane]) for lane in _LANES):
        raise ValueError("result vector does not match the frozen schedule")
    return rows


def _write_rows(root: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write terminal rows into stable per-run directories."""

    runs_root = root / "runs"
    os.mkdir(runs_root, 0o700)
    for row in rows:
        run_root = runs_root / cast(str, row["run_id"])
        os.mkdir(run_root, 0o700)
        atomic_write_json_artifact(run_root / "record.json", dict(row))


def load_terminal_rows(root: Path) -> list[dict[str, object]]:
    """Load terminal rows in stable run-id order."""

    rows = [load_strict_json(path) for path in sorted((root / "runs").glob("*/record.json"))]
    for row in rows:
        _validate_terminal_row(row)
    return rows


def _is_finite_number(value: object) -> bool:
    """Return whether a value is a non-boolean finite number."""

    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_availability_series(value: object) -> None:
    """Validate one non-empty bounded network-availability series."""

    if not isinstance(value, list) or not value:
        raise ValueError(_INVALID_RUN_METRIC)
    if any(not _is_finite_number(item) or not 0.0 <= cast(float, item) <= 1.0 for item in value):
        raise ValueError(_INVALID_RUN_METRIC)


def _validate_metric_value(metric: str, value: object) -> None:
    """Validate one available or unavailable declared run metric."""

    if value is None:
        return
    if metric == "steps_to_termination":
        if type(value) is not int or not 0 <= value <= 600:
            raise ValueError(_INVALID_RUN_METRIC)
    elif metric == "cumulative_attacker_reward":
        if not _is_finite_number(value):
            raise ValueError(_INVALID_RUN_METRIC)
    elif metric == "network_availability":
        _validate_availability_series(value)
    elif metric == "terminal_cause" and value not in {
        "attacker-ownership",
        "defender-sla",
        "defender-eviction",
        "evaluator-cutoff",
    }:
        raise ValueError(_INVALID_RUN_METRIC)


def _validate_terminal_row(row: Mapping[str, object]) -> None:
    """Validate one closed terminal run projection."""

    expected = frozenset(
        {
            "schema_version",
            "run_id",
            "attempt_id",
            "lane",
            "replicate",
            "seed_label",
            "disposition",
            "declaration_sha256",
            "protocol_sha256",
            "stochastic_controls",
            "metrics",
            "metric_status",
            "cleanup",
            "evidence_refs",
            "diagnostics",
        }
    )
    _require_keys(row, expected, "terminal run")
    if row["schema_version"] != _RUN_SCHEMA or row["disposition"] not in _DISPOSITIONS:
        raise ValueError("terminal run is invalid")
    metrics = row["metrics"]
    statuses = row["metric_status"]
    if not isinstance(metrics, dict) or set(metrics) != set(_METRICS):
        raise ValueError("terminal run metrics are invalid")
    if not isinstance(statuses, dict) or set(statuses) != set(_METRICS):
        raise ValueError("terminal run metrics are invalid")
    for metric, value in metrics.items():
        _validate_metric_value(metric, value)
        expected_status = "available" if value is not None else "unavailable"
        if statuses[metric] != expected_status:
            raise ValueError("terminal run metric status is invalid")


def _failed_rows(protocol: Mapping[str, object], lane: str, code: str) -> list[dict[str, object]]:
    """Terminalize every scheduled row in one lane as failed."""

    schedule = cast(dict[str, object], protocol["declaration"])["schedule"]
    return [
        _terminal_row(
            protocol,
            entry,
            result=None,
            disposition="failed",
            protocol_sha256=None,
            diagnostic_code=code,
        )
        for entry in cast(list[dict[str, object]], schedule)
        if entry["lane"] == lane
    ]


def _valid_native_rows(
    protocol: Mapping[str, object], results: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    """Join a complete native result vector to its frozen schedule."""

    if len(results) != _ATTEMPTS_PER_LANE:
        raise ValueError("native evaluator returned the wrong episode count")
    schedule = cast(
        list[dict[str, object]], cast(dict[str, object], protocol["declaration"])["schedule"]
    )
    native_schedule = [entry for entry in schedule if entry["lane"] == "source-native"]
    rows = [
        _terminal_row(
            protocol,
            scheduled,
            result=result,
            disposition="valid",
            protocol_sha256=None,
        )
        for scheduled, result in zip(native_schedule, results, strict=True)
    ]
    for row in rows:
        _validate_terminal_row(row)
    return rows


def _record_native_failure(
    protocol: Mapping[str, object],
    root: Path,
    bench_notes: dict[str, object],
) -> Never:
    """Seal all native attempts as failed and raise a bounded error."""

    rows = _failed_rows(protocol, "source-native", "reproduction.native.execution-failed")
    _write_rows(root, rows)
    atomic_write_json_artifact(root / _PROTOCOL_FILE, dict(protocol))
    atomic_write_json_artifact(
        root / _COLLECTION_FILE,
        {"lane": "source-native", "terminal_count": len(rows), "valid_count": 0},
    )
    for row in rows:
        run_id = cast(str, row["run_id"])
        _append_bench_note(
            bench_notes,
            phase="native",
            severity="error",
            event_code="native-attempt-terminalized",
            summary=f"Scheduled source-native attempt {run_id} was terminalized as failed.",
            disposition="failed",
            evidence_paths=(f"runs/{run_id}/record.json",),
        )
    _append_bench_note(
        bench_notes,
        phase="native",
        severity="error",
        event_code="native-collection-failed",
        summary=(
            "The source-native batch failed; all ten scheduled attempts remain retained as failed."
        ),
        disposition="failed",
        evidence_paths=(_PROTOCOL_FILE,),
    )
    _write_bench_notes(root, bench_notes)
    _seal_inventory(root)
    raise RuntimeError("native collection failed") from None


def _complete_native_collection(
    protocol: Mapping[str, object],
    root: Path,
    rows: Sequence[Mapping[str, object]],
    bench_notes: dict[str, object],
) -> None:
    """Bind a valid native vector into the oracle and seal its stage."""

    ordered = [
        {"run_id": row["run_id"], "metrics": row["metrics"]}
        for row in sorted(rows, key=lambda item: cast(int, item["replicate"]))
    ]
    result_set_sha256 = sha256_payload(ordered)
    completed = cast(dict[str, object], json.loads(json.dumps(protocol)))
    completed["oracle"] = {
        "lane": "source-native",
        "declaration_sha256": protocol["declaration_sha256"],
        "native_result_set_sha256": result_set_sha256,
        "ordered_results": ordered,
    }
    validate_protocol(completed, require_oracle=True)
    _write_rows(root, rows)
    atomic_write_json_artifact(root / _PROTOCOL_FILE, completed)
    atomic_write_json_artifact(
        root / _COLLECTION_FILE,
        {
            "lane": "source-native",
            "terminal_count": len(rows),
            "valid_count": len(rows),
            "native_result_set_sha256": result_set_sha256,
        },
    )
    for row in rows:
        run_id = cast(str, row["run_id"])
        _append_bench_note(
            bench_notes,
            phase="native",
            severity="info",
            event_code="native-attempt-terminalized",
            summary=f"Scheduled source-native attempt {run_id} was terminalized as valid.",
            disposition="passed",
            evidence_paths=(f"runs/{run_id}/record.json",),
        )
    _append_bench_note(
        bench_notes,
        phase="native",
        severity="info",
        event_code="native-collection-passed",
        summary="The exact upstream evaluator returned all ten scheduled terminal results.",
        disposition="passed",
        evidence_paths=(_PROTOCOL_FILE,),
    )
    _write_bench_notes(root, bench_notes)
    _seal_inventory(root)


def collect_native(
    declaration_root: Path,
    output: Path,
    *,
    executor: Callable[[], list[dict[str, object]]] | None = None,
) -> Path:
    """Collect the one exact upstream ten-episode batch and freeze its oracle."""

    protocol = load_strict_json(declaration_root / _PROTOCOL_FILE)
    validate_protocol(protocol, require_oracle=False)
    _verify_inventory(declaration_root)
    root = _reserve_directory(output)
    source_ledger = load_strict_json(declaration_root / _SOURCE_LEDGER_FILE)
    validate_source_ledger(source_ledger, protocol)
    atomic_write_json_artifact(root / _SOURCE_LEDGER_FILE, source_ledger)
    atomic_write_json_artifact(root / _ENVIRONMENT_FILE, _environment_payload("source-native"))
    bench_notes = _load_bench_notes(declaration_root, protocol)
    _append_bench_note(
        bench_notes,
        phase="native",
        severity="info",
        event_code="native-collection-started",
        summary="The exact admitted upstream ten-episode evaluator batch was started.",
        disposition="observed",
        evidence_paths=(_PROTOCOL_FILE, _SOURCE_LEDGER_FILE, _ENVIRONMENT_FILE),
    )
    _write_bench_notes(root, bench_notes)
    execute = executor if executor is not None else _execute_native_batch
    try:
        rows = _valid_native_rows(protocol, execute())
    except Exception:
        _record_native_failure(protocol, root, bench_notes)
    _complete_native_collection(protocol, root, rows, bench_notes)
    return root


def _mediated_schedule(protocol: Mapping[str, object]) -> list[dict[str, object]]:
    """Return the mediated slice of the frozen schedule."""

    declaration = cast(dict[str, object], protocol["declaration"])
    schedule = cast(list[dict[str, object]], declaration["schedule"])
    return [entry for entry in schedule if entry["lane"] == "raes-mediated"]


def _execute_mediated_row(
    protocol: Mapping[str, object],
    scheduled: Mapping[str, object],
    pack_root: Path,
    run_root: Path,
    protocol_digest: str,
    epsilon_step_offset: int,
    execute: Callable[[dict[str, object], Path], dict[str, object]],
) -> dict[str, object]:
    """Execute and terminalize one mediated schedule row."""

    try:
        result = execute(
            {
                **scheduled,
                "pack_root": pack_root.as_posix(),
                "epsilon_step_offset": epsilon_step_offset,
            },
            run_root,
        )
        row = _terminal_row(
            protocol,
            scheduled,
            result=result,
            disposition="valid",
            protocol_sha256=protocol_digest,
        )
        _validate_terminal_row(row)
        return row
    except Exception:
        return _terminal_row(
            protocol,
            scheduled,
            result=None,
            disposition="failed",
            protocol_sha256=protocol_digest,
            diagnostic_code="reproduction.mediated.execution-failed",
        )


def _record_mediated_row(
    bench_notes: dict[str, object], run_root: Path, row: Mapping[str, object]
) -> None:
    """Persist one mediated terminal row and its timestamped disposition."""

    run_id = cast(str, row["run_id"])
    atomic_write_json_artifact(run_root / "record.json", dict(row))
    valid = row["disposition"] == "valid"
    _append_bench_note(
        bench_notes,
        phase="mediated",
        severity="info" if valid else "error",
        event_code="mediated-attempt-terminalized",
        summary=(
            f"Scheduled RAES-mediated attempt {run_id} was terminalized as {row['disposition']}."
        ),
        disposition="passed" if valid else "failed",
        evidence_paths=(f"runs/{run_id}/record.json",),
    )


def collect_mediated(
    oracle_root: Path,
    pack_root: Path,
    output: Path,
    *,
    runner: Callable[[dict[str, object], Path], dict[str, object]] | None = None,
) -> Path:
    """Collect ten ordered RAES-mediated attempts without silent drops."""

    protocol_path = oracle_root / _PROTOCOL_FILE
    protocol = load_strict_json(protocol_path)
    validate_protocol(protocol, require_oracle=True)
    _verify_inventory(oracle_root)
    protocol_digest = _sha256_file(protocol_path)
    root = _reserve_directory(output)
    atomic_write_json_artifact(root / _PROTOCOL_FILE, protocol)
    atomic_write_json_artifact(root / _ENVIRONMENT_FILE, _environment_payload("raes-mediated"))
    bench_notes = _new_bench_notes(protocol)
    _append_bench_note(
        bench_notes,
        phase="mediated",
        severity="info",
        event_code="mediated-collection-started",
        summary="The ten preallocated RAES-mediated attempts were started with zero retries.",
        disposition="observed",
        evidence_paths=(_PROTOCOL_FILE, _ENVIRONMENT_FILE),
    )
    _write_bench_notes(root, bench_notes)
    runs_root = root / "runs"
    os.mkdir(runs_root, 0o700)
    execute = runner if runner is not None else _execute_mediated_attempt
    schedule = _mediated_schedule(protocol)
    rows: list[dict[str, object]] = []
    epsilon_step_offset = 0
    for scheduled in schedule:
        run_id = cast(str, scheduled["run_id"])
        run_root = runs_root / cast(str, scheduled["run_id"])
        os.mkdir(run_root, 0o700)
        _append_bench_note(
            bench_notes,
            phase="mediated",
            severity="info",
            event_code="mediated-attempt-started",
            summary=f"Scheduled RAES-mediated attempt {run_id} was started.",
            disposition="observed",
            evidence_paths=(_PROTOCOL_FILE,),
        )
        _write_bench_notes(root, bench_notes)
        row = _execute_mediated_row(
            protocol,
            scheduled,
            pack_root,
            run_root,
            protocol_digest,
            epsilon_step_offset,
            execute,
        )
        _record_mediated_row(bench_notes, run_root, row)
        rows.append(row)
        if row["disposition"] == "valid":
            metrics = cast(dict[str, object], row["metrics"])
            completed_steps = metrics["steps_to_termination"]
            if type(completed_steps) is not int:
                raise RuntimeError("mediated epsilon schedule is incomplete")
            epsilon_step_offset += completed_steps
        _write_bench_notes(root, bench_notes)
    atomic_write_json_artifact(
        root / _COLLECTION_FILE,
        {
            "lane": "raes-mediated",
            "terminal_count": len(rows),
            "valid_count": sum(row["disposition"] == "valid" for row in rows),
            "protocol_sha256": protocol_digest,
        },
    )
    valid_count = sum(row["disposition"] == "valid" for row in rows)
    _append_bench_note(
        bench_notes,
        phase="mediated",
        severity="info" if valid_count == len(rows) else "warning",
        event_code="mediated-collection-completed",
        summary=(
            f"The RAES-mediated lane terminalized all ten attempts; {valid_count} were valid "
            f"and {len(rows) - valid_count} failed."
        ),
        disposition="passed" if valid_count == len(rows) else "weakened",
        evidence_paths=tuple(f"runs/{row['run_id']}/record.json" for row in rows),
    )
    _write_bench_notes(root, bench_notes)
    _seal_inventory(root)
    return root


def _numeric_value(row: Mapping[str, object], metric: str) -> float | None:
    """Project one validated numeric metric from a terminal row."""

    metrics = cast(dict[str, object], row["metrics"])
    value = metrics[metric]
    if value is None:
        return None
    if metric == "network_availability":
        return statistics.fmean(cast(list[float], value))
    return float(cast(int | float, value))


def _percentile(values: Sequence[float], probability: float) -> float:
    """Compute one linearly interpolated percentile."""

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _draw_index(
    declaration_sha256: str, metric: str, lane: str, sample: int, position: int, count: int
) -> int:
    """Derive one deterministic counter-addressed bootstrap index."""

    address = f"{declaration_sha256}:{metric}:{lane}:{sample}:{position}".encode()
    return int.from_bytes(hashlib.sha256(address).digest()[:8], "big") % count


def _bootstrap_means(
    values: Sequence[float], declaration_sha256: str, metric: str, lane: str, count: int
) -> list[float]:
    """Return deterministic bootstrap means for one lane and metric."""

    return [
        statistics.fmean(
            values[_draw_index(declaration_sha256, metric, lane, sample, position, len(values))]
            for position in range(len(values))
        )
        for sample in range(count)
    ]


def _numeric_summary(
    values: Sequence[float], declaration_sha256: str, metric: str, lane: str, resamples: int
) -> dict[str, object]:
    """Summarize one complete numeric lane projection."""

    bootstraps = _bootstrap_means(values, declaration_sha256, metric, lane, resamples)
    return {
        "available_count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "sample_standard_deviation": statistics.stdev(values) if len(values) > 1 else 0.0,
        "minimum": min(values),
        "maximum": max(values),
        "mean_interval_95": {
            "lower": _percentile(bootstraps, 0.025),
            "upper": _percentile(bootstraps, 0.975),
        },
    }


def _lane_aggregate(
    lane: str,
    ordered_rows: Sequence[Mapping[str, object]],
    declaration_digest: str,
    resamples: int,
    numeric_metrics: Sequence[str],
) -> tuple[dict[str, object], dict[str, list[float]], list[str]]:
    """Aggregate dispositions and declared metrics for one lane."""

    selected = [row for row in ordered_rows if row["lane"] == lane]
    disposition_counts = {
        disposition: sum(row["disposition"] == disposition for row in selected)
        for disposition in sorted(_DISPOSITIONS)
    }
    numeric_values: dict[str, list[float]] = {}
    metric_payloads: dict[str, object] = {}
    for metric in numeric_metrics:
        values = [
            value
            for row in selected
            if row["disposition"] == "valid" and (value := _numeric_value(row, metric)) is not None
        ]
        numeric_values[metric] = values
        if values:
            summary = _numeric_summary(values, declaration_digest, metric, lane, resamples)
        else:
            summary = {"available_count": 0}
        summary["missing_count"] = len(selected) - len(values)
        metric_payloads[metric] = summary
    causes = [
        cast(str, cast(dict[str, object], row["metrics"])["terminal_cause"])
        for row in selected
        if row["disposition"] == "valid"
        and cast(dict[str, object], row["metrics"])["terminal_cause"] is not None
    ]
    categories = sorted(set(causes))
    metric_payloads["terminal_cause"] = {
        "available_count": len(causes),
        "missing_count": len(selected) - len(causes),
        "proportions": {category: causes.count(category) / len(causes) for category in categories},
    }
    payload = {
        "scheduled_count": len(selected),
        "dispositions": disposition_counts,
        "metrics": metric_payloads,
    }
    return payload, numeric_values, causes


def _comparison_result(*, exact: bool, bounded: bool) -> str:
    """Choose one ordered comparison disposition without nested conditionals."""

    if exact:
        return "exact"
    if bounded:
        return "bounded"
    return "outside-tolerance"


def _numeric_comparison(
    metric: str,
    native: Sequence[float],
    mediated: Sequence[float],
    declaration_digest: str,
    resamples: int,
    tolerance_value: object,
) -> dict[str, object]:
    """Compare one complete numeric lane pair under its frozen tolerance."""

    if len(native) != _ATTEMPTS_PER_LANE or len(mediated) != _ATTEMPTS_PER_LANE:
        return {"result": "unavailable", "mean_difference": None, "interval_95": None}
    if not isinstance(tolerance_value, (int, float)) or isinstance(tolerance_value, bool):
        raise ValueError("comparison tolerance is invalid")
    native_boot = _bootstrap_means(native, declaration_digest, metric, "source-native", resamples)
    mediated_boot = _bootstrap_means(
        mediated, declaration_digest, metric, "raes-mediated", resamples
    )
    differences = [right - left for left, right in zip(native_boot, mediated_boot, strict=True)]
    interval = {
        "lower": _percentile(differences, 0.025),
        "upper": _percentile(differences, 0.975),
    }
    tolerance = float(tolerance_value)
    return {
        "result": _comparison_result(
            exact=native == mediated,
            bounded=interval["lower"] >= -tolerance and interval["upper"] <= tolerance,
        ),
        "mean_difference": statistics.fmean(mediated) - statistics.fmean(native),
        "interval_95": interval,
        "tolerance": tolerance,
    }


def _terminal_cause_comparison(
    native: Sequence[str], mediated: Sequence[str], tolerance_value: object
) -> dict[str, object]:
    """Compare categorical terminal-cause proportions."""

    if len(native) != _ATTEMPTS_PER_LANE or len(mediated) != _ATTEMPTS_PER_LANE:
        return {"result": "unavailable", "proportion_differences": None}
    if not isinstance(tolerance_value, (int, float)) or isinstance(tolerance_value, bool):
        raise ValueError("comparison tolerance is invalid")
    categories = sorted(set(native) | set(mediated))
    differences = {
        category: mediated.count(category) / len(mediated) - native.count(category) / len(native)
        for category in categories
    }
    tolerance = float(tolerance_value)
    return {
        "result": _comparison_result(
            exact=native == mediated,
            bounded=all(abs(value) <= tolerance for value in differences.values()),
        ),
        "proportion_differences": differences,
        "tolerance": tolerance,
    }


def compute_aggregates(
    protocol: Mapping[str, object], rows: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """Purely recompute all aggregate and comparison projections."""

    validate_protocol(protocol, require_oracle=False)
    ordered_rows = sorted(
        rows, key=lambda item: (cast(str, item["lane"]), cast(int, item["replicate"]))
    )
    for row in ordered_rows:
        _validate_terminal_row(row)
    declaration = cast(dict[str, object], protocol["declaration"])
    resamples = cast(dict[str, object], declaration["aggregation"])["bootstrap_resamples"]
    if type(resamples) is not int or resamples < 1:
        raise ValueError("bootstrap declaration is invalid")
    declaration_digest = cast(str, protocol["declaration_sha256"])
    numeric_metrics = _METRICS[:-1]
    lanes: dict[str, object] = {}
    lane_values: dict[str, dict[str, list[float]]] = {}
    terminal_values: dict[str, list[str]] = {}
    for lane in _LANES:
        lanes[lane], lane_values[lane], terminal_values[lane] = _lane_aggregate(
            lane, ordered_rows, declaration_digest, resamples, numeric_metrics
        )
    tolerances = cast(
        dict[str, object], cast(dict[str, object], declaration["comparison"])["bounded"]
    )
    comparisons: dict[str, object] = {}
    for metric in numeric_metrics:
        comparisons[metric] = _numeric_comparison(
            metric,
            lane_values["source-native"][metric],
            lane_values["raes-mediated"][metric],
            declaration_digest,
            resamples,
            tolerances[metric],
        )
    comparisons["terminal_cause"] = _terminal_cause_comparison(
        terminal_values["source-native"],
        terminal_values["raes-mediated"],
        tolerances["terminal_cause"],
    )
    return {
        "schema_version": _AGGREGATE_SCHEMA,
        "declaration_sha256": declaration_digest,
        "scheduled_count": len(ordered_rows),
        "lanes": lanes,
        "comparisons": comparisons,
        "bootstrap": {
            "resamples": resamples,
            "method": "counter-addressed-sha256-percentile",
            "interval_level": 0.95,
        },
    }


def _installed_version(name: str) -> str:
    """Return an installed distribution version or a stable absence marker."""

    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _installed_source_artifact_sha256() -> str:
    """Return only the installed wheel digest, never its local URL."""

    result = "unavailable"
    try:
        distribution = importlib.metadata.distribution("cyberbattlesim")
        direct_text = distribution.read_text("direct_url.json")
        direct = json.loads(direct_text) if direct_text is not None else None
        archive = direct.get("archive_info") if isinstance(direct, dict) else None
        if isinstance(archive, dict):
            digest = archive.get("hash")
            hashes = archive.get("hashes")
            if isinstance(digest, str) and digest.startswith("sha256=") and _is_sha256(digest[7:]):
                result = digest[7:]
            elif isinstance(hashes, dict) and _is_sha256(hashes.get("sha256")):
                result = cast(str, hashes["sha256"])
    except (
        importlib.metadata.PackageNotFoundError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        pass
    return result


def _physical_memory_bytes() -> int | None:
    """Return installed physical memory without exposing host identity."""

    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (OSError, ValueError):
        return None


def _environment_payload(lane: str) -> dict[str, object]:
    """Describe one privacy-bounded lane execution environment."""

    qualification = cast(dict[str, object], load_qualification())
    source = cast(dict[str, object], qualification["source"])
    return {
        "schema_version": "cyberbattlesim-baseline-environment/v1",
        "lane": lane,
        "machine": {
            "architecture": platform.machine(),
            "operating_system": platform.system(),
            "operating_system_release": platform.release(),
            "logical_cpu_count": os.cpu_count(),
            "physical_memory_bytes": _physical_memory_bytes(),
        },
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "software": {
            name: _installed_version(name)
            for name in (
                "cyberbattlesim",
                "gymnasium",
                "numpy",
                "raes",
                "raes-adapters",
                "raes-env-packs",
            )
        },
        "source": {
            "commit": source["commit"],
            "tree": source["tree"],
            "version": source["version"],
            "installed_artifact_sha256": _installed_source_artifact_sha256(),
        },
        "pack": {
            "identity": "cyberbattlesim-chain",
            "version": "1.0.0",
            "content_digest": (
                "sha256:66493882579d5cba87248c5722782ff5ded5f0d7423f4e559f15bfb61712a905"
            ),
        },
        "limitations": [
            (
                "A prior 20-attempt series was terminalized but rejected from final "
                "publication after its byte-oriented leak gate produced a false positive; "
                "the fresh series uses disjoint identities and unchanged scientific conditions."
            ),
            "The upstream source has no selected public index or release artifact.",
            "Python-global and NumPy-global random streams are unbound in the mediated lane.",
            "All four observed random streams are unbound in the source-native lane.",
            "The authored RAES topology is representative rather than state-identical.",
            (
                "The mediated evaluator retains only per-step network availability and a "
                "source-backed reconstructed terminal cause from source info."
            ),
        ],
    }


def _validate_lane_environment(payload: Mapping[str, object], lane: str) -> None:
    """Validate one lane's privacy-bounded environment record."""

    _require_keys(
        payload,
        frozenset(
            {
                "schema_version",
                "lane",
                "machine",
                "python",
                "software",
                "source",
                "pack",
                "limitations",
            }
        ),
        "lane environment",
    )
    if payload["schema_version"] != "cyberbattlesim-baseline-environment/v1":
        raise ValueError("lane environment schema is invalid")
    if payload["lane"] != lane:
        raise ValueError("lane environment identity is invalid")
    closed = {
        "machine": frozenset(
            {
                "architecture",
                "operating_system",
                "operating_system_release",
                "logical_cpu_count",
                "physical_memory_bytes",
            }
        ),
        "python": frozenset({"implementation", "version"}),
        "software": frozenset(
            {
                "cyberbattlesim",
                "gymnasium",
                "numpy",
                "raes",
                "raes-adapters",
                "raes-env-packs",
            }
        ),
        "source": frozenset({"commit", "tree", "version", "installed_artifact_sha256"}),
        "pack": frozenset({"identity", "version", "content_digest"}),
    }
    for field, keys in closed.items():
        value = payload[field]
        if not isinstance(value, dict):
            raise ValueError("lane environment is invalid")
        _require_keys(value, keys, f"lane environment {field}")
    limitations = payload["limitations"]
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(item, str) for item in limitations)
    ):
        raise ValueError("lane environment limitations are invalid")


def _validate_combined_environment(payload: Mapping[str, object]) -> None:
    """Validate the joined native and mediated environment record."""

    _require_keys(
        payload,
        frozenset(
            {
                "schema_version",
                "source_native",
                "raes_mediated",
                "research_consumers",
                "publication_scope",
                "limitations",
            }
        ),
        "combined environment",
    )
    if payload["schema_version"] != "cyberbattlesim-baseline-environment-pair/v1":
        raise ValueError("combined environment schema is invalid")
    native = payload["source_native"]
    mediated = payload["raes_mediated"]
    if not isinstance(native, dict) or not isinstance(mediated, dict):
        raise ValueError("combined environment lanes are invalid")
    _validate_lane_environment(native, "source-native")
    _validate_lane_environment(mediated, "raes-mediated")
    if payload["research_consumers"] != ["OpenRAE/research#14", "OpenRAE/research#20"]:
        raise ValueError("combined environment consumers are invalid")


def _worker_environment(work_root: Path) -> dict[str, str]:
    """Build the isolated subprocess environment for a native worker."""

    home = work_root / "home"
    cache = work_root / "cache"
    temporary = work_root / "tmp"
    for path in (home, cache, temporary):
        path.mkdir(mode=0o700)
    return {
        "HOME": home.as_posix(),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "MPLBACKEND": "Agg",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONPATH": "",
        "PYTHONSAFEPATH": "1",
        "TMPDIR": temporary.as_posix(),
        "XDG_CACHE_HOME": cache.as_posix(),
    }


def _native_worker(output: Path) -> None:
    """Run the exact upstream evaluator and retain raw vectors only in scratch."""

    verify_selected_cyberbattlesim_source()
    qualification = cast(dict[str, object], load_qualification())
    selection = cast(
        dict[str, object], cast(dict[str, object], qualification["protocol"])["selection"]
    )
    attacker = cast(dict[str, object], selection["attacker"])
    bounds_selection = cast(dict[str, object], attacker["environment_bounds"])
    environment = cast(_NativeEvaluatorEnvironment, construct_selected_cyberbattlesim_environment())
    cleanup_verified = False
    result: object | None = None
    try:
        learner_module = importlib.import_module("cyberbattle.agents.baseline.learner")
        policy_module = importlib.import_module(
            "cyberbattle.agents.baseline.agent_randomcredlookup"
        )
        wrapper_module = importlib.import_module("cyberbattle.agents.baseline.agent_wrapper")
        bounds = wrapper_module.EnvironmentBounds.of_identifiers(
            maximum_total_credentials=bounds_selection["maximum_total_credentials"],
            maximum_node_count=bounds_selection["maximum_node_count"],
            identifiers=environment.identifiers,
        )
        policy = policy_module.CredentialCacheExploiter()
        with (
            Path(os.devnull).open("w", encoding="utf-8") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            result = learner_module.epsilon_greedy_search(
                cyberbattle_gym_env=environment,
                environment_properties=bounds,
                learner=policy,
                title="Credential lookups (epsilon-greedy)",
                episode_count=attacker["episode_count"],
                iteration_count=attacker["iteration_count"],
                epsilon=attacker["epsilon"],
                render=False,
                epsilon_exponential_decay=attacker["epsilon_exponential_decay"],
                epsilon_minimum=attacker["epsilon_minimum"],
                verbosity=wrapper_module.Verbosity.Quiet,
            )
    finally:
        try:
            environment.close()
            cleanup_verified = True
        except Exception:
            cleanup_verified = False
    if not isinstance(result, dict):
        raise RuntimeError(_INVALID_NATIVE_RESULT)
    rewards = result.get("all_episodes_rewards")
    availability = result.get("all_episodes_availability")
    if not isinstance(rewards, list) or not isinstance(availability, list):
        raise RuntimeError(_INVALID_NATIVE_RESULT)
    if len(rewards) != _ATTEMPTS_PER_LANE or len(availability) != _ATTEMPTS_PER_LANE:
        raise RuntimeError(_INVALID_NATIVE_RESULT)
    atomic_write_json_artifact(
        output,
        {
            "episodes": [
                {"rewards": episode_rewards, "availability": episode_availability}
                for episode_rewards, episode_availability in zip(rewards, availability, strict=True)
            ],
            "cleanup_verified": cleanup_verified,
        },
    )


def _terminal_cause(
    rewards: Sequence[float], availability: Sequence[float], maximum_steps: int
) -> str | None:
    """Classify a native terminal cause from the frozen evaluator signals."""

    if not rewards or len(rewards) != len(availability):
        return None
    last_reward = rewards[-1]
    terminated = math.isclose(last_reward, WINNING_REWARD) or (
        len(rewards) < maximum_steps and math.isclose(last_reward, LOSING_REWARD)
    )
    cause = classify_terminal_cause(
        last_reward=last_reward,
        network_availability=availability[-1],
        step_count=len(rewards),
        maximum_steps=maximum_steps,
        terminated=terminated,
        truncated=False,
    )
    return None if cause in {"source-terminated", "source-truncated"} else cause


def _native_episode_result(value: object, cleanup_verified: object) -> dict[str, object]:
    """Validate and project one native worker episode."""

    if not isinstance(value, dict) or set(value) != {"rewards", "availability"}:
        raise RuntimeError(_INVALID_NATIVE_RESULT)
    rewards = value["rewards"]
    availability = value["availability"]
    if not isinstance(rewards, list) or not isinstance(availability, list):
        raise RuntimeError(_INVALID_NATIVE_RESULT)
    if len(rewards) != len(availability) or not 1 <= len(rewards) <= 600:
        raise RuntimeError(_INVALID_NATIVE_RESULT)
    numeric_rewards = [float(item) for item in rewards]
    numeric_availability = [float(item) for item in availability]
    if any(not math.isfinite(item) for item in numeric_rewards):
        raise RuntimeError(_INVALID_NATIVE_RESULT)
    if any(not math.isfinite(item) or not 0.0 <= item <= 1.0 for item in numeric_availability):
        raise RuntimeError(_INVALID_NATIVE_RESULT)
    return {
        "steps_to_termination": len(numeric_rewards),
        "cumulative_attacker_reward": math.fsum(numeric_rewards),
        "network_availability": numeric_availability,
        "terminal_cause": _terminal_cause(numeric_rewards, numeric_availability, 600),
        "cleanup_verified": cleanup_verified is True,
        "evidence_refs": [],
    }


def _execute_native_batch() -> list[dict[str, object]]:
    """Execute the native worker in isolated scratch and validate its batch."""

    with tempfile.TemporaryDirectory(prefix="cyberbattlesim-native-") as scratch:
        work_root = Path(scratch)
        output = work_root / "native-worker.json"
        command = [
            sys.executable,
            "-m",
            "raes_adapters.cyberbattlesim.reproduction",
            "_native-worker",
            "--output",
            output.as_posix(),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=work_root,
                env=_worker_environment(work_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1800,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("native evaluator timed out") from error
        if completed.returncode != 0:
            raise RuntimeError("native evaluator failed")
        payload = load_strict_json(output)
        _require_keys(payload, frozenset({"episodes", "cleanup_verified"}), "native worker")
        episodes = payload["episodes"]
        if not isinstance(episodes, list) or len(episodes) != _ATTEMPTS_PER_LANE:
            raise RuntimeError(_INVALID_NATIVE_RESULT)
        return [
            _native_episode_result(episode, payload["cleanup_verified"]) for episode in episodes
        ]


def _mediated_measure(path: Path) -> float:
    """Load the exact finite mediated cumulative-reward measure."""

    value = _load_strict_value(path)
    if not isinstance(value, list):
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    matches = [
        measure
        for measure in value
        if isinstance(measure, dict)
        and isinstance(measure.get("metric_ref"), dict)
        and cast(dict[str, object], measure["metric_ref"]).get("ref_id")
        == "cumulative_attacker_reward"
    ]
    if len(matches) != 1:
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    measure = matches[0]
    reward = measure.get("value")
    if not isinstance(reward, (int, float)) or isinstance(reward, bool):
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    numeric_reward = float(reward)
    if not math.isfinite(numeric_reward):
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    return numeric_reward


def _mediated_outcome(path: Path) -> tuple[list[float], str]:
    """Load the allowlisted availability series and reconstructed source cause."""

    payload = load_strict_json(path)
    _require_keys(
        payload,
        frozenset({"schema_version", "network_availability", "terminal_cause"}),
        "mediated outcome",
    )
    if payload["schema_version"] != "cyberbattlesim-sanitized-episode-outcome/v1":
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    availability = payload["network_availability"]
    cause = payload["terminal_cause"]
    try:
        _validate_availability_series(availability)
        _validate_metric_value("terminal_cause", cause)
    except ValueError as error:
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE) from error
    if cause is None:
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    values = [float(cast(float | int, item)) for item in cast(list[object], availability)]
    return values, cast(str, cause)


def _execute_mediated_attempt(schedule: dict[str, object], run_root: Path) -> dict[str, object]:
    """Execute one isolated RAES-mediated attempt and project portable evidence."""

    pack_root = Path(cast(str, schedule["pack_root"])).resolve()
    run_id = cast(str, schedule["run_id"])
    command = [
        sys.executable,
        "-m",
        "raes_adapters.cli",
        "run",
        "--backend",
        "cyberbattlesim-chain",
        "--mode",
        "smoke",
        "--pack",
        pack_root.as_posix(),
        "--pack-digest",
        "sha256:66493882579d5cba87248c5722782ff5ded5f0d7423f4e559f15bfb61712a905",
        "--scenario",
        "sdl/cyberbattlesim-chain.sdl.yaml",
        "--scenario-digest",
        "sha256:9d696ea7fa23a1e7cf4c1cbc145a7989370dc4e9afff2cd5a17d6d1af887b528",
        "--experiment",
        "experiment/cyberbattlesim-chain.spec.exp.json",
        "--task",
        "experiment/cyberbattlesim-chain.task.exp.json",
        "--participant-implementation",
        "cyberbattlesim-red-credential-cache",
        "--participant-manifest",
        "participant/cyberbattlesim-red-credential-cache.manifest.json",
        "--participant-selection",
        "participant/cyberbattlesim-red-credential-cache.selection.json",
        "--participant-configuration",
        "participant/cyberbattlesim-red-credential-cache.configuration.json",
        "--trial-length",
        "600",
        "--epsilon-step-offset",
        str(schedule["epsilon_step_offset"]),
        "--seed",
        str(_SEED_LABEL),
        "--run-id",
        run_id,
        "--output",
        "portable",
    ]
    with tempfile.TemporaryDirectory(prefix="cyberbattlesim-mediated-") as scratch:
        try:
            completed = subprocess.run(
                command,
                cwd=run_root,
                env=_worker_environment(Path(scratch)),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=900,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("mediated execution timed out") from error
    if completed.returncode != 0:
        raise RuntimeError("mediated execution failed")
    portable = run_root / "portable"
    summary = load_strict_json(portable / "summary.json")
    run_summary = load_strict_json(portable / "runs" / f"{run_id}-1" / "summary.json")
    derived_path = portable / "runs" / f"{run_id}-1" / "derived-measures.json"
    outcome_path = portable / "runs" / f"{run_id}-1" / _EPISODE_OUTCOME_FILE
    reward = _mediated_measure(derived_path)
    availability, terminal_cause = _mediated_outcome(outcome_path)
    steps = run_summary.get("completed_steps")
    if type(steps) is not int:
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    if steps != len(availability):
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    if summary.get("disposition") != "succeeded":
        raise RuntimeError(_INVALID_MEDIATED_EVIDENCE)
    evidence_paths = (
        portable / "runs" / f"{run_id}-1" / "run.json",
        portable / "runs" / f"{run_id}-1" / _EVIDENCE_RECORDS_FILE,
        derived_path,
        outcome_path,
        portable / _INVENTORY_NAME,
    )
    return {
        "steps_to_termination": steps,
        "cumulative_attacker_reward": reward,
        "network_availability": availability,
        "terminal_cause": terminal_cause,
        "cleanup_verified": run_summary.get("cleanup_verified") is True,
        "evidence_refs": [
            {
                "path": path.relative_to(run_root).as_posix(),
                "sha256": _sha256_file(path),
            }
            for path in evidence_paths
        ],
    }


def _inventory_payload(root: Path) -> dict[str, object]:
    """Recompute the closed artifact inventory for one stage."""

    _require_regular_tree(root)
    artifacts = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == _INVENTORY_NAME:
            continue
        content = path.read_bytes()
        artifacts.append(
            {
                "path": path.relative_to(root).as_posix(),
                "media_type": _media_type(path),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    return {"artifacts": artifacts}


def _verify_inventory(root: Path) -> None:
    """Verify a stage inventory exactly against its retained files."""

    _require_regular_tree(root)
    recorded = load_strict_json(root / _INVENTORY_NAME)
    if recorded != _inventory_payload(root):
        raise ValueError("artifact inventory is invalid")


def _combined_environment(native_root: Path, mediated_root: Path) -> dict[str, object]:
    """Join both privacy-bounded lane environment records."""

    native = load_strict_json(native_root / _ENVIRONMENT_FILE)
    mediated = load_strict_json(mediated_root / _ENVIRONMENT_FILE)
    _validate_lane_environment(native, "source-native")
    _validate_lane_environment(mediated, "raes-mediated")
    limitations = sorted(
        {
            item
            for payload in (native, mediated)
            for item in cast(list[object], payload.get("limitations", []))
            if isinstance(item, str)
        }
    )
    combined: dict[str, object] = {
        "schema_version": "cyberbattlesim-baseline-environment-pair/v1",
        "source_native": native,
        "raes_mediated": mediated,
        "research_consumers": ["OpenRAE/research#14", "OpenRAE/research#20"],
        "publication_scope": "reviewed public, non-sensitive reproduction evidence",
        "limitations": limitations,
    }
    _validate_combined_environment(combined)
    return combined


def _citation(path: str, pointer: str, digests: Mapping[str, str]) -> dict[str, object]:
    """Build one digest-bound JSON Pointer citation."""

    return {"path": path, "sha256": digests[path], "json_pointer": pointer}


def _outcome_tier_result(comparison_results: set[str]) -> str:
    """Choose the outcome tier from ordered comparison severity."""

    if "outside-tolerance" in comparison_results:
        return "failed"
    if "unavailable" in comparison_results:
        return "weakened"
    return "passed"


def compute_tiers(
    protocol: Mapping[str, object],
    source_ledger: Mapping[str, object],
    environment: Mapping[str, object],
    aggregates: Mapping[str, object],
    digests: Mapping[str, str],
) -> dict[str, object]:
    """Recompute the six fixed issue-30 tier projections."""

    validate_protocol(protocol, require_oracle=True)
    source_selection = cast(
        dict[str, object], cast(dict[str, object], protocol["declaration"])["source_selection"]
    )
    ledger_source = cast(dict[str, object], source_ledger["source"])
    authored_result = (
        "passed"
        if all(
            ledger_source.get(key) == source_selection.get(key)
            for key in ("commit", "tree", "version", "runtime_tree_sha256", "notebook_sha256")
        )
        else "failed"
    )
    controls = cast(
        dict[str, object], cast(dict[str, object], protocol["declaration"])["stochastic_controls"]
    )
    execution_result = (
        "passed" if controls["source-native"] == controls["raes-mediated"] else "weakened"
    )
    loss_refs = source_ledger.get("loss_refs")
    state_result = (
        "weakened"
        if isinstance(loss_refs, list) and "loss-abstracted-topology" in loss_refs
        else "passed"
    )
    comparisons = cast(dict[str, object], aggregates["comparisons"])
    comparison_results = {
        cast(str, cast(dict[str, object], value)["result"]) for value in comparisons.values()
    }
    outcome_result = _outcome_tier_result(comparison_results)
    limitations = environment.get("limitations")
    disclosure_result = "passed" if isinstance(limitations, list) and limitations else "failed"
    tier_rows = [
        {
            "tier": "authored-source",
            "result": authored_result,
            "rationale": "Pinned source, tree, notebook, and runtime-tree identities join.",
            "evidence": [_citation(_SOURCE_LEDGER_FILE, "/source", digests)],
        },
        {
            "tier": "contract",
            "result": "passed",
            "rationale": (
                "The declaration embeds a validated RAES study over the published task/spec refs."
            ),
            "evidence": [_citation(_PROTOCOL_FILE, "/declaration/study", digests)],
        },
        {
            "tier": "execution-control",
            "result": execution_result,
            "rationale": "Actual random-stream binding dispositions differ between lanes.",
            "evidence": [_citation(_PROTOCOL_FILE, "/declaration/stochastic_controls", digests)],
        },
        {
            "tier": "state-observation",
            "result": state_result,
            "rationale": (
                "The authored RAES topology is representative and native observations "
                "remain private."
            ),
            "evidence": [_citation(_SOURCE_LEDGER_FILE, "/loss_refs", digests)],
        },
        {
            "tier": "outcome-evaluation",
            "result": outcome_result,
            "rationale": "Only complete predeclared metric comparisons can pass this tier.",
            "evidence": [_citation(_AGGREGATES_FILE, "/comparisons", digests)],
        },
        {
            "tier": "disclosure",
            "result": disclosure_result,
            "rationale": (
                "Known apparatus, source, stochastic, topology, and metric losses are retained."
            ),
            "evidence": [
                _citation(_SOURCE_LEDGER_FILE, "/exclusions", digests),
                _citation(_ENVIRONMENT_FILE, "/limitations", digests),
                _citation(_BENCH_NOTES_FILE, "/notes", digests),
            ],
        },
    ]
    return {
        "schema_version": "cyberbattlesim-baseline-tiers/v1",
        "declaration_sha256": protocol["declaration_sha256"],
        "tiers": tier_rows,
        "explicit_non_claims": cast(dict[str, object], protocol["declaration"])[
            "explicit_non_claims"
        ],
    }


def _validation_report(revision: str) -> str:
    """Render the stable offline-verification report for one revision."""

    return (
        "# CyberBattleSim baseline reproduction validation\n\n"
        f"Frozen revision: `{revision}`\n\n"
        "The bundle contains 20 preallocated terminal attempts: ten source-native "
        "episodes and ten RAES-mediated episodes. Aggregate and tier projections are "
        "derived only from retained portable evidence.\n\n"
        "Offline verification command:\n\n"
        "```bash\n"
        "python -m raes_adapters.cyberbattlesim.reproduction verify --bundle .\n"
        "```\n\n"
        "Verification checks the frozen declaration/oracle, RAES study model, terminal "
        "schedule, timestamped bench notes, per-file digests, evidence references, "
        "aggregate recomputation, six tier citations, and the bounded leakage denylist. "
        "It needs no network or native simulator import.\n\n"
        "This artifact does not claim deterministic replay, exact state or observation "
        "equivalence, cross-simulator equality, agent ranking, benchmark comparability, "
        "outcome equivalence, or general scientific reproducibility.\n"
    )


def _assert_stage_rows(
    protocol: Mapping[str, object], rows: Sequence[Mapping[str, object]]
) -> None:
    """Require every frozen attempt to have one terminal stage row."""

    schedule = cast(
        list[dict[str, object]], cast(dict[str, object], protocol["declaration"])["schedule"]
    )
    expected = {(entry["run_id"], entry["attempt_id"], entry["lane"]) for entry in schedule}
    observed = {(row["run_id"], row["attempt_id"], row["lane"]) for row in rows}
    if len(rows) != len(schedule) or observed != expected:
        raise ValueError("terminal inventory does not match the frozen schedule")
    if any(row["disposition"] not in _DISPOSITIONS for row in rows):
        raise ValueError("terminal inventory contains a nonterminal attempt")


def _write_tier_projection(
    root: Path,
    protocol: Mapping[str, object],
    source_ledger: Mapping[str, object],
    environment: Mapping[str, object],
    aggregates: Mapping[str, object],
) -> None:
    """Recompute and write the digest-bound six-tier projection."""

    digest_paths = (
        _PROTOCOL_FILE,
        _SOURCE_LEDGER_FILE,
        _ENVIRONMENT_FILE,
        _AGGREGATES_FILE,
        _BENCH_NOTES_FILE,
    )
    digests = {name: _sha256_file(root / name) for name in digest_paths}
    tiers = compute_tiers(protocol, source_ledger, environment, aggregates, digests)
    atomic_write_json_artifact(root / _TIERS_FILE, tiers)


def _verify_finalized_stage(
    root: Path,
    bench_notes: dict[str, object],
    protocol: Mapping[str, object],
    source_ledger: Mapping[str, object],
    environment: Mapping[str, object],
    aggregates: Mapping[str, object],
    failure_summary: str,
) -> None:
    """Seal and offline-verify one note-bound finalization state."""

    _write_bench_notes(root, bench_notes)
    _write_tier_projection(root, protocol, source_ledger, environment, aggregates)
    _scan_portable(root)
    _seal_inventory(root)
    try:
        verify_bundle(root)
    except Exception:
        _append_bench_note(
            bench_notes,
            phase="verify",
            severity="error",
            event_code="offline-verification-failed",
            summary=failure_summary,
            disposition="failed",
            evidence_paths=(_INVENTORY_NAME,),
        )
        _write_bench_notes(root, bench_notes)
        _write_tier_projection(root, protocol, source_ledger, environment, aggregates)
        _seal_inventory(root)
        raise RuntimeError("final bundle offline verification failed") from None


def _combined_bench_notes(
    oracle_root: Path,
    mediated_root: Path,
    protocol: Mapping[str, object],
) -> dict[str, object]:
    """Combine and validate stage notes in their timestamped order."""

    oracle_notes = _load_bench_notes(oracle_root, protocol)
    mediated_notes = _load_bench_notes(mediated_root, protocol)
    notes = sorted(
        cast(list[dict[str, object]], oracle_notes["notes"])
        + cast(list[dict[str, object]], mediated_notes["notes"]),
        key=lambda note: (cast(str, note["recorded_at"]), cast(str, note["note_id"])),
    )
    bench_notes = _new_bench_notes(protocol, notes)
    _validate_bench_notes(bench_notes, protocol)
    return bench_notes


def _copy_stage_runs(root: Path, *stage_roots: Path) -> None:
    """Copy every stage run into the reserved final bundle."""

    runs_root = root / "runs"
    os.mkdir(runs_root, 0o700)
    for stage in stage_roots:
        for run in sorted((stage / "runs").iterdir()):
            shutil.copytree(run, runs_root / run.name)


def finalize_bundle(oracle_root: Path, mediated_root: Path, output: Path) -> Path:
    """Assemble and seal the accepted bundle exactly once."""

    _verify_inventory(oracle_root)
    _verify_inventory(mediated_root)
    oracle_protocol_path = oracle_root / _PROTOCOL_FILE
    mediated_protocol_path = mediated_root / _PROTOCOL_FILE
    if oracle_protocol_path.read_bytes() != mediated_protocol_path.read_bytes():
        raise ValueError("mediated collection is not bound to the frozen protocol")
    protocol = load_strict_json(oracle_protocol_path)
    validate_protocol(protocol, require_oracle=True)
    if output.name != protocol["declaration_sha256"]:
        raise ValueError("bundle directory is not the declaration-digest revision")
    native_rows = load_terminal_rows(oracle_root)
    mediated_rows = load_terminal_rows(mediated_root)
    rows = native_rows + mediated_rows
    _assert_stage_rows(protocol, rows)
    ordered_native = [
        {"run_id": row["run_id"], "metrics": row["metrics"]}
        for row in sorted(native_rows, key=lambda item: cast(int, item["replicate"]))
    ]
    oracle = cast(dict[str, object], protocol["oracle"])
    if sha256_payload(ordered_native) != oracle["native_result_set_sha256"]:
        raise ValueError("source-native oracle does not match retained terminal evidence")
    bench_notes = _combined_bench_notes(oracle_root, mediated_root, protocol)
    root = _reserve_directory(output)
    atomic_write_json_artifact(root / _PROTOCOL_FILE, protocol)
    source_ledger = load_strict_json(oracle_root / _SOURCE_LEDGER_FILE)
    validate_source_ledger(source_ledger, protocol)
    atomic_write_json_artifact(root / _SOURCE_LEDGER_FILE, source_ledger)
    environment = _combined_environment(oracle_root, mediated_root)
    atomic_write_json_artifact(root / _ENVIRONMENT_FILE, environment)
    _append_bench_note(
        bench_notes,
        phase="finalize",
        severity="info",
        event_code="bundle-finalization-started",
        summary="Assembly of the content-addressed public bundle was started.",
        disposition="observed",
        evidence_paths=(_PROTOCOL_FILE, _SOURCE_LEDGER_FILE, _ENVIRONMENT_FILE),
    )
    _write_bench_notes(root, bench_notes)
    _copy_stage_runs(root, oracle_root, mediated_root)
    aggregates = compute_aggregates(protocol, rows)
    atomic_write_json_artifact(root / _AGGREGATES_FILE, aggregates)
    revision_value = protocol["declaration_sha256"]
    if not isinstance(revision_value, str):
        raise ValueError("protocol declaration digest is invalid")
    revision = revision_value
    (root / "validation-report.md").write_text(
        _validation_report(revision), encoding="utf-8", newline="\n"
    )
    _append_bench_note(
        bench_notes,
        phase="finalize",
        severity="info",
        event_code="bundle-finalized",
        summary="All declared runs and derived public artifacts were assembled without drops.",
        disposition="passed",
        evidence_paths=(_AGGREGATES_FILE, "validation-report.md"),
    )
    _append_bench_note(
        bench_notes,
        phase="verify",
        severity="info",
        event_code="offline-verification-started",
        summary="Pure offline recomputation and integrity verification were started.",
        disposition="observed",
        evidence_paths=(_PROTOCOL_FILE, _AGGREGATES_FILE),
    )
    _verify_finalized_stage(
        root,
        bench_notes,
        protocol,
        source_ledger,
        environment,
        aggregates,
        "Pure offline recomputation or integrity verification failed.",
    )
    _append_bench_note(
        bench_notes,
        phase="verify",
        severity="info",
        event_code="offline-verification-passed",
        summary="Pure offline recomputation and integrity verification passed.",
        disposition="passed",
        evidence_paths=(_INVENTORY_NAME, _AGGREGATES_FILE, _TIERS_FILE),
    )
    _verify_finalized_stage(
        root,
        bench_notes,
        protocol,
        source_ledger,
        environment,
        aggregates,
        "The final note-bound bundle failed its second integrity verification.",
    )
    return root


def _resolve_pointer(document: object, pointer: str) -> object:
    """Resolve one strict JSON Pointer within a cited document."""

    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("tier citation JSON Pointer is invalid")
    current = document
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ValueError("tier citation JSON Pointer is unresolved")
    return current


def _contains_native_field_name(value: str) -> bool:
    """Detect a forbidden native field name in portable text."""

    folded = value.casefold()
    return any(name.casefold() in folded for name in _FORBIDDEN_NATIVE_FIELD_NAMES)


def _scan_json_value(value: object, *, withheld_ref: bool = False) -> None:
    """Structurally scan JSON while permitting disclosed withheld references."""

    if isinstance(value, dict):
        for key, child in value.items():
            if _contains_native_field_name(key):
                raise ValueError(_FORBIDDEN_PORTABLE_VALUE)
            _scan_json_value(child, withheld_ref=key == "withheld_refs")
    elif isinstance(value, list):
        for child in value:
            _scan_json_value(child, withheld_ref=withheld_ref)
    elif isinstance(value, str) and not withheld_ref and _contains_native_field_name(value):
        raise ValueError(_FORBIDDEN_PORTABLE_VALUE)


def _host_path_prefixes() -> tuple[str, ...]:
    """Return host-path markers that portable artifacts must not contain."""

    temporary_prefix = PurePosixPath("/", "tmp").as_posix() + "/"
    local_prefixes = ("/home/", temporary_prefix)
    return local_prefixes + tuple(f"file://{prefix}" for prefix in local_prefixes)


def _scan_portable_file(path: Path) -> None:
    """Apply size, native-value, secret, and host-path gates to one file."""

    content = path.read_bytes()
    if len(content) > 500 * 1024:
        raise ValueError("portable artifact exceeds the repository size limit")
    text = content.decode("utf-8", errors="ignore")
    folded = text.casefold()
    if any(token.casefold() in folded for token in _FORBIDDEN_PORTABLE_TOKENS):
        raise ValueError(_FORBIDDEN_PORTABLE_VALUE)
    if path.suffix == ".json":
        _scan_json_value(_load_strict_value(path))
    elif _contains_native_field_name(text):
        raise ValueError(_FORBIDDEN_PORTABLE_VALUE)
    if any(prefix in text for prefix in _host_path_prefixes()):
        raise ValueError("portable artifact contains a host path")


def _scan_portable(root: Path) -> None:
    """Scan every retained portable artifact without native imports."""

    _require_regular_tree(root)
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        _scan_portable_file(path)


def _validate_model_list(path: Path, model: type[object]) -> None:
    """Validate a portable list against one published RAES model."""

    payload = _load_strict_value(path)
    if not isinstance(payload, list):
        raise ValueError("portable RAES model collection is invalid")
    validator = getattr(model, "model_validate", None)
    if not callable(validator):
        raise ValueError("portable RAES model validator is unavailable")
    for item in payload:
        validator(item)


def _validate_mediated_portable(
    run_root: Path, run_id: str, *, require_outcome: bool = True
) -> None:
    """Validate the complete portable RAES projection for one mediated run."""

    portable = run_root / "portable"
    archival = portable / "runs" / f"{run_id}-1"
    ExperimentRunModel.model_validate(load_strict_json(archival / "run.json"))
    ParticipantImplementationProvenanceModel.model_validate(
        load_strict_json(archival / "participant-provenance.json")
    )
    _validate_model_list(archival / _EVIDENCE_RECORDS_FILE, ExperimentEvidenceRecordModel)
    _validate_model_list(archival / "derived-measures.json", ExperimentDerivedMeasureModel)
    _validate_model_list(archival / "diagnostics.json", DiagnosticModel)
    outcome_path = archival / _EPISODE_OUTCOME_FILE
    if not require_outcome:
        _verify_inventory(portable)
        return
    _mediated_outcome(outcome_path)
    evidence_payload = _load_strict_value(archival / _EVIDENCE_RECORDS_FILE)
    if not isinstance(evidence_payload, list):
        raise ValueError("portable outcome evidence is invalid")
    records = [ExperimentEvidenceRecordModel.model_validate(item) for item in evidence_payload]
    matching = [
        record.raw_content
        for record in records
        if record.raw_content.content_uri == _EPISODE_OUTCOME_FILE
    ]
    if (
        len(matching) != 1
        or matching[0].content_checksum is None
        or matching[0].content_checksum.algorithm != "sha256"
        or matching[0].content_checksum.value != _sha256_file(outcome_path)
    ):
        raise ValueError("portable outcome evidence binding is invalid")
    _verify_inventory(portable)


def _verify_bench_evidence(root: Path, notes: Sequence[Mapping[str, object]]) -> None:
    """Verify every bench-note evidence path stays inside the bundle."""

    for note in notes:
        for ref in cast(list[dict[str, object]], note["evidence_refs"]):
            target = (root / _safe_relative_path(ref["path"])).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError("bench note evidence reference is unresolved")


def _verify_terminal_refs(run_root: Path, refs: object) -> None:
    """Verify the structure, location, and digest of terminal evidence refs."""

    if not isinstance(refs, list):
        raise ValueError("terminal row evidence references are invalid")
    resolved_root = run_root.resolve()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise ValueError("terminal row evidence references are invalid")
        target = (run_root / _safe_relative_path(ref["path"])).resolve()
        if not target.is_relative_to(resolved_root) or not target.is_file():
            raise ValueError("terminal row evidence reference is unresolved")
        if _sha256_file(target) != ref["sha256"]:
            raise ValueError("terminal row evidence digest is invalid")


def _verify_terminal_evidence(
    root: Path,
    protocol: Mapping[str, object],
    protocol_digest: str,
    row: Mapping[str, object],
) -> None:
    """Verify bindings and evidence references for one terminal row."""

    if row["declaration_sha256"] != protocol["declaration_sha256"]:
        raise ValueError("terminal row declaration binding is invalid")
    mediated = row["lane"] == "raes-mediated"
    if mediated and row["protocol_sha256"] != protocol_digest:
        raise ValueError("mediated terminal row protocol binding is invalid")
    run_root = root / "runs" / cast(str, row["run_id"])
    if mediated and row["disposition"] == "valid":
        declaration = cast(Mapping[str, object], protocol["declaration"])
        _validate_mediated_portable(
            run_root,
            cast(str, row["run_id"]),
            require_outcome=declaration["attempt_series"] == _ATTEMPT_SERIES,
        )
    _verify_terminal_refs(run_root, row["evidence_refs"])


def _verify_native_oracle(
    protocol: Mapping[str, object], rows: Sequence[Mapping[str, object]]
) -> None:
    """Recompute the ordered source-native oracle digest."""

    native_rows = sorted(
        (row for row in rows if row["lane"] == "source-native"),
        key=lambda item: cast(int, item["replicate"]),
    )
    oracle_rows = [{"run_id": row["run_id"], "metrics": row["metrics"]} for row in native_rows]
    oracle = cast(dict[str, object], protocol["oracle"])
    if sha256_payload(oracle_rows) != oracle["native_result_set_sha256"]:
        raise ValueError("source-native oracle digest is invalid")


def _verify_tier_citation(root: Path, citation: object) -> None:
    """Verify one digest-bound tier citation and JSON Pointer."""

    if not isinstance(citation, dict) or set(citation) != {"path", "sha256", "json_pointer"}:
        raise ValueError("tier evidence is invalid")
    relative = _safe_relative_path(citation["path"])
    target = root / relative
    if not target.is_file() or _sha256_file(target) != citation["sha256"]:
        raise ValueError("tier evidence digest is invalid")
    _resolve_pointer(load_strict_json(target), cast(str, citation["json_pointer"]))


def _verify_tier(root: Path, tier: object) -> None:
    """Verify one ordered tier row and all of its citations."""

    if not isinstance(tier, dict) or tier.get("result") not in {"passed", "failed", "weakened"}:
        raise ValueError("tier inventory is invalid")
    evidence = tier.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("tier evidence is invalid")
    for citation in evidence:
        _verify_tier_citation(root, citation)


def _verified_tiers(
    root: Path,
    protocol: Mapping[str, object],
    source_ledger: Mapping[str, object],
    environment: Mapping[str, object],
    aggregates: Mapping[str, object],
) -> list[dict[str, object]]:
    """Recompute and validate the complete ordered tier projection."""

    digest_names = (
        _PROTOCOL_FILE,
        _SOURCE_LEDGER_FILE,
        _ENVIRONMENT_FILE,
        _AGGREGATES_FILE,
        _BENCH_NOTES_FILE,
    )
    digests = {name: _sha256_file(root / name) for name in digest_names}
    recorded = load_strict_json(root / _TIERS_FILE)
    expected = compute_tiers(protocol, source_ledger, environment, aggregates, digests)
    if canonical_json_bytes(recorded) != canonical_json_bytes(expected):
        raise ValueError("tier recomputation failed")
    tiers = recorded.get("tiers")
    expected_names = list(_TIERS)
    if (
        not isinstance(tiers, list)
        or [item.get("tier") for item in tiers if isinstance(item, dict)] != expected_names
    ):
        raise ValueError("tier inventory is invalid")
    for tier in tiers:
        _verify_tier(root, tier)
    return cast(list[dict[str, object]], tiers)


def verify_bundle(root: Path) -> dict[str, object]:
    """Verify and recompute a sealed bundle without importing native source."""

    _require_regular_tree(root)
    root = root.resolve()
    protocol = load_strict_json(root / _PROTOCOL_FILE)
    validate_protocol(protocol, require_oracle=True)
    source_ledger = load_strict_json(root / _SOURCE_LEDGER_FILE)
    validate_source_ledger(source_ledger, protocol)
    environment = load_strict_json(root / _ENVIRONMENT_FILE)
    _validate_combined_environment(environment)
    bench_notes = _load_bench_notes(root, protocol)
    notes = cast(list[dict[str, object]], bench_notes["notes"])
    _verify_bench_evidence(root, notes)
    rows = load_terminal_rows(root)
    _assert_stage_rows(protocol, rows)
    protocol_digest = _sha256_file(root / _PROTOCOL_FILE)
    for row in rows:
        _verify_terminal_evidence(root, protocol, protocol_digest, row)
    _verify_native_oracle(protocol, rows)
    recorded_aggregates = load_strict_json(root / _AGGREGATES_FILE)
    expected_aggregates = compute_aggregates(protocol, rows)
    if canonical_json_bytes(recorded_aggregates) != canonical_json_bytes(expected_aggregates):
        raise ValueError("aggregate recomputation failed")
    tiers = _verified_tiers(root, protocol, source_ledger, environment, recorded_aggregates)
    _scan_portable(root)
    _verify_inventory(root)
    return {
        "disposition": "verified",
        "scheduled_count": len(rows),
        "tier_count": len(tiers),
        "bench_note_count": len(notes),
        "inventory_sha256": _sha256_file(root / _INVENTORY_NAME),
    }


def _parser() -> argparse.ArgumentParser:
    """Build the closed researcher command-line parser."""

    parser = argparse.ArgumentParser(prog="python -m raes_adapters.cyberbattlesim.reproduction")
    subcommands = parser.add_subparsers(dest="command", required=True)
    declare = subcommands.add_parser("declare")
    declare.add_argument("--output", type=Path, required=True)
    native = subcommands.add_parser("native")
    native.add_argument("--declaration", type=Path, required=True)
    native.add_argument("--output", type=Path, required=True)
    mediated = subcommands.add_parser("mediated")
    mediated.add_argument("--oracle", type=Path, required=True)
    mediated.add_argument("--pack", type=Path, required=True)
    mediated.add_argument("--output", type=Path, required=True)
    finalize = subcommands.add_parser("finalize")
    finalize.add_argument("--oracle", type=Path, required=True)
    finalize.add_argument("--mediated", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)
    verify = subcommands.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    worker = subcommands.add_parser("_native-worker", help=argparse.SUPPRESS)
    worker.add_argument("--output", type=Path, required=True)
    return parser


def _invocation_output(value: Path) -> Path:
    """Resolve an output strictly beneath the invocation directory."""

    root = Path.cwd().resolve()
    resolved = (root / value).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError("reproduction output must be beneath the invocation directory")
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    """Run the closed collection commands with bounded failures."""

    try:
        args = _parser().parse_args(argv)
        if args.command == "declare":
            write_declaration(Path.cwd(), _invocation_output(args.output))
        elif args.command == "native":
            collect_native(args.declaration, _invocation_output(args.output))
        elif args.command == "mediated":
            collect_mediated(args.oracle, args.pack, _invocation_output(args.output))
        elif args.command == "finalize":
            finalize_bundle(args.oracle, args.mediated, _invocation_output(args.output))
        elif args.command == "verify":
            print(json.dumps(verify_bundle(args.bundle), sort_keys=True))
        else:
            _native_worker(args.output)
    except Exception:
        print("reproduction.command.failed: reproduction command failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_declaration",
    "canonical_json_bytes",
    "collect_mediated",
    "collect_native",
    "compute_aggregates",
    "compute_tiers",
    "finalize_bundle",
    "load_strict_json",
    "load_terminal_rows",
    "main",
    "sha256_payload",
    "terminal_rows_from_results",
    "validate_protocol",
    "verify_bundle",
    "write_declaration",
]
