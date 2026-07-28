# Agent guide — raes-adapters

This repo hosts simulator adapters for RAES (Reproducible Agentic Environments
System). RAES (`RAESystem/rae`) is the semantic authority and its scope is
agentic environments generally; CAGE-2 replication is the first backend the
CybORG adapter serves, not the boundary of the repository. Work here is
issue-driven from RAES (RAES ADR-069 §8).

## Hard rules

- **RAES is the authority.** Do not add backend-specific SDL, schemas, profiles,
  vocabularies, manifest blocks, exceptions, stores, or policy gates to make a
  mapping convenient (ADR-069 §1). Adapters consume RAES *published contracts*.
- **Backend concepts stay in their adapter.** CybORG and CAGE-2 material is
  scoped source/backend evidence inside `cyborg_adapter`; it must never define
  the shared semantic boundary (ADR-002).
- **`sim_adapter_base` is plumbing, not authority.** It must not define a
  semantic model, schema registry, backend protocol, diagnostic envelope,
  exception hierarchy, conformance-profile table, fixture corpus, concept
  catalog, or policy gate (ADR-069 §4).
- **Per-adapter isolation.** Each adapter owns its own `pyproject.toml` +
  `uv.lock`. Never introduce a global adapter lockfile or uv workspace
  (ADR-069 §5).
- **No native simulator leakage.** Native CybORG state, gym/PettingZoo tuples,
  reward vectors, action ids, object reprs, raw logs, hidden truth, argv/env
  dumps, tokens, and full tracebacks must not appear in portable RAES artifacts
  (ADR-069 §3, risks).
- **No agent attribution** in commits, PRs, issues, code, or docs.

## Before declaring completion

Run the canonical graph and make it green:

```bash
uv tool run --from 'nox[uv]==2026.4.10' nox -s verify
```

Set `ACES_REQUIREMENT_UID` (or use a UID-bearing branch) so requirement
governance passes; use `--skip-requirement` only for genuine requirement-free
maintenance.

## Governing documents

- RAES ADR-069 — CAGE-2 Replication Architecture (authority).
- RAES `docs/decisions/cage-2-replication-design.md` — implementation checklist.
- Repo-local ADRs under `docs/decisions/adrs/`.
