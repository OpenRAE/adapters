"""CybORG backend construction through published RAES provisioning contracts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import random
import sys
import textwrap
from collections import deque
from dataclasses import dataclass, field, replace
from importlib.machinery import ModuleSpec, PathFinder
from pathlib import Path
from typing import Any

import pytest
from raes import parse_sdl
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.planning import (
    ChangeAction,
    PlannedResource,
    ProvisioningPlan,
    ProvisionOp,
    RuntimeDomain,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.manager import RuntimeManager

from raes_adapters.cyborg import (
    CAGE2_SOURCE_26CE1C1,
    CYBORG_SCENARIO_MAPPING_VERSION,
    CyborgScenarioDescriptor,
    SourceInstalledCyborgDriver,
    create_cyborg_manifest,
    create_cyborg_target,
    load_qualification,
    translate_scenario,
)
from raes_adapters.cyborg import driver as driver_module

_SDL = """
name: honest-cyborg
nodes:
  user-net: {type: switch}
  linux-host: {type: vm, os: linux}
  windows-host: {type: vm, os: windows}
infrastructure:
  user-net:
    properties: {cidr: 10.20.0.0/24, gateway: 10.20.0.1}
  linux-host: {count: 2, links: [user-net]}
  windows-host: {count: 1, links: [user-net]}
"""

_SECOND_SDL = """
name: honest-cyborg
nodes:
  operations: {type: switch}
  linux-host: {type: vm, os: linux}
infrastructure:
  operations:
    properties: {cidr: 172.20.0.0/24, gateway: 172.20.0.1}
  linux-host: {count: 1, links: [operations]}
