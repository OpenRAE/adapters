# PrimAITE backend architecture guardrails

GitHub issue #41 is the authority for the backend deliverable. This record fixes
the boundaries that implementation must respect; it is neither an implementation
plan nor a new RAES contract.

## Admission and claim boundary

The selected profile is PrimAITE v4.0.0 at commit
`98617981d7f6ae2c3ffd9a8cc39944e05c9a09ea`, the checked-in
`data_manipulation` configuration, and the immutable `DATA_MANIPULATION`
evidence selection. The qualification admits that profile while retaining these
limitations:

- there is no public index distribution or upstream release wheel;
- the dependency graph is a dated, unpinned snapshot and includes undeclared
  runtime dependencies;
- the public seeded-reset seam fails on the qualified no-RL route, and GREEN
  randomness remains uncontrolled;
- the smoke was qualified on CPython 3.11 while this repository requires Python
  3.12 or newer; and
- participant and network controls are abstracted, and fixed-horizon truncation
  is the only source terminal.

The manifest and run evidence may claim the attested source identity, attested
protocol configuration, partial execution control, attestable run evidence, and
stochastic-bounded outcome reproduction already recorded by qualification. They
must not upgrade those facts to automatic installability, deterministic replay,
full dependency attestation, exact interface equivalence, or goal-based
termination. A source-backed claim on Python 3.12 needs new bounded qualification
evidence; package metadata that merely permits 3.12 is not that evidence.

## Keep the concepts separate

| Concept | Boundary |
| --- | --- |
| Qualification and source ledger | Backend-local evidence and claim limits. They are not a manifest, scenario, runtime result, or portable schema. |
| Authored scenario and experiment contracts | Portable topology/objective intent plus published episode/evaluation controls. They are not native configuration, an action map, live state, or an execution workflow. |
| Backend manifest | A validated declaration of implemented RAES capabilities and limitations. It is not an installation recipe or qualification record. |
| Provisioned target | Portable RAES state and references for the selected realization. It never owns or exposes a native environment. |
| Participant action | A validated RAES request and typed terminal result. A contract family is not a PrimAITE action index or an exact operation variant. |
| Simulator turn, orchestration, and time | One BLUE admission, the source's aggregate BLUE/RED/GREEN turn, workflow state, and logical time are related but distinct transitions. |
| Participant observation and evaluation | Participant-relative disclosure is separate from hidden source state, objective truth, scalar reward, evidence, and derived measures. |
| Termination, reset, and cleanup | Gym `terminated`, Gym `truncated`, logical cutoff, participant lifecycle, aggregate reset, and verified cleanup are distinct facts. |

Do not conceal a mismatch between these layers behind a generic
`environment`, `step`, `done`, `result`, `profile`, or `state` abstraction.

## Compose the canonical incumbents

`raes_adapters.base` remains mechanical plumbing and published RAES contracts
remain semantic authority. Implementation must build on these incumbents:

