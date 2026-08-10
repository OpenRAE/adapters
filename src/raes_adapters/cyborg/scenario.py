"""Deterministic projection of admitted RAES resources into CybORG scenario data."""

from __future__ import annotations

import copy
from typing import NamedTuple

import raes  # type: ignore[import-untyped]
from raes_backend_protocols.capabilities import BackendManifest  # type: ignore[import-untyped]
from raes_contracts.runtime_state import RuntimeSnapshot  # type: ignore[import-untyped]
from raes_processor.compiler import (  # type: ignore[import-untyped]
    compile_scenario_runtime_model,
)
from raes_processor.planner import plan as build_execution_plan  # type: ignore[import-untyped]

_IMAGE_BY_OS_FAMILY = {
    "linux": "linux_decoy_host",
    "windows": "windows_user_host1",
}
_GENERIC_SUPPORTED_RESOURCE_TYPES = frozenset({"network", "node"})
_SUPPORTED_RESOURCE_TYPES = frozenset({"account-placement", "network", "node"})
CYBORG_SCENARIO_MAPPING_VERSION = "raes-cyborg-scenario-v2"
SCENARIO2_CANONICAL_DIGEST = (
    "sha256:58aa6b438c38bb53a5d6636e11835e44ebd6e57b48561e48aa80f0f14bfa6bf2"
)
_SCENARIO2_NETWORKS = frozenset({"enterprise", "operational", "user"})
_SCENARIO2_NATIVE_NETWORKS = {
    "enterprise": "Enterprise",
    "operational": "Operational",
    "user": "User",
}
_SCENARIO2_NATIVE_HOSTS = {
    "defender": ("Defender", "Velociraptor_Server"),
    "enterprise-0": ("Enterprise0", "Gateway"),
    "enterprise-1": ("Enterprise1", "Internal"),
    "enterprise-2": ("Enterprise2", "Internal"),
    "op-host-0": ("Op_Host0", "Gateway"),
    "op-host-1": ("Op_Host1", "Gateway"),
    "op-host-2": ("Op_Host2", "Gateway"),
    "op-server-0": ("Op_Server0", "OP_Server"),
    "user-0": ("User0", "windows_user_host1"),
    "user-1": ("User1", "windows_user_host1"),
    "user-2": ("User2", "windows_user_host2"),
    "user-3": ("User3", "linux_user_host1"),
    "user-4": ("User4", "linux_user_host2"),
}
_SCENARIO2_PARTICIPANTS = frozenset(
    {
        "participant.behavior.blue",
        "participant.behavior.green",
        "participant.behavior.red",
    }
)
_SCENARIO2_OBSERVATION_BOUNDARIES = (
    "participant.observation-boundary.blue",
    "participant.observation-boundary.green",
    "participant.observation-boundary.red",
)
_SCENARIO2_OBJECTIVES = (
    "evaluation.objective.defend-operational-service",
    "evaluation.objective.impact-operational-service",
)
_SCENARIO2_NATIVE_ACTIONS_BY_CONTRACT = {
    "participant.action-contract.sleep": ("Sleep",),
    "participant.action-contract.monitor": ("Monitor",),
    "participant.action-contract.analyse": ("Analyse",),
    "participant.action-contract.remove": ("Remove",),
    "participant.action-contract.deploy-decoy": (
        "DecoyApache",
        "DecoyFemitter",
        "DecoyHarakaSMPT",
        "DecoySmss",
        "DecoySSHD",
        "DecoySvchost",
        "DecoyTomcat",
        "DecoyVsftpd",
    ),
    "participant.action-contract.restore": ("Restore",),
    "participant.action-contract.green-ping-sweep": ("GreenPingSweep",),
    "participant.action-contract.green-port-scan": ("GreenPortScan",),
    "participant.action-contract.green-connection": ("GreenConnection",),
    "participant.action-contract.discover-remote-systems": ("DiscoverRemoteSystems",),
    "participant.action-contract.discover-network-services": ("DiscoverNetworkServices",),
    "participant.action-contract.exploit-remote-service": (
        "ExploitRemoteService",
        "BlueKeep",
        "EternalBlue",
        "FTPDirectoryTraversal",
        "HarakaRCE",
        "HTTPRFI",
        "HTTPSRFI",
        "SQLInjection",
        "SSHBruteForce",
    ),
    "participant.action-contract.privilege-escalate": ("PrivilegeEscalate",),
    "participant.action-contract.impact": ("Impact",),
}
_NETWORK_PAYLOAD_KEYS = frozenset({"name", "node_name", "spec"})
_NODE_PAYLOAD_KEYS = frozenset(
    {
        "name",
        "node_name",
        "node_type",
        "os_family",
        "count",
        "network_namespace_target",
        "domain_topology",
        "spec",
    }
)
_SPEC_KEYS = frozenset({"node", "infrastructure"})
_COMPILED_NODE_KEYS = frozenset(
    {
        "type",
        "description",
        "source",
        "resources",
        "os",
        "os_version",
        "features",
        "conditions",
        "injects",
        "vulnerabilities",
        "roles",
        "services",
        "asset_value",
        "endpoint_persona",
        "runtime",
    }
)
_COMPILED_INFRASTRUCTURE_KEYS = frozenset(
    {
        "count",
        "links",
        "dependencies",
        "properties",
        "acls",
        "description",
    }
)
_NETWORK_PROPERTY_KEYS = frozenset({"cidr", "gateway", "internal"})
_INVALID_NODE_CODE = "cyborg-backend.plan.invalid-node"
_INVALID_NODE_MESSAGE = "A node resource is not a complete compiled RAES VM descriptor."
_GENERIC_BLUE_ACTIONS = ["Sleep", "Monitor", "Analyse", "Remove", "Restore"]
_GENERIC_GREEN_ACTIONS = [
    "Sleep",
    "GreenPingSweep",
    "GreenPortScan",
    "GreenConnection",
]
_GENERIC_RED_ACTIONS = [
    "Sleep",
    "DiscoverRemoteSystems",
    "DiscoverNetworkServices",
    "ExploitRemoteService",
    "PrivilegeEscalate",
    "Impact",
]
_NetworkFacts = tuple[
    str,
    dict[str, object],
    int,
    tuple[str, ...],
    list[object],
    dict[str, object],
]
_NodeFacts = tuple[
    str,
    int,
    str,
    dict[str, object],
    dict[str, object],
    int,
    tuple[str, ...],
]


