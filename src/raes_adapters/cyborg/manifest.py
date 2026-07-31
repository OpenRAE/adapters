"""Evidence-bounded manifest for the selected CybORG/CAGE-2 backend."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import Any

from raes_backend_protocols.capabilities import (  # type: ignore[import-untyped]
    BackendCapabilitySet,
    BackendManifest,
    ProvisionerCapabilities,
)
from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_contracts.apparatus import (  # type: ignore[import-untyped]
    ConceptBinding,
    RealizationSupportDeclaration,
)
from raes_contracts.realization_envelope import (  # type: ignore[import-untyped]
    BackendRealizationEnvelopeModel,
    realization_envelope_digest,
    realizer_configuration_digest,
    validate_backend_realization_envelope,
)
from raes_contracts.vocabulary import RealizationSupportMode  # type: ignore[import-untyped]

from .scenario import CYBORG_SCENARIO_MAPPING_VERSION

CYBORG_BACKEND_NAME = "cyborg-cage2"
CYBORG_PROFILE_ID = "cage2-cyborg-2.1-source-26ce1c1"

_SUPPORTED_CONTRACTS = frozenset(
    {
        "backend-manifest-v2",
        "operation-receipt-v1",
        "operation-status-v1",
        "provisioning-plan-v1",
        "realization-envelope-v1",
        "runtime-snapshot-v1",
    }
)


def _current_backend_version() -> str:
    try:
        return distribution_version("raes-adapters")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def create_cyborg_realization_envelope(
    *,
    seed: int | None = None,
) -> BackendRealizationEnvelopeModel:
    """Return the validated disclosure for generated native construction."""

    configuration: dict[str, Any] = {
        "mode": "raes-scenario-projection",
        "architecture": "mixed",
        "image_policy": (
            f"{CYBORG_PROFILE_ID}:{CYBORG_SCENARIO_MAPPING_VERSION}:"
            "linux=linux_decoy_host,windows=windows_user_host1"
        ),
        "network_policy": (
            "cyborg-v2.1-private-address-allocation;"
            f"seed={seed if seed is not None else 'unseeded'}"
        ),
        "supported_node_types": ["switch", "vm"],
        "supported_os_families": ["linux", "windows"],
        "supported_content_types": [],
        "supported_account_features": [],
        "supported_domain_profiles": [],
        "supports_acls": False,
        "memory_mib": {"minimum": 1, "maximum": None},
        "vcpus": {"minimum": 1, "maximum": None},
    }
    configuration["configuration_digest"] = realizer_configuration_digest(configuration)
    unsupported: dict[str, Any] = {
        "disposition": "unsupported",
        "observation_strength": "none",
        "mechanism": None,
        "transformations": [],
    }
    descriptor: dict[str, Any] = {
        "disposition": "descriptor-only",
        "observation_strength": "driver-reported",
        "mechanism": "generated-raes-scenario-v1",
        "transformations": [],
    }
    topology: dict[str, Any] = {
        "disposition": "transformed",
        "observation_strength": "driver-reported",
        "mechanism": "generated-raes-scenario-v1",
        "transformations": ["bounded-normalization"],
    }
    image: dict[str, Any] = {
        "disposition": "transformed",
        "observation_strength": "driver-reported",
        "mechanism": "selected-cyborg-image-catalog",
        "transformations": ["image-substitution", "default-substitution"],
    }
    network: dict[str, Any] = {
        "disposition": "transformed",
        "observation_strength": "driver-reported",
        "mechanism": "cyborg-v2.1-private-address-allocation",
        "transformations": ["descriptor-substitution"],
    }
    payload: dict[str, Any] = {
        "schema_version": "realization-envelope/v1",
        "contract_id": "realization-envelope-v1",
        "id": "cyborg-cage2.raes-scenario.v1",
        "expression": {
            "schema_version": "realization-envelope/v1",
            "id": "cyborg-cage2.raes-scenario.expression.v1",
            "scope": "scenario",
            "domains": {},
            "bindings": [],
            "closure": [],
        },
        "configuration": configuration,
        "concerns": [
            {"concern": "topology", **topology},
            {"concern": "architecture", **descriptor},
            {"concern": "image", **image},
            {"concern": "resource-allocation", **unsupported},
            {"concern": "network", **network},
            {"concern": "content-placement", **unsupported},
            {"concern": "account-placement", **unsupported},
            {"concern": "feature-binding", **unsupported},
            {"concern": "service", **unsupported},
            {"concern": "acl", **unsupported},
        ],
    }
    payload["digest"] = realization_envelope_digest(payload)
    return validate_backend_realization_envelope(payload)


def _provisioner_capabilities(
    envelope: BackendRealizationEnvelopeModel,
) -> ProvisionerCapabilities:
    configuration = envelope.configuration
    return ProvisionerCapabilities(
        name="cyborg-cage2-provisioner",
        supported_node_types=frozenset(configuration.supported_node_types),
        supported_os_families=frozenset(configuration.supported_os_families),
        supported_content_types=frozenset(configuration.supported_content_types),
        supported_account_features=frozenset(configuration.supported_account_features),
        supported_domain_profiles=frozenset(configuration.supported_domain_profiles),
        supported_service_materialization_profiles=frozenset(),
        max_total_nodes=None,
        supports_acls=configuration.supports_acls,
        supports_accounts=bool(configuration.supported_account_features),
        constraints={
            "scenario_projection": (
                "The complete admitted RAES network and VM desired state is "
                "deterministically projected into a generated CybORG scenario."
            )
        },
    )


def create_cyborg_manifest(**config: object) -> BackendManifest:
    """Return the provisioning-only manifest for the selected backend."""

    seed = config.get("seed")
    if seed is not None and (type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF):
        raise ValueError("CybORG seed must be an unsigned 32-bit integer.")
    envelope = create_cyborg_realization_envelope(
        seed=seed if isinstance(seed, int) else None,
    )
    manifest = BackendManifest(
        name=CYBORG_BACKEND_NAME,
        version=_current_backend_version(),
        supported_contract_versions=_SUPPORTED_CONTRACTS,
        compatible_processors=frozenset({"raes-reference-processor"}),
        concept_bindings=(
            ConceptBinding(
                scope="capabilities.provisioner.supported_node_types",
                family="assets",
            ),
            ConceptBinding(
                scope="capabilities.provisioner.supported_os_families",
                family="assets",
            ),
            ConceptBinding(
                scope="capabilities.provisioner.supported_content_types",
                family="tools-and-artifacts",
            ),
            ConceptBinding(
                scope="capabilities.provisioner.supported_account_features",
                family="identities",
            ),
            ConceptBinding(
                scope="capabilities.provisioner.supported_domain_profiles",
                family="identities",
            ),
            ConceptBinding(
                scope="capabilities.provisioner.supported_service_materialization_profiles",
                family="tools-and-artifacts",
            ),
        ),
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset({"node-type", "os-family"}),
                supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
                disclosure_kinds=frozenset(
                    {
                        "backend-manifest-v2",
                        "operation-status-v1",
                        "runtime-snapshot-v1",
                    }
                ),
            ),
        ),
        capabilities=BackendCapabilitySet(
            provisioner=_provisioner_capabilities(envelope),
        ),
        realization_envelope=envelope,
        constraints={
            "profile": CYBORG_PROFILE_ID,
            "source_installation": (
                "CybORG 2.1 must be installed from the maintainer-selected CAGE-2 "
                "source profile until its packaging fix is published."
            ),
            "equivalence": (
                "Provisioning records and constructs the admitted RAES topology; "
                "CybORG substitutes selected OS images and native private addresses. "
                "This provisioning-only target makes no action, observation, "
                "evaluation, or outcome-equivalence claim."
            ),
        },
    )
    backend_manifest_payload(manifest)
    return manifest


__all__ = [
    "CYBORG_BACKEND_NAME",
    "CYBORG_PROFILE_ID",
    "create_cyborg_manifest",
    "create_cyborg_realization_envelope",
]