"""


class HostileNativeHandle:
    """Native handle that raises if a portable boundary tries to render it."""

    def __str__(self) -> str:
        raise AssertionError("native handle was rendered")

    def __repr__(self) -> str:
        raise AssertionError("native handle was rendered")


@dataclass
class FakeCyborgDriver:
    """Mechanical backend driver used to verify Provisioner ownership."""

    construction_error: Exception | None = None
    cleanup_outcomes: deque[bool | Exception] = field(default_factory=deque)
    descriptors: list[CyborgScenarioDescriptor] = field(default_factory=list)
    seeds: list[int | None] = field(default_factory=list)
    handles: list[HostileNativeHandle] = field(default_factory=list)
    cleanup_calls: list[object] = field(default_factory=list)

    def construct(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
    ) -> object:
        self.descriptors.append(descriptor)
        self.seeds.append(seed)
        if self.construction_error is not None:
            raise self.construction_error
        handle = HostileNativeHandle()
        self.handles.append(handle)
        return handle

    def cleanup(self, handle: object) -> bool:
        self.cleanup_calls.append(handle)
        outcome = self.cleanup_outcomes.popleft() if self.cleanup_outcomes else True
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _plan(target: Any, source: str = _SDL) -> ProvisioningPlan:
    execution = RuntimeManager(target).plan(parse_sdl(textwrap.dedent(source)))
    assert not execution.diagnostics
    return execution.provisioning


def _plan_with_snapshot(
    target: Any,
    snapshot: RuntimeSnapshot,
    source: str,
) -> ProvisioningPlan:
    execution = RuntimeManager(target, initial_snapshot=snapshot).plan(
        parse_sdl(textwrap.dedent(source))
    )
    assert not execution.diagnostics
    return execution.provisioning


def _delete_plan(target: Any, snapshot: RuntimeSnapshot) -> ProvisioningPlan:
    return ProvisioningPlan(
        resources={},
        operations=[
            ProvisionOp(
                action=ChangeAction.DELETE,
                address=entry.address,
                resource_type=entry.resource_type,
                payload={},
            )
            for entry in snapshot.entries.values()
        ],
        realization_envelope=target.manifest.realization_envelope.identity,
    )


def _replace_node_payload(
    plan: ProvisioningPlan,
    transform: Any,
) -> ProvisioningPlan:
    node_address = next(
        address for address, resource in plan.resources.items() if resource.resource_type == "node"
    )
    node = plan.resources[node_address]
    payload = transform(node.payload)
    changed_node = replace(node, payload=payload)
    resources = {**plan.resources, node_address: changed_node}
    operations = [
        replace(operation, payload=payload) if operation.address == node_address else operation
        for operation in plan.operations
    ]
    return ProvisioningPlan(
        resources=resources,
        operations=operations,
        realization_envelope=plan.realization_envelope,
    )


def test_manifest_is_valid_and_discloses_the_actual_projection() -> None:
    manifest = create_cyborg_manifest(seed=7)

    model = BackendManifestV2Model.model_validate(backend_manifest_payload(manifest))

    assert model.identity.name == "cyborg-cage2"
    assert model.capabilities.provisioner.name == "cyborg-cage2-provisioner"
    assert manifest.realization_envelope is not None
    assert manifest.has_orchestrator is True
    assert manifest.has_evaluator is False
    assert manifest.has_participant_runtime is True
    assert manifest.has_observation is False
    assert manifest.has_time is True
    configuration = manifest.realization_envelope.configuration
    assert configuration.mode == "raes-scenario-projection"
    assert configuration.supported_node_types == ["switch", "vm"]
    assert "seed=7" in configuration.network_policy
    concerns = {
        concern.concern.value: concern.disposition.value
        for concern in manifest.realization_envelope.concerns
    }
    assert concerns["topology"] == "transformed"
    assert concerns["image"] == "transformed"
    assert concerns["network"] == "transformed"
    assert concerns["resource-allocation"] == "unsupported"
    assert "source_installation" in manifest.constraints
    assert "equivalence" in manifest.constraints


def test_seed_is_bound_into_the_realization_identity() -> None:
    seed_seven = create_cyborg_manifest(seed=7)
    seed_eight = create_cyborg_manifest(seed=8)
    unseeded = create_cyborg_manifest()

    assert seed_seven.realization_envelope is not None
    assert seed_eight.realization_envelope is not None
    assert unseeded.realization_envelope is not None
    assert seed_seven.realization_envelope.identity != seed_eight.realization_envelope.identity
    assert seed_seven.realization_envelope.identity != unseeded.realization_envelope.identity


def test_compiled_sdl_is_translated_to_native_topology_not_a_fixed_scenario() -> None:
    first_driver = FakeCyborgDriver()
    first_target = create_cyborg_target(driver=first_driver, seed=7)
    first_plan = _plan(first_target)

    result = first_target.provisioner.apply(first_plan, RuntimeSnapshot())

    assert result.success is True
    assert (
        result.snapshot.realization_envelope == first_target.manifest.realization_envelope.identity
    )
    assert set(result.snapshot.entries) == set(first_plan.resources)
    assert first_driver.seeds == [7]
    descriptor = first_driver.descriptors[0]
    assert descriptor.profile_id == load_qualification()["profile_id"]
    assert descriptor.source_commit == load_qualification()["source"]["commit"]
    assert descriptor.mapping_version == CYBORG_SCENARIO_MAPPING_VERSION
    assert (
        descriptor.resources[0].payload
        is not first_plan.resources[descriptor.resources[0].address].payload
    )

    scenario = translate_scenario(descriptor)
    assert set(scenario["Agents"]) == {"Blue", "Green", "Red"}
    agents = scenario["Agents"]
    assert isinstance(agents, dict)
    assert agents["Blue"]["AllowedSubnets"] == ["user-net"]
    assert agents["Green"]["AllowedSubnets"] == ["user-net"]
    assert agents["Red"]["AllowedSubnets"] == ["user-net"]
    assert {session["hostname"] for session in agents["Blue"]["starting_sessions"]} == {
        "linux-host-0",
        "linux-host-1",
        "windows-host",
    }
    assert {session["hostname"] for session in agents["Green"]["starting_sessions"]} == {
        "linux-host-0",
        "linux-host-1",
        "windows-host",
    }
    assert agents["Red"]["starting_sessions"] == [
        {
            "hostname": "linux-host-0",
            "name": "RedPhish",
            "type": "RedAbstractSession",
            "username": "SYSTEM",
        }
    ]
    assert scenario["Subnets"] == {
        "user-net": {
            "Hosts": ["linux-host-0", "linux-host-1", "windows-host"],
            "Size": 3,
            "NACLs": {"all": {"in": "all", "out": "all"}},
        }
    }
    assert scenario["Hosts"] == {
        "linux-host-0": {"image": "linux_decoy_host"},
        "linux-host-1": {"image": "linux_decoy_host"},
        "windows-host": {"image": "windows_user_host1"},
    }

    second_driver = FakeCyborgDriver()
    second_target = create_cyborg_target(driver=second_driver, seed=7)
    second_plan = _plan(second_target, _SECOND_SDL)
    second = second_target.provisioner.apply(second_plan, RuntimeSnapshot())

    assert second.success is True
    second_scenario = translate_scenario(second_driver.descriptors[0])
    assert second_scenario != scenario
    assert second_scenario["Subnets"] == {
        "operations": {
            "Hosts": ["linux-host"],
            "Size": 1,
            "NACLs": {"all": {"in": "all", "out": "all"}},
        }
    }


def test_snapshot_is_the_portable_compiled_record_and_contains_no_native_handle() -> None:
    driver = FakeCyborgDriver()
    target = create_cyborg_target(driver=driver, seed=7)
    plan = _plan(target)
    authored = plan.resources["provision.node.windows-host"].payload

    result = target.provisioner.apply(plan, RuntimeSnapshot())

    assert result.success is True
    assert result.snapshot.entries["provision.node.windows-host"].payload == authored
    assert result.snapshot.entries["provision.node.windows-host"].payload is not authored
    assert all(handle not in result.snapshot.metadata.values() for handle in driver.handles)
    assert all(handle not in result.details.values() for handle in driver.handles)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"qualification_profile_id": "wrong-profile"}, "qualification profile"),
        ({"source_commit": "0" * 40}, "source commit"),
        ({"simulator_version": "99"}, "simulator version"),
        ({"mapping_ledger_resource": ("mapping", "wrong.jsonl")}, "mapping ledger"),
        ({"seed": -1}, "seed"),
        ({"seed": True}, "seed"),
        ({"surprise": "value"}, "unknown CybORG target configuration"),
    ],
)
def test_invalid_target_configuration_fails_before_backend_construction(
    config: dict[str, object],
    message: str,
) -> None:
    driver = FakeCyborgDriver()

    with pytest.raises(ValueError, match=message):
        create_cyborg_target(driver=driver, **config)

    assert driver.descriptors == []


def test_plan_identity_and_unsupported_resources_fail_before_construction() -> None:
    driver = FakeCyborgDriver()
    target = create_cyborg_target(driver=driver)
    plan = _plan(target)
    mismatched = ProvisioningPlan(
        resources=plan.resources,
        operations=plan.operations,
        realization_envelope=None,
    )

    diagnostics = target.provisioner.validate(mismatched)
    assert [item.code for item in diagnostics] == ["cyborg-backend.realization-envelope.missing"]

    content = PlannedResource(
        address="provision.content.payload",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="content-placement",
        payload={"content_type": "file"},
    )
    unsupported = ProvisioningPlan(
        resources={content.address: content},
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=content.address,
                resource_type=content.resource_type,
                payload=dict(content.payload),
            )
        ],
        realization_envelope=target.manifest.realization_envelope.identity,
    )
    result = target.provisioner.apply(unsupported, RuntimeSnapshot())

    assert result.success is False
    assert result.snapshot == RuntimeSnapshot()
    assert [item.code for item in result.diagnostics] == [
        "cyborg-backend.plan.unsupported-resource"
    ]
    assert driver.descriptors == []


@pytest.mark.parametrize(
    ("transform", "diagnostic_code"),
    [
        (
            lambda payload: {**payload, "node_type": "container"},
            "cyborg-backend.plan.unsupported-node-type",
        ),
        (
            lambda payload: {**payload, "os_family": "bsd"},
            "cyborg-backend.plan.unsupported-os-family",
        ),
        (
            lambda payload: {
                **payload,
                "spec": {
                    **payload["spec"],
                    "node": {**payload["spec"]["node"], "os": "windows"},
                },
            },
            "cyborg-backend.plan.unsupported-os-family",
        ),
        (
            lambda payload: {
                **payload,
                "spec": {
                    **payload["spec"],
                    "node": {
                        **payload["spec"]["node"],
                        "source": {"name": "unmapped-image", "version": "1"},
                    },
                },
            },
            "cyborg-backend.plan.unsupported-node-detail",
        ),
        (
            lambda payload: {
                **payload,
                "spec": {
                    **payload["spec"],
                    "infrastructure": {
                        **payload["spec"]["infrastructure"],
                        "links": [],
                    },
                },
            },
            "cyborg-backend.plan.unattached-node",
        ),
    ],
)
def test_lossy_or_unrepresentable_node_facts_fail_before_construction(
    transform: Any,
    diagnostic_code: str,
) -> None:
    driver = FakeCyborgDriver()
    target = create_cyborg_target(driver=driver)
    unsupported = _replace_node_payload(_plan(target), transform)

    result = target.provisioner.apply(unsupported, RuntimeSnapshot())

    assert result.success is False
    assert result.snapshot == RuntimeSnapshot()
    assert [item.code for item in result.diagnostics] == [diagnostic_code]
    assert driver.descriptors == []


def test_unknown_compiled_fields_and_inconsistent_operations_fail_closed() -> None:
    driver = FakeCyborgDriver()
    target = create_cyborg_target(driver=driver)
    plan = _plan(target)

    unknown_field = _replace_node_payload(
        plan,
        lambda payload: {**payload, "unpublished_backend_hint": "ignore-me"},
    )
    unknown_result = target.provisioner.apply(unknown_field, RuntimeSnapshot())

    inconsistent_operations = [
        (
            replace(operation, payload={**operation.payload, "unrecorded": True})
            if operation.resource_type == "node"
            else operation
        )
        for operation in plan.operations
    ]
    inconsistent = ProvisioningPlan(
        resources=plan.resources,
        operations=inconsistent_operations,
        realization_envelope=plan.realization_envelope,
    )
    inconsistent_result = target.provisioner.apply(inconsistent, RuntimeSnapshot())

    assert [item.code for item in unknown_result.diagnostics] == [
        "cyborg-backend.plan.invalid-node"
    ]
    assert [item.code for item in inconsistent_result.diagnostics] == [
        "cyborg-backend.plan.inconsistent-projection"
    ]
    assert driver.descriptors == []


def test_internal_network_request_fails_instead_of_becoming_all_allow() -> None:
    driver = FakeCyborgDriver()
    target = create_cyborg_target(driver=driver)
    plan = _plan(target)
    network_address = next(
        address
        for address, resource in plan.resources.items()
        if resource.resource_type == "network"
    )
    network = plan.resources[network_address]
    payload = {
        **network.payload,
        "spec": {
            **network.payload["spec"],
            "infrastructure": {
                **network.payload["spec"]["infrastructure"],
                "properties": {
                    **network.payload["spec"]["infrastructure"]["properties"],
                    "internal": True,
                },
            },
        },
    }
    changed = replace(network, payload=payload)
    resources = {**plan.resources, network_address: changed}
    operations = [
        replace(operation, payload=payload) if operation.address == network_address else operation
        for operation in plan.operations
    ]
    unsupported = ProvisioningPlan(
        resources=resources,
        operations=operations,
        realization_envelope=plan.realization_envelope,
    )

    result = target.provisioner.apply(unsupported, RuntimeSnapshot())

    assert [item.code for item in result.diagnostics] == [
        "cyborg-backend.plan.unsupported-network-detail"
    ]
    assert driver.descriptors == []


def test_source_tree_is_verified_before_any_cyborg_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "CybORG"
    package_root.mkdir()
    initializer = package_root / "__init__.py"
    initializer.write_text("raise RuntimeError('must never execute')\n", encoding="utf-8")
    spec = ModuleSpec("CybORG", loader=None, origin=str(initializer))
    spec.submodule_search_locations = [str(package_root)]
    monkeypatch.setattr(PathFinder, "find_spec", lambda _name: spec)
    monkeypatch.setattr(
        driver_module,
        "load_qualification",
        lambda: {
            "selected_files": [
                {
                    "path": "CybORG/CybORG/__init__.py",
                    "sha256": hashlib.sha256(initializer.read_bytes()).hexdigest(),
                }
            ],
            "runtime": {
                "integrity": {
                    "python_source_count": 1,
                    "python_source_tree_sha256": "0" * 64,
                }
            },
        },
    )
    imports: list[str] = []
    monkeypatch.setattr(
        driver_module,
        "import_module",
        lambda name: imports.append(name),
    )

    driver = SourceInstalledCyborgDriver(expected_version="2.1")

    with pytest.raises(RuntimeError, match="does not match the selected profile"):
        driver._native_binding()

    assert imports == []


def test_driver_uses_generated_document_deletes_it_and_preserves_global_rng(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_driver = FakeCyborgDriver()
    target = create_cyborg_target(driver=fake_driver, seed=19)
    plan = _plan(target)
    target.provisioner.apply(plan, RuntimeSnapshot())
    descriptor = fake_driver.descriptors[0]
    observed: dict[str, Any] = {}

    class FakeNative:
        def __init__(self, path: str, mode: str) -> None:
            observed["path"] = path
            observed["mode"] = mode
            observed["scenario"] = json.loads(Path(path).read_text(encoding="utf-8"))
            observed["seeded_sample"] = random.random()

        def set_seed(self, seed: int) -> None:
            observed["seed"] = seed

        def reset(self) -> None:
            observed["reset"] = True

        def shutdown(self) -> None:
            observed["shutdown"] = True

    source_driver = SourceInstalledCyborgDriver(expected_version="2.1")
    monkeypatch.setattr(source_driver, "_native_binding", lambda: FakeNative)
    random.seed(1234)
    before = random.getstate()

    native = source_driver.construct(descriptor, seed=19)

    assert isinstance(native, FakeNative)
    assert observed["mode"] == "sim"
    assert observed["scenario"] == translate_scenario(descriptor)
    assert observed["seed"] == 19
    assert observed["seeded_sample"] == random.Random(19).random()
    assert observed["reset"] is True
    assert not Path(observed["path"]).exists()
    assert random.getstate() == before


def test_driver_executes_a_private_source_snapshot_not_installed_bytecode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "CybORG"
    package_root.mkdir()
    initializer = package_root / "__init__.py"
    initializer.write_text(
        "\n".join(
            (
                'CYBORG_VERSION = "2.1"',
                "class CybORG:",
                '    execution_origin = "verified-source"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    malicious_source = tmp_path / "malicious.py"
    malicious_source.write_text(
        "\n".join(
            (
                'CYBORG_VERSION = "2.1"',
                "class CybORG:",
                '    execution_origin = "unverified-bytecode"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    cache_path = Path(importlib.util.cache_from_source(str(initializer)))
    cache_path.parent.mkdir()
    py_compile.compile(
        str(malicious_source),
        cfile=str(cache_path),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    source_driver = SourceInstalledCyborgDriver(expected_version="2.1")
    monkeypatch.setattr(
        source_driver,
        "_resolve_verified_package_root",
        lambda: package_root,
    )
    monkeypatch.setattr(source_driver, "_verify_selected_files", lambda _root: None)
    monkeypatch.setattr(source_driver, "_verify_python_source_tree", lambda _root: None)

    try:
        cyborg_type = source_driver._native_binding()
        assert cyborg_type.execution_origin == "verified-source"
        assert source_driver._runtime_workspace is not None
        module_path = Path(sys.modules[cyborg_type.__module__].__file__).resolve()
        assert module_path.is_relative_to(Path(source_driver._runtime_workspace.name).resolve())
    finally:
        for name in tuple(sys.modules):
            if name == "CybORG" or name.startswith("CybORG."):
                sys.modules.pop(name, None)
        if source_driver._runtime_workspace is not None:
            source_driver._runtime_workspace.cleanup()


def test_failed_construction_returns_unchanged_snapshot_and_bounded_diagnostic() -> None:
    driver = FakeCyborgDriver(
        construction_error=RuntimeError(
            "token=secret /native/path Traceback native-id-9981",
        )
    )
    target = create_cyborg_target(driver=driver)
    baseline = RuntimeSnapshot(metadata={"portable": "kept"})

    result = target.provisioner.apply(_plan(target), baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert result.details == {}
    assert [item.code for item in result.diagnostics] == [
        "cyborg-backend.driver.construction-failed"
    ]
    rendered = " ".join(item.message for item in result.diagnostics)
    assert "secret" not in rendered
    assert "/native/path" not in rendered
    assert "Traceback" not in rendered
    assert "native-id" not in rendered


def test_unchanged_apply_does_not_construct_a_second_backend() -> None:
    driver = FakeCyborgDriver()
    target = create_cyborg_target(driver=driver)
    first_plan = _plan(target)
    first = target.provisioner.apply(first_plan, RuntimeSnapshot())
    unchanged_plan = _plan_with_snapshot(target, first.snapshot, _SDL)
    unchanged = target.provisioner.apply(unchanged_plan, first.snapshot)

    assert first.success is True
    assert unchanged.success is True
    assert unchanged.changed_addresses == []
    assert len(driver.descriptors) == 1
    assert driver.cleanup_calls == []


def test_topology_removal_replaces_the_aggregate_with_complete_desired_state() -> None:
    driver = FakeCyborgDriver()
    target = create_cyborg_target(driver=driver, seed=5)
    first = target.provisioner.apply(_plan(target), RuntimeSnapshot())
    replacement_plan = _plan_with_snapshot(target, first.snapshot, _SECOND_SDL)

    replacement = target.provisioner.apply(replacement_plan, first.snapshot)

    assert replacement.success is True
    assert len(driver.descriptors) == 2
    assert driver.cleanup_calls == [driver.handles[0]]
    assert translate_scenario(driver.descriptors[1])["Hosts"] == {
        "linux-host": {"image": "linux_decoy_host"}
    }
    assert set(replacement.snapshot.entries) == set(replacement_plan.resources)


def test_failed_cleanup_retains_ownership_and_retries_until_delete_succeeds() -> None:
    driver = FakeCyborgDriver(cleanup_outcomes=deque([False, True]))
    target = create_cyborg_target(driver=driver)
    created = target.provisioner.apply(_plan(target), RuntimeSnapshot())

    first_delete = target.provisioner.apply(
        _delete_plan(target, created.snapshot),
        created.snapshot,
    )
    second_delete = target.provisioner.apply(
        _delete_plan(target, created.snapshot),
        created.snapshot,
    )

    assert first_delete.success is False
    assert first_delete.snapshot is created.snapshot
    assert [item.code for item in first_delete.diagnostics] == [
        "cyborg-backend.driver.cleanup-failed"
    ]
    assert second_delete.success is True
    assert second_delete.snapshot.entries == {}
    assert driver.cleanup_calls == [driver.handles[0], driver.handles[0]]
    assert target.provisioner.cleanup() is True


def test_failed_replacement_cleanup_compensates_candidate_without_advancing_snapshot() -> None:
    driver = FakeCyborgDriver(cleanup_outcomes=deque([False, True]))
    target = create_cyborg_target(driver=driver)
    created = target.provisioner.apply(_plan(target), RuntimeSnapshot())
    replacement_plan = _plan_with_snapshot(target, created.snapshot, _SECOND_SDL)

    replacement = target.provisioner.apply(replacement_plan, created.snapshot)
    recovery_plan = _plan_with_snapshot(target, created.snapshot, _SDL)
    recovered = target.provisioner.apply(recovery_plan, created.snapshot)

    assert replacement.success is False
    assert replacement.snapshot is created.snapshot
    assert [item.code for item in replacement.diagnostics] == [
        "cyborg-backend.driver.cleanup-failed"
    ]
    assert recovered.success is True
    assert len(driver.handles) == 3
    assert driver.cleanup_calls == [
        driver.handles[0],
        driver.handles[1],
        driver.handles[0],
    ]


def test_selected_cyborg_source_is_admitted_and_the_installation_limit_is_disclosed() -> None:
    record = load_qualification()

    assert record["admission"]["decision"] == "admitted"
    assert record["admission"]["scope"] == "maintainer-selected-cyborg-backend"
    assert record["packaging"]["patched_wheel"]["published"] is False
    assert CAGE2_SOURCE_26CE1C1.qualification_profile_id == record["profile_id"]
