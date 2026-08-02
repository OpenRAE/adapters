"""Qualification evidence for the selected public NASim case."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import raes_adapters.nasim as nasim

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_resources_select_one_immutable_source_and_protocol() -> None:
    record = nasim.load_qualification()
    protocol = nasim.read_public_protocol()

    assert nasim.__all__ == ["load_qualification", "read_public_protocol"]
    assert record["source"]["repository"] == (
        "https://github.com/Jjschwartz/NetworkAttackSimulator"
    )
    assert record["source"]["commit"] == "7c732bc4620d20a25b221a782adee29c2a89d800"
    assert record["source"]["tree"] == "4eedd4cc3ed9c31b17281baf447e67fcaa826298"
    assert record["source"]["package"] == "nasim"
    assert record["source"]["version"] == "0.12.0"
    assert record["source"]["wheel"]["sha256"] == (
        "4c059e64e0dd2365a6d43613ca3f83307dc0ecc47c48a39e02f590bbd01629db"
    )
    assert record["source"]["sdist"]["sha256"] == (
        "c5da8be95c5b5bcd89b03c15baeddd794af4c4844a632b48a8cccb61a5354ec9"
    )
    assert "# NASim public experiment protocol" in protocol
    assert "`tiny`" in protocol
    assert "run_bruteforce_agent" in protocol
    assert hashlib.sha256(protocol.encode("utf-8")).hexdigest() == record["protocol"]["sha256"]


def test_clean_install_and_source_native_smoke_are_bounded_and_complete() -> None:
    record = nasim.load_qualification()
    runtime = record["runtime"]
    smoke = runtime["smoke"]

    assert runtime["python"] == "3.12.3"
    assert runtime["wheel_sha256"] == (
        "4c059e64e0dd2365a6d43613ca3f83307dc0ecc47c48a39e02f590bbd01629db"
    )
    assert runtime["clean_install"] == "passed"
    assert smoke["reset_arity"] == 2
    assert smoke["step_arity"] == 5
    assert smoke["observation_type"] == "ndarray"
    assert smoke["observation_shape"] == [56]
    assert smoke["representative_step"] == {
        "action_index": 0,
        "action": "ServiceScan: target=(1, 0), cost=1.00, prob=1.00, req_access=USER",
        "reward": -1.0,
        "terminated": False,
        "truncated": False,
        "step_count": 1,
    }
    assert smoke["termination_probe"]["steps"] == 47
    assert smoke["termination_probe"]["total_reward"] == 153.0
    assert smoke["termination_probe"]["terminated"] is True
    assert smoke["termination_probe"]["truncated"] is False
    # Truncation stays distinct from goal termination (step-limit boundary).
    assert smoke["truncation_probe"]["steps"] == 1000
    assert smoke["truncation_probe"]["terminated"] is False
    assert smoke["truncation_probe"]["truncated"] is True
    assert "raw_observation" not in smoke
    assert "info" not in smoke


def test_runtime_artifact_attestation_covers_complete_import_roots() -> None:
    record = nasim.load_qualification()
    runtime_tree = record["runtime_source_tree"]

    assert runtime_tree["root"] == "nasim"
    assert runtime_tree["file_count"] == 42
    assert runtime_tree["sha256"] == (
        "be7ced2eff1d1ac372fbaae806cf401bf8be1e33cdaf6201132111fed7fab370"
    )
    assert "__pycache__" in runtime_tree["include"]
    source_files = {entry["path"]: entry["sha256"] for entry in record["source_files"]}
    assert source_files["nasim/__init__.py"] == (
        "7b10a01f275df7fab29b2c5b81711344a6d7ea2333d551c5aa41ad94ac63a4dd"
    )
    assert source_files["nasim/envs/action.py"] == (
        "ff7d820e210c13cab237c13371b77861bb7c173918f75325c5d6954237c6207b"
    )
    artifacts = {artifact["name"]: artifact for artifact in record["runtime_artifacts"]}
    assert set(artifacts) == {"nasim", "gymnasium", "numpy"}
    assert artifacts["nasim"]["roots"] == [
        {
            "path": "nasim",
            "file_count": 36,
            "sha256": ("813821d5b055497aa23ab3108d855b42fc153568483b34f38fa557294431b173"),
        }
    ]
    assert artifacts["gymnasium"]["artifact"]["sha256"] == (
        "4be0085252759c65b09c9fb83970ceedd02fab03b075024d8ba22eaa1a11eda1"
    )
    assert {artifact["artifact"]["runtime_identity"] for artifact in artifacts.values()} == {
        "complete-root-tree"
    }
    assert all(
        artifact["artifact"]["require_direct_archive_sha256"] is True
        for artifact in artifacts.values()
    )
    assert {root["path"] for root in artifacts["numpy"]["roots"]} == {
        "numpy",
        "numpy.libs",
    }


def test_protocol_fixes_every_identity_and_discloses_random_streams() -> None:
    record = nasim.load_qualification()
    selection = record["protocol"]["selection"]

    assert selection["scenario"] == {
        "name": "tiny",
        "type": "static-benchmark",
        "source_path": "nasim/scenarios/benchmark/tiny.yaml",
        "constructor": "nasim.make_benchmark",
        "fully_obs": True,
        "flat_actions": True,
        "flat_obs": True,
        "flat_action_space_n": 18,
        "observation_shape": [56],
        "observation_dtype": "float32",
        "step_limit": 1000,
        "sensitive_hosts": ["(2, 0)", "(3, 0)"],
    }
    assert selection["baseline"]["policy"] == "run_bruteforce_agent"
    assert selection["baseline"]["model_weights"] is False
    assert selection["seed"]["value"] == 20260802
    assert selection["termination"] == {
        "terminated": "goal_reached: all sensitive hosts compromised",
        "truncated": "env.steps >= scenario.step_limit (1000)",
        "independent": True,
    }
    assert {stream["owner"] for stream in record["stochastic_sources"]} == {
        "action-success-global-numpy",
        "gym-environment-rng",
        "scenario-generator-global-numpy",
        "host-config-randomisation-global-numpy",
        "agent-policy-rng",
    }


def test_legal_maintenance_and_patch_dispositions_are_explicit() -> None:
    record = nasim.load_qualification()

    assert record["legal"]["upstream_license"] == "MIT"
    assert record["legal"]["notice_required"] is True
    assert record["legal"]["redistribution"] == "permitted-with-notice"
    assert record["legal"]["retained_output"] == "permitted"
    assert record["legal"]["external_downloads"] == []
    # The only model weight ships git-only and is unused by the selected profile.
    weights = record["legal"]["model_weights"]
    assert [w["path"] for w in weights] == ["nasim/agents/policies/dqn_tiny.pt"]
    assert all(w["used_by_selected_protocol"] is False for w in weights)
    assert record["patches"] == []
    assert record["maintenance"]["archived"] is False
    assert record["maintenance"]["selected_commit"] == ("7c732bc4620d20a25b221a782adee29c2a89d800")
    assert {defect["id"] for defect in record["known_defects"]} == {
        "supplied-agents-numpy-int-incompatibility-gymnasium-ge-0.27",
        "action-success-rng-unbound-by-env-seed",
        "static-benchmark-seed-ignored",
        "headless-import-requires-tkinter",
    }
    assert record["dependencies"]
    assert all(
        {"name", "version", "license"} <= dependency.keys() for dependency in record["dependencies"]
    )


def test_qualification_admits_selected_backend_and_bounds_claim_strength() -> None:
    record = nasim.load_qualification()
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]

    assert record["admission"]["decision"] == "admitted"
    assert record["admission"]["authority"] == "maintainer-selection"
    assert record["admission"]["target"] == "RAESystem/research#12"
    assert record["admission"]["claim_strength"] == {
        "source_identity": "attested",
        "protocol_configuration": "attested",
        "execution_controls": "partial",
        "run_evidence": "attestable",
        "outcome_reproduction": "stochastic-bounded",
    }
    # The nasim extra pins the published distribution AND its qualified runtime
    # so installing the extra reproduces the admitted protocol; other extras
    # untouched.
    assert extras["nasim"] == ["nasim==0.12.0", "gymnasium==0.26.3", "numpy==1.26.4"]
    assert record["packaging"]["extra_declaration"] == extras["nasim"]
    # The extra must install exactly the qualified runtime the record attests,
    # so installing raes-adapters[nasim] reproduces the admitted protocol.
    pins = record["dependency_resolution"]["qualified_pins"]
    assert f"gymnasium=={pins['gymnasium']}" in extras["nasim"]
    assert f"numpy=={pins['numpy']}" in extras["nasim"]
    assert extras["cyberbattlesim"] == []
    assert extras["cyborg"] == ["raes-env-packs==3.6.2"]
