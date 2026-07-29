# CyberBattleSim public experiment protocol

## Status and scope

This is the one selected source-native protocol for the CyberBattleSim
qualification in RAESystem/adapters issue #25. It is backend-local evidence,
not a RAES-authored scenario, adapter manifest, conformance profile, or claim
of equivalence. The associated qualification record currently classifies the
case as **not admissible** to RAESystem/research#12; this protocol fixes what
would be run after the admission blockers are resolved.

The source is Microsoft's official
[`microsoft/CyberBattleSim`](https://github.com/microsoft/CyberBattleSim)
repository at commit
[`854d6966607fb68645651f55b0f97221bd293e0d`](https://github.com/microsoft/CyberBattleSim/tree/854d6966607fb68645651f55b0f97221bd293e0d).
All paths and symbols below resolve at that commit.

## Selected apparatus

| Role | Exact selection |
| --- | --- |
| Distribution metadata | `cyberbattlesim==0.1.0` from `setup.py`; no public index distribution or upstream release artifact exists |
| Python | CPython 3.12 |
| Gym environment | `CyberBattleChain-v0`, unwrapped `CyberBattleChain`, `size=10` |
| Topology and vulnerability model | `cyberbattle/samples/chainpattern/chainpattern.py`; `new_environment(10)` |
| Attacker | `cyberbattle.agents.baseline.agent_randomcredlookup.CredentialCacheExploiter` |
| Defender | `cyberbattle._env.defender.ScanAndReimageCompromisedMachines(probability=0.6, scan_capacity=2, scan_frequency=5)` |
| Evaluator | `cyberbattle.agents.baseline.learner.epsilon_greedy_search` |
| Public notebook | `notebooks/notebook_withdefender.py` |
| Historical benchmark snapshot | tag `benchmark-2024-08-08`, commit `2cbe240a760bdf15e16277110e3065d19eb6bdbe` |

The credential-cache baseline is selected instead of the DQL participant. It
requires no model weights and avoids representing the open upstream
"DQL still learning at evaluation time" defect as a valid held-out evaluation.
The historical benchmark tag remains evidence of the upstream public notebook
run, but it is not treated as output from the newer selected source commit.

## Exact configuration

Create the environment with these values:

```text
gym_id = "CyberBattleChain-v0"
size = 10
attacker_goal.own_atleast = 0
attacker_goal.own_atleast_percent = 1.0
defender_constraint.maintain_sla = 0.80
defender.probability = 0.6
defender.scan_capacity = 2
defender.scan_frequency = 5
winning_reward = 5000.0
losing_reward = 0.0
```

Run `CredentialCacheExploiter` through `epsilon_greedy_search` with:

```text
episode_count = 10
iteration_count = 600
epsilon = 0.90
epsilon_exponential_decay = 10000
epsilon_minimum = 0.10
render = false
verbosity = quiet
```

The selected public seed is decimal `20260729`. A conforming future runner must
bind that value separately to all four observed random sources:

1. `CyberBattleEnv.reset(seed=20260729)` for the Gym environment generator;
2. `env.action_space.seed(20260729)` for action-space sampling;
3. `random.seed(20260729)` for the defender's Python `random` calls; and
4. `numpy.random.seed(20260729)` for the defender and baseline policy's global
   NumPy calls.

The upstream `epsilon_greedy_search` implementation calls `reset()` without
forwarding a seed, so these bindings cannot currently be preserved through the
unmodified public evaluator. A top-level seed alone is therefore not a replay
claim, and no result from this protocol may be called deterministic until that
upstream seam is fixed or an explicit, identified compatibility patch is
qualified.

## Reset, action, result, and termination

`reset()` returns `(observation, info)`. `step(action)` returns
`(observation, reward, terminated, truncated, info)`. Native observations,
action arrays, credentials, explored graphs, and complete `info` values remain
inside the source-native runner; portable evidence may retain only bounded
types, field names, dimensions, booleans, scalar measures, and stable digests.

The representative smoke action is the valid initial
`local_vulnerability=[0, 1]` action. At the selected commit and seed it returns
a scalar reward of `14.0`, `terminated=false`, `truncated=false`, and
`step_count=1`. This value proves the pinned smoke only; it is not an experiment
result or study metric.

The source evaluates stop conditions in this order after each attacker and
defender step:

1. attacker goal reached **or** defender SLA constraint broken → terminate and
   replace the step reward with `winning_reward`;
2. otherwise, defender eviction goal reached → terminate and replace the step
   reward with `losing_reward`;
3. otherwise continue, clamping a negative action reward to zero.

The implementation always returns `truncated=false`. The evaluator's
`iteration_count=600` is a participant/evaluator cutoff, not Gym truncation, and
must be reported separately from goal success, SLA failure, or defender
eviction. The evaluator stops at the first source-native termination or after
600 attempted steps; it does not distinguish the two causes in its returned
`TrainedLearner` structure.

The attacker goal's cumulative-reward predicate reads the rewards from prior
steps because the current step reward is appended after the termination check.
This off-by-one behavior is an upstream semantic limitation. It does not affect
the selected ownership predicate, but it prohibits silently switching this
protocol to a reward-threshold goal.

## Measures and retained output

The primary measures are:

- steps to source-native termination, or `600` when the evaluator cutoff fires;
- cumulative attacker reward per episode;
- network availability per step and its per-episode series; and
- terminal cause, reconstructed by the runner as one of `attacker-ownership`,
  `defender-sla`, `defender-eviction`, or `evaluator-cutoff`.

Reward, terminal result, and derived measures remain distinct. Plot images are
optional derived presentation and are not source evidence. No native object
representation, raw observation, credential cache, hidden graph state, action
identifier, full reward vector, environment dump, argument dump, token, or
traceback is retained in a portable RAES artifact.

## Network, files, and patches

After source acquisition and dependency installation, execution requires no
external datasets, downloads, caches, or model weights. The protocol uses a
temporary working directory, clears `PYTHONPATH`, enables Python safe-path
behavior, and performs no checkout-relative import.

No compatibility patch, monkey patch, dependency override, edited notebook, or
copied upstream source is part of this selection. Any future patch must record
the base commit, patch digest, resulting-tree or artifact digest, purpose,
license, semantic effect, and side-by-side unmodified behavior before this
protocol can adopt it.