class CyborgScenarioResource(NamedTuple):
    """One copied admitted RAES resource supplied to native construction."""

    address: str
    resource_type: str
    payload: dict[str, object]
    ordering_dependencies: tuple[str, ...]
    refresh_dependencies: tuple[str, ...]


class CyborgParticipantBinding(NamedTuple):
    """RAES-compiled participant surface admitted for one selected scenario."""

    address: str
    action_contract_addresses: tuple[str, ...]
    observation_boundary_addresses: tuple[str, ...]
    starting_account_addresses: tuple[str, ...]
    initial_knowledge_addresses: tuple[str, ...]
    allowed_subnet_addresses: tuple[str, ...]


class CyborgScenarioBinding(NamedTuple):
    """RAES-owned scenario identity and compiled contracts for native selection."""

    canonical_digest: str
    resources: tuple[CyborgScenarioResource, ...]
    participants: tuple[CyborgParticipantBinding, ...]
    observation_boundary_addresses: tuple[str, ...]
    objective_addresses: tuple[str, ...]


class CyborgScenarioDescriptor(NamedTuple):
    """Private construction input derived from a complete desired RAES state."""

    profile_id: str
    source_commit: str
    mapping_version: str
    resources: tuple[CyborgScenarioResource, ...]
    scenario_binding: CyborgScenarioBinding | None


class CyborgTranslationIssue(NamedTuple):
    """One bounded reason an admitted plan cannot be represented by CybORG."""

    code: str
    message: str


def copied_resource(
    *,
    address: str,
    resource_type: str,
    payload: dict[str, object],
    ordering_dependencies: tuple[str, ...],
    refresh_dependencies: tuple[str, ...],
) -> CyborgScenarioResource:
    """Copy an admitted resource so driver preparation cannot mutate the plan."""

    return CyborgScenarioResource(
        address=address,
        resource_type=resource_type,
        payload=copy.deepcopy(payload),
        ordering_dependencies=tuple(ordering_dependencies),
        refresh_dependencies=tuple(refresh_dependencies),
    )


def bind_scenario_profile(
    scenario: object,
    manifest: BackendManifest,
    *,
    target_name: str,
) -> CyborgScenarioBinding | None:
    """Bind the fixed Scenario2 mapping to RAES canonical and compiled identity."""

    try:
        instantiated = raes.instantiate_scenario(scenario)
        model = compile_scenario_runtime_model(instantiated)
        execution = build_execution_plan(
            model,
            manifest,
            RuntimeSnapshot(),
            target_name=target_name,
        )
    except Exception:
        raise ValueError("CybORG scenario profile could not be compiled by RAES.") from None
    resources = tuple(
        copied_resource(
            address=resource.address,
            resource_type=resource.resource_type,
            payload=resource.payload,
            ordering_dependencies=resource.ordering_dependencies,
            refresh_dependencies=resource.refresh_dependencies,
        )
        for resource in sorted(
            execution.provisioning.resources.values(),
            key=lambda item: item.address,
        )
    )
    if not _is_scenario2_candidate(resources):
        return None
    digest = raes.canonical_instantiated_sdl_digest(instantiated).value
    if digest != SCENARIO2_CANONICAL_DIGEST or execution.diagnostics:
        raise ValueError("CybORG scenario does not match the selected Scenario2 profile.")
    try:
        participants = tuple(
            CyborgParticipantBinding(
                address=address,
                action_contract_addresses=tuple(behavior.action_contract_addresses),
                observation_boundary_addresses=tuple(behavior.observation_boundary_addresses),
                starting_account_addresses=tuple(behavior.starting_account_addresses),
                initial_knowledge_addresses=tuple(behavior.initial_knowledge_addresses),
                allowed_subnet_addresses=_participant_allowed_subnet_addresses(behavior.spec),
            )
            for address, behavior in sorted(model.participant_behaviors.items())
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            "CybORG scenario contracts do not match the selected Scenario2 profile."
        ) from None
    binding = CyborgScenarioBinding(
        canonical_digest=digest,
        resources=resources,
        participants=participants,
        observation_boundary_addresses=tuple(sorted(model.observation_boundaries)),
        objective_addresses=tuple(sorted(model.objectives)),
    )
    if _scenario2_binding_issue(binding) is not None:
        raise ValueError("CybORG scenario contracts do not match the selected Scenario2 profile.")
    return binding


