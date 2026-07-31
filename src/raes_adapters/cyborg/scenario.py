"""Deterministic projection of admitted RAES resources into CybORG scenario data."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class CyborgScenarioResource:
    """One copied admitted RAES resource supplied to native construction."""

    address: str
    resource_type: str
    payload: dict[str, object]
    ordering_dependencies: tuple[str, ...]
    refresh_dependencies: tuple[str, ...]


@dataclass(frozen=True)
class CyborgScenarioDescriptor:
    """Private construction input derived from a complete desired RAES state."""

    profile_id: str
    source_commit: str
    mapping_version: str
    resources: tuple[CyborgScenarioResource, ...]


@dataclass(frozen=True)
class CyborgTranslationIssue:
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

    unsupported_types = sorted(
        {resource.resource_type for resource in resources} - _SUPPORTED_RESOURCE_TYPES
    )
    if unsupported_types:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-resource",
            "The provisioning plan contains a resource CybORG cannot represent.",
        )

    networks = tuple(resource for resource in resources if resource.resource_type == "network")
    nodes = tuple(resource for resource in resources if resource.resource_type == "node")
    if not networks or not nodes:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.incomplete-scenario",
            "CybORG construction requires at least one network and one attached VM.",
        )

    network_names: set[str] = set()
    for resource in networks:
        issue = _validate_network(resource, network_names)
        if issue is not None:
            return issue

    native_host_names: set[str] = set()
    for resource in nodes:
        issue = _validate_node(resource, network_names, native_host_names)
        if issue is not None:
            return issue
    return None


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
        "Agents": {},
        "Subnets": subnets,
        "Hosts": hosts,
    }


def _validate_network(
    resource: CyborgScenarioResource,
    names: set[str],
) -> CyborgTranslationIssue | None:
    payload = resource.payload
    try:
        if set(payload) != _NETWORK_PAYLOAD_KEYS:
            raise ValueError
        name = _required_string(payload, "name")
        if payload.get("node_name") != name:
            raise ValueError
        spec = _required_mapping(payload, "spec")
        if set(spec) != _SPEC_KEYS:
            raise ValueError
        node = _required_mapping(spec, "node")
        infrastructure = _required_mapping(spec, "infrastructure")
        if set(node) != _COMPILED_NODE_KEYS or set(infrastructure) != _COMPILED_INFRASTRUCTURE_KEYS:
            raise ValueError
        count = _required_positive_int(infrastructure, "count")
        links = _required_string_list(infrastructure, "links")
        _required_string_list(infrastructure, "dependencies")
        acls = _required_list(infrastructure, "acls")
        properties = _network_properties(infrastructure)
    except (KeyError, TypeError, ValueError):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.invalid-network",
            "A network resource is not a complete compiled RAES switch descriptor.",
        )
    if name in names:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.native-name-collision",
            "Multiple RAES resources would produce the same native CybORG name.",
        )
    names.add(name)
    if node.get("type") != "switch" or count != 1:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-network-shape",
            "CybORG represents each admitted RAES switch as exactly one subnet.",
        )
    if _has_unsupported_switch_detail(node) or links or acls or properties.get("internal"):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-network-detail",
            "Linked switches and authored network ACLs are not supported by this CybORG mapping.",
        )
    return None


def _validate_node(
    resource: CyborgScenarioResource,
    network_names: set[str],
    native_names: set[str],
) -> CyborgTranslationIssue | None:
    payload = resource.payload
    try:
        if set(payload) != _NODE_PAYLOAD_KEYS:
            raise ValueError
        name = _required_string(payload, "name")
        if payload.get("node_name") != name:
            raise ValueError
        count = _required_positive_int(payload, "count")
        os_family = _required_string(payload, "os_family")
        spec = _required_mapping(payload, "spec")
        if set(spec) != _SPEC_KEYS:
            raise ValueError
        node = _required_mapping(spec, "node")
        infrastructure = _required_mapping(spec, "infrastructure")
        if set(node) != _COMPILED_NODE_KEYS or set(infrastructure) != _COMPILED_INFRASTRUCTURE_KEYS:
            raise ValueError
        infrastructure_count = _required_positive_int(infrastructure, "count")
        links = _required_string_list(infrastructure, "links")
        _required_string_list(infrastructure, "dependencies")
        _required_list(infrastructure, "acls")
    except (KeyError, TypeError, ValueError):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.invalid-node",
            "A node resource is not a complete compiled RAES VM descriptor.",
        )

    if payload.get("node_type") != "vm" or node.get("type") != "vm":
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-node-type",
            "The CybORG scenario mapping supports VM nodes and switch networks.",
        )
    if os_family not in _IMAGE_BY_OS_FAMILY or node.get("os") != os_family:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-os-family",
            "The CybORG scenario mapping has no selected image for the requested OS family.",
        )
    if infrastructure_count != count:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.invalid-node",
            "A node resource is not a complete compiled RAES VM descriptor.",
        )
    if not links:
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unattached-node",
            "Every CybORG host must be attached to at least one admitted RAES network.",
        )
    if any(link not in network_names for link in links):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unknown-network",
            "A CybORG host references a network absent from the complete desired state.",
        )
    if len(links) != len(set(links)):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.invalid-node",
            "A node resource is not a complete compiled RAES VM descriptor.",
        )
    if _has_unsupported_node_detail(payload, node, infrastructure):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.unsupported-node-detail",
            "The RAES node requests a fact the selected CybORG image mapping cannot preserve.",
        )

    expanded = _expanded_names(name, count)
    if any(hostname in native_names for hostname in expanded):
        return CyborgTranslationIssue(
            "cyborg-backend.plan.native-name-collision",
            "Multiple RAES resources would produce the same native CybORG name.",
        )
    native_names.update(expanded)
    return None


def _has_unsupported_node_detail(
    payload: dict[str, object],
    node: dict[str, object],
    infrastructure: dict[str, object],
) -> bool:
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
    if count == 1:
        return (name,)
    return tuple(f"{name}-{index}" for index in range(count))


def _required_mapping(value: dict[str, object], key: str) -> dict[str, Any]:
    candidate = value[key]
    if not isinstance(candidate, dict):
        raise TypeError
    return candidate


def _required_string(value: dict[str, object], key: str) -> str:
    candidate = value[key]
    if not isinstance(candidate, str) or not candidate:
        raise TypeError
    return candidate


def _required_positive_int(value: dict[str, object], key: str) -> int:
    candidate = value[key]
    if type(candidate) is not int or candidate < 1:
        raise TypeError
    return candidate


def _required_string_list(value: dict[str, object], key: str) -> tuple[str, ...]:
    candidate = value[key]
    if not isinstance(candidate, list) or any(
        not isinstance(item, str) or not item for item in candidate
    ):
        raise TypeError
    return tuple(candidate)


def _required_list(value: dict[str, object], key: str) -> list[object]:
    candidate = value[key]
    if not isinstance(candidate, list):
        raise TypeError
    return candidate


__all__ = [
    "CYBORG_SCENARIO_MAPPING_VERSION",
    "CyborgScenarioDescriptor",
    "CyborgScenarioResource",
    "CyborgTranslationIssue",
    "copied_resource",
    "translate_scenario",
    "validate_scenario_resources",
]
