# raes-adapters

[![Documentation](https://readthedocs.org/projects/raes-adapters/badge/?version=latest)](https://raes-adapters.readthedocs.io/en/latest/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/RAESystem/adapters/badge)](https://scorecard.dev/viewer/?uri=github.com/RAESystem/adapters)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects?as=badge&url=https%3A%2F%2Fgithub.com%2FRAESystem%2Fadapters)](https://www.bestpractices.dev/projects?as=entry&url=https%3A%2F%2Fgithub.com%2FRAESystem%2Fadapters)

A single distribution, **`raes-adapters`**, that realizes
[RAES](https://github.com/RAESystem/rae) scenarios against concrete simulator
backends. It ships shared adapter plumbing plus one importable module per
simulator, with each simulator's dependencies exposed as an optional extra.

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
concepts — including CybORG and CAGE-2 — stay inside the module that owns them
and never define the shared semantic boundary (ADR-002).

## Install

```bash
pip install raes-adapters            # shared base plumbing
pip install raes-adapters[cyborg]    # + the CybORG backend
```

## One distribution, optional simulator extras

RAES owns the *contracts* an adapter must honor; how this repository packages,
locks, and releases its code is a local decision (RAES ADR-069 §5 as amended —
see [RAESystem/rae#949](https://github.com/RAESystem/rae/issues/949) — and
[ADR-003](docs/decisions/adrs/adr-003-single-distribution-and-trusted-publishing.md)).
`raes-adapters` is one distribution: `raes_adapters.base` is always installed,
and each simulator is an optional module (`raes_adapters.cyborg`, ...) whose
heavy, mutually-incompatible dependencies live behind an extra. A single
`uv.lock` covers the tree; a future simulator with a conflicting stack is
isolated with uv's `conflicts` extras declaration, not a separate lockfile.

## Layout

```text
raes-adapters/
  pyproject.toml               # the raes-adapters distribution (build + deps + extras)
  noxfile.py                   # canonical verification graph
  src/raes_adapters/
    base/                      # shared adapter plumbing (ADR-069 §4)
    cyborg/                    # CybORG backend module (optional `cyborg` extra; ADR-069 §3)
      mapping/                 # pinned CAGE-2 → RAES source ledger (REP-003)
      profiles/                # conformance profile overrides
  tests/                       # pytest suite for the distribution
  release-please-config.json   # Release Please: versioning + CHANGELOG from main
  .github/workflows/           # CI + PR-title lint + Release Please publish
  docs/decisions/adrs/         # repo-local ADRs (pinned)
```

## Program status

This repository is stood up under **REP-002** (RAES issue #636). The modules are
buildable skeletons; adapter logic is downstream:

| Requirement | Scope |
|-------------|-------|
| REP-001 (#635) | Design: RAES ADR-069 + `cage-2-replication-design.md` |
| **REP-002 (#636)** | **This standup: distribution, CI, GC onboarding, strict Sonar** |
| REP-003 | CAGE-2 RAES SDL scenario + pinned mapping ledger |
| REP-004 | CybORG backend + `raes_adapters.base` implementation |
| REP-005 | Replicated runs + tiered equivalence evidence |

## Development

Requires [`uv`](https://docs.astral.sh/uv/). Repo-wide gates run through nox:

```bash
# full verification graph (hygiene, policy, lint, typecheck, tests, build)
uv tool run --from 'nox[uv]==2026.4.10' nox -s verify

# just the tests (base plus all extras)
uv tool run --from 'nox[uv]==2026.4.10' nox -s tests
```

Activate the git hooks on every fresh clone (hooks are not versioned):

```bash
uv run --project . pre-commit install --install-hooks
```

## Releases

`raes-adapters` uses [Release Please](https://github.com/googleapis/release-please):
each push to `main` maintains a release PR that bumps the version and updates
`CHANGELOG.md` from Conventional Commit history. Merging it tags the release and
publishes the wheel and sdist to PyPI over OIDC Trusted Publishing (no stored
token), then opens a `main`→`dev` back-merge PR. Do not hand-edit `CHANGELOG.md`;
carry the release note in the Conventional Commit PR title.

## Cross-repo workflow

Work here is issue-driven from RAES (ADR-069 §8). Adapter PRs reference the RAES
issue, `REP-001`, ADR-069, the design record, the source-ledger id, conformance
profile id, and seed suite. Cross-repo status is read from linked issues, PRs,
conformance reports, and evidence artifacts — not from comments or docs.

## License

MIT — see [LICENSE](LICENSE).
