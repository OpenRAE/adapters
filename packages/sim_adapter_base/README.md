# sim_adapter_base

Shared plumbing for ACES simulator adapters — a convenience library for
simulator drivers, **not** an authority.

Per ACES [ADR-069](https://github.com/Brad-Edwards/aces/blob/main/docs/decisions/adrs/adr-069-cage-2-replication-architecture.md)
§4, this package consumes ACES published contracts and must never define a new
semantic model, schema registry, backend protocol, diagnostic envelope,
exception hierarchy, conformance-profile table, fixture corpus, concept
catalog, or policy gate.

**Status:** skeleton (REP-002 standup). Helpers land under REP-004.

## Isolation

This adapter owns its own `pyproject.toml` and `uv.lock`. Work on it from this
directory:

```bash
uv sync
uv run pytest
```
