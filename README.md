# raes-adapters

[![Documentation](https://readthedocs.org/projects/raes-adapters/badge/?version=latest)](https://raes-adapters.readthedocs.io/en/latest/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/RAESystem/adapters/badge)](https://scorecard.dev/viewer/?uri=github.com/RAESystem/adapters)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects?as=badge&url=https%3A%2F%2Fgithub.com%2FRAESystem%2Fadapters)](https://www.bestpractices.dev/projects?as=entry&url=https%3A%2F%2Fgithub.com%2FRAESystem%2Fadapters)

A monorepo of **independent** per-simulator adapter projects that realize
[RAES](https://github.com/RAESystem/rae) scenarios against concrete
simulator backends, plus a shared adapter base and a backend conformance
harness.

RAES — Reproducible Agentic Environments System — is the semantic authority.
Its scope is agentic environments generally: cyber, AI security, AI safety,
testing, research, and evaluation are examples of what an environment can model,
not the boundary of the model. Adapters here translate between a specific
simulator backend and the published RAES contracts; the shared surfaces speak in
participants, observations, actions, resources, controls, evaluation, provenance,
evidence, replay boundaries, and conformance.

This repository hosts the adapter *implementations* and their build/CI mechanics.
It consumes published RAES contracts and never adds SDL, schemas, profiles,
vocabularies, or policy gates of its own (RAES ADR-069 §1). Backend-specific
concepts — including CybORG and CAGE-2 — stay inside the adapter that owns them
and never define the shared semantic boundary (ADR-002).

## Why a monorepo of isolated projects

Simulator packages carry mutually incompatible dependency constraints (e.g. old
gym/numpy pins). Each adapter under `packages/` therefore owns its **own**
`pyproject.toml` and `uv.lock` and is built/tested in an isolated environment,
driven by a **per-adapter CI matrix**, so one simulator's pins can never gate
another's (RAES ADR-069 §5). The repo root locks the shared toolchain only —
there is no global adapter lockfile and no uv workspace.

## Layout

```text
raes-adapters/
  pyproject.toml               # tooling-only root project (ruff, hooks, towncrier)
  noxfile.py                   # canonical verification graph
  packages/
    sim_adapter_base/          # shared adapter plumbing (ADR-069 §4)
    cyborg_adapter/            # CybORG backend adapter (ADR-069 §3)
      mapping/                 # pinned CAGE-2 → RAES source ledger (REP-003)
      profiles/                # conformance profile overrides
  docs/decisions/adrs/         # repo-local ADRs (pinned)
  .github/workflows/           # per-adapter CI matrix + PR-title lint
```

## Program status

This repository is stood up under **REP-002** (RAES issue #636). The packages
are buildable skeletons; adapter logic is downstream:

| Requirement | Scope |
|-------------|-------|
| REP-001 (#635) | Design: RAES ADR-069 + `cage-2-replication-design.md` |
| **REP-002 (#636)** | **This standup: monorepo, CI isolation, GC onboarding, strict Sonar** |
| REP-003 | CAGE-2 RAES SDL scenario + pinned mapping ledger |
| REP-004 | CybORG backend + `sim_adapter_base` implementation |
| REP-005 | Replicated runs + tiered equivalence evidence |

## Development

Requires [`uv`](https://docs.astral.sh/uv/). Repo-wide gates run through nox:

```bash
# full verification graph (hygiene, policy, lint, typecheck, per-adapter tests)
uv tool run --from 'nox[uv]==2026.4.10' nox -s verify

# one adapter in isolation
uv tool run --from 'nox[uv]==2026.4.10' nox -s ci-adapter -- cyborg_adapter
```

Activate the git hooks on every fresh clone (hooks are not versioned):

```bash
uv run --project . pre-commit install --install-hooks
```

## Cross-repo workflow

Work here is issue-driven from RAES (ADR-069 §8). Adapter PRs reference the RAES
issue, `REP-001`, ADR-069, the design record, the source-ledger id, conformance
profile id, and seed suite. Cross-repo status is read from linked issues, PRs,
conformance reports, and evidence artifacts — not from comments or docs.

## License

MIT — see [LICENSE](LICENSE).