def _participant_allowed_subnet_addresses(spec: dict[str, object]) -> tuple[str, ...]:
    """Read compiled allowed-subnet references without defining a second contract."""

    agent = spec["agent"]
    if not isinstance(agent, dict):
        raise TypeError
    allowed = agent["allowed_subnets"]
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise TypeError
    return tuple(f"provision.network.{item}" for item in allowed)


def validate_scenario_resources(
    resources: tuple[CyborgScenarioResource, ...],
    scenario_binding: CyborgScenarioBinding | None = None,
) -> CyborgTranslationIssue | None:
    """Return the first deterministic representability failure, if any."""

    if _is_scenario2_candidate(resources):
        issue = _scenario2_profile_issue(resources, scenario_binding)
    else:
        issue = _unsupported_resource_issue(resources)
    if issue is None and not _is_scenario2_resources(resources, scenario_binding):
        networks = tuple(resource for resource in resources if resource.resource_type == "network")
        nodes = tuple(resource for resource in resources if resource.resource_type == "node")
        issue = _validate_complete_scenario(networks, nodes)
    return issue


def _unsupported_resource_issue(
    resources: tuple[CyborgScenarioResource, ...],
) -> CyborgTranslationIssue | None:
    """Reject resource kinds outside the provisioning-only mapping."""

    unsupported_types = sorted(
        {resource.resource_type for resource in resources} - _GENERIC_SUPPORTED_RESOURCE_TYPES
    )
    if unsupported_types:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-resource",
            "The provisioning plan contains a resource CybORG cannot represent.",
        )
    return None


def _validate_complete_scenario(
    networks: tuple[CyborgScenarioResource, ...],
    nodes: tuple[CyborgScenarioResource, ...],
) -> CyborgTranslationIssue | None:
    """Validate required resource families and their cross-resource names."""

    if not networks or not nodes:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.incomplete-scenario",
            "CybORG construction requires at least one network and one attached VM.",
        )
    network_names: set[str] = set()
    issue = _first_network_issue(networks, network_names)
    if issue is None:
        issue = _first_node_issue(nodes, network_names)
    return issue


def _first_network_issue(
    networks: tuple[CyborgScenarioResource, ...],
    network_names: set[str],
) -> CyborgTranslationIssue | None:
    """Return the first network failure while collecting valid subnet names."""

    issue: CyborgTranslationIssue | None = None
    for resource in networks:
        issue = _validate_network(resource, network_names)
        if issue is not None:
            break
    return issue


def _first_node_issue(
    nodes: tuple[CyborgScenarioResource, ...],
    network_names: set[str],
) -> CyborgTranslationIssue | None:
    """Return the first node failure while reserving valid native host names."""

    issue: CyborgTranslationIssue | None = None
    native_host_names: set[str] = set()
    for resource in nodes:
        issue = _validate_node(resource, network_names, native_host_names)
        if issue is not None:
            break
    return issue


def translate_scenario(
    descriptor: CyborgScenarioDescriptor,
) -> dict[str, dict[str, object]]:
    """Translate a valid complete desired state into native scenario data."""

    resources = tuple(sorted(descriptor.resources, key=lambda item: item.address))
    issue = validate_scenario_resources(resources, descriptor.scenario_binding)
    if issue is not None:
        raise ValueError(issue.message)
    if _is_scenario2_resources(resources, descriptor.scenario_binding):
        assert descriptor.scenario_binding is not None
        return _translate_scenario2(resources, descriptor.scenario_binding)

    subnets: dict[str, object] = {}
    for resource in resources:
        if resource.resource_type != "network":
            continue
        name = _required_string(resource.payload, "name")
        subnets[name] = {
            "Hosts": [],
            "Size": 1,
            "NACLs": {"all": {"in": "all", "out": "all"}},
        }

    hosts: dict[str, object] = {}
    for resource in resources:
        if resource.resource_type != "node":
            continue
        payload = resource.payload
        name = _required_string(payload, "name")
        count = _required_positive_int(payload, "count")
        image = _IMAGE_BY_OS_FAMILY[_required_string(payload, "os_family")]
        infrastructure = _required_mapping(_required_mapping(payload, "spec"), "infrastructure")
        links = _required_string_list(infrastructure, "links")
        for hostname in _expanded_names(name, count):
            hosts[hostname] = {"image": image}
            for network_name in links:
                subnet = subnets[network_name]
                assert isinstance(subnet, dict)
                subnet_hosts = subnet["Hosts"]
                assert isinstance(subnet_hosts, list)
                subnet_hosts.append(hostname)

    for subnet in subnets.values():
        assert isinstance(subnet, dict)
        subnet_hosts = subnet["Hosts"]
        assert isinstance(subnet_hosts, list)
        subnet["Size"] = max(1, len(subnet_hosts))

    return {
        "Agents": _agent_declarations(hosts, subnets),
        "Subnets": subnets,
        "Hosts": hosts,
    }


def host_address_map(descriptor: CyborgScenarioDescriptor) -> dict[str, str]:
    """Map private native host labels to admitted portable node addresses."""

    resources = tuple(sorted(descriptor.resources, key=lambda item: item.address))
    issue = validate_scenario_resources(resources, descriptor.scenario_binding)
    if issue is not None:
        raise ValueError(issue.message)
    result: dict[str, str] = {}
    scenario2 = _is_scenario2_resources(resources, descriptor.scenario_binding)
    for resource in resources:
        if resource.resource_type != "node":
            continue
        name = _required_string(resource.payload, "name")
        count = _required_positive_int(resource.payload, "count")
        native_names = (
            (_SCENARIO2_NATIVE_HOSTS[name][0],) if scenario2 else _expanded_names(name, count)
        )
        result.update(dict.fromkeys(native_names, resource.address))
    return result


