# CybORG participant episode and observation guardrails

GitHub issue #17 is the authority for this increment. This note fixes the
portable/native boundary, lifecycle coordination rule, disclosure path, and
claim limits that implementation must preserve. It adds no adapter contract and
is not an implementation plan. The logical-step, transaction, stochastic, and
quarantine rules in `cyborg-step-control-guardrails.md` remain in force.

## One shared native session, three portable participants

CAGE-2 red, green, and blue are three stable RAES participant identities over
one aggregate native CybORG environment. Their portable episode state,
observation projection, action authority, behavior history, and implementation
apparatus stay distinct even though a blue admission triggers the one shared
native turn.

These identities are not aliases:

| Identity | Meaning and owner |
| --- | --- |
| `cyborg-cage2` | Backend/target identity owned by the manifest and target. |
| workflow address/run id | Orchestration identity owned by the compiled plan and workflow result contracts. |
| evaluator identity | Absent until a RAES evaluator is implemented; native reward calculation does not create one. |
| control-plane caller/receipt | Operator/authentication and operation identity owned by `RuntimeControlPlane`; it is not a participant. |
| red, green, blue participant addresses | Stable semantic actors whose episode chains and participant-visible data are isolated by address. |
| red policy, blue implementation, green behavior | Apparatus/implementation identities selected by the admitted experiment or scenario; they never replace participant identity. |
| native agent name, action class/id, object handle | Driver-private source coordinates with no portable identity status. |

The current `CyborgProvisioner` session owner, execution generation, quarantine
state, and re-entrant `execution_transaction()` lock remain the single native
mutation boundary. Initialize, reset/restart, terminate, action execution,
projection commit, orchestration state, time state, replacement, and cleanup
must not race or acquire a second session owner.

## Canonical incumbents to compose

| Concern | Canonical incumbent and required use |
| --- | --- |
| Episode lifecycle | `BaseParticipantRuntime` plus `ParticipantEpisode*Request`, `ParticipantEpisodeExecutionState`, and episode history models. Reuse its identity allocation, sequence increment, previous-episode linkage, legal-state checks, and append-only history. Override only behavior forced by the shared native session. |
| Aggregate reset | `CoordinatedParticipantResetRuntime`, `BaseParticipantRuntime.reset_many`, `ReferenceTimeRuntime`, RAES time transition validation, and the existing CybORG transaction/quarantine boundary. A successful native reset is one atomic red/green/blue episode and clock-segment transition. |
| Action admission | Compiled participant behavior, `ParticipantDecisionSurfaceModel` or the declared v2 surface, `bind_participant_decision_surface_selection`/v2 binding, `ParticipantActionAdmissionRequest`, `ParticipantValidatedActionSelection`, and the existing exact CybORG action translator. The adapter checks backend representability only after RAES validates authority, exposure, targets, and argument shape. |
| Outcomes and behavior | `ParticipantNativeActionExecution`, `ParticipantActionApplyResult`, `ParticipantActionResultModel`, `participant_action_binding_events`, `participant_behavior_event_payload`, and the published action-result contract validation. Preserve the controlling participant, live episode, action instance, action contract, observation point, and terminal status joins. |
| Observations | `ParticipantObservationEnvelopeModel`, its loss/stochastic/source-status models, compiled observation boundaries, and the source-ledger observation mappings/loss disclosures. Publish a deliberately constructed participant-relative envelope; never sanitize and forward a native observation mapping. |
| Action availability | The RAES participant decision-surface action entries/forms and their binding validators. Eligibility/support is derived at an exact participant/episode/sequence cut. A native mask or action-space tuple may inform private projection but is never the portable surface. |
| Histories and joins | `RuntimeSnapshot` participant episode/behavior carriers, `ParticipantSharedStateRecordModel`, `ParticipantJointActionRecordModel`, `ParticipantTimeManagementContextModel`, and RUN-305/307/308 validators. Keep per-participant streams append-only and join shared records by portable episode/action/event refs. |
| Retrieval and isolation | `ParticipantRetrievalMixin` and `ParticipantStatusViewModel`, `ParticipantHistoryViewModel`, and `ParticipantContextViewModel`. Reuse participant-and-episode filtering; do not expose the runtime's private observation cache or another participant's history through a generic status mapping. |
| Boundary validation | `RuntimeManager`/`RuntimeControlPlane`, `_call_backend_apply` as reached through their public methods, `participant_runtime_state_contract_diagnostics`, `participant_runtime_history_transition_diagnostics`, snapshot/changed-address validation, and published conformance fixtures. Do not import private manager gates into the adapter. |
| Failure hygiene | RAES `Diagnostic`, `ApplyResult`, `ParticipantActionApplyResult`, base redaction/projection helpers, and the existing bounded CybORG failure codes. Rejection, timeout, reset failure, post-effect projection failure, and cleanup failure all use allowlisted portable facts. |
| Persistence and receipts | `RuntimeControlPlane`, `ControlPlaneStore`, `OperationReceipt`, operation status, and idempotency records. The adapter owns only ephemeral session/projection mechanics and adds no receipt, repository, cache, audit log, or replay store. |

