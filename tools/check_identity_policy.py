#!/usr/bin/env python3
"""Fail-closed retired-identity gate for raes-adapters.

One matcher owns the retired-token definition and is reused unchanged for four
surfaces, so they cannot drift apart:

1. tracked path *names*,
2. tracked file bytes,
3. wheel/sdist member names and bytes,
4. installed distribution metadata.

The only exception is the identity register described in ADR-002, which admits
exactly two record classes:

- ``external-identity`` -- a live identity this repository provably does not own
  (an immutable key or a shared workflow contract), carrying the condition that
  retires it;
- ``historical-record`` -- a superseded decision retained unchanged because it is
  an accurate record of what was decided, never current guidance.

Every entry is an exact path pinned by content digest and occurrence count, and
names its owner and rationale. The register fails closed when the digest drifts,
when the occurrence count changes, when the file disappears, or when an entry is
malformed. It carries no globs, path prefixes, or generated-file exclusions.

This module never spells the retired token contiguously: the matcher assembles
it from non-matching fragments so the gate needs no exemption for its own source.

Usage:
    check_identity_policy.py                     # scan the tracked tree
    check_identity_policy.py --archive <path>    # also scan a built archive
    check_identity_policy.py --update            # re-pin existing register entries

``--update`` refreshes the digest and occurrence count of entries that are
already registered, for when a registered file changes for an unrelated reason.
It cannot add an entry: granting a new exception stays a reviewed edit to the
register itself.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = REPO_ROOT / "docs" / "decisions" / "identity-register.yaml"

# Assembled from fragments; never written contiguously in tracked source.
_STEM = ("ac" + "es").encode()

# Token boundaries keep the gate usable: the stem appears inside ordinary words
# this repository uses constantly (surfaces, interfaces, spaces, traces,
# namespaces). Matching those would drive maintainers toward exemptions, which
# is exactly what ADR-002 forbids.
_MATCHER = re.compile(rb"(?<![A-Za-z])" + _STEM + rb"(?![A-Za-z])", re.IGNORECASE)

# The current stem, assembled the same way. A rename is malformed when this stem
# lands immediately after a letter -- "surf" + stem -- because a plain
# search-and-replace rewrote the retired stem inside an unrelated word.
_CURRENT_STEM = ("r" + "aes").encode()
_MALFORMED = re.compile(rb"[A-Za-z]" + _CURRENT_STEM, re.IGNORECASE)
_PERCENT_ESCAPE = re.compile(rb"%[0-9A-Fa-f]{2}")

# PEP 610 provenance is written by the *installer* at install time to record
# where a wheel was fetched from -- for a local install, the builder's absolute
# path. It is not part of what this repository publishes: the wheel and sdist are
# scanned wholesale by scan_archive, so a build-host directory name is not a
# distribution defect. Kept to exactly this one file; every other metadata file
# is scanned.
_INSTALLER_PROVENANCE = frozenset({"direct_url.json"})

_ALLOWED_RECORD_CLASSES = frozenset({"external-identity", "historical-record"})
_REQUIRED_FIELDS = (
    "path",
    "digest",
    "record_class",
    "owner",
    "rationale",
    "occurrences",
    "retires_when",
)


class RegisterError(ValueError):
    """The external-identity register is malformed or out of contract."""


@dataclass(frozen=True)
class Finding:
    kind: str  # "path" | "content"
    path: str
    count: int


@dataclass(frozen=True)
class RegisterEntry:
    path: str
    digest: str
    record_class: str
    owner: str
    rationale: str
    occurrences: int
    retires_when: str


def scan_bytes(data: bytes) -> list[int]:
    """Return the offset of every retired-token occurrence in ``data``."""
    return [m.start() for m in _MATCHER.finditer(data)]


def scan_malformed(data: bytes) -> list[int]:
    """Return offsets where the *current* token is glued inside another word.

    This is the inverse failure mode of a cutover, and the retired-token matcher
    is blind to it by construction. A careless whole-word replace rewrites every
    occurrence of the retired stem, including the ones inside unrelated words --
    turning "surfaces" into "surf" + the current token. The retired spelling is
    genuinely gone, so a scan for it reports clean while the prose is corrupted.
    Catching it here keeps a mechanical rename honest.
    """
    hits = []
    for match in _MALFORMED.finditer(data):
        # Percent-encoding puts a hex letter immediately before the stem:
        # "%2F" + "RAES..." in an encoded URL is a separator, not a glued word.
        if _PERCENT_ESCAPE.fullmatch(data[max(0, match.start() - 2) : match.start() + 1]):
            continue
        hits.append(match.start())
    return hits


def _scan_name(name: str) -> int:
    return len(scan_bytes(name.encode("utf-8", "surrogateescape")))


def _normalize(name: str) -> str:
    """PEP 503 style normalization so ``a-b`` and ``a_b`` compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


