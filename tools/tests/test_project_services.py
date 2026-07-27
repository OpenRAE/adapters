from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.check_project_services import validate_action_pins, validate_repository

REPO_ROOT = Path(__file__).resolve().parents[2]


class ProjectServicesPolicyTests(unittest.TestCase):
    def test_repository_configuration_satisfies_policy(self) -> None:
        errors = validate_repository(REPO_ROOT)
        self.assertEqual([], errors, "\n".join(errors))

    def test_action_refs_must_be_full_commit_shas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow = Path(tmp) / "workflow.yml"
            workflow.write_text(
                "steps:\n  - uses: actions/checkout@v7\n",
                encoding="utf-8",
            )

            self.assertEqual(
                [
                    "workflow.yml: GitHub Action references must use full "
                    "40-character commit SHAs: actions/checkout@v7"
                ],
                validate_action_pins(workflow, Path(tmp)),
            )


if __name__ == "__main__":
    unittest.main()
