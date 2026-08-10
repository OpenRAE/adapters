# CyberBattleSim baseline-reproduction guardrails

GitHub issue #30 is the authority for this deliverable. This note fixes the
repository-wide boundaries for the frozen source-native/RAES comparison bundle.
It defines no RAES contract, scientific equivalence vocabulary, simulator
profile, or implementation plan.

## One frozen study artifact, two execution lanes

The issue-mandated
`packages/cyberbattlesim_adapter/reproduction/<frozen-revision>/` coordinate is
a checked-in, consumer-facing **data** boundary for OpenRAE/research#14 and #20.
It is not a Python package, import root, distribution, environment pack,
runtime store, or second adapter. Do not add `pyproject.toml`, `__init__.py`, a
lockfile, executable source, or native simulator content beneath that path.
The one `raes-adapters` distribution and all executable CyberBattleSim behavior
remain under `src/raes_adapters/cyberbattlesim`; the external environment pack
remains under `environments/cyberbattlesim-chain`.

The source-native and RAES-mediated lanes share only immutable selection,
metric definitions, attempt identities, terminal-disposition rules, and
post-run analysis. Their execution paths remain deliberately distinct:

- The source-native lane executes the pinned
  `notebooks/notebook_withdefender.py` selection through the pinned upstream
  `epsilon_greedy_search` path before adapter normalization. It must first
  reuse the complete source/distribution/tree/module-origin admission checks.
  It must not call `CyberBattleSimDriver`, RAES action admission, the adapter
  evaluator, or a copied/reimplemented notebook loop and call that native.
- The mediated lane uses the exact admitted external pack and participant
  artifacts, `CyberBattleSimDriver`, `create_cyberbattlesim_target()`,
  `RuntimeManager`, public participant action admission, the adapter evaluator,
  and verified cleanup. It must not call the upstream evaluator directly,
  inject a fake driver, or import native state around the target boundary.

Common post-processing reads retained portable evidence from both lanes. It
must not compare in-memory native objects, use the native lane as an alternate
adapter implementation, or force the two lanes through one ambiguous generic
"runner" abstraction.

## Freeze and identity boundary

`protocol.json` has two integrity domains. Its declaration fixes the condition
matrix, source and apparatus selections, evaluator, metric definitions, run
allocation, seeds and actual binding dispositions, reset/order/budget/stop and
exclusion rules, aggregation and 95% uncertainty method, missing-data policy,
tolerances, and exact/bounded/failed criteria before source execution. Its
oracle section records the source-native results without changing that
declaration. The declaration digest is retained before the native lane; the
completed file and oracle are byte-frozen in version control before the first
mediated attempt, and every mediated attempt binds their digest. Neither
criteria nor source outcomes may be edited after mediated evidence exists.

The semantic owners inside that file remain the published
`ExperimentTaskModel`, `ExperimentSpecModel`, and `ExperimentStudyModel`
surfaces. In particular, use the study run-allocation and analysis-plan fields
for conditions, replication, statistical method, uncertainty, multiplicity,
stopping, and missingness, and use the task's evaluation protocol and metric
definitions for measured constructs. `protocol.json` is a thin issue-local
index plus the comparison/oracle fields issue #30 explicitly requires; it must
reference the canonical task/spec/pack artifacts by id and digest rather than
copy their contents or define another experiment model or JSON Schema.

`source-ledger.json` is likewise a bundle-local integrity index, not a second
mapping ledger. It cites `qualification.json`, `public-protocol.md`,
`mapping/source-ledger.jsonl`, `mapping/loss-disclosures.md`, the selected
notebook/source files, external pack, participant artifacts, adapter version,
and every compatibility patch by immutable identity and digest. Existing loss
and exclusion meanings stay with their canonical owners. A new patch must first
become reviewed qualification evidence with its base and resulting identities;
it cannot appear only in setup code or the reproduction bundle.

