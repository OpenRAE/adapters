# cyborg_adapter (`raes_adapter_cyborg`)

CybORG simulator backend adapter for RAES — a conformant simulator backend
behind the RAES backend protocol surface (Provisioner, Orchestrator, Evaluator,
ParticipantRuntime), per RAES
[ADR-069](https://github.com/RAESystem/rae/blob/main/docs/decisions/adrs/adr-069-cage-2-replication-architecture.md)
§3.

**Status:** skeleton (REP-002 standup). Downstream:

- **REP-003** authors the CAGE-2 RAES SDL scenario and the pinned mapping ledger
  under [`mapping/`](mapping/).
- **REP-004** implements the four backend protocols and `sim_adapter_base`.
- **REP-005** drives replicated runs and records tiered equivalence evidence.

## Layout

| Path | Purpose |
|------|---------|
| `src/raes_adapter_cyborg/` | Adapter implementation (skeleton) |
| `tests/` | Adapter tests |
| `mapping/` | Pinned CAGE-2 → RAES source ledger + loss disclosures (REP-003) |
| `profiles/conformance-overrides/` | Adapter-specific conformance profile overrides |

## Isolation

This adapter owns its own `pyproject.toml` and `uv.lock`:

```bash
uv sync
uv run pytest
```
