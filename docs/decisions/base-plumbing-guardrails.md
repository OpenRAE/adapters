# Shared simulator-adapter plumbing guardrails

GitHub issue #14 is the authority for the shared-base deliverable. This note
fixes the architecture boundaries that implementation must respect; it does not
define a new contract or prescribe an implementation plan.

## Keep mechanics separate from semantics

`raes_adapters.base` is an always-installed convenience layer over
`raes==2.0.0`. It may sequence functions, bind driver-local callables, enforce
bounded failure hygiene, and reduce repetitive target construction. It does not
own the meaning or portable shape of targets, clocks, stochastic controls,
cleanup, projections, diagnostics, or conformance.

The public base surface must therefore use the published RAES types directly.
A local type may describe ephemeral in-process mechanics only when RAES has no
portable counterpart. Such a type must not be a Pydantic model, JSON schema,
manifest or wire format, must not be serialized as authority, and must not
repeat fields from a RAES contract. In particular, do not add a base semantic
model, backend protocol, schema/profile/fixture registry, diagnostic envelope,
exception hierarchy, concept catalog, store, or policy gate.

The pinned RAES distribution does not currently ship a PEP 561 `py.typed`
marker. Keep concrete RAES annotations on the public API and confine any
`import-untyped` suppression to imports. Do not erase public types to `Any`,
copy RAES annotations into local stubs, or invent local DTOs to make mypy green.
`raes-adapters` already ships its own `py.typed`; strict mypy, documented
signatures, and behavior tests remain the local typing boundary.

## Canonical incumbents

| Concern | Published owner to compose | Base boundary |
| --- | --- | --- |
| Runtime target | `raes_runtime.registry.RuntimeTarget`, `RuntimeTargetComponents`, `BackendRegistry`; `raes_backend_protocols.backend_manifest.BackendManifest` | Construct the RAES target and let its manifest/presence/signature checks run. Do not mirror target fields, validate method shapes locally, or create another registry. |
| Backend behavior | Protocols in `raes_backend_protocols.protocols` and capability types/validators in `raes_backend_protocols.capabilities` | Driver implementations satisfy the published structural protocols. Base callables are mechanical extension seams, not another backend protocol family. |
| Logical time | `raes_runtime.time_coordinator.ReferenceTimeRuntime` and `TimeCoordinator`; closed time models and `validate_time_runtime_state` in `raes_contracts.contracts.time_model`; `time_model_conformance_diagnostics` | Reuse exact superdense coordinates, append-only history, declaration digest, lifecycle rules, and typed readback. Do not define a second clock state or infer that one simulator call equals one logical tick. |
| Stochastic control | `ExperimentStochasticControlModel`, `PublicSeedModel`, `RandomStreamControlBindingModel`, `RandomStreamDrawRecordModel`; `load_random_stream_profile` and the stateless `raes_contracts.random_stream_engine` | Apply explicitly named driver-local seed bindings and report unsupported/unbound controls honestly. Do not treat an integer seed or successful setter call as a replay claim. |
| Cleanup | `TrialCleanupPlanModel`, `TrialCleanupReceiptModel`, `validate_trial_cleanup_receipt`; `CleanupCapabilities` and `require_cleanup_plan_capability` | Sequence driver-local operations only after capability admission and return the published receipt at a portable boundary. RAES publishes no generic native cleanup executor, so do not invent one as a backend protocol. |
| Projection | The applicable closed RAES action, participant-observation, evaluation, evidence, and runtime-result models and their validators | Compose typed callables; validate the terminal portable value with its RAES owner. Do not introduce generic action/observation/reward DTOs or make native simulator tuples a shared protocol. |
| Diagnostics/results | `raes_contracts.diagnostics.Diagnostic`, `DiagnosticModel`, `diagnostic_model`; `raes_contracts.runtime_state.ApplyResult` | Portable failures use these exact types and bounded, input-free messages. Do not surface native exceptions or create a local result envelope. |
| Conformance | `raes_conformance.conformance.run_target_conformance`, `run_fixture_suite`, `profile_for_manifest`, `BackendConformanceReport`, and the published corpus roots | Delegate selection, fixture validation, target probes, bounded claims, and report construction. Do not append hand-made report cases, copy fixtures, or maintain a profile-to-contract table. |
| Runtime validation | `raes_runtime.RuntimeManager` / `RuntimeControlPlane` and their backend-call, snapshot-transition, time-readback, and result-contract gates | Exercise helpers through the public RAES manager/control plane where portable state crosses the boundary. Do not import RAES private `_call_backend_*` helpers or fork their validation. |
| Persistence | `raes_runtime.control_plane_store.ControlPlaneStore` and its existing implementations | Base helpers are in-process and stateless except for explicitly owned lifecycle state. Add no cache, repository, audit log, or evidence store. |

