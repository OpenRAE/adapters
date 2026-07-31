# CybORG logical-step and action-translation guardrails

GitHub issue #16 is the authority for this increment. This note fixes the
component boundaries, validation path, and claim limits that implementation
must preserve. It does not define a local contract or provide an implementation
plan.

## One aggregate native turn, existing RAES public surfaces

CybORG owns one aggregate in-process environment. Its public step executes more
than a blue operation: native red and green policies, backend state changes,
truth/reward calculation, training updates, and the blue monitor update occur in
the pinned source order recorded by source-ledger row `control-turn-order`.
That aggregate must not be represented as independent simulator calls merely to
make the RAES component diagram look symmetrical.

The public RAES ownership split is:

- `Orchestrator.start` admits and reconciles the compiled run/turn policy,
  including the explicit trial limit, ordering, reset, and terminal rules. The
  published `Orchestrator` protocol has no `step` method; do not add an
  adapter-specific public method or reinterpret `start` as an unbounded hidden
  loop.
- `ParticipantRuntime.admit_action` is the existing trigger for one admitted
  participant action. For the selected CybORG profile, one admitted external
  blue action may trigger exactly one aggregate native environment turn. The
  red and green actions selected inside that turn are projected as distinct
  participant occurrences in the same joint-action record; they are not
  falsely described as separately submitted RAES actions.
- `TimeRuntime` owns portable logical time. A successfully validated and
  committed aggregate turn advances the admitted logical clock exactly once.
  Native counters and wall time are observations, not a second clock.
- `Evaluator` remains absent until an `EvaluationPlan` and the published
  evaluation result contracts are actually implemented. A native reward or
  evaluator calculation that happens inside `step` is not by itself a RAES
  evaluator capability.

The Provisioner, Orchestrator, ParticipantRuntime, and TimeRuntime need one
module-private aggregate-session owner and one shared re-entrant mutation lock.
This is ephemeral backend mechanics, not a DTO, registry, store, or new backend
protocol. It extends the ownership and availability rules already enforced by
`CyborgProvisioner`; the native handle must never be copied into
`RuntimeSnapshot.metadata`, `ApplyResult.details`, a receipt, a diagnostic, or
a component status mapping. Provisioning replacement, action execution, reset,
stop, and cleanup all pass through the same owner so no operation can race a
turn or use a retired handle.

## Canonical incumbents

