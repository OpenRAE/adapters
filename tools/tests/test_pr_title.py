from __future__ import annotations

import unittest

from tools.check_pr_title import _validate


class PrTitleConventionalCommitTests(unittest.TestCase):
    def test_valid_conventional_titles_pass(self) -> None:
        for title in (
            "feat: add the cyborg backend module",
            "fix(cyborg): guard the optional import",
            "chore(main): release 0.1.0",
            "chore: back-merge v0.1.0 into dev",
            "docs: document the release process",
            "feat!: drop the per-adapter monorepo layout",
        ):
            with self.subTest(title=title):
                self.assertEqual([], _validate(title), title)

    def test_non_conventional_title_is_rejected(self) -> None:
        errors = _validate("adopt release please and publish to pypi")
        self.assertTrue(any("Conventional Commit" in e for e in errors), errors)

    def test_capitalized_subject_is_rejected(self) -> None:
        errors = _validate("feat: Add the cyborg backend module")
        self.assertTrue(any("capital letter" in e for e in errors), errors)

    def test_bracketed_agent_tag_is_rejected(self) -> None:
        errors = _validate("[codex] feat: add the cyborg backend module")
        self.assertTrue(any("bracketed tag" in e for e in errors), errors)

    def test_attribution_is_rejected(self) -> None:
        errors = _validate("feat: add module generated with an assistant")
        self.assertTrue(any("branding" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
