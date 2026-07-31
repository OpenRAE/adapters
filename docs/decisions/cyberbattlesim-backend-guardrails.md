# CyberBattleSim backend architecture guardrails

GitHub issue #27 is the authority for the implemented backend deliverable. This
record fixes the boundaries that implementation must respect; the document
itself defines neither an implementation plan nor a new RAES contract.

## Admission and claim qualification

The maintainer-selected source profile is admitted for issue #27. The canonical
`qualification.json` records `admission.decision = "admitted"` and preserves
these limitations:

- no official index or release artifact for the selected immutable source;
- incomplete binding of the Gym environment, action-space, Python-global, and
  NumPy-global random streams through reset and evaluation; and
- unresolved upstream benchmark/evaluation defects.

The scenario and source ledger deliberately preserve those limitations.
Implementation may attest source identity, portable configuration, and observed
run evidence while reporting partial stochastic control and stochastic-bounded
outcome reproduction. It must not claim published dependency installability,
deterministic replay, or scientific equivalence that the evidence does not
support. A future patch or repackaging becomes part of the qualified identity
and must carry source, tree, patch, artifact, license, notice, dependency, and
behavioral evidence; none of that is a precondition for implementing the
selected adapter.

## Keep the concepts separate

| Concept | Boundary |
| --- | --- |
| Qualification and public protocol | Immutable backend-local source evidence, maintainer admission, and attainable claim strength. They are not a manifest, scenario, or runtime result. |
| Authored scenario | Portable RAES intent. The representative four-node authored topology is not the generated native `size=10` topology, an instantiated scenario snapshot, or live simulator state. |
| Source ledger and loss disclosures | Backend-local traceability and claim bounds. They are not portable state and do not extend RAES vocabulary. |
| Backend manifest | A truthful declaration of implemented RAES capabilities and realization limits, serialized with the published manifest-v2 model. It is not a source qualification record. |
| Provisioned target | RAES runtime state and references resulting from a plan. It is not a native Gym environment, reset observation, or hidden source truth. |
| Participant action | A validated RAES admission request and typed terminal result. Its contract address and action-instance identity are not a native action id. |
| Orchestration, time, and simulator execution | Workflow progress, logical clock transitions, and a native `env.step` are distinct. Exactly one component owns each native transition. |
| Participant observation and evaluation | Participant-relative disclosed information is separate from evaluator-only facts, objective truth, reward, evidence, and derived measures. |
| Termination and cleanup | Source termination, truncation, evaluator cutoff, ownership/SLA outcomes, participant termination, and verified resource cleanup are distinct facts. |

Do not hide a mismatch between these layers behind a generic “environment,”
“step,” “result,” “profile,” or “done” abstraction.

## Compose the canonical incumbents

`raes_adapters.base` remains plumbing and published RAES contracts remain the
semantic owners. The backend must build on these incumbents instead of copying
their DTOs, validators, registries, receipts, or workflow logic:

| Concern | Canonical incumbent and required use |
| --- | --- |
| Selected evidence | The existing `EvidenceSelection`, `qualification.json`, `public-protocol.md`, authored SDL, experiment task/spec, source ledger, and loss disclosures under `raes_adapters.cyberbattlesim`. Consume one admitted immutable selection; do not repeat its constants in runtime code. |
| Packaging and isolation | `pyproject.toml`, the single `uv.lock`, ADR-003, and `_extras()` / `_verification_envs()` in `noxfile.py`. A real `cyberbattlesim` extra is verified alone and must not change a base-only import or install. Add `tool.uv.conflicts` only for a demonstrated mutually incompatible extra stack. |
| Manifest | `raes_backend_protocols.backend_manifest.BackendManifest`, the capability models and validators, `backend_manifest_v2_model()` / `backend_manifest_payload()`, and the RAES-owned supported-contract catalog. Do not hand-author manifest JSON, capability vocabularies, or a supported-contract table. |
| Realization disclosure | `BackendRealizationEnvelopeModel` and its digest/cross-concern validation. Disclose the authored-to-native topology transformation and every applicable realization concern; do not claim exact topology realization when the evidence supports only a representative pattern. |
| Runtime target | `raes_adapters.base.build_runtime_target()` over `raes_runtime.registry.RuntimeTarget` and `RuntimeTargetComponents`. Let RAES check component presence, capability agreement, and method signatures; add no backend registry. |
| Runtime lifecycle and validation | `raes_runtime.RuntimeManager` / `RuntimeControlPlane` and the published provisioning, workflow, evaluation, proposition, participant, time, snapshot-transition, and `ApplyResult` gates. Never invoke private `_call_backend_*` helpers or fork their validation. |
| Participant lifecycle | `raes_backend_protocols.participant_runtime_base.BaseParticipantRuntime` and `ParticipantNativeActionExecution`. Reuse its initialize/reset/restart/terminate state machine, participant/episode identities, generation, append-only history, sequence, linkage, status, and results. The backend-specific seam is `_model_action`, not a second lifecycle controller. |
| Action admission and result | `ParticipantActionAdmissionRequest`, the published implementation-selection/exposure/evidence validators, `ParticipantActionResultModel`, and `autonomous_action_result_violation()`. Every admitted request must yield one typed terminal result matching its participant, episode, action instance, contract, generation, and temporal observation point. |
| Observation and retrieval | `ParticipantObservationEnvelopeModel`, published observation-boundary validation, `ParticipantRetrievalMixin`, and the participant-scoped context/status/history view models. Do not define a custom observation or history DTO, and do not return native dictionaries or masks. |
| Logical time | `ReferenceTimeRuntime`, `TimeCoordinator`, `apply_logical_clock_transition()`, and RAES time conformance validation. Define the explicit source-event-to-logical-transition mapping; never infer that one action or `env.step` is one RAES tick. |
| Stochastic controls | The checked-in experiment controls, published stochastic-control models, and `apply_seed_controls()` when an executable binding is supplied. The selected public task deliberately records descriptive controls without executable bindings; the driver separately reports which runtime seed calls were applied or remain unbound. A setter call or top-level integer is not a replay guarantee. |
| Workflow and evaluation | The compiled workflow contracts, `WorkflowExecutionStateModel`, evaluation lifecycle/history models, proposition/objective truth models, and their RAES validators. Orchestrator receipts do not substitute for participant outcomes or evaluator evidence. |
| Evidence and measures | `ExperimentEvidenceRecordModel`, `ExperimentRawEvidenceContentModel`, `ExperimentDerivedMeasureModel`, and `ExperimentRunModel`. Keep source reward/result facts, objective truth, evidence, derived measures, limitations, and evaluator lifecycle in their distinct published shapes. |
| Cleanup | `TrialCleanupPlanModel`, `CleanupCapabilities`, `require_cleanup_plan_capability()`, `execute_cleanup()`, `TrialCleanupReceiptModel`, and `validate_trial_cleanup_receipt()`. Native `close`/destroy/verify operations remain driver-local, deterministic, idempotent, and failure-preserving. |
| Receipts and persistence | `RuntimeControlPlane` operation receipts/statuses and `ControlPlaneStore`. Use the existing idempotency, audit, and persistence seam; create no CyberBattleSim receipt, repository, cache, database, or evidence store. |
| Failure hygiene and conformance | Base projection/redaction helpers, RAES `Diagnostic` / `DiagnosticModel` / `ApplyResult`, and `run_target_conformance()`. Return bounded portable failures and the canonical conformance report; do not create an exception hierarchy, fallback native payload, custom case family, or second report. |

## Driver boundary and ownership

The legitimate backend-specific seam is a private, in-process driver bound to
one admitted evidence selection and one native environment lifecycle. It may
hold native environment objects, observations, action masks, identifiers,
arrays, reward components, hidden truth, and compensation state. None of those
values crosses into a RAES contract, diagnostic, receipt, history, log,
exception message, or stable reference.