| Concern | Canonical owner to reuse | CybORG boundary |
| --- | --- | --- |
| Target and capability shape | `BackendManifest`, `BackendCapabilitySet`, `OrchestratorCapabilities`, `ParticipantRuntimeCapabilities`, `TimeCapabilities`, `RuntimeTargetComponents`, and `RuntimeTarget` | Extend `create_cyborg_manifest`, `create_cyborg_components`, and `build_runtime_target`; let controlled-vocabulary, required-contract, component-presence, and method-signature validation run. Declare only the components and exact features exercised by tests. |
| Orchestration input and readback | `OrchestrationPlan`, `OrchestrationOp`, `WorkflowExecutionState`, `WorkflowHistoryEvent`, and RAES workflow result-contract validation | Consume admitted operations and `startup_order`; do not create a CybORG step-plan schema. Publish workflow state/history only for actual compiled workflow entries and preserve the compiled execution/result contract. |
| Action admission and normalization | `ParticipantActionAdmissionRequest`, `ParticipantValidatedActionSelection`, `bind_participant_decision_surface_selection`, and `raes_processor.models.resolve_participant_action_arguments` | Require the already validated selection and exact action/argument-shape join. Backend admission checks only whether that normalized meaning has an evidence-backed CybORG binding; it must not parse the original proposal or reimplement defaults, omission, cardinality, enum, range, or canonical-order validation. |
| Participant lifecycle and action commit | `BaseParticipantRuntime`, `ParticipantNativeActionExecution`, `ParticipantActionApplyResult`, `ParticipantActionResultModel`, `participant_action_binding_events`, and `participant_behavior_event_payload` | Reuse the RUN-311 episode state machine and standard attempted/transition/terminal-observation events. Override only the private native action hook and native reset mechanics. Require a typed terminal result for every admitted action. |
| Action semantics and failure mapping | The compiled `ParticipantActionContractRuntime`, `validate_participant_action_result_contract`, and `map_backend_diagnostic_to_participant_failure` | When the exact compiled contract is available through a public RAES runtime context, use its validator to preserve action-instance, participant, live episode, action-contract, observation-point, target, declared precondition/effect, failure-class, and evidence joins. Do not reconstruct that contract locally or infer portable effects from a native success boolean, especially for the qualified `Remove` defect. |
| Shared state and realized order | `ParticipantSharedStateRecordModel`, `ParticipantSharedStateAccessModel`, `ParticipantJointActionRecordModel`, `ParticipantJointActionAccessSetModel`, `ParticipantTimeManagementContextModel`, and the RUN-307/RUN-308 validators | Project only mapped revisions/digests and portable references. `realized_order` is an exact permutation of behavior-event references, not native action ids or class names. Use `backend_serialized` only with its required clock and ordering basis. |
| Logical time and reset | `ReferenceTimeRuntime`, `TimeCoordinator`, `apply_logical_clock_transition`, time-model validators, `CoordinatedParticipantResetRuntime`, and `CoordinatedParticipantTimeRuntime` | Use the admitted declaration and snapshot state; do not maintain a parallel `step_count`. Claim coordinated reset only when native session, participant episodes, and clock commit or fail together. |
| Receipts, status, and persistence | `RuntimeControlPlane`, `OperationReceipt`, `OperationStatus`, `ControlPlaneOperationRecord`, and `ControlPlaneStore` | Let the control plane allocate and persist operation identity, enforce idempotency, and expose status. The adapter returns `ApplyResult`/`ParticipantActionApplyResult`; it does not mint a second receipt or repository. Use the portable action instance as the caller's stable idempotency/correlation input where the calling surface permits it. |
| Boundary validation | `RuntimeManager`/`RuntimeControlPlane` backend-call gates; workflow, participant-history, shared-state, concurrency, time, snapshot-transition, and changed-address validators | Exercise every portable result through the public manager/control plane. Never import or fork private `_call_backend_apply` or result-contract helpers. |
| Projection and failure hygiene | `project_action`, `project_observation`, `redact_native_value`, `bounded_context_label`, `Diagnostic`, `diagnostic_model`, and `ApplyResult` | Native inputs/outputs remain private. Projection failures use stable bounded messages and the baseline portable snapshot; never include the rejected value or native exception text. |
| Stochastic control | `ExperimentStochasticControlModel`, `ParticipantStreamAddressModel`, `apply_seed_controls`, the RAES random-stream engine/profile loaders, and the existing realization envelope | Keep simulator, Python, NumPy, wrapper/action-space, scheduler, red/green policy, blue policy, and evaluator streams separate. Report applied, unbound, unsupported, and failed controls; application is not a determinism claim. |

`CyborgDriver` remains a backend-local protocol. Its action seam should be a
closed dispatch over exact admitted action-contract bindings and normalized
arguments, returning a private native turn result. Do not create an action
registry DTO, native action-id table, generic Gym action model, or another
protocol family. Native constructor/class selection must remain fixed module
code backed by the pinned source profile, not a caller-supplied import path.

`ParticipantExecutionBinding` is the RAES portable claim for autonomous
scheduler-to-native bindings, but its enclosing
`ParticipantRuntimeCapabilities` validator requires the complete autonomous
execution-control and bounded-concurrency capability set. Do not populate that
field or advertise RAES autonomous execution merely to describe red/green
operations that CybORG schedules internally. If a later increment integrates
the RAES autonomous scheduler, it must use `ParticipantExecutionBinding` and
satisfy that complete validator; issue #16 must not bypass it with a partial
lookalike.

## Public seam constraints

Two RAES 2.0.0 limits are architectural boundaries, not invitations for local
schemas:

- `ParticipantRuntime.admit_action` receives a
  `ParticipantActionAdmissionRequest`, not the full compiled
  `ParticipantActionContractRuntime`. The request validates identity,
  selection, exposure, and result joins, while the richer
  `validate_participant_action_result_contract` requires the compiled contract
  to validate declared preconditions, effects, failure classes, and evidence.
  Use that richer validator only through an existing public runtime context
  that actually carries the exact compiled contract. If no such context is
  available on the chosen call path, do not copy the contract into an adapter
  DTO or claim that model construction alone proves full semantic conformance;
  a stronger boundary requires an upstream RAES context/API change.
- The control plane allocates `OperationReceipt.operation_id` before invoking
  the backend but does not pass it to `admit_action`. Consequently the adapter
  cannot embed the actual receipt id into an execution-attempt behavior event.
  Keep control-plane receipt/idempotency correlation and action-instance joins
  distinct. An embedded receipt/action foreign key likewise requires an
  upstream RAES API change.

## Admission, effect, and commit boundary

Every check that can be completed without native effects happens before the
driver is called: published request type, live session and episode, admitted
run state, non-terminal logical coordinate, expected sequence, exact action and
implementation binding, action-instance uniqueness/idempotency, target closure,
validated argument selection, and backend representability. An unmapped action,
unknown/extra argument, target mismatch, stale episode/generation, duplicate
with a different fingerprint, or exhausted trial returns bounded RAES
diagnostics with zero driver calls and an unchanged snapshot.

