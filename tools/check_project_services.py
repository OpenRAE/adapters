#!/usr/bin/env python3
"""Validate repository-owned governance and external-service configuration."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ACTION_REF_RE = re.compile(r"uses:\s*([^@\s]+)@([^\s#]+)")
FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")
EXACT_REQUIREMENT_RE = re.compile(r"[A-Za-z0-9_.-]+==[^=\s]+")


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.name


def validate_action_pins(path: Path, repo_root: Path) -> list[str]:
    """Return errors for non-local GitHub Actions not pinned to a full SHA."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for action, ref in ACTION_REF_RE.findall(text):
        if action.startswith("./"):
            continue
        if not FULL_SHA_RE.fullmatch(ref):
            errors.append(
                f"{_relative(path, repo_root)}: GitHub Action references must use full "
                f"40-character commit SHAs: {action}@{ref}"
            )
    return errors


def _require(text: str, expected: str, path: str, errors: list[str]) -> None:
    if expected not in text:
        errors.append(f"{path}: missing required configuration: {expected}")


def _read_required(repo_root: Path, relative: str, errors: list[str]) -> str:
    path = repo_root / relative
    if not path.is_file():
        errors.append(f"{relative}: required file is missing")
        return ""
    return path.read_text(encoding="utf-8")


def _validate_devmain(makefile: str, errors: list[str]) -> None:
    match = re.search(r"^devmain:.*\n(?P<recipe>(?:\t.*\n)+)", makefile, re.MULTILINE)
    if match is None:
        errors.append("Makefile: missing devmain recipe")
        return
    recipe = match.group("recipe")
    for expected in (
        "gh pr create --base main --head dev",
        '--title "chore(main): promote dev"',
        "Merge with a merge commit",
    ):
        _require(recipe, expected, "Makefile", errors)
    if re.search(r"\b(?:git\s+(?:checkout|switch|merge|rebase|push)|gh\s+pr\s+merge)\b", recipe):
        errors.append("Makefile: devmain must only open the promotion PR")


def _validate_docs_requirements(text: str, errors: list[str]) -> None:
    requirements = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    ]
    if not requirements:
        errors.append("docs/requirements.txt: no locked requirements found")
    for requirement in requirements:
        if not EXACT_REQUIREMENT_RE.match(requirement):
            errors.append(
                f"docs/requirements.txt: dependencies must be exactly pinned: {requirement}"
            )


