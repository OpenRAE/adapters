# NASim conformance-composition guardrails

GitHub issue #35 is the authority for this deliverable. This note fixes how
published RAES backend conformance composes with NASim-local executable
evidence. It defines no new contract, profile, fixture, report, probe schema, or
implementation plan.

## Keep the three claims separate

The published RAES profile, fixture corpus, target probes, report, and bounded
claim remain authoritative. NASim probes add source-protocol evidence; they do
not extend backend conformance.

| Result | Meaning and owner |
| --- | --- |
| Backend conformance | The exact `BackendConformanceReport` returned by `run_target_conformance()` for the profile inferred from the live manifest, serialized by `backend_conformance_report_payload()`. |
| Source-protocol reproduction | Adapter-local executable evidence for the qualified `NASIM_TINY` selection: source/ledger identity, reset and stochastic dispositions, source ordering, action and observation projection, reward/evaluator facts, independent terminal facts, and cleanup. It uses RAES diagnostics and existing evidence references, not another report case family. |
| Research/readiness claim | A bounded interpretation of qualification, experiment controls, source-native observations, loss disclosures, and declared weaknesses. It never upgrades stochastic-bounded outcome reproduction to deterministic replay, outcome equivalence, or scientific validity. |

Do not combine these into a new aggregate `passed` value. A live NASim run does
not change the canonical report's meaning. An injected driver is hermetic
adapter evidence and must keep `native_conformance=false`; a real driver is
source-protocol integration evidence unless the published RAES native-live
harness and its observation/cleanup requirements are actually satisfied.

Every fixture selected by `profile_for_manifest(create_nasim_manifest())` is
applicable and must pass. Adapter code may not relabel a failed fixture as
unsupported. An unsupported disposition is legitimate only when the published
runner emits it or a local source-control probe reports a genuinely unavailable
control using a validated RAES diagnostic and a non-contradictory manifest
claim. It is never an `xfail`, skip, swallowed exception, or fake-driver
fallback.

The source `tiny` protocol and the published backend capability profile are
different identities. Do not call the source selection a conformance profile or
copy either identity into a second table.

## Compose the existing owners

