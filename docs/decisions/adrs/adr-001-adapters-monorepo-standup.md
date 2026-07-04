# ADR-001: Adapters Monorepo Standup and CI Isolation

## Status

accepted

## Date

2026-07-04

## Classification

Classification: FM2
Required artifacts: ADR, changelog fragment
Waivers: No adapter logic, simulator dependency, mapping ledger content, schema,
fixture, profile, or conformance harness implementation is introduced by this
decision. Those are downstream work (REP-003 authors the CAGE-2 scenario and
mapping ledger; REP-004 implements `sim_adapter_base` and the CybORG backend;
REP-005 drives replicated runs).

## Context

ACES requirement REP-002 (issue #636) mandates standing up
`Brad-Edwards/aces-adapters` as the governed home for simulator adapters in the
CAGE-2 replication program. The governing design is ACES ADR-069 (CAGE-2
Replication Architecture) and `docs/decisions/cage-2-replication-design.md`,
accepted under REP-001 (issue #635). REP-002 is scoped to the *standup*:
repository structure, dependency isolation, Ground Control onboarding, and a
strict SonarCloud gate — not adapter implementation.

Simulator packages carry mutually incompatible dependency constraints (for
example old gym/numpy pins). A single resolved dependency graph across all
adapters would couple unrelated projects and make the monorepo a hidden
dependency-policy authority (ADR-069 §5, "Use one global adapter lockfile" —
rejected).

## Decision

1. **Independent per-adapter projects.** Each adapter lives under `packages/`
   with its own `pyproject.toml` and `uv.lock`, synced and tested in an
   isolated environment. Repo-root `pyproject.toml` + `uv.lock` lock the shared
   *toolchain only* (ruff, hooks, towncrier); there is no uv workspace and no
   shared adapter lock.

2. **Seeded packages.** `packages/sim_adapter_base` (shared adapter plumbing,
   consumes ACES contracts; never a semantic/protocol authority — ADR-069 §4)
   and `packages/cyborg_adapter` (`src/aces_adapter_cyborg`, with `mapping/`
   and `profiles/conformance-overrides/`) are created as buildable skeletons so
   the CI matrix and conventions are exercised from day one. Their adapter
   logic is deferred to REP-004; the CAGE-2 mapping ledger content is deferred
   to REP-003.

3. **Per-adapter CI matrix.** `.github/workflows/ci.yml` fans out by adapter
   path, lockfile, Python version, optional simulator extras, conformance
   profile id, seed suite, and source-ledger id (ADR-069 §5) so one adapter's
   pins cannot gate another's job.

4. **Ground Control onboarding.** `.ground-control.yaml`, the ADR directory
   with a pin gate, a towncrier changelog, a `nox` verify graph, pre-commit
   hooks, requirement-governance / repo-policy / PR-title gates, and main+dev
   branch protection, so the repo is drivable by the `/implement` workflow.

5. **Strict SonarCloud.** An `aces-adapters-strict` quality gate mirroring
   aces `aces-strict` (fails on any new issue; `sonar.qualitygate.wait=true`;
   new-code coverage / duplication / rating / security-hotspot conditions),
   using `Brad-Edwards/aces` as the reference configuration.

6. **Conformance composes ACES gates.** Backend conformance for adapters will
   invoke/wrap the published ACES conformance runner, profiles, and fixtures
   (ADR-069 §6); this repo does not define a second profile table, fixture
   corpus, schema registry, or manifest renderer.

## Alternatives Considered

- **One global lockfile / uv workspace.** Rejected (ADR-069 §5): couples
  incompatible simulator stacks and hides dependency policy.
- **Put adapters in the ACES repo.** Rejected: ACES core must build from
  published contracts without importing concrete simulator packages
  (ADR-069 "Treat CybORG as a direct ACES runtime dependency" — rejected).
- **Defer creating package skeletons until REP-004.** Rejected: standing up the
  CI matrix and conventions against real (if empty) packages catches structural
  problems now instead of at first implementation.
- **Lenient/default SonarCloud gate.** Rejected: REP-002 explicitly requires a
  strict gate mirroring `aces-strict`.

## Consequences

### Positive

- Incompatible adapter dependency stacks are isolated by construction.
- The replication program gets a governed, `/implement`-drivable home with the
  same quality bar as ACES.
- Downstream REP-003/004/005 work drops into an established structure.

### Negative / Costs

- More CI ceremony (a matrix) than a single shared package.
- Each adapter re-declares and re-locks its toolchain-adjacent dev deps.

### Risks

- Skeleton packages could rot if REP-004 lags. Mitigation: the CI matrix and
  coverage gate run against them continuously, so they stay green and current.