def validate_repository(repo_root: Path) -> list[str]:
    """Validate the complete repository-owned project-services contract."""
    errors: list[str] = []

    ground_control = _read_required(repo_root, ".ground-control.yaml", errors)
    _require(ground_control, "github_repo: RAESystem/adapters", ".ground-control.yaml", errors)
    _require(ground_control, "project_key: RAESystem_adapters", ".ground-control.yaml", errors)
    _require(ground_control, "test_command: make verify", ".ground-control.yaml", errors)
    _require(ground_control, "completion_command: make verify", ".ground-control.yaml", errors)
    _require(ground_control, "policy_command: make policy", ".ground-control.yaml", errors)
    _require(ground_control, "precommit_command: make precommit", ".ground-control.yaml", errors)
    if "default_fallback:" in ground_control:
        errors.append(".ground-control.yaml: routing.default_fallback is retired")

    root_pyproject = _read_required(repo_root, "pyproject.toml", errors)
    _require(root_pyproject, 'name = "raes-adapters"', "pyproject.toml", errors)

    makefile = _read_required(repo_root, "Makefile", errors)
    _require(makefile, ".PHONY:", "Makefile", errors)
    _validate_devmain(makefile, errors)
    for target in ("policy:", "precommit:", "prepush:", "verify:"):
        _require(makefile, target, "Makefile", errors)

    precommit = _read_required(repo_root, ".pre-commit-config.yaml", errors)
    for expected in ("entry: make precommit", "entry: make prepush"):
        _require(precommit, expected, ".pre-commit-config.yaml", errors)

    readthedocs = _read_required(repo_root, ".readthedocs.yaml", errors)
    for expected in (
        "version: 2",
        'os: "ubuntu-24.04"',
        'python: "3.12"',
        "configuration: mkdocs.yml",
        "requirements: docs/requirements.txt",
    ):
        _require(readthedocs, expected, ".readthedocs.yaml", errors)

    mkdocs = _read_required(repo_root, "mkdocs.yml", errors)
    for expected in (
        "site_name: RAES Adapters",
        "READTHEDOCS_CANONICAL_URL",
        "name: material",
        "docs_dir: docs",
    ):
        _require(mkdocs, expected, "mkdocs.yml", errors)

    docs_requirements = _read_required(repo_root, "docs/requirements.txt", errors)
    _validate_docs_requirements(docs_requirements, errors)

    codeql = _read_required(repo_root, ".github/workflows/codeql-analysis.yml", errors)
    for expected in (
        "name: CodeQL",
        "jobs:\n  analyze:\n    name: CodeQL",
        "branches: [main, dev]",
        "security-events: write",
        "languages: python",
        "queries: security-extended",
    ):
        _require(codeql, expected, ".github/workflows/codeql-analysis.yml", errors)
    if "continue-on-error:" in codeql:
        errors.append(".github/workflows/codeql-analysis.yml: CodeQL must fail closed")

    title_lint = _read_required(repo_root, ".github/workflows/pr-title-lint.yml", errors)
    _require(title_lint, "name: Lint PR title", ".github/workflows/pr-title-lint.yml", errors)

    ci = _read_required(repo_root, ".github/workflows/ci.yml", errors)
    # The verification graph runs as independent parallel jobs; `PR Gate` is the
    # single aggregating required check that keeps every stage mandatory before a
    # protected-branch merge. Pin its contract so no job can silently leave the
    # gate: it must depend on every verification job plus Sonar, run on every PR,
    # and fail closed unless each verification job succeeded (and Sonar passed on
    # same-repository PRs). Adding a verification job means extending this list.
    for expected in (
        "name: PR Gate",
        "needs: [fast-checks, policy, tool-tests, typecheck, tests, distributions, docs, sonar]",
        "if: ${{ always() && github.event_name == 'pull_request' }}",
        '.value.result == "success"',
        "A required verification job did not succeed",
        "SonarCloud did not succeed for a same-repository PR",
    ):
        _require(ci, expected, ".github/workflows/ci.yml", errors)

    scorecard = _read_required(repo_root, ".github/workflows/scorecard.yml", errors)
    for expected in (
        "name: OpenSSF Scorecard",
        "permissions: read-all",
        "security-events: write",
        "id-token: write",
        "publish_results: true",
        "results_format: sarif",
        "github/codeql-action/upload-sarif@",
    ):
        _require(scorecard, expected, ".github/workflows/scorecard.yml", errors)

    noxfile = _read_required(repo_root, "noxfile.py", errors)
    for expected in (
        "def _docs(session: nox.Session)",
        '"mkdocs",\n        "build",\n        "--strict",',
        "def _tool_tests(session: nox.Session)",
        '"tools/check_project_services.py"',
    ):
        _require(noxfile, expected, "noxfile.py", errors)

    sonar = _read_required(repo_root, "sonar-project.properties", errors)
    for expected in (
        "sonar.projectKey=RAESystem_adapters",
        "sonar.projectName=RAES Adapters",
        "sonar.organization=brad-edwards",
        "sonar.qualitygate.wait=true",
    ):
        _require(sonar, expected, "sonar-project.properties", errors)

    readme = _read_required(repo_root, "README.md", errors)
    for expected in (
        "readthedocs.org/projects/raes-adapters/badge/",
        "api.scorecard.dev/projects/github.com/RAESystem/adapters/badge",
        "bestpractices.dev/projects?as=badge&url=https%3A%2F%2Fgithub.com%2FRAESystem%2Fadapters",
    ):
        _require(readme, expected, "README.md", errors)

    services = _read_required(repo_root, "docs/maintainers/project-services.md", errors)
    for expected in (
        "Read the Docs project: `raes-adapters`",
        "PyPI distribution name: `raes-adapters`",
        "PyPI Trusted Publisher workflow: `release-please.yml`",
        "PyPI environment: `pypi`",
        "SonarCloud project key: `RAESystem_adapters`",
        "OpenSSF Scorecard URI: `github.com/RAESystem/adapters`",
        "OpenSSF Best Practices lookup: `https://github.com/RAESystem/adapters`",
    ):
        _require(services, expected, "docs/maintainers/project-services.md", errors)

    # Release Please owns versioning + CHANGELOG; PyPI publication is OIDC Trusted
    # Publishing only (ADR-003). Validate the config, manifest, and workflow
    # boundary here rather than in a second release-config validator.
    release_config = _read_required(repo_root, "release-please-config.json", errors)
    for expected in (
        '"release-type": "python"',
        '"package-name": "raes-adapters"',
    ):
        _require(release_config, expected, "release-please-config.json", errors)

    _read_required(repo_root, ".release-please-manifest.json", errors)

    release_wf = _read_required(repo_root, ".github/workflows/release-please.yml", errors)
    for expected in (
        "googleapis/release-please-action@",
        "pypa/gh-action-pypi-publish@",
        "environment: pypi",
        "id-token: write",
    ):
        _require(release_wf, expected, ".github/workflows/release-please.yml", errors)
    # No stored PyPI credential, and no silent `skip-existing` recovery that could
    # mask a partial or duplicate publication.
    for forbidden in ("PYPI_API_TOKEN", "TWINE_PASSWORD", "skip-existing: true"):
        if forbidden in release_wf:
            errors.append(
                ".github/workflows/release-please.yml: forbidden release setting "
                f"present: {forbidden}"
            )

    workflows = sorted((repo_root / ".github/workflows").glob("*.y*ml"))
    for workflow in workflows:
        errors.extend(validate_action_pins(workflow, repo_root))
        workflow_text = workflow.read_text(encoding="utf-8")
        if "actions/deploy-pages@" in workflow_text or "pages: write" in workflow_text:
            errors.append(f"{workflow.relative_to(repo_root)}: GitHub Pages publishing is retired")

    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    errors = validate_repository(repo_root)
    if errors:
        print("project services policy: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("project services policy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
