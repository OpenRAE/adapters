"""Repository-wide capability and evidence-claim integrity checks."""

from __future__ import annotations

import ast
import json
from importlib import resources
from pathlib import Path
from types import SimpleNamespace

import pytest
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_contracts.contracts import ExperimentTaskModel

from raes_adapters import _conformance_support, cli
from raes_adapters.primaite.backend.manifest import create_primaite_manifest

REPO_ROOT = Path(__file__).parents[1]

_TASKS = {
    "cyborg-cage2": (
        "raes_adapters.cyborg",
        "examples/cage2-research/experiment/cage2-research.task.exp.json",
    ),
    "nasim-tiny": (
        "raes_adapters.nasim",
        "examples/nasim-tiny/experiment/nasim-tiny.task.exp.json",
    ),
    "cyberbattlesim-chain": (
        "raes_adapters.cyberbattlesim",
        "experiment/cyberbattle-chain.task.exp.yaml",
    ),
    "primaite": (
        "raes_adapters.primaite",
        "experiment/data-manipulation.task.exp.yaml",
    ),
}

_MANIFESTS = {
    **{name: adapter.backend_manifest for name, adapter in cli._BACKENDS.items()},
    "primaite": create_primaite_manifest,
}

_RETIRED_EXACT_IDENTIFIERS = frozenset(
    {
        "_CAPABILITY_PROBE_REQUIREMENTS",
        "evidence_satisfies_refs",
        "standard_probe_requirements",
        "standard_cleanup_capabilities",
        "standard_evaluator_capabilities",
        "standard_orchestrator_capabilities",
    }
)


class _PortableModel:
    """Small JSON-ready model used at the artifact-writing boundary."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return self._payload


def _task(backend: str) -> ExperimentTaskModel:
    package, relative = _TASKS[backend]
    source = resources.files(package).joinpath(relative).read_text(encoding="utf-8")
    if relative.endswith(".json"):
        return ExperimentTaskModel.model_validate_json(source)
    import yaml

    return ExperimentTaskModel.model_validate(yaml.safe_load(source))


def _identifier_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names.update(node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute))
    names.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    )
    return names


def _retired_static_claim_gate_identifiers(names: set[str]) -> list[str]:
    """Return retired exact names and the entire manifest-evidence helper family."""

    return sorted(
        name
        for name in names
        if name in _RETIRED_EXACT_IDENTIFIERS or "manifest_capability_evidence" in name
    )


@pytest.mark.parametrize(
    "data_quality",
    ("available", "missing", "unavailable", "redacted", "withheld", "lossy"),
)
def test_evaluator_summary_artifact_makes_no_semantic_satisfaction_claim(
    tmp_path: Path,
    data_quality: str,
) -> None:
    run_ref = SimpleNamespace(ref_id="run.claim-integrity")
    record = SimpleNamespace(
        captured_at="2026-08-12T00:00:00Z",
        run_ref=run_ref,
        model_dump=lambda *, mode: {
            "schema_version": "experiment-evidence-record/v1",
            "run_ref": {"ref_kind": "experiment-run", "ref_id": run_ref.ref_id},
            "test_data_quality": data_quality,
        },
    )
    result = SimpleNamespace(
        evidence_records=(record,),
        derived_measures=(),
        diagnostics=(),
    )
    provenance = _PortableModel({"schema_version": "participant-implementation-provenance/v1"})
    adapter = SimpleNamespace(
        episode_provenance=lambda _run_id, _selection: provenance,
        evidence_source_label="bounded evaluator summary",
    )
    admitted = SimpleNamespace(participant_selection=object())

    artifact = cli._write_episode_evidence(
        adapter,
        tmp_path,
        run_ref.ref_id,
        1,
        result,
        admitted,
    )

    assert artifact.satisfies_refs == []
    assert json.loads((tmp_path / "evidence-records.json").read_text())


@pytest.mark.parametrize("backend", sorted(_TASKS))
def test_current_semantic_evidence_requirements_fail_closed_before_execution(
    backend: str,
) -> None:
    assert set(cli._BACKENDS) <= set(_TASKS)
    gaps = cli._task_capture_admission_gaps(_task(backend), _MANIFESTS[backend]())

    assert gaps
    assert set(gaps) >= {
        requirement.ref_id
        for requirement in _task(backend).evaluation_protocol.observation_requirements
    }


@pytest.mark.parametrize("backend", sorted(_TASKS))
def test_every_affirmative_manifest_leaf_is_an_unresolved_inventory_gap(backend: str) -> None:
    manifest = _MANIFESTS[backend]()
    payload = backend_manifest_payload(manifest)
    affirmative = _conformance_support.affirmative_capability_pointers(payload)

    assert affirmative
    assert _conformance_support.manifest_capability_gaps(payload) == affirmative

    capabilities = payload["capabilities"]
    assert isinstance(capabilities, dict)
    provisioner = capabilities["provisioner"]
    assert isinstance(provisioner, dict)
    provisioner["supports_new_mode"] = True
    assert "/capabilities/provisioner/supports_new_mode" in (
        _conformance_support.manifest_capability_gaps(payload)
    )


def test_source_tree_contains_no_retired_static_claim_gate_identifiers() -> None:
    offenders: dict[str, list[str]] = {}
    for path in sorted((REPO_ROOT / "src" / "raes_adapters").rglob("*.py")):
        retired = _retired_static_claim_gate_identifiers(_identifier_names(path))
        if retired:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = retired

    assert offenders == {}


@pytest.mark.parametrize(
    "identifier",
    (
        "manifest_capability_evidence",
        "manifest_capability_evidence_gaps",
        "cyborg_manifest_capability_evidence",
        "cyborg_manifest_capability_evidence_gaps",
    ),
)
def test_retired_manifest_evidence_helper_family_is_closed(identifier: str) -> None:
    assert _retired_static_claim_gate_identifiers({identifier}) == [identifier]
