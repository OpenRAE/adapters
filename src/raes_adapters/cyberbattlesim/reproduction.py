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
from typing import Protocol, cast

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

_SCHEMA = "cyberbattlesim-baseline-reproduction/v2"
_SOURCE_LEDGER_SCHEMA = "cyberbattlesim-baseline-source-ledger/v1"
_RUN_SCHEMA = "cyberbattlesim-baseline-run/v1"
_AGGREGATE_SCHEMA = "cyberbattlesim-baseline-aggregates/v1"
_BENCH_NOTES_SCHEMA = "cyberbattlesim-baseline-bench-notes/v1"
_INVENTORY_NAME = "inventory.json"
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
_ATTEMPT_SERIES = "cbs-r2"
_REJECTED_DECLARATION_SHA256 = "825dde3b4cd66f228e0f93157a2add35e3c9a822a7adac1d8ffd322b32116232"
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
    identifiers: object

    def close(self) -> None: ...


def canonical_json_bytes(payload: object) -> bytes:
    """Return the byte representation used by every issue-local digest."""

    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_payload(payload: object) -> str:
    """Hash one canonical issue-local JSON payload."""

    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_constant(_value: str) -> object:
    raise ValueError("invalid JSON artifact")


def _closed_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid JSON artifact")
        result[key] = value
    return result


def _load_strict_value(path: Path) -> object:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_closed_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("invalid JSON artifact") from error


def load_strict_json(path: Path) -> dict[str, object]:
    """Load a duplicate-key-free, finite JSON object."""

    value = _load_strict_value(path)
    if not isinstance(value, dict):
        raise ValueError("invalid JSON artifact")
    return value


