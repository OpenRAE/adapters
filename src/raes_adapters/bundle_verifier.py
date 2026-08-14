"""Offline, integrity-only verification for inventory-sealed bundles."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import NoReturn

MAX_FILES = 100_000
MAX_INVENTORIES = 100_000
MAX_ENTRIES = 200_000
MAX_UNIQUE_BYTES = 4 * 1024**3
MAX_ARTIFACT_BYTES = 500 * 1024
MAX_INVENTORY_BYTES = 16 * 1024**2
MAX_DEPTH = 32
MAX_PATH_BYTES = 1_024

_MAX_DIRECTORIES = 100_000
_MAX_JSON_DEPTH = 64
_READ_CHUNK_BYTES = 1024 * 1024
_FDINFO_MAX_BYTES = 4_096

_INVENTORY_NAME = "inventory.json"
_ENTRY_KEYS = {"media_type", "path", "sha256", "size_bytes"}
_CODE_ENTRY_MALFORMED = "bundle.inventory.entry-malformed"
_CODE_FILESYSTEM_MUTATED = "bundle.filesystem.mutated"
_CODE_FILESYSTEM_UNREADABLE = "bundle.filesystem.unreadable"
_CODE_INVENTORY_MALFORMED = "bundle.inventory.malformed"
_CODE_PATH_INVALID = "bundle.inventory.path-invalid"

_PATH_ADMISSION_ERRORS = (OSError, ValueError, UnicodeError)


class BundleInvalid(ValueError):
    """A stable integrity failure safe to render to a user."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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
    size: int
    sha256: str
    identity: _Identity
    content: bytes | None = None


_Identity = tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class _TreeSnapshot(object):
    """One descriptor-rooted view of admitted files and directories."""

    files: dict[str, _Identity]
    directories: dict[str, _Identity]


@dataclass
class _ScanState(object):
    """Bounded mutable counters for one descriptor-rooted traversal."""

    files: dict[str, _Identity]
    directories: dict[str, _Identity]
    file_count: int = 0
    directory_count: int = 0


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


def _entry_kind(mode: int) -> str:
    """Classify an admitted regular file or directory."""

    if stat.S_ISLNK(mode):
        _invalid("bundle.filesystem.symlink")
    if stat.S_ISDIR(mode):
        return "directory"
    if not stat.S_ISREG(mode):
        _invalid("bundle.filesystem.special-file")
    return "file"


def _identity(info: os.stat_result) -> _Identity:
    """Return the filesystem fields used to detect concurrent mutation."""

    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _secure_descriptor_primitives_available() -> bool:
    """Return whether this platform can enforce every containment guarantee."""

    supports_dir_fd: set[object] = getattr(os, "supports_dir_fd", set())
    supports_fd: set[object] = getattr(os, "supports_fd", set())
    return all(
        (
            bool(getattr(os, "O_NOFOLLOW", 0)),
            bool(getattr(os, "O_DIRECTORY", 0)),
            bool(getattr(os, "O_NONBLOCK", 0)),
            os.open in supports_dir_fd,
            os.scandir in supports_fd,
        )
    )


def _directory_flags() -> int:
    """Return the fail-closed flags for opening one directory component."""

    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    """Return non-blocking no-follow flags for a terminal regular file."""

    return os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _mount_id(descriptor: int) -> int | None:
    """Read Linux's mount identity for one open descriptor, when available."""

    path = f"/proc/self/fdinfo/{descriptor}"
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fdinfo = os.open(path, flags)
    except OSError:
        return None
    try:
        content = os.read(fdinfo, _FDINFO_MAX_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fdinfo)
    if len(content) > _FDINFO_MAX_BYTES:
        return None
    for line in content.splitlines():
        if line.startswith(b"mnt_id:"):
            try:
                return int(line.partition(b":")[2].strip())
            except ValueError:
                return None
    return None


def _descriptor_stat(descriptor: int, code: str) -> os.stat_result:
    """Read one open descriptor's identity through a bounded failure code."""

    try:
        return os.fstat(descriptor)
    except OSError:
        _invalid(code)


def _open_directory_at(
    parent: int,
    name: str,
    expected: _Identity,
    *,
    root_device: int,
    root_mount_id: int,
) -> int:
    """Open and identity-pin one directory relative to an admitted parent."""

    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent)
    except OSError:
        _invalid(_CODE_FILESYSTEM_MUTATED)
    try:
        current = _descriptor_stat(descriptor, _CODE_FILESYSTEM_MUTATED)
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_dev != root_device
            or _mount_id(descriptor) != root_mount_id
            or _identity(current) != expected
        ):
            _invalid(_CODE_FILESYSTEM_MUTATED)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _entry_stat(entry: os.DirEntry[str], code: str) -> os.stat_result:
    """Read an enumerated entry without following a link."""

    try:
        return entry.stat(follow_symlinks=False)
    except OSError:
        _invalid(code)


