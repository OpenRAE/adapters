"""Qualification evidence for the selected public PrimAITE case."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import raes_adapters.primaite as primaite

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_resources_select_one_immutable_source_and_protocol() -> None:
    record = primaite.load_qualification()
    protocol = primaite.read_public_protocol()

    assert primaite.__all__ == ["load_qualification", "read_public_protocol"]
    assert record["source"] == {
        "repository": "https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE",
        "tag": "v4.0.0",
        "tag_object": "f6513362e9882217fb90595de51e7ca659ee1416",
        "commit": "98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea",
        "tree": "3928ab452c51206ba8706b3f575e31fe99eb842e",
        "package": "primaite",
        "version": "4.0.0",
        "requires_python": ">=3.9,<3.13",
        "public_index_distribution": None,
        "index_note": (
            "No PyPI distribution or upstream release wheel exists; the README "
            "documents wheel-from-GitHub install only."
        ),
    }
    assert "# PrimAITE public experiment protocol" in protocol
    assert "`data_manipulation.yaml`" in protocol
    assert "`PrimaiteGymEnv`" in protocol or "PrimaiteGymEnv" in protocol
    assert hashlib.sha256(protocol.encode("utf-8")).hexdigest() == record["protocol"]["sha256"]


def test_clean_install_and_source_native_smoke_are_bounded_and_complete() -> None:
    record = primaite.load_qualification()
    runtime = record["runtime"]
    smoke = runtime["smoke"]

    assert runtime["python"] == "3.11.15"
    assert runtime["setuptools"] == "75.6.0"
    assert runtime["clean_install"] == "passed"
    assert runtime["network_after_install"] == "not-required"
    assert runtime["wheel_sha256"] == (
        "06df7275d2e5334a041e075695f9ce465789989d7bcf0a7696145fecc417c926"
    )
    assert smoke["reset_arity"] == 2
    assert smoke["step_arity"] == 5
    assert smoke["reset_obs_type"] == "ndarray"
    assert smoke["reset_obs_shape"] == [1652]
    assert smoke["reset_obs_dtype"] == "int64"
    assert smoke["representative_step"] == {
        "action": 0,
        "reward_type": "float",
        "reward": 0.65,
        "terminated": False,
        "truncated": False,
        "step_count": 1,
    }
    assert smoke["episode_run"] == {
        "action_policy": "do-nothing-every-step",
        "steps_to_end": 128,
        "terminated": False,
        "truncated": True,
        "final_step_reward": -0.8,
        "cumulative_reward": -57.05,
        "observed_stable_runs": 3,
    }
    # The public seed seam is broken without the rl/torch stack.
    assert smoke["seeded_reset"]["raised"] is True
    assert smoke["seeded_reset"]["exception_type"] == "KeyError"
    assert smoke["seeded_reset"]["missing_module"] == "torch"
    # Bounded structural summary only: no native payloads leak into the record.
    forbidden = {"observation", "observation_values", "credentials", "traceback", "state"}
    assert forbidden.isdisjoint(smoke)


def test_runtime_artifact_attestation_covers_complete_import_root() -> None:
    record = primaite.load_qualification()
    tree = record["runtime_source_tree"]

    assert tree["root"] == "primaite"
    assert tree["file_count"] == 234
    assert tree["sha256"] == ("9fe7ba158a005ead6133769336ff66e95da38c1cfe5054954be38d16d7f54dcc")
    assert tree["installed_wheel_tree_matches_source"] is True

    (artifact,) = record["runtime_artifacts"]
    assert artifact["name"] == "primaite"
    assert artifact["artifact"]["runtime_identity"] == "complete-root-tree"
    assert artifact["artifact"]["require_direct_archive_sha256"] is False
    assert artifact["roots"] == [
        {
            "path": "primaite",
            "file_count": 234,
            "sha256": ("9fe7ba158a005ead6133769336ff66e95da38c1cfe5054954be38d16d7f54dcc"),
        }
    ]

    source_files = {entry["path"]: entry["sha256"] for entry in record["source_files"]}
    assert source_files["LICENSE"] == (
        "669b434561703dbfa093fe2c02c2569bcfe3347caf339e5d42643e4c1b4b76e8"
    )
    assert source_files["src/primaite/session/environment.py"]


def test_protocol_fixes_every_identity_and_discloses_random_streams() -> None:
    record = primaite.load_qualification()
    selection = record["protocol"]["selection"]

    assert selection["scenario"] == {
        "use_case": "data_manipulation",
        "config_path": "primaite/config/_package_data/data_manipulation.yaml",
        "config_sha256": ("73c93965a32783f72f272993df4d65ab9bfcf670ba761503985199ff7e6debd6"),
        "config_metadata_version": "3.0",
        "max_episode_length": 128,
    }
    assert selection["entrypoint"] == "primaite.session.environment.PrimaiteGymEnv"
    assert selection["action_space"] == {"type": "Discrete", "n": 78}
    assert selection["observation_space"] == {
        "type": "Box",
        "shape": [1652],
        "dtype": "int64",
        "low": 0.0,
        "high": 1.0,
        "flattened": True,
    }
    assert selection["seed"] == 20260802
    assert selection["termination"] == {
        "terminated": "always false (hardcoded in step())",
        "truncated_rule": "step_counter >= max_episode_length",
        "max_episode_length": 128,
        "terminal_cause": "fixed-horizon-truncation",
    }
    assert selection["participants"]["blue"] == {
        "ref": "defender",
        "type": "proxy-agent",
        "role": "rl-controlled",
    }
    assert selection["participants"]["red"]["type"] == "red-database-corrupting-agent"
    assert {g["ref"] for g in selection["participants"]["green"]} == {
        "client_1_green_user",
        "client_2_green_user",
    }
    assert {stream["owner"] for stream in record["stochastic_sources"]} == {
        "gym-reset-seam",
        "python-random",
        "numpy-global",
        "torch",
    }


def test_legal_maintenance_and_patch_dispositions_are_explicit() -> None:
    record = primaite.load_qualification()

    assert record["legal"]["upstream_license"] == "MIT"
    assert record["legal"]["notice_required"] is True
    assert record["legal"]["redistribution"] == "permitted-with-notice"
    assert record["legal"]["retained_output"] == "permitted"
    assert record["legal"]["external_downloads"] == []
    assert record["legal"]["model_weights"] == []
    assert record["legal"]["raes_redistributes_source"] is False
    assert record["patches"] == []
    assert record["maintenance"]["archived"] is False
    assert record["maintenance"]["selected_commit"] == ("98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea")
    assert record["dependency_license_summary"]["strong_copyleft"] == []
    assert record["dependencies"]
    assert all(
        {"name", "version", "license"} <= dependency.keys() for dependency in record["dependencies"]
    )


def test_dependency_resolution_digest_is_reproducible_from_the_recorded_graph() -> None:
    record = primaite.load_qualification()
    resolution = record["dependency_resolution"]

    assert resolution["resolver"] == "uv"
    assert resolution["upstream_lockfile"] is None
    assert resolution["no_rl_dependency_count"] == len(record["dependencies"])

    env_lines = sorted(f"{d['name']}=={d['version']}" for d in record["dependencies"])
    digest = hashlib.sha256(("\n".join(env_lines) + "\n").encode("utf-8")).hexdigest()
    assert digest == resolution["normalized_environment_sha256"]


def test_qualification_admits_selected_backend_and_bounds_claim_strength() -> None:
    record = primaite.load_qualification()
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]

    assert record["admission"]["decision"] == "admitted"
    assert record["admission"]["authority"] == "maintainer-selection"
    assert set(record["admission"]["limitations"]) == {
        "no-index-or-release-artifact",
        "undeclared-setuptools-and-torch-runtime-deps",
        "unpinned-dependency-graph",
        "broken-public-seed-seam",
        "python-support-inconsistency",
    }
    assert record["admission"]["claim_strength"] == {
        "source_identity": "attested",
        "protocol_configuration": "attested",
        "execution_controls": "partial",
        "run_evidence": "attestable",
        "outcome_reproduction": "stochastic-bounded",
    }
    # The primaite extra is dependency-light; base and the other simulator
    # extras remain independent and unchanged.
    assert extras["primaite"] == []
    assert extras["cyberbattlesim"] == ["raes-env-packs==3.6.2"]
    assert extras["cyborg"] == ["raes-env-packs==3.6.2"]
