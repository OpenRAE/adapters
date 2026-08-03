"""Backend-neutral installed-source admission for index-published simulators.

A gym-style simulator adapter installs its selected source and pinned runtime as
ordinary distributions, then must attest — before importing anything native —
that the installed artifacts are exactly the qualified ones: the right
versions, complete symlink-free import-root trees, applicable direct-archive
provenance, and module origins that resolve inside the selected distributions.

This module is the single shared implementation of those mechanics (see the
NASim backend guardrails "Installed-source admission" row: extract only a
backend-neutral private verifier; expected roots, versions, digests, and
admission policy stay backend-local evidence). The caller supplies the qualified
identities read from its own ``qualification.json``; nothing here is
simulator-specific. Native values are never inspected or rendered — every
failure is a bounded, fixed message.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from importlib.util import find_spec
from pathlib import Path, PurePosixPath
from typing import cast

QUALIFICATION_INVALID = "selected simulator qualification is invalid"
SOURCE_IDENTITY_INVALID = "selected simulator source identity could not be verified"
DEPENDENCY_IDENTITY_INVALID = "selected simulator dependency identity could not be verified"
MODULE_ORIGIN_INVALID = "selected simulator module origin could not be verified"
NOT_INSTALLED = "selected simulator source is not installed"
VERSION_MISMATCH = "installed simulator version does not match the selected source"


def resolve_selected_distribution(package: str, expected_version: str) -> Distribution:
    """Resolve the installed selected distribution and confirm its version."""

    try:
        selected_distribution = distribution(package)
    except PackageNotFoundError as exc:
        raise RuntimeError(NOT_INSTALLED) from exc
    if selected_distribution.version != expected_version:
        raise RuntimeError(VERSION_MISMATCH)
    return selected_distribution


def verify_runtime_artifacts(
    qualification: dict[str, object],
    selected_distribution: Distribution,
    *,
    expected_names: frozenset[str],
    primary_name: str,
) -> dict[str, Distribution]:
    """Verify the complete selected runtime artifact set.

    ``expected_names`` is the exact set of artifact records the selection
    declares (the selected source plus its pinned runtime). ``primary_name`` is
    the already-resolved selected distribution's artifact name.
    """

    selected_versions, records = _artifact_maps(qualification, expected_names)
    verified: dict[str, Distribution] = {primary_name: selected_distribution}
    for package_name, record in records.items():
        dependency = _verify_runtime_artifact(
            package_name,
            record,
            selected_versions,
            verified,
        )
        verified[package_name] = dependency
    return verified


def verify_selected_source_files(
    qualification: dict[str, object],
    selected_distribution: Distribution,
    *,
    source_paths: Sequence[str],
) -> None:
    """Verify each declared source file digest against the installed tree."""

    source_files = qualification.get("source_files")
    if not isinstance(source_files, list):
        raise RuntimeError(SOURCE_IDENTITY_INVALID)
    expected: dict[str, str] = {}
    for entry in source_files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        digest = entry.get("sha256")
        if isinstance(path, str) and isinstance(digest, str):
            expected[path] = digest
    try:
        for source_path in source_paths:
            expected_digest = expected[source_path]
            installed_source = cast(Path, selected_distribution.locate_file(source_path))
            content = installed_source.read_bytes()
            if hashlib.sha256(content).hexdigest() != expected_digest:
                raise RuntimeError(SOURCE_IDENTITY_INVALID)
    except (KeyError, OSError) as exc:
        raise RuntimeError(SOURCE_IDENTITY_INVALID) from exc


def verify_runtime_source_tree(
    qualification: dict[str, object],
    selected_distribution: Distribution,
    *,
    import_root: str,
) -> None:
    """Verify every installed file under the selected source import root.

    Use this only when the installed distribution IS the complete selected
    source tree (a source install). A wheel install whose importable tree is a
    subset of the recorded git ``runtime_source_tree`` verifies the installed
    tree through :func:`verify_runtime_artifacts` instead.
    """

    tree = qualification.get("runtime_source_tree")
    distribution_files = selected_distribution.files
    if not isinstance(tree, dict) or distribution_files is None:
        raise RuntimeError(SOURCE_IDENTITY_INVALID)
    expected_digest = tree.get("sha256")
    expected_count = tree.get("file_count")
    if not isinstance(expected_digest, str) or not isinstance(expected_count, int):
        raise RuntimeError(SOURCE_IDENTITY_INVALID)
    paths = _runtime_root_paths(
        selected_distribution,
        import_root,
        SOURCE_IDENTITY_INVALID,
    )
    if len(paths) != expected_count:
        raise RuntimeError(SOURCE_IDENTITY_INVALID)
    package_root = cast(Path, selected_distribution.locate_file(import_root)).resolve()
    observed_digest = _installed_tree_digest(
        selected_distribution,
        paths,
        SOURCE_IDENTITY_INVALID,
        root_path=import_root,
        package_root=package_root,
    )
    if observed_digest != expected_digest:
        raise RuntimeError(SOURCE_IDENTITY_INVALID)


def verify_package_origin(
    module_name: str,
    selected_distribution: Distribution,
    expected_relative_path: str,
) -> None:
    """Verify a resolvable module resolves inside the selected distribution."""

    module_spec = find_spec(module_name)
    origin = module_spec.origin if module_spec is not None else None
    expected = cast(Path, selected_distribution.locate_file(expected_relative_path)).resolve()
    if not isinstance(origin, str) or Path(origin).resolve() != expected:
        raise RuntimeError(MODULE_ORIGIN_INVALID)


def _artifact_maps(
    qualification: dict[str, object],
    expected_names: frozenset[str],
) -> tuple[dict[str, str], dict[str, dict[object, object]]]:
    """Index selected dependency versions and runtime artifact records."""

    artifacts = qualification.get("runtime_artifacts")
    dependencies = qualification.get("dependencies")
    if not isinstance(artifacts, list) or not isinstance(dependencies, list):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    selected_versions = {
        str(entry["name"]).casefold(): entry["version"]
        for entry in dependencies
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and isinstance(entry.get("version"), str)
    }
    records = {
        str(entry["name"]).casefold(): entry
        for entry in artifacts
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    if set(records) != expected_names:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    return selected_versions, records


def _verify_runtime_artifact(
    package_name: str,
    record: dict[object, object],
    selected_versions: dict[str, str],
    verified: dict[str, Distribution],
) -> Distribution:
    """Verify one selected artifact record and installed distribution."""

    expected_version = _validate_artifact_identity(package_name, record, selected_versions)
    dependency = _resolve_distribution(package_name, verified)
    if dependency.version != expected_version:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    _verify_direct_installation(record, dependency)
    _verify_artifact_roots(record, dependency)
    return dependency


def _validate_artifact_identity(
    package_name: str,
    record: dict[object, object],
    selected_versions: dict[str, str],
) -> str:
    """Validate one artifact's declared version and identity policy."""

    expected_version = record.get("version")
    artifact = record.get("artifact")
    if not isinstance(expected_version, str) or not isinstance(artifact, dict):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    valid = (
        isinstance(artifact.get("filename"), str)
        and _is_sha256(artifact.get("sha256"))
        and isinstance(artifact.get("require_direct_archive_sha256"), bool)
        and artifact.get("runtime_identity") == "complete-root-tree"
        and selected_versions.get(package_name) == expected_version
    )
    if not valid:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    return expected_version


