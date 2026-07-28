# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the
`raes-adapters` monorepo. ADRs capture significant architectural decisions
along with their context, rationale, and consequences.

RAES (`RAESystem/rae`) remains the semantic authority for the replication
program (ADR-069 §1). ADRs here record decisions *local to this repository*
(monorepo structure, CI isolation, adapter conventions) and reference the
governing RAES requirements, ADRs, and design records rather than restating
them.

## Format

We use [MADR](https://adr.github.io/madr/) (Markdown Any Decision Records).
Each ADR includes: **Status**, **Date**, **Classification**, **Context**,
**Decision**, **Alternatives Considered**, and **Consequences**. Use
[`TEMPLATE.md`](TEMPLATE.md) when drafting a new ADR.

## Principles

- An **accepted** ADR's content is **pinned** and citable. Its acceptance (or
  last-amendment) content hash is recorded in
  [`adr-index.yaml`](adr-index.yaml) and enforced by the `policy` nox session
  (`tools/check_adr_immutability.py`). A substantive change to an accepted ADR
  is legitimate only as a new **superseding** ADR, or as a recorded
  **amendment** (a `## Amendments` row plus an updated pin, in the same change).
- `proposed` ADRs may change freely; `superseded`/`deprecated` ADRs leave the
  pinned set.
- ADRs are **numbered sequentially** in landing order and never reused.
- ADRs are **versioned with code** and live in the repo.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [000](adr-000-use-adrs.md) | Use Architecture Decision Records | superseded | 2026-07-04 |
| [001](adr-001-adapters-monorepo-standup.md) | Adapters Monorepo Standup and CI Isolation | superseded | 2026-07-04 |
| [002](adr-002-raes-authority-and-adapter-boundaries.md) | RAES Authority, ADR Migration, and Adapter Boundaries | accepted | 2026-07-28 |

ADR-000 and ADR-001 were superseded by ADR-002 in the RAES cutover. They are
retained unchanged as historical records: they state accurately what was decided
at the time and are not current guidance. Per the pinning rule above they have
left the pinned index set; their content is digest-pinned in
[`../identity-register.yaml`](../identity-register.yaml) instead.