def _require_keys(value: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} has unknown or missing fields")


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("artifact relative path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or path.as_posix() != value:
        raise ValueError("artifact relative path is invalid")
    return value


def _bench_note_policy() -> dict[str, object]:
    return {
        "artifact": "bench-notes.json",
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
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_bench_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("bench note timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("bench note timestamp is invalid") from error
    normalized = parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if parsed.utcoffset() != UTC.utcoffset(None) or normalized != value:
        raise ValueError("bench note timestamp is invalid")
    return value


def _validate_bench_notes(payload: Mapping[str, object], protocol: Mapping[str, object]) -> None:
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
        if not isinstance(note, dict):
            raise ValueError("bench note is invalid")
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
        previous_timestamp = recorded_at
        if note["phase"] not in _BENCH_PHASES:
            raise ValueError("bench note phase is invalid")
        if note["severity"] not in _BENCH_SEVERITIES:
            raise ValueError("bench note severity is invalid")
        if note["event_code"] not in _BENCH_EVENT_CODES:
            raise ValueError("bench note event code is invalid")
        if note["disposition"] not in _BENCH_DISPOSITIONS:
            raise ValueError("bench note disposition is invalid")
        summary = note["summary"]
        if not isinstance(summary, str) or not summary or len(summary) > 240 or "\n" in summary:
            raise ValueError("bench note summary is invalid")
        evidence_refs = note["evidence_refs"]
        if not isinstance(evidence_refs, list):
            raise ValueError("bench note evidence references are invalid")
        for ref in evidence_refs:
            if not isinstance(ref, dict) or set(ref) != {"path"}:
                raise ValueError("bench note evidence references are invalid")
            _safe_relative_path(ref["path"])


def _new_bench_notes(
    protocol: Mapping[str, object], notes: Sequence[Mapping[str, object]] = ()
) -> dict[str, object]:
    return {
        "schema_version": _BENCH_NOTES_SCHEMA,
        "declaration_sha256": protocol["declaration_sha256"],
        "notes": [dict(note) for note in notes],
    }


def _append_bench_note(
    payload: dict[str, object],
    protocol: Mapping[str, object],
    *,
    phase: str,
    severity: str,
    event_code: str,
    summary: str,
    disposition: str,
    evidence_paths: Sequence[str],
) -> None:
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
    _validate_bench_notes(payload, protocol)


def _write_bench_notes(root: Path, payload: Mapping[str, object]) -> None:
    atomic_write_json_artifact(root / "bench-notes.json", dict(payload))


def _load_bench_notes(root: Path, protocol: Mapping[str, object]) -> dict[str, object]:
    payload = load_strict_json(root / "bench-notes.json")
    _validate_bench_notes(payload, protocol)
    return payload


def _artifact(repo_root: Path, artifact_id: str, relative: str) -> dict[str, object]:
    path = repo_root / relative
    return {"artifact_id": artifact_id, "path": relative, "sha256": _sha256_file(path)}


def _study(task: ExperimentTaskModel) -> dict[str, object]:
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
        "behavioral_claims": [
            {
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
                "limitations": [
                    "The lanes have different stochastic bindings and evaluator paths."
                ],
                "explicit_non_claims": [
                    "No trace, state, observation, deterministic-replay, or outcome-equivalence "
                    "claim is made."
                ],
            }
        ],
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
        "analysis_plan": {
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
                "missingness_assumption": (
                    "Missingness is apparatus- or failure-induced, not random."
                ),
                "handling": (
                    "Retain all terminal attempts in denominators; do not impute or silently drop."
                ),
                "sensitivity_analysis": "Unavailable declared metrics weaken the applicable tier.",
            },
        },
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
    artifacts = [
        _artifact(
            repo_root,
            "qualification",
            "src/raes_adapters/cyberbattlesim/qualification.json",
        ),
        _artifact(
            repo_root,
            "public-protocol",
            "src/raes_adapters/cyberbattlesim/public-protocol.md",
        ),
        _artifact(
            repo_root,
            "source-ledger",
            "src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl",
        ),
        _artifact(
            repo_root,
            "loss-disclosures",
            "src/raes_adapters/cyberbattlesim/mapping/loss-disclosures.md",
        ),
        _artifact(
            repo_root,
            "reproduction-runner",
            "src/raes_adapters/cyberbattlesim/reproduction.py",
        ),
        _artifact(
            repo_root,
            "mediated-researcher",
            "src/raes_adapters/cyberbattlesim/researcher.py",
        ),
        _artifact(
            repo_root,
            "mediated-driver",
            "src/raes_adapters/cyberbattlesim/backend/driver.py",
        ),
        _artifact(
            repo_root,
            "selected-source-helper",
            "src/raes_adapters/cyberbattlesim/backend/source.py",
        ),
        _artifact(
            repo_root,
            "task",
            task_path.relative_to(repo_root).as_posix(),
        ),
        _artifact(
            repo_root,
            "spec",
            spec_path.relative_to(repo_root).as_posix(),
        ),
        _artifact(
            repo_root,
            "pack-manifest",
            "environments/cyberbattlesim-chain/pack.content-manifest.json",
        ),
        _artifact(
            repo_root,
            "participant-manifest",
            "environments/cyberbattlesim-chain/participant/"
            "cyberbattlesim-red-credential-cache.manifest.json",
        ),
        _artifact(
            repo_root,
            "participant-selection",
            "environments/cyberbattlesim-chain/participant/"
            "cyberbattlesim-red-credential-cache.selection.json",
        ),
        _artifact(
            repo_root,
            "participant-configuration",
            "environments/cyberbattlesim-chain/participant/"
            "cyberbattlesim-red-credential-cache.configuration.json",
        ),
    ]
    declaration: dict[str, object] = {
        "study": _study(task),
        "artifacts": artifacts,
        "source_selection": {
            "repository": source["repository"],
            "commit": source["commit"],
            "tree": source["tree"],
            "version": source["version"],
            "runtime_tree_sha256": runtime_tree["sha256"],
            "notebook_path": "notebooks/notebook_withdefender.py",
            "notebook_sha256": benchmark["source_notebook_sha256"],
            "evaluator": qualification["protocol"]["selection"]["evaluator"],  # type: ignore[index]
        },
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
    protocol: dict[str, object] = {
        "schema_version": _SCHEMA,
        "declaration_sha256": sha256_payload(declaration),
        "declaration": declaration,
        "oracle": None,
    }
    source_ledger: dict[str, object] = {
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
        "artifact_refs": artifacts,
        "adapter": {
            "distribution": "raes-adapters",
            "version": _installed_version("raes-adapters"),
            "runner_artifact_ids": [
                "reproduction-runner",
                "mediated-researcher",
                "mediated-driver",
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
    validate_protocol(protocol, require_oracle=False)
    validate_source_ledger(source_ledger, protocol)
    return protocol, source_ledger


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
    source = payload["source"]
    if not isinstance(source, dict):
        raise ValueError("source ledger source is invalid")
    _require_keys(
        source,
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
    for digest_key in ("runtime_tree_sha256", "notebook_sha256"):
        if not _is_sha256(source[digest_key]):
            raise ValueError("source ledger digest is invalid")
    _safe_relative_path(source["notebook_path"])
    declaration = cast(dict[str, object], protocol["declaration"])
    if payload["artifact_refs"] != declaration["artifacts"]:
        raise ValueError("source ledger artifact join is invalid")
    adapter = payload["adapter"]
    if not isinstance(adapter, dict):
        raise ValueError("source ledger adapter is invalid")
    _require_keys(
        adapter,
        frozenset({"distribution", "version", "runner_artifact_ids"}),
        "source ledger adapter",
    )
    runner_ids = adapter["runner_artifact_ids"]
    if not isinstance(runner_ids, list) or len(set(runner_ids)) != len(runner_ids):
        raise ValueError("source ledger adapter is invalid")
    for field in ("loss_refs", "exclusions", "compatibility_patches"):
        value = payload[field]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("source ledger disclosure is invalid")


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
    expected_declaration_keys = frozenset(
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
    _require_keys(declaration, expected_declaration_keys, "protocol declaration")
    if payload["declaration_sha256"] != sha256_payload(declaration):
        raise ValueError("protocol declaration digest is invalid")
    ExperimentStudyModel.model_validate(declaration["study"])
    if declaration["retry_budget"] != 0:
        raise ValueError("retry policy is invalid")
    if declaration["attempt_series"] != _ATTEMPT_SERIES:
        raise ValueError("attempt series is invalid")
    prior_attempts = declaration["prior_attempts"]
    if prior_attempts != _prior_attempt_disclosure():
        raise ValueError("prior attempt disclosure is invalid")
    if declaration["bench_notes"] != _bench_note_policy():
        raise ValueError("bench note policy is invalid")
    if declaration["metrics"] != list(_METRICS):
        raise ValueError("metric declaration is invalid")
    if declaration["tier_policy"] != list(_TIERS):
        raise ValueError("tier policy is invalid")
    if set(cast(list[object], declaration["terminal_dispositions"])) != _DISPOSITIONS:
        raise ValueError("terminal dispositions are invalid")
    artifacts = declaration["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("artifact references are invalid")
    artifact_ids: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("artifact references are invalid")
        _require_keys(item, frozenset({"artifact_id", "path", "sha256"}), "artifact reference")
        artifact_id = item["artifact_id"]
        if not isinstance(artifact_id, str) or artifact_id in artifact_ids:
            raise ValueError("artifact references are invalid")
        artifact_ids.add(artifact_id)
        _safe_relative_path(item["path"])
        if not _is_sha256(item["sha256"]):
            raise ValueError("artifact digest is invalid")
    schedule = declaration["schedule"]
    if not isinstance(schedule, list) or len(schedule) != 20:
        raise ValueError("attempt schedule is invalid")
    run_ids: set[str] = set()
    attempt_ids: set[str] = set()
    counts = dict.fromkeys(_LANES, 0)
    for entry in schedule:
        if not isinstance(entry, dict):
            raise ValueError("attempt schedule is invalid")
        _require_keys(
            entry,
            frozenset({"lane", "replicate", "run_id", "attempt_id", "seed_label"}),
            "schedule entry",
        )
        lane = entry["lane"]
        if lane not in _LANES or type(entry["replicate"]) is not int:
            raise ValueError("attempt schedule is invalid")
        run_id = entry["run_id"]
        attempt_id = entry["attempt_id"]
        if not isinstance(run_id, str) or not isinstance(attempt_id, str):
            raise ValueError("attempt schedule is invalid")
        if run_id in run_ids or attempt_id in attempt_ids:
            raise ValueError("attempt identities are not unique")
        run_ids.add(run_id)
        attempt_ids.add(attempt_id)
        counts[cast(str, lane)] += 1
    if set(counts.values()) != {_ATTEMPTS_PER_LANE}:
        raise ValueError("attempt schedule is invalid")
    prior_run_ids = set(cast(list[str], prior_attempts["run_ids"]))
    prior_attempt_ids = set(cast(list[str], prior_attempts["attempt_ids"]))
    if run_ids & prior_run_ids or attempt_ids & prior_attempt_ids:
        raise ValueError("attempt identities overlap the rejected series")
    if any(not run_id.startswith(f"{_ATTEMPT_SERIES}-") for run_id in run_ids):
        raise ValueError("attempt schedule series is invalid")
    if any(not attempt_id.startswith(f"{_ATTEMPT_SERIES}-") for attempt_id in attempt_ids):
        raise ValueError("attempt schedule series is invalid")
    oracle = payload["oracle"]
    if oracle is None:
        if require_oracle:
            raise ValueError("source-native oracle is required")
        return
    if not isinstance(oracle, dict):
        raise ValueError("source-native oracle is invalid")
    _require_keys(
        oracle,
        frozenset({"lane", "declaration_sha256", "native_result_set_sha256", "ordered_results"}),
        "source-native oracle",
    )
    if (
        oracle["lane"] != "source-native"
        or oracle["declaration_sha256"] != payload["declaration_sha256"]
    ):
        raise ValueError("source-native oracle is invalid")
    if not _is_sha256(oracle["native_result_set_sha256"]):
        raise ValueError("source-native oracle is invalid")
    results = oracle["ordered_results"]
    native_ids = [entry["run_id"] for entry in schedule if entry["lane"] == "source-native"]
    if (
        not isinstance(results, list)
        or [item.get("run_id") for item in results if isinstance(item, dict)] != native_ids
    ):
        raise ValueError("source-native oracle is invalid")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _reserve_directory(path: Path) -> Path:
    resolved = path.resolve()
    os.mkdir(resolved, 0o700)
    return resolved


def _media_type(path: Path) -> str:
    return "application/json" if path.suffix == ".json" else "text/markdown"


def _seal_inventory(root: Path) -> dict[str, object]:
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
    atomic_write_json_artifact(root / "protocol.json", protocol)
    atomic_write_json_artifact(root / "source-ledger.json", source_ledger)
    bench_notes = _new_bench_notes(protocol)
    _append_bench_note(
        bench_notes,
        protocol,
        phase="declaration",
        severity="info",
        event_code="protocol-declared",
        summary=(
            "The declaration and 20 never-reused attempt identities were written before "
            "experiment effects."
        ),
        disposition="passed",
        evidence_paths=("protocol.json", "source-ledger.json"),
    )
    _write_bench_notes(root, bench_notes)
    _seal_inventory(root)
    return root


def _control_disposition(protocol: Mapping[str, object], lane: str) -> dict[str, object]:
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


def _validate_metric_value(metric: str, value: object) -> None:
    if value is None:
        return
    if metric == "steps_to_termination":
        if type(value) is not int or not 0 <= value <= 600:
            raise ValueError("run metric is invalid")
    elif metric == "cumulative_attacker_reward":
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError("run metric is invalid")
    elif metric == "network_availability":
        if not isinstance(value, list) or not value:
            raise ValueError("run metric is invalid")
        if any(
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(item)
            or not 0.0 <= item <= 1.0
            for item in value
        ):
            raise ValueError("run metric is invalid")
    elif metric == "terminal_cause" and value not in {
        "attacker-ownership",
        "defender-sla",
        "defender-eviction",
        "evaluator-cutoff",
    }:
        raise ValueError("run metric is invalid")


def _validate_terminal_row(row: Mapping[str, object]) -> None:
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


def collect_native(
    declaration_root: Path,
    output: Path,
    *,
    executor: Callable[[], list[dict[str, object]]] | None = None,
) -> Path:
    """Collect the one exact upstream ten-episode batch and freeze its oracle."""

    protocol = load_strict_json(declaration_root / "protocol.json")
    validate_protocol(protocol, require_oracle=False)
    _verify_inventory(declaration_root)
    root = _reserve_directory(output)
    source_ledger = load_strict_json(declaration_root / "source-ledger.json")
    validate_source_ledger(source_ledger, protocol)
    atomic_write_json_artifact(root / "source-ledger.json", source_ledger)
    atomic_write_json_artifact(root / "environment.json", _environment_payload("source-native"))
    bench_notes = _load_bench_notes(declaration_root, protocol)
    _append_bench_note(
        bench_notes,
        protocol,
        phase="native",
        severity="info",
        event_code="native-collection-started",
        summary="The exact admitted upstream ten-episode evaluator batch was started.",
        disposition="observed",
        evidence_paths=("protocol.json", "source-ledger.json", "environment.json"),
    )
    _write_bench_notes(root, bench_notes)
    execute = executor if executor is not None else _execute_native_batch
    try:
        results = execute()
        if len(results) != _ATTEMPTS_PER_LANE:
            raise ValueError("native evaluator returned the wrong episode count")
        native_schedule = [
            entry
            for entry in cast(list[dict[str, object]], protocol["declaration"]["schedule"])  # type: ignore[index]
            if entry["lane"] == "source-native"
        ]
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
    except Exception:
        rows = _failed_rows(protocol, "source-native", "reproduction.native.execution-failed")
        _write_rows(root, rows)
        atomic_write_json_artifact(root / "protocol.json", protocol)
        atomic_write_json_artifact(
            root / "collection.json",
            {"lane": "source-native", "terminal_count": len(rows), "valid_count": 0},
        )
        for row in rows:
            run_id = cast(str, row["run_id"])
            _append_bench_note(
                bench_notes,
                protocol,
                phase="native",
                severity="error",
                event_code="native-attempt-terminalized",
                summary=f"Scheduled source-native attempt {run_id} was terminalized as failed.",
                disposition="failed",
                evidence_paths=(f"runs/{run_id}/record.json",),
            )
        _append_bench_note(
            bench_notes,
            protocol,
            phase="native",
            severity="error",
            event_code="native-collection-failed",
            summary=(
                "The source-native batch failed; all ten scheduled attempts remain retained "
                "as failed."
            ),
            disposition="failed",
            evidence_paths=("protocol.json",),
        )
        _write_bench_notes(root, bench_notes)
        _seal_inventory(root)
        raise RuntimeError("native collection failed") from None
    ordered = [
        {"run_id": row["run_id"], "metrics": row["metrics"]}
        for row in sorted(rows, key=lambda item: cast(int, item["replicate"]))
    ]
    result_set_sha256 = sha256_payload(ordered)
    completed = copy_protocol = json.loads(json.dumps(protocol))
    copy_protocol["oracle"] = {
        "lane": "source-native",
        "declaration_sha256": protocol["declaration_sha256"],
        "native_result_set_sha256": result_set_sha256,
        "ordered_results": ordered,
    }
    validate_protocol(completed, require_oracle=True)
    _write_rows(root, rows)
    atomic_write_json_artifact(root / "protocol.json", completed)
    atomic_write_json_artifact(
        root / "collection.json",
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
            completed,
            phase="native",
            severity="info",
            event_code="native-attempt-terminalized",
            summary=f"Scheduled source-native attempt {run_id} was terminalized as valid.",
            disposition="passed",
            evidence_paths=(f"runs/{run_id}/record.json",),
        )
    _append_bench_note(
        bench_notes,
        completed,
        phase="native",
        severity="info",
        event_code="native-collection-passed",
        summary="The exact upstream evaluator returned all ten scheduled terminal results.",
        disposition="passed",
        evidence_paths=("protocol.json",),
    )
    _write_bench_notes(root, bench_notes)
    _seal_inventory(root)
    return root


def collect_mediated(
    oracle_root: Path,
    pack_root: Path,
    output: Path,
    *,
    runner: Callable[[dict[str, object], Path], dict[str, object]] | None = None,
) -> Path:
    """Collect ten independent RAES-mediated attempts without silent drops."""

    protocol_path = oracle_root / "protocol.json"
    protocol = load_strict_json(protocol_path)
    validate_protocol(protocol, require_oracle=True)
    _verify_inventory(oracle_root)
    protocol_digest = _sha256_file(protocol_path)
    root = _reserve_directory(output)
    atomic_write_json_artifact(root / "protocol.json", protocol)
    atomic_write_json_artifact(root / "environment.json", _environment_payload("raes-mediated"))
    bench_notes = _new_bench_notes(protocol)
    _append_bench_note(
        bench_notes,
        protocol,
        phase="mediated",
        severity="info",
        event_code="mediated-collection-started",
        summary="The ten preallocated RAES-mediated attempts were started with zero retries.",
        disposition="observed",
        evidence_paths=("protocol.json", "environment.json"),
    )
    _write_bench_notes(root, bench_notes)
    runs_root = root / "runs"
    os.mkdir(runs_root, 0o700)
    execute = runner if runner is not None else _execute_mediated_attempt
    schedule = [
        entry
        for entry in cast(list[dict[str, object]], protocol["declaration"]["schedule"])  # type: ignore[index]
        if entry["lane"] == "raes-mediated"
    ]
    rows: list[dict[str, object]] = []
    for scheduled in schedule:
        run_id = cast(str, scheduled["run_id"])
        run_root = runs_root / cast(str, scheduled["run_id"])
        os.mkdir(run_root, 0o700)
        _append_bench_note(
            bench_notes,
            protocol,
            phase="mediated",
            severity="info",
            event_code="mediated-attempt-started",
            summary=f"Scheduled RAES-mediated attempt {run_id} was started.",
            disposition="observed",
            evidence_paths=("protocol.json",),
        )
        _write_bench_notes(root, bench_notes)
        try:
            result = execute({**scheduled, "pack_root": pack_root.as_posix()}, run_root)
            row = _terminal_row(
                protocol,
                scheduled,
                result=result,
                disposition="valid",
                protocol_sha256=protocol_digest,
            )
            _validate_terminal_row(row)
        except Exception:
            row = _terminal_row(
                protocol,
                scheduled,
                result=None,
                disposition="failed",
                protocol_sha256=protocol_digest,
                diagnostic_code="reproduction.mediated.execution-failed",
            )
        atomic_write_json_artifact(run_root / "record.json", row)
        rows.append(row)
        valid = row["disposition"] == "valid"
        _append_bench_note(
            bench_notes,
            protocol,
            phase="mediated",
            severity="info" if valid else "error",
            event_code="mediated-attempt-terminalized",
            summary=(
                f"Scheduled RAES-mediated attempt {run_id} was terminalized as "
                f"{row['disposition']}."
            ),
            disposition="passed" if valid else "failed",
            evidence_paths=(f"runs/{run_id}/record.json",),
        )
        _write_bench_notes(root, bench_notes)
    atomic_write_json_artifact(
        root / "collection.json",
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
        protocol,
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
    metrics = cast(dict[str, object], row["metrics"])
    value = metrics[metric]
    if value is None:
        return None
    if metric == "network_availability":
        return statistics.fmean(cast(list[float], value))
    return float(cast(int | float, value))


def _percentile(values: Sequence[float], probability: float) -> float:
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
    address = f"{declaration_sha256}:{metric}:{lane}:{sample}:{position}".encode()
    return int.from_bytes(hashlib.sha256(address).digest()[:8], "big") % count


def _bootstrap_means(
    values: Sequence[float], declaration_sha256: str, metric: str, lane: str, count: int
) -> list[float]:
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
    lanes: dict[str, object] = {}
    numeric_metrics = _METRICS[:-1]
    lane_values: dict[str, dict[str, list[float]]] = {
        lane: {metric: [] for metric in numeric_metrics} for lane in _LANES
    }
    terminal_values: dict[str, list[str]] = {lane: [] for lane in _LANES}
    for lane in _LANES:
        selected = [row for row in ordered_rows if row["lane"] == lane]
        disposition_counts = {
            disposition: sum(row["disposition"] == disposition for row in selected)
            for disposition in sorted(_DISPOSITIONS)
        }
        metric_payloads: dict[str, object] = {}
        for metric in numeric_metrics:
            values = [
                value
                for row in selected
                if row["disposition"] == "valid"
                and (value := _numeric_value(row, metric)) is not None
            ]
            lane_values[lane][metric] = values
            summary = (
                _numeric_summary(values, declaration_digest, metric, lane, resamples)
                if values
                else {"available_count": 0}
            )
            summary["missing_count"] = len(selected) - len(values)
            metric_payloads[metric] = summary
        causes = [
            cast(str, cast(dict[str, object], row["metrics"])["terminal_cause"])
            for row in selected
            if row["disposition"] == "valid"
            and cast(dict[str, object], row["metrics"])["terminal_cause"] is not None
        ]
        terminal_values[lane] = causes
        categories = sorted(set(causes))
        metric_payloads["terminal_cause"] = {
            "available_count": len(causes),
            "missing_count": len(selected) - len(causes),
            "proportions": {
                category: causes.count(category) / len(causes) for category in categories
            },
        }
        lanes[lane] = {
            "scheduled_count": len(selected),
            "dispositions": disposition_counts,
            "metrics": metric_payloads,
        }
    tolerances = cast(
        dict[str, object], cast(dict[str, object], declaration["comparison"])["bounded"]
    )
    comparisons: dict[str, object] = {}
    for metric in numeric_metrics:
        native = lane_values["source-native"][metric]
        mediated = lane_values["raes-mediated"][metric]
        if len(native) != _ATTEMPTS_PER_LANE or len(mediated) != _ATTEMPTS_PER_LANE:
            comparisons[metric] = {
                "result": "unavailable",
                "mean_difference": None,
                "interval_95": None,
            }
            continue
        native_boot = _bootstrap_means(
            native, declaration_digest, metric, "source-native", resamples
        )
        mediated_boot = _bootstrap_means(
            mediated, declaration_digest, metric, "raes-mediated", resamples
        )
        numeric_differences = [
            right - left for left, right in zip(native_boot, mediated_boot, strict=True)
        ]
        interval = {
            "lower": _percentile(numeric_differences, 0.025),
            "upper": _percentile(numeric_differences, 0.975),
        }
        tolerance_value = tolerances[metric]
        if not isinstance(tolerance_value, (int, float)) or isinstance(tolerance_value, bool):
            raise ValueError("comparison tolerance is invalid")
        tolerance = float(tolerance_value)
        exact = native == mediated
        bounded = interval["lower"] >= -tolerance and interval["upper"] <= tolerance
        comparisons[metric] = {
            "result": "exact" if exact else "bounded" if bounded else "outside-tolerance",
            "mean_difference": statistics.fmean(mediated) - statistics.fmean(native),
            "interval_95": interval,
            "tolerance": tolerance,
        }
    native_causes = terminal_values["source-native"]
    mediated_causes = terminal_values["raes-mediated"]
    if len(native_causes) != _ATTEMPTS_PER_LANE or len(mediated_causes) != _ATTEMPTS_PER_LANE:
        comparisons["terminal_cause"] = {"result": "unavailable", "proportion_differences": None}
    else:
        categories = sorted(set(native_causes) | set(mediated_causes))
        cause_differences = {
            category: mediated_causes.count(category) / len(mediated_causes)
            - native_causes.count(category) / len(native_causes)
            for category in categories
        }
        tolerance_value = tolerances["terminal_cause"]
        if not isinstance(tolerance_value, (int, float)) or isinstance(tolerance_value, bool):
            raise ValueError("comparison tolerance is invalid")
        tolerance = float(tolerance_value)
        comparisons["terminal_cause"] = {
            "result": (
                "exact"
                if native_causes == mediated_causes
                else "bounded"
                if all(abs(value) <= tolerance for value in cause_differences.values())
                else "outside-tolerance"
            ),
            "proportion_differences": cause_differences,
            "tolerance": tolerance,
        }
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
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _installed_source_artifact_sha256() -> str:
    """Return only the installed wheel digest, never its local URL."""

    try:
        distribution = importlib.metadata.distribution("cyberbattlesim")
        direct_text = distribution.read_text("direct_url.json")
        if direct_text is None:
            return "unavailable"
        direct = json.loads(direct_text)
        if not isinstance(direct, dict):
            return "unavailable"
        archive = direct.get("archive_info")
        if not isinstance(archive, dict):
            return "unavailable"
        digest = archive.get("hash")
        if isinstance(digest, str) and digest.startswith("sha256=") and _is_sha256(digest[7:]):
            return digest[7:]
        hashes = archive.get("hashes")
        if isinstance(hashes, dict) and _is_sha256(hashes.get("sha256")):
            return cast(str, hashes["sha256"])
    except (
        importlib.metadata.PackageNotFoundError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        pass
    return "unavailable"


def _physical_memory_bytes() -> int | None:
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (OSError, ValueError):
        return None


def _environment_payload(lane: str) -> dict[str, object]:
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
                "The mediated evaluator does not retain availability series or a specific "
                "terminal cause."
            ),
        ],
    }


def _validate_lane_environment(payload: Mapping[str, object], lane: str) -> None:
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
        raise RuntimeError("native evaluator returned an unsupported result")
    rewards = result.get("all_episodes_rewards")
    availability = result.get("all_episodes_availability")
    if not isinstance(rewards, list) or not isinstance(availability, list):
        raise RuntimeError("native evaluator returned an unsupported result")
    if len(rewards) != _ATTEMPTS_PER_LANE or len(availability) != _ATTEMPTS_PER_LANE:
        raise RuntimeError("native evaluator returned an unsupported result")
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
    if not rewards or len(rewards) != len(availability):
        return None
    last_reward = rewards[-1]
    last_availability = availability[-1]
    if last_reward == 5000.0:
        return "defender-sla" if last_availability < 0.8 else "attacker-ownership"
    if len(rewards) < maximum_steps and last_reward == 0.0:
        return "defender-eviction"
    if len(rewards) == maximum_steps and last_reward != 5000.0:
        return "evaluator-cutoff"
    return None


def _execute_native_batch() -> list[dict[str, object]]:
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
            raise RuntimeError("native evaluator returned an unsupported result")
        results: list[dict[str, object]] = []
        for episode in episodes:
            if not isinstance(episode, dict) or set(episode) != {"rewards", "availability"}:
                raise RuntimeError("native evaluator returned an unsupported result")
            rewards = episode["rewards"]
            availability = episode["availability"]
            if not isinstance(rewards, list) or not isinstance(availability, list):
                raise RuntimeError("native evaluator returned an unsupported result")
            if len(rewards) != len(availability) or not 1 <= len(rewards) <= 600:
                raise RuntimeError("native evaluator returned an unsupported result")
            numeric_rewards = [float(value) for value in rewards]
            numeric_availability = [float(value) for value in availability]
            if any(not math.isfinite(value) for value in numeric_rewards):
                raise RuntimeError("native evaluator returned an unsupported result")
            if any(
                not math.isfinite(value) or not 0.0 <= value <= 1.0
                for value in numeric_availability
            ):
                raise RuntimeError("native evaluator returned an unsupported result")
            results.append(
                {
                    "steps_to_termination": len(numeric_rewards),
                    "cumulative_attacker_reward": math.fsum(numeric_rewards),
                    "network_availability": numeric_availability,
                    "terminal_cause": _terminal_cause(numeric_rewards, numeric_availability, 600),
                    "cleanup_verified": payload["cleanup_verified"] is True,
                    "evidence_refs": [],
                }
            )
        return results


def _execute_mediated_attempt(schedule: dict[str, object], run_root: Path) -> dict[str, object]:
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
    derived = _load_strict_value(derived_path)
    if not isinstance(derived, list) or len(derived) != 1 or not isinstance(derived[0], dict):
        raise RuntimeError("mediated evidence is invalid")
    reward = derived[0].get("value")
    steps = run_summary.get("completed_steps")
    if type(steps) is not int or not isinstance(reward, (int, float)) or isinstance(reward, bool):
        raise RuntimeError("mediated evidence is invalid")
    if not math.isfinite(float(reward)) or summary.get("disposition") != "succeeded":
        raise RuntimeError("mediated evidence is invalid")
    evidence_paths = (
        portable / "runs" / f"{run_id}-1" / "run.json",
        portable / "runs" / f"{run_id}-1" / "evidence-records.json",
        derived_path,
        portable / _INVENTORY_NAME,
    )
    return {
        "steps_to_termination": steps,
        "cumulative_attacker_reward": float(reward),
        "network_availability": None,
        "terminal_cause": None,
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
    recorded = load_strict_json(root / _INVENTORY_NAME)
    if recorded != _inventory_payload(root):
        raise ValueError("artifact inventory is invalid")


def _combined_environment(native_root: Path, mediated_root: Path) -> dict[str, object]:
    native = load_strict_json(native_root / "environment.json")
    mediated = load_strict_json(mediated_root / "environment.json")
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
    return {"path": path, "sha256": digests[path], "json_pointer": pointer}


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
    outcome_result = (
        "failed"
        if "outside-tolerance" in comparison_results
        else "weakened"
        if "unavailable" in comparison_results
        else "passed"
    )
    limitations = environment.get("limitations")
    disclosure_result = "passed" if isinstance(limitations, list) and limitations else "failed"
    tier_rows = [
        {
            "tier": "authored-source",
            "result": authored_result,
            "rationale": "Pinned source, tree, notebook, and runtime-tree identities join.",
            "evidence": [_citation("source-ledger.json", "/source", digests)],
        },
        {
            "tier": "contract",
            "result": "passed",
            "rationale": (
                "The declaration embeds a validated RAES study over the published task/spec refs."
            ),
            "evidence": [_citation("protocol.json", "/declaration/study", digests)],
        },
        {
            "tier": "execution-control",
            "result": execution_result,
            "rationale": "Actual random-stream binding dispositions differ between lanes.",
            "evidence": [_citation("protocol.json", "/declaration/stochastic_controls", digests)],
        },
        {
            "tier": "state-observation",
            "result": state_result,
            "rationale": (
                "The authored RAES topology is representative and native observations "
                "remain private."
            ),
            "evidence": [_citation("source-ledger.json", "/loss_refs", digests)],
        },
        {
            "tier": "outcome-evaluation",
            "result": outcome_result,
            "rationale": "Only complete predeclared metric comparisons can pass this tier.",
            "evidence": [_citation("aggregates.json", "/comparisons", digests)],
        },
        {
            "tier": "disclosure",
            "result": disclosure_result,
            "rationale": (
                "Known apparatus, source, stochastic, topology, and metric losses are retained."
            ),
            "evidence": [
                _citation("source-ledger.json", "/exclusions", digests),
                _citation("environment.json", "/limitations", digests),
                _citation("bench-notes.json", "/notes", digests),
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
    digest_paths = (
        "protocol.json",
        "source-ledger.json",
        "environment.json",
        "aggregates.json",
        "bench-notes.json",
    )
    digests = {name: _sha256_file(root / name) for name in digest_paths}
    tiers = compute_tiers(protocol, source_ledger, environment, aggregates, digests)
    atomic_write_json_artifact(root / "tiers.json", tiers)


def finalize_bundle(oracle_root: Path, mediated_root: Path, output: Path) -> Path:
    """Assemble and seal the accepted bundle exactly once."""

    _verify_inventory(oracle_root)
    _verify_inventory(mediated_root)
    oracle_protocol_path = oracle_root / "protocol.json"
    mediated_protocol_path = mediated_root / "protocol.json"
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
    oracle_notes = _load_bench_notes(oracle_root, protocol)
    mediated_notes = _load_bench_notes(mediated_root, protocol)
    combined_notes = sorted(
        cast(list[dict[str, object]], oracle_notes["notes"])
        + cast(list[dict[str, object]], mediated_notes["notes"]),
        key=lambda note: (cast(str, note["recorded_at"]), cast(str, note["note_id"])),
    )
    bench_notes = _new_bench_notes(protocol, combined_notes)
    _validate_bench_notes(bench_notes, protocol)
    root = _reserve_directory(output)
    atomic_write_json_artifact(root / "protocol.json", protocol)
    source_ledger = load_strict_json(oracle_root / "source-ledger.json")
    validate_source_ledger(source_ledger, protocol)
    atomic_write_json_artifact(root / "source-ledger.json", source_ledger)
    environment = _combined_environment(oracle_root, mediated_root)
    atomic_write_json_artifact(root / "environment.json", environment)
    _append_bench_note(
        bench_notes,
        protocol,
        phase="finalize",
        severity="info",
        event_code="bundle-finalization-started",
        summary="Assembly of the content-addressed public bundle was started.",
        disposition="observed",
        evidence_paths=("protocol.json", "source-ledger.json", "environment.json"),
    )
    _write_bench_notes(root, bench_notes)
    runs_root = root / "runs"
    os.mkdir(runs_root, 0o700)
    for stage in (oracle_root, mediated_root):
        for run in sorted((stage / "runs").iterdir()):
            shutil.copytree(run, runs_root / run.name)
    aggregates = compute_aggregates(protocol, rows)
    atomic_write_json_artifact(root / "aggregates.json", aggregates)
    revision_value = protocol["declaration_sha256"]
    if not isinstance(revision_value, str):
        raise ValueError("protocol declaration digest is invalid")
    revision = revision_value
    (root / "validation-report.md").write_text(
        _validation_report(revision), encoding="utf-8", newline="\n"
    )
    _append_bench_note(
        bench_notes,
        protocol,
        phase="finalize",
        severity="info",
        event_code="bundle-finalized",
        summary="All declared runs and derived public artifacts were assembled without drops.",
        disposition="passed",
        evidence_paths=("aggregates.json", "validation-report.md"),
    )
    _append_bench_note(
        bench_notes,
        protocol,
        phase="verify",
        severity="info",
        event_code="offline-verification-started",
        summary="Pure offline recomputation and integrity verification were started.",
        disposition="observed",
        evidence_paths=("protocol.json", "aggregates.json"),
    )
    _write_bench_notes(root, bench_notes)
    _write_tier_projection(root, protocol, source_ledger, environment, aggregates)
    _scan_portable(root)
    _seal_inventory(root)
    try:
        verify_bundle(root)
    except Exception:
        _append_bench_note(
            bench_notes,
            protocol,
            phase="verify",
            severity="error",
            event_code="offline-verification-failed",
            summary="Pure offline recomputation or integrity verification failed.",
            disposition="failed",
            evidence_paths=("inventory.json",),
        )
        _write_bench_notes(root, bench_notes)
        _write_tier_projection(root, protocol, source_ledger, environment, aggregates)
        _seal_inventory(root)
        raise RuntimeError("final bundle offline verification failed") from None
    _append_bench_note(
        bench_notes,
        protocol,
        phase="verify",
        severity="info",
        event_code="offline-verification-passed",
        summary="Pure offline recomputation and integrity verification passed.",
        disposition="passed",
        evidence_paths=("inventory.json", "aggregates.json", "tiers.json"),
    )
    _write_bench_notes(root, bench_notes)
    _write_tier_projection(root, protocol, source_ledger, environment, aggregates)
    _scan_portable(root)
    _seal_inventory(root)
    try:
        verify_bundle(root)
    except Exception:
        _append_bench_note(
            bench_notes,
            protocol,
            phase="verify",
            severity="error",
            event_code="offline-verification-failed",
            summary="The final note-bound bundle failed its second integrity verification.",
            disposition="failed",
            evidence_paths=("inventory.json",),
        )
        _write_bench_notes(root, bench_notes)
        _write_tier_projection(root, protocol, source_ledger, environment, aggregates)
        _seal_inventory(root)
        raise RuntimeError("final bundle offline verification failed") from None
    return root


def _resolve_pointer(document: object, pointer: str) -> object:
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


def _scan_portable(root: Path) -> None:
    def contains_native_field_name(value: str) -> bool:
        folded = value.casefold()
        return any(name.casefold() in folded for name in _FORBIDDEN_NATIVE_FIELD_NAMES)

    def scan_json_value(value: object, *, withheld_ref: bool = False) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if contains_native_field_name(key):
                    raise ValueError("portable artifact contains a forbidden native value")
                scan_json_value(child, withheld_ref=key == "withheld_refs")
        elif isinstance(value, list):
            for child in value:
                scan_json_value(child, withheld_ref=withheld_ref)
        elif isinstance(value, str) and not withheld_ref and contains_native_field_name(value):
            raise ValueError("portable artifact contains a forbidden native value")

    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        content = path.read_bytes()
        if len(content) > 500 * 1024:
            raise ValueError("portable artifact exceeds the repository size limit")
        text = content.decode("utf-8", errors="ignore")
        if any(token.casefold() in text.casefold() for token in _FORBIDDEN_PORTABLE_TOKENS):
            raise ValueError("portable artifact contains a forbidden native value")
        if path.suffix == ".json":
            scan_json_value(_load_strict_value(path))
        elif contains_native_field_name(text):
            raise ValueError("portable artifact contains a forbidden native value")
        if any(prefix in text for prefix in ("/home/", "/tmp/", "file:///home/", "file:///tmp/")):
            raise ValueError("portable artifact contains a host path")


def _validate_model_list(path: Path, model: type[object]) -> None:
    payload = _load_strict_value(path)
    if not isinstance(payload, list):
        raise ValueError("portable RAES model collection is invalid")
    validator = getattr(model, "model_validate", None)
    if not callable(validator):
        raise ValueError("portable RAES model validator is unavailable")
    for item in payload:
        validator(item)


def _validate_mediated_portable(run_root: Path, run_id: str) -> None:
    portable = run_root / "portable"
    archival = portable / "runs" / f"{run_id}-1"
    ExperimentRunModel.model_validate(load_strict_json(archival / "run.json"))
    ParticipantImplementationProvenanceModel.model_validate(
        load_strict_json(archival / "participant-provenance.json")
    )
    _validate_model_list(archival / "evidence-records.json", ExperimentEvidenceRecordModel)
    _validate_model_list(archival / "derived-measures.json", ExperimentDerivedMeasureModel)
    _validate_model_list(archival / "diagnostics.json", DiagnosticModel)
    _verify_inventory(portable)


def verify_bundle(root: Path) -> dict[str, object]:
    """Verify and recompute a sealed bundle without importing native source."""

    root = root.resolve()
    protocol = load_strict_json(root / "protocol.json")
    validate_protocol(protocol, require_oracle=True)
    source_ledger = load_strict_json(root / "source-ledger.json")
    validate_source_ledger(source_ledger, protocol)
    environment = load_strict_json(root / "environment.json")
    _validate_combined_environment(environment)
    bench_notes = _load_bench_notes(root, protocol)
    notes = cast(list[dict[str, object]], bench_notes["notes"])
    for note in notes:
        for ref in cast(list[dict[str, object]], note["evidence_refs"]):
            target = (root / _safe_relative_path(ref["path"])).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError("bench note evidence reference is unresolved")
    rows = load_terminal_rows(root)
    _assert_stage_rows(protocol, rows)
    protocol_digest = _sha256_file(root / "protocol.json")
    for row in rows:
        if row["declaration_sha256"] != protocol["declaration_sha256"]:
            raise ValueError("terminal row declaration binding is invalid")
        if row["lane"] == "raes-mediated" and row["protocol_sha256"] != protocol_digest:
            raise ValueError("mediated terminal row protocol binding is invalid")
        run_root = root / "runs" / cast(str, row["run_id"])
        if row["lane"] == "raes-mediated" and row["disposition"] == "valid":
            _validate_mediated_portable(run_root, cast(str, row["run_id"]))
        refs = row["evidence_refs"]
        if not isinstance(refs, list):
            raise ValueError("terminal row evidence references are invalid")
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
                raise ValueError("terminal row evidence references are invalid")
            relative = _safe_relative_path(ref["path"])
            target = (run_root / relative).resolve()
            if not target.is_relative_to(run_root.resolve()) or not target.is_file():
                raise ValueError("terminal row evidence reference is unresolved")
            if _sha256_file(target) != ref["sha256"]:
                raise ValueError("terminal row evidence digest is invalid")
    native_rows = sorted(
        (row for row in rows if row["lane"] == "source-native"),
        key=lambda item: cast(int, item["replicate"]),
    )
    oracle_rows = [{"run_id": row["run_id"], "metrics": row["metrics"]} for row in native_rows]
    oracle = cast(dict[str, object], protocol["oracle"])
    if sha256_payload(oracle_rows) != oracle["native_result_set_sha256"]:
        raise ValueError("source-native oracle digest is invalid")
    recorded_aggregates = load_strict_json(root / "aggregates.json")
    expected_aggregates = compute_aggregates(protocol, rows)
    if canonical_json_bytes(recorded_aggregates) != canonical_json_bytes(expected_aggregates):
        raise ValueError("aggregate recomputation failed")
    digests = {
        name: _sha256_file(root / name)
        for name in (
            "protocol.json",
            "source-ledger.json",
            "environment.json",
            "aggregates.json",
            "bench-notes.json",
        )
    }
    recorded_tiers = load_strict_json(root / "tiers.json")
    expected_tiers = compute_tiers(
        protocol, source_ledger, environment, recorded_aggregates, digests
    )
    if canonical_json_bytes(recorded_tiers) != canonical_json_bytes(expected_tiers):
        raise ValueError("tier recomputation failed")
    tiers = recorded_tiers.get("tiers")
    if not isinstance(tiers, list) or [
        item.get("tier") for item in tiers if isinstance(item, dict)
    ] != list(_TIERS):
        raise ValueError("tier inventory is invalid")
    for tier in tiers:
        if not isinstance(tier, dict) or tier.get("result") not in {"passed", "failed", "weakened"}:
            raise ValueError("tier inventory is invalid")
        evidence = tier.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("tier evidence is invalid")
        for citation in evidence:
            if not isinstance(citation, dict) or set(citation) != {
                "path",
                "sha256",
                "json_pointer",
            }:
                raise ValueError("tier evidence is invalid")
            relative = _safe_relative_path(citation["path"])
            target = root / relative
            if not target.is_file() or _sha256_file(target) != citation["sha256"]:
                raise ValueError("tier evidence digest is invalid")
            _resolve_pointer(load_strict_json(target), cast(str, citation["json_pointer"]))
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
