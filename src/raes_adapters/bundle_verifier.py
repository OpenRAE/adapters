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
_CODE_ENTRY_MALFORMED = "bundle.inventory.entry-malformed"
_CODE_FILESYSTEM_MUTATED = "bundle.filesystem.mutated"
_CODE_FILESYSTEM_UNREADABLE = "bundle.filesystem.unreadable"
_CODE_INVENTORY_MALFORMED = "bundle.inventory.malformed"
_CODE_PATH_INVALID = "bundle.inventory.path-invalid"


class BundleInvalid(ValueError):
    """A stable integrity failure safe to render to a user."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _UsageFailure(Exception):
    """An intentionally detail-free command-line usage failure."""


class _Parser(argparse.ArgumentParser):
    """Argument parser that maps usage errors to the documented exit code."""

    def error(self, message: str) -> NoReturn:
        """Raise a private usage exception without echoing input paths."""

        del message
        raise _UsageFailure


@dataclass(frozen=True)
class VerificationCard(object):
    """Deterministic integrity-only result safe for public rendering."""

    status: str
    code: str
    files: int = 0
    inventories: int = 0
    entries: int = 0
    unique_bytes: int = 0

    def payload(self) -> dict[str, object]:
        """Return the stable machine-readable card payload."""

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
class _FileRecord(object):
    """One content digest bound to a stable filesystem identity."""

    relative: str
    content: bytes
    size: int
    sha256: str
    identity: tuple[int, int, int, int, int, int]


def _invalid(code: str) -> NoReturn:
    """Raise a redaction-safe bundle integrity failure."""

    raise BundleInvalid(code)


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object while rejecting duplicate member names."""

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _invalid("bundle.inventory.duplicate-key")
        result[key] = value
    return result


def _path_text(value: object) -> str:
    """Require a non-empty, NUL-free text path."""

    if not isinstance(value, str) or not value or "\x00" in value:
        _invalid(_CODE_PATH_INVALID)
    return value


def _check_path_bytes(value: str) -> None:
    """Enforce the UTF-8 path byte limit."""

    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _invalid(_CODE_PATH_INVALID)
    if len(encoded) > MAX_PATH_BYTES:
        _invalid(_CODE_PATH_INVALID)


def _check_path_shape(value: str, path: PurePosixPath) -> None:
    """Reject non-normal, escaping, or over-deep POSIX paths."""

    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in value:
        _invalid(_CODE_PATH_INVALID)
    if len(path.parts) > MAX_DEPTH:
        _invalid("bundle.limit.depth")
    if path.as_posix() != value:
        _invalid(_CODE_PATH_INVALID)


def _relative_path(value: object) -> str:
    """Validate and normalize a contained inventory-relative path."""

    text = _path_text(value)
    _check_path_bytes(text)
    path = PurePosixPath(text)
    _check_path_shape(text, path)
    return path.as_posix()


def _directory_entries(directory: Path, remaining: int) -> list[os.DirEntry[str]]:
    """Read at most the remaining bounded number of directory entries."""

    collected: list[os.DirEntry[str]] = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(collected) >= remaining:
                    _invalid("bundle.limit.files")
                collected.append(entry)
    except BundleInvalid:
        raise
    except OSError:
        _invalid(_CODE_FILESYSTEM_UNREADABLE)
    return collected


def _entry_mode(entry: os.DirEntry[str]) -> int:
    """Read an entry mode without following symbolic links."""

    try:
        return entry.stat(follow_symlinks=False).st_mode
    except OSError:
        _invalid(_CODE_FILESYSTEM_UNREADABLE)


def _entry_kind(mode: int) -> str:
    """Classify an admitted regular file or directory."""

    if stat.S_ISLNK(mode):
        _invalid("bundle.filesystem.symlink")
    if stat.S_ISDIR(mode):
        return "directory"
    if not stat.S_ISREG(mode):
        _invalid("bundle.filesystem.special-file")
    return "file"


