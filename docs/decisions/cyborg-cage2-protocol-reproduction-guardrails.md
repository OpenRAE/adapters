# CAGE-2 protocol-reproduction guardrails

GitHub issue #22 is the authority for this requirement-free deliverable. This
note fixes the ownership, evidence, security, persistence, statistical, and
claim boundaries for CAGE Challenge 2 protocol reproduction. It
defines no RAES contract, adapter protocol, reusable study schema, or
implementation plan.

## Generated evidence, not repository content

The adapter writes a reproduction bundle only to the fresh, explicit output
directory selected by the operator. Generated study data is not checked into
this repository, packaged in the distribution, or bound to a downstream
repository or filesystem location. Research projects and archives independently
own retention and publication after validating an exported bundle.

Each completed output is immutable. Changed inputs, methods, tolerances,
agents, or results require a fresh output directory; a rerun never rewrites an
accepted result. The issue-named JSON files are operational indexes and
projections for the generated study, not new portable schema families. They do
not carry adapter-defined schema names or versions; the frozen revision and
declaration digest identify the one study selection. Embedded RAES artifacts
remain exact published models and are validated by their owners.

Generated evidence is not `ControlPlaneStore` state, an adapter database, a
replay cache, package data, or a release artifact. The adapter records no
retention destination or path reference.

## Freeze distinct source facts before execution

Do not flatten the cited sources into one alleged upstream protocol. The
checked-in qualified `evaluation.py` row records 100 episodes, trial lengths
30/50/100, the three Red variants, and no seed binding. The paper reports 1,000
episodes for every Red-agent/trial-length pairing, while the qualified README
evidence records the validation seed statement `random.seed(153)`. The frozen
oracle must identify which source supports each matrix or method field and must
retain the disagreements and `loss-evaluation-seed-unbound`.

In particular, a seed value is not a seed policy. `protocol.json` must freeze
the stream owner, API, initialization scope (study, condition, attempt, or
episode), ordering, and reset behavior supported by the source. Repeating
per-episode `RunControls(seed=153)` is not equivalent to one batch-level
`random.seed(153)` call. Parallel execution is permitted only when the frozen
stream/order semantics remain unchanged. Simulator, Python, NumPy, wrapper,
Red, Green, Blue-policy, and evaluator streams stay distinct; unsupported or
unbound streams weaken the result.

Every selected Blue baseline requires immutable implementation identity,
source/artifact digests, admitted participant manifest/selection/configuration,
and any model/configuration bytes it needs. The current packaged Blue Sleep
selection is the only complete external Blue implementation in this repository.
The qualified `BlueLoadAgent` fallback has no bound model artifact and must not
be presented as the published policy or silently replaced by Sleep. A baseline
without a complete public closure is predeclared as excluded, with the
exclusion retained in the schedule and source ledger.

`source-ledger.json` is a frozen projection joining the existing qualification,
mapping ledger, loss disclosures, pack/scenario identities, and additional
paper/leaderboard sources needed by this study. It must cite and digest those
owners rather than copy `cage2-source-ledger.jsonl` into a second mapping
authority. Source bytes are not fetched during aggregation, and a URL without
a revision/content digest is not an immutable input.

## Compose the canonical owners

