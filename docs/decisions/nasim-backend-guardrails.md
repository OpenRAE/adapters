# NASim backend architecture guardrails

GitHub issue #34 is the authority for the backend deliverable. This record
fixes the repository-wide boundaries that implementation must respect; it is
not an implementation plan and defines no new RAES contract.

## Admission and claim boundary

The admitted selection is the checked-in `NASIM_TINY` evidence set over
`nasim==0.12.0`, `gymnasium==0.26.3`, and `numpy==1.26.4`. The official wheel,
static `tiny` benchmark, public seed, reset/step shapes, bruteforce baseline,
termination probes, complete installed import-root identities, and known
defects remain owned by `qualification.json`, `public-protocol.md`, the authored
SDL, experiment task/spec, source ledger, and loss disclosures. Runtime code
must consume those joined artifacts rather than repeat their constants.

Admission permits implementation; it does not upgrade the recorded claim
strength. The adapter may attest the selected source/configuration, the controls
it actually applied, and observed run facts. It must retain partial execution
control and stochastic-bounded outcome reproduction. A seeded reset, a matching
smoke result, canonical conformance, or the manual live run does not establish
deterministic replay, scientific validity, or outcome equivalence.

The selected source uses `fully_obs=True`, while the portable SDL deliberately
declares a narrower attacker observation boundary and excludes the flat native
vector. Do not describe the selected native environment as partially observed.
The RAES observation is a lossy, default-deny participant projection from a
fully observed native source. This distinction must be explicit in manifest
constraints, observation loss descriptors, evidence limitations, and positive
and negative disclosure tests.

## Keep the concepts separate

| Concept | Boundary |
| --- | --- |
| Qualification and protocol | Immutable backend-local source, runtime, legal, and apparatus evidence. They are not a manifest, scenario, portable result, or replay claim. |
| Authored scenario | Portable node-for-node intent for the selected static `tiny` case. It is not an arbitrary NASim generator input, native scenario object, live host state, or flat observation. |
| Source ledger and losses | Backend-local traceability and claim bounds. They do not extend RAES vocabulary or authorize a native value to cross the driver. |
| Manifest and realization envelope | A truthful declaration of implemented RAES surfaces and the selected static-scenario realization. They are not qualification records or a generic NASim capability claim. |
| Provisioned target | Portable compiled state and stable selected-source references. It never contains the environment, scenario, action space, arrays, native coordinates, or hidden host truth. |
| Participant action | A validated RAES request and typed terminal result. Its contract, target, and action-instance identities are not a flat action index or native action object. |
| Orchestration, time, and source execution | Workflow progress, an explicit logical-clock transition, and one `env.step()` are distinct. One component owns each mutation. |
| Observation and evaluation | Participant-relative disclosed facts are separate from fully observed native state, evaluator-only goal truth, reward, evidence, and derived measures. |
| Termination and cleanup | Goal termination, step-limit truncation, participant terminal status, workflow completion, evaluator state, and verified resource cleanup are separate facts. |

Do not collapse these layers behind generic `environment`, `step`, `result`,
`profile`, or `done` abstractions.

## Canonical incumbents to compose

`raes_adapters.base` remains mechanical plumbing and published RAES contracts
remain semantic authority. The implementation must build on these incumbents:

| Concern | Canonical incumbent and required use |
| --- | --- |
| Selected evidence | `raes_adapters.nasim.scenario_ledger.NASIM_TINY` / `LEDGER`, `_qualification.backend_evidence_loaders()`, shared `_scenario_ledger.ScenarioLedger`, and the checked-in NASim resources. Validate the admitted selection and its joins before native construction. |
| Packaging and isolation | `pyproject.toml`, one `uv.lock`, ADR-003, and `_extras()` / `_verification_envs()` in `noxfile.py`. Keep simulator imports lazy, preserve base-only installation, and verify each extra alone; add `tool.uv.conflicts` only for demonstrated incompatibility. |
| Installed-source admission | The complete-root, direct-install provenance, symlink rejection, distribution-version, and module-origin mechanics already exercised by `CyberBattleSimDriver`, grounded in NASim's own qualification identities. Do not import that backend's private methods or copy another artifact-policy implementation. If mechanics are shared, extract only a backend-neutral private verifier; expected roots, versions, digests, and admission policy stay backend-local evidence. |
| Manifest | `raes_backend_protocols.backend_manifest.BackendManifest`, published capability models/admission validators, `backend_manifest_v2_model()` / `backend_manifest_payload()`, RAES backend profiles, and the RAES-owned supported-contract catalog. Do not hand-author manifest JSON, capability vocabulary, or a contract table. |
| Realization disclosure | `BackendRealizationEnvelopeModel` and its digest/cross-concern validation. Claim only the selected static `tiny` realization and disclose excluded native state plus the narrower participant projection; do not advertise arbitrary NASim YAML or generated scenarios. |
| Runtime target | `raes_adapters.base.build_runtime_target()` over `RuntimeTarget` and `RuntimeTargetComponents`. Let RAES enforce component presence, manifest agreement, and signatures; add no backend registry unless a real caller uses the published `BackendRegistry`. |
| Runtime boundary | `RuntimeManager` / `RuntimeControlPlane` and their provisioning, workflow, evaluation, proposition, participant, time, snapshot-transition, result-contract, and `ApplyResult` gates. Never call private `_call_backend_*` helpers or fork their validation. |
| Participant lifecycle | `BaseParticipantRuntime` and `ParticipantNativeActionExecution`. Reuse initialize/reset/restart/terminate, episode identity, generation, append-only history, sequence/linkage, and terminal-result behavior. `_model_action` is the backend seam; do not create another lifecycle controller. |
| Action admission | `ParticipantActionAdmissionRequest`, `ParticipantValidatedActionSelection`, published implementation/exposure/evidence validators, `ParticipantActionResultModel`, and `autonomous_action_result_violation()`. Validate contract, target, arguments, participant, episode, generation, and requested evidence before native mutation. |
| Observation and retrieval | `ParticipantObservationEnvelopeModel`, published observation-boundary validation, and `RuntimeControlPlane`'s `ParticipantRetrievalMixin` projections for status/history/context. Return no custom observation/history DTO and never expose the flat vector or `info`. |
| Logical time | `ReferenceTimeRuntime`, `TimeCoordinator`, `apply_logical_clock_transition()`, and RAES time-state validation. For this selected sequential protocol, explicitly map one successfully committed native step to one logical advance; rejected/no-transition actions do not advance, and reset starts a new declared logical segment. |
| Stochastic controls | Checked-in experiment controls, published stochastic-control models, `apply_seed_controls()` only when an executable binding exists, and the process-global state-isolation pattern in `SourceInstalledCyborgDriver`. Report the Gym reset stream and global-NumPy action-success stream separately; applying either is not a replay claim. |
| Workflow and receipts | Compiled workflow contracts and `WorkflowExecutionStateModel` for logical orchestration; `RuntimeControlPlane` operation receipts/status and `ControlPlaneStore` for idempotency, audit, and persistence. Do not create NASim receipts, a second workflow engine, or a backend store. |
| Evaluation | CybORG's separation of objective/proposition truth from reward and CyberBattleSim's sanitized evidence/derived-measure pattern, implemented with published evaluation lifecycle/history, proposition truth, `ExperimentEvidenceRecordModel`, raw-evidence content, derived-measure, capture, and run contracts. Reuse the contract shapes, not either backend's semantics or classes. |
| Projection and failure hygiene | Base `project_action()`, `project_observation()`, `project_evaluation()`, `redact_native_value()`, and `bounded_context_label()` plus RAES `Diagnostic` / `DiagnosticModel` / `ApplyResult`. Do not add a third copied diagnostic-address helper, an exception hierarchy, or a native fallback payload. |
| Cleanup | `TrialCleanupPlanModel`, `CleanupCapabilities`, `require_cleanup_plan_capability()`, base `execute_cleanup()`, `TrialCleanupReceiptModel`, and `validate_trial_cleanup_receipt()`, following the driver-local dispatch in CyberBattleSim cleanup. Native close/verify remains deterministic, idempotent, and failure-preserving. |
| Conformance and tests | Base `run_conformance_probe()` / RAES `run_target_conformance()`, the end-to-end fake-driver pattern in `test_cyberbattlesim_backend.py`, mutation/quarantine negatives in CybORG tests, shared NASim qualification/ledger tests, and the canonical nox graph. Do not mint a NASim profile, fixture corpus, report, or parallel workflow. |

## Driver ownership, mutation, and recovery

One private, in-process driver owns one admitted selection, one NASim
environment lifecycle, its native action space and observations, the latest
reward/terminal facts, and one isolated global-NumPy stream state. The
Provisioner, ParticipantRuntime, and Evaluator share that owner; portable
snapshots contain no driver handle.

ParticipantRuntime is the sole owner of admitted `env.step()` execution. It
translates a validated RAES action contract plus admitted portable target and
arguments into exactly one private native action coordinate, records one
adapter-generated driver operation reference, and returns one typed terminal
result joined to participant, episode, action instance, contract, generation,
and observation point. Translation must find one unambiguous selected-source
action before mutation. Flat indices and native target tuples remain private.
Unsupported, unavailable, ambiguous, or malformed selections fail before a
source call.

Orchestrator owns portable workflow coordination and logical-step state; it
does not replay the participant action. Evaluator performs a read-only
projection of already committed driver facts and never advances or resets the
environment. Observation projection performs no second native call. Native
access is serialized and the manifest must not claim bounded concurrency.