Provisioner, Orchestrator, ParticipantRuntime, and Evaluator may compose that
driver, but native state has one owner. One admitted participant action maps to
exactly one driver operation and at most one source transition. The
Orchestrator must not replay the action, the Evaluator must not advance the
environment while projecting facts, and observation projection must not
trigger another source call.

The driver must serialize access unless the qualified source proves safe
bounded concurrency; the manifest must not claim concurrent execution merely
because RAES supports it. Portable inputs should be completely admitted before
native mutation. After mutation, projection and portable result validation must
either succeed or leave the episode in an explicit failed/terminated state with
compensation or cleanup available. RAES rolls back an invalid portable
snapshot, but it cannot roll back a mutated native simulator.

Reset must bind every declared random stream and distinguish reset from restart,
new episode identity, deterministic replay, termination, and cleanup. Cleanup
must be safe after partial construction, failed admission, projection failure,
termination, repeated calls, and ordinary success. `RuntimeManager.destroy()`
stopping components and removing portable provisioning entries is not, by
itself, verified native cleanup.

## Cross-cutting validation and security path

The intended design is an in-process optional backend. It introduces no new
authentication service, HTTP route, environment-variable configuration, CLI,
subprocess, network fetch, or durable store.

| Layer the design passes | How it passes |
| --- | --- |
| Source/admission and dependency authority | The admitted qualification identity remains package evidence. `pyproject.toml` publishes a dependency-light adapter extra because upstream provides no index/release artifact; a separately installed simulator must match the qualified complete import-root tree (including native libraries and unexpected files), critical-file digests, and the qualified Gymnasium/NumPy wheel identities, complete roots, versions, and module origins. The locally built simulator wheel is admitted by its complete root because upstream publishes no reproducible wheel artifact; a direct Gymnasium/NumPy archive install must also match the selected public wheel hash. Editable/directory/VCS installations, symlinks, unqualified direct dependency artifacts, hidden patches, and dependency state received transitively from another extra fail the driver boundary. The remaining normalized dependency graph is recorded evidence, not a runtime authenticity claim. |
| Contract parsing and configuration shape | SDL uses the bounded RAES parser and compiler; experiment and runtime values use closed published models (`ContractModel`, generally `extra="forbid"`) and existing cross-artifact joins. No environment override, arbitrary import path, permissive mapping, duplicate schema, or duplicated enum list may bypass them. |
| Manifest and target shape | Backend manifest capability, contract-family, realization-envelope, digest, component-presence, and callable-signature validation run before target use. Unsupported facts are rejected or represented as limitations, never advertised optimistically. |
| Plan, transition, and result envelopes | `RuntimeManager` / `RuntimeControlPlane` validate planning identity, baseline snapshots, `ApplyResult`, changed addresses, workflow/evaluation/proposition state, participant history, time readback, and realization disclosure. Invalid portable output fails closed and does not become a success receipt. |
| Participant admission and disclosure | Action contract, implementation selection, target addresses, generation, evidence references, exposure policy, terminal result, sequence/linkage, and participant/episode scope use the published validators. Positive and negative tests must prove that another participant's data and evaluator-only/hidden references cannot enter views or observations. |
| Secret handling | The driver neither reads a repository/user secret store nor accepts credentials as runtime configuration. Source-native learned credentials remain opaque driver state. Tokens, secret values, environment dumps, and authentication material never enter argv, logs, evidence, snapshots, diagnostics, or portable histories. |
| OS/process exposure | Native code is imported lazily only when the extra-backed target is constructed, after the selected distribution and directly imported Gymnasium/NumPy artifacts have matched qualified versions, full installed import-root trees, applicable direct-archive identities, and module origins. Complete-root enumeration rejects unlisted source, bytecode, extension, native-library, data, and symlink entries before driver import. Base import/install does not import the simulator. Execution uses no shell, child process, inherited configuration dump, home-cache authority, checkout-relative import, or runtime network fetch. If a future qualified driver requires a subprocess, reuse the repository's confined temporary directory, explicit argument vector, small environment allowlist, cleared `PYTHONPATH`, safe-path, timeout, and bounded-output pattern. |
| Error and log envelopes | Base default-deny redaction and RAES diagnostics/results are the only portable failure path. Never use `str`/`repr` on native values; native exceptions contribute at most a safe type name, without args, causes, locals, paths, stdout/stderr, or traceback. Logs are limited to bounded published addresses, safe operation names, counts, and dispositions. |
| Authentication/authorization if later exposed | Reuse `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`, verified identity, role/target authorization, request-size limits, denial audit, and its redacted exception handler. Do not create an adapter-specific endpoint or weaker auth/config surface. |
| Persistence and idempotency | `ControlPlaneStore` and control-plane receipts remain the operation-persistence boundary. Backend-native state is lifecycle-scoped and is closed/verified through cleanup; it is not persisted as a second source of truth. |
| Distribution and workflow | Extend the existing `_distributions()` / `probe_installed_identity.py` clean-wheel proof and existing tests, docs, type, policy, and `verify` graph. The base environment and each extra remain isolated. Do not add a second lock, build probe authority, CI workflow, or required-check path. |

