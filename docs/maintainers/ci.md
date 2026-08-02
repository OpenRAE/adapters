# Continuous integration

`raes-adapters` is one distribution verified by one graph
(`noxfile.py`). CI runs that graph's stages as **independent, concurrent
jobs** rather than one serial job, so a small change gets actionable
feedback in seconds and static analysis starts as soon as coverage exists —
without weakening the merge gate. This page explains the fast-feedback path,
the full gate, who owns each job, and how to reproduce any failure locally.

## The fast-feedback path

Every stage of the verification graph is its own job in
`.github/workflows/ci.yml`, and the jobs run at the same time:

| Job | `nox` session | What it checks |
| --- | --- | --- |
| **Fast checks (hygiene + lint)** | `hygiene`, `lint` | file hygiene (whitespace, EOL, YAML/JSON), `ruff format --check`, `ruff check` |
| **Policy** | `policy` | requirement governance, repo policy, ADR-immutability pins, project services, identity |
| **Tool tests** | `tool-tests` | stdlib unit tests for repository tooling under `tools/` |
| **Typecheck** | `typecheck` | `mypy` over `src`, base install plus each extra alone |
| **Tests** | `tests` | `pytest` + coverage, base plus each extra; uploads `coverage.xml` |
| **Distributions** | `distributions` | build wheel/sdist, clean-install, prove installed identity |
| **Docs** | `docs` | strict MkDocs build |

Because the jobs are independent, a formatting or lint mistake surfaces from
**Fast checks** in a few seconds without waiting on the typecheck, test, build,
or docs stages, and each stage reports its own result even when another stage
fails. Within **Fast checks**, lint still runs when hygiene fails (`if:
!cancelled()`) so one fast-lane failure never hides the other.

`SonarCloud` depends on `tests` **only** (`needs: [tests]`) because static
analysis needs source plus `coverage.xml` and nothing else — it no longer waits
for the whole graph (typecheck, build, docs) to finish before it starts.

## The full gate

Shortening the critical path does not remove any verification. Branch
protection on `main` and `dev` requires exactly three checks — `CodeQL`,
`Lint PR title`, and **`PR Gate`** — and `PR Gate` is the aggregator that
stands in for the entire verification graph.

`PR Gate` runs after every verification job plus `SonarCloud` (`if: always()`),
reads their results, and fails unless:

- **every** verification job succeeded (all `needs` except `sonar`), and
- `SonarCloud` **succeeded** on a same-repository PR, or was **skipped** on a
  fork PR (forks never receive `SONAR_TOKEN`).

The `needs:` list on `PR Gate` is the gate contract: a verification job that is
not listed there is not enforced. **Adding a verification job means adding it to
that list.** Keeping one required check (`PR Gate`) means the parallel jobs can
be added, split, or renamed without reconfiguring branch protection, while the
protected branches still block on the complete graph.

## Job ownership and sharding

Each job maps 1:1 to a `nox` session, so ownership is unambiguous: the session
in `noxfile.py` is the single source of truth for what the job runs, and the
same session name is the local command (below).

The **test suite is a single shard.** `raes-adapters` is one package with
optional per-simulator extras; the `tests` session already runs the base
install and each extra in one job and aggregates their coverage with `coverage
combine`, so every test executes exactly once per run. Splitting into multiple
CI shards would add coordination (deterministic test partitioning, cross-shard
coverage merging) for a suite that finishes in seconds — the cost outweighs the
benefit at this size. If a future simulator's suite grows enough to justify it,
shard the `tests` session deterministically, keep `coverage combine` merging the
shard outputs, and record each shard's owner in the table above.

A **change-based early-feedback lane** (running only the checks a diff touches)
was evaluated and **not** adopted. The parallel jobs already deliver early
per-stage feedback, and the full graph is fast; a separate change-scoped lane
would add a second definition of "what to run" that can drift from the required
gate, for negligible time saved on a suite this small. The required merge gate
stays the complete graph.

## CybORG conformance tiers

The normal tests and distributions jobs run the dependency-free PR tier at the
fixed ordered seed `(3,)`. The distributions session also builds the one wheel,
installs its `cyborg` extra into a clean isolated environment, loads the
installed qualification and ledger resources, runs the published RAES report
plus adapter-local probes, and persists the report through RAES's atomic,
redaction-gated writer.

