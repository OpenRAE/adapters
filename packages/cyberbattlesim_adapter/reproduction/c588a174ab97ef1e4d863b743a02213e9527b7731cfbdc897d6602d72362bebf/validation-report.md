# CyberBattleSim baseline reproduction validation

Frozen revision: `c588a174ab97ef1e4d863b743a02213e9527b7731cfbdc897d6602d72362bebf`

The bundle contains 20 preallocated terminal attempts: ten source-native episodes and ten RAES-mediated episodes. Aggregate and tier projections are derived only from retained portable evidence.

Offline verification command:

```bash
python -m raes_adapters.cyberbattlesim.reproduction verify --bundle .
```

Verification checks the frozen declaration/oracle, RAES study model, terminal schedule, timestamped bench notes, per-file digests, evidence references, aggregate recomputation, six tier citations, and the bounded leakage denylist. It needs no network or native simulator import.

This artifact does not claim deterministic replay, exact state or observation equivalence, cross-simulator equality, agent ranking, benchmark comparability, outcome equivalence, or general scientific reproducibility.
