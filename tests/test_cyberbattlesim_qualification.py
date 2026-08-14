"""Qualification evidence for the selected public CyberBattleSim case."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import pytest
import yaml

import raes_adapters.cyberbattlesim as cyberbattlesim

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_resources_select_one_immutable_source_and_protocol() -> None:
    record = cyberbattlesim.load_qualification()
    protocol = cyberbattlesim.read_public_protocol()

    assert cyberbattlesim.__all__ == ["load_qualification", "read_public_protocol"]
    assert record["source"] == {
        "repository": "https://github.com/microsoft/CyberBattleSim",
        "commit": "854d6966607fb68645651f55b0f97221bd293e0d",
        "tree": "4271b137ab2de593be52d7afb0a51bee59045a45",
        "archive_sha256": "31c8ead1f75262b3a91146f2ccbb3d7753618751bb6efa971530ed3f573eef4c",
        "package": "cyberbattlesim",
        "version": "0.1.0",
    }
    assert "# CyberBattleSim public experiment protocol" in protocol
    assert "`CyberBattleChain-v0`" in protocol
    assert "`CredentialCacheExploiter`" in protocol
    assert hashlib.sha256(protocol.encode("utf-8")).hexdigest() == record["protocol"]["sha256"]


def test_researcher_pack_is_external_and_validator_is_installed() -> None:
    """The release pack is repository content, never a Python package resource."""

    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra = project["project"]["optional-dependencies"]["cyberbattlesim"]
    pack = REPO_ROOT / "environments" / "cyberbattlesim-chain"

    assert extra == ["raes-env-packs==3.6.2"]
    assert (pack / "pack.yaml").is_file()
    assert (pack / "pack.compatibility.yaml").is_file()
    assert (pack / "docs" / "golden-readiness-checklist.md").is_file()
    assert "environments" not in project["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]


def test_external_pack_mirrors_the_installed_selected_contracts() -> None:
    """The release asset cannot drift from the adapter's qualified selection."""

    pack = REPO_ROOT / "environments" / "cyberbattlesim-chain"
    package = REPO_ROOT / "src" / "raes_adapters" / "cyberbattlesim"
    assert (pack / "sdl" / "cyberbattlesim-chain.sdl.yaml").read_bytes() == (
        package / "scenario" / "cyberbattle-chain.sdl.yaml"
    ).read_bytes()
    for stem in ("spec", "task"):
        external = json.loads(
            (pack / "experiment" / f"cyberbattlesim-chain.{stem}.exp.json").read_text()
        )
        installed = yaml.safe_load(
            (package / "experiment" / f"cyberbattle-chain.{stem}.exp.yaml").read_text()
        )
        if stem == "spec":
            participant_artifacts = external.pop("artifact_refs")
            assert {item["role"] for item in participant_artifacts} == {
                "manifest",
                "configuration",
            }
            external["intended_scenario_ref"]["ref_path"] = "scenario/cyberbattle-chain.sdl.yaml"
        else:
            external["scenario_ref"]["ref_path"] = "scenario/cyberbattle-chain.sdl.yaml"
        assert external == installed


def test_external_pack_content_manifest_is_exact_and_immutable() -> None:
    derive_pack_content_manifest = pytest.importorskip(
        "raes_env_packs"
    ).derive_pack_content_manifest

    pack = REPO_ROOT / "environments" / "cyberbattlesim-chain"
    recorded = json.loads((pack / "pack.content-manifest.json").read_text())
    derived = derive_pack_content_manifest(pack).model_dump(mode="json")
    assert recorded == derived
    assert recorded["set_digest"] == (
        "sha256:66493882579d5cba87248c5722782ff5ded5f0d7423f4e559f15bfb61712a905"
    )


def test_clean_install_and_source_native_smoke_are_bounded_and_complete() -> None:
    record = cyberbattlesim.load_qualification()
    runtime = record["runtime"]
    smoke = runtime["smoke"]

    assert runtime["python"] == "3.12.3"
    assert runtime["wheel_sha256"] == (
        "6e5f855a999ccfcb93f643dda9cbf7ac679640c67df246f4750c344acf2e2138"
    )
    assert runtime["clean_install"] == "passed"
    assert smoke["reset_arity"] == 2
    assert smoke["step_arity"] == 5
    assert smoke["representative_step"] == {
        "reward": 14.0,
        "terminated": False,
        "truncated": False,
        "step_count": 1,
    }
    assert smoke["termination_probe"] == {
        "reward": 5000.0,
        "terminated": True,
        "truncated": False,
        "step_count": 1,
        "post_done_guard": True,
    }
    assert "_explored_nodes" not in smoke
    assert "credential_cache" not in smoke