`raes_adapters.base` remains optional mechanical plumbing, not the owner of a
participant schema, observation vocabulary, exposure policy, lifecycle
controller, exception hierarchy, fixture corpus, or store. The other backend's
`CyberBattleSimParticipantRuntime` is a useful example of composing
`BaseParticipantRuntime` and `ParticipantObservationEnvelopeModel`; its
single-participant reset behavior and source-specific observation semantics are
not reusable CybORG authority.

## Lifecycle coordination and fixture applicability

Portable participant chains are independent; native reset/reconstruction is
aggregate. Preserve both facts rather than collapsing one into the other.

- Initialization may create each declared participant's initial portable
  episode without reconstructing an already provisioned aggregate, but action
  readiness requires the admitted workflow, healthy native session, clock, and
  all three expected running episode heads. Unknown participant addresses fail
  before changing the snapshot.
- Reset of the native trial is valid only as one complete red/green/blue batch.
  It creates three new episode ids, increments each participant's sequence once,
  links each new head only to that participant's predecessor, starts one new
  logical-time segment, clears episode-scoped projected observations/action
  surfaces, and resets or reconstructs the native aggregate exactly once.
- Restart has the same aggregate rule after the required terminal predecessors.
  Do not implement it as a reset alias, and do not restart one participant while
  silently changing the other two participants' native state.
- Termination reason, source terminal, logical-step cutoff, timeout,
  interruption, reset, restart, workflow completion, and native cleanup remain
  distinct. Any condition that makes another aggregate turn impossible closes
  action readiness consistently; it does not fabricate evaluator state.
- Failed lifecycle operations return the exact predecessor portable snapshot,
  restore every participant, orchestrator, control, clock, and cache mirror or
  counter changed while staging, and either prove native state was unchanged or
  quarantine it. Observation/action-surface caches follow the same
  commit/rollback boundary. Validate the complete candidate before an effect
  where possible; an outer manager rollback cannot repair adapter-owned memory
  or an already-mutated native session.

RAES 2.0.0's generic live target probe submits initialize, reset, terminate, and
restart for one synthetic `participant.conformance` address. That probe is not
an applicable proof of a fixed three-member aggregate runtime: accepting it
would require an undeclared participant and a single-member native reset.
Apply the published lifecycle models, semantic validators, and fixture
expectations to each red/green/blue chain inside the coordinated transition.
Do not claim the generic probe passes unless RAES provides an aggregate-aware
fixture/call path or the adapter can satisfy its single-participant semantics
without affecting the shared native session. Do not copy or weaken the fixture
to make it pass.

The manifest may advertise coordinated participant reset only when the exact
RAES capability dependencies and public call path are executable. A private
`reset_many` method or a direct unit test alone is not a capability claim.

RAES 2.0.0 does not publish a coordinated participant-restart protocol. Its
published `ParticipantRuntime.restart` request addresses one participant, while
restarting CAGE-2 native state necessarily changes the aggregate. Do not add a
CybORG-only `restart_many` protocol or reinterpret one participant's restart
request as authority to create sibling episode ids. If the individual contract
cannot be honored without changing sibling native state, treat coordinated
restart as an upstream contract/call-path gap and do not claim that acceptance
criterion until the published boundary resolves it.

Individual termination remains an episode-state transition, not native reset or
cleanup authority. Terminating one participant closes aggregate action readiness
because a valid turn requires all three running heads, but it must not fabricate
terminal events for the siblings. A source-native aggregate terminal may close
all three chains under the existing transaction only by producing a separately
typed terminal transition for each participant; workflow completion, participant
termination, and native cleanup still remain distinct.

## Observation, availability, and exposure boundary

The source ledger is the evidence authority for what can be projected. In
particular, `scenario-initial-knowledge`, `observation-visibility`,
`observation-hidden-truth`, `observation-native-shape`, and
`control-admissibility` distinguish participant-relative source facts from
hidden truth and native representation. A source field not covered by an
admitted mapping is withheld, not copied into a free-form detail field.

Every observation and decision surface is bound to one participant address,
one live episode id, a monotonic sequence/observation cut, its compiled
observation boundary, and the controlling action when applicable. Red, green,
and blue projections are built independently. The same private native turn may
be their provenance, but one participant's envelope may not contain another
participant's observation, availability, implementation identity, history, or
hidden source coordinates.

Projection is default-deny and constructive:

- create the published RAES model from explicitly mapped portable facts;
- keep `hidden_state_refs` and `centralized_state_refs` empty unless an admitted
  portable reference is both semantically required and authorized by the exact
  exposure policy; a native truth key/value is never such a reference;
- record unavoidable loss through the envelope's loss/redaction fields and the
  checked-in loss-disclosure refs, not through native values;
- derive stable refs from portable episode/action/sequence coordinates, never
  native ids, dictionary keys, paths, hashes of native serialization, or
  `str`/`repr`;
- return immutable/defensive participant-scoped readback, and clear only
  episode-local caches after a successful coordinated reset/restart;
- apply the same allowlist to success, rejected action, timeout, reset,
  projection failure, diagnostics, status, history, and logs. Failure paths do
  not gain a debug exception to the exposure policy.

Action availability is an input to RAES admission, not an after-the-fact
description of what CybORG accepted. A selection must join the exact delivered
decision surface/cut, compiled behavior and action contract, implementation and
exposure selection, observation boundary, target closure, and normalized
argument shape before any driver call. Ineligible, unsupported, stale,
cross-participant, cross-episode, or withheld selections have no native effect,
clock advance, history append, shared-state write, or cache mutation.

Use the one decision-surface contract version selected by the admitted RAES
artifacts and its matching binder end to end. Do not emit v1 and v2 in parallel,
locally translate between them, or weaken v2 derivation-anchor, delivery, memory,
digest, evidence, and provenance requirements to fit a private cache.

RAES 2.0.0's published `ParticipantRuntime` protocol exposes lifecycle,
admission, status, episode results, and episode history; `RuntimeSnapshot` has no
carrier for observation envelopes or decision surfaces. The existing
`CyberBattleSimParticipantRuntime.observations()` helper demonstrates safe local
projection mechanics, but it is not a published portable retrieval boundary.
Consequently, a CybORG-only observation/surface getter, a private cache, or a
model-construction unit test cannot by itself satisfy issue #17's published-
boundary acceptance claim. Use an exact public RAES carrier/retrieval path if
one is available at implementation time; otherwise record the upstream contract
gap, keep any cache ephemeral, and do not smuggle envelopes through snapshot
metadata, `ApplyResult.details`, component status, behavior-event details, or an
operation receipt.

## Cross-cutting security and whole-repository path

| Layer the design passes | Required treatment |
| --- | --- |
| Source/profile authority | `qualification.json`, the selected-source verification in `SourceInstalledCyborgDriver`, the CAGE-2 source ledger, and loss disclosures remain the only native mapping authority. No runtime discovery, unqualified source fallback, or caller-selected class/import path. |
| Target config shape | `_normalized_config` and `_validate_selection` continue to reject unknown keys and mismatched profile/version/commit/ledger/seed/driver values. Participant identities, policies, boundaries, availability, and episode values come from admitted RAES artifacts, not new flags or environment variables. |
| Published model parsers | Closed RAES contract constructors validate episode requests/state, observation envelopes, decision surfaces, implementation/exposure selections, action admissions/results, shared-state/joint/time records, and diagnostics. Adapter checks do not duplicate enum, shape, or semantic validation. |
| Manifest/target shape | `create_cyborg_manifest`, `create_cyborg_components`, `build_runtime_target`, required-contract/capability validators, component presence, and callable signatures must agree with executable behavior. Do not claim evaluator, autonomous scheduling, bounded concurrency, generic observation service, or coordinated reset merely because a model exists. |
| Apply/transition envelope | Public manager/control-plane calls deep-copy the predecessor and validate result type, diagnostic/detail shapes, canonical addresses, changed addresses, participant snapshot semantics, append-only transitions, shared/concurrency/time joins, and workflow state. Post-effect validation failure quarantines the native session because portable rollback cannot undo it. |
| Authorization/exposure | Compiled participant behavior, decision-surface binding, implementation selection, exposure-policy refs, observation-boundary evidence refs, target/generation checks, and participant-scoped retrieval all fail closed. Another participant, caller, backend, or evaluator identity grants no participant visibility. |
| Secret surface | No secret is required or read. Native credentials, learned sessions, environment values, entropy state, tokens, and authentication material stay driver-private and never enter arguments, snapshots, evidence, refs, diagnostics, status, logs, or tests. |
| OS/process surface | Execution remains inside the verified private source snapshot and confined temporary scenario workspace already owned by the driver. Add no subprocess, shell, inherited environment forwarding, argv payload, stdout/stderr capture, socket, runtime download, plugin discovery, or persistent native file. Temporary paths never become portable refs. |
| Error/log envelope | Use stable RAES/CybORG diagnostic codes and bounded messages containing only published addresses, safe stage/disposition, and counts. Never interpolate requests, arguments, native observations/masks/tuples/ids, exception text/args/causes, object types derived from hostile values, paths, logs, or tracebacks. Module logging, if added, uses the same allowlist. |
| Authentication if later networked | Issue #17 adds no controller or route. A later network surface must reuse RAES `create_control_plane_app` with `ControlPlaneSecurityConfig.strict_defaults`, verified identity, role/target authorization, request-size limits, denial audit, and redacted exception handling; no adapter endpoint. |
| Persistence/idempotency | `ControlPlaneStore` and operation receipts own durable snapshots, idempotency, status, and audit. Action instance id remains the participant/action join; it is not a fabricated operation receipt. Do not persist native handles or episode-local observation caches. |
| Packaging/workflow | Keep lazy CybORG imports, the single `pyproject.toml`/`uv.lock`, `_verification_envs()`, existing qualification check, tests/type/lint/policy/docs/distribution sessions, and canonical `nox -s verify`. Add no extra lock, workflow, schema bundle, conformance corpus, or validator script. |

