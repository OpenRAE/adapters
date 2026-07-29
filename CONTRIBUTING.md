# Contributing to raes-adapters

This repository hosts simulator adapters for RAES (Reproducible Agentic
Environments System) and is driven from RAES issues and requirements (RAES
ADR-069 §8). CAGE-2 replication is one backend served by the CybORG adapter
rather than the scope of the repository. Contributions land through the Ground
Control `/implement` workflow.

## Branching

- `main` — production. PRs only (from `dev`). No direct pushes, no force-push.
- `dev` — integration. PRs only; feature branches target `dev`; `dev` PRs
  target `main`.
- Feature branches embed the governing requirement UID, e.g.
  `12-REP-004-cyborg-provisioner` — CI reads the UID from the branch via the
  `[A-Z]{3}-[0-9]{3}` pattern.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python 3.12+).
- Activate git hooks on every fresh clone (they are not versioned):
  ```bash
  uv run --project . pre-commit install --install-hooks
  ```

## Verifying locally

```bash
uv tool run --from 'nox[uv]==2026.4.10' nox -s verify
```

The graph runs, in order: `hygiene` (file checks), `policy` (requirement
governance, repo policy, ADR pins), `lint` (ruff), `typecheck` (mypy),
`tests` (pytest + coverage, base plus all extras), and `distributions` (build
the wheel/sdist and prove it clean-installs).

CI runs those stages as **independent, concurrent jobs** rather than one serial
job, and each job maps 1:1 to a `nox` session, so you can reproduce any red CI
job locally by running that one session (e.g. `nox -s lint`). See
[Continuous integration](docs/maintainers/ci.md) for the fast-feedback path,
the full merge gate, and per-job reproduction commands.

## Adding a simulator backend

1. Add a module under `src/raes_adapters/<simulator>/` (import
   `raes_adapters.<simulator>`), guarding its heavy imports so a bare install
   still imports cleanly.
2. Declare its dependencies as an optional extra in `pyproject.toml`
   (`[project.optional-dependencies]`). If its stack is mutually incompatible
   with another simulator's, add a `[tool.uv] conflicts` entry so neither gates
   the other in the single lock — do **not** add a second lockfile or a uv
   workspace.
3. Add tests under `tests/`. `src` and `tests` are already the SonarCloud source
   and test roots, so no `sonar-project.properties` change is needed.

## Changes and changelog

Release Please owns `CHANGELOG.md` and the version, derived from Conventional
Commit history on `main`. Do **not** hand-edit `CHANGELOG.md` and do **not** add
`changelog.d/` fragments — carry the release note in the Conventional Commit PR
title (`<type>(<scope>)?: <lowercase subject>`), which CI enforces.

## Decisions

Repo-local architectural decisions are recorded as ADRs under
`docs/decisions/adrs/` and pinned in `adr-index.yaml`. Amending an accepted ADR
requires a `## Amendments` row and a regenerated pin
(`uv run --project . python tools/check_adr_immutability.py --update`).

## Attribution

Do not add agent/tool attribution to commits, PRs, issues, code, or docs.
