# CybORG conformance-composition guardrails

GitHub issue #19 is the authority for this deliverable. This note fixes how the
completed CybORG target composes with published RAES conformance and with
adapter-local executable evidence. It defines no new contract, profile, fixture
corpus, report schema, or implementation plan.

## One conformance authority, several bounded evidence claims

Keep these results distinct:

| Result | Meaning and owner |
| --- | --- |
| Backend conformance | The exact `BackendConformanceReport` returned by published `run_target_conformance()` for the profile selected from the live manifest, and serialized by `backend_conformance_report_payload()`. Its claim is finite and bounded by the named profile, corpus, target, execution basis, and cases. |
| CybORG adapter probes | Backend-local executable facts about the selected source ledger, pins, stochastic and clock controls, lifecycle, projections, cleanup, and leakage. They use RAES `Diagnostic` and evidence references but are not fixture cases, a profile extension, or another conformance report. |
| Native readiness | Execution against the exact qualified CAGE-2 source closure. It proves that the selected installation exercised the named paths; it is not interchangeable with the injected-driver PR run. |
| Scientific equivalence | A separately governed claim over eligible run evidence and retained loss disclosures. Neither a green conformance report nor a controlled seed establishes replay, state/observation equivalence, outcome equivalence, or scientific validity. |

Do not collapse these into one locally invented `passed` value. The canonical
report remains unchanged; local probe dispositions, evidence links, weaknesses,
and reproduction commands accompany it as disclosure data.

Published fixture cases do not have an adapter-owned unsupported escape hatch.
Every fixture selected by the published profile must pass. An unsupported result
is legitimate only when the published runner or a local probe vocabulary permits
it and the manifest makes no contradictory affirmative claim. It is never an
`xfail`, skip, swallowed exception, fake-driver fallback, or manually rewritten
case.

## Implemented fail-closed dispositions

The implementation resolves these live-contract facts without hiding them in
the new surface:

- `profile_for_manifest(create_cyborg_manifest())` selects the published
  `full-remote-control-plane` profile. The manifest derives the profile's
  required contract set through the published profile loader, including
  `participant-control-occurrence-v1`,
  `participant-crossing-occurrence-v1`, `participant-lifecycle-event-v1`,
  `workflow-history-event-stream-v1`, and `workflow-result-envelope-v1`. The
  existing runtime honors those contracts, and the published runner reports no
  contract gap. A local profile remains forbidden.
- The current realization envelope has an empty, non-constructive expression.
  Published probe generation therefore returns the failed/unsupported
  `realization-envelope-constructive` case before any injected harness can run.
  RAES 2.0.0 cannot synthesize the list-valued network binding, so the adapter
  preserves the published runner's `unsupported` no-witness disposition and
  exercises the supported topology separately through local diagnostics. It
  does not patch the report or runner.
- Several existing CybORG diagnostics use dotted or bare addresses such as
  `runtime.cyborg.provisioning`, `cyborg-cage2`, and participant compiled
  addresses. They are now projected to JSON Pointer syntax at the component
  boundary, and every emitted adapter diagnostic passes `diagnostic_model()`;
  bypassing that gate with `asdict()` or a hand-built dictionary is not valid
  conformance evidence.
- Published target probes may include an unexpected component exception's text
  in a failure diagnostic. Every adapter-owned native exception must therefore
  be caught at its existing component boundary and replaced with a stable,
  input-free diagnostic before the call can reach that path.

`backend_manifest_from_v2_model()` is not a round-trip loader for this target:
`backend-manifest-v2` carries only a realization-envelope identity and the
published function rejects envelope-bearing payloads that lack the full planner
declaration. Load the live manifest through `BackendRegistry` /
`register_cyborg_backend()`, validate it with `backend_manifest_v2_model()` and
`backend_manifest_payload()`, and retain the live typed manifest for target
construction.