def _resolve_distribution(
    package_name: str,
    verified: dict[str, Distribution],
) -> Distribution:
    """Resolve an installed distribution without leaking package metadata."""

    dependency = verified.get(package_name)
    if dependency is not None:
        return dependency
    try:
        return distribution(package_name)
    except PackageNotFoundError as exc:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID) from exc


def _verify_direct_installation(
    record: dict[object, object],
    selected_distribution: Distribution,
) -> None:
    """Reject unverifiable editable/VCS installs and check archive identity."""

    direct_url_text = _direct_url_text(selected_distribution)
    if direct_url_text is None:
        return
    expected_digest, require_archive_digest = _direct_artifact_policy(record)
    direct_url = _load_direct_url(direct_url_text)
    if not {"dir_info", "vcs_info"}.isdisjoint(direct_url):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    observed_digest = _archive_sha256(direct_url)
    if require_archive_digest and observed_digest != expected_digest:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)


def _direct_url_text(selected_distribution: Distribution) -> str | None:
    """Read optional direct-install provenance from a distribution."""

    read_text = getattr(selected_distribution, "read_text", None)
    if not callable(read_text):
        return None
    direct_url_text = read_text("direct_url.json")
    if direct_url_text is not None and not isinstance(direct_url_text, str):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    return direct_url_text


def _direct_artifact_policy(record: dict[object, object]) -> tuple[str, bool]:
    """Read the selected archive digest policy from an artifact record."""

    artifact = record.get("artifact")
    if not isinstance(artifact, dict):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    expected_digest = artifact.get("sha256")
    require_archive_digest = artifact.get("require_direct_archive_sha256")
    if not isinstance(expected_digest, str):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    if not isinstance(require_archive_digest, bool):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    return expected_digest, require_archive_digest


def _load_direct_url(direct_url_text: str) -> dict[object, object]:
    """Decode a direct-install provenance record as a JSON object."""

    try:
        direct_url = json.loads(direct_url_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID) from exc
    if not isinstance(direct_url, dict):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    return direct_url