| Concern | Canonical incumbent and required boundary |
| --- | --- |
| Source admission | `qualification.json`, `CAGE2_SOURCE_26CE1C1`, `load_qualification()`, `load_source_ledger()`, `load_loss_disclosures()`, `validate_all()`, `verify_selected_cyborg_source()`, and the qualified source-tree/file/module-origin checks. Extend the evidence selection for genuinely new primary sources; do not add a second qualification record or permissive source loader. |
| Authored scenario and pack | `src/raes_adapters/cyborg/scenario/cage2-scenario2.sdl.yaml`, its byte-identical packaged `cage2-research` snapshot, the RAES module lock and canonical digest APIs, `raes-env-packs` validation, and the associated-artifact manifest/set digest. Use the same authored bytes for both execution lanes; do not author a reproduction-only SDL. |
| Experiment and participant controls | Published `ExperimentSpecModel`, `ExperimentTaskModel`, episode/red-variant/stochastic-control models, participant manifest/selection/configuration models and validators, `RunControls`, and the researcher CLI's exact digest/binding admission. Matrix membership is frozen data, not target defaults or environment configuration. |
| Target and execution | `create_cyborg_target()`, `_normalized_config()`, `_validate_selection()`, `RuntimeManager`, `RuntimeControlPlane`, `CyborgProvisioner`, `CyborgOrchestrator`, `CyborgParticipantRuntime`, `ReferenceTimeRuntime`, and `SourceInstalledCyborgDriver`. Preserve one admitted Blue action to one serialized aggregate turn, quarantine after an unprojectable mutation, and verified cleanup. |
| Evaluation and evidence | `CyborgEvaluator`, its committed per-step reward evidence and cumulative Blue-score `ExperimentDerivedMeasureModel`, RAES objective/truth/evidence/capture models, and `validate_experiment_run_against_task()`. Upstream score, RAES objective truth, participant outcome, conformance, and equivalence remain separate. |
| Run/study projection | `raes_adapters.cyborg.researcher`, `_researcher_support.build_archival_run()`, the published run/study models, and their cross-artifact validators. Canonical RAES records are emitted for evidence-complete runs; the operational run inventory retains every attempt, including those that cannot be sealed as a successful RAES run. |
| Diagnostics and failures | RAES `Diagnostic`/`DiagnosticModel`, `diagnostic_model()`, `diagnostic_payload()`, the CLI's stable `_CommandFailure` exit mapping, `redact_native_value()`, and `bounded_context_label()`. Add no exception hierarchy or reproduction error envelope. |
| Persistence | Exclusive mode-`0700` output reservation, safe run labels, `raes_operations.run_artifacts.atomic_write_json_artifact()`, relative artifact names, SHA-256 inventory entries, and inventory-last sealing. The atomic writer prevents partial files but does not prevent replacement; exclusive directory creation and frozen-revision policy supply that guarantee. |
| Conformance | The exact published `BackendConformanceReport`, report projector/writer, CybORG local diagnostics, declared weaknesses, and `_conformance_support` evidence-closure helpers. Conformance may be cited but is never copied into an equivalence case family or used as a score-similarity result. |
| Reference path | `raes_processor.reference.ReferenceProcessor.realize()`, the live manifest, published planning/runtime models, and `RuntimeControlPlane` gates. Report exactly the authored/contract/control surfaces this path exercises; do not relabel the reference processor as a CybORG simulator or synthesize native state and outcomes. |
| Repository workflow | The single `pyproject.toml`/`uv.lock`, existing `raes-adapters` console entry point, `_verification_envs()`, tests, clean-install distribution probes, strict docs/policy gates, `.github/workflows/ci.yml`, `PR Gate`, and canonical Nox graph. Extend these incumbents instead of adding a second command package, workflow, or verification graph. |

The current CLI's native batch is useful for admission, execution, projection,
and sealing, but its fail-fast list comprehension and success-only run records
are not the issue #22 scheduler. Reuse its lower-level owners and persistence
rules; do not call a failed batch complete or duplicate the entire CLI. The
current hermetic conformance suite's seed 153 is likewise conformance evidence,
not a native evaluation run.

## Immutable schedule and attempt lifecycle

Separate a logical schedule slot from an execution attempt. The frozen slot
identifies the condition, expected ordinal, source-backed controls, and
predeclared eligibility. Every attempt has a never-reused run id and points to
one slot. A retry receives a new run id and an explicit predecessor/slot link;
the original terminal record remains immutable.

Every scheduled slot and attempt ends in exactly one issue-defined terminal
disposition:

- `valid`: execution, evidence validation, and required cleanup completed, and
  the attempt is eligible under the frozen inclusion rule;
- `invalid`: execution returned but protocol, evidence, artifact, or validation
  requirements were not satisfied;
