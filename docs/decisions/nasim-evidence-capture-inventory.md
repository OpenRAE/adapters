# NASim evidence-capture inventory and fixture design

GitHub issue [#87](https://github.com/OpenRAE/adapters/issues/87) owns the
reconciliation of the NASim evidence requirements, the pinned simulator's
outputs, and the adapter's capture and manifest. Its 2026-08-13 hold forbids
contract, schema, manifest, runtime, package, and CLI changes, and permits
static inventories and regression-fixture design that preserve production
behavior. This page is that inventory and design. It changes no code, packaged
resource, ledger, SDL, task, manifest, or test, and it defines no RAES contract,
capability, evidence type, or status vocabulary.

- **Snapshot:** `dev` at [`0272949`][a-commit], which pins `raes==3.3.0`
  ([`pyproject.toml` L36][a-pyproject-raes]) and the `nasim` extra
  `nasim==0.12.0`, `gymnasium==0.26.3`, `numpy==1.26.4`, and
  `raes-env-packs==3.6.2` ([L67][a-pyproject-nasim]).
- **Native pin:** NetworkAttackSimulator tag `v0.12.0`, commit
  [`7c732bc`][n-commit], as recorded in [`qualification.json`][a-qualification].
  Native line references on this page are to that commit.
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
| redacted | The pinned source emits the datum, and the authored requirement asks to redact this datum in the portable form. |
| withheld | The pinned source emits the datum, and an existing ledger row or authored statement keeps it source-private. |
| lossy | The pinned source emits only a reduced or ambiguous form of the datum. |
| unavailable | The pinned source does not emit the datum. |

R1's `redaction: redact_secrets` targets secrets in the record. No datum in
section 2 is a secret, so none is classed redacted.

## 1. Authored requirements

The packaged example copies are part of the inventory. The pack SDL is
byte-identical to the scenario SDL (SHA-256 `c33598c4…`), and the pack task JSON
carries the same requirement refs as the task YAML.

| ID | Requirement | Declared in | Demands |
| --- | --- | --- | --- |
| R1 | SDL `attacker-action-log` | [scenario SDL L296–306][a-sdl-r1]; [pack SDL L296–306][a-pack-sdl-r1] | `source_class: participant_action`, window "full episode", `channel: log`, `sensitivity: redacted`, `redaction: redact_secrets`, `integrity: checksum`, `loss_disclosure: best_effort` |
| R2 | SDL `host-compromise-series` | [scenario SDL L307–317][a-sdl-r2]; [pack SDL L307–317][a-pack-sdl-r2] | `source_class: scenario_state`, window "per-step", `channel: metric`, `sensitivity: plain`, `redaction: none`, `integrity: checksum`, `loss_disclosure: best_effort` |
| T1 | metric `steps_to_termination` → R1 | [task YAML L35–37][a-task-t1]; [pack JSON L27–32][a-json-t1] | attacker steps to the goal, or the step limit when truncation comes first |
| T2 | metric `cumulative_attacker_reward` → R1 | [task YAML L49–51][a-task-t2]; [pack JSON L42–47][a-json-t2] | per-episode sum of `action_result.value - action.cost` |
| T3 | metric `goal_reached` → R2 | [task YAML L62–64][a-task-t3]; [pack JSON L57–62][a-json-t3] | every sensitive host compromised before the step limit |
| T4 | metric `terminal_cause` → R1 | [task YAML L76–78][a-task-t4]; [pack JSON L72–77][a-json-t4] | goal or step-limit, kept distinct |
| T5 | `observation_requirements` → R1, R2 | [task YAML L79–83][a-task-t5]; [pack JSON L80–89][a-json-t5] | both records observed for the episode |

The measures also depend on the run plan: `max_steps: 1000` with
`termination_condition_refs` `goal-reached` and `step-limit`
([spec YAML L21–35][a-spec-episode]; [pack JSON L18–27][a-json-spec-episode]),
and two descriptive stochastic controls, `numpy-global-action-success` and
`gym-environment-reset` ([spec YAML L36–51][a-spec-stochastic];
[pack JSON L28–41][a-json-spec-stochastic]). The task description states that
"Native reward scalars, the flat action index, and the raw observation vector
remain source-private" ([task YAML L5–10][a-task-description];
[pack JSON L6][a-json-description]).

## 2. Native availability at the pin