def _scan(root: Path) -> dict[str, Path]:
    """Scan a bounded regular-file tree without following links."""

    files: dict[str, Path] = {}
    pending: list[tuple[Path, int]] = [(root, 0)]
    scanned_entries = 0
    while pending:
        directory, depth = pending.pop()
        if depth > MAX_DEPTH:
            _invalid("bundle.limit.depth")
        entries = _directory_entries(directory, MAX_FILES - scanned_entries)
        scanned_entries += len(entries)
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            _relative_path(relative)
            kind = _entry_kind(_entry_mode(entry))
            if kind == "directory":
                pending.append((Path(entry.path), depth + 1))
            else:
                files[relative] = Path(entry.path)
    return files


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Return the filesystem fields used to detect concurrent mutation."""

    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_content(descriptor: int, *, inventory: bool) -> bytes:
    """Read one descriptor while enforcing its class-specific byte limit."""

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
            code = "bundle.limit.inventory-bytes" if inventory else "bundle.limit.artifact-bytes"
            _invalid(code)
    return b"".join(chunks)


def _read_stable(root: Path, relative: str, *, inventory: bool) -> _FileRecord:
    """Hash a contained regular file and reject identity changes during I/O."""

    candidate = root / relative
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before_path = candidate.lstat()
        descriptor = os.open(candidate, flags)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or _identity(before_path) != _identity(before):
                _invalid(_CODE_FILESYSTEM_MUTATED)
            content = _read_content(descriptor, inventory=inventory)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after_path = candidate.lstat()
    except BundleInvalid:
        raise
    except OSError:
        _invalid(_CODE_FILESYSTEM_MUTATED)
    if _identity(before) != _identity(after) or _identity(after) != _identity(after_path):
        _invalid(_CODE_FILESYSTEM_MUTATED)
    return _FileRecord(
        relative=relative,
        content=content,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        identity=_identity(after),
    )


def _inventory_payload(record: _FileRecord) -> list[object]:
    """Decode one exact-shape inventory object."""

    try:
        payload = json.loads(record.content, object_pairs_hook=_json_object)
    except BundleInvalid:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        _invalid(_CODE_INVENTORY_MALFORMED)
    if not isinstance(payload, dict) or set(payload) != {"artifacts"}:
        _invalid(_CODE_INVENTORY_MALFORMED)
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list):
        _invalid(_CODE_INVENTORY_MALFORMED)
    return artifacts


def _entry_size(value: object) -> int:
    """Validate one non-negative, non-boolean byte count."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _invalid(_CODE_ENTRY_MALFORMED)
    return value


def _entry_digest(value: object) -> str:
    """Validate one lower-case SHA-256 hex digest."""

    if not isinstance(value, str) or len(value) != 64:
        _invalid(_CODE_ENTRY_MALFORMED)
    if any(character not in "0123456789abcdef" for character in value):
        _invalid(_CODE_ENTRY_MALFORMED)
    return value


def _check_media_type(value: object) -> None:
    """Require a non-empty inventory media type label."""

    if not isinstance(value, str) or not value:
        _invalid(_CODE_ENTRY_MALFORMED)


def _entry(item: object) -> tuple[str, int, str]:
    """Validate and project one exact-shape inventory entry."""

    if not isinstance(item, dict) or set(item) != _ENTRY_KEYS:
        _invalid(_CODE_ENTRY_MALFORMED)
    relative = _relative_path(item["path"])
    size = _entry_size(item["size_bytes"])
    digest = _entry_digest(item["sha256"])
    _check_media_type(item["media_type"])
    return relative, size, digest


def _root_details(bundle: Path) -> tuple[Path, tuple[int, int, int, int, int, int]]:
    """Admit one real directory root and capture its identity."""

    try:
        root_stat = bundle.lstat()
    except OSError:
        _invalid("bundle.root.invalid")
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        _invalid("bundle.root.invalid")
    return bundle.resolve(), _identity(root_stat)


def _assert_current_identity(
    path: Path,
    expected: tuple[int, int, int, int, int, int],
    *,
    regular: bool,
) -> None:
    """Require a path to retain its admitted filesystem identity."""

    try:
        current = path.lstat()
    except OSError:
        _invalid(_CODE_FILESYSTEM_MUTATED)
    if regular and not stat.S_ISREG(current.st_mode):
        _invalid(_CODE_FILESYSTEM_MUTATED)
    if _identity(current) != expected:
        _invalid(_CODE_FILESYSTEM_MUTATED)