def _scan_file(relative: str, info: os.stat_result, state: _ScanState) -> None:
    """Charge and retain one regular-file identity."""

    state.file_count += 1
    if state.file_count > MAX_FILES:
        _invalid("bundle.limit.files")
    state.files[relative] = _identity(info)


def _scan_child_directory(
    descriptor: int,
    entry: os.DirEntry[str],
    relative: str,
    info: os.stat_result,
    state: _ScanState,
    *,
    depth: int,
    root_device: int,
    root_mount_id: int,
    error_code: str,
) -> None:
    """Open, scan, and close one identity-pinned descendant directory."""

    state.directory_count += 1
    if state.directory_count > _MAX_DIRECTORIES:
        _invalid("bundle.limit.directories")
    expected = _identity(info)
    state.directories[relative] = expected
    child = _open_directory_at(
        descriptor,
        entry.name,
        expected,
        root_device=root_device,
        root_mount_id=root_mount_id,
    )
    try:
        _scan_directory(
            child,
            relative,
            state,
            depth=depth + 1,
            root_device=root_device,
            root_mount_id=root_mount_id,
            error_code=error_code,
        )
    finally:
        os.close(child)


def _scan_entry(
    descriptor: int,
    entry: os.DirEntry[str],
    base: str,
    state: _ScanState,
    *,
    depth: int,
    root_device: int,
    root_mount_id: int,
    error_code: str,
) -> None:
    """Classify and charge one descriptor-relative directory entry."""

    relative = entry.name if not base else f"{base}/{entry.name}"
    _relative_path(relative)
    info = _entry_stat(entry, error_code)
    kind = _entry_kind(info.st_mode)
    if info.st_dev != root_device:
        _invalid("bundle.filesystem.mount")
    if kind == "directory":
        _scan_child_directory(
            descriptor,
            entry,
            relative,
            info,
            state,
            depth=depth,
            root_device=root_device,
            root_mount_id=root_mount_id,
            error_code=error_code,
        )
    else:
        _scan_file(relative, info, state)


def _scan_directory(
    descriptor: int,
    base: str,
    state: _ScanState,
    *,
    depth: int,
    root_device: int,
    root_mount_id: int,
    error_code: str,
) -> None:
    """Enumerate one pinned directory while bounding depth and mutation."""

    if depth > MAX_DEPTH:
        _invalid("bundle.limit.depth")
    before = _descriptor_stat(descriptor, error_code)
    try:
        with os.scandir(descriptor) as entries:
            for entry in entries:
                _scan_entry(
                    descriptor,
                    entry,
                    base,
                    state,
                    depth=depth,
                    root_device=root_device,
                    root_mount_id=root_mount_id,
                    error_code=error_code,
                )
    except BundleInvalid:
        raise
    except OSError:
        _invalid(error_code)
    after = _descriptor_stat(descriptor, error_code)
    if _identity(before) != _identity(after):
        _invalid(_CODE_FILESYSTEM_MUTATED)


def _scan(
    root_descriptor: int,
    root_identity: _Identity,
    root_mount_id: int,
    *,
    error_code: str = _CODE_FILESYSTEM_UNREADABLE,
) -> _TreeSnapshot:
    """Scan one bounded tree only through descriptor-relative operations."""

    scan_root = _open_directory_at(
        root_descriptor,
        ".",
        root_identity,
        root_device=root_identity[0],
        root_mount_id=root_mount_id,
    )
    state = _ScanState(files={}, directories={})
    try:
        _scan_directory(
            scan_root,
            "",
            state,
            depth=0,
            root_device=root_identity[0],
            root_mount_id=root_mount_id,
            error_code=error_code,
        )
    finally:
        os.close(scan_root)
    return _TreeSnapshot(files=state.files, directories=state.directories)


def _open_member(
    root_descriptor: int,
    snapshot: _TreeSnapshot,
    relative: str,
    root_mount_id: int,
) -> tuple[int, os.stat_result]:
    """Open one file through identity-pinned intermediate directories."""

    current, owned_directory, expected_file = _open_member_parent(
        root_descriptor,
        snapshot,
        relative,
        root_mount_id,
    )
    try:
        return _open_regular_file(
            current, PurePosixPath(relative).name, expected_file, root_mount_id
        )
    finally:
        if owned_directory is not None:
            os.close(owned_directory)