| Datum (needed by) | Native source at `7c732bc` | Class | Ledger basis |
| --- | --- | --- | --- |
| D1 portable action kind and target host per step (R1, T1) | `Action` subclass and `target` ([`action.py` L79–138][n-action]); the flat index resolves through `FlatActionSpace.get_action` ([L685–701][n-get-action]) in `generative_step` ([`environment.py` L217–218][n-get-action-call]) | available | [row 8][a-ledger-8] `actions-portable`, mapped to `sdl:action_contracts`, and [row 1][a-ledger-1] `topology-hosts`, mapped to `sdl:nodes`; the native coordinates stay private (`native_action_coordinates: driver-private`, [`manifest.py` L91][a-manifest-coordinates]), and a target is echoed as a realized effect target only with a verified source join (`native_target_attribution`, [L102–105][a-manifest-target-attribution]; [`nasim-backend-guardrails.md` L181–183][a-backend-target-join]) |
| D2 flat action index and native action class | `env.step(action)` ([`environment.py` L143–189][n-step]); `tiny` has 18 flat actions | withheld | [row 9][a-ledger-9] `actions-native-flat-index`, excluded |
| D3 success and failure kind per step (R1) | `ActionResult` `success`, `connection_error`, `permission_error`, `undefined_error` ([`action.py` L578–629][n-action-result]), set by `Network.perform_action` ([`network.py` L36–97][n-perform]) and `HostVector.perform_action` ([`host_vector.py` L211–295][n-host-perform]); `env.step` returns them in `info` ([`environment.py` L228][n-info-return]; [`action.py` L631–651][n-info]) and in the observation's auxiliary row ([`state.py` L141][n-obs-aux-call]; [`observation.py` L92–100][n-obs-aux]) | withheld | four authored statements withhold `info` and exempt none of its flags: the participant boundary's `native-info` ([`participant_runtime.py` L36][a-redacted-info]), the participant constraint `native_observation` ([`manifest.py` L97–101][a-manifest-native-observation]), and the evaluator's `loss_disclosure` ([`evaluator.py` L47–50][a-evaluator-loss]) and `capture_notes` ([L60][a-evaluator-notes]); [row 11][a-ledger-11] excludes the observation vector |
| D4 discovery maps in `info` (`services`, `os`, `processes`, `access`, `discovered`, `newly_discovered`) | `ActionResult.info()` ([`action.py` L631–651][n-info]) | withheld | the participant boundary redacts `native-info` ([`participant_runtime.py` L28–38][a-redacted-fields]); [row 6][a-ledger-6] excludes host access state |
| D5 reward per step (R1, T2) | `reward = action_obs.value - action.cost` ([`environment.py` L227][n-reward]) | withheld | the task keeps native reward scalars source-private (section 1); [row 14][a-ledger-14] `reward-model` maps only the definition to the metric |
| D6 step count (T1) | `self.steps` ([`environment.py` L182][n-steps]) | available | [row 15][a-ledger-15] `termination-independent`, [row 17][a-ledger-17] `evaluator-run-plan` |
| D7 `terminated` and `truncated` per step (T1, T4) | `done = self.goal_reached(next_state)` ([`environment.py` L226][n-done]) and `step_limit_reached` ([L182–189][n-step-limit]); `step_limit: 1000` ([`tiny.yaml` L78][n-tiny-limit]) | available | [row 15][a-ledger-15] `termination-independent` |
| D8 root access of sensitive hosts (2, 0) and (3, 0) per step (R2, T3) | `State.host_has_access` ([`state.py` L232–239][n-state]) over `HostVector.access` ([`host_vector.py` L170–176][n-host-access]); also inside the fully observed vector | withheld | [row 6][a-ledger-6] `identity-native-host-state` and [row 11][a-ledger-11] `observations-native-vector`, both excluded |
| D9 goal predicate per step (R2, T3) | `Network.all_sensitive_hosts_compromised` ([`network.py` L210–214][n-all-sensitive]) through `NASimEnv.goal_reached` ([`environment.py` L451–469][n-goal]) | available | [row 13][a-ledger-13] `objective-goal`, mapped to the SDL objective |

Three tensions belong to the #87 reconciliation and are recorded here, not
resolved:

- R1 asks for a "Portable record of attacker action outcomes"
  ([SDL L297][a-sdl-r1-outcomes]), but both `env.step` channels that carry D3
  are withheld: `info` by the four statements in D3's row, and the observation
  vector, auxiliary row included, by row 11. The SDL already gives each action
  contract portable failure classes ([L170–172][a-sdl-failures-exploit],
  [L189–191][a-sdl-failures-privesc], [L208–209][a-sdl-failures-service],
  [L226–227][a-sdl-failures-subnet]; [row 8][a-ledger-8]), and
  [`public-protocol.md` L104–107][a-protocol-portable] keeps complete `info`
  values in the runner while letting portable evidence retain booleans; the
  four statements withhold `info` without that distinction.
- R2 asks for a plain per-step compromise record, while [row 6][a-ledger-6]
  states: "The native per-host access-level state and compromised flags are
  simulator-private runtime state and never enter a portable artifact." A
  per-host boolean from the predicate D9 uses would avoid the native vector of
  row 11, but it projects the per-host access-level state that row 6 keeps
  private.