def test_runtime_artifact_attestation_covers_complete_import_roots() -> None:
    record = cyberbattlesim.load_qualification()
    runtime_tree = record["runtime_source_tree"]

    assert runtime_tree == {
        "root": "cyberbattle",
        "include": "all regular files; symlinks and unlisted files are rejected",
        "file_count": 48,
        "canonicalization": ("Sorted POSIX path, NUL, lowercase SHA-256 of raw file bytes, LF."),
        "sha256": "1b8bf39a7cb9c172b51b5223dfac13b9d01e166b34dc2bb29297cddb254a06fe",
    }
    source_files = {entry["path"]: entry["sha256"] for entry in record["source_files"]}
    assert source_files["cyberbattle/__init__.py"] == (
        "146a6297d4361b7cd550e293e050c98b6795c4fc5416a1e72f62a8dc142668c4"
    )
    artifacts = {artifact["name"]: artifact for artifact in record["runtime_artifacts"]}
    assert set(artifacts) == {"cyberbattlesim", "gymnasium", "numpy"}
    assert artifacts["cyberbattlesim"]["roots"] == [
        {
            "path": "cyberbattle",
            "file_count": 48,
            "sha256": ("1b8bf39a7cb9c172b51b5223dfac13b9d01e166b34dc2bb29297cddb254a06fe"),
        }
    ]
    assert artifacts["gymnasium"]["artifact"]["sha256"] == (
        "61c3384b5575985bb7f85e43213bcb40f36fcdff388cae6bc229304c71f2843e"
    )
    assert artifacts["cyberbattlesim"]["artifact"]["require_direct_archive_sha256"] is False
    assert artifacts["gymnasium"]["artifact"]["require_direct_archive_sha256"] is True
    assert artifacts["numpy"]["artifact"]["require_direct_archive_sha256"] is True
    assert {artifact["artifact"]["runtime_identity"] for artifact in artifacts.values()} == {
        "complete-root-tree"
    }
    assert {root["path"] for root in artifacts["numpy"]["roots"]} == {
        "numpy",
        "numpy.libs",
    }


def test_protocol_fixes_every_identity_and_discloses_random_streams() -> None:
    record = cyberbattlesim.load_qualification()
    selection = record["protocol"]["selection"]

    assert selection["scenario"] == {
        "gym_id": "CyberBattleChain-v0",
        "size": 10,
        "source_path": "cyberbattle/samples/chainpattern/chainpattern.py",
    }
    assert selection["attacker"] == {
        "policy": "CredentialCacheExploiter",
        "episode_count": 10,
        "iteration_count": 600,
        "epsilon": 0.90,
        "epsilon_exponential_decay": 10000,
        "epsilon_minimum": 0.10,
        "environment_bounds": {
            "maximum_total_credentials": 22,
            "maximum_node_count": 22,
        },
    }
    assert selection["defender"] == {
        "policy": "ScanAndReimageCompromisedMachines",
        "probability": 0.6,
        "scan_capacity": 2,
        "scan_frequency": 5,
    }
    assert selection["termination"] == {
        "attacker_own_atleast": 0,
        "attacker_own_atleast_percent": 1.0,
        "defender_maintain_sla": 0.80,
        "evaluator_cutoff_steps": 600,
    }
    assert {stream["owner"] for stream in record["stochastic_sources"]} == {
        "gym-environment",
        "gym-action-space",
        "python-random",
        "numpy-global",
    }


def test_legal_maintenance_and_patch_dispositions_are_explicit() -> None:
    record = cyberbattlesim.load_qualification()

    assert record["legal"]["upstream_license"] == "MIT"
    assert record["legal"]["notice_required"] is True
    assert record["legal"]["redistribution"] == "permitted-with-notices"
    assert record["legal"]["retained_output"] == "permitted"
    assert record["legal"]["external_downloads"] == []
    assert record["legal"]["model_weights"] == []
    assert record["patches"] == []
    assert record["maintenance"]["archived"] is False
    assert record["maintenance"]["latest_commit"] == ("854d6966607fb68645651f55b0f97221bd293e0d")
    assert record["dependencies"]
    assert all(
        {"name", "version", "license"} <= dependency.keys() for dependency in record["dependencies"]
    )


def test_qualification_admits_selected_backend_and_bounds_claim_strength() -> None:
    record = cyberbattlesim.load_qualification()
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]

    assert record["admission"]["decision"] == "admitted"
    assert record["admission"]["authority"] == "maintainer-selection"
    assert set(record["admission"]["limitations"]) == {
        "no-index-or-release-artifact",
        "incomplete-random-stream-binding",
        "unresolved-upstream-benchmark-defects",
    }
    assert record["admission"]["claim_strength"] == {
        "source_identity": "attested",
        "protocol_configuration": "attested",
        "execution_controls": "partial",
        "run_evidence": "attestable",
        "outcome_reproduction": "stochastic-bounded",
    }
    assert extras["cyberbattlesim"] == ["raes-env-packs==3.6.2"]
    assert extras["cyborg"] == ["raes-env-packs==3.6.2"]