The selected one-participant reset may be initiated from participant lifecycle
initialization/reset/restart, but native reset occurs exactly once. Workflow
reset, logical-clock reset, new episode identity, source reset, deterministic
replay, termination, and cleanup remain distinct. A failed native reset restores
the predecessor portable mirror. A source transition followed by failed
projection or RAES validation cannot be rolled back; quarantine the episode as
failed/terminated and require reset or cleanup instead of returning success.

Provisioning admits only the compiled selected static scenario and rejects
unsupported changes before construction. Construction, deletion, replacement,
and cleanup must preserve ownership on failure so cleanup can be retried.
Cleanup is safe after partial construction, failed admission, projection
failure, termination, ordinary success, and repeated calls. Clearing the RAES
snapshot or stopping components is not verified native cleanup.

## Global RNG and terminal-result rules

NASim resolves action success through the process-global legacy NumPy RNG. A
plain `numpy.random.seed()` in library code would corrupt caller state and let
unrelated code corrupt the episode. Reuse the established CybORG pattern with a
process-wide lock and driver-private saved RNG state: save caller state, install
the selected driver's state, call the bounded native operation, retain the
advanced driver state, and restore caller state in `finally`. Reset may seed the
driver's saved state with the admitted unsigned seed and separately call
`env.reset(seed=...)`; report both dispositions and their different meanings.
Never seed at import time, leave modified global state behind, or infer replay
strength from a successful binding.

NASim computes `terminated` (goal reached) and `truncated` (step limit)
independently. Retain both booleans. If both are true on one source transition,
project participant completion with goal precedence while retaining truncation
as evaluator evidence and an explicit limitation; never erase either fact with
an `if`/`elif` native-fact model. Source reward, action processing, objective
truth, terminal cause, participant status, workflow status, evidence, and
derived measures remain distinct projections.

## Cross-cutting validation and security path

The intended backend is an optional in-process library. It adds no HTTP route,
authentication mechanism, environment-variable configuration, CLI, subprocess,
network fetch, or durable backend store.

| Layer the design passes | How it passes |
| --- | --- |
| Source/admission and dependency authority | Read the admitted package evidence; require the qualified NASim/Gymnasium/NumPy versions, complete import-root trees, applicable direct-archive provenance, symlink-free files, and module origins before importing NASim. Reject editable/directory/VCS installs and hidden patches. Remaining transitive dependency and system-library facts are recorded evidence, not a runtime authenticity claim. |
| Contract parsing and configuration shape | Parse/compile SDL with RAES and validate experiment/runtime objects with closed published models and existing cross-artifact joins. Target construction accepts only an explicit immutable selection, bounded unsigned seed, and test driver factory; reject unknown keys, environment overrides, arbitrary import paths, mismatched digests, or permissive mappings. |
| Manifest and target shape | Run published manifest capability, supported-contract, realization-envelope/digest, component-presence, and callable-signature checks before target use. Unsupported facts are rejected or disclosed as limitations, never optimistically advertised. |
| Plan, transition, and result envelopes | `RuntimeManager` / `RuntimeControlPlane` validate plan identity, baseline snapshots, changed addresses, `ApplyResult`, workflow/evaluation/proposition state, participant histories, clock readback, and realization disclosure. Invalid portable output fails closed and does not become a success receipt. |
| Participant admission and exposure | Published validators join action contract, implementation selection, target/argument bindings, generation, evidence request, exposure policy, result, sequence/linkage, and participant/episode scope. Positive and negative tests prove that evaluator-only sensitive-host truth, another scope, hidden references, the full native observation, and unrequested evidence cannot enter participant views or histories. |
| Secret handling | The backend does not read secret stores or accept credentials as configuration. SDL credentials are synthetic intent; native learned access/credential state remains opaque. Tokens, secret values, environment dumps, authentication material, and native credentials never enter argv, logs, evidence, snapshots, diagnostics, or histories. |
| OS and import exposure | Base/module import remains dependency-light. Verify artifacts and the Tk system prerequisite before the first lazy NASim import; construct only with `render_mode=None`. Treat NASim's unconditional `tkinter` import and `TkAgg` selection as a disclosed process-global source defect—do not monkey-patch it, set a hidden matplotlib environment override, render, or claim headless portability without Tk. Use no shell, subprocess, network, home/cache authority, checkout-relative import, or broad environment forwarding. |
| Error and logging envelopes | Native values are never stringified. Portable failures use bounded fixed diagnostics; native exceptions contribute no args, causes, contexts, locals, paths, stdout/stderr, or traceback. Logs, if any, contain only bounded published addresses, safe operation names, counts, and dispositions. |
| Authentication/authorization if later exposed | Reuse `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`, verified identity, target/role and participant subject/audience authorization, request-size limits, denial audit, and RAES's redacted exception handler. Do not add a NASim endpoint or weaker auth/config shape. |
| Persistence and idempotency | `ControlPlaneStore` and control-plane receipts remain the portable operation boundary. Driver state and saved NumPy state are lifecycle-scoped, cleared and verified through cleanup, and never persisted as a second source of truth. |
| Distribution and workflow | Extend the existing clean-wheel `_distributions()` proof for a hermetic NASim target/conformance probe without making live Tk availability a base-install requirement. Keep the issue-required live run as bounded manual evidence on the qualified runtime. The existing hygiene, policy, lint, type, test, distribution, docs, and `verify -- --skip-requirement` graph remains canonical. |