| Concern | Canonical incumbent and required use |
| --- | --- |
| Selected evidence | `raes_adapters.primaite.scenario_ledger.DATA_MANIPULATION`, its `EvidenceSelection`, `qualification.json`, `public-protocol.md`, SDL, experiment task/spec, source ledger, and loss disclosures. Consume the selection and its pinned digests; do not repeat an independent set of constants. |
| Evidence validation | `raes_adapters._scenario_ledger.ScenarioLedger` and the existing PrimAITE qualification/ledger tests. Extend that evidence closure before using a new source symbol or field as a semantic or capability claim. |
| Target configuration | A module-local closed normalizer/selection gate, following the established `cyborg.target._normalized_config()` and `_validate_selection()` shape without importing backend code. Accept only the evidence selection and an explicit driver/factory seam; reject unknown keys, native paths or identifiers, source aliases, and seed overrides. |
| Installed-source proof | The pre-import sequence established by `CyberBattleSimDriver`: distribution identity/version, direct-install provenance, complete import-root membership and digest, selected-artifact digests, and resolved module origin. Reuse the verification pattern, not another backend's private code or evidence values. |
| Packaging and isolation | `pyproject.toml`, the single `uv.lock`, ADR-003, and `_extras()`, `_verification_envs()`, and `_distributions()` in `noxfile.py`. The already declared dependency-light `primaite` extra must leave base-only and unrelated-extra installs unchanged. Add `tool.uv.conflicts` only if a governed PrimAITE stack actually enters the lock and proves incompatible. |
| Manifest | RAES `BackendManifest`, its capability models and supported-contract catalog, and `backend_manifest_v2_model()` / `backend_manifest_payload()`. Never hand-author manifest JSON, a capability vocabulary, or a supported-contract registry. |
| Manifest claim evidence | `backend_manifest_payload()` plus the exact affirmative-pointer/evidence-closure pattern in the Cyborg and CyberBattleSim conformance probes. Every positive claim needs a passing executable probe; qualification weaknesses and losses remain explicit limitations. |
| Realization disclosure | `BackendRealizationEnvelopeModel` and its digest and cross-concern validators. Bind the scenario, experiment controls, source selection, mapping losses, and stochastic disposition without copying native configuration into portable state. |
| Runtime target | `raes_adapters.base.build_runtime_target()` over RAES `RuntimeTarget` and `RuntimeTargetComponents`. Let RAES enforce component presence, capability agreement, and callable signatures; add no backend registry. |
| Runtime validation | RAES `RuntimeManager` / `RuntimeControlPlane` and their public planning, snapshot, `ApplyResult`, changed-address, workflow, evaluation, proposition, participant, time, and realization gates. Never import or fork private backend-call validators. |
| Participant lifecycle | `BaseParticipantRuntime` and `ParticipantNativeActionExecution`. Reuse their initialize/reset/restart/terminate state machine, participant and episode identities, generation, status, append-only history, sequence, linkage, and terminal results. `_model_action` is the backend-specific seam, not a second lifecycle controller. |
| Action admission | `ParticipantActionAdmissionRequest`, implementation-selection and exposure validation, `ParticipantActionResultModel`, and the published terminal-result validators. Admit the complete portable request before any native mutation. |
| Observation and retrieval | `ParticipantObservationEnvelopeModel`, published observation-boundary validation, and `ParticipantRetrievalMixin` participant/episode/audience views. No custom observation, history, or context DTO may carry native values. |
| Logical time | `ReferenceTimeRuntime`, `TimeCoordinator`, and `apply_logical_clock_transition()`. Declare the source-event-to-logical-transition mapping explicitly; a native call is not automatically a RAES tick. |
| Stochastic controls | The checked-in experiment controls, published stochastic-control models, and `apply_seed_controls()` only for real executable bindings. Broken, absent, and unbound streams remain distinct reported dispositions. |
| Workflow and evaluation | Published workflow, proposition, objective, evaluation-lifecycle, evidence, derived-measure, and `ExperimentRunModel` shapes and validators. Empty compiled SDL orchestration is valid and must not be replaced with an invented workflow. |
| Cleanup | RAES `TrialCleanupPlanModel`, `CleanupCapabilities`, `require_cleanup_plan_capability()`, `execute_cleanup()`, `TrialCleanupReceiptModel`, and its validator. Close, workspace removal, and verification are private driver operations with deterministic, idempotent outcomes. |
| Receipts and persistence | `RuntimeControlPlane` receipts/statuses and `ControlPlaneStore`. The participant result and driver-operation reference join to a receipt but do not replace it. If artifacts are written, use RAES run-artifact path confinement and atomic JSON writers, including `write_backend_conformance_report()` for the canonical report. Add no PrimAITE repository, cache, database, receipt type, filename scheme, or direct writer. |
| Failure hygiene and conformance | Base projection/redaction helpers, RAES diagnostics/results, and `run_conformance_probe()`. Use the exact RAES conformance report and cases; add no exception hierarchy, diagnostic envelope, fallback native payload, profile table, or local conformance corpus. |
| Regression patterns | `tests/test_cyberbattlesim_backend.py`, `tests/test_cyberbattlesim_conformance.py`, `tests/test_cyborg_execution.py`, and `tests/test_cyborg_conformance.py` demonstrate aggregate ownership, projection quarantine, cleanup, disclosure, and canonical conformance without making either backend a Primaite semantic dependency. |

## Driver ownership and transition rules

The legitimate backend-specific seam is a private driver bound to one immutable
evidence selection and one native environment lifecycle. It may hold native
objects, action ids, arrays, tuples, masks, `info`, reward components, source
identifiers, paths, logs, and hidden truth. None may enter a contract, snapshot,
diagnostic, receipt, history, log, stable reference, or exception message.

