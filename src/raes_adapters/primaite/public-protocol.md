# PrimAITE public experiment protocol

## Status and scope

This is the one selected source-native protocol for the PrimAITE qualification
in RAESystem/adapters issue #39. It is backend-local evidence, not a
RAES-authored scenario, adapter manifest, conformance profile, or claim of
equivalence. The maintainer-selected profile is admitted for adapter
realization. The associated qualification record fixes the source identity and
bounds the attainable claims; its packaging, dependency, stochastic-control, and
upstream defect limitations do not veto execution.

The source is the ARCD
[`Autonomous-Resilient-Cyber-Defence/PrimAITE`](https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE)
repository at tag `v4.0.0`, commit
[`98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea`](https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/tree/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea).
All paths and symbols below resolve at that commit.

## Selected apparatus

| Role | Exact selection |
| --- | --- |
| Distribution metadata | `primaite==4.0.0` from `pyproject.toml`; no public index distribution or upstream release wheel exists (the README documents wheel-from-GitHub install only) |
| Python | CPython 3.11 (upstream classifiers and README support `>=3.9,<3.12`; the `requires-python` metadata says `<3.13`) |
| Gymnasium entrypoint | `primaite.session.environment.PrimaiteGymEnv` |
| Use case / scenario | `primaite/config/_package_data/data_manipulation.yaml` (`metadata.version 3.0`, `game.max_episode_length 128`) |
| RL-controlled seat (BLUE) | agent `defender`, `type: proxy-agent` |
| RED participant | agent `data_manipulation_attacker`, `type: red-database-corrupting-agent` (scripted) |
| GREEN participants | agents `client_1_green_user`, `client_2_green_user`, `type: probabilistic-agent` |
| Baseline participant | a scriptable policy over the BLUE action space; the do-nothing baseline (`action 0`) is used for the smoke |

The core install **without** the `rl` extra is selected. It requires no Ray
RLlib, TensorFlow, StableBaselines3, or deep-learning weights, and is the
lightest documented supported route. The RL training path behind the `rl` extra
is not part of this qualified protocol.

## Exact configuration and spaces

The scenario is loaded verbatim from the shipped
`data_manipulation.yaml`; its `sha256` is pinned in the qualification record.
The environment is constructed as:

```text
PrimaiteGymEnv(env_config="<installed>/primaite/config/_package_data/data_manipulation.yaml")
```

At the selected commit the BLUE seat exposes:

```text
action_space       = Discrete(78)
observation_space  = Box(shape=(1652,), dtype=int64, low=0, high=1)   # flatten_obs: true
```

`reset()` returns `(observation, info)` (arity 2); `observation` is a NumPy
`ndarray` of shape `(1652,)` dtype `int64` and `info` is an empty dict.
`step(action)` returns `(observation, reward, terminated, truncated, info)`
(arity 5); `reward` is a Python `float`. Native observations, traffic contents,
learned state, action ids, full reward vectors, and complete `info` values
remain inside the source-native runner; portable evidence retains only bounded
types, shapes, dtypes, booleans, scalar measures, and stable digests.

## Seeds and stochastic control

The public seed seam is `PrimaiteGymEnv.reset(seed=<int>)`, which calls
`primaite.session.environment.set_random_seed(seed, generate_seed_value)` and
seeds Python `random`, the global NumPy generator, and (when present) `torch`.
The selected public seed is decimal `20260802`.

This seam is **not usable on the light route**. `set_random_seed` dereferences
`sys.modules["torch"]` unconditionally, so `reset(seed=<int>)` raises
`KeyError('torch')` unless the `rl`/torch stack is installed. In addition, each
GREEN `ProbabilisticAgent` seeds its own generator from the uncontrolled global
NumPy RNG (`numpy.random.default_rng(numpy.random.randint(0, 65535))`), and the
scenario sets no `game.seed`. A conforming future runner must therefore treat
the following as separate, currently uncontrolled stochastic sources:

1. the Gymnasium reset seam `reset(seed=...)` (broken without torch);
2. Python `random` (scripted RED timing);
3. the global NumPy generator (GREEN policy generators, and the env
   construction seed path);
4. `torch` (only when the `rl` stack is installed).

No result from this protocol may be called deterministic or replayable until the
torch seam is fixed or an explicit, identified compatibility patch is qualified.
The bounded smoke below was nonetheless observed identical across repeated
fresh-process runs; that is empirical stability of the do-nothing smoke, not a
seed-controlled determinism claim for RL or varied-action episodes.

## Reset, action, result, and termination

The representative smoke action is the do-nothing action (`action 0`). From an
unseeded reset it returns, at the first step, a scalar reward of `0.65`,
`terminated=false`, `truncated=false`, and `step_count=1`. This value proves the
pinned smoke only; it is not an experiment result or study metric.

`step()` sets `terminated=False` unconditionally. The episode ends **only** by
truncation: `PrimaiteGame.calculate_truncated()` returns `True` when
`step_counter >= max_episode_length`. For this scenario the horizon is `128`
steps. A full do-nothing episode therefore ends after `128` steps with
`truncated=true`, `terminated=false`, a final step reward of `-0.8`, and a
cumulative reward of `-57.05`.

There is no source-native success/failure `terminated` condition in this
scenario: goal satisfaction, reward thresholds, an evaluator cutoff, the fixed
horizon, and participant stop conditions are distinct and must not be conflated.
Only the fixed-horizon truncation is present here.

## Measures and retained output

The primary measures are the per-step BLUE reward and its per-episode cumulative
series over the fixed 128-step horizon, together with the terminal cause
(`fixed-horizon-truncation`). Reward, terminal result, and any derived measure
remain distinct; a cumulative reward is not automatically the study metric. No
native object representation, raw observation, traffic payload, hidden state,
action identifier, full reward vector, environment dump, argument dump, token, or
traceback is retained in a portable RAES artifact.

PrimAITE writes session, agent-action, and system logs under a
platform-dependent home/app directory on import and during a run. These are
source-private operational outputs; the smoke isolates them under a temporary
`HOME` and does not retain them as RAES evidence.

## Network, files, and patches

After source acquisition and dependency installation, execution requires no
external datasets, downloads, caches, or model weights, and performs no network
access. The protocol uses a temporary working directory and isolated `HOME`,
clears `PYTHONPATH`, enables Python safe-path behavior, and performs no
checkout-relative import.

No compatibility patch, monkey patch, dependency override, edited scenario, or
copied upstream source is part of this selection; the `patches` list in the
qualification record is empty. Pinning `setuptools==75.6.0` (the upstream `dev`
pin) to supply the `pkg_resources` module the runtime imports is an environment
provisioning choice, not a source modification. Any future patch must record the
base commit, patch digest, resulting-tree or artifact digest, purpose, license,
semantic effect, and side-by-side unmodified behavior before this protocol can
adopt it.