## Mechanics and extension seams

Runtime-target construction is composition, not translation. The driver
supplies a published `BackendManifest` and components satisfying the published
protocols; constructing `RuntimeTarget` (or using `BackendRegistry.create`)
remains the shape gate. Manifest capability declarations and actual optional
component presence must agree. A convenience factory must not catch and
reinterpret those `ValueError`s using rejected configuration values.

Logical-clock convenience must use `ReferenceTimeRuntime`/`TimeCoordinator` and
RAES time contracts. Simulator steps, participant actions, complete environment
turns, wrapper cutoffs, evaluator cutoffs, termination, truncation, reset,
replay, and cleanup are distinct events. The driver owns the explicit mapping
from a native event to an admitted clock transition; the base must not guess it.
Determinism covers the declared logical transition sequence only, not wall
clock scheduling, native simulator determinism, or outcome equivalence.

Seed application uses an explicit ordered set of driver-local bindings. Keep
each random source distinct: simulator, scenario generator, scheduler,
participant policy, action space/wrapper, Python, NumPy, evaluator, and any
backend-specific stream are separate controls. The report must distinguish
applied, unsupported, unbound, and failed controls and retain limitation
diagnostics; it must never silently skip a source, fall back to process-global
randomness, derive order from a set or mapping, or call `random.seed`/NumPy
globally unless that exact binding was explicitly supplied. Governed entropy
references are resolved only by an authorized driver-local resolver and raw
entropy never returns through the base API. Any local status collection remains
ephemeral mechanics; portable reporting uses RAES diagnostics and the existing
experiment/run contracts, not a base seed-report DTO.

Cleanup must attempt every eligible triggered obligation consistent with its
dependency order while preserving the distinction between trial outcome and
cleanup outcome. Dependency order, retry safety, required verification,
residual-state disclosure, and receipt consistency come from the RAES
plan/receipt validators. A driver-local dispatch mapping is the extension seam
for native `destroy`, `reset`, `restore`, `compensate`, `verify`, or custom
operations. Cleanup failure must neither hide the primary failure nor be
swallowed; a successful trial with failed, unverified, or residual cleanup
remains a cleanup failure. Residual state is reported by bounded reference,
never by raw native inventory.

Projection composition is direction-aware:

- action projection translates an admitted portable action into a private
  driver-native invocation;
- observation projection translates private native results into the applicable
  participant-visible RAES contract; and
- evaluation projection translates private native measures into published
  evaluation/evidence contracts.

Use generic typed callable composition rather than an inheritance hierarchy or
simulator-aware base class. The required extensibility seam is the caller-
supplied terminal validator/factory for the applicable RAES type. Intermediate
native values remain in process and are never logged, placed in diagnostics, or
returned as a portable fallback. Composition must preserve order and must not
merge action admission, execution, observation, reward, evaluation, or
termination into one ambiguous "step".

Conformance convenience returns the existing `BackendConformanceReport` from
`run_target_conformance`. Profile inference and the default fixture/profile
roots remain RAES-owned. Corpus-root overrides are test injection only, must
remain path-confined by the RAES loader, and are not production configuration.
The supported extension parameters are the runner's existing seams, including
the exact target, reference scenario, realization harness, execution basis,
selected envelope, and observer version. A driver-specific live probe belongs
behind the published harness/protocol seam; it does not mint a second report or
claim family.

## Redaction and failure hygiene

RAES provides closed diagnostic/result shapes and a redacted HTTP exception
handler, but no general native-value redactor. A small base redaction helper is
therefore legitimate mechanics. It must be default-deny and bounded:

- arbitrary objects are never stringified or recursively inspected; `repr` and
  `str` can execute backend code and expose state;
- native exceptions contribute at most an allowlisted exception type name,
  never `str(exc)`, `repr(exc)`, `args`, causes, contexts, locals, or traceback;
- rejected actions, observations, configuration values, paths, environment
  values, tokens, raw logs, stdout/stderr, argv, and native identifiers are not
  echoed;