def _is_scenario2_candidate(resources: tuple[CyborgScenarioResource, ...]) -> bool:
    """Recognize the fixed Scenario2 topology before exact-profile validation."""

    names: dict[str, set[str]] = {"network": set(), "node": set()}
    for resource in resources:
        if resource.resource_type not in names:
            continue
        name = resource.payload.get("name")
        if isinstance(name, str):
            names[resource.resource_type].add(name)
    return names["network"] == _SCENARIO2_NETWORKS and names["node"] == set(_SCENARIO2_NATIVE_HOSTS)


def _scenario2_profile_issue(
    resources: tuple[CyborgScenarioResource, ...],
    scenario_binding: CyborgScenarioBinding | None,
) -> CyborgTranslationIssue | None:
    """Require the exact compiled portable resource closure selected for Scenario2."""

    if {resource.resource_type for resource in resources} - _SUPPORTED_RESOURCE_TYPES:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-resource",
            "The provisioning plan contains a resource CybORG cannot represent.",
        )
    if scenario_binding is None:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.scenario-profile-unbound",
            "The CAGE-2 Scenario2 plan is not bound to its canonical RAES contracts.",
        )
    if not _is_scenario2_resources(resources, scenario_binding):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.scenario-profile-mismatch",
            "The CAGE-2 Scenario2 resources do not match the selected mapping profile.",
        )
    return None


def _scenario2_binding_issue(
    binding: CyborgScenarioBinding,
) -> CyborgTranslationIssue | None:
    """Validate the RAES-compiled participant, observation, and objective join."""

    participants = {participant.address: participant for participant in binding.participants}
    resources = {resource.address: resource for resource in binding.resources}
    participant_boundaries = tuple(
        boundary
        for participant in binding.participants
        for boundary in participant.observation_boundary_addresses
    )
    if set(participants) != _SCENARIO2_PARTICIPANTS or any(
        not participant.action_contract_addresses
        or any(
            contract not in _SCENARIO2_NATIVE_ACTIONS_BY_CONTRACT
            for contract in participant.action_contract_addresses
        )
        for participant in binding.participants
    ):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.scenario-participants-mismatch",
            "The Scenario2 participant action contracts do not match the selected mapping.",
        )
    if any(
        resources.get(address) is None or resources[address].resource_type != "account-placement"
        for participant in binding.participants
        for address in participant.starting_account_addresses
    ) or any(
        resources.get(address) is None
        or resources[address].resource_type not in {"network", "node"}
        for participant in binding.participants
        for address in (
            *participant.initial_knowledge_addresses,
            *participant.allowed_subnet_addresses,
        )
    ):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.scenario-participants-mismatch",
            "The Scenario2 participant resources do not match the compiled contracts.",
        )
    if (
        participant_boundaries != _SCENARIO2_OBSERVATION_BOUNDARIES
        or binding.observation_boundary_addresses != _SCENARIO2_OBSERVATION_BOUNDARIES
    ):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.scenario-observations-mismatch",
            "The Scenario2 observation contracts do not match the selected mapping.",
        )
    if binding.objective_addresses != _SCENARIO2_OBJECTIVES:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.scenario-objectives-mismatch",
            "The Scenario2 objective contracts do not match the selected mapping.",
        )
    return None


def _is_scenario2_resources(
    resources: tuple[CyborgScenarioResource, ...],
    scenario_binding: CyborgScenarioBinding | None,
) -> bool:
    """Match the plan against the RAES-derived selected Scenario2 closure."""

    return bool(
        scenario_binding is not None
        and scenario_binding.canonical_digest == SCENARIO2_CANONICAL_DIGEST
        and resources == scenario_binding.resources
        and _scenario2_binding_issue(scenario_binding) is None
    )


def _translate_scenario2(
    resources: tuple[CyborgScenarioResource, ...],
    scenario_binding: CyborgScenarioBinding,
) -> dict[str, dict[str, object]]:
    """Translate the exact admitted Scenario2 closure into selected native facts."""

    subnets: dict[str, object] = {
        "Enterprise": {
            "Hosts": [],
            "Size": 3,
            "NACLs": {"all": {"in": "all", "out": "all"}},
        },
        "Operational": {
            "Hosts": [],
            "Size": 4,
            "NACLs": {
                "User": {"in": "None", "out": "all"},
                "all": {"in": "all", "out": "all"},
            },
        },
        "User": {
            "Hosts": [],
            "Size": 5,
            "NACLs": {"all": {"in": "all", "out": "all"}},
        },
    }
    hosts: dict[str, object] = {}
    for resource in resources:
        if resource.resource_type != "node":
            continue
        portable_name = _required_string(resource.payload, "name")
        native_name, image = _SCENARIO2_NATIVE_HOSTS[portable_name]
        facts: dict[str, object] = {"AWS_Info": [], "image": image}
        facts.update(copy.deepcopy(_scenario2_host_facts(native_name)))
        hosts[native_name] = facts
        node = _parse_node(resource)
        assert node is not None
        for network_name in node[-1]:
            subnet = subnets[_SCENARIO2_NATIVE_NETWORKS[network_name]]
            assert isinstance(subnet, dict)
            members = subnet["Hosts"]
            assert isinstance(members, list)
            members.append(native_name)
    return {
        "Agents": _scenario2_agent_declarations(scenario_binding),
        "Subnets": subnets,
        "Hosts": hosts,
    }