`<frozen-revision>` names an immutable study revision, not a mutable branch,
working tree, date alias, source tag alone, or "latest" directory. An admitted
bundle root is never overwritten, resumed, appended, or reused. A changed
protocol, source, pack, patch, analysis method, or rerun is a new revision with
new attempt identities.

## Reuse the existing owners

| Concern | Canonical incumbent and required boundary |
| --- | --- |
| Selected source and public protocol | `load_qualification()`, `read_public_protocol()`, `CYBERBATTLE_CHAIN`, `EvidenceSelection`, the qualified source-file/tree/runtime-artifact identities, and the package-local source/loss ledgers. Read and join them; do not repeat source constants in a study runner. |
| Source admission | `verify_selected_cyberbattlesim_source()` and `_source_admission`'s distribution, direct-artifact, complete-root, selected-file, symlink, version, and module-origin checks. Both real lanes fail closed before native import; a missing/mismatched source is retained as a terminal failure, never a fake-driver fallback. |
| Pack and authored contracts | `raes_env_packs.validate_pack()`, `verify_pack_content_digest()`, `raes-pack-release check`, confined `_pack_child()`, strict duplicate-key JSON loading, bounded RAES SDL parsing/instantiation/digest, and the exact external task/spec/participant artifacts. Do not execute acquired pack code or trust filenames without bytes. |
| Experiment design and allocation | `ExperimentTaskModel`, `ExperimentSpecModel`, `ExperimentStudyModel`, `ExperimentRunAllocationPlanModel`, `ExperimentAnalysisPlanModel`, and their cross-artifact validators. Do not create a reproduction protocol DTO, alternate metric catalog, or prose-only tolerance table. |
| Scheduled trial identity | RAES `AdmittedTrialPlanModel` / `AdmittedTrialEntryModel`, their seal/digest validators, `TrialCoordinateModel`, and admitted execution-control/cleanup-plan fields where the scheduled study is representable. Preallocate unique run coordinates and distinguish a logical run from every effect-capable attempt. |
| Attempt and run provenance | `TrialRunProvenanceModel`, `TrialExecutionAttemptReferenceModel`, `ExperimentRunModel` statuses, `ExperimentInvalidationModel`, operation references, and the published cleanup receipt on the mediated path. The mandated valid/invalid/failed/excluded bundle disposition is a thin terminal index over those owners, not another run or receipt model. Never turn an exclusion into a success or omit it from the scheduled inventory. |
| Runtime and participant authority | `RunControls`, `execute_episode()`, `create_cyberbattlesim_target()`, `RuntimeManager`, `RuntimeTarget`, the four backend components, public participant admission/result/history validation, and `RuntimeManager.destroy()`. Reuse or narrowly extract existing admission/artifact mechanics; do not call private RAES backend methods or copy the researcher workflow into a second adapter. |
| Evidence and measures | `ExperimentCaptureSpecModel`, `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, `ExperimentArtifactRefModel`, `_experiment_evidence.py`, `CyberBattleSimEvaluator`, and task metric ids. Retain model-validated per-run projections; no local observation/reward/metric DTO and no native fallback payload. |
| Conformance and disclosures | `run_cyberbattlesim_conformance()`, `cyberbattlesim_backend_conformance_payload()`, source-protocol diagnostics, manifest capability-evidence closure, declared weaknesses, scenario-ledger validation, and the existing non-claims. Conformance is cited evidence, not a study run or outcome-equivalence result. |
| Diagnostics and redaction | RAES `Diagnostic` / `DiagnosticModel` / `diagnostic_model()`, `ApplyResult`, canonical model/report projections, `redact_native_value()`, and `bounded_context_label()`. Use stable JSON Pointer addresses and bounded input-free messages; add no exception or diagnostic hierarchy. |
| Persistence and integrity | Exclusive invocation-relative output reservation, `atomic_write_json_artifact()`, relative artifact references, `_seal_inventory()`-style size/hash inventory written last, and existing no-clobber behavior. The checked-in bundle is archival experiment output, not `ControlPlaneStore` runtime state or a new evidence repository service. |
| Verification and workflow | Existing CyberBattleSim qualification, ledger, backend, conformance, researcher-command, hostile-leak, and clean-wheel tests; the one `pyproject.toml`/`uv.lock`; `_verification_envs()`, `_distributions()`, strict docs/policy, and canonical `nox -s verify`. Real native evidence remains a reviewed manual/readiness lane; do not add a network-dependent PR test or unenforced workflow. |

Published models should carry every fact they can express. The four mandated
bundle projections that RAES does not currently own remain narrowly
issue-local:

- `protocol.json` adds the source/mediated pairing, frozen oracle values, and
  predeclared exact/bounded/failed comparison criteria around canonical
  experiment references;
- each `runs/` terminal row adds only lane plus
  valid/invalid/failed/excluded disposition and references to the applicable
  RAES run/evidence/attempt/cleanup artifacts;
- `aggregates.json` adds structured point estimates and 95% interval endpoints
  computed from referenced per-run measures, because a prose uncertainty field
  is not a recomputable interval; and
- `tiers.json` fixes exactly the six issue-named tiers and their
  pass/fail/weakened result with relative, digest-bound, JSON-Pointer evidence
  citations. These labels are not a backend profile, RAES validation profile,
  capability table, or reusable equivalence vocabulary.

Use a small closed backend-local validator for only those issue-mandated gaps:
reject duplicate/unknown fields, non-finite numbers, duplicate identities,
unsafe relative paths, missing digests, unresolved citations, undeclared
metrics, nonterminal attempts, post-freeze drift, and aggregate/tier results
that cannot be recomputed. Do not publish Pydantic models or JSON Schemas for
them, put them in `raes_adapters.base`, or duplicate validation already owned by
RAES, the pack validator, qualification, or the source ledger.

## Attempts, aggregation, and tier claims

All logical run and attempt identities are allocated before the applicable
lane starts. A retry is a new effect-capable attempt id linked to the same
logical run only when the frozen retry policy permits it; an id is never reused
after failure, exclusion, cancellation, timeout, cleanup failure, or process
failure. The accepted bundle contains no scheduled/running/unknown residue.
Every row ends valid, invalid, failed, or excluded, cites bounded diagnostics
and cleanup evidence where applicable, and remains visible to denominator and
missing-data calculations.

The current researcher batch loop is not sufficient by itself: it stops at the
first exception and retains only a batch-level failure. Reproduction must keep
the same admission/execution/sealing mechanics while terminalizing each
predeclared attempt and continuing or stopping exactly as the frozen policy
says. A cleanup, evidence-validation, persistence, inventory, or terminalization
failure is not a valid run. An interrupted, unsealed root is not publishable and
must never be mistaken for a resumable successful bundle.

Aggregation is a pure read of retained terminal rows and model-validated
per-run evidence. It uses the frozen metric, inclusion, missingness,
aggregation, and 95% interval methods; records all scheduled, valid, invalid,
failed, and excluded counts; and never reads simulator source, imports the
adapter, uses wall-clock order as data, or silently drops a bad run. Clean
recomputation verifies every content digest and contract join, recomputes
`aggregates.json` and `tiers.json` byte-for-byte or semantically under an
explicit canonicalization, and needs no network, native source, credential,
provider log, or private artifact.

Tier results do not collapse into one `passed` boolean. A tier may pass only
the predeclared facts and evidence within its scope. A known loss, unsupported
RAES fact, missing source artifact, control mismatch, or unavailable metric
becomes failed or weakened according to the frozen criteria; it is not repaired
by widening a tolerance after viewing outcomes. Citations point to retained
artifact paths, SHA-256 digests, and JSON Pointers, never raw source logs or an
uncited prose assertion.

## Cross-cutting security and whole-repository path

| Layer the intended design passes | Required treatment |
| --- | --- |
| Authentication and authorization | The reproducer is a local operator command with no route, daemon, remote caller, or new authentication surface. Source-native execution is oracle collection only, not participant authorization. Mediated actions still cross the compiled participant behavior, exact manifest/selection/configuration and exposure-policy joins, and public RAES admission. Any later HTTP surface must reuse `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`, verified identity, role/target authorization, request-size limits, denial audit, and redacted errors. |
| Secrets and disclosure | The public protocol needs no credential input and must not read a repository/user secret store, `.env`, provider log, or ambient token. Learned CyberBattleSim credentials, native observations, action coordinates/masks, hidden graph/evaluator truth, reward vectors, random state, stdout/stderr, object representations, paths, argv/environment mappings, exceptions, and tracebacks remain private. Hashing any of them does not make them publishable. Final publication is allowlist-based and reviewed. |
| CLI and configuration shape | Extend only the existing closed command/backend selection or a backend-local module entry point; accept no arbitrary import, evaluator class, source path, corpus/profile root, plugin, URL, environment override, or native field selector. Reuse safe run-id rules, exact mode/cardinality checks, strict JSON, confined pack-child resolution, pack digest, scenario/task/spec/participant joins, and source admission before output/native execution. |
| Source-native shape checks | Verify the qualified artifact before import, then validate only the pinned reset/step/evaluator return shapes and bounded scalar/category/series projections. Native records are not made portable by recursive sanitization. An unexpected shape or unsupported terminal/availability fact is a bounded failed/weakened result, not guessed data. |
| RAES/runtime validation | The mediated path passes RAES SDL/experiment/participant closed models, pack validation, `RuntimeTarget` manifest/signature gates, `RuntimeManager` planning, `ApplyResult` and snapshot-transition validation, participant/action/history joins, evaluator/evidence models, and cleanup receipt validation. Native mutation followed by invalid projection is failure requiring cleanup. |
| Error envelopes | Expected source, parser, identity, control, execution, timeout, cleanup, projection, persistence, recomputation, and tier failures become validated RAES diagnostics with fixed codes/messages. Never serialize exception text/types from hostile native code, causes, locals, rejected Pydantic input, raw stdout/stderr, or traceback. The terminal bundle row references diagnostics and does not invent an error envelope. |
| OS/process exposure | Run from explicit isolated temporary working/home/cache directories with cleared `PYTHONPATH`, `PYTHONSAFEPATH=1`, no network after acquisition, no shell interpolation, explicit argument vectors, a small environment allowlist, timeouts, bounded control output, and native stdout/stderr redirected and discarded. Reuse the pattern in `sanitized_subprocess_env()` / `_run()` from the qualification tooling when process isolation is needed; never put secrets or native payloads in argv/environment. |
| Logging and observability | Portable observability is contract-validated evidence, terminal rows, bounded diagnostics, cleanup/operation references, aggregates, tiers, limitations, closed timestamped bench notes, and the final inventory. Each bench note uses an RFC 3339 UTC timestamp, phase, severity, stable event code, observation, disposition, and relative evidence references; start, failure, and terminalization events are written as they occur. Logs/terminal output are allowlisted to safe ids, counts, relative names, modes, and dispositions. Do not log plans, pack contents, actions, observations, rewards, paths, random state, exception text, or native process output. |
| Persistence and publication | Reserve a new confined root exclusively, reject files/directories/symlinks already present, publish validated JSON atomically, use fixed/safe child names and relative URIs, and write the content inventory last. Never overwrite, append, resume, auto-delete material failures, retain host paths, or treat a mutable cache/database as evidence. The repository's 500 KiB file gate and private-key/leak scans still apply to every checked-in member. |
| Repository workflow | Keep code/tests in the existing package/test/nox graph and preserve lazy base/extra isolation. The real source-native plus real mediated run updates the manual CyberBattleSim readiness protocol and passing record only after both identities and leak checks pass. If a new CI job ever becomes unavoidable, it must join `PR Gate`; issue #30 does not justify one by default. |

## Extension seam

The extension seam is one immutable backend-local reproduction selection:
frozen revision; source qualification and notebook/evaluator identity; external
pack/scenario/task/spec/participant identities; lane ids; admitted trial plan;
metric and analysis references; and comparison/tier policy. Execution harnesses
receive that selection and emit retained evidence; the recomputer receives only
the sealed bundle.

A second CyberBattleSim public baseline, changed run count, or additional metric
is another selection and frozen bundle. It must not require editing the first
bundle, a cross-simulator registry, `raes_adapters.base`, RAES schemas/profiles,
or a hard-coded metric/tier switch outside the selection. The seam is not an
invitation to make source-native execution generic across simulators.

## Gotchas and anti-patterns

- The public notebook leaves all four stochastic sources uncontrolled, while
  the current mediated reset applies the provided value to Gym environment and
  action-space streams but leaves Python and global NumPy unbound. A repeated
  seed label is not the same as an executable binding. Freeze and compare the
  actual dispositions; do not silently seed the native oracle, remove seeding
  from the mediated path, or call the lanes equivalent merely to improve a tier.
- The current task declares steps, cumulative reward, availability, and
  terminal-cause metrics, but the current adapter evaluator retains only a
  cumulative-reward derived measure and the driver reports generic
  `source-terminated`. Do not fabricate missing series or terminal causes,
  infer them from reward alone, or claim metric completeness. Project them
  through the existing evaluator/evidence boundary with source-backed meaning,
  or record the predeclared failed/weakened/unsupported result.
- The authored RAES topology is explicitly representative while the native
  apparatus generates the size-10 chain. Shared condition identity does not
  make the scenario snapshots or state spaces equal. Preserve
  `loss-abstracted-topology` in state/observation and outcome interpretation.
- The adapter reproduces the selected policy through proposal plus RAES
  admission and an adapter-owned loop; the native oracle uses upstream
  `epsilon_greedy_search`. Compare their frozen schedules and reset semantics;
  a shared policy class name alone is not evaluator equivalence.
- Keep source termination, reconstructed cause, Gym termination/truncation,
  evaluator cutoff, participant terminal reason, objective truth, run status,
  attempt disposition, cleanup status, derived measure, aggregate acceptance,
  conformance, readiness, and scientific validity distinct.
- Do not combine the historical benchmark snapshot with the newer qualified
  commit, use it as the oracle, or tune against it. Do not fetch a floating
  notebook, branch, image, dependency, or environment pack during reproduction.
- Do not duplicate `qualification.json`, `source-ledger.jsonl`, task/spec,
  participant artifacts, native source, raw notebooks, or environment-pack
  content into the bundle. Cite immutable identities and include only the
  issue-required reviewed projections.
- Do not add a reproduction schema registry, profile, capability table,
  controller, service, database, repository, cache, exception hierarchy,
  redaction policy, second console script, second distribution/lock, or
  simulator-wide baseline framework.

## Non-goals and implementation boundaries

- No patch or requalification of CyberBattleSim, new source artifact,
  deterministic random-stream binding, replay engine, training loop, agent
  ranking, leaderboard, or notebook UI is part of issue #30.
- No change to RAES SDL/experiment/participant/validation semantics, backend
  profiles, fixture corpus, environment-pack schema, manifest vocabulary,
  runtime security, `ControlPlaneStore`, or shared base semantic boundary.
- No deterministic replay, exact state/observation equivalence,
  cross-simulator equality, benchmark comparability, agent superiority,
  general scientific reproducibility, or outcome equivalence follows from a
  passing run, interval, tier, readiness record, or clean recomputation.
- The bundle qualifies this one pinned CyberBattleSim baseline and adapter
  selection for the named frozen research consumers. It is not a general
  reproduction service or evidence authority for other backends or studies.