- `failed`: execution, timeout, process, projection, persistence, or required
  cleanup failed before valid evidence could be sealed; or
- `excluded`: a predeclared source/apparatus/eligibility rule says the slot is
  not run or not eligible.

These dispositions are not participant outcomes or score quality. Failure and
exclusion reasons use closed, stable codes and evidence references, never
native exception text. The retry limit and deterministic attempt-selection rule
(for example, first valid attempt in attempt order) are frozen before execution
so retries cannot become score-based optional stopping. Aggregates retain counts
for every disposition and never impute, delete, or overwrite an attempt.

Because the source execution unit is one retained native session per condition,
a failed condition session terminally fails that attempt for every slot in the
condition. The one predeclared retry restores the condition's ordered-stream
checkpoint and allocates a new predecessor-linked run id to every slot. If the
retry also fails, its terminal records remain and the scheduler still attempts
every later independent condition; it never turns one condition failure into
fabricated attempts for the rest of the matrix.

Reserve the per-attempt directory before native construction and seal its
inventory last. An interrupted or unsealed attempt is failed, not absent. A
parent process crash must be recoverable by comparing the immutable schedule to
the retained attempt directories; recovery creates new attempt ids and does not
resume or append to an old directory.

The source evaluator retains one native session per condition and resets it
between episodes, so the adapter does the same without reseeding the
study-scoped random stream. Each slot is still a distinct RAES experiment run:
its portable snapshot begins from the pristine realized baseline and never
inherits lifecycle, action, observation, or evaluation history from the prior
slot. Native-session continuity and portable evidence isolation are separate
invariants.

## One evidence closure and one aggregation implementation

The eligible scalar score is the validated cumulative Blue reward already
projected by `CyborgEvaluator` from committed per-step RAES evidence. Do not
recompute it from a native reward vector, stdout, a private evaluator object, or
free-form summary. The aggregate reader accepts only sealed per-attempt
inventories, validates embedded RAES records, verifies file digests and
slot/attempt joins, and selects attempts through the frozen rule.

Each run retains the exact transitive RAES evidence closure referenced by its
published derived measures. Unreferenced runtime telemetry is not research
evidence for this protocol and is omitted rather than bulk-archived; the
offline verifier rejects both a missing referenced record and an unrelated
extra record. This keeps the public bundle tied to the declared measurements
without weakening per-step component and score traceability.

`protocol.json` must predeclare the estimator, two-sided 95% confidence-interval
method, sample-variance convention, finite-value policy, critical-value method,
rounding/display rule, minimum eligible count, retry/inclusion treatment,
tolerances, and exact/bounded/failed reproduction criteria. A paper table that
prints intervals is not evidence of an unstated formula. If the published
method cannot be established, the study method is explicitly adapter-study
methodology and the tier/claim is weakened rather than reverse-engineered from
reported numbers.

One pure aggregation function owns both initial `aggregates.json` production
and clean-environment recomputation. It reads only immutable retained run
evidence plus the frozen protocol, uses a deterministic ordering and JSON
projection, and reports eligible `n` plus every terminal-disposition count per
condition. Tests must recompute after shuffled directory enumeration and reject
missing, duplicate, non-finite, digest-drifted, cross-condition, or post-freeze
inputs. Do not maintain separate “runner” and “validator” formulas.

Published and observed tables remain separately identified. Numerical equality
or tolerance membership may support only the predeclared exact/bounded/failed
reproduction classification. It does not establish contract conformance,
state/observation equivalence, backend identity, deterministic replay, or
scientific reproducibility.

## Equivalence tiers and reference-backend separation

`tiers.json` contains exactly the issue's six review tiers: `authored-source`,
`contract`, `execution-control`, `state/observation`, `outcome/evaluation`, and
`disclosure`. `disclosure` is an issue-local evidence-completeness tier; do not
add it to the existing source-ledger loss vocabulary merely to reuse its parser.

