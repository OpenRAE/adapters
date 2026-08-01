"""Deterministic projection of admitted RAES resources into CybORG scenario data."""

from __future__ import annotations

import copy
from typing import NamedTuple

_IMAGE_BY_OS_FAMILY = {
    "linux": "linux_decoy_host",
    "windows": "windows_user_host1",
}
_SUPPORTED_RESOURCE_TYPES = frozenset({"network", "node"})
CYBORG_SCENARIO_MAPPING_VERSION = "raes-cyborg-scenario-v1"
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
_BLUE_ACTIONS = [
    "Sleep",
    "Monitor",
    "Analyse",
    "Remove",
    "Restore",
]
_GREEN_ACTIONS = [
    "Sleep",
    "GreenPingSweep",
    "GreenPortScan",
    "GreenConnection",
]
_RED_ACTIONS = [
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


class CyborgScenarioDescriptor(NamedTuple):
    """Private construction input derived from a complete desired RAES state."""

    profile_id: str
    source_commit: str
    mapping_version: str
    resources: tuple[CyborgScenarioResource, ...]


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


def validate_scenario_resources(
    resources: tuple[CyborgScenarioResource, ...],
) -> CyborgTranslationIssue | None:
    """Return the first deterministic representability failure, if any."""

    issue = _unsupported_resource_issue(resources)
    if issue is None:
        networks = tuple(resource for resource in resources if resource.resource_type == "network")
        nodes = tuple(resource for resource in resources if resource.resource_type == "node")
        issue = _validate_complete_scenario(networks, nodes)
    return issue


def _unsupported_resource_issue(
    resources: tuple[CyborgScenarioResource, ...],
) -> CyborgTranslationIssue | None:
    """Reject resource kinds outside the provisioning-only mapping."""

    unsupported_types = sorted(
        {resource.resource_type for resource in resources} - _SUPPORTED_RESOURCE_TYPES
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
    issue = validate_scenario_resources(resources)
    if issue is not None:
        raise ValueError(issue.message)

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
            "actions": list(_BLUE_ACTIONS),
            "agent_type": "SleepAgent",
            "reward_calculator_type": "HybridAvailabilityConfidentiality",
            "starting_sessions": _blue_starting_sessions(host_names),
            "wrappers": [],
        },
        "Green": {
            "AllowedSubnets": subnet_names,
            "INT": {"Hosts": visible_hosts},
            "actions": list(_GREEN_ACTIONS),
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
            "actions": list(_RED_ACTIONS),
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
    "CyborgScenarioDescriptor",
    "CyborgScenarioResource",
    "CyborgTranslationIssue",
    "copied_resource",
    "translate_scenario",
    "validate_scenario_resources",
]