## Compose the existing owners

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Manifest and target | `register_cyborg_backend()`, `create_cyborg_manifest()`, `create_cyborg_target()`, `BackendRegistry`, `BackendManifest`, `backend_manifest_v2_model()`, `backend_manifest_payload()`, `build_runtime_target()`, and `RuntimeTarget` shape/signature validation. Do not keep a golden manifest payload or duplicate supported-contract table. |
| Profile and corpus | `profile_for_manifest()`, `required_contracts()`, `run_fixture_suite()`, `run_target_conformance()`, published profile/corpus roots, and `raes_adapters.base.run_conformance_probe()`. Production uses the published default roots; root overrides remain test injection only. |
| Realization | The existing validated `BackendRealizationEnvelopeModel`, its configuration/envelope digests, published positive/negative probe generation, `RealizationConformanceHarness`, `ExecutionBasis`, and report cases. Do not turn the harness into a generic local-probe hook. |
| Source identity and coverage | `CAGE2_SOURCE_26CE1C1`, `EvidenceSelection`, `load_qualification()`, `load_source_ledger()`, `validate_all()`, `load_loss_disclosures()`, selected-file digests, and `tools/verify_cyborg_qualification.py`. Read these owners; do not repeat source, scenario, seed, defect, or loss facts in a probe catalog. |
| Provisioning and lifecycle | `CyborgProvisioner`, `SourceInstalledCyborgDriver`, realization-envelope admission, complete desired-state reconciliation, aggregate ownership, quarantine, retrying cleanup, and `RuntimeControlPlane` result/snapshot gates. Partial construction and failed replacement must remain owned until cleanup is verified. |
| Orchestration and time | `CyborgOrchestrator`, `CyborgExecutionControl`, admitted `OrchestrationPlan`, workflow result/history validators, `ReferenceTimeRuntime`, `apply_logical_clock_transition()`, and RAES time-model validators. Native step counts and wall time are observations, not a second clock. |
| Seed controls | The target's closed `seed` configuration, qualification stochastic-source inventory, admitted `ExperimentStochasticControlModel` bindings, `apply_seed_controls()`, driver-local reset behavior, and retained loss disclosures. Applied, unbound, unsupported, and failed streams remain distinct; application is not determinism. |
| Action and observation | `CyborgParticipantRuntime`, `ParticipantActionAdmissionRequest`, validated selections, compiled action/result contracts, participant episode/history/shared-state/joint-action/time-context validators, and `ParticipantObservationEnvelopeModel`. Native ids, masks, observations, sessions, credentials, and hidden truth stay private. |
| Reward and evaluation | `CyborgEvaluator`, committed private turn facts, `EvaluationResultStateModel`, `EvaluationHistoryEventModel`, `PropositionTruthResultModel`, capture/evidence/derived-measure models, and their existing validators. Reward components, cumulative score, objective truth, participant outcome, and conformance remain separate. |
| Cleanup | Existing provisioner/driver ownership and verified idempotent cleanup. If the manifest gains published cleanup capability, compose `execute_cleanup()`, capability admission, `TrialCleanupReceiptModel`, and `validate_trial_cleanup_receipt()`; a successful `driver.cleanup()` boolean alone does not establish a RAES clean-state claim. |
| Diagnostics and projection | `Diagnostic`, `diagnostic_model()`, `diagnostic_payload()`, closed RAES result models, `backend_conformance_report_payload()`, `redact_native_value()`, and `bounded_context_label()`. Never serialize through `repr`, `str`, `dataclasses.asdict`, or an exception traceback. |
| Report persistence | `raes_operations.realization_conformance.write_backend_conformance_report()`, its shared redaction gate, safe run-id path construction, and atomic JSON writer. The writer is mandatory but not sufficient for CybORG-specific hostile-sentinel coverage. |
| Persistence | `ControlPlaneStore` is the only durable runtime-state seam. Conformance target state is ephemeral and report output uses an explicit output directory. Do not add an adapter database, cache, evidence repository, or checked-in generated report. |
| Packaging and CI | The single `pyproject.toml`/`uv.lock`, `_verification_envs()`, `_tests()`, `_distributions()`, `probe_installed_identity.py`, the existing CI workflow and `PR Gate`, strict docs/policy gates, and canonical `nox -s verify`. Extend these paths; do not create a second lock, workflow, or unenforced verification graph. |

The CyberBattleSim conformance module is the closest repository precedent for
canonical report projection, RAES diagnostics, weakness references, and
hostile-value tests. Reuse its composition pattern, not its source protocol,
action model, seed semantics, cleanup claims, capability inventory, or
backend-specific helper module.

## Local probes, capability inventory, and leakage