## Extensibility seam

The external parameter is an admitted immutable `EvidenceSelection` (or a
future selection with the same package-local role) plus a driver factory for
that selection. Action translation is keyed by published action-contract
address and validated portable arguments/targets; observation projection is
keyed by the published participant boundary; termination/evaluation mapping is
keyed by the selected source protocol. These are backend-private mappings, not
new base registries or portable schemas.

A second qualified CyberBattleSim scenario, policy, or source artifact should
be addable as another immutable selection and driver configuration without
editing a cross-simulator registry, copying participant lifecycle logic, or
changing RAES contracts. Source-version-specific compatibility stays behind
the driver factory and remains tied to qualification evidence. Do not
generalize this seam into `raes_adapters.base` until a real cross-backend
mechanical pattern exists and RAES does not already own it.

## Gotchas and anti-patterns

- Do not turn an admitted selection into a deterministic-replay, dependency
  installability, or outcome-equivalence claim without matching evidence.
- Do not treat source import/smoke success, finite conformance, or one clean run
  as proof of deterministic replay, scientific validity, or outcome
  equivalence.
- Do not conflate native `terminated`, Gym `truncated`, evaluator cutoff,
  ownership, defender SLA failure, eviction, participant terminal status, and
  cleanup outcome. Preserve precedence and the recorded off-by-one limitation.
- Do not turn reward into an action outcome, objective truth, evaluator
  lifecycle state, evidence, or a derived measure. Project each fact through
  its published owner and retain limitations.
- Do not expose native action ids, node ids, tuples, arrays, masks,
  credential-cache contents, observations, `info`, logs, paths, hidden truth,
  exceptions, arguments, environment values, credentials, or tracebacks as
  portable data or “stable” references. Stable source references are
  qualification/ledger identities and digests.
- Do not attribute an effect to the request's portable target when the private
  source coordinate cannot be joined to that target. Preserve the request as
  intent and leave realized effect target references empty.
- Do not duplicate manifest payloads, RAES schemas/validators, participant
  views or histories, operation receipts, time state, cleanup receipts,
  diagnostics, stores, conformance cases, or workflow/evaluator controllers.
- Do not override `BaseParticipantRuntime` lifecycle methods merely to mirror
  the simulator API. Claim coordinated reset only if the native implementation
  supplies real atomic multi-participant reset and rollback.
- Do not let Provisioner reset the participant episode, Orchestrator execute the
  admitted action a second time, or Evaluator advance or mutate the simulator.
- Do not return portable success after a native mutation whose projection or
  RAES validation failed. Treat compensation and cleanup failures as distinct
  from the primary operation failure and preserve both safely.
