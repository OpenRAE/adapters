"""Tests for the fail-closed retired-identity policy.

This module never spells the retired token contiguously: every fixture builds it
from non-matching fragments so the policy needs no exemption for its own tests.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.check_identity_policy import (
    RegisterError,
    check_repository,
    load_register,
    repin_register,
    scan_archive,
    scan_bytes,
    scan_installed_metadata,
    scan_malformed,
    scan_tree,
    validate_register,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Assembled, never written contiguously.
_R = "ac" + "es"
_R_UPPER = _R.upper()


class MatcherTests(unittest.TestCase):
    def test_flags_retired_token_at_word_boundaries(self) -> None:
        for sample in (
            f"{_R}-adapters",
            f"{_R}_adapter_cyborg",
            f"{_R_UPPER}_REQUIREMENT_UID",
            f"name = {_R}-adapter-cyborg",
            f"see {_R_UPPER} ADR-069",
            f"({_R})",
        ):
            with self.subTest(sample=sample):
                self.assertEqual(1, len(scan_bytes(sample.encode("utf-8"))), sample)

    def test_ignores_the_token_inside_unrelated_words(self) -> None:
        # These are common in this repo's prose; flagging them would make the
        # gate unusable and push maintainers toward exemptions.
        for sample in (
            "published surfaces",
            "backend interfaces",
            "two spaces",
            "replay traces",
            "faces and races",
            "namespaces",
        ):
            with self.subTest(sample=sample):
                self.assertEqual([], scan_bytes(sample.encode("utf-8")), sample)

    def test_counts_every_occurrence(self) -> None:
        payload = f"{_R}-adapters and {_R}_adapter_cyborg".encode()
        self.assertEqual(2, len(scan_bytes(payload)))

    def test_binary_content_is_scanned_without_decoding_errors(self) -> None:
        payload = b"\x00\xff" + f"{_R}-adapters".encode() + b"\x00"
        self.assertEqual(1, len(scan_bytes(payload)))


class MalformedRenameTests(unittest.TestCase):
    """The inverse failure mode: a careless rename gluing the current token
    inside an unrelated word. A naive replace turns "surfaces" into "surf"+the
    current token, which the retired-token matcher cannot see because the retired
    spelling is gone."""

    def test_current_token_glued_inside_a_word_is_flagged(self) -> None:
        for sample in ("new features / surfr" + "aes", "interfr" + "aes", "spr" + "aes"):
            with self.subTest(sample=sample):
                self.assertEqual(1, len(scan_malformed(sample.encode("utf-8"))), sample)

    def test_legitimate_current_identifiers_are_not_flagged(self) -> None:
        for sample in (
            "raes==2.0.0",
            "raes_adapter_cyborg",
            "raes-adapter-cyborg",
            "raes_contracts",
            "raes-adapters",
            "import raes_backend_protocols",
            "RAES is the authority",
            # Percent-encoded URL: the "F" of "%2F" precedes the stem.
            "bestpractices.dev/projects?as=badge&url=https%3A%2F%2Fgithub.com%2FOpenRAE%2Fadapters",
        ):
            with self.subTest(sample=sample):
                self.assertEqual([], scan_malformed(sample.encode("utf-8")), sample)

    def test_repository_tree_has_no_malformed_renames(self) -> None:
        from tools.check_identity_policy import check_repository

        self.assertEqual([], [e for e in check_repository(REPO_ROOT) if "malformed" in e])


class TreeScanTests(unittest.TestCase):
    def test_path_names_are_scanned_even_when_content_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "src" / f"{_R}_adapter_cyborg"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text("clean content\n", encoding="utf-8")

            findings = scan_tree(root, [f"src/{_R}_adapter_cyborg/__init__.py"])

            self.assertEqual(1, len(findings))
            self.assertEqual("path", findings[0].kind)

    def test_content_findings_report_the_owning_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(f"built on {_R_UPPER}\n", encoding="utf-8")

            findings = scan_tree(root, ["README.md"])

            self.assertEqual(1, len(findings))
            self.assertEqual("content", findings[0].kind)
            self.assertEqual("README.md", findings[0].path)


class ArchiveScanTests(unittest.TestCase):
    def test_archive_member_names_and_bytes_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pkg-0.0.0-py3-none-any.whl"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(f"{_R}_adapter_cyborg/__init__.py", "clean\n")
                zf.writestr("pkg/METADATA", f"Name: {_R}-adapter-cyborg\n")

            findings = scan_archive(archive)

            kinds = sorted({f.kind for f in findings})
            self.assertEqual(["content", "path"], kinds)

    def test_clean_archive_produces_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pkg-0.0.0-py3-none-any.whl"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("raes_adapter_cyborg/__init__.py", "clean\n")

            self.assertEqual([], scan_archive(archive))


class RegisterTests(unittest.TestCase):
    """The register is the single narrow exception, and it fails closed."""

    def _write(self, root: Path, body: str) -> Path:
        path = root / "register.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def _entry(self, path: str, digest: str, occurrences: int) -> str:
        return (
            "entries:\n"
            f"  - path: {path}\n"
            f"    digest: {digest}\n"
            "    record_class: external-identity\n"
            "    owner: ground-control\n"
            "    rationale: immutable key in an external system of record\n"
            f"    occurrences: {occurrences}\n"
            "    retires_when: ground control offers an identifier migration\n"
        )

    def test_matching_digest_and_count_suppresses_the_registered_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "config.yaml"
            target.write_text(f"project: {_R}-adapters\n", encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            register = load_register(self._write(root, self._entry("config.yaml", digest, 1)))

            self.assertEqual([], validate_register(root, register))

    def test_digest_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "config.yaml"
            target.write_text(f"project: {_R}-adapters\n", encoding="utf-8")
            stale = hashlib.sha256(b"something else").hexdigest()
            register = load_register(self._write(root, self._entry("config.yaml", stale, 1)))

            errors = validate_register(root, register)

            self.assertEqual(1, len(errors))
            self.assertIn("digest", errors[0])

    def test_occurrence_count_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "config.yaml"
            target.write_text(f"a: {_R}-adapters\nb: {_R}-adapters\n", encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            register = load_register(self._write(root, self._entry("config.yaml", digest, 1)))

            errors = validate_register(root, register)

            self.assertEqual(1, len(errors))
            self.assertIn("occurrence", errors[0])

    def test_missing_registered_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest = hashlib.sha256(b"gone").hexdigest()
            register = load_register(self._write(root, self._entry("config.yaml", digest, 1)))

            errors = validate_register(root, register)

            self.assertEqual(1, len(errors))
            self.assertIn("missing", errors[0])

    def test_glob_and_prefix_entries_are_rejected(self) -> None:
        digest = hashlib.sha256(b"x").hexdigest()
        for path in ("docs/*", "docs/", "**/*.md", "../escape.yaml"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self.assertRaises(RegisterError):
                    load_register(self._write(root, self._entry(path, digest, 1)))

    def test_historical_record_class_is_accepted(self) -> None:
        """A superseded decision is retained and pinned, not deleted."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "adr.md"
            target.write_text(f"decided under {_R_UPPER}\n", encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            body = self._entry("adr.md", digest, 1).replace(
                "record_class: external-identity", "record_class: historical-record"
            )

            entries = load_register(self._write(root, body))

            self.assertEqual("historical-record", entries[0].record_class)
            self.assertEqual([], validate_register(root, entries))

    def test_unknown_record_class_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest = hashlib.sha256(b"x").hexdigest()
            body = self._entry("adr.md", digest, 1).replace(
                "record_class: external-identity", "record_class: convenient"
            )
            with self.assertRaises(RegisterError):
                load_register(self._write(root, body))

    def test_entry_must_declare_owner_rationale_and_retirement(self) -> None:
        digest = hashlib.sha256(b"x").hexdigest()
        for field in ("owner", "rationale", "retires_when"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                body = "\n".join(
                    line
                    for line in self._entry("config.yaml", digest, 1).splitlines()
                    if not line.strip().startswith(f"{field}:")
                )
                with self.assertRaises(RegisterError):
                    load_register(self._write(root, body + "\n"))


class InstalledMetadataScopeTests(unittest.TestCase):
    """The gate proves *our* artifacts are clean, not our dependencies'."""

    def _dist_info(self, site_packages: Path, name: str) -> Path:
        dist_info = site_packages / f"{name}.dist-info"
        dist_info.mkdir(parents=True)
        return dist_info

    def test_third_party_distribution_metadata_is_not_scanned(self) -> None:
        # Upstream ships tombstones naming retired identities on purpose; that is
        # their governed historical record, and not this repository's artifact.
        with tempfile.TemporaryDirectory() as tmp:
            site_packages = Path(tmp)
            upstream = self._dist_info(site_packages, "raes-2.0.0")
            (upstream / "RECORD").write_text(
                f"raes_contracts/_corpus/tombstones/{_R}-semantic-invariants.json,,\n",
                encoding="utf-8",
            )
            ours = self._dist_info(site_packages, "raes_adapter_cyborg-0.0.0")
            (ours / "METADATA").write_text("Name: raes-adapter-cyborg\n", encoding="utf-8")

            self.assertEqual([], scan_installed_metadata(site_packages, {"raes_adapter_cyborg"}))

    def test_our_distribution_metadata_is_still_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site_packages = Path(tmp)
            ours = self._dist_info(site_packages, "raes_adapter_cyborg-0.0.0")
            (ours / "METADATA").write_text(f"Name: {_R}-adapter-cyborg\n", encoding="utf-8")

            findings = scan_installed_metadata(site_packages, {"raes_adapter_cyborg"})

            self.assertEqual(1, len(findings))
            self.assertEqual("content", findings[0].kind)

    def test_installer_provenance_is_not_distribution_content(self) -> None:
        # PEP 610 direct_url.json records where the installer fetched the wheel
        # from. It is generated at install time and is not part of what we
        # publish; the wheel itself is scanned wholesale by scan_archive.
        with tempfile.TemporaryDirectory() as tmp:
            site_packages = Path(tmp)
            ours = self._dist_info(site_packages, "raes_adapter_cyborg-0.0.0")
            (ours / "direct_url.json").write_text(
                f'{{"url":"file:///home/dev/{_R}-adapters/dist/pkg.whl"}}',
                encoding="utf-8",
            )

            self.assertEqual([], scan_installed_metadata(site_packages, {"raes_adapter_cyborg"}))


class RepinTests(unittest.TestCase):
    """Re-pinning refreshes existing entries; it never grants new exceptions."""

    def _register_body(self, digest: str, occurrences: int) -> str:
        return (
            "entries:\n"
            "  - path: config.yaml\n"
            f"    digest: {digest}\n"
            "    record_class: external-identity\n"
            "    owner: ground-control\n"
            "    rationale: immutable key in an external system of record\n"
            f"    occurrences: {occurrences}\n"
            "    retires_when: tracked upstream\n"
        )

    def test_repin_refreshes_a_legitimately_changed_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "config.yaml"
            target.write_text(f"project: {_R}-adapters\n", encoding="utf-8")
            register = root / "register.yaml"
            stale = hashlib.sha256(b"stale").hexdigest()
            register.write_text(self._register_body(stale, 1), encoding="utf-8")

            repin_register(root, register)

            self.assertEqual([], validate_register(root, load_register(register)))

    def test_repin_does_not_add_an_unregistered_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.yaml").write_text(f"project: {_R}-adapters\n", encoding="utf-8")
            # A new violation appears that nobody registered.
            (root / "sneaky.md").write_text(f"{_R_UPPER} lives here\n", encoding="utf-8")
            register = root / "register.yaml"
            digest = hashlib.sha256((root / "config.yaml").read_bytes()).hexdigest()
            register.write_text(self._register_body(digest, 1), encoding="utf-8")

            repin_register(root, register)

            entries = load_register(register)
            self.assertEqual(["config.yaml"], [e.path for e in entries])


class FailClosedDiscoveryTests(unittest.TestCase):
    """A gate that cannot enumerate the tree must not report it clean."""

    def test_non_repository_root_is_an_error_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)  # not a git checkout
            (root / "register.yaml").write_text("entries: []\n", encoding="utf-8")

            errors = check_repository(root, root / "register.yaml")

            self.assertTrue(errors, "an unlistable tree must fail closed")
            self.assertTrue(any("tracked" in e for e in errors), errors)


class RepinMultiEntryTests(unittest.TestCase):
    """Re-pinning must rewrite the entry it is pinning, not a lookalike."""

    def _two_entries(self, digest_a: str, digest_b: str) -> str:
        return (
            "entries:\n"
            "  - path: first.md\n"
            f"    digest: {digest_a}\n"
            "    record_class: external-identity\n"
            "    owner: ground-control\n"
            "    rationale: first\n"
            "    occurrences: 1\n"
            "    retires_when: tracked upstream\n"
            "  - path: second.md\n"
            f"    digest: {digest_b}\n"
            "    record_class: external-identity\n"
            "    owner: ground-control\n"
            "    rationale: second\n"
            "    occurrences: 1\n"
            "    retires_when: tracked upstream\n"
        )

    def test_repinning_a_later_entry_leaves_the_earlier_one_intact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.md"
            second = root / "second.md"
            # Both start with one occurrence, so the occurrence lines are
            # identical and a global first-match replace would hit the wrong one.
            first.write_text(f"{_R_UPPER} once\n", encoding="utf-8")
            second.write_text(f"{_R_UPPER} once\n", encoding="utf-8")
            digest_a = hashlib.sha256(first.read_bytes()).hexdigest()
            digest_b = hashlib.sha256(second.read_bytes()).hexdigest()
            register = root / "register.yaml"
            register.write_text(self._two_entries(digest_a, digest_b), encoding="utf-8")

            # Only the second file changes, gaining an occurrence.
            second.write_text(f"{_R_UPPER} twice {_R_UPPER}\n", encoding="utf-8")
            repin_register(root, register)

            entries = {e.path: e for e in load_register(register)}
            self.assertEqual(1, entries["first.md"].occurrences)
            self.assertEqual(digest_a, entries["first.md"].digest)
            self.assertEqual(2, entries["second.md"].occurrences)
            self.assertEqual([], validate_register(root, load_register(register)))


class RepositoryTreeTests(unittest.TestCase):
    def test_tracked_tree_carries_no_unregistered_retired_identity(self) -> None:
        from tools.check_identity_policy import check_repository

        errors = check_repository(REPO_ROOT)

        self.assertEqual([], errors, "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