def _archive_sha256(direct_url: dict[object, object]) -> object:
    """Read modern or legacy SHA-256 metadata from a direct archive."""

    archive_info = direct_url.get("archive_info")
    hashes = archive_info.get("hashes") if isinstance(archive_info, dict) else None
    legacy_hash = archive_info.get("hash") if isinstance(archive_info, dict) else None
    observed_digest = hashes.get("sha256") if isinstance(hashes, dict) else None
    if observed_digest is None and isinstance(legacy_hash, str):
        algorithm, separator, digest = legacy_hash.partition("=")
        if algorithm == "sha256" and separator:
            observed_digest = digest
    return observed_digest


def _verify_artifact_roots(
    record: dict[object, object],
    selected_distribution: Distribution,
) -> None:
    """Verify every declared import root for one runtime artifact."""

    roots = record.get("roots")
    if not isinstance(roots, list) or not roots:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    for root in roots:
        if not isinstance(root, dict):
            raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
        _verify_artifact_root(root, selected_distribution)


def _verify_artifact_root(
    root: dict[object, object],
    selected_distribution: Distribution,
) -> None:
    """Verify one complete installed import-root tree."""

    root_path = root.get("path")
    expected_count = root.get("file_count")
    expected_digest = root.get("sha256")
    if not isinstance(root_path, str) or not isinstance(expected_count, int):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    if not _is_sha256(expected_digest):
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    paths = _runtime_root_paths(
        selected_distribution,
        root_path,
        DEPENDENCY_IDENTITY_INVALID,
    )
    if len(paths) != expected_count:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)
    observed_digest = _installed_tree_digest(
        selected_distribution,
        paths,
        DEPENDENCY_IDENTITY_INVALID,
        root_path=root_path,
    )
    if observed_digest != expected_digest:
        raise RuntimeError(DEPENDENCY_IDENTITY_INVALID)


def _runtime_root_paths(
    selected_distribution: Distribution,
    root_path: str,
    identity_error: str = DEPENDENCY_IDENTITY_INVALID,
) -> list[str]:
    """Enumerate a real, symlink-free installed import-root tree."""

    portable_root = PurePosixPath(root_path)
    if portable_root.is_absolute() or ".." in portable_root.parts:
        raise RuntimeError(identity_error)
    installed_root = cast(Path, selected_distribution.locate_file(root_path))
    if installed_root.is_symlink() or not installed_root.is_dir():
        raise RuntimeError(identity_error)
    paths: list[str] = []
    try:
        for installed_path in installed_root.rglob("*"):
            relative_path = installed_path.relative_to(installed_root)
            # Interpreter bytecode caches are created on import and are not part
            # of the recorded clean-install tree ("__pycache__ and *.pyc
            # excluded"); skip them before the symlink/file checks so an imported
            # runtime still matches the qualified digest.
            if "__pycache__" in relative_path.parts or relative_path.suffix in {".pyc", ".pyo"}:
                continue
            if installed_path.is_symlink():
                raise RuntimeError(identity_error)
            if installed_path.is_dir():
                continue
            if not installed_path.is_file():
                raise RuntimeError(identity_error)
            paths.append(str(portable_root / PurePosixPath(relative_path.as_posix())))
    except OSError as exc:
        raise RuntimeError(identity_error) from exc
    return sorted(paths)


def _installed_tree_digest(
    selected_distribution: Distribution,
    paths: Sequence[str],
    identity_error: str,
    *,
    root_path: str,
    package_root: Path | None = None,
) -> str:
    """Hash sorted installed paths and contents into a portable tree identity.

    The recorded tree digest names each file by its path relative to the import
    root, so this hashes ``relative_name`` while still locating each file by its
    root-prefixed distribution path.
    """

    digest = hashlib.sha256()
    root_prefix = PurePosixPath(root_path)
    try:
        for artifact_path in paths:
            portable_path = PurePosixPath(artifact_path)
            if portable_path.is_absolute() or ".." in portable_path.parts:
                raise RuntimeError(identity_error)
            installed_path = cast(Path, selected_distribution.locate_file(artifact_path)).resolve()
            if package_root is not None and not installed_path.is_relative_to(package_root):
                raise RuntimeError(identity_error)
            content_digest = hashlib.sha256(installed_path.read_bytes()).hexdigest()
            relative_name = portable_path.relative_to(root_prefix).as_posix()
            digest.update(relative_name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(content_digest.encode("ascii"))
            digest.update(b"\n")
    except OSError as exc:
        raise RuntimeError(identity_error) from exc
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    """Return whether a value is a lowercase SHA-256 digest."""

    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "DEPENDENCY_IDENTITY_INVALID",
    "MODULE_ORIGIN_INVALID",
    "NOT_INSTALLED",
    "QUALIFICATION_INVALID",
    "SOURCE_IDENTITY_INVALID",
    "VERSION_MISMATCH",
    "resolve_selected_distribution",
    "verify_package_origin",
    "verify_runtime_artifacts",
    "verify_runtime_source_tree",
    "verify_selected_source_files",
]