- Do not claim a capability without executable evidence, including reset,
  stochastic control, exposure, observation sealing/capture, objective truth,
  cleanup verification, or concurrency. Reject unsupported requests and
  disclose bounded limitations.
- Do not add process-global random seeding, working-directory dependence,
  import-time simulator discovery, broad environment forwarding, unbounded
  logging, a catch-all success fallback, or a backend-independent native
  simulator abstraction.

## Non-goals and implementation boundaries

- This preflight does not select or approve a replacement artifact, patch,
  repackaging route, or defect disposition; those belong to requalification.
- This guardrail record is not itself the optional extra, driver, target,
  manifest, protocol surface, projection, cleanup result, test, or conformance
  report; those remain executable repository artifacts.
- It does not change the authored RAES scenario to imitate native `size=10`
  state or upgrade the recorded equivalence tier. Any mapping loss remains
  explicit.
- It does not add semantics to `raes_adapters.base`, change published RAES
  contracts, create a generic Gym adapter, or make CyberBattleSim concepts
  shared authority.
- It adds no authentication mechanism, HTTP controller, CLI, daemon,
  subprocess launcher, plugin discovery, environment-binding format,
  repository/database/cache, second distribution/lockfile, or CI workflow.

## Issue #27 acceptance evidence

Qualification limitations bound the assertions in this table; none is an
admission gate.

| Acceptance concern | Executable evidence |
| --- | --- |
| Selected scenario and target realization | `test_selected_scenario_realizes_and_runs_across_applicable_surfaces` compiles the checked-in size-10 scenario with `ReferenceProcessor` and exercises provisioning, orchestration, participant action, evaluation, and verified cleanup through one target. |
| Truthful manifest and published RAES contracts | `test_manifest_and_target_claim_exact_implemented_surfaces` validates manifest-v2 projection and constrained capability declarations; `test_target_passes_canonical_backend_conformance_probe` requires every canonical finite case to pass with no contract or capability gap. |
| Exactly one native transition per admitted action | `test_each_admitted_action_has_one_driver_operation_and_typed_terminal_result` proves the portable identity/result join without falsely attributing the private native coordinate to the requested portable target; `test_live_driver_is_lazy_seed_bounded_and_performs_exactly_one_native_step` verifies qualified complete artifact roots, critical source digests, selected Gymnasium/NumPy artifacts and module origins before source import, rejects an added extension artifact, then probes the live-driver seam, selected source configuration, and one native transition. |
| Participant/evaluator separation and no native leakage | `test_action_boundary_withholds_unrequested_evidence_and_native_failures` and `test_evaluator_reads_distinct_facts_without_advancing_or_leaking_to_participant` cover evidence admission, generic failure projection, reward ownership, non-mutating evaluation, and distinct internally joined artifact identities for successive projections. |
| Unsupported behavior fails before source mutation | `test_unsupported_action_is_rejected_before_native_mutation` and `test_unsupported_provisioning_is_rejected_before_construction` bind negative behavior to the declared capability surface. |
| Bounded stochastic controls, termination, and restart | `test_live_driver_is_lazy_seed_bounded_and_performs_exactly_one_native_step` records applied and unbound streams plus evaluator cutoff; `test_source_termination_closes_episode_and_restart_resets_same_seed` keeps source termination and participant restart distinct. |
| Idempotent, failure-preserving cleanup | `test_cleanup_is_idempotent_verified_and_preserves_bounded_failure` covers repeated cleanup, verification, required/best-effort outcomes, and native-error redaction; `test_provisioner_reconciles_live_driver_and_orchestrator_never_steps_driver` proves create → cleanup/destroy → create reuses the advertised target safely. |
| Optional dependency isolation | `test_backend_import_is_dependency_light_and_lazy` proves that importing the backend loads neither CyberBattleSim nor Gymnasium. The canonical distribution matrix verifies base, `cyberbattlesim`, and other extras independently from the single lock. |