- caller-supplied safe stage/code/address text is grammar-checked, control
  characters are rejected or normalized, and output has an explicit length
  limit no greater than `DiagnosticModel.message`'s 512-character ceiling; and
- token/path/pattern filtering is defense in depth, not permission to render an
  otherwise private value. An unsafe or unclassifiable input becomes a fixed
  sentinel.

The configurable seam is a smaller output-length bound and safe contextual
labels, not a caller-provided permissive redaction policy. Tests must use
hostile exception/string/repr objects and prove that native exception text,
object representations, rejected payloads, tracebacks, absolute and home
paths, environment values, bearer/API-like tokens, and overlong/control-
character input cannot reach the result.

## Cross-cutting layers

The shared base is an in-process library. Issue #14 adds no HTTP endpoint,
authentication mechanism, environment binding, CLI, subprocess, persistence,
or network service. Its cross-cutting path is:

1. closed RAES contract construction (`ContractModel`, generally
   `extra="forbid"`) and cross-object validators;
2. backend manifest capability/contract validation;
3. `RuntimeTarget` presence and callable-signature validation;
4. `RuntimeManager`/`RuntimeControlPlane` backend-result, snapshot-transition,
   time-readback, and result-contract validation where applicable;
5. `DiagnosticModel`/published report projection at a portable boundary; and
6. the repository's strict type, test, distribution, policy, and docs graph.

No base function reads configuration from environment variables, discovers
plugins from the filesystem, accepts arbitrary import paths, scans a user home,
or forwards process environment. If a later driver starts a subprocess, it
must use argument vectors, explicit confined working/cache directories, a
small environment allowlist, cleared `PYTHONPATH`, safe-path behavior,
timeouts, and bounded output as established by
`tools/verify_cyborg_qualification.py`; credentials and native payloads never
belong in argv or the forwarded environment.

If a later change exposes these helpers over HTTP, it must use
`raes_runtime.control_plane_api.create_control_plane_app` with
`ControlPlaneSecurityConfig.strict_defaults`, verified identities,
role/target authorization, request-size guarding, denial audit, and the
redacted exception handler. It must not add a weaker adapter endpoint.

Standard module logging, if needed, is limited to bounded operation names,
published addresses, counts, and dispositions. Portable observability uses
RAES diagnostics/reports. Never log native values, rejected inputs, secret
references or resolutions, environment/argument mappings, paths, raw
subprocess output, or tracebacks.

## Repository and verification boundaries

- Keep all base imports free of simulator extras and native simulator modules.
  `pyproject.toml` and the single `uv.lock` remain dependency authorities.
- Reuse `_verification_envs()` in `noxfile.py`: the base install and each extra
  are verified separately, never through `--all-extras`.
- Keep tests in the existing `tests` session and exercise the same plumbing
  with a non-cyber toy driver. The toy must use neutral names and behavior; it
  must not be a renamed CybORG fixture.
- Test deterministic ordering, repeated calls, partial failure, cleanup after
  failure, invalid capability/target shapes, limitation preservation, and the
  complete redaction threat set. Also prove imports and public annotations from
  a base-only clean install.
- Reuse the existing `distributions` clean-install proof and `verify` graph.
  Do not add a second workflow, build probe, policy validator, or simulator
  registry for this work.

## Non-goals and anti-patterns

- No CybORG/CAGE-2 or CyberBattleSim adapter, mapping, terminology, scenario,
  profile override, native dependency, or conformance claim is implemented.
- No authored SDL, manifest authority, schema, validation profile, fixture
  corpus, backend protocol, portable diagnostic/result envelope, store, audit
  service, or policy gate is defined by base.
- No generic simulator object model, `Environment`/`Step` DTO, Gym/PettingZoo
  tuple normalization, reward-vector abstraction, action-id registry, or
  simulator plugin discovery is introduced.
- Do not re-export broad RAES namespaces, copy private RAES helpers, catch
  `Exception` and return success, inspect native values for convenience, or
  make redaction a regex-only scrubber.
- Do not conflate seed application with deterministic replay, logical time with
  wall time or simulator turns, cleanup completion with verified clean state,
  fixture success with live target conformance, or finite conformance with
  equivalence.
- No database, cache, durable lifecycle manager, background worker, HTTP
  controller, CLI, environment-variable configuration, subprocess launcher,
  or release/workflow change belongs to issue #14.