The existing CI workflow runs the broader `(3, 153)` tier on its weekly
schedule or when `workflow_dispatch` selects `full`; the resulting canonical
reports are uploaded as the `cyborg-conformance` artifact. Both tiers are
hermetic and explicitly retain `native_conformance=false`. Native source
readiness remains the separate `tools/verify_cyborg_qualification.py` evidence
already exercised by the CybORG test environment; a hermetic injected driver
is never relabeled as native.

```bash
uv run --frozen python -m raes_adapters.cyborg.conformance \
  --suite pr --output-dir artifacts/cyborg-conformance
uv run --frozen python -m raes_adapters.cyborg.conformance \
  --suite full --output-dir artifacts/cyborg-conformance
```

## Reproduce any failure locally

Every CI job runs one `nox` session. Reproduce a red job by running that
session locally (needs [`uv`](https://docs.astral.sh/uv/), Python 3.12+):

```bash
# The whole graph, exactly as the sum of the CI jobs:
uv tool run --from 'nox[uv]==2026.4.10' nox -s verify

# A single failing job, by its session name:
uv tool run --from 'nox[uv]==2026.4.10' nox -s hygiene       # Fast checks (hygiene)
uv tool run --from 'nox[uv]==2026.4.10' nox -s lint          # Fast checks (lint)
uv tool run --from 'nox[uv]==2026.4.10' nox -s tool-tests    # Tool tests
uv tool run --from 'nox[uv]==2026.4.10' nox -s typecheck     # Typecheck
uv tool run --from 'nox[uv]==2026.4.10' nox -s tests         # Tests (+ coverage.xml)
uv tool run --from 'nox[uv]==2026.4.10' nox -s distributions # Distributions
uv tool run --from 'nox[uv]==2026.4.10' nox -s docs          # Docs

# The Policy job resolves a requirement UID from the branch; reproduce it with:
uv tool run --from 'nox[uv]==2026.4.10' nox -s policy -- --skip-requirement
# ...or, on a requirement branch, --requirement-uid REP-00X
```

`make verify`, `make precommit`, and `make prepush` wrap the same sessions for
the git hooks.

## Before / after timings

Measured from GitHub Actions job timings (`gh api .../actions/runs/<id>/jobs`)
on same-repository runs. *Final required-check completion* is the wall-clock
from the first verification job starting to `PR Gate` finishing; *first
actionable feedback* is the earliest verification job to report a result.

**Before — one serial `verify` job.** The whole graph ran in a single job
(~21–22 s), then `SonarCloud` (~51–53 s, dominated by the `sonar.qualitygate.wait`)
started only after that job finished, then `PR Gate` (~4 s):

- Final required-check completion: **≈ 82–85 s** (median ≈ 83 s over the
  available same-repository runs of this design).
- First actionable feedback: only after a stage's turn inside the one serial
  job — a lint error could wait behind hygiene and policy, and an earlier-stage
  failure aborted the job before later stages ran at all.

> The single-`verify` design is recent (it arrived with the single-distribution
> cutover), so the sample is small; the values above are the observed spread
> rather than a large-sample percentile. Percentiles accrue in the Actions run
> history as more runs land on this workflow.

**After — the parallel graph.** Observed on this change's first parallel run
(Actions run `30407385220`): the seven verification jobs run concurrently and
all report by **+16 s** (Typecheck +10 s; Fast checks, Policy, Tool tests +15 s;
Tests, Docs +16 s). `SonarCloud` starts at **+18 s** — right after `tests`,
not after the whole graph — and its ~46 s quality-gate wait ends at +64 s;
`PR Gate` closes the run at **+74 s**.

- Final required-check completion: **74 s**, down from ≈ 82–85 s. SonarCloud's
  quality-gate wait is the tall pole in *both* designs (it needs coverage and
  cannot be parallelized away), so the remaining time is analysis the merge
  gate requires rather than avoidable serialization.
- First actionable feedback: **≈ 10–16 s** — every stage reports on its own,
  and a failure in one stage no longer hides the others. Under the old serial
  job, stages ran one after another in a single ~22 s job and an early-stage
  failure aborted the rest before they ran.

This first run also populated the `setup-uv` cache, so steady-state runs start
warm. The larger win is structural and grows with the repository: as simulators
are added, the typecheck/test/build stages that used to run one-after-another
now run side by side, and no single stage's failure hides the others.