def scan_tree(root: Path, relpaths: list[str]) -> list[Finding]:
    """Scan path names and file bytes for every path in ``relpaths``."""
    findings: list[Finding] = []
    for rel in relpaths:
        name_hits = _scan_name(rel)
        if name_hits:
            findings.append(Finding("path", rel, name_hits))
        target = root / rel
        if not target.is_file() or target.is_symlink():
            continue
        try:
            content_hits = len(scan_bytes(target.read_bytes()))
        except OSError:
            continue
        if content_hits:
            findings.append(Finding("content", rel, content_hits))
    return findings


def _archive_members(archive: Path) -> list[tuple[str, bytes]]:
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            return [(i.filename, zf.read(i)) for i in zf.infolist() if not i.is_dir()]
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            members = []
            for info in tf.getmembers():
                if not info.isfile():
                    continue
                handle = tf.extractfile(info)
                members.append((info.name, handle.read() if handle else b""))
            return members
    raise RegisterError(f"unsupported archive format: {archive}")


def scan_archive(archive: Path) -> list[Finding]:
    """Scan member names and member bytes of a built wheel or sdist."""
    findings: list[Finding] = []
    for name, data in _archive_members(archive):
        name_hits = _scan_name(name)
        if name_hits:
            findings.append(Finding("path", f"{archive.name}:{name}", name_hits))
        content_hits = len(scan_bytes(data))
        if content_hits:
            findings.append(Finding("content", f"{archive.name}:{name}", content_hits))
    return findings


def scan_installed_metadata(
    site_packages: Path, distributions: set[str] | None = None
) -> list[Finding]:
    """Scan installed ``*.dist-info`` metadata for this repository's packages.

    ``distributions`` names the installed packages this repository publishes.
    Third-party dependencies are out of scope: this gate proves *our* artifacts
    carry no retired identity, and upstream projects legitimately ship tombstone
    records naming identities they themselves retired. Scanning those would
    report a dependency's governed history as our defect.
    """
    findings: list[Finding] = []
    for dist_info in sorted(site_packages.glob("*.dist-info")):
        key = _normalize(dist_info.name.split("-")[0])
        if distributions is not None and key not in {_normalize(d) for d in distributions}:
            continue
        name_hits = _scan_name(dist_info.name)
        if name_hits:
            findings.append(Finding("path", dist_info.name, name_hits))
        for meta in sorted(dist_info.iterdir()):
            if not meta.is_file() or meta.name in _INSTALLER_PROVENANCE:
                continue
            hits = len(scan_bytes(meta.read_bytes()))
            if hits:
                findings.append(Finding("content", f"{dist_info.name}/{meta.name}", hits))
    return findings


def _reject_unsafe_path(path: str) -> None:
    if any(ch in path for ch in "*?[]"):
        raise RegisterError(f"register entries must be exact paths, not globs: {path}")
    if path.endswith("/") or path in ("", "."):
        raise RegisterError(f"register entries must name a file, not a prefix: {path}")
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RegisterError(f"register entries must stay inside the repository: {path}")


