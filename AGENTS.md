# Agent guide — aces-adapters

This repo is part of the ACES CAGE-2 replication program. ACES
(`Brad-Edwards/aces`) is the semantic authority; work here is issue-driven from
ACES (ACES ADR-069 §8).

## Hard rules

- **ACES is the authority.** Do not add CAGE-specific SDL, schemas, profiles,
  vocabularies, manifest blocks, exceptions, stores, or policy gates to make a
  mapping convenient (ADR-069 §1). Adapters consume ACES *published contracts*.
- **`sim_adapter_base` is plumbing, not authority.** It must not define a
  semantic model, schema registry, backend protocol, diagnostic envelope,
  exception hierarchy, conformance-profile table, fixture corpus, concept
  catalog, or policy gate (ADR-069 §4).
- **Per-adapter isolation.** Each adapter owns its own `pyproject.toml` +
  `uv.lock`. Never introduce a global adapter lockfile or uv workspace
  (ADR-069 §5).
- **No native simulator leakage.** Native CybORG state, gym/PettingZoo tuples,
  reward vectors, action ids, object reprs, raw logs, hidden truth, argv/env
  dumps, tokens, and full tracebacks must not appear in portable ACES artifacts
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

- ACES ADR-069 — CAGE-2 Replication Architecture (authority).
- ACES `docs/decisions/cage-2-replication-design.md` — implementation checklist.
- Repo-local ADRs under `docs/decisions/adrs/`.
