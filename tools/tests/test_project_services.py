from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

from tools.check_project_services import (
    _validate_ci,
    _validate_codeql,
    _validate_devmain,
    _validate_docs_requirements,
    _validate_ground_control,
    _validate_release_workflow,
    validate_action_pins,
    validate_repository,
    validate_workflow_policy,
)

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

    def test_hygiene_bulk_commands_suppress_the_repository_file_list(self) -> None:
        calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        class FakeSession:
            def run(self, *args: object, **kwargs: object) -> None:
                calls.append((args, kwargs))

            def log(self, _message: str) -> None:
                pass

        fake_nox = ModuleType("nox")
        fake_nox.Session = FakeSession  # type: ignore[attr-defined]
        fake_nox.options = SimpleNamespace()  # type: ignore[attr-defined]

        def session_decorator(function: object | None = None, *, name: str | None = None) -> object:
            del name
            if function is not None:
                return function
            return lambda decorated: decorated

        fake_nox.session = session_decorator  # type: ignore[attr-defined]
        spec = importlib.util.spec_from_file_location(
            "noxfile_under_test", REPO_ROOT / "noxfile.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)

        previous_nox = sys.modules.get("nox")
        sys.modules["nox"] = fake_nox
        try:
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        finally:
            if previous_nox is None:
                del sys.modules["nox"]
            else:
                sys.modules["nox"] = previous_nox

        module._hygiene(  # type: ignore[attr-defined]
            FakeSession(),
            [
                "README.md",
                "mkdocs.yml",
                "release-please-config.json",
                "tests/test_base_smoke.py",
            ],
        )

        self.assertEqual(7, len(calls))
        self.assertTrue(all(kwargs.get("log") is False for _args, kwargs in calls))

    def test_ground_control_retired_routing_fallback_is_detected(self) -> None:
        errors: list[str] = []
        _validate_ground_control("routing:\n  default_fallback: permissive\n", errors)
        self.assertEqual([".ground-control.yaml: routing.default_fallback is retired"], errors)

    def test_devmain_restricted_git_command_is_detected(self) -> None:
        errors: list[str] = []
        _validate_devmain("devmain:\n\tgit push origin dev\n", errors)
        self.assertIn("Makefile: devmain must only open the promotion PR", errors)

    def test_unpinned_docs_requirement_is_detected(self) -> None:
        errors: list[str] = []
        _validate_docs_requirements("mkdocs>=1.6\n", errors)
        self.assertEqual(
            ["docs/requirements.txt: dependencies must be exactly pinned: mkdocs>=1.6"],
            errors,
        )

    def test_codeql_continue_on_error_is_detected(self) -> None:
        errors: list[str] = []
        _validate_codeql("continue-on-error: true\n", errors)
        self.assertIn(".github/workflows/codeql-analysis.yml: CodeQL must fail closed", errors)

    def test_ci_required_job_contract_violation_is_detected(self) -> None:
        errors: list[str] = []
        _validate_ci("name: PR Gate\n", errors)
        self.assertIn(
            ".github/workflows/ci.yml: missing required configuration: "
            "needs: [fast-checks, policy, tool-tests, typecheck, tests, "
            "distributions, docs, sonar]",
            errors,
        )

    def test_release_workflow_pypi_credential_is_detected(self) -> None:
        errors: list[str] = []
        _validate_release_workflow("PYPI_API_TOKEN: forbidden\n", errors)
        self.assertIn(
            ".github/workflows/release-please.yml: forbidden release setting present: "
            "PYPI_API_TOKEN",
            errors,
        )

    def test_github_pages_permission_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workflow = repo_root / ".github" / "workflows" / "pages.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("permissions:\n  pages: write\n", encoding="utf-8")

            self.assertEqual(
                [".github/workflows/pages.yml: GitHub Pages publishing is retired"],
                validate_workflow_policy(workflow, repo_root),
            )


if __name__ == "__main__":
    unittest.main()
