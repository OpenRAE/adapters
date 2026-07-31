"""Qualification evidence for the selected CybORG/CAGE-2 backend profile."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import raes_adapters.cyborg as cyborg

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_resources_bind_one_immutable_cage2_source_closure() -> None:
    record = cyborg.load_qualification()

    assert {
        "CyborgProvisioner",
        "SourceInstalledCyborgDriver",
        "create_cyborg_manifest",
        "create_cyborg_target",
        "load_qualification",
        "read_compatibility_patch",
    } <= set(cyborg.__all__)
    assert record["profile_id"] == "cage2-cyborg-2.1-source-26ce1c1"
    assert record["source"] == {
        "repository": "https://github.com/cage-challenge/cage-challenge-2",
        "commit": "26ce1c1253fa9e2e73f25e6a7f2da32860c11257",
        "tree": "f2ed32db4ac93500659d6e320e898c83e544e1c6",
        "cyborg_tree": "a125e32fb9b7392ae2ac1b94485f53570298974a",
        "package_tree": "b4180d2be22baf79e16a84bd375e03c2d42565c9",
        "archive_sha256": "b1127d8f77ddf8f69ec6ebc21691ae8484e7040e71704493ad20d81a2b280d1a",
        "package": "CybORG",
        "version": "2.1",
    }
    selected = {item["path"]: item["sha256"] for item in record["selected_files"]}
    assert selected["CybORG/CybORG/Shared/Scenarios/Scenario2.yaml"] == (
        "c2f15ec1bd9ab94d2a44acadf6cb9a71acdcb4cbb8fc946129c832139b155b1b"
    )
    assert selected["CybORG/CybORG/Evaluation/evaluation.py"] == (
        "e4980dea8f1243ffda44bbae92521fc79ce89e74183623cce4d21715b940d51c"
    )
    assert selected["CybORG/CybORG/Agents/Wrappers/ChallengeWrapper.py"] == (
        "61ff99c786c63613c8db2a908c43a5e2835bff9c0fd760a6d1064cc5eb37102c"
    )
    assert selected["README.md"] == (
        "f48bc9ec73a59b401da77806a68c18c06b86428d116bc226ece8d5d8831fb754"
    )
    scenario_images = {
        path for path in selected if path.startswith("CybORG/CybORG/Shared/Scenarios/images/")
    }
    assert scenario_images == {
        "CybORG/CybORG/Shared/Scenarios/images/Gateway_image.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/Internal_image.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/Kali_Box_image.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/OP_Server_image.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/Velociraptor_Server_image.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/images.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/linux_decoy_host_image.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/linux_user_host_image1.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/linux_user_host_image2.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/windows_user_host_image1.yaml",
        "CybORG/CybORG/Shared/Scenarios/images/windows_user_host_image2.yaml",
    }


def test_packaging_patch_is_explicit_and_preserves_original_behavior() -> None:
    record = cyborg.load_qualification()
    patch = cyborg.read_compatibility_patch()
    packaging = record["packaging"]
    patch_record = record["patches"][0]

    assert hashlib.sha256(patch.encode("utf-8")).hexdigest() == patch_record["sha256"]
    assert patch_record["kind"] == "packaging-only"
    assert patch_record["behavioral_delta"] == "none"
    assert patch_record["status"] == "qualification-candidate-only"
    assert "CybORG/setup.py" in patch
    assert "package_data" in patch
    assert "Shared/Scenarios/*.yaml" in patch
    assert "Shared/Scenarios/images/*.yaml" in patch

    assert packaging["unmodified_wheel"] == {
        "sha256": "80708d7e8c964a598530718895c374242b03992d6189c3de9a00666d6c67275d",
        "normalized_sha256": "ee61283f78df460441285263c861fc9c7ce65737b39f131125f889aadfd21bcd",
        "build": "passed",
        "import": "failed",
        "missing_runtime_files": [
            "CybORG/version.txt",
            "CybORG/Shared/Scenarios/Scenario2.yaml",
            "CybORG/Shared/Scenarios/images/*.yaml",
        ],
    }
    assert packaging["original_behavior_probe"]["installation"] == "editable-source"
    assert packaging["original_behavior_probe"]["result"] == "passed"
    assert packaging["patched_wheel"]["clean_install"] == "passed"
    assert packaging["patched_wheel"]["source_native_smoke"] == "passed"
    assert packaging["patched_wheel"]["normalized_sha256"] == (
        "9b6ecd41749466f3f6f5cc118be9536f153e57fb66b400aaa949f88d1c736039"
    )


def test_clean_patched_wheel_smoke_is_bounded_and_covers_all_roles() -> None:
    record = cyborg.load_qualification()
    runtime = record["runtime"]
    smoke = runtime["smoke"]

    assert runtime["python"] == "3.12.3"
    assert runtime["platform"] == {
        "system": "Linux",
        "kernel": "6.8.0-117-generic",
        "machine": "x86_64",
        "libc": "glibc-2.39",
    }
    assert runtime["working_directory"] == "isolated-temporary-directory"
    assert runtime["pythonpath"] == "cleared"
    assert runtime["python_safe_path"] is True
    assert runtime["network_after_install"] == "not-required"
    assert runtime["integrity"] == {
        "algorithm": "sha256(relative-posix-path + NUL + sha256(source-bytes))",
        "python_source_count": 337,
        "python_source_tree_sha256": (
            "f74427419b587b95e2f083c69f230a28a54871977fb4432644120e7f555d2212"
        ),
    }
    assert smoke == {
        "seed": 3,
        "scenario_exists": True,
        "reset_type": "ndarray",
        "reset_shape": [52],
        "step_arity": 4,
        "reward_types": ["float", "float"],
        "step_count": 2,
        "done_sequence": [False, True],
        "termination": "ChallengeWrapper.max_steps",
        "role_actions": {
            "blue": ["Sleep", "Sleep"],
            "red": ["DiscoverRemoteSystems", "DiscoverNetworkServices"],
            "green": ["GreenPortScan", "GreenPortScan"],
        },
    }
    serialized = json.dumps(smoke)
    assert "observation_values" not in serialized
    assert "reward_vector" not in serialized
    assert "action_id" not in serialized
    assert "native_state" not in serialized


def test_raes_adapter_smoke_constructs_and_cleans_the_selected_backend() -> None:
    smoke = cyborg.load_qualification()["runtime"]["adapter_smoke"]

    assert smoke == {
        "backend": "cyborg-cage2",
        "constructed": True,
        "cleaned": True,
        "native_projection_matches": True,
        "recorded_resources": 2,
        "realization_recorded": True,
    }


def test_selection_dependencies_and_stochastic_sources_are_explicit() -> None:
    record = cyborg.load_qualification()
    selection = record["selection"]

    assert selection["scenario"] == {
        "path": "CybORG/CybORG/Shared/Scenarios/Scenario2.yaml",
        "environment": "sim",
    }
    assert selection["evaluation"] == {
        "path": "CybORG/CybORG/Evaluation/evaluation.py",
        "episodes": 100,
        "trial_lengths": [30, 50, 100],
    }
    assert selection["wrapper"] == {
        "symbol": "CybORG.Agents.Wrappers.ChallengeWrapper",
        "agent_name": "Blue",
        "smoke_max_steps": 2,
    }
    assert selection["agents"] == {
        "blue": "external Sleep action",
        "red": "CybORG.Agents.B_lineAgent",
        "green": "CybORG.Agents.GreenAgent",
        "evaluation_red_set": ["B_lineAgent", "RedMeanderAgent", "SleepAgent"],
        "evaluation_blue": "BlueLoadAgent",
    }
    assert record["dependency_resolution"]["normalized_environment_sha256"] == (
        "56e2c189d6fd4b195584f34d93f66500b30eba8eedff6fca869ed61a8ab4079a"
    )
    assert record["dependency_resolution"]["uv_lock_sha256"] == (
        "7f815a2ed3d699432eb2bbfe5b3a2d6d09eae41be36ee794ee53cdb36d28b31b"
    )
    assert record["dependencies"]
    assert all(
        {"name", "version", "license"} <= dependency.keys() for dependency in record["dependencies"]
    )
    assert {stream["owner"] for stream in record["stochastic_sources"]} == {
        "cyborg-python-random",
        "gym-action-space",
        "numpy-global",
        "external-blue-policy",
    }


def test_legal_defect_and_fail_closed_packaging_decisions_are_explicit() -> None:
    record = cyborg.load_qualification()
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]

    assert record["legal"] == {
        "root_license": "MIT",
        "bundled_cyborg_license": "MIT",
        "notice_required": True,
        "source_redistribution": "permitted-with-notice",
        "patched_wheel_redistribution": "permitted-with-notice",
        "scenario_redistribution": "permitted-with-notice",
        "bundled_examples_redistribution": "permitted-with-notice",
        "retained_output": "permitted",
        "external_downloads": [],
        "model_weights": [],
    }
    assert {defect["id"] for defect in record["known_defects"]} == {
        "wheel-omits-runtime-data",
        "legacy-gym-unmaintained",
        "remove-success-misreport",
        "scenario-user3-port-mismatch",
        "evaluation-seed-not-bound",
    }
    assert record["admissibility"]["decision"] == "admitted"
    assert record["admissibility"]["scope"] == "maintainer-selected-cyborg-backend"
    assert set(record["admissibility"]["installation_limitations"]) == {
        "no-governed-public-patched-artifact",
        "declared-python-range-not-qualified",
        "declared-platform-range-not-qualified",
    }
    assert extras["cyborg"] == []
    assert "CybORG" not in project["project"]["dependencies"]