## Extensibility seam

The external seam is the existing immutable `EvidenceSelection`, joined to its
qualification/protocol record, plus a driver factory and explicit seed for that
selection. Native action translation is keyed by published action-contract
address and validated target/arguments; observation projection is keyed by the
published participant boundary; termination and evaluation mapping are keyed
by the selected protocol. These mappings are NASim-private and are not a base
registry, generic Gym wrapper, or portable schema.

A second qualified NASim static scenario or generated profile must be addable
as another immutable selection and driver configuration without editing a
cross-simulator registry, copying lifecycle logic, or changing RAES contracts.
Generated-scenario parameters belong in existing SDL variables/variation
points and checked instantiations. Version-specific compatibility remains
behind the driver factory and tied to qualification evidence. Generalize into
shared plumbing only after an identical mechanical concern exists in multiple
backends and RAES does not already own it.

## Gotchas and anti-patterns

- Do not reuse CyberBattleSim or CybORG semantics, driver protocols, DTOs, or
  capability claims; reuse only published contracts and proven mechanical
  patterns.
- Do not treat `fully_obs=True` as permission to expose the raw vector, all
  host truth, action availability, evaluator facts, native identifiers, or
  `info`. The portable attacker boundary is intentionally narrower.
- Do not hard-code or publish flat indices. Resolve a unique private native
  action from validated portable semantics, and do not echo a requested target
  as a realized effect unless the source result supplies a verified join.
- Do not let Provisioner reset an episode, Orchestrator call `env.step()`,
  Evaluator mutate the source, or observation projection trigger a source call.
- Do not override `BaseParticipantRuntime` lifecycle wholesale, duplicate
  histories/views/results, or claim coordinated multi-participant reset for the
  selected single-attacker source.
- Do not duplicate manifest payloads, RAES validators, capability vocabularies,
  receipts, logical time, cleanup receipts, diagnostics, stores, conformance
  fixtures/cases, installed-artifact verification, or workflow/evaluator
  controllers.
- Do not publish native tuples, arrays, dtypes, object representations, action
  IDs, target coordinates, logs, paths, hidden state, exceptions, argv or
  environment data, credentials, Tk objects, matplotlib state, or tracebacks as
  portable data or stable references. Qualification/ledger identities and
  digests are the stable source references.
- Do not collapse reward into action outcome, objective truth, evaluator
  status, evidence, or a measure; do not collapse `terminated`, `truncated`,
  participant termination, workflow completion, and cleanup into `done`.
- Do not return portable success after native mutation when projection or RAES
  validation fails. Preserve primary, compensation, and cleanup failures as
  distinct bounded facts.
- Do not claim reset, stochastic control, exposure, objective truth, cleanup
  verification, concurrency, or any other capability without executable
  evidence. Reject unsupported requests before source mutation.
- Do not add working-directory dependence, import-time discovery, process-global
  RNG leakage, silent monkey patches, broad environment forwarding, rendering,
  unbounded logging, catch-all success, or a backend-independent simulator
  abstraction.

## Non-goals and implementation boundaries

- This preflight does not implement the optional backend, target, driver,
  manifest, component, cleanup adapter, conformance report, test, or manual run.
- It does not requalify NASim, select another artifact/runtime, patch upstream,
  upgrade claim strength, or alter the admitted SDL/experiment/ledger evidence.
- It does not support arbitrary NASim scenarios, scenario generation, learning
  agents or weights, rendering, defenders, multi-participant coordination,
  concurrency, training, or a generic Gym/Gymnasium adapter.
- It does not add semantics to `raes_adapters.base`, change published RAES
  contracts, create a NASim schema/profile/vocabulary/exception hierarchy, or
  make backend concepts shared authority.
- It adds no authentication service, HTTP controller, CLI, daemon, subprocess
  launcher, plugin discovery, environment-binding format, database/repository/
  cache, second distribution/lockfile, or CI workflow.
- The manual integration check is bounded operational evidence: on the
  qualified installed runtime with Tk present, exercise the default live target
  through reset, a representative admitted step, source termination, and
  verified cleanup, recording only reward, both terminal booleans, step/control
  dispositions, and cleanup outcome. It is not a portable native-state dump or
  a replay/equivalence claim.
