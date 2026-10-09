# CyberBattleSim evidence-capture inventory and fixture design

GitHub issue [#86](https://github.com/OpenRAE/adapters/issues/86) owns the
reconciliation of the CyberBattleSim evidence requirements, the pinned
simulator's outputs, and the adapter's capture and manifest. Its 2026-08-13
hold forbids contract, schema, manifest, runtime, package, and CLI changes, and
permits static inventories and regression-fixture design that preserve
production behavior. This page is that inventory and design. It changes no code,
packaged resource, ledger, SDL, task, manifest, or test, and it defines no RAES
contract, capability, evidence type, or status vocabulary. It uses the format of
the [NASim inventory](nasim-evidence-capture-inventory.md).

- **Snapshot:** `dev` at [`0272949`][a-commit], which pins `raes==3.3.0`
  ([`pyproject.toml` L36][a-pyproject-raes]). The `cyberbattlesim` extra
  carries only `raes-env-packs==3.6.2` ([L44][a-pyproject-cbs]), because
  CyberBattleSim installs from the pinned source.
- **Native pin:** microsoft/CyberBattleSim commit [`854d696`][m-commit]
  (`cyberbattlesim` 0.1.0), as recorded in
  [`qualification.json`][a-qualification]. Native line references on this page
  are to that commit.
- **Hold status on 2026-10-09:** in force. Of its two resume conditions, the
  capture-admission work in [OpenRAE/rae#1112][r-issue-1112] closed on
  2026-09-07 through [OpenRAE/rae#1239][r-pr-1239]; the naming decision,
  [OpenRAE/rae#1023][r-issue-1023], is still open.

## Classes

Each required datum gets one class. The class describes the datum at the pin
under today's authored boundary and ledger, not what the adapter captures;
section 3 covers capture.

| Class | Meaning on this page |
| --- | --- |
| available | The pinned source emits the datum, and no ledger row or authored statement keeps it source-private. |
| redacted | The pinned source emits the datum, and the authored requirement asks for a redacted portable form. |
| withheld | The pinned source emits the datum, and an existing ledger row or authored statement keeps it source-private. |
| lossy | The pinned source emits only a reduced or ambiguous form of the datum. |
| unavailable | The pinned source does not emit the datum. |

## 1. Authored requirements

The environment pack lives at the repository root, outside the package, in
`environments/cyberbattlesim-chain`. Its SDL is byte-identical to the scenario
SDL (SHA-256 `935ffc3c…`), and its task JSON carries the same requirement refs
as the task YAML. Neither SDL proposition cites an evidence requirement.

| ID | Requirement | Declared in | Demands |
| --- | --- | --- | --- |
| R1 | SDL `attacker-action-log` | [scenario SDL L343–353][a-sdl-r1]; [pack SDL L343–353][a-pack-sdl-r1] | `source_class: participant_action`, window "full episode", `channel: log`, `sensitivity: redacted`, `redaction: redact_secrets`, `integrity: checksum`, `loss_disclosure: best_effort` |
| R2 | SDL `availability-series` | [scenario SDL L354–364][a-sdl-r2]; [pack SDL L354–364][a-pack-sdl-r2] | `source_class: scenario_state`, window "per-step", `channel: metric`, `sensitivity: plain`, `redaction: none`, `integrity: checksum`, `loss_disclosure: best_effort` |
| T1 | metric `steps_to_termination` → R1 | [task YAML L36–38][a-task-t1]; [pack JSON L27–32][a-json-t1] | attacker steps to source-native termination, or 600 when the evaluator cutoff fires first |
| T2 | metric `cumulative_attacker_reward` → R1 | [task YAML L50–52][a-task-t2]; [pack JSON L42–47][a-json-t2] | per-episode cumulative attacker reward; winning reward 5000.0, losing reward 0.0 |
| T3 | metric `network_availability` → R2 | [task YAML L63–65][a-task-t3]; [pack JSON L57–62][a-json-t3] | per-step network availability against the 0.80 SLA floor |
| T4 | metric `terminal_cause` → R1 | [task YAML L77–79][a-task-t4]; [pack JSON L72–77][a-json-t4] | one of `attacker-ownership`, `defender-sla`, `defender-eviction`, `evaluator-cutoff`, kept distinct from Gym flags |
| T5 | `observation_requirements` → R1, R2 | [task YAML L80–84][a-task-t5]; [pack JSON L80–89][a-json-t5] | both records observed for the episode |

The run plan sets `max_steps: 600`, the four causes as
`termination_condition_refs`, four descriptive stochastic controls
(`gym-environment`, `gym-action-space`, `python-random`, `numpy-global`), and
`target_run_count: 10` ([spec YAML L20–62][a-spec-run-plan];
[pack JSON L17–56][a-json-spec-run-plan]). The task description states that
"Native reward vectors, action ids, and observations remain source-private"
([task YAML L5–11][a-task-description]; [pack JSON L6][a-json-description]).

## 2. Native availability at the pin

| Datum (needed by) | Native source at `854d696` | Class | Ledger basis |
| --- | --- | --- | --- |
| D1 portable action kind per step (R1, T1) | the single `local_vulnerability`, `remote_vulnerability`, or `connect` key of the action ([`cyberbattle_env.py` L707–745][m-execute-action]) | available | [row 10][a-ledger-10] `actions-portable`, mapped |
| D2 native action coordinates (node, vulnerability, port, and credential indices) | the same action tuples | withheld | [row 11][a-ledger-11] `actions-native-ids`, excluded |
| D3 outcome kind per step (R1) | `ActionResult(reward, outcome)` ([`actions.py` L104–108][m-action-result]); the outcome reaches the caller only as observation fields ([`cyberbattle_env.py` L859–925][m-observation-reward]) | withheld | [row 13][a-ledger-13] `observations-native-dict`, excluded; leaked credentials also fall under [row 7][a-ledger-7] |
| D4 reward per step (R1, T2) | `reward`, replaced by the winning or losing constant at termination and clamped at 0 otherwise ([`cyberbattle_env.py` L1145–1185][m-step]) | withheld | the task keeps native reward vectors source-private (section 1); [row 17][a-ledger-17] `reward-constants` maps only the winning and losing constants and the cumulative reward to the metric definition |
| D5 network availability per step (R2, T3) | `info["network_availability"]` ([`cyberbattle_env.py` L1176–1182][m-step-info]), computed after every attacker step from running nodes and services ([`actions.py` L714–746][m-availability]) | available | [row 14][a-ledger-14] `control-availability` and [row 15][a-ledger-15] `control-sla-threshold`, mapped |
| D6 terminated flag per step (T1, T4) | `self.__done` from the precedence checks ([`cyberbattle_env.py` L1162–1167][m-precedence]) | available | [row 19][a-ledger-19] `termination-precedence`, mapped |
| D7 truncation or cutoff | `step` always returns `truncated=False` ([L1185][m-step-return]); the iteration cutoff exists only in the evaluator loop ([`learner.py` L285–354][m-learner-loop]) | unavailable | [row 20][a-ledger-20] `termination-cutoff-not-truncation`, loss-disclosed as [`loss-benchmark-defects`][a-loss-defects] |
| D8 terminal cause (T4) | attacker ownership and a broken SLA both return the winning reward ([L1162–1164][m-winning]); the attacker goal reads only prior-step rewards ([L1080–1101][m-attacker-goal], appended at [L1183][m-append-reward]) | lossy | [row 18][a-ledger-18] `reward-goal-off-by-one`, loss-disclosed; the cause is separable only with D5 against the 0.80 floor |
| D9 step count (T1) | `info["step_count"]` ([L1176–1182][m-step-info]) | available | [row 22][a-ledger-22] `evaluator-run-plan`, mapped |
| D10 credential cache in `info` | `info["credential_cache"]` ([L1176–1182][m-step-info]) | withheld | [row 7][a-ledger-7] `credential-cache-native`, excluded |

The authored SDL encodes the chain pattern rather than the generated size-10
graph ([row 5][a-ledger-5], [`loss-abstracted-topology`][a-loss-topology]), so
any per-step portable target can only be one of the representative SDL hosts.

T2 cites the action log as its evidence, while D4 is withheld. A per-step reward
field in that log therefore depends on #86 first correcting the authored
boundary. This tension is recorded here, not resolved.

## 3. The capture chain today

**Admission.** `validate`, `run --mode smoke`, and `run --mode study` go through
`_task_capture_admission_gaps()` ([`cli.py` L1225–1253][a-gate],
[L1277–1278][a-gate-raise]), which returns every task evidence and observation
ref for any manifest because the RAES 3.3.0 observation capability cannot bind
a semantic ref to an emitted artifact field. For this task it returns
`attacker-action-log` and `availability-series`, so those commands exit `3`
with `researcher.validation.evidence-unverifiable`
([`docs/cyberbattlesim-researcher-command.md` L22–28][a-doc-fail-closed]).

The baseline reproduction's mediated lane runs that same `run --mode smoke`
command once per attempt and treats a non-zero exit as a failed attempt
([`reproduction.py` L2352–2412][a-mediated]). A local run of that command
against the wheel built from `0272949`, with the `cyberbattlesim` extra and the
repository's `environments/cyberbattlesim-chain` pack from a `git archive` of
`0272949`, printed the `evidence-unverifiable` diagnostic, exited `3`, and
created no output. The mediated lane behind the Revision 3 results in the
[native-readiness record](cyberbattlesim-native-readiness-record.md#corrective-baseline-reproduction-2026-08-11)
therefore cannot complete on `dev` while the gate rejects the task.

**Code behind the gate.** If a run were admitted:

- The driver keeps the step count, cumulative reward, one network-availability
  value per committed step, the latest `terminated` and `truncated`, and a
  terminal cause classified from the reward constants and availability
  ([`driver.py` L407–487][a-driver-step], [L513–526][a-driver-availability];
  [`termination.py` L12–45][a-classify]). The observation and every other
  `info` key stay in the driver.
- The participant runtime is the shared gym runtime used for NASim. Each step's
  action result and observation envelope stay in memory, with status `succeeded`
  whenever the source processed the step ([`_gym_backend/participant_runtime.py`
  L288–338][a-gym-accepted]). Each action contract has one fixed portable target
  ([`participant_runtime.py` L54–58][a-fixed-targets]).
- The evaluator emits the shared summary record and cumulative-reward measure,
  plus an outcome record whose `raw_content.content_uri` is
  `episode-outcome.json` and whose checksum is that member's SHA-256. The member
  holds `network_availability`, which must have one finite `[0, 1]` value per
  step, and `terminal_cause` ([`evaluator.py` L101–150][a-outcome-record]). The
  CLI writes the member and checks that exactly one record binds it
  ([`cli.py` L1554–1604][a-supplemental]).
- The CLI writes `evidence-records.json`, `derived-measures.json`,
  `diagnostics.json`, `participant-provenance.json`, `episode-outcome.json`,
  `run.json`, and `summary.json` per run ([`cli.py` L1511–1551][a-cli-episode],
  [L1607–1644][a-cli-run-record]). `run.json` carries one result summary,
  `cumulative_attacker_reward` ([`researcher.py` L224–228][a-result-summary]).

| Req | Declared ref in `runtime_plans.py` | Manifest declaration | Emitted artifact or field, if admitted | Gap |
| --- | --- | --- | --- | --- |
| R1 | `source-ledger:attacker-action-log` as the ownership proposition's `evidence_requirement_refs` ([L75][a-plans-ref]); `source-ledger.jsonl` has no row with that `source_id` | no `observation` capability ([`manifest.py` L258–280][a-manifest]); evaluator `supported_evidence_channels` is `{"api_response"}`, not `log` ([L199][a-channels]) | none; per-step action results stay in memory | no per-step record of D1, D4, or D6 |
| R2 | none | none for a `metric` channel | `episode-outcome.json` `network_availability`, checksum-bound by the outcome record | the series exists and is bound, but no declaration names it as R2 and RAES 3.3.0 cannot verify it |
| T1 | none | none | `completed_steps` in `summary.json`; step count in `payload_summary`; the series length | no derived measure |
| T2 | none | evaluator `supports_scoring` ([`manifest.py` L188–210][a-evaluator]) | `derived-measures.json` value | not recomputable from per-step evidence |
| T3 | none | none | the R2 series | no derived measure |
| T4 | the four causes as orchestration `termination_condition_refs` ([L49–58][a-plans-termination]) | evaluator constraint `objective_terminal_state` ([`manifest.py` L188–210][a-evaluator]) | `terminal_cause` in `episode-outcome.json` | no derived measure; the cause inherits D8's ambiguity |
| T5 | none | none | the R2 series only | R1 is not captured |

No `satisfies_refs` claim remains in this path: the retired
`evidence_satisfies_refs` identifier is pinned absent by
[`tests/test_claim_integrity.py` L44–53][a-retired], [L176–183][a-retired-test].
The runtime-plan label at L75 is the remaining static evidence reference that
#86's scope names. Other manifest declarations are the participant constraint
`native_target_attribution: unavailable` ([`manifest.py` L150–167][a-participant])
and `run_evidence: attestable` ([L276][a-run-evidence]).

**What RAES 3.3.0 can express.** As recorded for NASim, the pinned
`ObservationCapabilities` declares capture kinds, channel kinds, evidence
contracts, media types, sealing modes, and three support flags
([`capabilities.py` L144–157][r-observation]), and
`ExperimentEvidenceSatisfactionReferenceModel` names a satisfied concept by
reference only ([`experiment_manifest_references.py` L187–196][r-satisfies]).
Neither can state which artifact field carries a requirement or its
data-quality state. A field-level witness needs a RAES release that includes
[OpenRAE/rae#1239][r-pr-1239]; this repository still pins 3.3.0.

## 4. Equivalence data needs

The public notebook runs the credential-cache baseline through
`epsilon_greedy_search` for 10 episodes of up to 600 iterations
([`notebook_withdefender.py` L102–107][m-notebook-run], with
`iteration_count` at [L52][m-notebook-iterations]). The evaluator resets
without a seed, draws its explore-or-exploit choice from global NumPy, and keeps
every step's reward and network availability ([`learner.py` L224–378][m-learner]).

| Need | Today | Evidence |
| --- | --- | --- |
| Action | missing | Each step's policy proposal is admitted through RAES, but no per-step action record is written. Portable targets are fixed per action kind. |
| Outcome | missing | Per-step reward (D4) and outcome kind (D3) are withheld and not written; only the cumulative reward is. |
| Observation | missing | Envelopes withhold every native field and are not written. |
| Availability | present | `episode-outcome.json` keeps one D5 value per committed step; the public evaluator keeps the same series. |
| Termination or cutoff cause | present, lossy | `terminal_cause` is written, classified as in [`termination.py` L12–45][a-classify]; it inherits D7 and D8. |
| RNG and stochastic control | partly present, overstated | With a seed, the driver reports `gym-environment` and `gym-action-space` as applied, but the run draws from none of the generators those seeds set, and the generator behind every explore draw is unseeded and unreported (see the stream table below). The runtime emits one `seed.applied` or `seed.unbound` diagnostic per stream without naming the stream ([`_gym_backend/participant_runtime.py` L199–228][a-gym-seed-diagnostics]), and `run.json` records one control, `cyberbattlesim-gym-reset-seed` ([`researcher.py` L224][a-seed-control-id]), which is none of the spec's four control ids. |
| Evaluator | partly present | Method `cyberbattlesim-cumulative-reward` covers T2; T1, T3, and T4 have no derived measure. |
| Lineage | partly present | Run-level lineage is present as for NASim; per-step lineage is not written. |

**Random streams on the `run` path.** The table lists each generator that the
driver seeds or that the `CredentialCacheExploiter` path draws from at the pin,
with the driver's reset report ([`driver.py` L330–367][a-driver-reset]).

| Stream | Generator and seeding | Driver report with a seed | Draws on this path |
| --- | --- | --- | --- |
| `gym-environment` | `env.np_random`, rebuilt from the `reset` seed ([`cyberbattle_env.py` L1195][m-reset-seed]) | applied | none: only `sample_connect_action_in_expected_range` reads it ([L945–957][m-connect-sample]), for action kind 2 only ([L983–984][m-kind-connect]), and the policy explores with kinds `[0, 1]` ([`agent_randomcredlookup.py` L54–55][m-explore]) |
| `gym-action-space` | the space's own generator and its three subspace generators, reseeded by gymnasium 0.29.1 `Dict.seed` ([`dict.py` L111–147][g-dict-seed]), which `DiscriminatedUnion.seed` calls ([`discriminatedunion.py` L50–51][m-union-seed]) | applied ([`driver.py` L348][a-space-seed]) | none: apart from `Dict.seed` deriving the subspace seeds, only `action_space.sample()` reads any of them, from `sample_valid_action_with_luck` ([`cyberbattle_env.py` L1049–1055][m-sample-luck]), which this path never calls |
| no spec id | `action_space.union_np_random`, created when the environment builds its action space without a seed ([`cyberbattle_env.py` L561][m-action-space]), so it takes fresh OS entropy ([`discriminatedunion.py` L43–48][m-union-random]; [`seeding.py` L31–34][g-seeding]); `Dict.seed` never reseeds it | not reported | every explore draw: `explore` calls `sample_valid_action([0, 1])` ([`agent_randomcredlookup.py` L54–55][m-explore]), which repeats `sample_action_in_range` until the action mask admits the result ([`cyberbattle_env.py` L1041–1047][m-sample-valid]); that method takes the kind and every index from this generator ([L980–1005][m-sample-range]) |
| `python-random` | Python `random` | unbound | the defender's scan choice ([`defender.py` L45][m-defender-scan]) |
| `numpy-global` | global NumPy | unbound | the epsilon draw ([`driver.py` L386][a-epsilon-draw]), the exploit's source node and credential ([`agent_randomcredlookup.py` L26][m-exploit-source], [L40][m-exploit-credential]), and the defender's detection draw ([`defender.py` L49][m-defender-detect]) |

The two seeds reported as applied therefore drive no draw on this path, and an
unseeded generator drives every explore action. The spec's four controls
([spec YAML L37–61][a-spec-stochastic]; [pack JSON L30–55][a-json-spec-stochastic]),
ledger rows [24][a-ledger-24] `stochastic-controls` and
[25][a-ledger-25] `stochastic-binding-loss`,
[`loss-unbound-random-streams`][a-loss-random], which counts "four randomness
sources", and `qualification.json` `stochastic_sources`
([L460–481][a-qualification-stochastic]) all list only those four sources. None
of them names `union_np_random`, and the `env.action_space.seed` call they give
for `gym-action-space` does not reach it. The cumulative-reward measure's
limitations, written to `derived-measures.json`, name only the Python-global and
NumPy-global streams as unbound ([`evaluator.py` L76–77][a-evaluator-rng];
[`_experiment_evidence.py` L321][a-measure-limitations]).

## 5. Regression-fixture design (spec only)

Nothing in this section is implemented. It specifies the fixtures that the
implementation resuming after the hold would add to meet #86's criteria that
tests exercise the complete requirement-to-capability-to-artifact chain, fail on
missing or falsely claimed data, and make RNG coverage machine-readable. Each
chain reads requirement → native source → manifest declaration → artifact field.

- **Hermetic** means an injected driver such as `FakeDriver`
  ([`tests/test_cyberbattlesim_researcher_cli.py` L94–166][a-fake-driver]).
- **Native** means the pinned source install recorded in `qualification.json`;
  there is no index artifact ([`loss-no-source-artifact`][a-loss-artifact]),
  and CI does not install it.
- Until a RAES contract can express the witness, the existing fail-closed test
  ([`tests/test_claim_integrity.py` L143–154][a-claim-test]) remains the guard.

| Fixture | Chain | Positive case | Negative cases | Lane |
| --- | --- | --- | --- | --- |
| F1 action log | R1 → D1, D6, the cause so far, and D4 once the authored boundary allows it → a capture declaration for a participant-action `log` channel → a per-step member bound by SHA-256 from an evidence record that names `attacker-action-log` | one row per source transition with step index, portable action contract, portable target, and `terminated`. A per-step reward field depends on #86 first correcting the authored boundary that keeps D4 withheld (section 2). | missing datum: one step lacks its `terminated` value, and the run must end without a sealed success. False claim: the manifest declares the capture but the member lacks a required field. Leak: a native index or credential-cache entry in the member fails the leakage scan. | hermetic |
| F2 availability series | R2 → D5 → a `metric` channel declaration → the `episode-outcome.json` series | one value per committed step, each in `[0, 1]` | missing or extra value, and an unbound member, which the current code already rejects; a declaration naming R2 with no member behind it | hermetic |
| F3 terminal cause | T4 → D6, D4, and D5 → the cause field | one case per cause: `attacker-ownership`, `defender-sla`, `defender-eviction`, `evaluator-cutoff` | the winning reward without an availability value must stay the generic `source-terminated`, never a guessed cause | hermetic |
| F4 stochastic controls | spec control ids and every generator the path draws from → driver reset report → a per-run record that names each stream, whether its seed was applied, and whether the run draws from the generator that seed sets | a seeded run records `gym-environment` and `gym-action-space` as applied but not drawn on this path, and `python-random`, `numpy-global`, and the action-space union generator as drawn and unbound | a stream recorded as applied whose seed misses the generator the policy draws from, checked natively in F6; a drawn generator missing from the record; a run claiming `python-random` or `numpy-global` as bound; a seed value presented as a binding | hermetic; the missed-generator case is native (F6) |
| F5 measures | T1–T4 → derived from F1–F3 only | each measure recomputed from per-step records equals the reported value; T2 needs F1's reward field, so it waits on the same boundary correction | a reported measure that disagrees with recomputation | hermetic |
| F6 native shapes | the F1–F4 chain over the real driver | one seeded episode records the real per-step shapes once, so the hermetic fakes stay faithful | F4's missed-generator case: seed two builds as the driver does and compare the state of each generator the policy draws from. At the pin `union_np_random` differs between them, so a record that counts the explore draws as covered by an applied seed must fail. | native |

## 6. Related records

- [Capability and evidence-claim integrity guardrails](capability-and-evidence-claim-guardrails.md),
  from issue #84.
- [CyberBattleSim scenario and source-ledger guardrails](cyberbattlesim-scenario-ledger-guardrails.md),
  [CyberBattleSim environment-pack and researcher-command guardrails](cyberbattlesim-researcher-command-guardrails.md),
  [CyberBattleSim baseline-reproduction guardrails](cyberbattlesim-baseline-reproduction-guardrails.md),
  and the [native-readiness record](cyberbattlesim-native-readiness-record.md).
- The packaged mapping ledger: [`README.md`][a-mapping-readme],
  [`source-ledger.jsonl`][a-ledger] (29 rows), and
  [`loss-disclosures.md`][a-losses] (four entries). This page cites them and
  does not edit them.

## How this was checked

- Adapter files were read at `0272949`. The two cited RAES files were read at
  tag `v3.3.0` ([`fb8a23a`][r-commit]) and matched the same files in the
  `raes-3.3.0` wheel from PyPI.
- Native files were fetched from CyberBattleSim at `854d696` through the GitHub
  API. The cited files listed in `qualification.json` `source_files` matched
  their recorded SHA-256. `cyberbattle/simulation/actions.py`,
  `cyberbattle/_env/discriminatedunion.py`, and
  `cyberbattle/agents/baseline/agent_wrapper.py` are not in that list and were
  read at the commit. Apart from the lines cited in section 4, no line in
  `cyberbattle_env.py`, `agent_wrapper.py`, or `agent_randomcredlookup.py`
  reads `env.np_random` or `union_np_random`.
- The gymnasium 0.29.1 wheel from PyPI matched the SHA-256 in
  `qualification.json`, and its `spaces/dict.py`, `spaces/space.py`, and
  `utils/seeding.py` are byte-identical to tag `v0.29.1`
  ([`7cf4952`][g-commit]). With that wheel and NumPy 1.26.4, two spaces built
  from the pinned `discriminatedunion.py` without a seed, as at L561, and then
  seeded with `20260729` had equal own and subspace generator states but
  different `union_np_random` states, and a second `seed` call left
  `union_np_random` unchanged.
- The gate check in section 3 installed the wheel built from `0272949`
  (SHA-256 `068871d1…`) with the `cyberbattlesim` extra into a fresh CPython
  3.12 virtual environment and ran the mediated lane's `run --mode smoke`
  arguments, with `--epsilon-step-offset 0`, against
  `environments/cyberbattlesim-chain` from a `git archive` of the same commit.
  CyberBattleSim itself was not installed, and no native episode was run.

[a-commit]: https://github.com/OpenRAE/adapters/tree/0272949fa964920a7e06fb56f6d7051054756b5b
[a-pyproject-raes]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L36
[a-pyproject-cbs]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L44
[a-qualification]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/qualification.json
[a-qualification-stochastic]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/qualification.json#L460-L481
[a-sdl-r1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/scenario/cyberbattle-chain.sdl.yaml#L343-L353
[a-sdl-r2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/scenario/cyberbattle-chain.sdl.yaml#L354-L364
[a-pack-sdl-r1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/sdl/cyberbattlesim-chain.sdl.yaml#L343-L353
[a-pack-sdl-r2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/sdl/cyberbattlesim-chain.sdl.yaml#L354-L364
[a-task-description]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/experiment/cyberbattle-chain.task.exp.yaml#L5-L11
[a-task-t1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/experiment/cyberbattle-chain.task.exp.yaml#L36-L38
[a-task-t2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/experiment/cyberbattle-chain.task.exp.yaml#L50-L52
[a-task-t3]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/experiment/cyberbattle-chain.task.exp.yaml#L63-L65
[a-task-t4]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/experiment/cyberbattle-chain.task.exp.yaml#L77-L79
[a-task-t5]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/experiment/cyberbattle-chain.task.exp.yaml#L80-L84
[a-json-description]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.task.exp.json#L6
[a-json-t1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.task.exp.json#L27-L32
[a-json-t2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.task.exp.json#L42-L47
[a-json-t3]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.task.exp.json#L57-L62
[a-json-t4]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.task.exp.json#L72-L77
[a-json-t5]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.task.exp.json#L80-L89
[a-spec-run-plan]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/experiment/cyberbattle-chain.spec.exp.yaml#L20-L62
[a-json-spec-run-plan]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.spec.exp.json#L17-L56
[a-spec-stochastic]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/experiment/cyberbattle-chain.spec.exp.yaml#L37-L61
[a-json-spec-stochastic]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/environments/cyberbattlesim-chain/experiment/cyberbattlesim-chain.spec.exp.json#L30-L55
[a-plans-termination]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/runtime_plans.py#L49-L58
[a-plans-ref]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/runtime_plans.py#L75
[a-participant]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/manifest.py#L150-L167
[a-evaluator]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/manifest.py#L188-L210
[a-channels]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/manifest.py#L199
[a-manifest]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/manifest.py#L258-L280
[a-run-evidence]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/manifest.py#L276
[a-driver-reset]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/driver.py#L330-L367
[a-space-seed]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/driver.py#L348
[a-epsilon-draw]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/driver.py#L386
[a-driver-step]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/driver.py#L407-L487
[a-driver-availability]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/driver.py#L513-L526
[a-classify]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/termination.py#L12-L45
[a-outcome-record]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/evaluator.py#L101-L150
[a-evaluator-rng]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/evaluator.py#L76-L77
[a-measure-limitations]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_experiment_evidence.py#L321
[a-fixed-targets]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/participant_runtime.py#L54-L58
[a-result-summary]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/researcher.py#L224-L228
[a-seed-control-id]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/researcher.py#L224
[a-mediated]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/reproduction.py#L2352-L2412
[a-gym-seed-diagnostics]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/participant_runtime.py#L199-L228
[a-gym-accepted]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/participant_runtime.py#L288-L338
[a-gate]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1225-L1253
[a-gate-raise]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1277-L1278
[a-cli-episode]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1511-L1551
[a-cli-run-record]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1607-L1644
[a-supplemental]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1554-L1604
[a-doc-fail-closed]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/cyberbattlesim-researcher-command.md?plain=1#L22-L28
[a-fake-driver]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_cyberbattlesim_researcher_cli.py#L94-L166
[a-claim-test]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_claim_integrity.py#L143-L154
[a-retired]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_claim_integrity.py#L44-L53
[a-retired-test]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_claim_integrity.py#L176-L183
[a-mapping-readme]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/README.md
[a-ledger]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl
[a-ledger-5]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L5
[a-ledger-7]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L7
[a-ledger-10]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L10
[a-ledger-11]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L11
[a-ledger-13]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L13
[a-ledger-14]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L14
[a-ledger-15]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L15
[a-ledger-17]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L17
[a-ledger-18]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L18
[a-ledger-19]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L19
[a-ledger-20]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L20
[a-ledger-22]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L22
[a-ledger-24]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L24
[a-ledger-25]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/source-ledger.jsonl#L25
[a-losses]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/loss-disclosures.md
[a-loss-artifact]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/loss-disclosures.md?plain=1#L17-L29
[a-loss-random]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/loss-disclosures.md?plain=1#L31-L42
[a-loss-topology]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/loss-disclosures.md?plain=1#L44-L58
[a-loss-defects]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/mapping/loss-disclosures.md?plain=1#L60-L72
[m-commit]: https://github.com/microsoft/CyberBattleSim/tree/854d6966607fb68645651f55b0f97221bd293e0d
[m-execute-action]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L707-L745
[m-observation-reward]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L859-L925
[m-attacker-goal]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1080-L1101
[m-step]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1145-L1185
[m-precedence]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1162-L1167
[m-winning]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1162-L1164
[m-step-info]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1176-L1182
[m-append-reward]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1183
[m-step-return]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1185
[m-reset-seed]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1195
[m-action-space]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L561
[m-connect-sample]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L945-L957
[m-sample-range]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L980-L1005
[m-kind-connect]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L983-L984
[m-sample-valid]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1041-L1047
[m-sample-luck]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/cyberbattle_env.py#L1049-L1055
[m-union-random]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/discriminatedunion.py#L43-L48
[m-union-seed]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/discriminatedunion.py#L50-L51
[m-explore]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/agents/baseline/agent_randomcredlookup.py#L54-L55
[m-exploit-source]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/agents/baseline/agent_randomcredlookup.py#L26
[m-exploit-credential]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/agents/baseline/agent_randomcredlookup.py#L40
[m-action-result]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/simulation/actions.py#L104-L108
[m-availability]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/simulation/actions.py#L714-L746
[m-defender-scan]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/defender.py#L45
[m-defender-detect]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/_env/defender.py#L49
[m-learner]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/agents/baseline/learner.py#L224-L378
[m-learner-loop]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/cyberbattle/agents/baseline/learner.py#L285-L354
[m-notebook-iterations]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/notebooks/notebook_withdefender.py#L52
[m-notebook-run]: https://github.com/microsoft/CyberBattleSim/blob/854d6966607fb68645651f55b0f97221bd293e0d/notebooks/notebook_withdefender.py#L102-L107
[r-commit]: https://github.com/OpenRAE/rae/tree/fb8a23aee827f5c45ea6e736bc06b45f90671472
[r-issue-1023]: https://github.com/OpenRAE/rae/issues/1023
[r-issue-1112]: https://github.com/OpenRAE/rae/issues/1112
[r-pr-1239]: https://github.com/OpenRAE/rae/pull/1239
[r-observation]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_backend_protocols/capabilities.py#L144-L157
[r-satisfies]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_contracts/contracts/experiment_manifest_references.py#L187-L196
[g-commit]: https://github.com/Farama-Foundation/Gymnasium/tree/7cf49527c945297f0bfeb89edab417d87819ab00
[g-dict-seed]: https://github.com/Farama-Foundation/Gymnasium/blob/7cf49527c945297f0bfeb89edab417d87819ab00/gymnasium/spaces/dict.py#L111-L147
[g-seeding]: https://github.com/Farama-Foundation/Gymnasium/blob/7cf49527c945297f0bfeb89edab417d87819ab00/gymnasium/utils/seeding.py#L31-L34