Provisioning accepts only a plan that joins completely to the selected scenario,
experiment controls, source configuration, and realization envelope. It creates
one aggregate native session; the portable snapshot contains only planned RAES
state and stable qualification/ledger references. Unsupported or approximate
plans fail before construction. Do not synthesize an arbitrary PrimAITE topology
from SDL or store a native handle in the provisioned target.

One admitted external BLUE action maps to exactly one driver operation and at
most one `env.step`. That source call advances the aggregate turn in which RED
and GREEN may act internally; their occurrences are not additional external
admissions or source steps. They may be projected to their own scoped portable
histories only when published RAES shapes and source evidence support the fact.
The Orchestrator does not call `env.step`, the Evaluator does not advance the
source, and observation projection does not make another source call.

The request, driver-operation reference, typed terminal result, participant,
episode, generation, action instance, and temporal observation point must form
one validated join. The operation reference is adapter-generated portable
identity, never a native action id. A control-plane receipt is a separate
operation record.
Portable admission completes before the source mutates. If native mutation
succeeds but projection or RAES validation fails, quarantine the native episode,
return the unchanged portable baseline with a bounded failure, and require an
aggregate reset/reconstruction or cleanup before another action. RAES can reject
a portable transition; it cannot roll back PrimAITE.

Reset is aggregate because all four portable participants share one native
session. Do not pretend an individual participant reset is atomic. Claim
coordinated reset or concurrency only if the implementation supplies the exact
published behavior, including failure handling and executable evidence. Source
truncation occurs on step 128; preserve that boundary without an N+1 transition
or an invented success/failure terminal.

## Hard representability gates

The present SDL action contracts describe broad families and do not carry an
operation argument. For example, `service-control` covers scan, stop, start,
pause, resume, restart, disable, and enable. The qualified smoke, by contrast,
exercises native do-nothing action `0`, for which the authored SDL has no
portable BLUE contract.

Consequently:

- do not map an existing contract to action `0` merely to make the smoke run;
- do not let a broad contract silently choose one of several native operations;
- do not expose a native action id or opaque option dictionary as the missing
  selector; and
- admit an action only when a qualified, deterministic mapping from its
  contract, portable target, and published arguments selects exactly one native
  operation. Otherwise reject it before source mutation.

If precise caller-controlled variants are required, the selector belongs in a
governed RAES participant decision-surface argument shape and arrives as a
`ParticipantValidatedActionSelection`; the evidence selection/ledger must be
revised and revalidated. It does not belong in a manifest extension, an
adapter-only DTO, or `raes_adapters.base`. The do-nothing smoke remains source
protocol evidence; it is not itself proof of portable action conformance.

Likewise, a ledger row proving that a reward family, observation boundary, or
objective exists does not prove that every live native field needed to project
it has been qualified. Before reading an additional source member for action
translation, participant observation, objective truth, reward components, or
cleanup verification, extend the source evidence closure. When a fact cannot be
evidenced, report it as unsupported, unknown, missing, or withheld as the
published model permits; never infer it from the scalar reward, flattened
observation, action choice, or total score.

The current closure pins environment, game, configuration, and probabilistic-
agent sources, but not the complete action mapping or the source members needed
for semantic reward/observation projection. Closing those gaps with digest and
mutation tests is a prerequisite to consuming the fields. A source-code guess
or an observation index copied into adapter code is not evidence.

## Cross-cutting validation and security path

The intended design is an in-process optional backend. It adds no authentication
service, HTTP route, CLI, subprocess, network fetch, credential input,
environment-binding format, or durable store.

