# PrimAITE → RAES loss disclosures

**Authored under RAESystem/adapters#40.** Each entry records a pinned PrimAITE
source fact that the portable RAES evidence set cannot carry exactly, the
reason, and the ADR-069 equivalence tier it weakens (RAES ADR-069 §2, §7). A
disclosed gap weakens or fails that tier explicitly; it is never backfilled by
raw simulator logs, native observations, fixture-local assertions, or prose-only
evidence.

The equivalence tiers named below are issue-local validation labels for the
ADR-069 tiered-equivalence ladder — the same status as the ledger's disposition
and category labels — not a new RAES vocabulary. Every `loss-disclosed` row in
`source-ledger.jsonl` references one of these losses and repeats its tier; the
deterministic validator fails closed when a loss is unreferenced, a lossy row
names no loss, or a loss declares no tier.

## loss-no-source-artifact

**Equivalence tier:** reproducibility

DSTL publishes the PrimAITE `v4.0.0` source but neither a public index
distribution nor a release wheel; the README documents a wheel-from-GitHub
install only, and PyPI does not accept direct-URL dependencies. The exact
selected commit therefore cannot be reinstalled through a published, hash-locked
dependency route, so the `primaite` adapter extra is dependency-light and users
install the pinned source separately. This weakens apparatus reconstruction and
every higher equivalence tier. It does not make the maintainer-selected
simulator unavailable to the adapter, and the limitation must not be hidden with
a floating Git reference.

## loss-unbound-random-streams

**Equivalence tier:** deterministic-replay

The selected case has several randomness sources — the Gymnasium reset seam, the
scripted RED start/frequency/variance timing, the global NumPy generator, and
(only with the rl stack) `torch`. `set_random_seed` dereferences
`sys.modules["torch"]` unconditionally, so the light route's public
`reset(seed=<int>)` seam raises `KeyError('torch')`; each GREEN
`ProbabilisticAgent` seeds its own generator from the uncontrolled global NumPy
RNG; and the scenario sets no `game.seed`. A single top-level seed is therefore
not evidence that the run is controlled, and the published stochastic controls
remain **descriptive only** (no `RandomStreamControlBindingModel`). No run under
this protocol is a deterministic replay until the torch seam is fixed or an
explicit, identified compatibility patch is qualified.

## loss-abstracted-participant-interface

**Equivalence tier:** outcome-equivalence

The BLUE seat exposes a native `Discrete(78)` action space and a flattened
`Box(1652)` observation. RAES SDL is declarative: it carries portable action
contracts and observation boundaries, not a native action index or a materialized
observation vector. The authored scenario therefore projects the participant
interface to portable action contracts (service control, data-integrity
remediation, node lifecycle, network access control, and interface control) and
observation boundaries, rather than reproducing the exact native action indices,
option dictionaries, action mask, and observation cells. This weakens per-step
behavioral comparability between a run driven through the portable interface and
one driven through the native `Discrete(78)`/`Box(1652)` interface, so no outcome
equivalence is claimed from the participant interface alone.

## loss-abstracted-network-controls

**Equivalence tier:** outcome-equivalence

Several source network controls reach RAES only as an abstract surface, not as
their concrete facts. The subnet addressing plan reaches the SDL infrastructure
`cidr`/`gateway`, but the per-host IP assignments and the `arcd.com` DNS domain
mapping are not materialized; the perimeter router's baseline permit ACL
(POSTGRES, DNS, FTP, HTTP, ARP, ICMP) and the blue-editable per-IP rules reach
only the abstract network-access-control action contract, not their concrete
rule set; and the NMNE capture keywords and high/medium/low thresholds reach only
the defender observation boundary's monitoring projection basis, with raw event
counts source-private. Each concrete remainder is recorded as its own
`loss-disclosed` control row rather than hidden in a mapped row's prose. This
weakens outcome comparability for addressing, firewall/routing, and
traffic-detection behavior between a run on the portable model and one on the
native configuration, so no outcome equivalence is claimed from these controls.

## loss-fixed-horizon-only-termination

**Equivalence tier:** outcome-equivalence

`PrimaiteGymEnv.step()` sets `terminated=False` unconditionally, and the episode
ends only when `PrimaiteGame.calculate_truncated()` fires at
`step_counter >= max_episode_length` (128). There is no source-native
success/failure terminal condition: goal satisfaction, a reward threshold, an
evaluator cutoff, and the fixed horizon are distinct, and only fixed-horizon
truncation is present. The portable evidence keeps the scalar reward, the
terminal cause, and any derived measure distinct and never converts the data-
corruption goal into a silent reward threshold or an invented terminal, so
outcome comparability cannot rest on a goal-based terminal that the source does
not expose.
