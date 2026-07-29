# CyberBattleSim → RAES loss disclosures

**Authored under RAESystem/adapters#26.** Each entry records a pinned
CyberBattleSim source fact that the portable RAES evidence set cannot carry
exactly, the reason, and the ADR-069 equivalence tier it weakens (RAES ADR-069
§2, §7). A disclosed gap weakens or fails that tier explicitly; it is never
filled by raw simulator logs, native observations, fixture-local assertions, or
prose-only evidence.

The equivalence tiers named below are issue-local validation labels for the
ADR-069 tiered-equivalence ladder — the same status as the ledger's disposition
and category labels — not a new RAES vocabulary. Every `loss-disclosed` row in
`source-ledger.jsonl` references one of these losses and repeats its tier; the
deterministic validator fails closed when a loss is unreferenced, a lossy row
names no loss, or a loss declares no tier.

## loss-no-source-artifact

**Equivalence tier:** reproducibility

The official Microsoft source declares `cyberbattlesim==0.1.0` but publishes
neither a public index distribution nor a release artifact, and PyPI does not
accept direct-URL dependencies. The exact selected commit therefore cannot be
reinstalled through a published, hash-locked route, so no `cyberbattlesim` extra
is advertised. This defeats the base reproducibility precondition on which every
higher equivalence tier depends: an apparatus that cannot be reconstructed from a
published artifact cannot ground a portable replication claim. The gap is a
standing admissibility blocker for RAESystem/research#12, not a packaging
convenience to be papered over with a floating Git reference or an empty extra.

## loss-unbound-random-streams

**Equivalence tier:** deterministic-replay

The selected public case has four randomness sources — the Gym environment
generator, the Gym action space, Python `random`, and global NumPy. The public
`epsilon_greedy_search` evaluator calls `reset()` without forwarding a seed and
the public notebook binds none of the other three. A single top-level seed is
therefore not evidence that the run is controlled, and the published stochastic
controls remain **descriptive only** (no `RandomStreamControlBindingModel`). No
run under this protocol is a deterministic replay until the upstream seam is
fixed or an explicit, identified compatibility patch is qualified.

## loss-abstracted-topology

**Equivalence tier:** outcome-equivalence

The selected source case is `CyberBattleChain-v0` at generation size 10, produced
by `new_environment(10)`. RAES SDL is declarative and has no construct that
structurally materializes a generator's node graph, so the authored scenario
encodes the chain *pattern and host roles* as a bounded representative topology
(an entry host, alternating Linux/Windows relay hosts, and a terminal
high-value host) rather than a node-for-node expansion of the size-10 case. The
selected size is recorded as the `chain_size` SDL variable and in the companion
run plan, but the exact per-host structure of the generated graph is not
reproduced. This weakens outcome comparability between a run on this
representative topology and a run on the full generated chain, so no outcome
equivalence is claimed from topology alone.

## loss-benchmark-defects

**Equivalence tier:** outcome-equivalence

Material upstream benchmark and evaluation defects remain open
(microsoft/CyberBattleSim #87, #115, #117, #156), the attacker reward-goal
predicate reads prior-step rewards (an off-by-one limitation), and the evaluator
iteration cutoff is not Gym truncation (Gym always returns `truncated=false`).
These weaken outcome comparability: cumulative reward, terminal cause, and the
historical benchmark snapshot cannot be treated as equivalent study outcomes of
the selected commit. The portable evidence keeps reward, terminal result, and
derived measures distinct and never converts the ownership goal into a silent
reward threshold.
