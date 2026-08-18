"""Private byte-level inventory primitives shared by adapter producers.

This module describes files, not experiment meaning. It deliberately imports
neither simulators nor RAES contracts and defines no portable schema.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from pathlib import Path


def media_type(path: Path) -> str:
    """Return the established portable media type for a produced artifact."""

    return "application/json" if path.suffix == ".json" else "application/octet-stream"


def inventory_entry(
    root: Path,
    path: Path,
    *,
    type_name: str | None = None,
) -> dict[str, object]:
    """Describe one regular contained file with the established entry shape."""

    resolved_root = root.resolve()
    if path.is_symlink() or not path.is_file():
        raise ValueError("inventory member is not a regular file")
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("inventory member escapes its root")
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("inventory member escapes its root") from error
    content = path.read_bytes()
    return {
        "media_type": type_name if type_name is not None else media_type(path),
        "path": relative,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def inventory_document(
    root: Path,
    members: Iterable[Path],
    *,
    type_for: Callable[[Path], str] = media_type,
) -> dict[str, object]:
    """Build a deterministic inventory document without writing it."""

    ordered = sorted(members)
    return {
        "artifacts": [inventory_entry(root, path, type_name=type_for(path)) for path in ordered]
    }


__all__ = ["inventory_document", "inventory_entry", "media_type"]