| Layer the design passes | How it satisfies the layer |
| --- | --- |
| Source and dependency authority | Verify the selected PrimAITE distribution version, complete import-root file count/digest, critical source digests, and module origin before native import. Reject editable, directory, VCS, symlinked, patched, unexpected-file, and wrong-origin installations. The qualification attests only the PrimAITE root; Gymnasium, NumPy, setuptools, and the remaining normalized graph are observed dependency evidence, not separately attested runtime artifacts. Do not upgrade them without qualification evidence. |
| Python/runtime claim | The live source proof is currently CPython 3.11-only, while the project graph is 3.12+. Add bounded 3.12 qualification evidence before advertising or shipping a live source-backed capability there; otherwise fail the source-backed target honestly. A fake driver may test contracts but cannot upgrade the live-runtime claim. This is a completion blocker, not a limitation that a manifest note can waive. |
| Contract and config shape | Use bounded RAES parsing/compilation, closed published models, the pinned `EvidenceSelection`, and existing cross-artifact joins. Accept no arbitrary import path, native config path, action id, permissive mapping, environment override, or duplicated enum/schema. |
| Manifest and target shape | Run RAES manifest capability, supported-contract, realization-envelope, digest, component-presence, and callable-signature validation before use. Unsupported capabilities are rejected or disclosed, never optimistically advertised. |
| Plan and transition envelopes | `RuntimeManager` / `RuntimeControlPlane` validate plan identity, baseline snapshot, `ApplyResult`, changed addresses, workflow/evaluation/proposition/participant/time state, append-only histories, and realization claims. Invalid portable output fails closed and never becomes a successful receipt. |
| Participant admission and exposure | Published validators enforce contract, implementation selection, target, episode, generation, evidence, exposure, terminal-result, sequence, linkage, audience, and identity boundaries. Positive and negative tests must prove that another participant's facts and evaluator-only integrity/service/reward facts cannot enter a participant view or observation. |
| Observation shape | Construct a fresh `ParticipantObservationEnvelopeModel` from a closed allowlist of evidence-backed semantic facts. The current evidence does not authorize semantic extraction from the flattened `Box(1652)` array; a later qualified index/meaning map may expose only its selected mapped facts. Never traverse, serialize, hash, summarize, or expose the array, native `info`, mask, or object graph wholesale. RAES participant retrieval owns persisted scoped views; do not smuggle an observation through metadata, status, history details, or diagnostics. |
| Evaluator boundary | Capture only evidence-backed, finite, sanitized facts as part of the one committed driver transition. Evaluator reads that committed fact record without source mutation and emits distinct proposition truth, objective result, evidence, derived measure, terminal cause, and limitation models. Participant access to those facts remains governed separately. |
| Secret handling | Read no user/repository secret store and accept no credential configuration. Native learned credentials and tokens remain opaque driver state. Never copy argv, environment, credential values, or authentication material into portable artifacts, logs, diagnostics, errors, or subprocess arguments. |
| OS/process exposure | PrimAITE import creates platform application/session/log directories. First prove a source-supported explicit path binding scoped to the native target. A temporary rewrite of process-global `HOME`, cwd, or platform state is not race-safe merely because target operations are locked: unrelated threads and imports can observe it, and Python caches imported modules and paths. If explicit binding is unavailable, the in-process live driver is blocked pending a separately reviewed worker/process-isolation decision. Paths never enter CLI arguments, portable config, status, receipts, diagnostics, or artifacts; owned temporary state is removed and verified through cleanup. Base import must not import PrimAITE, Gymnasium, or NumPy. |
| Error and log envelope | Catch native exceptions inside the driver/component boundary and translate them to a closed private failure disposition, then to bounded RAES diagnostics/results. Never pass exception objects, native type names, args, causes, `str`/`repr`, locals, paths, stdout/stderr, logs, or tracebacks to `RuntimeManager`, whose generic catch path otherwise exposes an exception type name. Logs contain only bounded portable addresses, safe operation labels, counts, and dispositions. |
| Authentication if later exposed | Reuse RAES `create_control_plane_app()` and `ControlPlaneSecurityConfig.strict_defaults`: verified identity, role/target authorization, untrusted proxy headers, request-size limits, denial audit, and redacted errors. Do not add an adapter endpoint or weaker auth/config parser. |
| Persistence and idempotency | `ControlPlaneStore` and control-plane receipts remain the operation persistence seam. Driver state and its temporary workspace are lifecycle-scoped, never a second source of portable truth, and must be closed and verified by cleanup. |
| Distribution and workflow | Extend the existing isolated extra matrix and clean-wheel identity probe in `noxfile.py`; retain the canonical pre-commit, docs, type, policy, test, build, distribution, and `verify` graph. Add no second lockfile, CI workflow, required-check path, or dependency on another simulator extra. |

