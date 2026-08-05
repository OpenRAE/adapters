# NASim tiny concepts

This pack is a portable RAES model of the admitted NASim `tiny` static-benchmark
case (`nasim==0.12.0`, `nasim/scenarios/benchmark/tiny.yaml`) with the
`run_bruteforce_agent` baseline. It ships topology and objective truth as an SDL
scenario, the reward/evaluator/termination intent as published experiment
contracts, and one red bruteforce participant selection.

## What is portable

- The fixed three-subnet, three-host topology, represented node-for-node (a
  static benchmark, so there is no abstraction loss).
- Abstract action contracts for service exploit, privilege escalation, service
  discovery, and subnet discovery.
- The compromise-both-sensitive-hosts objective, and the descriptive
  reward/termination measures.

## What stays source-private

The native fully observed state, the flat observation vector, the flat action
index, per-host access-level state, and evaluator-only goal truth are withheld;
the participant view is a lossy default-deny projection.

## Retained determinism loss (ADR-069)

Action success is drawn from the global NumPy stream rather than the gym
environment seed, and the static benchmark ignores its constructor seed, so the
published stochastic controls are descriptive only and carry no executable
random-stream binding. A single top-level seed value is not a deterministic
replay claim; only an explicit global NumPy seed binds action success. This loss
is disclosed, not erased: no run under this protocol is asserted to be a
deterministic replay.
