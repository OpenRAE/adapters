"""Offline, integrity-only verification for inventory-sealed bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import NoReturn

EXIT_VERIFIED = 0
EXIT_USAGE = 2
EXIT_INVALID = 3
EXIT_INTERNAL = 70

MAX_FILES = 100_000
MAX_INVENTORIES = 100_000
MAX_ENTRIES = 200_000
MAX_UNIQUE_BYTES = 4 * 1024**3
MAX_ARTIFACT_BYTES = 500 * 1024
MAX_INVENTORY_BYTES = 16 * 1024**2
MAX_DEPTH = 32
MAX_PATH_BYTES = 1_024

_INVENTORY_NAME = "inventory.json"
_ENTRY_KEYS = {"media_type", "path", "sha256", "size_bytes"}


class BundleInvalid(ValueError):
    """A stable integrity failure safe to render to a user."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _UsageFailure(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _UsageFailure


@dataclass(frozen=True)
class VerificationCard:
    status: str
    code: str
    files: int = 0
    inventories: int = 0
    entries: int = 0
    unique_bytes: int = 0

    def payload(self) -> dict[str, object]:
        return {
            "claim": "integrity-only",
            "code": self.code,
            "counts": {
                "entries": self.entries,
                "files": self.files,
                "inventories": self.inventories,
                "unique_bytes": self.unique_bytes,
            },
            "disclaimers": [
                "semantic fidelity not assessed",
                "capture completeness not assessed",
            ],
            "status": self.status,
        }


@dataclass(frozen=True)
class _FileRecord:
    relative: str
    content: bytes
    size: int
    sha256: str
    identity: tuple[int, int, int, int, int, int]


def _invalid(code: str) -> NoReturn:
    raise BundleInvalid(code)


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _invalid("bundle.inventory.duplicate-key")
        result[key] = value
    return result


