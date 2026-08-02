# NASim → RAES loss disclosures

**Authored under RAESystem/adapters#33.** Each entry records a pinned NASim
source fact that the portable RAES evidence set cannot carry exactly, the
reason, and the ADR-069 equivalence tier it weakens (RAES ADR-069 §2, §7). A
disclosed gap weakens or fails that tier explicitly; it is never filled by raw
simulator logs, native observations, fixture-local assertions, or prose-only
evidence.

The equivalence tiers named below are issue-local validation labels for the
ADR-069 tiered-equivalence ladder — the same status as the ledger's disposition
and category labels — not a new RAES vocabulary. Every `loss-disclosed` row in
`source-ledger.jsonl` references one of these losses and repeats its tier; the
deterministic validator fails closed when a loss is unreferenced, a lossy row
names no loss, or a loss declares no tier.

The selected `tiny` case is a static benchmark with a fixed three-host topology,
so the topology is represented node-for-node and there is **no** abstracted
topology loss; termination maps cleanly because NASim computes goal completion
and the step-limit truncation independently.

## loss-unbound-action-rng

**Equivalence tier:** deterministic-replay

Action success in NASim is drawn from the **global** NumPy RNG
(`np.random.rand() > action.prob` at `nasim/envs/network.py:87`), not the
gym-seeded `self.np_random`. For a static benchmark `make_benchmark(seed=…)` is
ignored and `reset(seed=…)` seeds only the unused gym stream, so a single
top-level seed passed through the environment constructor or `reset` is not
evidence that the run is controlled. The published stochastic controls therefore
remain **descriptive only** (no `RandomStreamControlBindingModel`). No run under
this protocol is a deterministic replay unless a runner explicitly binds
`numpy.random.seed(20260802)`; a seed value alone is not a replay claim.

## loss-apparatus-reconstruction

**Equivalence tier:** reproducibility

Two upstream facts constrain reconstruction of the selected apparatus. First,
NASim's supplied agents assert a Python `int` action index
(`FlatActionSpace.get_action`, `nasim/envs/action.py:698`), so from
gymnasium `0.27` onward — where `Discrete.n`/`Discrete.sample()` return
`numpy.int64` — the bruteforce baseline raises `AssertionError`; the qualified
runtime therefore pins `gymnasium==0.26.3`. Second, importing NASim requires the
Tk system libraries because `nasim/envs/render.py` imports `tkinter` and selects
the `TkAgg` matplotlib backend at import time, so a headless environment needs
`python3-tk` present even for programmatic use. Both are recorded upstream
defects, not silent patches: NASim source is used unmodified and the
limitations bound apparatus reconstruction. They do not make the
maintainer-selected simulator unavailable to the adapter.