Implementation must build on these incumbents:

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Manifest, profile, and fixtures | `create_nasim_manifest()`, `BackendManifest`, `backend_manifest_v2_model()`, `backend_manifest_payload()`, `profile_for_manifest()`, `run_fixture_suite()`, `run_target_conformance()`, published corpus roots, and `raes_adapters.base.run_conformance_probe()`. Use the live declaration and default published roots; no golden payload, copied contract set, local profile, or production root override. |
| Target and runtime gates | `create_nasim_target()`, `build_runtime_target()`, `RuntimeTarget`, `RuntimeManager`, and `RuntimeControlPlane`. Exercise all portable transitions through public gates; never call RAES private `_call_backend_*` helpers or bypass snapshot/result validation. |
| Source identity and coverage | `NASIM_TINY`, `LEDGER`, `EvidenceSelection`, `load_qualification()`, the scenario/task/spec/loss loaders, `validate_all()`, and the checked-in qualification/protocol joins. Read the selected source, seed, scenario, cutoff, terminal, and weakness facts; do not transcribe them into a probe catalog. |
| Installed-source admission | `NasimDriver` and `raes_adapters._source_admission`: selected distribution versions, direct-archive identity, complete symlink-free import-root trees, selected-file digests, and pre-import module-origin checks. Expected artifacts and policy remain NASim qualification evidence. |
| Shared backend mechanics | `GymProvisioner`, `GymEpisodeOrchestrator`, `GymParticipantRuntime`, `GymEvaluator`, `execute_gym_cleanup()`, and their NASim wrappers. Extend their explicit backend-local callback/config seams; do not copy the four controllers or create another Gym abstraction. |
| Participant lifecycle and projection | `BaseParticipantRuntime`, `ParticipantActionAdmissionRequest`, `ParticipantNativeActionExecution`, `ParticipantActionResultModel`, `ParticipantObservationEnvelopeModel`, the published admission/exposure/history validators, and the driver-private semantic action resolver. No native action index, coordinate, observation vector, host state, or `info` crosses this boundary. |
| Evaluation | `NasimEvaluator`, `ExperimentCaptureSpecModel`, `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, proposition truth/result models, and `_experiment_evidence`. Reward, objective truth, terminal status, evidence, and derived measures remain distinct. |
| Cleanup | `execute_nasim_cleanup()`, cleanup capability admission, base `execute_cleanup()`, `TrialCleanupPlanModel`, `TrialCleanupReceiptModel`, and `validate_trial_cleanup_receipt()`. A close boolean is not verified clean state. |
| Diagnostics and failure hygiene | RAES `Diagnostic`, `diagnostic_model()`, `diagnostic_payload()`, `ApplyResult`; shared `diagnostic_address()`, `redact_native_value()`, and `bounded_context_label()`. Use stable pointer-addressed, input-free failures; add no exception or diagnostic hierarchy. |
| Report and artifact persistence | `backend_conformance_report_payload()` and `write_backend_conformance_report()` own canonical report validation, redaction checking, safe run labels, and atomic persistence. Other JSON uses `atomic_write_json_artifact()` only after its content is validated; no checked-in generated report or new evidence repository. |
| Capability evidence | `_conformance_support` and `_gym_backend.conformance` own live-manifest traversal, fail-closed pointer coverage, passed-evidence accounting, source diagnostics, and weakness derivation. Add NASim-local passing evidence through their explicit configuration/input seam; do not fork the traversal or maintain a second capability catalog. |
| Packaging and workflow | The single `pyproject.toml`/`uv.lock`, the isolated `nasim` extra, `_extras()`, `_verification_envs()`, `_tests()`, `_distributions()`, `probe_installed_identity.py`, `.github/workflows/ci.yml`, its `PR Gate`, and canonical `nox -s verify`. Extend these paths; do not add a lock, distribution, combined-extras environment, or parallel workflow. |

The existing `tests/test_nasim_backend.py`, `tests/test_nasim_driver.py`,
`tests/test_nasim_conformance.py`, and shared scenario-ledger tests already cover
most individual invariants. The issue-level suite must execute the production
composition and reuse those fixtures/patterns rather than restating their
semantics in a second test-only controller. The current clean-wheel
`NASIM_CONFORMANCE_PROBE` in `noxfile.py` is the distribution boundary to
generalize to the installed suite, not a second inline suite to grow in
parallel.

## Additive probes and evidence closure

Adapter-local probes cover facts RAES cannot know: the selected source/ledger
join, installed-source identity, stochastic-stream dispositions, private action
mapping, observation sealing, evaluator ownership, native terminal semantics,
and verified close. They do not become `BackendConformanceReport.cases`, a
fixture overlay, or a realization-harness misuse.

Every affirmative manifest capability must resolve from the live
`backend_manifest_payload()` to evidence references owned by probes that
passed. The existing shared pointer traversal remains the closure check. Stable
NASim-local probe references may be requirements for the applicable component
surface, but the requirement mapping contains only JSON pointers and evidence
references—not copied capability values—and must fail closed when a new
affirmative capability has no evidence. Source-ledger validation alone is not
runtime evidence; canonical target conformance alone is not source-protocol
evidence.

Leakage coverage is the success/failure cross-product over the four declared
backend surfaces—provisioner, orchestrator, participant runtime, and evaluator—
plus cleanup. Inspect the actual JSON-ready projections: `ApplyResult`, snapshot
entries and histories, operation receipts/status, participant action and
observation models, evaluator evidence/measures, cleanup receipt, diagnostics,
canonical report, and any persisted operational index. Use unique hostile
sentinels and objects whose `str` and `repr` are unsafe. Prove absence of native
arrays/dtypes/classes, flat indices, coordinates, host truth, `info`, reward
containers, random state, credentials, exception data, paths, stdout/stderr,
argv/environment mappings, and tracebacks. Do not use `repr(result)` or a regex
over a native dump as the oracle.

Portable caller-authored input may legitimately survive a successful plan; do
not confuse that with native leakage. Failure tests instead prove rejected or
native values are not echoed, and success tests prove only validated published
projections are emitted. If a native transition succeeds and later projection
or RAES validation fails, the episode is failed/quarantined and cleanup remains
required; portable success cannot be synthesized because rollback is
impossible.

## Suite and manual-live boundaries

The PR suite is fixed, deterministic, offline, and dependency-light. It uses
the selected public seed `20260802`, a fully constructed `RuntimeTarget`, and an
explicit deterministic injected driver. It runs the published profile/corpus,
the additive success/failure probes, capability-evidence closure, leakage
checks, report projection, and cleanup. The suite never derives seed or case
order from time, PR number, hashing, environment, test order, or global random
state.

The broader study/readiness tier retains the same canonical report and adds the
qualified installed-source checks and the source-native reset, global-NumPy
action-success stream, Gym reset stream, representative action, withheld
observation, scalar reward, goal, step-limit, and verified cleanup probes fixed
by the protocol. The hermetic mapping inventory separately covers the case
where both terminal booleans are true so projection cannot erase either fact.
The tier may add only reviewed immutable selections or seeds. A broader finite
sample does not erase loss disclosures or strengthen the research claim.

The issue-required manual integration run is the separate hands-on gate where
the adapter conformance composition is checked against the real simulator on the
qualified runtime from issue #32. It must explicitly construct a real
`NasimDriver` and a complete `RuntimeTarget`, execute the deterministic PR probe
inventory without substituting a stub/mock at any point, run
`run_nasim_conformance()` through that target, serialize the canonical report
through `backend_conformance_report_payload()`, collect
`nasim_source_protocol_diagnostics()` and manifest capability evidence, validate
every local diagnostic, close capability evidence, and verify cleanup. It does
not replace the deterministic injected-driver CI probe; it exercises the same
composition against installed NASim. The emitted report, diagnostics, evidence
references, and cleanup receipt must not contain native action coordinates,
observations, reward vectors, hidden state, host truth, object representations,
paths, environment dumps, or tracebacks. Record only portable reports,
diagnostics, evidence references, weakness references, and bounded
dispositions. Missing Tk, a mismatched installation, an unavailable native
control, or cleanup failure is a failed manual-readiness result, never a switch
to the injected driver under the same label. The operator records the command,
qualified identities, dispositions, and cleanup result; no native dump is
retained.

The clean-install PR proof remains in `_distributions()`: install the built
wheel with the `nasim` extra into its own throwaway environment, run from the
isolated working directory with `-I`, cleared `PYTHONPATH`, and
`PYTHONSAFEPATH=1`, load installed package resources, and run the PR suite. The
normal `tests` and `distributions` jobs remain PR owners. Any scheduled/full
automation extends the existing CI workflow and must either join `PR Gate` or
be explicitly non-PR readiness evidence; it does not create a second workflow.

## Cross-cutting security and whole-repository path

| Layer the design passes | Required treatment |
| --- | --- |
| Authentication and authorization | Local conformance adds no route, daemon, or caller authority. In-process work uses the existing manager/control plane. Any later HTTP exposure must use `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`, verified identity, role/target and participant subject/audience authorization, request-size limits, denial audit, and the redacted exception handler; no NASim endpoint is permitted. |
| Secret handling and environment bindings | No secret or credential is required. Do not read a secret store, accept token options, bind source identity from environment, or expose synthetic/learned credentials, entropy, tokens, environment data, or secret references through argv, filenames, logs, evidence, diagnostics, snapshots, or reports. |
| Static parsing and configuration shape | `EvidenceSelection` and qualification own source selection. RAES SDL parsing/compilation, closed experiment models, cross-artifact joins, strict JSONL validation, `schema_bundle()` target resolution, manifest validators, published profile/corpus loaders, and `RuntimeTarget` presence/signature checks all run. No arbitrary import path, environment-selected seed/corpus, permissive mapping, copied enum, or duplicate schema bypasses them. |
| Native source and OS boundary | Before the first lazy NASim import, verify admitted NASim/Gymnasium/NumPy artifacts, source files, and module origins, and require Tk. Use `render_mode=None`; do not monkey-patch Tk/matplotlib, render, download, open a socket, scan user-home/cache state, or forward a broad environment. The driver preserves/restores caller NumPy state under the existing process-wide lock on success and failure. |
| Runtime and participant gates | `RuntimeManager`/`RuntimeControlPlane` validate plan/manifest/snapshot identity, capability and dependency admission, `ApplyResult`, changed addresses, realization disclosure, workflow/evaluation/proposition state, participant lifecycle/action/history/exposure, receipts/status, and persistence. Adapter checks add only selected-NASim representability and private projection. |
| Error envelopes | Catch native failures at the existing component boundary before RAES's generic backend-call diagnostic can name native types. Emit fixed RAES diagnostics with JSON Pointer addresses and validate with `diagnostic_model()`. Never include exception strings/types derived from hostile code, args, causes, contexts, locals, rejected values, paths, logs, or traceback. Serialize reports and diagnostics only through their published projectors. |
| Logging and observability | Portable observability is reports, validated diagnostics, evidence/weakness references, limitations, cleanup receipts, and fixed reproduction argv. Logging, if needed, is limited to safe operation names, published pointers, counts, and dispositions; never log plans, actions/arguments, observations, rewards, native state, random state, paths, environment/argv, or tracebacks. |
| Persistence and output confinement | `ControlPlaneStore` remains the only runtime-state persistence seam. Reports use the RAES writer; other validated JSON uses the shared atomic writer beneath an explicit confined output root. Use relative artifact references and safe run labels. Hashing a native dump does not make it portable. |
| Repository workflow | Preserve isolated extras, the single lock/distribution, strict type/lint/test/docs/policy gates, the installed-wheel proof, and CI `PR Gate`. This requirement-free issue uses `--skip-requirement`; it does not create a substitute governance path. |

NASim exposes no RAES time runtime or time capability. Its serialized source
step number is an observation, not a logical clock. The clock-control probe must
therefore emit a validated unsupported/limitation disposition consistent with
the manifest. Do not add `ReferenceTimeRuntime`, infer one tick per `env.step()`,
or advertise time support merely to make the probe affirmative.

## Extension seam

The external seam is the immutable `EvidenceSelection`, an explicit ordered
suite/seed selection, and a driver provider whose execution basis is declared.
Probe semantics read scenario, stochastic, action, evaluator, and terminal
facts from that selection. A second qualified NASim case is another selection
and driver configuration, not a branch in shared plumbing or an edit to the
published corpus.

For shared Gym conformance, backend-local probe callbacks/evidence references
belong as explicit inputs on `GymConformanceConfig` (or an equally narrow
backend-neutral input), so a future Gym-style backend can reuse report
projection and capability closure without importing NASim. Version-specific
source behavior remains behind the NASim driver provider. Generalize only
mechanics already shared by multiple backends; source semantics stay local.

## Gotchas and anti-patterns

- `run_nasim_conformance()` currently chooses a real `NasimDriver` when no
  driver is supplied. PR and manual lanes must always select their driver
  explicitly; absence or failure never changes lane silently.
- Do not describe `fully_obs=True` as partially observed. The source is fully
  observed; the participant projection is deliberately narrower and lossy.
- Keep the Gym reset stream and global NumPy action-success stream distinct.
  Binding both explicitly still does not prove general deterministic replay.
- Preserve `terminated` and `truncated` independently, including when both are
  true. Goal precedence for participant completion must not erase evaluator
  truncation evidence.
- Do not turn the source step count into RAES logical time, reward into action
  success/objective truth, target intent into a realized effect, source terminal
  state into workflow completion, or close into verified cleanup.
- Do not import sibling-backend semantics, DTOs, probe catalogs, or private
  helpers. Reuse shared mechanics and published contracts only.
- Do not append local cases to the canonical report, reconstruct it with
  `asdict()`/`replace()`, copy profile or fixture roots, hand-author manifest
  JSON, or add a local unsupported escape hatch.
- Do not serialize native values and redact afterward, rely only on the generic
  report redaction gate, or persist an operational index before its referenced
  reports and diagnostics have validated.
- Do not run live native probes concurrently: NASim action success uses a
  process-global NumPy stream protected by the driver lock. Never seed at import
  time or leave caller global state changed after failure.

## Non-goals and implementation boundaries

- No new RAES schema, SDL vocabulary, backend profile, fixture corpus, manifest
  extension, capability vocabulary, report DTO, diagnostic envelope, exception
  hierarchy, store, audit service, policy gate, or workflow engine.
- No requalification, source patch, dependency upgrade, arbitrary NASim
  scenario/generator, defender, training agent, model weight, rendering,
  concurrency, or generic Gym/Gymnasium adapter.
- No new HTTP service, authentication mechanism, plugin discovery,
  environment-binding format, database/cache, subprocess launcher, second
  distribution/lockfile, combined-extras environment, or CI workflow.
- No claim of deterministic replay, exact native state/observation equivalence,
  outcome/evaluation equivalence, scientific validity, or behavior beyond the
  named finite cases and qualified selection.
