"""Canonical CAGE-2 Scenario2 SDL publication and realization acceptance."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import resources
from pathlib import Path

import pytest
from raes import parse_sdl, parse_sdl_file
from raes_runtime.manager import RuntimeManager

from raes_adapters.cyborg import create_cyborg_target
from raes_adapters.cyborg.conformance import cyborg_adapter_diagnostics
from raes_adapters.cyborg.scenario import CyborgScenarioDescriptor, translate_scenario
from raes_adapters.cyborg.source_ledger import load_source_ledger

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCENARIO_DIR = _REPO_ROOT / "src" / "raes_adapters" / "cyborg" / "scenario"
_SCENARIO = _SCENARIO_DIR / "cage2-scenario2.sdl.yaml"
_LOCK = _SCENARIO_DIR / "raes.lock.json"
_PACK_SCENARIO = (
    _REPO_ROOT
    / "src"
    / "raes_adapters"
    / "cyborg"
    / "examples"
    / "cage2-research"
    / "sdl"
    / "cage2-research.sdl.yaml"
)

_PORTABLE_HOSTS = {
    "defender",
    "enterprise-0",
    "enterprise-1",
    "enterprise-2",
    "op-host-0",
    "op-host-1",
    "op-host-2",
    "op-server-0",
    "user-0",
    "user-1",
    "user-2",
    "user-3",
    "user-4",
}
_PORTABLE_SUBNETS = {"enterprise", "operational", "user"}
_NATIVE_MEMBERSHIP = {
    "Enterprise": {"Defender", "Enterprise0", "Enterprise1", "Enterprise2"},
    "Operational": {"Op_Host0", "Op_Host1", "Op_Host2", "Op_Server0"},
    "User": {"User0", "User1", "User2", "User3", "User4"},
}
_NATIVE_IMAGES = {
    "Defender": "Velociraptor_Server",
    "Enterprise0": "Gateway",
    "Enterprise1": "Internal",
    "Enterprise2": "Internal",
    "Op_Host0": "Gateway",
    "Op_Host1": "Gateway",
    "Op_Host2": "Gateway",
    "Op_Server0": "OP_Server",
    "User0": "windows_user_host1",
    "User1": "windows_user_host1",
    "User2": "windows_user_host2",
    "User3": "linux_user_host1",
    "User4": "linux_user_host2",
}
_QUALIFIED_IMAGE_PATHS = {
    "CybORG/CybORG/Shared/Scenarios/images/Gateway_image.yaml",
    "CybORG/CybORG/Shared/Scenarios/images/Internal_image.yaml",
    "CybORG/CybORG/Shared/Scenarios/images/OP_Server_image.yaml",
    "CybORG/CybORG/Shared/Scenarios/images/Velociraptor_Server_image.yaml",
    "CybORG/CybORG/Shared/Scenarios/images/linux_user_host_image1.yaml",
    "CybORG/CybORG/Shared/Scenarios/images/linux_user_host_image2.yaml",
    "CybORG/CybORG/Shared/Scenarios/images/windows_user_host_image1.yaml",
    "CybORG/CybORG/Shared/Scenarios/images/windows_user_host_image2.yaml",
}


class _CapturingDriver:
    """Dependency-free driver seam that records the admitted native projection."""

    def __init__(self) -> None:
        self.descriptor: CyborgScenarioDescriptor | None = None
        self.native: dict[str, dict[str, object]] | None = None
        self.handle = object()
        self.cleaned = False

    def construct(self, descriptor: CyborgScenarioDescriptor, *, seed: int | None) -> object:
        self.descriptor = descriptor
        self.native = translate_scenario(descriptor)
        return self.handle

    def cleanup(self, handle: object) -> bool:
        self.cleaned = handle is self.handle
        return self.cleaned


def test_canonical_scenario_covers_full_scenario2_portable_surface() -> None:
    scenario = parse_sdl_file(_SCENARIO)

    assert scenario.module is not None
    assert scenario.module.id == "openrae/cyborg-cage2-scenario2"
    assert scenario.module.version == "1.0.0"
    assert set(scenario.infrastructure) == _PORTABLE_HOSTS | _PORTABLE_SUBNETS
    assert set(scenario.nodes) == _PORTABLE_HOSTS | _PORTABLE_SUBNETS
    assert set(scenario.entities) == {"blue-team", "green-workforce", "red-team"}
    assert set(scenario.agents) == {"blue", "green", "red"}
    assert set(scenario.objectives) == {"defend-operational-service", "impact-operational-service"}
    assert all(scenario.nodes[host].services for host in _PORTABLE_HOSTS)
    assert scenario.accounts
    assert all("password" not in account.model_dump() for account in scenario.accounts.values())


def test_canonical_scenario_resolves_verifies_and_publishes(tmp_path: Path) -> None:
    raes = Path(sys.executable).with_name("raes")
    assert raes.is_file()
    staged = tmp_path / _SCENARIO.name
    staged.write_bytes(_SCENARIO.read_bytes())

    subprocess.run(
        [raes, "sdl", "resolve", str(staged)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads((tmp_path / "raes.lock.json").read_text()) == json.loads(_LOCK.read_text())
    subprocess.run(
        [raes, "sdl", "verify-imports", str(staged)],
        check=True,
        capture_output=True,
        text=True,
    )
    output = tmp_path / "oci"
    subprocess.run(
        [raes, "sdl", "publish", str(staged), "--output-dir", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    layouts = list(output.glob("*.oci"))
    assert len(layouts) == 1
    assert (layouts[0] / "oci-layout").is_file()
    assert (layouts[0] / "index.json").is_file()


def test_canonical_scenario_reaches_driver_with_exact_scenario2_projection() -> None:
    driver = _CapturingDriver()
    scenario = parse_sdl_file(_SCENARIO)
    target = create_cyborg_target(driver=driver, scenario=scenario, seed=7)
    manager = RuntimeManager(target)

    planned = manager.plan(scenario)

    assert set(planned.evaluation.resources) == {
        "evaluation.proposition.operational-service-available",
        "evaluation.assertion.operational-impact-postcondition",
        "evaluation.assertion.operational-service-invariant",
        "evaluation.objective.impact-operational-service",
        "evaluation.objective.defend-operational-service",
    }
    assert planned.evaluation.resources[
        "evaluation.proposition.operational-service-available"
    ].payload["subject_addresses"] == ("provision.node.op-server-0",)

    applied = manager.apply(planned)

    assert applied.success, [(item.code, item.message) for item in applied.diagnostics]
    assert driver.descriptor is not None
    assert driver.native is not None
    assert {
        name: set(value["Hosts"]) for name, value in driver.native["Subnets"].items()
    } == _NATIVE_MEMBERSHIP
    assert {name: value["Size"] for name, value in driver.native["Subnets"].items()} == {
        "Enterprise": 3,
        "Operational": 4,
        "User": 5,
    }
    assert {
        name: value["image"] for name, value in driver.native["Hosts"].items()
    } == _NATIVE_IMAGES
    assert driver.native["Subnets"]["Operational"]["NACLs"]["User"] == {
        "in": "None",
        "out": "all",
    }
    assert set(driver.native["Agents"]) == {"Blue", "Green", "Red"}
    assert driver.native["Agents"]["Blue"]["actions"] == [
        "Sleep",
        "Monitor",
        "Analyse",
        "Remove",
        "DecoyApache",
        "DecoyFemitter",
        "DecoyHarakaSMPT",
        "DecoySmss",
        "DecoySSHD",
        "DecoySvchost",
        "DecoyTomcat",
        "DecoyVsftpd",
        "Restore",
    ]
    assert driver.native["Agents"]["Red"]["actions"] == [
        "Sleep",
        "DiscoverRemoteSystems",
        "DiscoverNetworkServices",
        "ExploitRemoteService",
        "BlueKeep",
        "EternalBlue",
        "FTPDirectoryTraversal",
        "HarakaRCE",
        "HTTPRFI",
        "HTTPSRFI",
        "SQLInjection",
        "SSHBruteForce",
        "PrivilegeEscalate",
        "Impact",
    ]
    assert driver.native["Agents"]["Red"]["INT"] == {
        "Hosts": {"User0": {"Interfaces": "All", "System info": "All"}}
    }
    assert {item["hostname"] for item in driver.native["Agents"]["Green"]["starting_sessions"]} == {
        "User0",
        "User1",
        "User2",
        "User3",
        "User4",
        "Op_Host0",
        "Op_Host1",
        "Op_Host2",
    }
    assert any(
        item["hostname"] == "Defender" and item["name"] == "VeloServer"
        for item in driver.native["Agents"]["Blue"]["starting_sessions"]
    )
    assert driver.native["Hosts"]["Enterprise2"]["info"]["Op_Server0"] == {
        "Interfaces": "IP Address"
    }
    assert driver.native["Hosts"]["Op_Server0"]["info"]["Op_Server0"]["Services"] == ["OTService"]

    destroyed = RuntimeManager(target, initial_snapshot=applied.snapshot).destroy()
    assert destroyed.success
    assert driver.cleaned


def test_scenario2_realization_rejects_resource_identical_digest_mismatch() -> None:
    altered_source = _SCENARIO.read_text(encoding="utf-8").replace(
        "Blue defender with source-defined estate visibility and remediation actions.",
        "Altered scenario identity with the same provisioning closure.",
        1,
    )
    altered = parse_sdl(altered_source)
    driver = _CapturingDriver()

    with pytest.raises(
        ValueError,
        match="CybORG scenario does not match the selected Scenario2 profile",
    ):
        create_cyborg_target(driver=driver, scenario=altered, seed=7)


def test_pack_snapshot_is_byte_identical_to_canonical_scenario() -> None:
    assert _PACK_SCENARIO.read_bytes() == _SCENARIO.read_bytes()


def test_canonical_scenario_and_lock_are_installed_resources() -> None:
    installed = resources.files("raes_adapters.cyborg") / "scenario"

    assert (installed / "cage2-scenario2.sdl.yaml").is_file()
    assert (installed / "raes.lock.json").is_file()


def test_source_ledger_covers_every_consumed_qualified_image() -> None:
    rows = load_source_ledger()
    covered = {
        str(row["source_path"])
        for row in rows
        if row["disposition"] == "mapped"
        and row["fact_facet"] in {"accounts", "privileges", "services"}
    }

    assert covered >= _QUALIFIED_IMAGE_PATHS


def test_adapter_conformance_evidence_includes_full_scenario2_realization() -> None:
    diagnostics = cyborg_adapter_diagnostics(seed=3)

    assert any(item.code == "cyborg.probe.scenario2-realization.validated" for item in diagnostics)
    assert all(item.code.endswith(".validated") for item in diagnostics)