def _relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        _invalid("bundle.inventory.path-invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _invalid("bundle.inventory.path-invalid")
    if len(encoded) > MAX_PATH_BYTES:
        _invalid("bundle.inventory.path-invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in value:
        _invalid("bundle.inventory.path-invalid")
    if len(path.parts) > MAX_DEPTH:
        _invalid("bundle.limit.depth")
    normalized = path.as_posix()
    if normalized != value:
        _invalid("bundle.inventory.path-invalid")
    return normalized


def _scan(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    pending: list[tuple[Path, int]] = [(root, 0)]
    scanned_entries = 0
    while pending:
        directory, depth = pending.pop()
        if depth > MAX_DEPTH:
            _invalid("bundle.limit.depth")
        try:
            entries = os.scandir(directory)
        except OSError:
            _invalid("bundle.filesystem.unreadable")
        try:
            with entries:
                for entry in entries:
                    scanned_entries += 1
                    if scanned_entries > MAX_FILES:
                        _invalid("bundle.limit.files")
                    relative = Path(entry.path).relative_to(root).as_posix()
                    _relative_path(relative)
                    try:
                        mode = entry.stat(follow_symlinks=False).st_mode
                    except OSError:
                        _invalid("bundle.filesystem.unreadable")
                    if stat.S_ISLNK(mode):
                        _invalid("bundle.filesystem.symlink")
                    if stat.S_ISDIR(mode):
                        pending.append((Path(entry.path), depth + 1))
                        continue
                    if not stat.S_ISREG(mode):
                        _invalid("bundle.filesystem.special-file")
                    files[relative] = Path(entry.path)
        except OSError:
            _invalid("bundle.filesystem.unreadable")
    return files


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_stable(root: Path, relative: str, *, inventory: bool) -> _FileRecord:
    candidate = root / relative
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before_path = candidate.lstat()
        descriptor = os.open(candidate, flags)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or _identity(before_path) != _identity(before):
                _invalid("bundle.filesystem.mutated")
            limit = MAX_INVENTORY_BYTES if inventory else MAX_ARTIFACT_BYTES
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > limit:
                    code = (
                        "bundle.limit.inventory-bytes"
                        if inventory
                        else "bundle.limit.artifact-bytes"
                    )
                    _invalid(code)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after_path = candidate.lstat()
    except BundleInvalid:
        raise
    except OSError:
        _invalid("bundle.filesystem.mutated")
    if _identity(before) != _identity(after) or _identity(after) != _identity(after_path):
        _invalid("bundle.filesystem.mutated")
    content = b"".join(chunks)
    return _FileRecord(
        relative=relative,
        content=content,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        identity=_identity(after),
    )


def _inventory_payload(record: _FileRecord) -> list[object]:
    try:
        payload = json.loads(record.content, object_pairs_hook=_json_object)
    except BundleInvalid:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        _invalid("bundle.inventory.malformed")
    if not isinstance(payload, dict) or set(payload) != {"artifacts"}:
        _invalid("bundle.inventory.malformed")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list):
        _invalid("bundle.inventory.malformed")
    return artifacts


def _entry(item: object) -> tuple[str, int, str]:
    if not isinstance(item, dict) or set(item) != _ENTRY_KEYS:
        _invalid("bundle.inventory.entry-malformed")
    relative = _relative_path(item["path"])
    size = item["size_bytes"]
    digest = item["sha256"]
    media_type = item["media_type"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        _invalid("bundle.inventory.entry-malformed")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(media_type, str)
        or not media_type
    ):
        _invalid("bundle.inventory.entry-malformed")
    return relative, size, digest


def verify_bundle(bundle: Path) -> VerificationCard:
    """Verify exact flat or transitive inventory closure without side effects."""

    try:
        root_stat = bundle.lstat()
    except OSError:
        _invalid("bundle.root.invalid")
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        _invalid("bundle.root.invalid")
    root_identity = _identity(root_stat)
    root = bundle.resolve()
    files = _scan(root)
    if _INVENTORY_NAME not in files:
        _invalid("bundle.inventory.missing")

    records: dict[str, _FileRecord] = {}
    referenced: set[str] = set()
    inventories_seen: set[str] = set()
    inventory_queue = deque([_INVENTORY_NAME])
    entries_count = 0
    unique_bytes = 0

    def record(relative: str, *, inventory: bool) -> _FileRecord:
        nonlocal unique_bytes
        existing = records.get(relative)
        if existing is not None:
            return existing
        if relative not in files:
            _invalid("bundle.inventory.member-missing")
        loaded = _read_stable(root, relative, inventory=inventory)
        records[relative] = loaded
        unique_bytes += loaded.size
        if unique_bytes > MAX_UNIQUE_BYTES:
            _invalid("bundle.limit.unique-bytes")
        return loaded

    while inventory_queue:
        inventory_path = inventory_queue.popleft()
        if inventory_path in inventories_seen:
            _invalid("bundle.inventory.duplicate")
        inventories_seen.add(inventory_path)
        if len(inventories_seen) > MAX_INVENTORIES:
            _invalid("bundle.limit.inventories")
        inventory_record = record(inventory_path, inventory=True)
        base = PurePosixPath(inventory_path).parent
        for item in _inventory_payload(inventory_record):
            entries_count += 1
            if entries_count > MAX_ENTRIES:
                _invalid("bundle.limit.entries")
            child, expected_size, expected_digest = _entry(item)
            joined = (base / child).as_posix()
            joined = _relative_path(joined)
            if joined == _INVENTORY_NAME or joined in referenced:
                _invalid("bundle.inventory.duplicate-path")
            referenced.add(joined)
            is_inventory = PurePosixPath(joined).name == _INVENTORY_NAME
            actual = record(joined, inventory=is_inventory)
            if actual.size != expected_size or actual.sha256 != expected_digest:
                _invalid("bundle.inventory.member-mismatch")
            if is_inventory:
                inventory_queue.append(joined)

    expected = set(files) - {_INVENTORY_NAME}
    if referenced != expected:
        _invalid("bundle.inventory.membership-mismatch")
    final_files = _scan(root)
    if set(final_files) != set(files):
        _invalid("bundle.filesystem.mutated")
    try:
        if _identity(bundle.lstat()) != root_identity:
            _invalid("bundle.filesystem.mutated")
        for relative, loaded in records.items():
            current = (root / relative).lstat()
            if not stat.S_ISREG(current.st_mode) or _identity(current) != loaded.identity:
                _invalid("bundle.filesystem.mutated")
    except BundleInvalid:
        raise
    except OSError:
        _invalid("bundle.filesystem.mutated")
    return VerificationCard(
        status="verified",
        code="bundle.integrity.verified",
        files=len(files),
        inventories=len(inventories_seen),
        entries=entries_count,
        unique_bytes=unique_bytes,
    )


def render_card(card: VerificationCard, output_format: str) -> str:
    payload = card.payload()
    if output_format == "json":
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
    counts = payload["counts"]
    assert isinstance(counts, dict)
    if output_format == "markdown":
        return "\n".join(
            (
                "# Bundle integrity card",
                "",
                f"- Status: `{card.status}`",
                f"- Code: `{card.code}`",
                "- Claim: integrity-only",
                f"- Files: {counts['files']}",
                f"- Inventories: {counts['inventories']}",
                f"- Entries: {counts['entries']}",
                f"- Unique bytes: {counts['unique_bytes']}",
                "- Semantic fidelity: not assessed",
                "- Capture completeness: not assessed",
            )
        )
    return "\n".join(
        (
            f"status: {card.status}",
            f"code: {card.code}",
            "claim: integrity-only",
            f"files: {counts['files']}",
            f"inventories: {counts['inventories']}",
            f"entries: {counts['entries']}",
            f"unique-bytes: {counts['unique_bytes']}",
            "semantic-fidelity: not-assessed",
            "capture-completeness: not-assessed",
        )
    )


def _parser() -> _Parser:
    parser = _Parser(prog="raes-adapters verify-bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "terminal", "markdown"), default="terminal")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        try:
            card = verify_bundle(args.bundle)
            result = EXIT_VERIFIED
        except BundleInvalid as error:
            card = VerificationCard(status="invalid", code=error.code)
            result = EXIT_INVALID
        print(render_card(card, args.format))
        return result
    except _UsageFailure:
        print("verify-bundle.usage.invalid: invalid command line", file=sys.stderr)
        return EXIT_USAGE
    except Exception:
        print("verify-bundle.internal.failure: internal verification failure", file=sys.stderr)
        return EXIT_INTERNAL


__all__ = [
    "BundleInvalid",
    "VerificationCard",
    "main",
    "render_card",
    "verify_bundle",
]