def _open_member_parent(
    root_descriptor: int,
    snapshot: _TreeSnapshot,
    relative: str,
    root_mount_id: int,
) -> tuple[int, int | None, _Identity]:
    """Traverse and pin every intermediate component of one member path."""

    parts = PurePosixPath(relative).parts
    expected_file = snapshot.files.get(relative)
    if expected_file is None:
        _invalid("bundle.inventory.member-missing")
    current = root_descriptor
    owned_directory: int | None = None
    prefix: list[str] = []
    try:
        for component in parts[:-1]:
            prefix.append(component)
            expected_directory = snapshot.directories.get("/".join(prefix))
            if expected_directory is None:
                _invalid(_CODE_FILESYSTEM_MUTATED)
            next_directory = _open_directory_at(
                current,
                component,
                expected_directory,
                root_device=expected_file[0],
                root_mount_id=root_mount_id,
            )
            if owned_directory is not None:
                os.close(owned_directory)
            owned_directory = next_directory
            current = next_directory
        return current, owned_directory, expected_file
    except BaseException:
        if owned_directory is not None:
            os.close(owned_directory)
        raise


def _open_regular_file(
    parent: int,
    name: str,
    expected: _Identity,
    root_mount_id: int,
) -> tuple[int, os.stat_result]:
    """Open and identity-pin one non-blocking terminal regular file."""

    try:
        descriptor = os.open(name, _file_flags(), dir_fd=parent)
    except OSError:
        _invalid(_CODE_FILESYSTEM_MUTATED)
    try:
        before = _descriptor_stat(descriptor, _CODE_FILESYSTEM_MUTATED)
        if (
            not stat.S_ISREG(before.st_mode)
            or _mount_id(descriptor) != root_mount_id
            or _identity(before) != expected
        ):
            _invalid(_CODE_FILESYSTEM_MUTATED)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, before


def _read_request_size(total: int, limit: int, unique_remaining: int | None) -> int:
    """Bound the next read by the per-file and optional aggregate budgets."""

    request = min(_READ_CHUNK_BYTES, limit + 1 - total)
    if unique_remaining is not None:
        request = min(request, max(1, unique_remaining + 1 - total))
    return request


def _hash_descriptor(
    descriptor: int,
    *,
    inventory: bool,
    retain_content: bool,
    unique_remaining: int | None,
) -> tuple[int, str, bytes | None]:
    """Stream one regular file under per-file and aggregate byte limits."""

    limit, limit_code = _content_limit(inventory)
    digest = hashlib.sha256()
    chunks = _content_buffer(retain_content)
    total = 0
    while True:
        chunk = _read_checked_chunk(
            descriptor,
            total=total,
            limit=limit,
            limit_code=limit_code,
            unique_remaining=unique_remaining,
        )
        if not chunk:
            break
        total += len(chunk)
        digest.update(chunk)
        if chunks is not None:
            chunks.append(chunk)
    content = b"".join(chunks) if chunks is not None else None
    return total, digest.hexdigest(), content


def _content_limit(inventory: bool) -> tuple[int, str]:
    """Return the byte limit and stable code for one file class."""

    if inventory:
        return MAX_INVENTORY_BYTES, "bundle.limit.inventory-bytes"
    return MAX_ARTIFACT_BYTES, "bundle.limit.artifact-bytes"


def _content_buffer(retain_content: bool) -> list[bytes] | None:
    """Allocate a buffer only for the currently parsed inventory."""

    if retain_content:
        return []
    return None


def _read_checked_chunk(
    descriptor: int,
    *,
    total: int,
    limit: int,
    limit_code: str,
    unique_remaining: int | None,
) -> bytes:
    """Read one bounded chunk and reject limit crossings before retention."""

    try:
        chunk = os.read(descriptor, _read_request_size(total, limit, unique_remaining))
    except OSError:
        _invalid(_CODE_FILESYSTEM_MUTATED)
    next_total = total + len(chunk)
    if next_total > limit:
        _invalid(limit_code)
    if unique_remaining is not None and next_total > unique_remaining:
        _invalid("bundle.limit.unique-bytes")
    return chunk


def _read_stable(
    root_descriptor: int,
    snapshot: _TreeSnapshot,
    relative: str,
    root_mount_id: int,
    *,
    inventory: bool,
    retain_content: bool,
    unique_remaining: int | None,
) -> _FileRecord:
    """Hash one contained regular file without retaining artifact bytes."""

    descriptor, before = _open_member(
        root_descriptor,
        snapshot,
        relative,
        root_mount_id,
    )
    try:
        size, digest, content = _hash_descriptor(
            descriptor,
            inventory=inventory,
            retain_content=retain_content,
            unique_remaining=unique_remaining,
        )
        after = _descriptor_stat(descriptor, _CODE_FILESYSTEM_MUTATED)
    finally:
        os.close(descriptor)
    if _identity(before) != _identity(after):
        _invalid(_CODE_FILESYSTEM_MUTATED)
    return _FileRecord(
        relative=relative,
        size=size,
        sha256=digest,
        identity=_identity(after),
        content=content,
    )


