# ADR-000: Use Architecture Decision Records

## Status

superseded

Superseded by [ADR-002](adr-002-raes-authority-and-adapter-boundaries.md) on
2026-07-28 (RAES identity cutover, issue #5). This record is retained unchanged
as the historical decision: its pre-cutover wording is an accurate record of what
was decided at the time, not current guidance. Per the ADR governance in
[README.md](README.md), a superseded ADR leaves the pinned set; its content is
instead digest-pinned in
[`../identity-register.yaml`](../identity-register.yaml) so the
retired identity it records cannot drift.

## Date

2026-07-04

## Classification

Classification: FM1
Required artifacts: ADR
Waivers: No schema, fixture, profile, contract, or runtime artifact is
introduced by this decision.

## Context

The `aces-adapters` monorepo hosts independent simulator-adapter projects that
realize ACES scenarios against concrete simulator backends. Structural
decisions (monorepo layout, dependency isolation, CI matrix, adapter
conventions) need a durable, reviewable record so that cross-repo work driven
from ACES stays legible over time.

## Decision

We record significant architectural decisions as MADR-style ADRs under
`docs/decisions/adrs/`. Accepted ADRs are content-pinned in `adr-index.yaml`
and enforced by the `policy` nox session. ADRs local to this repo reference —
and never override — the governing ACES requirements, ADRs, and design records.

## Alternatives Considered

- **No ADRs (decisions in PRs/issues only).** Rejected: decisions become
  unfindable and drift; the replication program explicitly requires readable
  cross-repo decision records (ADR-069 §8).
- **Keep all decisions in the ACES repo.** Rejected: repo-local structural
  choices (CI matrix, packaging) belong with the code they govern; ACES stays
  the semantic authority, not the home for adapter build mechanics.

## Consequences

- Decisions are discoverable and citable from ACES issues and PRs.
- Every accepted ADR carries a maintenance cost (the pin gate) that keeps its
  content honest.