Derive affirmative capability JSON pointers from the live
`backend_manifest_payload()` as unresolved inventory only. A broad published
conformance disposition, source-ledger validation, or adapter-local probe does
not prove every capability leaf, so there is no pointer-to-evidence requirement
map or positive join. Exercise negative and unsupported declarations as well,
especially replay, autonomous execution, bounded concurrency, execution
control, accounts, ACLs, generated artifacts, persistent volumes, and cleanup
when undeclared.

Weaknesses are machine-resolvable references derived from qualification
`admission.limitations`, `known_defects`, and the selected loss disclosures.
Do not transcribe them into a second list or erase them when a probe passes.

Leakage testing is a success/failure cross-product over every declared runtime
surface, plus cleanup:

| Boundary | Portable outputs that must be validated and inspected |
| --- | --- |
| Provisioner | `ApplyResult`, `OperationStatus`, snapshot entries, realization identity/provenance, construction failure, replacement failure, and partial-construction cleanup. |
| Orchestrator | Workflow result/history, operation status, start/stop/reset paths, and execution-session construction failure. |
| Participant runtime and observation | Episode/action results, behavior and lifecycle histories, participant-relative observation envelopes, shared state, joint action, time context, rejected actions, native-turn failure, and post-effect quarantine. |
| Evaluator | Evaluation result/history, proposition truth, capture spec, evidence records, derived measures, unsupported facts, non-finite/wrong-shaped native reward, and projection failure. |
| Time runtime | Valid initialize/advance/reset state and rejected invalid transition/coordinate requests. No native value should enter this RAES-owned surface. |
| Cleanup | Success, primary failure, partial construction, retry/idempotency, independently verified close, residual-state disclosure where declared, and failure during verification. |

Give each hostile path a unique native sentinel whose `str` and `repr` are
unsafe. Inspect the actual JSON-ready published projections and persisted
canonical report, not an in-memory `repr`. Prove the sentinels plus native action
ids/classes, observations, reward mappings/vectors, hidden truth, credentials,
paths, stdout/stderr, argv/environment mappings, exception text/causes, and
tracebacks are absent. Construct allowlisted portable values without traversing
native objects; a regex scrubber after broad serialization is not a projection
boundary.

## Deterministic suites, output, and workflow

The checked-in seed selections are ordered, immutable, and backend-local:

- the PR/hermetic suite uses `(3,)`, the qualified smoke seed, with a fully
  constructed target and deterministic injected driver;
- the scheduled/full hermetic suite uses `(3, 153)`, adding the pinned evaluation
  source's documented seed while retaining
  `loss-evaluation-seed-unbound` and all other stochastic limitations.

Select the tier explicitly at the command/session boundary. Do not derive seeds
from time, PR number, test order, hashing, global random state, or an environment
override. The full suite may cross the fixed seeds with reviewed red variants
and trial lengths, but neither suite may call that finite sample deterministic
replay or scientific equivalence.

The PR suite is dependency-light, offline, and independent of user-home state.
It runs the canonical published profile/corpus and all local success/failure
probes with `ExecutionBasis.HERMETIC_LIVE`; `native_conformance` remains false.
The full suite retains the same hermetic execution basis and adds the fixed
evaluation seed. Native readiness remains a separate responsibility of the
qualified-source reproducer, which uses `SourceInstalledCyborgDriver` and the
qualification tool's detached source, digest/module-origin checks,
argument-vector subprocesses, allowlisted environment, isolated temporary
directories, timeouts, and bounded errors. It may use
`ExecutionBasis.NATIVE_LIVE` only when the independent observer and cleanup
requirements are genuinely satisfied. Source absence or mismatch is a failed
readiness result, never an injected-driver fallback under the native label.

One executable may coordinate the outputs, but it must preserve their owners:

- serialize the canonical report only with
  `backend_conformance_report_payload()` and persist it only with
  `write_backend_conformance_report()`;
- serialize each local diagnostic through `diagnostic_payload()` after
  `diagnostic_model()` validation;
- emit evidence and weakness references as references to their existing
  owners; and
- emit fixed reproduction commands as argument arrays using repository-relative
  commands, with no shell interpolation, absolute paths, secrets, or environment
  dumps.

An operational index may point to those outputs, but it must not introduce a
second profile, case family, diagnostics envelope, schema version, or aggregate
`passed` field. The canonical report's `passed`, gaps, claim, cases,
`native_conformance`, limitations, and non-claims remain intact.