class _BundleVerifier(object):
    """Stateful bounded walk over one bundle's transitive inventory closure."""

    def __init__(self, bundle: Path) -> None:
        """Capture the root and initialize bounded verification state."""

        self.bundle = bundle
        self.root, self.root_identity = _root_details(bundle)
        self.files = _scan(self.root)
        if _INVENTORY_NAME not in self.files:
            _invalid("bundle.inventory.missing")
        self.records: dict[str, _FileRecord] = {}
        self.referenced: set[str] = set()
        self.inventories_seen: set[str] = set()
        self.inventory_queue = deque([_INVENTORY_NAME])
        self.entries_count = 0
        self.unique_bytes = 0

    def _record(self, relative: str, *, inventory: bool) -> _FileRecord:
        """Read each unique path once and charge it to the byte budget."""

        existing = self.records.get(relative)
        if existing is None:
            if relative not in self.files:
                _invalid("bundle.inventory.member-missing")
            existing = _read_stable(self.root, relative, inventory=inventory)
            self.records[relative] = existing
            self.unique_bytes += existing.size
            if self.unique_bytes > MAX_UNIQUE_BYTES:
                _invalid("bundle.limit.unique-bytes")
        return existing

    def _start_inventory(self, inventory_path: str) -> tuple[PurePosixPath, list[object]]:
        """Admit one not-yet-seen inventory and return its base and entries."""

        if inventory_path in self.inventories_seen:
            _invalid("bundle.inventory.duplicate")
        self.inventories_seen.add(inventory_path)
        if len(self.inventories_seen) > MAX_INVENTORIES:
            _invalid("bundle.limit.inventories")
        record = self._record(inventory_path, inventory=True)
        return PurePosixPath(inventory_path).parent, _inventory_payload(record)

    def _verify_item(self, base: PurePosixPath, item: object) -> None:
        """Verify one inventory member and enqueue nested inventories."""

        self.entries_count += 1
        if self.entries_count > MAX_ENTRIES:
            _invalid("bundle.limit.entries")
        child, expected_size, expected_digest = _entry(item)
        joined = _relative_path((base / child).as_posix())
        if joined == _INVENTORY_NAME or joined in self.referenced:
            _invalid("bundle.inventory.duplicate-path")
        self.referenced.add(joined)
        is_inventory = PurePosixPath(joined).name == _INVENTORY_NAME
        actual = self._record(joined, inventory=is_inventory)
        if actual.size != expected_size or actual.sha256 != expected_digest:
            _invalid("bundle.inventory.member-mismatch")
        if is_inventory:
            self.inventory_queue.append(joined)

    def _verify_closure(self) -> None:
        """Walk all flat or transitive inventory entries breadth-first."""

        while self.inventory_queue:
            inventory_path = self.inventory_queue.popleft()
            base, items = self._start_inventory(inventory_path)
            for item in items:
                self._verify_item(base, item)

    def _verify_membership(self) -> None:
        """Require exact membership beyond the root inventory itself."""

        expected = set(self.files) - {_INVENTORY_NAME}
        if self.referenced != expected:
            _invalid("bundle.inventory.membership-mismatch")

    def _verify_unchanged(self) -> None:
        """Re-scan and re-stat all read paths to reject concurrent mutation."""

        final_files = _scan(self.root)
        if set(final_files) != set(self.files):
            _invalid(_CODE_FILESYSTEM_MUTATED)
        _assert_current_identity(self.bundle, self.root_identity, regular=False)
        for relative, loaded in self.records.items():
            _assert_current_identity(self.root / relative, loaded.identity, regular=True)

    def verify(self) -> VerificationCard:
        """Run closure, membership, and final identity verification."""

        self._verify_closure()
        self._verify_membership()
        self._verify_unchanged()
        return VerificationCard(
            status="verified",
            code="bundle.integrity.verified",
            files=len(self.files),
            inventories=len(self.inventories_seen),
            entries=self.entries_count,
            unique_bytes=self.unique_bytes,
        )


def verify_bundle(bundle: Path) -> VerificationCard:
    """Verify exact flat or transitive inventory closure without side effects."""

    return _BundleVerifier(bundle).verify()


def render_card(card: VerificationCard, output_format: str) -> str:
    """Render one deterministic JSON, terminal, or Markdown integrity card."""

    if output_format == "json":
        return json.dumps(card.payload(), sort_keys=True, separators=(",", ":"))
    counts = {
        "entries": card.entries,
        "files": card.files,
        "inventories": card.inventories,
        "unique_bytes": card.unique_bytes,
    }
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
    """Build the isolated verifier command-line parser."""

    parser = _Parser(prog="raes-adapters verify-bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "terminal", "markdown"), default="terminal")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the verifier with its stable 0, 2, 3, and 70 exit contract."""

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