def load_register(path: Path) -> list[RegisterEntry]:
    """Parse and structurally validate the register. Raises on any violation."""
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RegisterError(f"register is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise RegisterError("register must be a mapping with an 'entries' key")
    entries_raw = raw.get("entries") or []
    if not isinstance(entries_raw, list):
        raise RegisterError("register 'entries' must be a list")

    entries: list[RegisterEntry] = []
    seen: set[str] = set()
    for item in entries_raw:
        if not isinstance(item, dict):
            raise RegisterError("each register entry must be a mapping")
        missing = [f for f in _REQUIRED_FIELDS if not str(item.get(f, "")).strip()]
        if missing:
            raise RegisterError(f"register entry is missing required fields: {', '.join(missing)}")
        entry_path = str(item["path"])
        _reject_unsafe_path(entry_path)
        if entry_path in seen:
            raise RegisterError(f"duplicate register entry: {entry_path}")
        seen.add(entry_path)
        record_class = str(item["record_class"])
        if record_class not in _ALLOWED_RECORD_CLASSES:
            raise RegisterError(
                f"unsupported record_class '{record_class}' for {entry_path}; "
                f"expected one of {sorted(_ALLOWED_RECORD_CLASSES)}"
            )
        try:
            occurrences = int(item["occurrences"])
        except (TypeError, ValueError) as exc:
            raise RegisterError(f"occurrences must be an integer for {entry_path}") from exc
        if occurrences < 1:
            raise RegisterError(f"occurrences must be positive for {entry_path}")
        entries.append(
            RegisterEntry(
                path=entry_path,
                digest=str(item["digest"]),
                record_class=record_class,
                owner=str(item["owner"]),
                rationale=str(item["rationale"]),
                occurrences=occurrences,
                retires_when=str(item["retires_when"]),
            )
        )
    return entries


def validate_register(root: Path, entries: list[RegisterEntry]) -> list[str]:
    """Verify every registered file still matches its pin. Fails closed."""
    errors: list[str] = []
    for entry in entries:
        target = root / entry.path
        if not target.is_file():
            errors.append(f"{entry.path}: registered file is missing")
            continue
        data = target.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry.digest:
            errors.append(
                f"{entry.path}: registered digest drifted "
                f"(expected {entry.digest}, found {digest}); re-review the entry"
            )
            continue
        actual = len(scan_bytes(data)) + _scan_name(entry.path)
        if actual != entry.occurrences:
            errors.append(
                f"{entry.path}: registered occurrence count drifted "
                f"(expected {entry.occurrences}, found {actual})"
            )
    return errors


def repin_register(root: Path, register_path: Path) -> int:
    """Refresh the digest and occurrence count of every existing entry.

    Rewrites each entry inside its own YAML block. A global first-match replace
    is wrong here: entries commonly share an occurrence count, so the first
    matching line can belong to a different entry -- corrupting one record while
    leaving the intended one stale.

    Deliberately cannot *add* an entry. Re-pinning is for a registered file that
    changed for an unrelated reason; granting a new exception stays a reviewed
    human edit to the register, so this flag can never wave a fresh violation
    through.
    """
    entries = load_register(register_path)
    if not entries:
        return 0
    by_path = {entry.path: entry for entry in entries}

    out: list[str] = []
    current: str | None = None
    changed: set[str] = set()
    for line in register_path.read_text(encoding="utf-8").splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("- path:"):
            current = stripped.split("- path:", 1)[1].strip()
        entry = by_path.get(current) if current else None
        if entry is not None:
            target = root / entry.path
            if target.is_file():
                data = target.read_bytes()
                if stripped.startswith("digest:"):
                    digest = hashlib.sha256(data).hexdigest()
                    if digest != entry.digest:
                        line = line.replace(entry.digest, digest)
                        changed.add(entry.path)
                elif stripped.startswith("occurrences:"):
                    occurrences = len(scan_bytes(data)) + _scan_name(entry.path)
                    if occurrences != entry.occurrences:
                        line = line.replace(
                            f"occurrences: {entry.occurrences}", f"occurrences: {occurrences}"
                        )
                        changed.add(entry.path)
        out.append(line)

    register_path.write_text("".join(out), encoding="utf-8")
    return len(changed)


class PolicyError(RuntimeError):
    """The gate could not establish what it is supposed to scan."""


def _tracked_paths(root: Path) -> list[str]:
    """List tracked files, or raise. Never returns an empty list quietly.

    Returning [] on failure would make every downstream scan trivially clean:
    a missing git binary or a broken checkout would silently disable the primary
    policy surface and still report success. A gate that cannot enumerate its
    inputs must fail closed, not pass vacuously.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--exclude-standard"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PolicyError(f"could not list tracked files under {root}: {exc}") from exc
    paths = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    if not paths:
        raise PolicyError(
            f"git reported no tracked files under {root}; refusing to report a clean tree"
        )
    return paths


def check_repository(root: Path, register_path: Path | None = None) -> list[str]:
    """Scan the tracked tree; registered external identities are the exception."""
    register_file = register_path or REGISTER_PATH
    try:
        entries = load_register(register_file)
    except RegisterError as exc:
        return [f"external-identity register is invalid: {exc}"]

    errors = validate_register(root, entries)
    registered = {e.path for e in entries}

    try:
        tracked = _tracked_paths(root)
    except PolicyError as exc:
        errors.append(str(exc))
        return errors

    for finding in scan_tree(root, tracked):
        if finding.path in registered and finding.kind == "content":
            continue
        errors.append(
            f"{finding.path}: retired identity found in {finding.kind} "
            f"({finding.count} occurrence(s))"
        )

    # A registered file is exempt from the retired token, never from corruption.
    for rel in tracked:
        target = root / rel
        if not target.is_file() or target.is_symlink():
            continue
        try:
            hits = scan_malformed(target.read_bytes())
        except OSError:
            continue
        if hits:
            errors.append(
                f"{rel}: malformed rename -- the current identity is glued inside "
                f"a word at {len(hits)} site(s); a replace rewrote the retired stem "
                "inside unrelated text"
            )
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--archive", action="append", default=[])
    parser.add_argument("--site-packages", default=None)
    parser.add_argument(
        "--distribution",
        action="append",
        default=[],
        help="installed distribution owned by this repository (repeatable)",
    )
    parser.add_argument("--update", action="store_true")
    args, _unknown = parser.parse_known_args(argv)

    if args.update:
        updated = repin_register(REPO_ROOT, REGISTER_PATH)
        print(f"identity policy: re-pinned {updated} register entry(ies)")
        return 0

    failures = check_repository(REPO_ROOT)

    for archive in args.archive:
        failures.extend(
            f"{f.path}: retired identity in built artifact {f.kind}"
            for f in scan_archive(Path(archive))
        )
    if args.site_packages:
        if not args.distribution:
            print(
                "identity policy: --site-packages requires at least one --distribution",
                file=sys.stderr,
            )
            return 1
        failures.extend(
            f"{f.path}: retired identity in installed metadata {f.kind}"
            for f in scan_installed_metadata(Path(args.site_packages), set(args.distribution))
        )

    if failures:
        print("identity policy: FAIL", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("identity policy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