One admitted action causes at most one mutating driver operation. The operation
returns one private result which is projected once into one terminal
`ParticipantActionResultModel`; the standard participant binding events then
carry that same action instance, participant, episode, action contract,
observation point, preconditions, effects, and result. Do not treat native red
or green policy choices as additional external admissions, and do not call
`CybORG.step` once per projected participant occurrence.

Portable commit is all-or-nothing across the action result, behavior histories,
shared-state records/history, joint-action/time context, and clock transition.
Construct and validate every candidate RAES value before returning the new
snapshot. RAES's backend-call gate can restore the baseline *portable*
snapshot, but it cannot undo a CybORG mutation. If a driver call raises, returns
an invalid shape, cannot be fully projected, or produces contradictory joins,
the adapter must mark the native session unavailable and reject all further
turns until an admitted reset/reconstruction succeeds. Returning the baseline
snapshot while continuing to use the already-mutated native handle is
prohibited split-brain behavior.

Do not fabricate a receipt id or claim that a backend-generated `operation_ref`
is the control-plane receipt. Preserve receipt-to-request correlation through
the existing control-plane idempotency/fingerprint record and preserve action
joins through `action_instance_id`.

## Logical step, terminal, reset, and stochastic semantics

The logical origin is the admitted initialized coordinate before any native
turn. Trial length `N` permits exactly `N` successfully committed aggregate
turns: the Nth commit advances the logical clock to tick `N`, applies the
admitted terminal rule, and prevents an N+1 driver call. Test 30, 50, and 100 as
parameters over the same mechanism; do not hard-code branches for those three
values.

Keep these facts separate in state and diagnostics: native source terminal,
wrapper `max_steps`, admitted trial limit, evaluator cutoff, participant episode
termination, truncation, interruption, reset, replay, and cleanup. A single
native `done`/tuple member is not an admissible terminal model. Early source
termination and the admitted length cutoff use their declared RAES terminal
reasons; if the compiled policy does not state how to interpret a native
terminal fact, reject or disclose it rather than inventing a reason.

Reset is not cleanup and replay is not reset. A successful trial reset must
establish a new participant episode chain, a new logical-time segment under the
admitted reset behavior, and a known native session state. If CybORG cannot make
that transition atomically, reconstruct the aggregate before publishing
success and do not advertise coordinated-reset capability.

The existing target `seed` records construction control only. Step-time native
policies use additional process-global and library random sources identified by
qualification. Any process-global stream used during a turn must be isolated
under the existing native-random lock by installing the session's saved state,
capturing its successor state, and restoring the caller's state; other streams
need equivalent explicit bindings or an `unbound`/`unsupported` disclosure.
Controlled-seed tests prove the declared control facts and ordered draw
addresses. They do not claim identical observations, rewards, state, or
outcomes, and must retain `loss-evaluation-seed-unbound` where it applies.

## Cross-cutting layers

| Layer | Required treatment |
| --- | --- |
| Closed input/config shapes | Keep `_normalized_config` as the source/profile/version/ledger/seed/driver authority and continue rejecting unknown keys. Trial length, participant implementation, ordering, action meaning, and terminal policy come from admitted RAES plans/contracts, not environment variables or ad hoc target flags. Driver injection remains a test/mechanical seam, never an import-string or native-class selection surface. |
| RAES model and semantic validation | Pass through `OrchestrationPlan` address/domain validation; participant decision-surface and argument normalization; manifest capability/required-contract validation; `RuntimeTarget` presence/signature checks; participant action/result joins; workflow/history/shared-state/concurrency/time validators; and final snapshot-transition validation. Backend checks add only CybORG representability and pinned-source mappings. |
| Authentication and authorization | Issue #16 adds no HTTP/controller/auth surface. In-process calls rely on the existing manager/control-plane boundary. Any later network exposure must use `create_control_plane_app` with `ControlPlaneSecurityConfig.strict_defaults`, verified identity, role/target authorization, request-size limits, denial audit, and the redacted exception handler; no adapter endpoint is permitted. |
| Secret handling | No secret is needed. Do not read secret stores, accept credentials in action arguments for this mapping, inspect environment values, or expose governed entropy. Native learned credentials, hidden truth, sessions, and source observations remain private even when they influence a bounded portable effect. |
| OS/process exposure | Execution remains in process and reuses the verified private source snapshot and private scenario file from `SourceInstalledCyborgDriver`; no new subprocess, shell, network fetch, plugin discovery, or forwarded environment is introduced. Native paths, argv/environment mappings, stdout/stderr, and temporary filenames never enter portable output. |
| Error envelopes and observability | Use RAES `Diagnostic`/`ApplyResult` and the base default-deny redaction helpers. Messages contain only stable codes, published addresses, stage/disposition, and bounded counts. Standard module logging, if needed, follows the same allowlist; never log actions/arguments, native observations, rewards, objects, paths, random state, rejected values, exception text, or tracebacks. |
| Persistence | The adapter keeps only ephemeral native session mechanics. `RuntimeControlPlane` and its configured `ControlPlaneStore` own snapshots, receipts/status, idempotency records, and audit. Do not add an adapter database, replay cache, receipt store, evidence repository, or write participant state into free-form metadata. |
| Packaging and workflow | Keep CybORG imports behind the module boundary and preserve the single `pyproject.toml`/`uv.lock`. Reuse `_verification_envs()`, the existing qualification verifier, tests session, clean-install distribution proof, docs build, and canonical `nox -s verify` graph. Do not add a second CI workflow, fixture corpus, conformance profile table, or simulator registry. |