Clean-install conformance belongs in `_distributions()`: install the built wheel
with the `cyborg` extra in its own throwaway environment, run from an isolated
working directory with `-I`, cleared `PYTHONPATH`, and `PYTHONSAFEPATH=1`, then
load installed qualification/ledger resources, build the target with the
deterministic driver, run and persist the canonical report, and execute local
probes. Generalize the existing per-extra clean-install probe narrowly rather
than copy its CyberBattleSim environment and command block.

Use the existing `.github/workflows/ci.yml`: the normal `tests` and
`distributions` jobs own the PR suite and clean-install proof; the same workflow
may select the full tier on its scheduled/explicit-dispatch path. Do not add a
second workflow. If a separate job ever becomes necessary, it must be included
in the `PR Gate` contract or explicitly remain a non-PR scheduled readiness job
without masquerading as required PR conformance.

## Cross-cutting security and whole-repository path

| Layer the design passes | Required treatment |
| --- | --- |
| Authentication and authorization | Local conformance introduces no route, controller, or caller authority. In-process execution uses `RuntimeManager`/`RuntimeControlPlane`. Any later network exposure must use `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`, verified identity, role/target and participant-controller authorization, request-size limits, denial audit, and the redacted exception handler; no adapter endpoint is permitted. |
| Secret handling | No secret is needed. Do not read a secret store, accept credentials, expose learned source credentials or governed entropy, or put tokens in diagnostics, evidence, commands, filenames, argv, environment output, logs, or reports. |
| Target/config shape | `_normalized_config()` and `_validate_selection()` remain the closed profile/version/commit/ledger/seed/driver authority and reject unknown keys. Suite tier, output directory, and run id are operational inputs only; they cannot change source identity, manifest semantics, profile roots, or fixture roots. |
| Static parsers and validators | Qualification joins, strict bounded JSONL parsing, `schema_bundle()` target resolution, manifest closed models, published profile loading/path confinement, fixture validation, and realization-envelope digest/shape/probe validation all run. No permissive parser, copied enum, arbitrary import path, or environment-selected corpus. |
| Runtime gates | Reference SDL parsing/compilation, `RuntimeTarget` component presence/signatures, control-plane plan/resource/dependency/capability admission, backend `ApplyResult` shape, changed-address and snapshot-transition checks, workflow/evaluation/proposition/participant/time validators, and cleanup receipt validation where claimed remain authoritative. Backend checks add only selected-CybORG representability and private projection rules. |
| Error envelopes | Adapter failures use stable RAES diagnostics with JSON Pointer addresses and bounded input-free messages. `diagnostic_model()` validates local diagnostics; the canonical report projector remains unmodified. Native exception strings, types derived from hostile values, causes, payloads, and tracebacks never cross the boundary. |
| OS/process exposure | PR and clean-install runs perform no runtime download, shell interpolation, inherited environment dump, or home-cache discovery. Native qualification runs reuse the qualification tool's explicit argv, environment allowlist, safe Python path, path confinement, temporary directories, timeout, and bounded stdout/stderr handling. |
| Logging/observability | Portable observability is RAES reports, diagnostics, evidence refs, limitations, and fixed reproduction argv. Standard logging, if needed, is limited to safe operation names, published pointer addresses, counts, and dispositions; never log plans, actions/arguments, native observations/rewards/state, paths, random state, rejected values, or tracebacks. |
| Persistence/artifacts | Runtime state stays in the existing `ControlPlaneStore`; reports use the RAES atomic writer, safe run-id labels, an explicit output root, and the shared redaction gate. CI uploads only validated portable output. A digest does not make a native dump safe. |
| Repository workflow | Preserve the single distribution/lock, isolated extras, canonical nox sessions, installed-wheel proof, strict lint/type/tests/docs/policy gates, CI `PR Gate`, and requirement-free `--skip-requirement` posture for this issue. |

The shared RAES report redaction gate is required but is intentionally generic
and not proof against every CybORG-native representation. Hostile-sentinel
projection tests remain additive defense in depth; they must operate before the
writer and on its actual persisted JSON.

## Published no-witness disposition