def _inventory_payload(record: _FileRecord) -> list[object]:
    """Decode one exact-shape inventory object."""

    if record.content is None:
        raise RuntimeError("inventory content was not retained")
    try:
        payload = json.loads(
            record.content,
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except BundleInvalid:
        raise
    except (ValueError, RecursionError):
        _invalid(_CODE_INVENTORY_MALFORMED)
    _check_json_depth(payload)
    if not isinstance(payload, dict) or set(payload) != {"artifacts"}:
        _invalid(_CODE_INVENTORY_MALFORMED)
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list):
        _invalid(_CODE_INVENTORY_MALFORMED)
    return artifacts


def _reject_json_constant(value: str) -> NoReturn:
    """Reject JSON's non-standard NaN and infinity spellings."""

    del value
    _invalid(_CODE_INVENTORY_MALFORMED)


def _check_json_depth(payload: object) -> None:
    """Reject excessive parser nesting without recursive Python traversal."""

    pending: list[tuple[object, int]] = [(payload, 1)]
    while pending:
        value, depth = pending.pop()
        if depth > _MAX_JSON_DEPTH:
            _invalid(_CODE_INVENTORY_MALFORMED)
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)


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


def _root_details(bundle: Path) -> tuple[int, _Identity, int]:
    """Open and identity-pin one real directory root."""

    if not _secure_descriptor_primitives_available():
        _invalid("bundle.filesystem.unsupported")
    root_stat = _root_path_stat(bundle)
    descriptor = _open_root_descriptor(bundle)
    try:
        opened, root_mount_id = _admit_open_root(descriptor, root_stat)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, _identity(opened), root_mount_id


def _root_path_stat(bundle: Path) -> os.stat_result:
    """Admit a lexical root that is a real directory rather than a link."""

    try:
        root_stat = bundle.lstat()
    except _PATH_ADMISSION_ERRORS:
        _invalid("bundle.root.invalid")
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        _invalid("bundle.root.invalid")
    return root_stat


def _open_root_descriptor(bundle: Path) -> int:
    """Open the selected root with directory and no-follow guarantees."""

    try:
        return os.open(bundle, _directory_flags())
    except _PATH_ADMISSION_ERRORS:
        _invalid("bundle.root.invalid")


def _admit_open_root(
    descriptor: int,
    path_stat: os.stat_result,
) -> tuple[os.stat_result, int]:
    """Bind a lexical root identity to its pinned descriptor and mount."""

    opened = _descriptor_stat(descriptor, _CODE_FILESYSTEM_MUTATED)
    if not stat.S_ISDIR(opened.st_mode) or _identity(opened) != _identity(path_stat):
        _invalid(_CODE_FILESYSTEM_MUTATED)
    root_mount_id = _mount_id(descriptor)
    if root_mount_id is None:
        _invalid("bundle.filesystem.unsupported")
    return opened, root_mount_id


def _assert_current_identity(
    bundle: Path,
    root_descriptor: int,
    expected: _Identity,
    root_mount_id: int,
) -> None:
    """Require both the lexical root and pinned descriptor to stay identical."""

    try:
        path_current = bundle.lstat()
    except _PATH_ADMISSION_ERRORS:
        _invalid(_CODE_FILESYSTEM_MUTATED)
    descriptor_current = _descriptor_stat(root_descriptor, _CODE_FILESYSTEM_MUTATED)
    if not stat.S_ISDIR(path_current.st_mode) or not stat.S_ISDIR(descriptor_current.st_mode):
        _invalid(_CODE_FILESYSTEM_MUTATED)
    if _identity(path_current) != expected or _identity(descriptor_current) != expected:
        _invalid(_CODE_FILESYSTEM_MUTATED)
    if _mount_id(root_descriptor) != root_mount_id:
        _invalid(_CODE_FILESYSTEM_MUTATED)