def _scenario2_host_facts(native_name: str) -> dict[str, object]:
    """Return selected source host values not supplied by the image reference."""

    self_info = {native_name: {"Interfaces": "All"}}
    facts: dict[str, dict[str, object]] = {
        "Enterprise0": {
            "info": self_info,
            "ConfidentialityValue": "Medium",
            "AvailabilityValue": "Medium",
        },
        "Enterprise1": {
            "info": self_info,
            "ConfidentialityValue": "Medium",
            "AvailabilityValue": "Medium",
        },
        "Enterprise2": {
            "info": {
                "Enterprise2": {"Interfaces": "All"},
                "Op_Server0": {"Interfaces": "IP Address"},
            },
            "ConfidentialityValue": "Medium",
            "AvailabilityValue": "Medium",
        },
        "Op_Host0": {"info": self_info},
        "Op_Host1": {"info": self_info},
        "Op_Host2": {"info": self_info},
        "Op_Server0": {
            "info": {
                "Op_Server0": {
                    "Interfaces": "All",
                    "Services": ["OTService"],
                }
            },
            "ConfidentialityValue": "Medium",
            "AvailabilityValue": "High",
        },
        "User0": {
            "info": self_info,
            "ConfidentialityValue": "None",
            "AvailabilityValue": "None",
        },
        "User1": {
            "info": {
                "Enterprise1": {"Interfaces": "IP Address"},
                "User1": {"Interfaces": "All"},
            },
            "AvailabilityValue": "None",
        },
        "User2": {
            "info": {
                "Enterprise1": {"Interfaces": "IP Address"},
                "User2": {"Interfaces": "All"},
            },
            "AvailabilityValue": "None",
        },
        "User3": {
            "info": {
                "Enterprise0": {"Interfaces": "IP Address"},
                "User3": {"Interfaces": "All"},
            },
            "AvailabilityValue": "None",
        },
        "User4": {
            "info": {
                "Enterprise0": {"Interfaces": "IP Address"},
                "User4": {"Interfaces": "All"},
            },
            "AvailabilityValue": "None",
        },
    }
    return facts.get(native_name, {})


def _scenario2_native_actions(
    binding: CyborgScenarioBinding,
    participant_address: str,
) -> list[str]:
    """Derive native action names from the bound RAES participant contracts."""

    participants = {participant.address: participant for participant in binding.participants}
    participant = participants[participant_address]
    return [
        native
        for contract in participant.action_contract_addresses
        for native in _SCENARIO2_NATIVE_ACTIONS_BY_CONTRACT[contract]
    ]


def _scenario2_participant(
    binding: CyborgScenarioBinding,
    participant_address: str,
) -> CyborgParticipantBinding:
    """Return one validated compiled participant binding."""

    participants = {participant.address: participant for participant in binding.participants}
    return participants[participant_address]


def _scenario2_account_sessions(
    binding: CyborgScenarioBinding,
    participant_address: str,
) -> list[tuple[str, str]]:
    """Derive native host and synthetic username pairs from starting accounts."""

    resources = {resource.address: resource for resource in binding.resources}
    participant = _scenario2_participant(binding, participant_address)
    sessions: list[tuple[str, str]] = []
    for address in participant.starting_account_addresses:
        resource = resources[address]
        node_name = _required_string(resource.payload, "node_name")
        username = _required_string(_required_mapping(resource.payload, "spec"), "username")
        sessions.append((_SCENARIO2_NATIVE_HOSTS[node_name][0], username))
    return sessions


def _scenario2_known_hosts(
    binding: CyborgScenarioBinding,
    participant_address: str,
) -> list[str]:
    """Derive native initial host visibility from compiled knowledge addresses."""

    resources = {resource.address: resource for resource in binding.resources}
    participant = _scenario2_participant(binding, participant_address)
    return [
        _SCENARIO2_NATIVE_HOSTS[_required_string(resources[address].payload, "name")][0]
        for address in participant.initial_knowledge_addresses
        if resources[address].resource_type == "node"
    ]


def _scenario2_allowed_subnets(
    binding: CyborgScenarioBinding,
    participant_address: str,
) -> list[str]:
    """Derive native allowed subnets from compiled participant declarations."""

    resources = {resource.address: resource for resource in binding.resources}
    participant = _scenario2_participant(binding, participant_address)
    return [
        _SCENARIO2_NATIVE_NETWORKS[_required_string(resources[address].payload, "name")]
        for address in participant.allowed_subnet_addresses
    ]


