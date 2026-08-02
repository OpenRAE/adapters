# NASim public experiment protocol

## Status and scope

This is the one selected source-native protocol for the NASim qualification in
RAESystem/adapters issue #32. It is backend-local evidence, not a RAES-authored
scenario, adapter manifest, conformance profile, or claim of equivalence. The
maintainer-selected profile is admitted for adapter realization. The associated
qualification record fixes the source identity and bounds the attainable claims;
its packaging, stochastic-control, and upstream defect limitations do not veto
execution.

The source is Jonathon Schwartz's official
[`Jjschwartz/NetworkAttackSimulator`](https://github.com/Jjschwartz/NetworkAttackSimulator)
repository at tag `v0.12.0`, commit
[`7c732bc4620d20a25b221a782adee29c2a89d800`](https://github.com/Jjschwartz/NetworkAttackSimulator/tree/7c732bc4620d20a25b221a782adee29c2a89d800),
published to PyPI as `nasim==0.12.0`. All paths and symbols below resolve at that
commit.

## Selected apparatus

| Role | Exact selection |
| --- | --- |
| Distribution | `nasim==0.12.0` (PyPI wheel `nasim-0.12.0-py3-none-any.whl`, `sha256:4c059e64…`) |
| Python | CPython 3.12.3 |
| Runtime pins | `gymnasium==0.26.3`, `numpy==1.26.4` (see "Compatibility" below) |
| Scenario | `tiny` static benchmark, `nasim/scenarios/benchmark/tiny.yaml` |
| Environment | `nasim.make_benchmark("tiny", fully_obs=True, flat_actions=True, flat_obs=True)` |
| Action space | `FlatActionSpace` (Discrete), `n=18` |
| Observation space | `Box`, shape `(56,)`, dtype `float32` |
| Baseline / evaluator | `nasim.agents.bruteforce_agent.run_bruteforce_agent` |
| Model weights | none (the bruteforce baseline uses no learned policy) |

The bruteforce baseline is selected instead of the `ql_agent` (tabular
Q-learning) or `dqn_agent` (Torch) participants. It requires no model weights,
introduces no training stochasticity, and is the documented `python
bruteforce_agent.py tiny` entry point. The `tiny` scenario is NASim's canonical
smallest fixed-topology benchmark, so the topology and vulnerability model are
fully determined by the YAML at the selected commit. Harder benchmark scenarios
(`small`, `medium`, …) and the learning baselines remain available and may be
qualified later as additional immutable selections without changing this one.

## Exact configuration

Construct the environment with these values (the documented headless
invocation):

```text
scenario     = "tiny"
fully_obs    = True
flat_actions = True
flat_obs     = True
render_mode  = None
```

The `tiny` scenario fixes, at the selected commit:

```text
hosts            = 3         subnets = 3
sensitive_hosts  = {(2, 0): 100, (3, 0): 100}
exploit  e_ssh   : service=ssh, os=linux, prob=0.8, cost=1, access=user
privesc  pe_tomcat: process=tomcat, os=linux, prob=1.0, cost=1, access=root
scan costs       = 1 each (service / os / subnet / process)
step_limit       = 1000
```

Run the baseline with `nasim.agents.bruteforce_agent.run_bruteforce_agent(env)`,
which cycles the flat action space in index order until the goal is reached, the
step limit fires, or its own `step_limit` (default `1e6`) is hit.

## Seeds and stochastic control

The selected public seed is decimal `20260802`. Binding it is **not** achieved
through the environment constructor or `reset`: for a static benchmark
`make_benchmark(seed=…)` is ignored, and `reset(seed=…)` seeds only the gym
`self.np_random` stream, which NASim does not use to resolve actions. Action
success is drawn from the **global** NumPy RNG at
`nasim/envs/network.py:87` (`np.random.rand() > action.prob`). A conforming
runner must therefore bind the seed explicitly:

```text
numpy.random.seed(20260802)     # the only stream that controls action success
```

The observed random sources and their binding status are enumerated in the
qualification record's `stochastic_sources`. Because the exploit `e_ssh`
succeeds with probability `0.8`, individual runs vary unless the global NumPy
seed is fixed; a top-level seed passed to `make_benchmark`/`reset` alone is not a
replay claim.

## Reset, action, result, and termination

`reset()` returns `(observation, info)`. `step(action)` returns
`(observation, reward, terminated, truncated, info)`, mapping NASim's semantics
onto the Gymnasium 5-tuple:

- `terminated = goal_reached` — every sensitive host has been compromised
  (`Network.all_sensitive_hosts_compromised`);
- `truncated = step_limit_reached` — `env.steps >= scenario.step_limit` (1000);
- `reward = action_result.value - action.cost`.

`terminated` and `truncated` are computed independently each step; the step
limit is Gymnasium truncation and must be reported separately from goal success.
Native observations, action arrays, host state, and complete `info` values
remain inside the source-native runner; portable evidence may retain only
bounded types, field names, dimensions, booleans, scalar measures, and stable
digests.

The representative smoke action is flat action index `0`
(`ServiceScan target=(1, 0)`). At the selected commit and seed it returns a
scalar reward of `-1.0` (the scan cost), `terminated=false`, `truncated=false`,
and `step_count=1`. This value proves the pinned smoke only; it is not an
experiment result or study metric.

The pinned termination probe runs the bruteforce baseline to the goal: with
`numpy.random.seed(20260802)` it reaches `terminated=true` (`truncated=false`)
after `47` steps with a total reward of `153.0`. The pinned truncation probe
drives an unproductive action to the step limit and reaches `truncated=true`
(`terminated=false`) at step `1000`, confirming the two boundaries stay
distinct.

## Measures and retained output

The primary measures are:

- steps to source-native termination, or `1000` when the step limit truncates;
- cumulative reward per episode;
- goal reached (boolean); and
- terminal cause, reconstructed by the runner as one of `goal` or `step-limit`.

Reward, terminal result, and derived measures remain distinct. No native object
representation, raw observation, host state, action identifier, full reward
vector, environment dump, argument dump, token, or traceback is retained in a
portable RAES artifact.

## Compatibility

The qualified runtime pins `gymnasium==0.26.3`, the last release where
`gymnasium.spaces.Discrete.n` is a Python `int`. From gymnasium `0.27` onward
`Discrete.n` and `Discrete.sample()` return `numpy.int64`, which NASim's own
`FlatActionSpace.get_action` rejects with `assert isinstance(action_idx, int)`
(`nasim/envs/action.py:698`); the supplied bruteforce and random agents, and the
greedy paths of the learning agents, then raise `AssertionError`. This is a
recorded upstream defect, not a silent patch: NASim source is used unmodified
and the incompatibility is disclosed in the qualification record's
`known_defects`.

## Network, files, and patches

After source acquisition and dependency installation, execution of the selected
protocol requires no external datasets, downloads, caches, or model weights. The
protocol uses a temporary working directory, clears `PYTHONPATH`, and enables
Python safe-path behavior. Importing NASim additionally requires the Tk system
libraries (`tkinter`), because `nasim/envs/render.py` imports `tkinter` and
selects the `TkAgg` matplotlib backend at import time; this is recorded as a
known defect.

No compatibility patch, monkey patch, dependency override, edited notebook, or
copied upstream source is part of this selection. Any future patch must record
the base commit, patch digest, resulting-tree or artifact digest, purpose,
license, semantic effect, and side-by-side unmodified behavior before this
protocol can adopt it.
