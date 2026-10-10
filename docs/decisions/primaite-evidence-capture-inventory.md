# PrimAITE evidence-capture inventory and fixture design

GitHub issue [#88](https://github.com/OpenRAE/adapters/issues/88) owns the
reconciliation of the PrimAITE evidence requirements, the pinned simulator's
outputs, and the adapter's capture and manifest. Its 2026-08-13 hold forbids
contract, schema, manifest, runtime, package, and CLI changes, and permits
static inventories and regression-fixture design that preserve production
behavior. This page is that inventory and design. It changes no code, packaged
resource, ledger, SDL, task, manifest, or test, and it defines no RAES contract,
capability, evidence type, or status vocabulary. It uses the format of the
[NASim inventory](nasim-evidence-capture-inventory.md).

- **Snapshot:** `dev` at [`0272949`][a-commit], which pins `raes==3.3.0`
  ([`pyproject.toml` L36][a-pyproject-raes]). The `primaite` extra is empty
  ([L51][a-pyproject-primaite]); PrimAITE installs from the pinned source.
- **Native pin:** Autonomous-Resilient-Cyber-Defence/PrimAITE tag `v4.0.0`,
  commit [`9861798`][p-commit], as recorded in
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
| redacted | The pinned source emits the datum, and the authored requirement asks to redact this datum in the portable form. |
| withheld | The pinned source emits the datum, and an existing ledger row or authored statement keeps it source-private. |
| lossy | The pinned source emits only a reduced or ambiguous form of the datum. |
| unavailable | The pinned source does not emit the datum. |

Of the authored requirements in section 1, only R1 asks for redaction. Its
`redaction: redact_secrets` targets secrets in its record. The data R1 needs,
D1, D3, and D2's response status, are not secrets, so no datum is classed
redacted.

## 1. Authored requirements

PrimAITE has no packaged example and no environment pack, so the scenario SDL
and the experiment task are the only authored copies. No SDL proposition cites
an evidence requirement.

| ID | Requirement | Declared in | Demands |
| --- | --- | --- | --- |
| R1 | SDL `blue-action-log` | [SDL L471–481][a-sdl-r1] | `source_class: participant_action`, window "full episode", `channel: log`, `sensitivity: redacted`, `redaction: redact_secrets`, `integrity: checksum`, `loss_disclosure: best_effort` |
| R2 | SDL `data-integrity-series` | [SDL L482–492][a-sdl-r2] | `source_class: scenario_state`, window "per-step", `channel: metric`, `sensitivity: plain`, `redaction: none`, `integrity: checksum`, `loss_disclosure: best_effort` |
| R3 | SDL `service-availability-series` | [SDL L493–503][a-sdl-r3] | per-step web and database service availability, with the same attributes as R2 |
| T1 | metric `steps_to_truncation` → R1 | [task YAML L37–39][a-task-t1] | steps to the fixed 128-step horizon |
| T2 | metric `cumulative_blue_reward` → R1 | [task YAML L52–54][a-task-t2] | per-episode cumulative BLUE reward: database-file integrity (weight 0.40) plus the two shared GREEN rewards |
| T3 | metric `data_asset_integrity` → R2 | [task YAML L66–68][a-task-t3] | per-step integrity of the protected database asset, as a bounded scalar series |
| T4 | metric `green_service_penalty` → R3 | [task YAML L80–82][a-task-t4] | per-episode GREEN penalty from webpage-unavailable (0.25) and database-unreachable (0.05) components |
| T5 | metric `terminal_cause` → R1 | [task YAML L94–96][a-task-t5] | the reconstructed terminal cause; only `fixed-horizon-truncation` exists |
| T6 | `observation_requirements` → R1, R2, R3 | [task YAML L97–103][a-task-t6] | all three records observed for the episode |

The run plan sets `max_steps: 128`, the single termination ref
`fixed-horizon-truncation`, four descriptive stochastic controls
(`gym-reset-seam`, `python-random`, `numpy-global`, `torch`), and
`target_run_count: 3` ([spec YAML L20–62][a-spec-run-plan]). The task
description states that "Native Discrete(78) action ids, the flattened
Box(1652) observation, per-step reward vectors, NMNE counts, and info dicts
remain source-private" ([task YAML L5–12][a-task-description]).

## 2. Native availability at the pin

| Datum (needed by) | Native source at `9861798` | Class | Ledger basis |
| --- | --- | --- | --- |
| D1 portable BLUE action contract per step (R1) | the CAOS action name and parameters the agent chose ([`interface.py` L24–47][p-history-item]), recorded for every agent by `apply_agent_actions` ([`game.py` L167–183][p-apply-actions]) | lossy | [row 9][a-ledger-9] maps the action map to SDL contracts, but [row 11][a-ledger-11] discloses that portable contracts do not reproduce the native interface ([`loss-abstracted-participant-interface`][a-loss-interface]) |
| D2 native action ids, requests, responses, and per-agent rewards | `AgentHistoryItem.request`, `.response`, `.reward`, and `.reward_info` ([`interface.py` L36–44][p-history-fields]): `save_reward_to_history` writes each agent's per-step reward into `.reward` ([L199–201][p-save-reward]), called for every agent at [`game.py` L163][p-reward-history], and the database-unreachable penalty writes its connection status, or `n/a` without a request, into `.reward_info` ([`rewards.py` L329–336][p-reward-info]). Every agent's latest item is returned in `info["agent_actions"]` ([`environment.py` L142–144][p-step-info]), and the histories are written to the agent log on reset when `save_agent_actions` is set ([L175–177][p-agent-log]; [`data_manipulation.yaml` L5][p-save-actions]) | withheld | [row 10][a-ledger-10] `actions-native-ids` and [row 13][a-ledger-13], which excludes the info dict |
| D3 BLUE reward per step (R1, T2) | `reward_function.current_reward` ([`environment.py` L138][p-reward]), the weighted sum of components ([`rewards.py` L492–505][p-reward-function]) | withheld | the task keeps per-step reward vectors source-private (section 1); [row 23][a-ledger-23] maps only the weights to the metric definitions |
| D4 BLUE reward component values per step (T2) | `RewardFunction.update` keeps only the total, not each component's value ([`rewards.py` L498–503][p-reward-total]) | unavailable | the integrity component is recomputable from D5; the two shared components equal the GREEN agents' rewards, built from D7's penalties, which PrimAITE emits, withheld, as each GREEN history item's `.reward` (D2) |
| D5 database file health per step (R2, T3) | `health_status` of `database.db` on `database_server` in the simulation state, which PrimAITE labels the actual status, beside a separate visible status ([`file_system_item_abc.py` L75–79][p-file-status-fields], emitted at [L101–102][p-file-state]; enum [L43–62][p-health-enum]), read through `get_sim_state` ([`game.py` L153–155][p-sim-state]) and scored by `DatabaseFileIntegrity` ([`rewards.py` L111–161][p-integrity]); the RED `DELETE` payload sets it to `COMPROMISED` ([`database_service.py` L302–310][p-delete]). BLUE observes only `visible_status`, which only a scan copies from the actual status ([`file.py` L116][p-file-scan]): the observation reads it while `file_system_requires_scan` is true ([`file_system_observations.py` L115–118][p-file-obs]), the default ([`node_observations.py` L50–57][p-scan-defaults]), which the BLUE observation space does not override ([`data_manipulation.yaml` L119–191][p-blue-obs]) | withheld | hidden truth, which [`mapping/README.md` L49–53][a-mapping-governance], [`primaite-scenario-ledger-guardrails.md` L83–85][a-ledger-guardrails-leak], [`public-protocol.md` L113–116][a-protocol-hidden], [`primaite-conformance-guardrails.md` L186–187][a-conformance-projection], [`evaluator.py` L73–81][a-evaluator-withheld], and [`AGENTS.md` L27–30][a-agents-leak] keep source-private; [row 21][a-ledger-21] and [row 23][a-ledger-23] map only the objective and the weights |
| D6a web service operating state per step (R3) | the web service's `operating_state` ([`service.py` L49][p-operating-state]), a `ServiceOperatingState` of RUNNING, STOPPED, PAUSED, DISABLED, INSTALLING, or RESTARTING ([L18–32][p-operating-enum]), which `Service.describe_state` writes into the simulation state ([L204][p-service-describe]); `_can_perform_action` lets a service perform actions only while it is RUNNING ([L108][p-service-gate]). BLUE observes it without a scan ([`software_observation.py` L49–54][p-service-obs]) | available | [row 15][a-ledger-15] `controls-service-ports` maps the services to SDL nodes |
| D6b web service actual health, and database service operating state and actual health, per step (R3) | each service's `health_state_actual` ([`service.py` L205][p-service-health]), a `SoftwareHealthState` of UNUSED, GOOD, FIXING, COMPROMISED, or OVERWHELMED ([`software.py` L44–56][p-software-health]), and the database service's `operating_state` (D6a's field). For the web service BLUE observes `health_state_visible` ([`service.py` L206][p-service-visible]), which only a scan updates ([`software.py` L207–210][p-software-scan]), while `services_requires_scan` keeps its default, true ([`software_observation.py` L49–54][p-service-obs]; [`node_observations.py` L50–57][p-scan-defaults]). The BLUE observation lists no service on `database_server` ([`data_manipulation.yaml` L131–135][p-blue-db-host]), so that slot is padded and observes nothing of the database service ([`host_observations.py` L138–140][p-service-pad]). Both database fields gate availability: `receive` drops every payload unless the service can perform actions, which needs RUNNING ([`database_service.py` L374–375][p-db-receive-gate]), and a query then gets status 500, "the database service is unavailable", unless `health_state_actual` is GOOD ([L279–281][p-db-health-gate]) | withheld | hidden state, on D5's basis; [row 15][a-ledger-15] maps only the services to SDL nodes |
| D7 workforce-visible web and database outcomes per step (R3, T4) | `WebpageUnavailablePenalty` and `GreenAdminDatabaseUnreachablePenalty`, which recompute only on a GREEN request and otherwise reuse the last value ([`rewards.py` L218–339][p-green-penalties]) | lossy | [row 24][a-ledger-24] `reward-green-penalties`, mapped to the metric definitions |
| D8 truncation per step (T1, T5) | `calculate_truncated` fires at `step_counter >= max_episode_length` ([`game.py` L201–206][p-truncated]); `max_episode_length: 128` ([`data_manipulation.yaml` L13][p-horizon]) | available | [row 25][a-ledger-25] `termination-fixed-horizon`, mapped |
| D9 source terminal state (T5) | `terminated = False` unconditionally ([`environment.py` L140][p-terminated]) | unavailable | [row 26][a-ledger-26], loss-disclosed as [`loss-fixed-horizon-only-termination`][a-loss-horizon] |
| D10 BLUE observation | the flattened `Box(1652)` observation | withheld | [row 13][a-ledger-13] `observations-native-vector`, excluded |

Four tensions belong to the #88 reconciliation and are recorded here, not
resolved:

- R1 asks for a "Portable record of blue action outcomes for adjudication"
  ([SDL L472][a-sdl-r1-outcomes]), but each action's outcome status is D2's
  `response.status`, which reaches the caller only in `info["agent_actions"]`,
  and [row 13][a-ledger-13] excludes the info dict.
- R2 and R3 ask for plain per-step scenario-state records
  ([SDL L482–503][a-sdl-series]), and T3 asks for "a bounded scalar series"
  ([task YAML L59–62][a-task-t3-construct]), but D5 and D6b are hidden state.
  [`public-protocol.md` L56–60][a-protocol-bounded] keeps native observations
  and complete `info` values in the runner while letting portable evidence
  retain booleans and scalar measures, and the statements in D5's row keep
  hidden state source-private. #88 must decide whether to admit a bounded
  projection, such as the boolean SDL propositions
  ([SDL L342–374][a-sdl-propositions]) or T3's scalar. The +1/0/−1 integrity
  mapping does not avoid the withholding: it is the BLUE
  `database-file-integrity` reward component
  ([`rewards.py` L155–161][p-integrity-mapping]). D7's
  per-step values are the GREEN agents' reward components
  ([row 24][a-ledger-24]). [`evaluator.py` L73–81][a-evaluator-withheld] and
  [`primaite-conformance-guardrails.md` L186–187][a-conformance-projection]
  withhold both.
- R3 asks for per-step service availability. Each service holds two
  candidates: `operating_state` (D6a for the web service, D6b for the database
  service), which gates whether a service can perform actions, and the
  separate health signal `health_state_actual` (D6b). Both gate the database's
  availability: its `receive` drops every payload unless the service is
  RUNNING, and a query then fails with status 500 unless the health is GOOD
  ([`database_service.py` L374–375][p-db-receive-gate],
  [L279–281][p-db-health-gate]). Which of them, or both, R3 means is for #88 to
  decide. T4's penalty reads neither; it uses D7, which only changes on the
  steps a GREEN user makes a request.
- T2 cites the action log, while D3 is withheld and D4 is not emitted. The
  BLUE total is recomputable from D5 and the two GREEN agents' per-step rewards
  in D2, with the weights in [`data_manipulation.yaml` L615–632][p-defender-reward].
  D5 and those rewards are withheld too, so that route needs a #88 decision to
  lift the reward and reward-component withholding for the recomputed total.

## 3. The capture chain today

**No execution path.** PrimAITE is not one of the researcher backends: the CLI
registry lists only `cyborg-cage2`, `nasim-tiny`, and `cyberbattlesim-chain`
([`cli.py` L966–1048][a-backends]). The live driver runs nothing in-process. On
every interpreter this distribution installs on, Python 3.12 and later
([`pyproject.toml` L22][a-pyproject-python]), `construct` and `reset`
([`driver.py` L135–156][a-driver-construct]) stop at the qualified-runtime gate,
because `qualification.json` records CPython 3.11
([L204–221][a-driver-runtime-gate]);
`test_live_driver_refuses_unqualified_runtime` pins that
([`tests/test_primaite_backend.py` L944–949][a-runtime-test]). Only on 3.11
would `construct` go on to verify the selected source identity and then refuse
in-process construction. `step` and `evaluate` refuse unconditionally
([L158–168][a-driver-step-refuse]). The module docstring gives the reasons:
PrimAITE writes to platform directories on import, and neither the
worker-process boundary nor bounded 3.12 qualification evidence exists
([L1–19][a-driver-doc]). A composed live run therefore fails at provisioning,
where the shared provisioner calls `construct`
([`_gym_backend/provisioner.py` L111–135][a-provisioner]). Conformance runs only
over an injected non-native driver ([`README.md` L119][a-readme]). No native
PrimAITE run produces portable evidence on `dev`.

**Code behind the refusal.** With an injected driver:

- The participant runtime admits a BLUE action and rejects it as
  `primaite.participant.unrepresentable-action` before source mutation when the
  driver reports `representable=False`
  ([`participant_runtime.py` L250–261][a-unrepresentable]). The module
  docstring gives the reason: no portable BLUE contract maps to exactly one
  native `Discrete(78)` operation ([L1–11][a-runtime-doc]). The default
  `FakeDriver` reports every step that way, which its docstring calls "the
  honest live behavior for the current evidence"
  ([`tests/test_primaite_backend.py` L83–85][a-fake-default]).
- A driver that reports a representable step with a source transition reaches
  the accepted path instead ([`participant_runtime.py` L273–327][a-accepted]).
  The runtime then records one observation envelope per accepted action, with
  the driver's step number as its `sequence_number` ([L408][a-sequence]). It
  attaches `evidence.primaite.blue-action` ([L48][a-action-ref]) to the action
  result and the envelope only when the request's observation boundary lists
  that ref ([L287–291][a-action-ref-gate] for the result,
  [L383–387][a-envelope-ref-gate] for the envelope); the SDL names R1
  `blue-action-log`, not that ref.
  `test_representable_transition_models_observation_without_leaking` exercises
  this path ([`tests/test_primaite_backend.py` L546–568][a-representable-test]).
  No live run reaches it, because a live run fails at provisioning.
- The evaluator emits one capture spec and one evidence record whose
  `payload_summary` states the step count and terminal cause and says the
  cumulative BLUE reward is withheld; it emits no derived measure
  ([`evaluator.py` L96–127][a-withheld]). The record itself is emitted with
  `sensitivity` and `redaction_state` set to `redacted`
  ([`_experiment_evidence.py` L264–274][a-record-redacted]); only the reward
  inside it is withheld.
- There is no `runtime_plans.py` for PrimAITE, and no PrimAITE module declares
  an `evidence_requirement_refs` value or names R1, R2, or R3.

| Req | Declared ref | Manifest declaration | Emitted artifact or field | Gap |
| --- | --- | --- | --- | --- |
| R1 | none for `blue-action-log`; the runtime's only per-action evidence ref is `evidence.primaite.blue-action` ([`participant_runtime.py` L48][a-action-ref]), a different name | no `observation` capability ([`manifest.py` L354–371][a-capability-set]); evaluator `supported_evidence_channels` is `{"api_response"}`, not `log` ([L283][a-channels]); constraint `action_representability` ([L339–350][a-participant-constraints]) | none on live or default-driver runs; on the unreached accepted path, an action result and an observation envelope, which carry `evidence.primaite.blue-action` only when the boundary lists it | on live and default-driver runs no BLUE action is accepted and nothing is recorded per step; the only per-action hook is gated on the boundary and does not name `blue-action-log` |
| R2 | none | none for a `metric` channel | none | no per-step record of D5 |
| R3 | none | none for a `metric` channel | none | no per-step record of D6 or D7 |
| T1, T5 | none | none | step count and terminal cause inside the `payload_summary` of the redacted evaluator record, which withholds the reward | no derived measure |
| T2 | none | `supports_scoring` is `False` and `reward_projection` is withheld ([`manifest.py` L264–294][a-evaluator]) | none | the reward is withheld by design |
| T3, T4 | none | none | none | no series and no derived measure |
| T6 | none | none | none | no observation requirement is captured |

The manifest also declares `run_evidence: attestable` and
`runtime_claim: live source qualified on CPython 3.11 only`
([`manifest.py` L374–427][a-manifest]). The claim-integrity test already pins
that the task's refs are unverifiable against this manifest
([`tests/test_claim_integrity.py` L20–42][a-claim-tasks], [L143–154][a-claim-test]).

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

The public evaluation surface is `PrimaiteGymEnv`: each `step` returns the
BLUE reward, `terminated=False`, the truncation flag, and every agent's latest
history item ([`environment.py` L125–147][p-step]).

| Need | Today | Evidence |
| --- | --- | --- |
| Action | missing | On live runs the driver refuses at provisioning, and on default-driver runs every BLUE action is reported unrepresentable, so none reaches the source; only an injected representable step reaches the accepted path (section 3). RED and GREEN act inside the aggregate source turn and are not participant-admitted ([`manifest.py` L346–349][a-source-internal]). |
| Outcome | missing | D2 and D3 are not captured. |
| Observation | missing | D10 stays withheld. Live and default-driver runs write no envelope; the unreached accepted path writes one that lists the native observation vector as redacted ([`participant_runtime.py` L431–444][a-envelope-redaction]). |
| Availability | missing | Neither D6 nor D7 is captured. |
| Termination or cutoff cause | partly present | Only fixed-horizon truncation exists (D8, D9); the cause appears only inside the `payload_summary` of the redacted evaluator record. |
| RNG and stochastic control | missing | `set_random_seed` binds Python `random`, global NumPy, and `torch`, but raises `KeyError('torch')` when `torch` is not imported ([`environment.py` L30–63][p-seed]), and `reset` only calls it for an explicit seed ([L171–172][p-reset-seed]). Each GREEN agent seeds its generator from global NumPy ([`probabilistic_agent.py` L19][p-green-rng]). The adapter's reset report distinguishes applied, broken, absent, and unbound streams ([`driver.py` L42–56][a-reset-report]), but no live reset runs. |
| Evaluator | missing | No derived measure exists for any of T1–T5. |
| Lineage | partly present | The redacted evaluator record, which withholds the reward, carries the shared run, task, and source-revision references; nothing per step. |

## 5. Regression-fixture design (spec only)

Nothing in this section is implemented. It specifies the fixtures that the
implementation resuming after the hold would add to meet #88's criterion that
tests exercise the complete requirement-to-capability-to-artifact chain and fail
on missing or falsely claimed data. Each chain reads requirement → native source
→ manifest declaration → artifact field.

- **Hermetic** means an injected driver such as `FakeDriver`
  ([`tests/test_primaite_backend.py` L79–178][a-fake-driver]).
- **Native** means a real `PrimaiteDriver` behind a separately reviewed
  worker-process boundary, on a runtime with bounded CPython 3.12
  qualification evidence. The driver docstring
  ([`driver.py` L13–18][a-driver-blockers]) and the conformance-composition
  guardrails ([`primaite-conformance-guardrails.md` L100–104][a-conformance-live],
  [L138–141][a-conformance-native]) require both before any live run, and
  neither exists at `0272949`, so this lane cannot run yet. There is no
  published, hash-locked install route
  ([`loss-no-source-artifact`][a-loss-artifact]), and no CI job installs
  PrimAITE: the distributions session installs only the empty `primaite` extra
  and runs an injected driver ([`noxfile.py` L911–934][a-nox-primaite]).
- Until a RAES contract can express the witness, the existing fail-closed test
  ([`tests/test_claim_integrity.py` L143–154][a-claim-test]) remains the guard.

| Fixture | Chain | Positive case | Negative cases | Lane |
| --- | --- | --- | --- | --- |
| F1 BLUE action log | R1 → D1 and the response status from D2 → a capture declaration for a participant-action `log` channel → a per-step member bound by SHA-256 from an evidence record that names `blue-action-log` | one row per step with the portable contract, the native outcome status, and the step index; presupposes the #88 decision to exempt the response status from the `info` withholding or to amend R1 (the R1 tension in section 2) | missing datum: one step lacks its outcome, and the run must end without a sealed success. False claim: the manifest declares the capture while every action is rejected as unrepresentable. Leak: a native action id, request path, or IP address in the member fails the leakage scan. | hermetic |
| F2 integrity series | R2 → a bounded projection of D5 → a `metric` channel declaration → a per-step series | one value per step, each the declared projection of D5 at that step; presupposes the #88 decision to admit a bounded projection of withheld D5 (the R2 and R3 tension in section 2) | a series shorter than the step count; a value outside the declared bounded range; a declared series with no member | hermetic |
| F3 availability series | R3 → D6 for service state (`operating_state`, `health_state_actual`, or both, as #88 decides) and D7 for workforce outcomes → a `metric` channel declaration → per-step series | the chosen D6 field for both services at every step, and workforce outcomes that change only on GREEN request steps; presupposes the #88 decision to admit the chosen withheld D6b field or fields and D7's reward-component values (the R2 and R3 tension) | a workforce value that changes on a step without a request; a single series presented as both D6 and D7; a `health_state_actual` series presented as `operating_state`, or the reverse | hermetic |
| F4 measures and termination | T1–T5 → derived from F1–F3 and D8 | `steps_to_truncation` is 128; the BLUE total is recomputed from D5 and the GREEN per-step rewards, which presupposes the #88 decision to lift the reward and reward-component withholding for it (the T2 tension); `terminal_cause` is `fixed-horizon-truncation` | a reported reward while `reward_projection` is withheld; any terminal cause other than fixed-horizon truncation | hermetic |
| F5 stochastic controls | spec control ids → the driver reset report → a per-run record of each id's disposition | a seeded run: `gym-reset-seam` and `python-random` broken without `torch`, `torch` absent, `numpy-global` unbound. An unseeded run: `gym-reset-seam` broken, `torch` absent, and `python-random` and `numpy-global` unbound, because `reset` applies no seed without one ([`environment.py` L171–172][p-reset-seed]) | a seeded run claiming a bound stream on the no-rl route; a spec control id missing from the record, as `python-random` is from the unseeded reports of today's `FakeDriver` and CI probe ([`tests/test_primaite_backend.py` L128][a-fake-reset]; [`noxfile.py` L281–283][a-nox-probe-reset]) | hermetic |
| F6 native shapes | the F1–F5 chain over a real worker-process driver | one seeded episode records the real per-step shapes once, so the hermetic fakes stay faithful | not applicable | native; blocked until both conditions above hold |

## 6. Related records

- [Capability and evidence-claim integrity guardrails](capability-and-evidence-claim-guardrails.md),
  from issue #84.
- [PrimAITE qualification guardrails](primaite-qualification-guardrails.md),
  [PrimAITE scenario and source-ledger guardrails](primaite-scenario-ledger-guardrails.md),
  [PrimAITE backend architecture guardrails](primaite-backend-guardrails.md), and
  [PrimAITE conformance-composition guardrails](primaite-conformance-guardrails.md).
- The packaged mapping ledger: [`README.md`][a-mapping-readme],
  [`source-ledger.jsonl`][a-ledger] (33 rows), and
  [`loss-disclosures.md`][a-losses] (five entries). This page cites them and
  does not edit them.

## How this was checked

- Adapter files were read at `0272949`. The two cited RAES files were read at
  tag `v3.3.0` ([`fb8a23a`][r-commit]) and matched the same files in the
  `raes-3.3.0` wheel from PyPI.
- Native files were fetched from PrimAITE at `9861798` through the GitHub API.
  The cited files listed in `qualification.json` `source_files`
  (`environment.py`, `game.py`, `probabilistic_agent.py`, and
  `data_manipulation.yaml`) matched their recorded SHA-256. The other cited
  files (`interface.py`, `rewards.py`, `node_observations.py`,
  `host_observations.py`, `file_system_observations.py`,
  `software_observation.py`, `file_system_item_abc.py`, `file.py`,
  `software.py`, `service.py`, and `database_service.py`) are not in that list
  and were read at the commit. A search of every module under `src/primaite`
  at the commit found no write of a file's or a service's actual health into
  its visible status beyond the two scans cited in section 2, and no code that
  turns a `requires_scan` flag off; `data_manipulation.yaml` sets none of them.
- No native PrimAITE episode was run for this page.

[a-commit]: https://github.com/OpenRAE/adapters/tree/0272949fa964920a7e06fb56f6d7051054756b5b
[a-pyproject-raes]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L36
[a-pyproject-primaite]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L51
[a-pyproject-python]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L22
[a-qualification]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/qualification.json
[a-readme]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/README.md?plain=1#L119
[a-agents-leak]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/AGENTS.md?plain=1#L27-L30
[a-sdl-propositions]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/scenario/data-manipulation.sdl.yaml#L342-L374
[a-sdl-r1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/scenario/data-manipulation.sdl.yaml#L471-L481
[a-sdl-r1-outcomes]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/scenario/data-manipulation.sdl.yaml#L472
[a-sdl-r2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/scenario/data-manipulation.sdl.yaml#L482-L492
[a-sdl-r3]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/scenario/data-manipulation.sdl.yaml#L493-L503
[a-sdl-series]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/scenario/data-manipulation.sdl.yaml#L482-L503
[a-task-description]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.task.exp.yaml#L5-L12
[a-task-t1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.task.exp.yaml#L37-L39
[a-task-t2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.task.exp.yaml#L52-L54
[a-task-t3-construct]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.task.exp.yaml#L59-L62
[a-task-t3]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.task.exp.yaml#L66-L68
[a-task-t4]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.task.exp.yaml#L80-L82
[a-task-t5]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.task.exp.yaml#L94-L96
[a-task-t6]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.task.exp.yaml#L97-L103
[a-spec-run-plan]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/experiment/data-manipulation.spec.exp.yaml#L20-L62
[a-backends]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L966-L1048
[a-driver-doc]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/driver.py#L1-L19
[a-driver-blockers]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/driver.py#L13-L18
[a-reset-report]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/driver.py#L42-L56
[a-driver-construct]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/driver.py#L135-L156
[a-driver-step-refuse]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/driver.py#L158-L168
[a-driver-runtime-gate]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/driver.py#L204-L221
[a-provisioner]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_gym_backend/provisioner.py#L111-L135
[a-runtime-doc]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/participant_runtime.py#L1-L11
[a-action-ref]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/participant_runtime.py#L48
[a-unrepresentable]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/participant_runtime.py#L250-L261
[a-accepted]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/participant_runtime.py#L273-L327
[a-action-ref-gate]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/participant_runtime.py#L287-L291
[a-envelope-ref-gate]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/participant_runtime.py#L383-L387
[a-sequence]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/participant_runtime.py#L408
[a-envelope-redaction]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/participant_runtime.py#L431-L444
[a-evaluator-withheld]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/evaluator.py#L73-L81
[a-withheld]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/evaluator.py#L96-L127
[a-record-redacted]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/_experiment_evidence.py#L264-L274
[a-evaluator]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/manifest.py#L264-L294
[a-channels]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/manifest.py#L283
[a-participant-constraints]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/manifest.py#L339-L350
[a-source-internal]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/manifest.py#L346-L349
[a-capability-set]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/manifest.py#L354-L371
[a-manifest]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/backend/manifest.py#L374-L427
[a-fake-driver]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_primaite_backend.py#L79-L178
[a-fake-default]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_primaite_backend.py#L83-L85
[a-fake-reset]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_primaite_backend.py#L128
[a-representable-test]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_primaite_backend.py#L546-L568
[a-runtime-test]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_primaite_backend.py#L944-L949
[a-nox-probe-reset]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/noxfile.py#L281-L283
[a-nox-primaite]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/noxfile.py#L911-L934
[a-claim-tasks]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_claim_integrity.py#L20-L42
[a-claim-test]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_claim_integrity.py#L143-L154
[a-mapping-readme]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/README.md
[a-mapping-governance]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/README.md?plain=1#L49-L53
[a-protocol-bounded]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/public-protocol.md?plain=1#L56-L60
[a-protocol-hidden]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/public-protocol.md?plain=1#L113-L116
[a-ledger-guardrails-leak]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/decisions/primaite-scenario-ledger-guardrails.md?plain=1#L83-L85
[a-conformance-live]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/decisions/primaite-conformance-guardrails.md?plain=1#L100-L104
[a-conformance-native]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/decisions/primaite-conformance-guardrails.md?plain=1#L138-L141
[a-conformance-projection]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/decisions/primaite-conformance-guardrails.md?plain=1#L186-L187
[a-ledger]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl
[a-ledger-9]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L9
[a-ledger-10]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L10
[a-ledger-11]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L11
[a-ledger-13]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L13
[a-ledger-15]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L15
[a-ledger-21]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L21
[a-ledger-23]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L23
[a-ledger-24]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L24
[a-ledger-25]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L25
[a-ledger-26]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/source-ledger.jsonl#L26
[a-losses]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/loss-disclosures.md
[a-loss-artifact]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/loss-disclosures.md?plain=1#L17-L29
[a-loss-interface]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/loss-disclosures.md?plain=1#L47-L61
[a-loss-horizon]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/primaite/mapping/loss-disclosures.md?plain=1#L81-L94
[p-commit]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/tree/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea
[p-seed]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/session/environment.py#L30-L63
[p-step]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/session/environment.py#L125-L147
[p-reward]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/session/environment.py#L138
[p-terminated]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/session/environment.py#L140
[p-step-info]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/session/environment.py#L142-L144
[p-reset-seed]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/session/environment.py#L171-L172
[p-agent-log]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/session/environment.py#L175-L177
[p-sim-state]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/game.py#L153-L155
[p-reward-history]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/game.py#L163
[p-apply-actions]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/game.py#L167-L183
[p-truncated]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/game.py#L201-L206
[p-history-item]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/interface.py#L24-L47
[p-history-fields]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/interface.py#L36-L44
[p-save-reward]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/interface.py#L199-L201
[p-integrity]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/rewards.py#L111-L161
[p-integrity-mapping]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/rewards.py#L155-L161
[p-green-penalties]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/rewards.py#L218-L339
[p-reward-info]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/rewards.py#L329-L336
[p-reward-function]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/rewards.py#L492-L505
[p-reward-total]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/rewards.py#L498-L503
[p-green-rng]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/scripted_agents/probabilistic_agent.py#L19
[p-scan-defaults]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/observations/node_observations.py#L50-L57
[p-service-pad]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/observations/host_observations.py#L138-L140
[p-file-obs]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/observations/file_system_observations.py#L115-L118
[p-service-obs]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/game/agent/observations/software_observation.py#L49-L54
[p-health-enum]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/file_system/file_system_item_abc.py#L43-L62
[p-file-status-fields]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/file_system/file_system_item_abc.py#L75-L79
[p-file-state]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/file_system/file_system_item_abc.py#L101-L102
[p-file-scan]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/file_system/file.py#L116
[p-software-health]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/software.py#L44-L56
[p-software-scan]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/software.py#L207-L210
[p-operating-enum]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/service.py#L18-L32
[p-operating-state]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/service.py#L49
[p-service-gate]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/service.py#L108
[p-service-describe]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/service.py#L204
[p-service-health]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/service.py#L205
[p-service-visible]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/service.py#L206
[p-db-health-gate]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/database/database_service.py#L279-L281
[p-delete]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/database/database_service.py#L302-L310
[p-db-receive-gate]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/simulator/system/services/database/database_service.py#L374-L375
[p-save-actions]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/config/_package_data/data_manipulation.yaml#L5
[p-horizon]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/config/_package_data/data_manipulation.yaml#L13
[p-blue-obs]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/config/_package_data/data_manipulation.yaml#L119-L191
[p-blue-db-host]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/config/_package_data/data_manipulation.yaml#L131-L135
[p-defender-reward]: https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE/blob/98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea/src/primaite/config/_package_data/data_manipulation.yaml#L615-L632
[r-commit]: https://github.com/OpenRAE/rae/tree/fb8a23aee827f5c45ea6e736bc06b45f90671472
[r-issue-1023]: https://github.com/OpenRAE/rae/issues/1023
[r-issue-1112]: https://github.com/OpenRAE/rae/issues/1112
[r-pr-1239]: https://github.com/OpenRAE/rae/pull/1239
[r-observation]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_backend_protocols/capabilities.py#L144-L157
[r-satisfies]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_contracts/contracts/experiment_manifest_references.py#L187-L196