def _scenario2_agent_declarations(
    binding: CyborgScenarioBinding,
) -> dict[str, object]:
    """Return the exact selected Scenario2 role, knowledge, and session surface."""

    blue_known_hosts = _scenario2_known_hosts(binding, "participant.behavior.blue")
    green_known_hosts = _scenario2_known_hosts(binding, "participant.behavior.green")
    red_known_hosts = _scenario2_known_hosts(binding, "participant.behavior.red")
    blue_visible_hosts = {
        hostname: {"Interfaces": "All", "System info": "All", "User info": "All"}
        for hostname in blue_known_hosts
    }
    green_visible_hosts = {
        hostname: {"Interfaces": "All", "System info": "All", "User info": "All"}
        for hostname in green_known_hosts
    }
    blue_accounts = _scenario2_account_sessions(binding, "participant.behavior.blue")
    blue_clients: list[dict[str, object]] = [
        {
            "hostname": native,
            "name": "Velo" + native,
            "parent": "VeloServer",
            "type": "VelociraptorClient",
            "username": username,
        }
        for native, username in blue_accounts
    ]
    defender_username = next(
        username for hostname, username in blue_accounts if hostname == "Defender"
    )
    blue_clients.append(
        {
            "artifacts": ["NetworkConnections", "ProcessCreation"],
            "hostname": "Defender",
            "name": "VeloServer",
            "num_children_sessions": 2,
            "type": "VelociraptorServer",
            "username": defender_username,
        }
    )
    green_accounts = _scenario2_account_sessions(binding, "participant.behavior.green")
    red_accounts = _scenario2_account_sessions(binding, "participant.behavior.red")
    return {
        "Blue": {
            "AllowedSubnets": _scenario2_allowed_subnets(binding, "participant.behavior.blue"),
            "INT": {"Hosts": blue_visible_hosts},
            "adversary": "Red",
            "actions": _scenario2_native_actions(binding, "participant.behavior.blue"),
            "agent_type": "SleepAgent",
            "reward_calculator_type": "HybridAvailabilityConfidentiality",
            "starting_sessions": blue_clients,
            "wrappers": [],
        },
        "Green": {
            "AllowedSubnets": _scenario2_allowed_subnets(binding, "participant.behavior.green"),
            "INT": {"Hosts": green_visible_hosts},
            "actions": _scenario2_native_actions(binding, "participant.behavior.green"),
            "agent_type": "SleepAgent",
            "reward_calculator_type": "None",
            "starting_sessions": [
                {
                    "hostname": hostname,
                    "name": "GreenSession",
                    "type": "green_session",
                    "username": username,
                }
                for hostname, username in green_accounts
            ],
            "wrappers": [],
        },
        "Red": {
            "AllowedSubnets": _scenario2_allowed_subnets(binding, "participant.behavior.red"),
            "INT": {
                "Hosts": {
                    hostname: {"Interfaces": "All", "System info": "All"}
                    for hostname in red_known_hosts
                }
            },
            "actions": _scenario2_native_actions(binding, "participant.behavior.red"),
            "agent_type": "SleepAgent",
            "reward_calculator_type": "HybridImpactPwn",
            "starting_sessions": [
                {
                    "hostname": "User0",
                    "name": "RedPhish",
                    "type": "RedAbstractSession",
                    "username": username,
                }
                for hostname, username in red_accounts
            ],
            "wrappers": [],
        },
    }


def _agent_declarations(
    hosts: dict[str, object],
    subnets: dict[str, object],
) -> dict[str, object]:
    """Declare the fixed CAGE-2 roles against the generated native topology."""

    host_names = sorted(hosts)
    subnet_names = sorted(subnets)
    first_host = host_names[0]
    visible_hosts = {
        hostname: {
            "Interfaces": "All",
            "System info": "All",
            "User info": "All",
        }
        for hostname in host_names
    }
    return {
        "Blue": {
            "AllowedSubnets": subnet_names,
            "INT": {"Hosts": visible_hosts},
            "adversary": "Red",
            "actions": list(_GENERIC_BLUE_ACTIONS),
            "agent_type": "SleepAgent",
            "reward_calculator_type": "HybridAvailabilityConfidentiality",
            "starting_sessions": _blue_starting_sessions(host_names),
            "wrappers": [],
        },
        "Green": {
            "AllowedSubnets": subnet_names,
            "INT": {"Hosts": visible_hosts},
            "actions": list(_GENERIC_GREEN_ACTIONS),
            "agent_type": "SleepAgent",
            "reward_calculator_type": "None",
            "starting_sessions": [
                {
                    "hostname": hostname,
                    "name": f"GreenSession{index}",
                    "type": "green_session",
                    "username": "GreenAgent",
                }
                for index, hostname in enumerate(host_names)
            ],
            "wrappers": [],
        },
        "Red": {
            "AllowedSubnets": subnet_names,
            "INT": {
                "Hosts": {
                    first_host: {
                        "Interfaces": "All",
                        "System info": "All",
                    }
                }
            },
            "actions": list(_GENERIC_RED_ACTIONS),
            "agent_type": "SleepAgent",
            "reward_calculator_type": "HybridImpactPwn",
            "starting_sessions": [
                {
                    "hostname": first_host,
                    "name": "RedPhish",
                    "type": "RedAbstractSession",
                    "username": "SYSTEM",
                }
            ],
            "wrappers": [],
        },
    }


def _blue_starting_sessions(host_names: list[str]) -> list[dict[str, object]]:
    """Create one Velociraptor server and generated clients for Blue."""

    first_host = host_names[0]
    sessions: list[dict[str, object]] = [
        {
            "artifacts": ["NetworkConnections", "ProcessCreation"],
            "hostname": first_host,
            "name": "VeloServer",
            "num_children_sessions": min(2, max(1, len(host_names))),
            "type": "VelociraptorServer",
            "username": "ubuntu",
        }
    ]
    sessions.extend(
        {
            "hostname": hostname,
            "name": f"VeloClient{index}",
            "parent": "VeloServer",
            "type": "VelociraptorClient",
            "username": "ubuntu",
        }
        for index, hostname in enumerate(host_names)
    )
    return sessions