class _BundleVerifier(object):
    """Stateful bounded walk over one bundle's transitive inventory closure."""

    def __init__(
        self,
        bundle: Path,
        root_descriptor: int,
        root_identity: _Identity,
        root_mount_id: int,
    ) -> None:
        """Capture the root and initialize bounded verification state."""

        self.bundle = bundle
        self.root_descriptor = root_descriptor
        self.root_identity = root_identity
        self.root_mount_id = root_mount_id
        self.snapshot = _scan(root_descriptor, root_identity, root_mount_id)
        if _INVENTORY_NAME not in self.snapshot.files:
            _invalid("bundle.inventory.missing")
        self.records: dict[str, _FileRecord] = {}
        self.referenced: set[str] = set()
        self.inventories_seen: set[str] = set()
        self.inventory_queue = deque([_INVENTORY_NAME])
        self.entries_count = 0
        self.unique_bytes = 0

    def _read_record(
        self,
        relative: str,
        *,
        inventory: bool,
        retain_content: bool,
        charge: bool,
    ) -> _FileRecord:
        """Read one record with optional aggregate-byte charging."""

        remaining = MAX_UNIQUE_BYTES - self.unique_bytes if charge else None
        return _read_stable(
            self.root_descriptor,
            self.snapshot,
            relative,
            self.root_mount_id,
            inventory=inventory,
            retain_content=retain_content,
            unique_remaining=remaining,
        )

    @staticmethod
    def _metadata_only(record: _FileRecord) -> _FileRecord:
        """Drop buffered inventory bytes before retaining a record."""

        return _FileRecord(
            relative=record.relative,
            size=record.size,
            sha256=record.sha256,
            identity=record.identity,
        )

    @staticmethod
    def _same_record(first: _FileRecord, second: _FileRecord) -> bool:
        """Compare stable file metadata without comparing buffered content."""

        return (
            first.relative,
            first.size,
            first.sha256,
            first.identity,
        ) == (
            second.relative,
            second.size,
            second.sha256,
            second.identity,
        )

    def _record(
        self,
        relative: str,
        *,
        inventory: bool,
        retain_content: bool = False,
    ) -> _FileRecord:
        """Read each unique path once and charge it to the byte budget."""

        existing = self.records.get(relative)
        if existing is None:
            if relative not in self.snapshot.files:
                _invalid("bundle.inventory.member-missing")
            loaded = self._read_record(
                relative,
                inventory=inventory,
                retain_content=retain_content,
                charge=True,
            )
            self.records[relative] = self._metadata_only(loaded)
            self.unique_bytes += loaded.size
            return loaded
        if not retain_content:
            return existing
        loaded = self._read_record(
            relative,
            inventory=inventory,
            retain_content=True,
            charge=False,
        )
        if not self._same_record(existing, loaded):
            _invalid(_CODE_FILESYSTEM_MUTATED)
        return loaded

    def _start_inventory(self, inventory_path: str) -> tuple[PurePosixPath, list[object]]:
        """Admit one not-yet-seen inventory and return its base and entries."""

        if inventory_path in self.inventories_seen:
            _invalid("bundle.inventory.duplicate")
        self.inventories_seen.add(inventory_path)
        if len(self.inventories_seen) > MAX_INVENTORIES:
            _invalid("bundle.limit.inventories")
        record = self._record(inventory_path, inventory=True, retain_content=True)
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

        expected = set(self.snapshot.files) - {_INVENTORY_NAME}
        if self.referenced != expected:
            _invalid("bundle.inventory.membership-mismatch")

    def _verify_unchanged(self) -> None:
        """Re-scan and re-stat all read paths to reject concurrent mutation."""

        final_snapshot = _scan(
            self.root_descriptor,
            self.root_identity,
            self.root_mount_id,
            error_code=_CODE_FILESYSTEM_MUTATED,
        )
        if final_snapshot != self.snapshot:
            _invalid(_CODE_FILESYSTEM_MUTATED)
        _assert_current_identity(
            self.bundle,
            self.root_descriptor,
            self.root_identity,
            self.root_mount_id,
        )

    def verify(self) -> VerificationCard:
        """Run closure, membership, and final identity verification."""

        self._verify_closure()
        self._verify_membership()
        self._verify_unchanged()
        return VerificationCard(
            status="verified",
            code="bundle.integrity.verified",
            files=len(self.snapshot.files),
            inventories=len(self.inventories_seen),
            entries=self.entries_count,
            unique_bytes=self.unique_bytes,
        )


def verify_bundle(bundle: Path) -> VerificationCard:
    """Verify exact flat or transitive inventory closure without side effects."""

    root_descriptor, root_identity, root_mount_id = _root_details(bundle)
    try:
        return _BundleVerifier(
            bundle,
            root_descriptor,
            root_identity,
            root_mount_id,
        ).verify()
    finally:
        os.close(root_descriptor)


__all__: list[str] = []