For each tier, keep CybORG and the RAES reference path as separately identified
subjects with one `pass`, `fail`, or `weakened` result, the predeclared rule,
and machine-resolvable evidence/loss references. Unsupported reference-runtime
facts produce `weakened`; they are never filled with CybORG observations,
published scores, zeros, or synthetic success. A failure in one subject does
not overwrite the other, and there is no bundle-wide boolean `passed`.

Known losses constrain attainable results. The native-observation boundary,
Remove misreport, wrapper-cutoff ambiguity, evaluator seed gap, and unbound
Blue policy remain visible even when a run succeeds. Acceptance requires honest
tier results, not six passes. The report's final claim is the strongest claim
supported by the weakest applicable evidence closure and must repeat the
explicit non-claims from issue #22.

## Security and whole-repository path

The design passes every applicable layer below before evidence is published:

| Layer | Required treatment |
| --- | --- |
| Authentication and authorization | This is a local, offline command and adds no controller, route, daemon, remote caller, or credential flow. Participant authority still comes from admitted participant selections and runtime/control-plane gates. Any later service must use `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`; no adapter endpoint is permitted. |
| Secret and policy-material surface | The public study requires no secret. Do not read secret stores or `.env`, add token options, resolve private provider artifacts, or expose credentials, learned sessions, governed entropy, private model weights, or secret references. Only reviewed public baseline bytes may be selected. |
| CLI and configuration shape | Keep the closed `argparse` choices, safe-label rules, exact matrix/source ids, and `_normalized_config()` / `_validate_selection()` authority. Operational output path and bounded worker count cannot change source identity, matrix membership, seed scope, participant implementation, profile/corpus roots, driver class, or claim criteria. Unknown keys and hidden defaults fail before native construction. |
| Pack, source, and static parsers | Run `raes-env-packs` validation and digest joins; strict duplicate-key JSON; RAES SDL parsing, lock/import verification, instantiation, compilation, and canonical digest; published experiment/participant models; qualification/source-ledger checks; and confined source/module-origin verification. No permissive YAML/JSON parser, floating ref, arbitrary import path, runtime fetch, or working-directory discovery is admission. |
| Runtime validation | Keep `RuntimeTarget` manifest/component/signature checks, `RuntimeManager`/`RuntimeControlPlane` plan and snapshot-transition gates, workflow/time/participant/action/observation/evaluation validators, terminal separation, session quarantine, and verified cleanup. Backend checks add only the selected CybORG mapping. |
| Native and disclosure boundary | Native state, hidden truth, observations, sessions, action ids/classes, reward mappings/vectors, raw logs, object representations, random states, and full tracebacks stay private. Build allowlisted RAES projections before serialization; hashing or redacting an arbitrary native dump does not make it portable. |
| Error envelopes | Use validated RAES diagnostics and the existing stable command exit classes/messages. Do not serialize Pydantic rejected values, exception strings/types/causes, stdout/stderr, host paths, argv/environment mappings, or traceback text. Cleanup failure is retained independently from the primary failure. |
| OS/process exposure | Resolve all inputs beneath explicit roots; reject absolute/traversing paths, existing targets, symlinks, and unsafe run ids; use mode-`0700` directories and argument-vector invocation. If attempts use subprocess isolation, reuse the qualification tool's explicit working directory, environment allowlist, cleared `PYTHONPATH`, safe-path behavior, timeout, bounded output handling, and no shell interpolation or runtime network access. Native stdout/stderr is suppressed, not retained. |
| Logging and observability | Portable observability is validated RAES evidence, stable diagnostics, terminal dispositions, counts, digests, provenance, limitations, and relative inventories. Logging is limited to safe operation names, public ids/pointers, counts, and dispositions; never log inputs, paths, actions, rewards, native/random state, policy material, or exceptions. |
| Persistence and publication | Validate before atomic write, reserve roots exclusively, retain failed attempts, use only relative references, seal inventories last, and verify all digests before aggregation. Public export requires leakage scans over actual persisted bytes. No overwrite/force/resume/append path exists. |
| Packaging and repository policy | Keep one distribution and lock. Generated run evidence remains outside the checkout and distribution. Keep individual exported records bounded rather than creating a monolithic native/result dump, and keep the existing CI/Nox/policy/docs/distribution graph authoritative. |