def _validate_network(
    resource: CyborgScenarioResource,
    names: set[str],
) -> CyborgTranslationIssue | None:
    """Validate one compiled switch and reserve its native subnet name."""

    facts = _parse_network(resource)
    issue: CyborgTranslationIssue | None = None
    if facts is None:
        issue = CyborgTranslationIssue(
            "cyborg-backend.plan.invalid-network",
            "A network resource is not a complete compiled RAES switch descriptor.",
        )
    else:
        name, node, count, links, acls, properties = facts
        if name in names:
            issue = CyborgTranslationIssue(
                "cyborg-backend.plan.native-name-collision",
                "Multiple RAES resources would produce the same native CybORG name.",
            )
        elif node.get("type") != "switch" or count != 1:
            issue = CyborgTranslationIssue(
                "cyborg-backend.plan.unsupported-network-shape",
                "CybORG represents each admitted RAES switch as exactly one subnet.",
            )
        elif _has_unsupported_switch_detail(node) or links or acls or properties.get("internal"):
            issue = CyborgTranslationIssue(
                "cyborg-backend.plan.unsupported-network-detail",
                "Linked switches and authored network ACLs are not supported "
                "by this CybORG mapping.",
            )
        else:
            names.add(name)
    return issue


def _parse_network(resource: CyborgScenarioResource) -> _NetworkFacts | None:
    """Parse the exact compiled switch payload shape without accepting extras."""

    facts: _NetworkFacts | None = None
    payload = resource.payload
    try:
        _require_exact_keys(payload, _NETWORK_PAYLOAD_KEYS)
        name = _required_string(payload, "name")
        _require_equal(payload.get("node_name"), name)
        spec = _required_mapping(payload, "spec")
        _require_exact_keys(spec, _SPEC_KEYS)
        node = _required_mapping(spec, "node")
        infrastructure = _required_mapping(spec, "infrastructure")
        _require_exact_keys(node, _COMPILED_NODE_KEYS)
        _require_exact_keys(infrastructure, _COMPILED_INFRASTRUCTURE_KEYS)
        count = _required_positive_int(infrastructure, "count")
        links = _required_string_list(infrastructure, "links")
        _required_string_list(infrastructure, "dependencies")
        acls = _required_list(infrastructure, "acls")
        properties = _network_properties(infrastructure)
        facts = name, node, count, links, acls, properties
    except (KeyError, TypeError, ValueError):
        facts = None
    return facts


def _validate_node(
    resource: CyborgScenarioResource,
    network_names: set[str],
    native_names: set[str],
) -> CyborgTranslationIssue | None:
    """Validate one compiled VM and reserve every expanded native host name."""

    facts = _parse_node(resource)
    if facts is None:
        return CyborgTranslationIssue(_INVALID_NODE_CODE, _INVALID_NODE_MESSAGE)
    issue = _node_semantic_issue(resource.payload, facts, network_names)
    if issue is None:
        name, count, *_ = facts
        issue = _reserve_native_names(name, count, native_names)
    return issue


def _node_semantic_issue(
    payload: dict[str, object],
    facts: _NodeFacts,
    network_names: set[str],
) -> CyborgTranslationIssue | None:
    """Return the first semantic loss or inconsistency in parsed VM facts."""

    _, count, os_family, node, infrastructure, infrastructure_count, links = facts
    issue: CyborgTranslationIssue | None = None
    if payload.get("node_type") != "vm" or node.get("type") != "vm":
        issue = CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-node-type",
            "The CybORG scenario mapping supports VM nodes and switch networks.",
        )
    elif os_family not in _IMAGE_BY_OS_FAMILY or node.get("os") != os_family:
        issue = CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-os-family",
            "The CybORG scenario mapping has no selected image for the requested OS family.",
        )
    elif infrastructure_count != count:
        issue = CyborgTranslationIssue(_INVALID_NODE_CODE, _INVALID_NODE_MESSAGE)
    elif not links:
        issue = CyborgTranslationIssue(
            "cyborg-backend.plan.unattached-node",
            "Every CybORG host must be attached to at least one admitted RAES network.",
        )
    elif any(link not in network_names for link in links):
        issue = CyborgTranslationIssue(
            "cyborg-backend.plan.unknown-network",
            "A CybORG host references a network absent from the complete desired state.",
        )
    elif len(links) != len(set(links)):
        issue = CyborgTranslationIssue(_INVALID_NODE_CODE, _INVALID_NODE_MESSAGE)
    elif _has_unsupported_node_detail(payload, node, infrastructure):
        issue = CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-node-detail",
            "The RAES node requests a fact the selected CybORG image mapping cannot preserve.",
        )
    return issue


def _reserve_native_names(
    name: str,
    count: int,
    native_names: set[str],
) -> CyborgTranslationIssue | None:
    """Reserve expanded host names or report a native-name collision."""

    expanded = _expanded_names(name, count)
    issue: CyborgTranslationIssue | None = None
    if any(hostname in native_names for hostname in expanded):
        issue = CyborgTranslationIssue(
            "cyborg-backend.plan.native-name-collision",
            "Multiple RAES resources would produce the same native CybORG name.",
        )
    else:
        native_names.update(expanded)
    return issue


