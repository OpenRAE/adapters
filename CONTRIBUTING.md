# Contributing to aces-adapters

This repository is part of the ACES CAGE-2 replication program and is driven
from ACES issues and requirements (ACES ADR-069 §8). Contributions land through
the Ground Control `/implement` workflow.

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
governance, repo policy, ADR pins), `lint` (ruff), `typecheck` (mypy per
adapter), and `tests` (pytest + coverage per adapter, each in its isolated
environment).

## Adding an adapter

1. Create `packages/<adapter>/` with its own `pyproject.toml`, `uv.lock`,
   `src/`, and `tests/` (copy an existing adapter as a template).
2. Add a matrix row in `.github/workflows/ci.yml` (path, Python version, extras,
   conformance profile id, seed suite, source-ledger id).
3. Add its `src`/`tests` dirs and `coverage.xml` path to
   `sonar-project.properties`.
4. Keep adapter dependencies inside that package — never introduce a shared
   adapter lockfile (ACES ADR-069 §5).

## Changes and changelog

Every user-visible change adds a towncrier fragment under `changelog.d/`
(see [`changelog.d/README.md`](changelog.d/README.md)). Do not edit
`CHANGELOG.md` directly.

## Decisions

Repo-local architectural decisions are recorded as ADRs under
`docs/decisions/adrs/` and pinned in `adr-index.yaml`. Amending an accepted ADR
requires a `## Amendments` row and a regenerated pin
(`uv run --project . python tools/check_adr_immutability.py --update`).

## Attribution

Do not add agent/tool attribution to commits, PRs, issues, code, or docs.