- T2 cites the action log as its evidence, while D5 is withheld. The sum can
  also be recomputed from D1 and D3 with the static table in
  [`tiny.yaml` L21–47][n-tiny-values]: every action costs 1, and value is gained
  only when root is first taken on a sensitive host, 100 each
  ([`host_vector.py` L240–245][n-host-value-exploit],
  [L279–284][n-host-value-privesc]). D3 is withheld too, so that route meets
  the R1 tension.

Of the ledger rows not cited above, [row 19][a-ledger-19] and
[row 22][a-ledger-22] carry the two loss disclosures,
[`loss-unbound-action-rng`][a-loss-rng] and
[`loss-apparatus-reconstruction`][a-loss-apparatus], which bound replay and
reconstruction claims. The others map static topology, vulnerability, identity,
participant, observation-boundary, firewall, evaluator, stochastic-control, and
provenance facts. None of them supplies per-step capture.

## 3. The capture chain today

**Admission.** `_admit_native_run()` calls `_task_capture_admission_gaps()`
([`cli.py` L1225–1253][a-gate], [L1277–1278][a-gate-raise]). That function
returns every task evidence and observation ref for any manifest, because the
RAES 3.3.0 observation capability cannot bind a semantic ref to an emitted
artifact field. For this task it returns `attacker-action-log` and
`host-compromise-series`, so `validate`, `run --mode smoke`, and
`run --mode study` exit `3` with `researcher.validation.evidence-unverifiable`
before runtime planning or native import
([`docs/nasim-researcher-command.md` L46–52][a-doc-fail-closed]). The 2026-10-09
live run recorded on [#36][a-issue-36-run] observed exactly that. No episode
artifact is produced on `dev`; conformance mode, which runs no native attacker
episode, is unaffected.

**Post-run task/run join.** A second fail-closed gate follows execution; it is
reached only if the admission gate is bypassed. `_complete_native_run` writes
the four episode files ([`cli.py` L1521–1539][a-cli-episode-files]) and then
calls `validate_experiment_run_against_task` ([L1633][a-cli-run-join]) before
it writes `run.json` ([L1634][a-cli-run-json]). Since [#90][a-pr-90]
(`8db4fbd`), the evidence artifact ([L1541–1551][a-cli-artifact]) carries no
`satisfies_refs` ([`tests/test_claim_integrity.py` L139][a-claim-satisfies]).
RAES 3.3.0 matches an observation requirement only by artifact id or by
`satisfies_refs` ([`experiment_run.py` L373–388][r-artifact-satisfies]), so the
join rejects `attacker-action-log` and `host-compromise-series`
([L419–427][r-observation-join]), and the command exits `6` with
`researcher.artifact.failure` ([`cli.py` L1725–1730][a-cli-artifact-failure]).
The claim guardrails design this layer: the seam "lets the canonical task/run
validator reject the run"
([`capability-and-evidence-claim-guardrails.md` L83–84][a-guardrails-seam]).
In smoke and study mode, an admitted run therefore leaves only
`evidence-records.json`, `derived-measures.json`, `diagnostics.json`, and
`participant-provenance.json` under `runs/<run-id>-1/`, unsealed, with no
`inventory.json` and no `failure.json`. It writes no `run.json`, no per-run
`summary.json`, and no batch artifact.

**Code behind the gates.** The episode path ([`researcher.py` L356–399][a-episode])
would capture the following if a run were admitted:

- The driver keeps running totals only: step count, cumulative reward, and the
  latest `terminated`, `truncated`, and terminal cause. It discards the
  observation and `info` returned by `env.step` ([`driver.py` L322–338][a-driver-step]).
- The participant runtime builds one action result and one observation envelope
  per step and holds them in memory ([`_gym_backend/participant_runtime.py`
  L288–338][a-gym-accepted], [L388–465][a-gym-observation]). The action status is
  `succeeded` whenever the source processed the step, whatever
  `ActionResult.success` was ([L300][a-gym-status]). Its single effect is
  `unknown_effect` with empty `target_refs`, because the NASim driver never sets
  `portable_target_refs` ([`driver.py` L124–141][a-driver-step-type]). Its
  `evidence_refs` stay empty, because the researcher request sets no
  `observation_boundary_evidence_refs` ([L381–386][a-gym-evidence-refs];
  [`researcher.py` L238–261][a-request]). No CLI path writes these models.
- The evaluator builds one capture spec with a single requirement,
  `nasim-evaluator-summary` ([`_experiment_evidence.py` L105–170][a-capture-spec];
  [`nasim/backend/evaluator.py` L13–62][a-nasim-evaluator]), but nothing writes
  it: `capture_spec()` ([`_gym_backend/evaluator.py` L532–535][a-gym-capture-spec])
  has no caller under `src/`. Only its projection-scoped ids reach each evidence
  record, as `capture_spec_ref` `nasim-evaluator-capture.<sha256>` and
  `capture_requirement_ref` `nasim-evaluator-summary.<sha256>`
  ([`_experiment_evidence.py` L223–243][a-record-capture-refs]). The evaluator
  also emits one evidence record, whose `raw_content.payload_summary` is a
  sentence carrying the step count, cumulative reward, both terminal flags, and
  the terminal cause ([L226–233][a-payload-summary]), and one derived measure for
  `cumulative_attacker_reward` ([L285–329][a-derived-measure]). The proposition
  truth result is always `unknown`, with `indeterminacy_reason`
  `lossy_evidence` ([`_gym_backend/evaluator.py` L402–439][a-truth]).
- The CLI writes the four episode files per run
  ([`cli.py` L1511–1551][a-cli-episode]). Its writers for `run.json` and
  `summary.json` per run ([L1607–1644][a-cli-run]) and, per batch, for
  `study.json` in study mode, `provenance.json`, `machine-inventory.json`,
  `summary.json`, and finally `inventory.json` ([L1647–1714][a-cli-batch]) exist
  but are unreachable for this task, because the post-run join fails first. In
  study mode, `study.json` also sits behind
  `validate_experiment_study_against_tasks_and_runs` ([L1658][a-cli-study-join]),
  which runs the same join again
  ([`experiment_analysis.py` L414–423][r-study-join]). The run record built in
  memory ([`researcher.py` L174–211][a-archival];
  [`_researcher_support.py` L453–462][a-run-summary]) would carry one result
  summary, `cumulative_attacker_reward`; it is never written. The per-run writer
  also has a path for supplemental JSON members: `_write_supplemental_artifacts`
  writes each one, and `_verify_supplemental_binding` requires exactly one
  evidence record to bind it by SHA-256 ([`cli.py` L1540][a-cli-supplemental-call],
  [L1554–1567][a-cli-supplemental-write], [L1587–1604][a-cli-supplemental-verify]).
  CyberBattleSim writes its per-step availability series this way
  ([`cyberbattlesim/backend/evaluator.py` L148–150][a-cbs-supplemental]); the
  NASim episode sets no member ([`researcher.py` L393–399][a-nasim-episode-evidence]).

| Req | Declared ref in `runtime_plans.py` | Manifest declaration | Emitted artifact or field, if admitted | Gap |
| --- | --- | --- | --- | --- |
| R1 | none | no `observation` capability: `compose_capability_set` never sets one ([`_manifest_support.py` L179–195][a-compose]); evaluator `supported_evidence_channels` is `{"api_response"}`, not `log` ([`manifest.py` L142][a-manifest-channels]) | none; per-step action results stay in memory | no per-step record of D1, D3, D5, or D7 |
| R2 | `source-ledger:host-compromise-series` as the proposition's `evidence_requirement_refs` ([L75][a-plans-ref], passed through [`_researcher_support.py` L645–655][a-objective-plan]); `source-ledger.jsonl` has no row with that `source_id` | none for a `metric` channel | none; the proposition truth result is `unknown` | no per-step record of D8 or D9; the ref is a label, not a join |
| T1 | none | none | step count inside `payload_summary` | no derived measure and no per-step source |
| T2 | none | evaluator `supports_scoring` ([`manifest.py` L131–156][a-manifest-evaluator]) | `derived-measures.json` value; `payload_summary` | the measure cites the summary record, so it is not recomputable from per-step evidence |
| T3 | none | none | `terminated` inside `payload_summary` | no derived measure |
| T4 | none | evaluator constraint `objective_terminal_state` ([`manifest.py` L131–156][a-manifest-evaluator]) | terminal cause inside `payload_summary` | no derived measure |
| T5 | none | none | none | neither observation requirement is captured |

The manifest's other evidence-related declarations are participant constraints
`native_observation` and `native_target_attribution: unavailable`
([`manifest.py` L97–105][a-manifest-participant]) and the manifest constraint
`run_evidence: attestable` ([`manifest.py` L210–233][a-manifest]).

**What RAES 3.3.0 can express.** The pinned `ObservationCapabilities` declares
capture kinds, channel kinds, evidence contracts, media types, sealing modes,
and three support flags ([`capabilities.py` L144–157][r-observation]), and
`BackendCapabilitySet.observation` is optional ([L244–254][r-capability-set]).
`ExperimentEvidenceSatisfactionReferenceModel` names a satisfied concept by
reference only ([`experiment_manifest_references.py` L187–196][r-satisfies]).
Neither can state which artifact field carries a requirement, or whether that
field is missing, withheld, redacted, or lossy, so the admission gate fails
closed as [the claim guardrails](capability-and-evidence-claim-guardrails.md)
require.
[OpenRAE/rae#1239][r-pr-1239] ships in raes 4.1.0 and later; this repository
still pins 3.3.0.

## 4. Equivalence data needs

| Need | Today | Evidence |
| --- | --- | --- |
| Action | missing | No per-step action record is written. The packaged red configuration selects only `participant.action-contract.service-exploit` ([configuration L18–28][a-red-configuration]; [`researcher.py` L224–235][a-red-contract]) and sends no target, so the driver resolves the first flat `Exploit` on every step ([`driver.py` L393–416][a-driver-resolve]): index 4, on host (1, 0). The bruteforce baseline cycles all 18 indices ([`bruteforce_agent.py` L57–75][n-bruteforce]), and the authored statements describe the attacker as that baseline: the SDL attacker is "cycling the flat action space" ([SDL L277][a-sdl-attacker]), ledger [row 16][a-ledger-16] maps the "exhaustive round-robin bruteforce baseline" and [row 17][a-ledger-17] the bruteforce run "that cycles the action space", and the task names the `run_bruteforce_agent` baseline ([task YAML L5–10][a-task-description], [L87–89][a-task-population]). This page records that contradiction for #87 and does not resolve it. A probe of that resolution rule with the pinned `nasim` 0.12.0 wheel truncated at step 1000 with cumulative reward −1000 and the goal unreached (see "How this was checked"). A per-step log is what would expose that difference in a run. |
| Outcome | missing | D3 and D5 are withheld (section 2) and not captured; the action status records only that the source processed the step. |
| Observation | missing | Envelopes withhold every native field and are not written ([`_gym_backend/participant_runtime.py` L388–465][a-gym-observation]). |
| Availability | not required | Neither the SDL nor the task declares an availability series or measure for `tiny`. |
| Termination or cutoff cause | partly present | Final flags and cause appear only in `payload_summary` text; there are no per-step flags and no derived measure. |
| RNG and stochastic control | partly present | With a seed, the driver binds the global NumPy stream and the gym reset seed ([`driver.py` L254–265][a-driver-reset]) and the runtime emits one `nasim.seed.applied` diagnostic per stream into `diagnostics.json` ([`_gym_backend/participant_runtime.py` L199–228][a-gym-seed-diagnostics]). The diagnostics do not name the stream, so neither spec control id that the driver's reset report carries ([`driver.py` L270–275][a-driver-streams]) is recorded in any artifact. The run record would carry one control, `nasim-gym-reset-seed` ([`researcher.py` L205][a-seed-control-id]; [`_researcher_support.py` L183–186][a-seed-controls]), which is neither of the spec's two control ids; it is built but never written for this task. The action-success draws ([`network.py` L87][n-rng]) are not emitted by the source. |
| Evaluator | partly present | Method `nasim-cumulative-reward` covers T2 only; T1, T3, and T4 have no derived measure. |
| Lineage | partly present | The evidence records that an admitted run writes carry the run ref, the task ref, the protocol ref at the source commit, and the qualification provenance ref ([`_experiment_evidence.py` L244–281][a-record-lineage]), and `participant-provenance.json` carries participant provenance. The run record's scenario digest, apparatus context, stochastic controls, and result summary ([`_researcher_support.py` L413–463][a-run-lineage]) are built but never written for this task. Per-step lineage from an action instance to its driver operation exists only in memory ([`_gym_backend/participant_runtime.py` L467–470][a-gym-operation-ref]). |

## 5. Regression-fixture design (spec only)

Nothing in this section is implemented. It specifies the fixtures that the
implementation resuming after the hold would add to meet #87's criterion that
tests exercise the complete requirement-to-capability-to-artifact chain and fail
on missing or falsely claimed data. Each chain reads requirement → native source
→ manifest declaration → artifact field.

- **Hermetic** means a deterministic injected driver in the style of
  `FakeNasimDriver` ([`tests/test_nasim_researcher_cli.py` L161–232][a-fake-driver]).
- **Native** means the `nasim` extra with Tk, on a platform whose runtime
  artifacts match `qualification.json`; the #36 run used linux/amd64.
- Until a RAES contract can express the witness, the existing fail-closed test
  ([`tests/test_claim_integrity.py` L143–154][a-claim-test]) remains the guard.

| Fixture | Chain | Positive case | Negative cases | Lane |
| --- | --- | --- | --- | --- |
| F1 action log | R1 → D1, D3, D7, and D5 or its recomputation inputs → a capture declaration for a participant-action `log` channel → a run-scoped per-step JSON member bound by SHA-256 from an evidence record that names `attacker-action-log` | one row per source transition with step index, portable action contract, portable target, success and failure kind, `terminated`, and `truncated`; presupposes the #87 decision to exempt D3's flags from the `info` withholding or to amend R1 (the R1 tension) | missing datum: the fake omits the outcome of one step, and the run must end without a sealed success. False claim: the manifest declares the capture but the member lacks a required field, and admission or task/run validation must reject it. Leak: a native action-class name or flat index in the member fails the leakage scan. | hermetic |
| F2 compromise series | R2 → D8 projected to one boolean per sensitive host, plus D9 → a `metric` channel declaration → a per-step series | the series length equals the step count, and `goal_reached` equals the conjunction at the last step; presupposes the #87 decision to amend row 6 or R2 (the R2 tension) | missing datum: the series is shorter than the step count. False claim: the record is declared but absent. Impossible data: a host loses root, which the source cannot produce. | hermetic |
| F3 measures | T1–T4 → derived from F1 and F2 only | `steps_to_termination` is the row count; `cumulative_attacker_reward` is the per-step sum or its recomputation from `tiny.yaml`; `goal_reached` comes from the last F2 row; `terminal_cause` comes from the last row's two flags, both kept | a reported measure that disagrees with recomputation from F1 and F2; a measure reported as satisfied while its source datum is withheld | hermetic |
| F4 stochastic controls | spec control ids → driver reset report → a per-run record naming each spec control id with its applied or unbound disposition | a seeded run names both ids as applied | an unseeded run claiming a binding; a control id the spec does not declare | hermetic |
| F5 native shapes | the F1–F4 chain over the real driver | one seeded episode records the real per-step shapes once, so the hermetic fakes stay faithful | not applicable | native |

## 6. Related records

- [Capability and evidence-claim integrity guardrails](capability-and-evidence-claim-guardrails.md),
  from issue #84.
- [NASim scenario and source-ledger guardrails](nasim-scenario-ledger-guardrails.md),
  [NASim backend architecture guardrails](nasim-backend-guardrails.md), and
  [NASim researcher run-and-evidence command guardrails](nasim-researcher-command-guardrails.md).
- The packaged mapping ledger: [`README.md`][a-mapping-readme],
  [`source-ledger.jsonl`][a-ledger] (22 rows), and
  [`loss-disclosures.md`][a-losses] (two entries). This page cites them and
  does not edit them.

## How this was checked

- Adapter files were read at `0272949`. The four cited RAES files were read at
  tag `v3.3.0` ([`fb8a23a`][r-commit]) and matched the same files in the
  `raes-3.3.0` wheel from PyPI.
- `nasim-0.12.0-py3-none-any.whl` from PyPI matched the wheel SHA-256 in
  `qualification.json` (`4c059e64…`). The eight `source_files` entries under
  `nasim/` matched their recorded digests in the wheel, and the cited
  `state.py`, `observation.py`, `host_vector.py`, `environment.py`,
  `network.py`, and `action.py` matched the blobs at `7c732bc`.
- The post-run join in section 3 was exercised against the adapter code at
  `0272949` through the test suite's native-source seams and a
  `FakeNasimDriver`, with `_task_capture_admission_gaps` bypassed:
  `run --mode smoke` and `run --mode study` both exited `6` and left only the
  four episode files. With
  the run join made a no-op, smoke exited `0` and study still exited `6` at the
  study join; with the pre-#90 `satisfies_refs` restored, both exited `0`. No
  file written in any of these runs contains either spec control id.
- The probe in section 4 ran on macOS arm64 with CPython 3.12.13,
  `nasim==0.12.0`, `gymnasium==0.26.3`, and `numpy==1.26.4`:
  `nasim.make_benchmark("tiny", fully_obs=True, flat_actions=True,
  flat_obs=True)`, `numpy.random.seed(20260802)`, `env.reset(seed=20260802)`,
  then `env.step(4)` until `terminated` or `truncated`. That host is not native
  in the section 5 sense: its NumPy wheel does not match `qualification.json`,
  so the adapter reports `native_available` false there. The outcome does not
  depend on the platform: every step costs 1, and index 4 grants only user
  access on a host that is not sensitive, so root is never taken and no value
  is gained ([`tiny.yaml` L21–47][n-tiny-values]).

[a-commit]: https://github.com/OpenRAE/adapters/tree/0272949fa964920a7e06fb56f6d7051054756b5b
[a-pyproject-raes]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L36
[a-pyproject-nasim]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L67
[a-qualification]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/qualification.json
[a-sdl-r1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/scenario/nasim-tiny.sdl.yaml#L296-L306
[a-sdl-r2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/scenario/nasim-tiny.sdl.yaml#L307-L317
[a-sdl-r1-outcomes]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/scenario/nasim-tiny.sdl.yaml#L297
[a-sdl-attacker]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/scenario/nasim-tiny.sdl.yaml#L277
[a-sdl-failures-exploit]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/scenario/nasim-tiny.sdl.yaml#L170-L172
[a-sdl-failures-privesc]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/scenario/nasim-tiny.sdl.yaml#L189-L191
[a-sdl-failures-service]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/scenario/nasim-tiny.sdl.yaml#L208-L209
[a-sdl-failures-subnet]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/scenario/nasim-tiny.sdl.yaml#L226-L227
[a-protocol-portable]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/public-protocol.md?plain=1#L104-L107
[a-pack-sdl-r1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/sdl/nasim-tiny.sdl.yaml#L296-L306
[a-pack-sdl-r2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/sdl/nasim-tiny.sdl.yaml#L307-L317
[a-task-description]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.task.exp.yaml#L5-L10
[a-task-population]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.task.exp.yaml#L87-L89
[a-task-t1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.task.exp.yaml#L35-L37
[a-task-t2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.task.exp.yaml#L49-L51
[a-task-t3]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.task.exp.yaml#L62-L64
[a-task-t4]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.task.exp.yaml#L76-L78
[a-task-t5]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.task.exp.yaml#L79-L83
[a-json-description]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/experiment/nasim-tiny.task.exp.json#L6
[a-json-t1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/experiment/nasim-tiny.task.exp.json#L27-L32
[a-json-t2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/experiment/nasim-tiny.task.exp.json#L42-L47
[a-json-t3]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/experiment/nasim-tiny.task.exp.json#L57-L62
[a-json-t4]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/experiment/nasim-tiny.task.exp.json#L72-L77
[a-json-t5]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/experiment/nasim-tiny.task.exp.json#L80-L89
[a-spec-episode]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.spec.exp.yaml#L21-L35
[a-spec-stochastic]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/experiment/nasim-tiny.spec.exp.yaml#L36-L51
[a-json-spec-episode]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/experiment/nasim-tiny.spec.exp.json#L18-L27
[a-json-spec-stochastic]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/experiment/nasim-tiny.spec.exp.json#L28-L41
[a-plans-ref]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/runtime_plans.py#L75
[a-objective-plan]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_researcher_support.py#L645-L655
[a-compose]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_manifest_support.py#L179-L195
[a-manifest]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/manifest.py#L210-L233
[a-manifest-participant]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/manifest.py#L97-L105
[a-manifest-native-observation]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/manifest.py#L97-L101
[a-manifest-coordinates]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/manifest.py#L91
[a-manifest-target-attribution]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/manifest.py#L102-L105
[a-manifest-evaluator]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/manifest.py#L131-L156
[a-manifest-channels]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/manifest.py#L142
[a-gate]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1225-L1253
[a-gate-raise]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1277-L1278
[a-cli-episode]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1511-L1551
[a-cli-run]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1607-L1644
[a-cli-batch]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1647-L1714
[a-cli-episode-files]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1521-L1539
[a-cli-artifact]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1541-L1551
[a-cli-run-join]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1633
[a-cli-run-json]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1634
[a-cli-study-join]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1658
[a-cli-artifact-failure]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1725-L1730
[a-cli-supplemental-call]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1540
[a-cli-supplemental-write]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1554-L1567
[a-cli-supplemental-verify]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1587-L1604
[a-doc-fail-closed]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/nasim-researcher-command.md?plain=1#L46-L52
[a-pr-90]: https://github.com/OpenRAE/adapters/pull/90
[a-guardrails-seam]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/decisions/capability-and-evidence-claim-guardrails.md?plain=1#L83-L84
[a-backend-target-join]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/decisions/nasim-backend-guardrails.md?plain=1#L181-L183
[a-issue-36-run]: https://github.com/OpenRAE/adapters/issues/36#issuecomment-6075415717
[a-episode]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/researcher.py#L356-L399
[a-red-contract]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/researcher.py#L224-L235
[a-request]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/researcher.py#L238-L261
[a-archival]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/researcher.py#L174-L211
[a-seed-control-id]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/researcher.py#L205
[a-nasim-episode-evidence]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/researcher.py#L393-L399
[a-red-configuration]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/examples/nasim-tiny/participant/nasim-red-bruteforce.configuration.json#L18-L28
[a-driver-step-type]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/driver.py#L124-L141
[a-driver-reset]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/driver.py#L254-L265
[a-driver-streams]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/driver.py#L270-L275
[a-driver-step]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/driver.py#L322-L338
[a-driver-resolve]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/driver.py#L393-L416
[a-redacted-fields]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/participant_runtime.py#L28-L38
[a-redacted-info]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/participant_runtime.py#L36
[a-gym-seed-diagnostics]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/participant_runtime.py#L199-L228
[a-gym-accepted]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/participant_runtime.py#L288-L338
[a-gym-status]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/participant_runtime.py#L300
[a-gym-evidence-refs]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/participant_runtime.py#L381-L386
[a-gym-observation]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/participant_runtime.py#L388-L465
[a-gym-operation-ref]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/participant_runtime.py#L467-L470
[a-truth]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/evaluator.py#L402-L439
[a-gym-capture-spec]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/evaluator.py#L532-L535
[a-capture-spec]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_experiment_evidence.py#L105-L170
[a-record-capture-refs]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_experiment_evidence.py#L223-L243
[a-payload-summary]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_experiment_evidence.py#L226-L233
[a-record-lineage]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_experiment_evidence.py#L244-L281
[a-derived-measure]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_experiment_evidence.py#L285-L329
[a-nasim-evaluator]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/evaluator.py#L13-L62
[a-evaluator-loss]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/evaluator.py#L47-L50
[a-evaluator-notes]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/backend/evaluator.py#L60
[a-cbs-supplemental]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyberbattlesim/backend/evaluator.py#L148-L150
[a-seed-controls]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_researcher_support.py#L183-L186
[a-run-lineage]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_researcher_support.py#L413-L463
[a-run-summary]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_researcher_support.py#L453-L462
[a-fake-driver]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_nasim_researcher_cli.py#L161-L232
[a-claim-test]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_claim_integrity.py#L143-L154
[a-claim-satisfies]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_claim_integrity.py#L139
[a-mapping-readme]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/README.md
[a-ledger]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl
[a-ledger-1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L1
[a-ledger-6]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L6
[a-ledger-8]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L8
[a-ledger-9]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L9
[a-ledger-11]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L11
[a-ledger-13]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L13
[a-ledger-14]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L14
[a-ledger-15]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L15
[a-ledger-16]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L16
[a-ledger-17]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L17
[a-ledger-19]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L19
[a-ledger-22]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/source-ledger.jsonl#L22
[a-losses]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/loss-disclosures.md
[a-loss-rng]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/loss-disclosures.md?plain=1#L22-L34
[a-loss-apparatus]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/nasim/mapping/loss-disclosures.md?plain=1#L36-L51
[n-commit]: https://github.com/Jjschwartz/NetworkAttackSimulator/tree/7c732bc4620d20a25b221a782adee29c2a89d800
[n-action]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/action.py#L79-L138
[n-action-result]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/action.py#L578-L629
[n-info]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/action.py#L631-L651
[n-get-action]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/action.py#L685-L701
[n-step]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/environment.py#L143-L189
[n-steps]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/environment.py#L182
[n-step-limit]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/environment.py#L182-L189
[n-get-action-call]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/environment.py#L217-L218
[n-done]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/environment.py#L226
[n-reward]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/environment.py#L227
[n-info-return]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/environment.py#L228
[n-goal]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/environment.py#L451-L469
[n-perform]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/network.py#L36-L97
[n-rng]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/network.py#L87
[n-all-sensitive]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/network.py#L210-L214
[n-host-access]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/host_vector.py#L170-L176
[n-host-perform]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/host_vector.py#L211-L295
[n-host-value-exploit]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/host_vector.py#L240-L245
[n-host-value-privesc]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/host_vector.py#L279-L284
[n-state]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/state.py#L232-L239
[n-obs-aux-call]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/state.py#L141
[n-obs-aux]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/envs/observation.py#L92-L100
[n-tiny-values]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/scenarios/benchmark/tiny.yaml#L21-L47
[n-tiny-limit]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/scenarios/benchmark/tiny.yaml#L78
[n-bruteforce]: https://github.com/Jjschwartz/NetworkAttackSimulator/blob/7c732bc4620d20a25b221a782adee29c2a89d800/nasim/agents/bruteforce_agent.py#L57-L75
[r-commit]: https://github.com/OpenRAE/rae/tree/fb8a23aee827f5c45ea6e736bc06b45f90671472
[r-issue-1023]: https://github.com/OpenRAE/rae/issues/1023
[r-issue-1112]: https://github.com/OpenRAE/rae/issues/1112
[r-pr-1239]: https://github.com/OpenRAE/rae/pull/1239
[r-observation]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_backend_protocols/capabilities.py#L144-L157
[r-capability-set]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_backend_protocols/capabilities.py#L244-L254
[r-satisfies]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_contracts/contracts/experiment_manifest_references.py#L187-L196
[r-artifact-satisfies]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_contracts/contracts/experiment_run.py#L373-L388
[r-observation-join]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_contracts/contracts/experiment_run.py#L419-L427
[r-study-join]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_contracts/contracts/experiment_analysis.py#L414-L423