Leakage tests inspect every JSON-ready or persisted success and failure surface,
not only object `repr`: manifest and realization payloads, `ApplyResult` and
snapshots, component status/results/histories, operation receipts/status,
participant observations and action results, evaluator output, cleanup receipts,
diagnostics, and the canonical conformance report. Hostile sentinels cover native
ids, tuples/arrays, paths, logs, exception text and types, tracebacks,
argv/environment data, and credential-shaped values.

## Extensibility seam

The extension parameter is an immutable `EvidenceSelection` plus a driver
factory for that selection. Backend-private mappings are keyed by published
action-contract address, validated portable target and arguments, participant
observation boundary, and selected source protocol. A second PrimAITE scenario
or source revision should enter as another qualified selection and factory
binding without editing a cross-simulator registry or copying lifecycle,
validation, time, receipt, cleanup, or persistence logic.

The obvious future action variation belongs at the action contract's typed
argument seam. The obvious future runtime variation belongs at the qualified
selection/driver-factory seam. Neither is a reason to introduce a generic Gym
driver, a native-simulator protocol in `base`, or an opaque options mapping.
Only narrow, demonstrated mechanics such as complete-root enumeration, tree
digesting, and module-origin verification may later be extracted into private
base plumbing; backend qualification parsing and semantic mappings remain local.

## Gotchas and anti-patterns

- Do not turn source import, the do-nothing smoke, three stable runs, or a green
  conformance probe into deterministic-replay or outcome-equivalence claims.
- Do not patch around the broken seed seam by installing the RL/Torch stack or
  globally seeding Python/NumPy without a new qualified selection. Report
  applied, broken, absent, and unbound controls separately.
- Do not fabricate orchestration operations because the compiled SDL plan is
  empty. Episode control comes from the published experiment contract; logical
  time uses `ReferenceTimeRuntime`, not a private step counter.
- Do not represent RED/GREEN internal occurrences as separately admitted BLUE
  actions or execute extra source turns for histories, observations, or
  evaluation.
- Do not conflate scalar reward, reward components, proposition truth, objective
  outcome, action result, participant terminal status, evidence, or a derived
  measure.
- Do not conflate `terminated=false`, horizon truncation, evaluator cutoff,
  objective satisfaction, participant termination, and cleanup completion.
- Do not expose native ids, tuples, arrays, masks, option dictionaries, `info`,
  object representations, raw logs, paths, hidden truth, exceptions, argv,
  environment data, credentials, or tracebacks as portable content or stable
  source references.
- Do not duplicate RAES schemas, validators, capabilities, participant state,
  histories, receipts, time state, cleanup models, diagnostics, stores,
  conformance cases, workflow logic, or evaluator controllers.
- Do not import CyberBattleSim or CybORG backend code as a Primaite dependency.
  Reuse their architecture patterns and shared incumbents, not their semantics
  or private drivers.
- Do not claim concurrency, autonomous control, coordinated reset, observation
  sealing/capture, cleanup verification, or objective truth without executable
  positive and negative evidence.
- Do not return portable success after an irreversible native mutation whose
  projection failed. Cleanup failure remains distinct from the primary failure.
- Do not introduce eager imports, source checkout discovery, runtime network
  installation, shell execution, broad environment forwarding, host-home writes,
  unbounded logging, or a catch-all success fallback.
- Do not treat an adapter lock as isolation for process-global environment or
  import state. If the qualified runtime cannot be confined safely in process,
  stop for a separate worker-boundary decision rather than hiding a Python 3.11
  executable or native payload in argv, environment, stdout, or stderr.

## Non-goals and implementation boundaries

- This preflight does not implement the backend, choose concrete action
  variants, expand source qualification, or approve a new artifact, patch,
  dependency graph, Python runtime, or repackaging route.
- It does not change the authored scenario, experiment semantics, evidence
  selection, equivalence tier, or loss disclosures to make a runtime mapping
  convenient.
- It adds no semantic model, schema registry, simulator protocol, diagnostic or
  exception hierarchy, policy gate, fixture corpus, or concept catalog to
  `raes_adapters.base`.
- It adds no generic Gym adapter, cross-backend driver registry, authentication
  mechanism, HTTP controller, CLI, daemon, subprocess launcher, plugin system,
  environment configuration, repository/database/cache, second distribution,
  lockfile, or workflow.
- Fake-driver tests may prove portable mechanics and failure behavior; they do
  not prove live PrimAITE identity, Python compatibility, stochastic control, or
  scientific equivalence.