Implementation confirmed that RAES 2.0.0's bounded realization-envelope
domains admit scalar and record constraints but cannot generate the required
list-valued `infrastructure.<host>.links` witness. Narrowing the live envelope
to one probe name/topology would reject the adapter's already-supported authored
scenarios; pretending an empty witness exercised construction would be a false
claim. The adapter therefore preserves its live open disclosure and the exact
published runner result: applicable fixtures pass, while the runner emits its
own machine-readable `unsupported` no-witness realization case. Adapter code
does not rewrite, append, or locally reclassify that case.

The executable adapter-local probes separately construct a supported switch/VM
topology with a hostile injected native handle, validate the source selection
and every declared runtime surface, verify cleanup, and inspect actual portable
projections. The bounded published conformance disposition, validated
source-ledger evidence, and passing adapter-runtime diagnostics remain three
independent facts; their conjunction is not per-leaf capability evidence. A
future RAES release that publishes a constructive list-domain or equivalent
governed witness seam can replace this unsupported case without a local schema
or profile.

The checked-in full tier remains hermetic at ordered seeds `(3, 153)` and keeps
`native_conformance=false`; the existing qualified-source reproducer owns native
readiness. This avoids mislabeling an injected driver while retaining seed 153's
documented evaluator limitation.

## Extension seam

The next selected CAGE/CybORG source closure composes through three existing
parameters: an immutable `EvidenceSelection`, an explicit ordered seed tuple,
and the published `ExecutionBasis` with an injected driver.
Suite tier selects those values; it does not become a profile, schema, simulator
registry, or environment binding.

A new qualified selection may add source resources, evidence bindings, seeds,
or a native harness without changing the RAES profile corpus, report type,
diagnostic model, control-plane persistence, or cross-simulator base API. A new
affirmative manifest claim automatically remains an unresolved inventory gap
until a published contract can verify the owning production path.

## Gotchas and anti-patterns

- Do not copy RAES fixtures/profiles, override production roots, hand-append
  local cases to `BackendConformanceReport`, reconstruct it with `replace()` or
  `asdict()`, or mark a failed canonical case unsupported locally.
- Do not conflate a manifest profile constraint (`CYBORG_PROFILE_ID`) with the
  published backend capability profile selected by `profile_for_manifest()`.
- Do not let an injected driver set `native_conformance=True`, let a native
  install failure fall back to the fake driver, or let a full-suite pass erase a
  qualification limitation.
- Do not conflate construction seed, stochastic-stream binding, reset, replay,
  logical-clock reset, native source terminal, wrapper cutoff, evaluator cutoff,
  participant terminal state, workflow completion, cleanup, and verified clean
  state.
- Do not treat `driver.cleanup() is True` as a cleanup receipt, source action
  success as a validated portable effect, a reward total as objective truth, or
  a conformance pass as scenario correctness/equivalence.
- Do not import CyberBattleSim backend code into CybORG, move source-specific
  probes into `raes_adapters.base`, or create a generic simulator/probe object
  model.
- Do not serialize a native object and then redact fields. Do not use `repr` as
  the leakage oracle or rely on the generic report redaction gate alone.
- Do not put native ids, observations, reward vectors, hidden/evaluator-only
  truth, credentials, logs, exception data, paths, argv/environment dumps, or
  temporary filenames into snapshot metadata, `ApplyResult.details`, status,
  evidence references, weaknesses, reproduction commands, or report names.
- Do not silently repair the selected Remove misreport, Scenario2 port mismatch,
  wrapper cutoff ambiguity, evaluator seed gap, blue-policy artifact gap, or
  packaging limitation to make a probe green.

## Non-goals and implementation boundaries

- No new RAES schema, SDL vocabulary, backend profile, fixture corpus, manifest
  extension, capability vocabulary, report DTO, diagnostic envelope, exception
  hierarchy, store, audit service, or policy gate.
- No change to RAES runner semantics, published corpus data, or unsupported-case
  policy from this repository.
- No new HTTP service, authentication mechanism, adapter endpoint, plugin
  discovery, arbitrary import/config surface, database, durable adapter state,
  second distribution, lockfile, or workflow.
- No automatic acquisition through the `cyborg` extra, publication of the local
  packaging patch, source requalification, or change to the selected source and
  loss facts.
- No claim of deterministic replay, exact state/observation equivalence,
  outcome/evaluation equivalence, scientific validity, or universal behavior
  outside the finite named cases and seed selections.