`environment.json` records bounded platform, Python, distribution, qualified
source, adapter, RAES, pack, study/protocol, and method identities. It is not an
environment-variable or argv dump and must not include hostnames, usernames,
absolute paths, caches, installed-package metadata unrelated to the study, or
provider logs.

## Extension seam and workflow boundary

The extension seam is one immutable reproduction selection: frozen revision,
source/pack/scenario/participant identities, an ordered matrix of condition and
slot ids, seed-allocation policy, failure/attempt-selection policy, statistical
method, tolerances, and claim rules. Backend-local executor callables remain in
`raes_adapters.cyborg`; this is not a new `raes_adapters.base` protocol. A new
public Blue baseline or future source revision adds a new admitted selection and
fresh output without editing an accepted protocol or hard-coding another
branch for trial length or Red policy.

Tests use reduced cardinalities and injected/hostile drivers but exercise the
same scheduler, terminal-disposition, retry, sealing, aggregation, tier, and
leakage code. They do not relabel hermetic evidence as native. The complete
native matrix is an explicit qualified-source acceptance run, not a PR-unit-test
loop or the existing weekly hermetic conformance suite. If CI later runs it, use
the existing workflow and label it as non-PR native reproduction; a new required
job must be added to `PR Gate`.

Before acceptance, run relevant targeted tests, the qualified native command in
the admitted environment, clean-environment aggregate recomputation, and the
canonical graph:

```shell
uv tool run --from 'nox[uv]==2026.4.10' nox -s verify -- --skip-requirement
```

The committed pack currently remains `status: built` with
`reference_triangle: false`. Reproduction evidence may support a later reviewed
status change, but implementation must not mark the pack golden or mutate that
publication claim automatically.

## Gotchas and anti-patterns

- Do not conflate the 100-episode checked-in evaluator default, the paper's
  1,000-episode evaluation, and the frozen adapter study.
- Do not turn `random.seed(153)` into 1,000 identical per-episode resets or call
  it complete stochastic control.
- Do not use the current external Blue Sleep selection as a substitute for
  `BlueLoadAgent`, submitted agents, or missing model weights.
- Do not drop failed slots, overwrite retries, choose the best attempt, or tune
  exclusions/tolerances/CI methods after seeing scores.
- Do not aggregate unsealed summaries or native output; use validated per-run
  derived measures and inventories.
- Do not equate score similarity with conformance, objective truth, semantic
  equivalence, or backend identity.
- Do not turn tier results into conformance cases, source-ledger dispositions,
  manifest capabilities, or one aggregate pass flag.
- Do not let the reference path fabricate CybORG observations, stochastic
  transitions, rewards, terminal causes, or cleanup facts.
- Do not duplicate the source ledger, RAES models/validators, evaluator score
  calculation, CLI failure hierarchy, artifact writer, inventory logic,
  conformance projector, or CI workflow.
- Do not check generated study output into this repository or encode a
  downstream repository or filesystem location in adapter code or metadata.

## Non-goals and implementation boundaries

- No deterministic replay, backend identity, exact native state/observation
  equality, or scientific reproducibility claim beyond retained evidence.
- No training, leaderboard service, submitted-agent reconstruction, private
  model acquisition, web UI, API, daemon, scheduler service, or authentication
  system.
- No new RAES/environment-pack SDL, schema, vocabulary, profile, fixture
  corpus, evidence type, metric meaning, backend protocol, diagnostic envelope,
  exception hierarchy, repository/store, or policy gate.
- No runtime clone/download, floating source, editable install, unpublished
  behavioral patch, arbitrary plugin/import, or second distribution/lock.
- No native hidden truth, observation payload, action id/class, reward vector,
  raw log, credential, object representation, host path, environment/argv dump,
  or full traceback in the public bundle.
- No change to the qualified source defects, loss disclosures, upstream score
  calculation, authored Scenario2 semantics, or existing conformance claim merely
  to make the reproduction pass.
