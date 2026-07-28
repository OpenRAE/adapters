from __future__ import annotations

import unittest
from pathlib import Path

from tools.check_repo_policy import (
    _manifest_version,
    _pyproject_version,
    changelog_ownership_failures,
    version_consistency_failures,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class VersionConsistencyTests(unittest.TestCase):
    def test_matching_versions_pass(self) -> None:
        self.assertEqual([], version_consistency_failures("0.1.0", "0.1.0"))

    def test_mismatch_fails(self) -> None:
        errors = version_consistency_failures("0.2.0", "0.1.0")
        self.assertEqual(1, len(errors))
        self.assertIn("lockstep", errors[0])

    def test_real_repo_version_matches_manifest(self) -> None:
        self.assertEqual(_pyproject_version(REPO_ROOT), _manifest_version(REPO_ROOT))


class ChangelogOwnershipTests(unittest.TestCase):
    def test_changelog_edited_with_manifest_passes(self) -> None:
        # A real release bumps both together.
        self.assertEqual(
            [],
            changelog_ownership_failures(["CHANGELOG.md", ".release-please-manifest.json"]),
        )

    def test_changelog_hand_edit_without_manifest_fails(self) -> None:
        errors = changelog_ownership_failures(["CHANGELOG.md", "src/raes_adapters/__init__.py"])
        self.assertEqual(1, len(errors))
        self.assertIn("Release Please", errors[0])

    def test_unrelated_changes_pass(self) -> None:
        self.assertEqual([], changelog_ownership_failures(["src/x.py", "tests/y.py"]))


if __name__ == "__main__":
    unittest.main()
