# CyberBattleSim baseline reproduction validation

Frozen revision: `f09ec5759021cf1d5de9b260e0299934bf6f6cc4161b822e8f5f0b76bdb96b53`

The bundle contains 20 preallocated terminal attempts: ten source-native episodes and ten RAES-mediated episodes. Aggregate and tier projections are derived only from retained portable evidence.

Offline verification command:

```bash
python -m raes_adapters.cyberbattlesim.reproduction verify --bundle .
```

Verification checks the frozen declaration/oracle, RAES study model, terminal schedule, timestamped bench notes, per-file digests, evidence references, aggregate recomputation, six tier citations, and the bounded leakage denylist. It needs no network or native simulator import.

This artifact does not claim deterministic replay, exact state or observation equivalence, cross-simulator equality, agent ranking, benchmark comparability, outcome equivalence, or general scientific reproducibility.
