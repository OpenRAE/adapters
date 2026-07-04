# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the
`aces-adapters` monorepo. ADRs capture significant architectural decisions
along with their context, rationale, and consequences.

ACES (`Brad-Edwards/aces`) remains the semantic authority for the replication
program (ADR-069 §1). ADRs here record decisions *local to this repository*
(monorepo structure, CI isolation, adapter conventions) and reference the
governing ACES requirements, ADRs, and design records rather than restating
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
| [000](adr-000-use-adrs.md) | Use Architecture Decision Records | accepted | 2026-07-04 |
| [001](adr-001-adapters-monorepo-standup.md) | Adapters Monorepo Standup and CI Isolation | accepted | 2026-07-04 |