## Extension seam

The extension seam is one backend-private selected-profile binding plus an
evidence-backed projection selected by the tuple of participant address,
compiled observation boundary, admitted action contract, and exact
episode/sequence cut. That binding is the single mechanical source for the
profile-required roles, source turn order, role-to-admitted-participant join,
and profile evidence refs; participant addresses and implementation selections
still come from admitted RAES artifacts. It is not a portable concept catalog
or registry.
The portable side remains the published observation envelope, decision surface,
action result, and history contracts. The native side remains fixed driver code
for the pinned source profile.

A future mapped red/green external action, blue implementation, observation
field, action contract, red policy, or reviewed source profile should add one
evidence-backed projection/binding without changing lifecycle contracts,
participant retrieval, error envelopes, receipts, persistence, or shared base
semantics. Do not promote the seam into a generic adapter registry until a real
second backend shares mechanics that RAES does not already own.

## Gotchas and anti-patterns

- Do not use role labels, native agent names, policy class names, or backend
  identity interchangeably with participant or implementation identity.
- Do not duplicate the participant roster, role mapping, or source turn order in
  driver, runtime, projection, and tests; select it once from the pinned
  backend-private profile binding and validate projected occurrences against it.
- Do not let `BaseParticipantRuntime` accept an undeclared fourth participant,
  and do not fork its episode schema, counter, linkage, or history logic.
- Do not reset/restart the native aggregate for one participant while leaving
  the other portable episode heads unchanged. Do not present three sequential
  partial resets as atomic.
- Do not clear append-only episode/behavior history on reset, merge participant
  histories into a global list, or key current observations only by native step
  number. Episode identity is part of every cache and foreign-key scope.
- Do not expose a native observation dictionary, action mask, Gym/PettingZoo
  tuple, native action/node/session id, reward vector, raw log, exception text,
  object representation, hidden truth, or a hash/ref derived from any of them.
- Do not treat emptying a payload after broad serialization as redaction.
  Construct the allowed RAES projection without traversing forbidden values.
- Do not equate action visibility with eligibility, eligibility with backend
  support, backend support with authority, or native success with a validated
  portable effect/outcome.
- Do not append a rejected action as a successful occurrence, advance time, or
  mutate shared-state/action-surface caches. Rejection history, if required by
  the published binding contract, must remain typed and exposure-safe.
- Do not reuse a stale delivered decision surface after reset/restart or an
  interleaved participant turn; its episode/sequence cut must still match.
- Do not continue after native mutation plus failed projection/validation.
  Quarantine and require admitted aggregate recovery; never retry blindly.
- Do not use `RuntimeSnapshot.metadata`, `ApplyResult.details`, component
  `status()`, or diagnostics as an escape hatch for observation content,
  native state, cache state, or identity joins.
- Do not modify source-ledger/loss facts merely to make a projection test pass,
  and do not infer observation or outcome equivalence from bounded projection.

## Non-goals and implementation boundaries

- No new RAES schema, SDL vocabulary, participant protocol, observation model,
  decision-surface model, exposure policy, exception hierarchy, store,
  conformance profile, fixture corpus, or workflow controller is defined here.
- No evaluator, reward/scoring projection, objective truth, derived measure,
  scientific equivalence, exact replay, deterministic-outcome, or full CAGE-2
  action/observation coverage claim is added by issue #17.
- No external red/green admission or RAES autonomous scheduler capability is
  implied by projecting their native occurrences and participant-relative
  observations from the aggregate turn.
- No HTTP API, authentication mechanism, CLI, daemon, subprocess launcher,
  environment-binding shape, runtime fetch, durable adapter persistence, second
  distribution/lockfile, or CI workflow is introduced.
- No selected source, qualification profile, packaging route, source-ledger
  disposition, loss disclosure, or known-defect interpretation changes without
  its separately governed evidence update.
