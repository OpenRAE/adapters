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

**After — the parallel graph.** `SonarCloud`'s ~52 s quality-gate wait now
begins after the `tests` job alone (~10–15 s) instead of after the full ~22 s
graph, and the seven verification jobs report independently:

- Final required-check completion: **≈ 68 s** *(projected from the measured
  per-stage timings above).*
- First actionable feedback: **≈ 5–8 s** — **Fast checks** reports hygiene and
  lint without waiting on any other stage.

The larger win is structural and grows with the repository: as simulators are
added, typecheck/test/build stages that used to run one-after-another now run
side by side, and a failure in any one stage no longer hides the others.
