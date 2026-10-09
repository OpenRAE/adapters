# CybORG evidence-capture inventory and fixture design

GitHub issue [#85](https://github.com/OpenRAE/adapters/issues/85) owns the
reconciliation of the CAGE-2 evidence requirements, the pinned CybORG outputs,
and the adapter's capture and manifest. Its 2026-08-13 hold forbids contract,
schema, manifest, runtime, package, and CLI changes, and permits static
inventories and regression-fixture design that preserve production behavior.
This page is that inventory and design. It changes no code, packaged resource,
ledger, SDL, task, manifest, or test, and it defines no RAES contract,
capability, evidence type, or status vocabulary. It uses the format of the
[NASim inventory](nasim-evidence-capture-inventory.md).

- **Snapshot:** `dev` at [`0272949`][a-commit], which pins `raes==3.3.0`
  ([`pyproject.toml` L36][a-pyproject-raes]). The `cyborg` extra carries only
  `raes-env-packs==3.6.2` ([L56][a-pyproject-cyborg]), because CybORG 2.1
  installs from the pinned source.
- **Native pin:** cage-challenge/cage-challenge-2 commit
  [`26ce1c1`][c-commit] (CybORG 2.1), as recorded in
  [`qualification.json`][a-qualification] together with a packaging-only
  [`setup.py` patch][a-patch] whose recorded behavioral delta is "none". Native
  line references on this page are to that commit.
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

The pack SDL is byte-identical to the scenario SDL (SHA-256 `14da37a9…`). The
task exists only as the packaged JSON; there is no CybORG experiment YAML
outside the pack. Its ref `source-ledger:reward-components` names ledger
[row 44][a-ledger-44], `reward-components`.

| ID | Requirement | Declared in | Demands |
| --- | --- | --- | --- |
| R1 | SDL `operational-service-state` | [scenario SDL L515–525][a-sdl-r1]; [pack SDL L515–525][a-pack-sdl-r1] | "Portable evidence of the qualified Blue availability component for the operational server": `source_class: scenario_state`, window "per-turn", `channel: metric`, `sensitivity: redacted`, `redaction: redact_secrets`, `integrity: checksum`, `loss_disclosure: best_effort` |
| P1 | proposition `operational-service-available` → R1 | [scenario SDL L432–444][a-sdl-p1]; [pack SDL L432–444][a-pack-sdl-p1] | `number` predicate on `availability` of `op-server-0`, `equals 0.0`, unit `reward_component`; read by assertions `operational-service-invariant` and `operational-impact-postcondition` ([L446–456][a-sdl-assertions]) |
| T1 | metric `cage2-cumulative-blue-reward` → `source-ledger:reward-components` | [pack task JSON L19–28][a-json-t1] | "Sum of admitted source reward components projected for the blue participant" |
| T2 | `observation_requirements` → `source-ledger:reward-components` | [pack task JSON L30][a-json-t2] | the reward components observed for the episode |

The run plan sets `max_steps: 2`, the termination ref
`source-ledger:wrapper-termination-cutoff`, seeds 7 and 11, three red variants,
and `target_run_count: 2` ([pack spec JSON L14–31][a-json-spec]).

## 2. Native availability at the pin

| Datum (needed by) | Native source at `26ce1c1` | Class | Ledger basis |
| --- | --- | --- | --- |
| D1 Blue availability component per host per turn (R1, P1, T1, T2) | `HostReward(confidentiality, availability)` from `HybridAvailabilityConfidentialityRewardCalculator` ([`BlueRewardCalculator.py` L54–82][c-blue-calculator]), negating `DistruptRewardCalculator`, which scores each host whose `OTService` process is not running ([`RedRewardCalculator.py` L68–116][c-disrupt]); read through `get_reward_breakdown` ([`EnvironmentController.py` L406–407][c-breakdown]; [`CybORG.py` L332–334][c-cyborg-breakdown]) | available | [row 44][a-ledger-44] `reward-components`, mapped |
| D2 Blue confidentiality component per host per turn (T1, T2) | the same `HostReward`, from `PwnRewardCalculator` ([`RedRewardCalculator.py` L20–65][c-pwn]) | available | [row 44][a-ledger-44] |
| D3 reward totals per turn for Blue, Green, and Red (T1) | `self.reward[agent_name] = reward + self.action[agent_name].cost` ([`EnvironmentController.py` L146–148][c-reward]); `CybORG.get_rewards()` ([`CybORG.py` L320–330][c-get-rewards]); calculators per role in `Scenario2.yaml` ([L77][c-calculator-blue], [L218][c-calculator-green], [L279][c-calculator-red]) | available | [row 44][a-ledger-44] for Blue, [row 45][a-ledger-45] `reward-objectives` for Red; Green has no calculator |
| D4 Blue action cost per turn (T1) | the `action.cost` term in D3; `Restore` costs −1 ([`Restore.py` L38–40][c-restore-cost]), and `Sleep` keeps the base cost 0 ([`Action.py` L21–31][c-sleep-cost]) | available | no ledger row names action cost; the adapter attributes the datum to [row 45][a-ledger-45] `reward-objectives`, whose selector is Red's `HybridImpactPwnRewardCalculator.calculate_reward` |
| D5 `OTService` process state on the operational server (R1) | the true state that `DistruptRewardCalculator` reads ([`RedRewardCalculator.py` L99–109][c-ot-service]) | withheld | [row 19][a-ledger-19] `observation-hidden-truth`, loss-disclosed as [`loss-native-observation-boundary`][a-loss-observation] |
| D6 actions of Blue, Green, and Red per turn | `get_last_action(agent)` ([`CybORG.py` L281–296][c-last-action]) over one ordered turn ([`EnvironmentController.py` L114–169][c-step]) | available | [row 22][a-ledger-22] `control-turn-order`, mapped to the joint-action record; rows 23–31 map the action contracts |
| D7 Blue action success per turn | the native observation `success` flag | lossy | `Remove` reports success even when nothing is removed: [row 25][a-ledger-25], [`loss-remove-success-misreport`][a-loss-remove] |
| D8 source terminal state | `done` comes from `determine_done`, which returns `False` ([`EnvironmentController.py` L184–204][c-done]); `SimulationController` does not override it ([`SimulationController.py` L20–83][c-simulation]) | unavailable | the sim never ends an episode by itself |
| D9 step cutoff | `ChallengeWrapper.max_steps` forces `done` at its bound ([`ChallengeWrapper.py` L28–35][c-wrapper-step]) | available | [row 32][a-ledger-32] `wrapper-termination-cutoff`, loss-disclosed as [`loss-wrapper-cutoff-semantics`][a-loss-cutoff] |
| D10 native observations | role-filtered `Observation` dictionaries | withheld | [row 20][a-ledger-20] `observation-native-shape` (out of scope) and row 19 |

The adapter does not run the pinned `Scenario2.yaml` directly. It constructs
CybORG from a generated translation of the authored SDL that carries the pinned
host values and calculator types ([`scenario.py` L715–785][a-host-facts],
[L912–951][a-agent-facts]), including `AvailabilityValue: High` for
`Op_Server0` ([`Scenario2.yaml` L334–343][c-op-server]).

Two tensions belong to the #85 reconciliation and are recorded here, not
resolved. R1 asks for operational-service state, while the datum the adapter can
carry is D1, a reward penalty derived from the withheld process state D5. D4
has no ledger row of its own, and the adapter attributes it to row 45, whose
selector is Red's calculator rather than the `action.cost` term that produces
the datum (section 3).

## 3. The capture chain today

**Admission.** The researcher `validate`, `run --mode smoke`, and
`run --mode study` commands go through `_task_capture_admission_gaps()`
([`cli.py` L1225–1253][a-gate], [L1277–1278][a-gate-raise]), which returns every
task evidence and observation ref for any manifest because the RAES 3.3.0
observation capability cannot bind a semantic ref to an emitted artifact field.
For this task it returns `source-ledger:reward-components`, so those commands
exit `3` with `researcher.validation.evidence-unverifiable`
([`docs/researcher-command.md` L23–29][a-doc-fail-closed]). The
`reproduce` command ([`cli.py` L1809–1877][a-reproduce-cli]) does not call that
gate.

**Code behind the gate.** Both paths share the episode code:

- The provisioner stages one evaluation turn per accepted aggregate turn. It
  sets the terminal cause to `source-terminal` when the native result is done,
  or `logical-step-limit` at the admitted limit, and publishes the turn only
  for the accepted portable action ([`provisioner.py` L238–306][a-execute-turn]).
- The driver reads `get_rewards()` and `get_reward_breakdown()` for Blue and Red
  on every turn ([`driver.py` L606–630][a-project-evaluation]). It keeps the
  three totals, every host's availability component, each non-zero
  confidentiality component ([L152–215][a-components]), and, when non-zero, a
  Blue `action-cost` component equal to the total minus the components. It
  rejects a turn whose totals do not reconcile ([L218–248][a-action-cost]). It
  tags each host component `source-ledger:reward-components` (row 44) and the
  action-cost component `source-ledger:reward-objectives` (row 45)
  ([L195–203][a-component-row], [L236–247][a-action-cost-row]).
- The evaluator emits one evidence record per participant reward per turn
  (`source-ledger:reward-objectives`), one per component, and one
  terminal-cause record (`source-ledger:wrapper-termination-cutoff`)
  ([`evaluator.py` L741–795][a-evidence]). A component record cites the row
  its component is tagged with ([L763–771][a-component-record]), so
  host-component records cite `source-ledger:reward-components` and action-cost
  records cite `source-ledger:reward-objectives`. Each record's
  `payload_summary` is one string of the form `run=…; episode=…; action=…;
  logical-step:N; participant=…; target=…; meaning=…; value=…; source=….`,
  with its SHA-256 and six source refs ([L797–872][a-evidence-record]). The
  capture spec has one requirement,
  `capture-requirement.cyborg-cage2.reward-fact` ([L874–926][a-capture-spec]).
- `_EVIDENCE_REQUIREMENT_BINDINGS` maps `operational-service-state` to row 44
  for Blue ([`evaluator.py` L67–71][a-bindings]), so P1 evaluates `true` or
  `false` from the latest committed Blue availability component on its subject,
  with an evidence ref and a logical-step context ([L472–502][a-truth],
  [L582–603][a-latest-component], [L633–676][a-observed-truth]).
- Measures: the `cage2-cumulative-blue-reward` score sums the per-turn Blue
  totals and cites the per-step Blue reward records ([L190–246][a-score]). Up
  to three more measures sum the Blue `availability`, `confidentiality`, and
  `action-cost` components ([L93–172][a-component-measures]), each emitted only
  when that Blue component has a retained record ([L175–187][a-component-filter]).
  When present, the `action-cost` measure cites the action-cost records, which
  cite row 45. The packaged Blue policy always selects
  `participant.action-contract.sleep`
  ([`cyborg-blue-sleep-policy.configuration.json` L20][a-blue-sleep]), which
  costs 0 (D4), so packaged runs emit no `action-cost` measure. The task
  defines only the first metric.

**Researcher path, if admitted.** The CLI writes the same per-run files as for
the other researcher backends, including every record in `evidence-records.json`
([`cli.py` L1511–1551][a-cli-episode]). The CybORG episode also carries
proposition-truth and objective results ([`researcher.py` L420–463][a-episode]),
which that path does not write.

**Reproduce path.** `reproduce --phase run` runs each condition through
`execute_episode_series` ([`reproduction.py` L2108–2143][a-condition]). Per
attempt it writes `evidence-NNN.json.gz` chunks that hold only the records some
measure cites, `episode-summary.json.gz` with measures, proposition truth,
objective results, and diagnostics, and `evidence-index.json`
([L1698–1788][a-reproduce-evidence]). Terminal-cause, Green, and Red records are
not retained there. The run's evidence artifact sets `satisfies_refs` to
`operational-service-state` and `source-ledger:reward-components` before
`validate_experiment_run_against_task()` runs ([L1790–1821][a-satisfies]). The
[claim guardrails](capability-and-evidence-claim-guardrails.md#keep-four-claims-distinct)
say a generic evidence concept must not be placed in `satisfies_refs` until a
published RAES contract can validate the artifact-and-field witness, and #85's
scope includes removing hardcoded satisfaction claims.

| Req | Declared ref in `runtime_plans.py` | Manifest declaration | Emitted artifact or field | Gap |
| --- | --- | --- | --- | --- |
| R1 | none; `cage2_evaluation_plan()` declares `source-ledger:reward-components` for a confidentiality predicate on `provision.node.user-host` ([L63–74][a-plans]), used by the conformance probe ([`conformance.py` L561–564][a-probe-plan]) and as the researcher fallback when the compiled SDL plan is empty ([`researcher.py` L339–341][a-fallback]) | no `observation` capability ([`manifest.py` L315–366][a-capability-set]); evaluator `supported_evidence_channels` is `{"api_response"}`, not `metric` ([L224][a-channels]) | `meaning=availability` records per host per turn, in `evidence-records.json` or `evidence-NNN.json.gz` | the value sits in free text; no declaration names R1's fields; the CLI path fails closed and the reproduce path asserts R1 through `satisfies_refs` |
| P1 | none | evaluator `supported_predicate_families` is `{"number"}` ([L221][a-predicates]) | truth result in the runtime snapshot; written only to `episode-summary.json.gz` | the truth result is not an R1 record, and the CLI path does not write it |
| T1 | `source-ledger:reward-components` in the fallback plan only ([L71][a-plans-ref]) | evaluator `supports_scoring` and constraint `score_semantics` ([`manifest.py` L213–237][a-evaluator]) | score measure in `derived-measures.json` or `episode-summary.json.gz`, citing per-step Blue reward records | recomputable from per-step records, but those cite `source-ledger:reward-objectives`, not the task's ref |
| T2 | as T1 | as R1 | as R1 | as R1 |

**What RAES 3.3.0 can express.** As recorded for NASim, the pinned
`ObservationCapabilities` declares capture kinds, channel kinds, evidence
contracts, media types, sealing modes, and three support flags
([`capabilities.py` L144–157][r-observation]), and
`ExperimentEvidenceSatisfactionReferenceModel` names a satisfied concept by
reference only ([`experiment_manifest_references.py` L187–196][r-satisfies]).
Neither can state which artifact field carries a requirement or its
data-quality state. A field-level witness needs
[OpenRAE/rae#1239][r-pr-1239]. RAES 4.1.0 and later include it; this
repository still pins 3.3.0.

## 4. Equivalence data needs

The public evaluator runs 100 episodes for each trial length (30, 50, 100) and
red agent (`B_lineAgent`, `RedMeanderAgent`, `SleepAgent`), records each step's
Blue and Red action strings, and reports the mean and standard deviation of
the per-episode total reward ([`evaluation.py` L58–91][c-evaluation]).

| Need | Today | Evidence |
| --- | --- | --- |
| Action | partly present | Green and Red action contracts become behavior-history events, and a joint-action record orders Blue, Green, and Red, both in the runtime snapshot ([`participant_runtime.py` L760–822][a-portable-turn], [L1104–1146][a-joint-action]). Neither path writes them, while the public evaluator logs each step's Blue and Red actions. |
| Outcome | partly present | Per-turn totals and components are captured. Blue action success is projected ([`driver.py` L569–604][a-project-turn]) but not written, and D7 is lossy. |
| Observation | missing | Lossy envelopes are held in memory ([`participant_runtime.py` L825–907][a-observations]); native observations stay private (D10). |
| Availability | present | Every host's Blue availability component is captured per turn (D1); the process state behind it stays withheld (D5). |
| Termination or cutoff cause | partly present | The CLI path writes one terminal-cause record per run; the reproduce path drops it. Only `logical-step-limit` can occur, because the sim never sets `done` (D8). |
| RNG and stochastic control | partly present | Construction and reset bind Python `random` and `CybORG.set_seed` and keep one stream per session ([`driver.py` L426–501][a-random]). The NumPy and Gym action-space streams listed in `qualification.json` are not bound by the driver; the public evaluator binds no stream ([row 40][a-ledger-40], [`loss-evaluation-seed-unbound`][a-loss-seed]). |
| Evaluator | present for T1 | The score and component measures exist; the condition mean and standard deviation map to [row 43][a-ledger-43] `evaluation-derived-measures`. |
| Lineage | present per record | Each record cites its source row, episode, action instance, logical step, derivation, and profile at the source commit ([`evaluator.py` L822–841][a-source-refs]). |

## 5. Regression-fixture design (spec only)

Nothing in this section is implemented. It specifies the fixtures that the
implementation resuming after the hold would add to meet #85's criterion that
tests exercise the complete requirement-to-capability-to-artifact chain and fail
on missing or falsely claimed data. Each chain reads requirement → native source
→ manifest declaration → artifact field.

- **Hermetic** means an injected driver such as `FakeExecutionDriver`
  ([`tests/test_cyborg_execution.py` L98–202][a-fake-driver]) or `StudyDriver`
  ([`tests/test_cyborg_reproduction.py` L54–141][a-study-driver]).
- **Native** means the pinned CybORG source install recorded in
  `qualification.json`. The pytest suite does not import it; CI installs it
  only in the temporary environment of `tools/verify_cyborg_qualification.py`,
  which the `tests` session runs for the `cyborg` extra
  ([`noxfile.py` L487–488][a-nox-qualification];
  [`docs/maintainers/ci.md` L90–93][a-ci-native]).
- That script is the existing native seam. It clones cage-challenge-2 at
  `26ce1c1`, installs the patched CybORG wheel and the adapter wheel in that
  environment, and runs a seeded native smoke
  ([`verify_cyborg_qualification.py` L534–829][a-verify]). Its adapter smoke
  then runs one `Restore` turn through the real
  `SourceInstalledCyborgDriver` and asserts that turn's exact totals and
  components, including the Blue `action-cost` component tagged
  `source-ledger:reward-objectives` ([L257–323][a-adapter-smoke]). It checks
  the committed facts the evaluator consumes, not evidence records or artifact
  fields. F5 extends this seam.
- Until a RAES contract can express the witness, the existing fail-closed test
  ([`tests/test_claim_integrity.py` L143–154][a-claim-test]) remains the guard for
  the CLI path. No test asserts the reproduce path's `satisfies_refs` today.

| Fixture | Chain | Positive case | Negative cases | Lane |
| --- | --- | --- | --- | --- |
| F1 availability series | R1 → D1 per host per turn → a `metric` channel capture declaration → a per-turn series member with logical step, target, component, value, and source row, bound by SHA-256 from an evidence record that names `operational-service-state` | one availability value per host per committed turn; P1's truth equals its predicate applied to the latest `op-server-0` value | missing datum: one turn lacks the operational server's value, and the run must end without a sealed success. False claim: an artifact names R1 in `satisfies_refs` without a declared member carrying R1's fields, as the reproduce artifact does today over free-text records, and validation must reject it. Leak: a native hostname or process record in the member fails the leakage scan. | hermetic |
| F2 reward components | T1 and T2 → D1, D2, D4 per turn → the same declaration → per-turn component members | per-turn components plus action cost equal the Blue total, and the score equals the sum of totals | a total that differs from its components; a non-zero confidentiality component that is missing; a measure citing records from a row other than its datum's ledger basis in section 2, as two measures do today: the score, whose per-step Blue records cite row 45 rather than row 44 (the T1 gap above), and the `action-cost` measure after a costed Blue action such as `Restore`, whose records cite row 45 (D4) | hermetic |
| F3 termination | run plan cutoff → D9 and the adapter's step counter → a per-run terminal-cause field kept by every path | `logical-step-limit` at the admitted limit | `source-terminal` reported in the sim, which the source cannot produce; a run sealed without a terminal cause | hermetic |
| F4 joint actions | D6 → the joint-action records → a written per-turn action member | one record per committed turn, ordered Blue, Green, Red | a `Remove` success presented as an observed state change; a turn with no record | hermetic |
| F5 native shapes | the F1–F4 chain over the real driver. It extends the qualification adapter smoke, which checks one `Restore` turn's committed facts on a one-host scenario with the `sleep` red variant, to whole episodes and the F1–F4 artifact fields | one seeded episode per red variant records the real per-turn shapes once, so the hermetic fakes stay faithful | not applicable | native |

## 6. Related records

- [Capability and evidence-claim integrity guardrails](capability-and-evidence-claim-guardrails.md),
  from issue #84.
- [CybORG/CAGE-2 source-ledger guardrails](cyborg-cage2-source-ledger-guardrails.md),
  [CybORG reward, objective, and outcome projection guardrails](cyborg-evaluation-projection-guardrails.md),
  [CybORG researcher run-and-evidence command guardrails](cyborg-researcher-command-guardrails.md),
  and [CybORG/CAGE-2 protocol-reproduction guardrails](cyborg-cage2-protocol-reproduction-guardrails.md).
- The packaged mapping ledger: [`README.md`][a-mapping-readme],
  [`cage2-source-ledger.jsonl`][a-ledger] (47 rows), and
  [`cage2-loss-disclosures.md`][a-losses] (six entries). This page cites them
  and does not edit them.

## How this was checked

- Adapter files were read at `0272949`. The two cited RAES files were read at
  tag `v3.3.0` ([`fb8a23a`][r-commit]) and matched the same files in the
  `raes-3.3.0` wheel from PyPI.
- Native files were fetched from cage-challenge-2 at `26ce1c1` through the
  GitHub API. The cited files listed in `qualification.json` `selected_files`
  matched their recorded SHA-256. `CybORG.py`,
  `Simulator/SimulationController.py`, and `Shared/Actions/Action.py` are not
  in that list and were read at the commit.
- No native CybORG episode was run for this page.

[a-commit]: https://github.com/OpenRAE/adapters/tree/0272949fa964920a7e06fb56f6d7051054756b5b
[a-pyproject-raes]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L36
[a-pyproject-cyborg]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/pyproject.toml#L56
[a-qualification]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/qualification.json
[a-patch]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/cage2-wheel-package-data.patch
[a-sdl-r1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/scenario/cage2-scenario2.sdl.yaml#L515-L525
[a-pack-sdl-r1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/examples/cage2-research/sdl/cage2-research.sdl.yaml#L515-L525
[a-sdl-p1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/scenario/cage2-scenario2.sdl.yaml#L432-L444
[a-pack-sdl-p1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/examples/cage2-research/sdl/cage2-research.sdl.yaml#L432-L444
[a-sdl-assertions]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/scenario/cage2-scenario2.sdl.yaml#L446-L456
[a-json-t1]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/examples/cage2-research/experiment/cage2-research.task.exp.json#L19-L28
[a-json-t2]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/examples/cage2-research/experiment/cage2-research.task.exp.json#L30
[a-json-spec]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/examples/cage2-research/experiment/cage2-research.spec.exp.json#L14-L31
[a-host-facts]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/scenario.py#L715-L785
[a-agent-facts]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/scenario.py#L912-L951
[a-plans]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/runtime_plans.py#L63-L74
[a-plans-ref]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/runtime_plans.py#L71
[a-probe-plan]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/conformance.py#L561-L564
[a-fallback]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/researcher.py#L339-L341
[a-episode]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/researcher.py#L420-L463
[a-blue-sleep]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/examples/cage2-research/participant/cyborg-blue-sleep-policy.configuration.json#L20
[a-capability-set]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/manifest.py#L315-L366
[a-evaluator]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/manifest.py#L213-L237
[a-predicates]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/manifest.py#L221
[a-channels]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/manifest.py#L224
[a-execute-turn]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/provisioner.py#L238-L306
[a-components]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/driver.py#L152-L215
[a-component-row]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/driver.py#L195-L203
[a-action-cost]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/driver.py#L218-L248
[a-action-cost-row]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/driver.py#L236-L247
[a-random]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/driver.py#L426-L501
[a-project-turn]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/driver.py#L569-L604
[a-project-evaluation]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/driver.py#L606-L630
[a-bindings]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L67-L71
[a-component-measures]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L93-L172
[a-component-filter]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L175-L187
[a-score]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L190-L246
[a-truth]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L472-L502
[a-latest-component]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L582-L603
[a-observed-truth]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L633-L676
[a-evidence]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L741-L795
[a-component-record]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L763-L771
[a-evidence-record]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L797-L872
[a-source-refs]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L822-L841
[a-capture-spec]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/evaluator.py#L874-L926
[a-portable-turn]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/participant_runtime.py#L760-L822
[a-observations]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/participant_runtime.py#L825-L907
[a-joint-action]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/participant_runtime.py#L1104-L1146
[a-reproduce-evidence]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/reproduction.py#L1698-L1788
[a-satisfies]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/reproduction.py#L1790-L1821
[a-condition]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/reproduction.py#L2108-L2143
[a-gate]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1225-L1253
[a-gate-raise]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1277-L1278
[a-cli-episode]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1511-L1551
[a-reproduce-cli]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cli.py#L1809-L1877
[a-doc-fail-closed]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/researcher-command.md?plain=1#L23-L29
[a-fake-driver]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_cyborg_execution.py#L98-L202
[a-study-driver]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_cyborg_reproduction.py#L54-L141
[a-nox-qualification]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/noxfile.py#L487-L488
[a-ci-native]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/docs/maintainers/ci.md?plain=1#L90-L93
[a-verify]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tools/verify_cyborg_qualification.py#L534-L829
[a-adapter-smoke]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tools/verify_cyborg_qualification.py#L257-L323
[a-claim-test]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/tests/test_claim_integrity.py#L143-L154
[a-mapping-readme]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/README.md
[a-ledger]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl
[a-ledger-19]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L19
[a-ledger-20]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L20
[a-ledger-22]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L22
[a-ledger-25]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L25
[a-ledger-32]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L32
[a-ledger-40]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L40
[a-ledger-43]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L43
[a-ledger-44]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L44
[a-ledger-45]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-source-ledger.jsonl#L45
[a-losses]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-loss-disclosures.md
[a-loss-observation]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-loss-disclosures.md?plain=1#L20-L29
[a-loss-remove]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-loss-disclosures.md?plain=1#L31-L38
[a-loss-cutoff]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-loss-disclosures.md?plain=1#L40-L48
[a-loss-seed]: https://github.com/OpenRAE/adapters/blob/0272949fa964920a7e06fb56f6d7051054756b5b/src/raes_adapters/cyborg/mapping/cage2-loss-disclosures.md?plain=1#L50-L58
[c-commit]: https://github.com/cage-challenge/cage-challenge-2/tree/26ce1c1253fa9e2e73f25e6a7f2da32860c11257
[c-blue-calculator]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/BlueRewardCalculator.py#L54-L82
[c-pwn]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/RedRewardCalculator.py#L20-L65
[c-disrupt]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/RedRewardCalculator.py#L68-L116
[c-ot-service]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/RedRewardCalculator.py#L99-L109
[c-step]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/EnvironmentController.py#L114-L169
[c-reward]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/EnvironmentController.py#L146-L148
[c-done]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/EnvironmentController.py#L184-L204
[c-breakdown]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/EnvironmentController.py#L406-L407
[c-last-action]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/CybORG.py#L281-L296
[c-get-rewards]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/CybORG.py#L320-L330
[c-cyborg-breakdown]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/CybORG.py#L332-L334
[c-simulation]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Simulator/SimulationController.py#L20-L83
[c-wrapper-step]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Agents/Wrappers/ChallengeWrapper.py#L28-L35
[c-restore-cost]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/Actions/AbstractActions/Restore.py#L38-L40
[c-sleep-cost]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/Actions/Action.py#L21-L31
[c-calculator-blue]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/Scenarios/Scenario2.yaml#L77
[c-calculator-green]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/Scenarios/Scenario2.yaml#L218
[c-calculator-red]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/Scenarios/Scenario2.yaml#L279
[c-op-server]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Shared/Scenarios/Scenario2.yaml#L334-L343
[c-evaluation]: https://github.com/cage-challenge/cage-challenge-2/blob/26ce1c1253fa9e2e73f25e6a7f2da32860c11257/CybORG/CybORG/Evaluation/evaluation.py#L58-L91
[r-commit]: https://github.com/OpenRAE/rae/tree/fb8a23aee827f5c45ea6e736bc06b45f90671472
[r-issue-1023]: https://github.com/OpenRAE/rae/issues/1023
[r-issue-1112]: https://github.com/OpenRAE/rae/issues/1112
[r-pr-1239]: https://github.com/OpenRAE/rae/pull/1239
[r-observation]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_backend_protocols/capabilities.py#L144-L157
[r-satisfies]: https://github.com/OpenRAE/rae/blob/fb8a23aee827f5c45ea6e736bc06b45f90671472/implementations/python/packages/raes_contracts/contracts/experiment_manifest_references.py#L187-L196