## Extension seam

The extension seam is an exact, ordered action-binding/turn-policy selection:
published RAES action-contract addresses and admitted normalized selections on
the portable side; module-private translator callables and pinned CybORG
operations on the native side. Trial length, red-policy implementation, and
seed/stochastic bindings are values in the admitted run/apparatus contracts,
not branches in the driver. A future blue action, green policy, red variant,
trial length, or reviewed CybORG source profile therefore adds evidence and one
binding/selection without changing the portable result, clock, receipt,
diagnostic, or session-ownership architecture. A future move to RAES-managed
autonomous scheduling replaces that private scheduling selection with the
published `ParticipantExecutionBinding` capability path; it does not weaken its
validators.

## Gotchas and anti-patterns

- Do not add a public `step`, `Turn`, `Action`, `Observation`, or `Result` DTO;
  the published RAES protocols and closed models already own those meanings.
- Do not let Orchestrator and ParticipantRuntime each call the native step, or
  let a background RAES participant clock driver race the backend-serialized
  CybORG turn. Declare only scheduling/concurrency capability that the selected
  execution path actually provides.
- Do not equate one blue submission with one blue-only native effect. The
  aggregate turn must retain red/green/backend/evaluator ordering and project
  participant identities separately.
- Do not dispatch by native action id, class-name string, address suffix, dict
  insertion order, or unvalidated target name. Dispatch only an exact admitted
  binding with normalized arguments and confined target translation.
- Do not repeat RAES argument normalization or action-result semantic
  validation in adapter code. CybORG validation answers only whether an already
  admitted portable meaning is supported by the pinned backend.
- Do not stringify, serialize, hash by `repr`, or recursively inspect native
  objects. A digest is portable only when derived from a deliberately projected
  canonical RAES value, never an opaque native representation.
- Do not use `RuntimeSnapshot.metadata` or `ApplyResult.details` as a semantic
  escape hatch for native state, counters, reward, terminal facts, histories,
  or joins.
- Do not return success after partial projection, swallow a native mutation
  failure, retry an effectful action blindly, or continue using a quarantined
  session. Idempotent receipt replay is not permission to execute twice.
- Do not infer that seed application, equal logical histories, or a passing
  controlled suite proves deterministic CybORG outcomes. Preserve every
  uncontrolled-source disclosure.
- Do not silently repair the selected source's Remove misreport, wrapper cutoff
  ambiguity, evaluator seed gap, blue-policy artifact gap, or other qualified
  loss to satisfy a test.

## Non-goals and implementation boundaries

- No CAGE-specific SDL, schema, vocabulary, conformance profile, fixture corpus,
  portable action registry, diagnostic envelope, exception hierarchy, store,
  audit service, or policy gate is introduced.
- No Gym/PettingZoo wrapper protocol, action-id translation surface, raw native
  observation, reward vector, hidden truth payload, log, native object, or full
  traceback becomes portable.
- Issue #16 does not establish reward/scoring projection, objective
  satisfaction, evidence capture, derived measures, outcome equivalence, or
  deterministic replay. Native evaluator ordering may be observed without
  advertising a RAES Evaluator.
- Issue #16 does not publish a patched CybORG artifact, populate the optional
  extra, change the selected source/qualification/legal decision, add network
  service configuration, or introduce durable adapter state.
- Supporting B-line, Meander, Sleep, representative blue actions, and green
  behavior proves only the declared mapped execution-control subset. It does
  not imply support for every native action, policy, scenario, participant
  feature, concurrency mode, or future CybORG revision.