def _parse_node(resource: CyborgScenarioResource) -> _NodeFacts | None:
    """Parse the exact compiled VM payload shape without accepting extras."""

    facts: _NodeFacts | None = None
    payload = resource.payload
    try:
        _require_exact_keys(payload, _NODE_PAYLOAD_KEYS)
        name = _required_string(payload, "name")
        _require_equal(payload.get("node_name"), name)
        count = _required_positive_int(payload, "count")
        os_family = _required_string(payload, "os_family")
        spec = _required_mapping(payload, "spec")
        _require_exact_keys(spec, _SPEC_KEYS)
        node = _required_mapping(spec, "node")
        infrastructure = _required_mapping(spec, "infrastructure")
        _require_exact_keys(node, _COMPILED_NODE_KEYS)
        _require_exact_keys(infrastructure, _COMPILED_INFRASTRUCTURE_KEYS)
        infrastructure_count = _required_positive_int(infrastructure, "count")
        links = _required_string_list(infrastructure, "links")
        _required_string_list(infrastructure, "dependencies")
        _required_list(infrastructure, "acls")
        facts = name, count, os_family, node, infrastructure, infrastructure_count, links
    except (KeyError, TypeError, ValueError):
        facts = None
    return facts


def _has_unsupported_node_detail(
    payload: dict[str, object],
    node: dict[str, object],
    infrastructure: dict[str, object],
) -> bool:
    """Detect compiled VM facts outside the selected image mapping."""

    unsupported_node_fields = (
        "source",
        "resources",
        "asset_value",
        "endpoint_persona",
        "runtime",
    )
    unsupported_node_collections = (
        "features",
        "conditions",
        "injects",
        "vulnerabilities",
        "roles",
        "services",
    )
    return (
        any(node.get(field) is not None for field in unsupported_node_fields)
        or any(bool(node.get(field)) for field in unsupported_node_collections)
        or bool(node.get("os_version"))
        or infrastructure.get("properties") is not None
        or bool(infrastructure.get("acls"))
        or bool(payload.get("network_namespace_target"))
        or payload.get("domain_topology") is not None
    )


def _has_unsupported_switch_detail(node: dict[str, object]) -> bool:
    """Detect compiled switch facts outside the selected subnet mapping."""

    unsupported_fields = (
        "source",
        "resources",
        "os",
        "asset_value",
        "endpoint_persona",
        "runtime",
    )
    unsupported_collections = (
        "features",
        "conditions",
        "injects",
        "vulnerabilities",
        "roles",
        "services",
    )
    return (
        any(node.get(field) is not None for field in unsupported_fields)
        or any(bool(node.get(field)) for field in unsupported_collections)
        or bool(node.get("os_version"))
    )


def _network_properties(infrastructure: dict[str, object]) -> dict[str, object]:
    """Return a strictly shaped network-property mapping."""

    candidate = infrastructure["properties"]
    if candidate is None:
        return {}
    if (
        not isinstance(candidate, dict)
        or set(candidate) != _NETWORK_PROPERTY_KEYS
        or not isinstance(candidate.get("cidr"), str)
        or not candidate["cidr"]
        or not isinstance(candidate.get("gateway"), str)
        or not candidate["gateway"]
        or type(candidate.get("internal")) is not bool
    ):
        raise TypeError
    return candidate


def _expanded_names(name: str, count: int) -> tuple[str, ...]:
    """Expand one RAES counted resource into deterministic native names."""

    if count == 1:
        return (name,)
    return tuple(f"{name}-{index}" for index in range(count))


def _required_mapping(value: dict[str, object], key: str) -> dict[str, object]:
    """Return one required mapping value or reject the payload shape."""

    candidate = value[key]
    if not isinstance(candidate, dict):
        raise TypeError
    return candidate


def _required_string(value: dict[str, object], key: str) -> str:
    """Return one required non-empty string value."""

    candidate = value[key]
    if not isinstance(candidate, str) or not candidate:
        raise TypeError
    return candidate


def _required_positive_int(value: dict[str, object], key: str) -> int:
    """Return one required positive integer value, excluding booleans."""

    candidate = value[key]
    if type(candidate) is not int or candidate < 1:
        raise TypeError
    return candidate


def _required_string_list(value: dict[str, object], key: str) -> tuple[str, ...]:
    """Return one required list of non-empty strings as an immutable tuple."""

    candidate = value[key]
    if not isinstance(candidate, list) or any(
        not isinstance(item, str) or not item for item in candidate
    ):
        raise TypeError
    return tuple(candidate)


def _required_list(value: dict[str, object], key: str) -> list[object]:
    """Return one required list value."""

    candidate = value[key]
    if not isinstance(candidate, list):
        raise TypeError
    return candidate


def _require_exact_keys(value: dict[str, object], expected: frozenset[str]) -> None:
    """Reject a compiled mapping that omits or adds any field."""

    if set(value) != expected:
        raise ValueError


def _require_equal(actual: object, expected: object) -> None:
    """Reject inconsistent duplicate fields in a compiled descriptor."""

    if actual != expected:
        raise ValueError


__all__ = [
    "CYBORG_SCENARIO_MAPPING_VERSION",
    "SCENARIO2_CANONICAL_DIGEST",
    "CyborgParticipantBinding",
    "CyborgScenarioBinding",
    "CyborgScenarioDescriptor",
    "CyborgScenarioResource",
    "CyborgTranslationIssue",
    "bind_scenario_profile",
    "copied_resource",
    "host_address_map",
    "translate_scenario",
    "validate_scenario_resources",
]
