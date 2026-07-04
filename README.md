# aces-adapters

A monorepo of **independent** per-simulator adapter projects that realize
[ACES](https://github.com/Brad-Edwards/aces) scenarios against concrete
simulator backends, plus a shared adapter base and a backend conformance
harness.

ACES is the semantic authority for the replication program. This repository
hosts the adapter *implementations* and their build/CI mechanics; it never adds
CAGE-specific SDL, schemas, profiles, vocabularies, or policy gates (ACES
ADR-069 §1).

## Why a monorepo of isolated projects

Simulator packages carry mutually incompatible dependency constraints (e.g. old
gym/numpy pins). Each adapter under `packages/` therefore owns its **own**
`pyproject.toml` and `uv.lock` and is built/tested in an isolated environment,
driven by a **per-adapter CI matrix**, so one simulator's pins can never gate
another's (ACES ADR-069 §5). The repo root locks the shared toolchain only —
there is no global adapter lockfile and no uv workspace.

## Layout

```text
aces-adapters/
  pyproject.toml               # tooling-only root project (ruff, hooks, towncrier)
  noxfile.py                   # canonical verification graph
  packages/
    sim_adapter_base/          # shared adapter plumbing (ADR-069 §4)
    cyborg_adapter/            # CybORG backend adapter (ADR-069 §3)
      mapping/                 # pinned CAGE-2 → ACES source ledger (REP-003)
      profiles/                # conformance profile overrides
  docs/decisions/adrs/         # repo-local ADRs (pinned)
  .github/workflows/           # per-adapter CI matrix + PR-title lint
```

## Program status

This repository is stood up under **REP-002** (ACES issue #636). The packages
are buildable skeletons; adapter logic is downstream:

| Requirement | Scope |
|-------------|-------|
| REP-001 (#635) | Design: ACES ADR-069 + `cage-2-replication-design.md` |
| **REP-002 (#636)** | **This standup: monorepo, CI isolation, GC onboarding, strict Sonar** |
| REP-003 | CAGE-2 ACES SDL scenario + pinned mapping ledger |
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

Work here is issue-driven from ACES (ADR-069 §8). Adapter PRs reference the ACES
issue, `REP-001`, ADR-069, the design record, the source-ledger id, conformance
profile id, and seed suite. Cross-repo status is read from linked issues, PRs,
conformance reports, and evidence artifacts — not from comments or docs.

## License

MIT — see [LICENSE](LICENSE).
