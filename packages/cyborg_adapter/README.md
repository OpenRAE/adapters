# cyborg_adapter (`aces_adapter_cyborg`)

CybORG simulator backend adapter for ACES — a conformant simulator backend
behind the ACES backend protocol surface (Provisioner, Orchestrator, Evaluator,
ParticipantRuntime), per ACES
[ADR-069](https://github.com/Brad-Edwards/aces/blob/main/docs/decisions/adrs/adr-069-cage-2-replication-architecture.md)
§3.

**Status:** skeleton (REP-002 standup). Downstream:

- **REP-003** authors the CAGE-2 ACES SDL scenario and the pinned mapping ledger
  under [`mapping/`](mapping/).
- **REP-004** implements the four backend protocols and `sim_adapter_base`.
- **REP-005** drives replicated runs and records tiered equivalence evidence.

## Layout

| Path | Purpose |
|------|---------|
| `src/aces_adapter_cyborg/` | Adapter implementation (skeleton) |
| `tests/` | Adapter tests |
| `mapping/` | Pinned CAGE-2 → ACES source ledger + loss disclosures (REP-003) |
| `profiles/conformance-overrides/` | Adapter-specific conformance profile overrides |

## Isolation

This adapter owns its own `pyproject.toml` and `uv.lock`:

```bash
uv sync
uv run pytest
```
