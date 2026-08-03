"""Mechanical source- and artifact-identity verification for backend drivers.

These helpers carry no simulator semantics: they enumerate a real, symlink-free
installed import-root tree, hash it into a portable identity, verify that an
imported module actually originates from the selected distribution, and reject
editable / VCS / directory installs whose bytes cannot be attested. A backend
driver composes them with its own qualification record; the qualification
parsing, package selection, and claim limits stay in the backend.

The functions are the shared extraction the ``primaite`` backend guardrails
permit ("complete-root enumeration, tree digesting, and module-origin
verification"); the CyberBattleSim driver consumes the same code so exactly one
copy exists.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from importlib.metadata import Distribution
from importlib.util import find_spec
from pathlib import Path, PurePosixPath
from typing import cast

_MODULE_ORIGIN_INVALID = "selected simulator module origin could not be verified"


def is_sha256(value: object) -> bool:
    """Return whether a value is a lowercase SHA-256 hexadecimal digest."""

    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def installed_root_paths(
    distribution: Distribution,
    root_path: str,
    identity_error: str,
) -> list[str]:
    """Enumerate a real, symlink-free installed import-root tree.

    Rejects absolute or parent-escaping roots, symlinked roots or members, and
    non-regular files. Returns the sorted portable paths of every regular file
    under ``root_path``.
    """

    portable_root = PurePosixPath(root_path)
    if portable_root.is_absolute() or ".." in portable_root.parts:
        raise RuntimeError(identity_error)
    installed_root = cast(Path, distribution.locate_file(root_path))
    if installed_root.is_symlink() or not installed_root.is_dir():
        raise RuntimeError(identity_error)
    paths: list[str] = []
    try:
        for installed_path in installed_root.rglob("*"):
            if installed_path.is_symlink():
                raise RuntimeError(identity_error)
            if installed_path.is_dir():
                continue
            if not installed_path.is_file():
                raise RuntimeError(identity_error)
            relative_path = installed_path.relative_to(installed_root)
            paths.append(str(portable_root / PurePosixPath(relative_path.as_posix())))
    except OSError as exc:
        raise RuntimeError(identity_error) from exc
    return sorted(paths)


def installed_tree_digest(
    distribution: Distribution,
    paths: Sequence[str],
    identity_error: str,
    *,
    package_root: Path | None = None,
) -> str:
    """Hash sorted installed paths and contents into a portable tree identity.

    When ``package_root`` is supplied, every resolved file must stay within it,
    rejecting an installed path that escapes the selected import root.
    """

    digest = hashlib.sha256()
    try:
        for artifact_path in paths:
            portable_path = PurePosixPath(artifact_path)
            if portable_path.is_absolute() or ".." in portable_path.parts:
                raise RuntimeError(identity_error)
            installed_path = cast(Path, distribution.locate_file(artifact_path)).resolve()
            if package_root is not None and not installed_path.is_relative_to(package_root):
                raise RuntimeError(identity_error)
            content_digest = hashlib.sha256(installed_path.read_bytes()).hexdigest()
            digest.update(artifact_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(content_digest.encode("ascii"))
            digest.update(b"\n")
    except OSError as exc:
        raise RuntimeError(identity_error) from exc
    return digest.hexdigest()


def verify_module_origin(
    module_name: str,
    distribution: Distribution,
    expected_relative_path: str,
    *,
    error: str = _MODULE_ORIGIN_INVALID,
) -> None:
    """Verify an imported module resolves to the selected distribution's file."""

    module_spec = find_spec(module_name)
    origin = module_spec.origin if module_spec is not None else None
    expected = cast(Path, distribution.locate_file(expected_relative_path)).resolve()
    if not isinstance(origin, str) or Path(origin).resolve() != expected:
        raise RuntimeError(error)


def _direct_url_text(distribution: Distribution, identity_error: str) -> str | None:
    """Read optional direct-install provenance from a distribution."""

    read_text = getattr(distribution, "read_text", None)
    if not callable(read_text):
        return None
    direct_url_text = read_text("direct_url.json")
    if direct_url_text is not None and not isinstance(direct_url_text, str):
        raise RuntimeError(identity_error)
    return direct_url_text


def _load_direct_url(direct_url_text: str, identity_error: str) -> dict[object, object]:
    """Decode a direct-install provenance record as a JSON object."""

    try:
        direct_url = json.loads(direct_url_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(identity_error) from exc
    if not isinstance(direct_url, dict):
        raise RuntimeError(identity_error)
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


def reject_unverifiable_install(
    distribution: Distribution,
    identity_error: str,
    *,
    expected_archive_sha256: str | None = None,
    require_archive_digest: bool = False,
) -> None:
    """Reject editable / directory / VCS installs and check archive identity.

    A distribution with no ``direct_url.json`` is an ordinary index/wheel install
    and passes. A directory (``dir_info``) or VCS (``vcs_info``) install cannot be
    attested and is rejected. When ``require_archive_digest`` is set, the recorded
    archive SHA-256 must match ``expected_archive_sha256``.
    """

    direct_url_text = _direct_url_text(distribution, identity_error)
    if direct_url_text is None:
        return
    direct_url = _load_direct_url(direct_url_text, identity_error)
    if not {"dir_info", "vcs_info"}.isdisjoint(direct_url):
        raise RuntimeError(identity_error)
    observed_digest = _archive_sha256(direct_url)
    if require_archive_digest and observed_digest != expected_archive_sha256:
        raise RuntimeError(identity_error)


__all__ = [
    "installed_root_paths",
    "installed_tree_digest",
    "is_sha256",
    "reject_unverifiable_install",
    "verify_module_origin",
]
