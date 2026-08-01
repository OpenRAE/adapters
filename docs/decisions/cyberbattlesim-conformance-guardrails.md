# CyberBattleSim conformance-composition guardrails

GitHub issue #28 is the authority for this deliverable. This note fixes how
published RAES backend conformance composes with CyberBattleSim-local executable
evidence. It defines no new contract, profile, fixture, report, or implementation
plan.

## One conformance authority, distinct evidence claims

The published RAES profile, fixtures, target probes, report type, serializer,
diagnostics, and bounded claim remain authoritative. The adapter adds evidence
about its selected source protocol; it does not extend the meaning of backend
conformance.

Keep these results distinct:

| Result | Meaning and owner |
| --- | --- |
| Backend conformance | The exact `BackendConformanceReport` returned by `run_target_conformance()` and serialized by `backend_conformance_report_payload()`. It covers the selected published profile, corpus, target probes, execution basis, and finite claim only. |
| Source-protocol reproduction | Adapter-local executable probes of the qualified CyberBattleSim selection: identity joins, reset, stochastic sources, action/observation projection, evaluator facts, termination, and cleanup. Results use RAES diagnostics and existing evidence references, but are not another backend-conformance report. |
| Research/readiness claim | A bounded interpretation of the evidence already recorded by qualification, experiment artifacts, loss disclosures, derived-measure limitations, and the conformance claim's limitations/non-claims. It must not upgrade stochastic-bounded reproduction to deterministic replay, outcome equivalence, or scientific validity. |

Do not merge these into one `passed` boolean, call local tests canonical RAES
fixtures, or set `native_conformance=True` for a deterministic injected driver.
A canonical report produced with an injected driver is hermetic adapter
conformance, not proof about the qualified native installation.

Every fixture required by the profile inferred from the manifest is applicable
and must pass. Adapter code must not rewrite a published fixture result as
unsupported. An unsupported outcome is legitimate only where a published RAES
probe/result vocabulary permits it or an adapter-local source probe reports a
genuinely unavailable source control with a validated diagnostic and limitation.
It is not an `xfail`, skip, swallowed exception, or reason to advertise the
capability. Published contract/capability gaps remain failures in the canonical
report.

## Compose existing owners

Implementation must build on these incumbents:

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Manifest | `create_cyberbattlesim_manifest()`, `BackendManifest`, RAES capability validators, `backend_manifest_v2_model()`, and `backend_manifest_payload()`. Validate the live declaration; do not keep a golden manifest payload or supported-contract list. |
| Profile and fixtures | `profile_for_manifest()`, `run_fixture_suite()`, `run_target_conformance()`, the published corpus roots, and `raes_adapters.base.run_conformance_probe()`. Production runs use default roots; root overrides remain test injection only. |
| Target and runtime gates | `create_cyberbattlesim_target()`, `build_runtime_target()`, `RuntimeTarget`, `RuntimeManager`, and `RuntimeControlPlane`. Drive all four declared backend surfaces through public RAES gates where portable state crosses the boundary. Never call private `_call_backend_*` helpers. |
| Source identity and coverage | `CYBERBATTLE_CHAIN`, `EvidenceSelection`, `load_qualification()`, the scenario/task/spec loaders, `load_source_ledger()`, `validate_source_ledger()`, and the existing qualification joins. Read the selected values; do not repeat source, scenario, seed, cutoff, or ledger constants in a probe table. |
| Reset and stochastic controls | The experiment spec's `ExperimentStochasticControlModel` values, `CyberBattleSimParticipantRuntime`, `CyberBattleSimDriver.reset()`, `DriverResetReport`, and RAES diagnostics. Preserve applied, unbound, unsupported, and failed dispositions per named stream. |
| Action and observation | `BaseParticipantRuntime`, `ParticipantActionAdmissionRequest`, `ParticipantNativeActionExecution`, `ParticipantActionResultModel`, `ParticipantObservationEnvelopeModel`, and the published admission/result/view validators. Native masks, coordinates, observations, and learned credentials stay driver-private. |
| Evaluation and evidence | `CyberBattleSimEvaluator`, `ExperimentCaptureSpecModel`, `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, proposition truth models, and their validators. Reward, objective truth, evidence, derived measures, and evaluator lifecycle remain separate. |
| Cleanup | `execute_cyberbattlesim_cleanup()`, `execute_cleanup()`, cleanup capability admission, `TrialCleanupReceiptModel`, and `validate_trial_cleanup_receipt()`. Probe success, primary failure, partial construction, repetition, and independent clean-state verification. |
| Diagnostics and report projection | `Diagnostic`, `DiagnosticModel` / `diagnostic_model()`, `ApplyResult`, `BackendConformanceReport`, and `backend_conformance_report_payload()`. Validate every emitted diagnostic and serialize through the published projection; do not use `dataclasses.asdict`, invent a JSON envelope, or echo rejected/native values. |
| Failure hygiene | `raes_adapters.base.redaction`, bounded input-free messages already used by the four backend surfaces, and the redacted RAES control-plane boundary. Native exception strings, causes, tracebacks, objects, paths, stdout/stderr, and environment mappings never become evidence. |
| Persistence | `ControlPlaneStore` is the only durable runtime-state seam. Conformance uses ephemeral target state and temporary report files; do not add a database, cache, evidence repository, or checked-in generated report. |
| Packaging and CI | `pyproject.toml`, the single `uv.lock`, `_extras()`, `_verification_envs()`, `_tests()`, `_distributions()`, `probe_installed_identity.py`, and the existing CI `PR Gate`. Extend these paths; do not add another lock, workflow, combined-extras environment, or unenforced job. |

The four backend surfaces for leak testing are provisioner, orchestrator,
participant runtime, and evaluator. Cleanup is an additional lifecycle boundary,
not a fifth semantic backend surface. Each surface needs both a successful
portable projection and a hostile failure whose native exception/payload has a
unique sentinel. Serialize the resulting `ApplyResult`, snapshot, operation
status/history, observations, evidence, diagnostics, and canonical conformance
report through their public projections and prove the sentinel and all native
representation classes are absent. Do not use `str(result)` as the leakage
oracle: that can invoke an unsafe representation and does not prove the actual
portable encoding.

## Additive probe and evidence-link boundary

Adapter probes may execute backend-local facts that RAES cannot know: selected
source/ledger identity, stream coverage, private action mapping, observation
sealing, evaluator ownership, source terminal precedence, and verified close.
They must not be appended manually to `BackendConformanceReport.cases` or passed
off as a copied fixture family. The published realization harness is used only
for realization-envelope questions it actually models; it is not a generic hook
for unrelated source-protocol assertions.

Every affirmative manifest capability must join to passing executable evidence.
Derive the capability addresses from `backend_manifest_payload()` at runtime and
join them to stable adapter-probe evidence references. The join may be a small
module-local test/probe inventory, but it is not portable authority: it carries
only manifest JSON pointers and evidence references, contains no copied
capability values or expected manifest payload, and fails closed when a newly
declared affirmative capability has no passing evidence. Negative declarations
and limitations must also be exercised so absence is not mistaken for support.
Where RAES already provides `evidence_refs`, `limitation_refs`, claim
`limitations`, or `explicit_non_claims`, reuse those fields rather than creating
adapter equivalents.

Source-ledger coverage is an integrity join through the existing validator, not
a new coverage schema. Likewise, portable-output leakage is a cross-product of
the existing public output projections and a backend-local hostile-value corpus,
not a new redaction policy or portable leakage report.

## Suite and execution boundaries

The small PR suite is deterministic and dependency-light. It uses a fully
constructed `RuntimeTarget` with an injected deterministic driver to run the
published profile/fixtures and bounded local probes. It must cover manifest and
source/profile identity, all four surfaces on success and failure, reset and
stream dispositions, action/observation/evaluator separation, terminal
semantics, cleanup, capability-to-evidence closure, and portable serialization.
It must not import the native simulator or depend on network, user-home state,
or an editable checkout.

The broader study/readiness suite uses the admitted native source and exact
qualification identity. It adds artifact-tree/module-origin verification and
source-native reset, stochastic, action, observation, reward, terminal, and
cleanup probes. Native-source absence or mismatch is an explicit readiness
result, never a fallback to the injected driver under the same label. The suite
does not strengthen the recorded research claim merely because it passes.

That native readiness lane is also where issue #28's adapter conformance
composition is checked against the real simulator. The manual run must construct
`CyberBattleSimDriver`, run `run_cyberbattlesim_conformance()` through the
adapter target, serialize the report with `backend_conformance_report_payload()`,
collect `cyberbattlesim_source_protocol_diagnostics()` and manifest capability
evidence, and verify cleanup succeeds or fails through bounded RAES diagnostics.
The emitted report, diagnostics, evidence references, and cleanup receipt must
not contain native action coordinates, observations, reward vectors, hidden
state, object representations, paths, environment dumps, or tracebacks. A
missing native installation is a readiness failure or skip in that lane; it must
not be relabeled as a passed adapter run by swapping in the deterministic driver.

Clean-install conformance belongs in the existing distribution verification
boundary: install the built wheel with the `cyberbattlesim` extra into the
throwaway environment, run from an isolated directory with `PYTHONPATH` cleared
and safe-path behavior enabled, construct the target with the deterministic
driver, run the canonical report projection, and prove the installed package
resources used by local probes are present. The native readiness lane remains
separate because the published extra intentionally does not acquire an
ungoverned upstream artifact.

The seam for the next qualified CyberBattleSim case is an explicit immutable
`EvidenceSelection` plus injected driver/harness and suite tier. Probe logic
reads scenario, protocol, stream, action, evaluator, and termination values from
that selection. Adding a selection must not require editing a cross-simulator
registry, the RAES profile corpus, report schema, or duplicated capability
catalog.

## Cross-cutting security and whole-repository path

| Layer the design passes | Required treatment |
| --- | --- |
| Authentication and authorization | None is introduced by local conformance. In-process calls use the existing runtime manager/control plane. Any later HTTP exposure must use `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`, verified identities, role/target authorization, request-size limits, denial audit, and its redacted exception handler. |
| Secret handling | No probe reads a repository/user secret store or accepts credentials. Learned source credentials and hostile sentinels remain private test/driver state. Never put tokens or secret values in evidence, diagnostics, logs, snapshots, argv, environment output, or report filenames. |
| Input and configuration shape | Qualification and `EvidenceSelection` own source selection; RAES bounded SDL parsing/compiler, closed contract models, experiment joins, manifest validators, `RuntimeTarget` signature/presence checks, and source-ledger validation all run. No environment override, arbitrary import path, permissive parser, duplicate enum, or copied schema may bypass them. |
| Runtime result and error envelopes | `RuntimeManager`/`RuntimeControlPlane` validate plans, `ApplyResult`, snapshot transitions, participant/action/history linkage, evaluation/proposition state, and operation status. `diagnostic_model()` validates local diagnostics, and `backend_conformance_report_payload()` is the only report serialization. A native mutation followed by invalid projection is failure requiring cleanup, not portable success. |
| OS/process exposure | The PR and clean-install lanes use no shell interpolation, child simulator process, runtime download, inherited environment dump, or home-cache authority. Clean-install execution uses an explicit temporary working directory, cleared `PYTHONPATH`, and `PYTHONSAFEPATH=1`. If native probing later needs a subprocess, reuse the qualification tool's argument-vector, environment-allowlist, timeout, and bounded-output pattern. |
| Logging and observability | Portable observability is RAES diagnostics, report payloads, evidence references, and declared limitations. Standard logging is limited to bounded published addresses, safe operation names, counts, and dispositions; never log native values, rejected payloads, raw reward/state, paths, environment mappings, or tracebacks. |
| Persistence and artifacts | Runtime state is ephemeral unless an existing `ControlPlaneStore` is explicitly under test. CI artifacts may contain only validated report/evidence projections and must not become a second source of truth. No native dump is made safe merely by hashing it. |
| Repository workflow | Keep tests in the canonical nox graph, base and extras isolated, strict mypy/lint/docs/policy active, and clean-wheel execution in `_distributions()`. If a CI job is ever unavoidable, it must join `PR Gate`; the default is to reuse the existing jobs. |

Failure-path probes must expose two existing envelope hazards. Several adapter
diagnostics currently use compiled dot-addresses, while `DiagnosticModel`
requires a JSON-pointer address; emitting the dataclass through an unvalidated
dictionary is not sufficient. Also, the published target runner may include the
text of an unexpected component exception in its own failure diagnostic. Every
adapter-owned native exception must therefore be caught and replaced with a
bounded, pointer-addressed diagnostic before it can reach that runner. Test the
actual published payload, not just the in-memory dataclass.

Logical clock support is a particular gotcha. The current manifest truthfully
declares no RAES time surface. A source step counter or serialized driver order
must not be relabeled as a RAES logical clock to satisfy the issue wording. The
local control probe should verify the selected source ordering/cutoff semantics
and emit a validated unsupported/limitation result for RAES clock control until
an evidence-backed time declaration, runtime, reset mapping, and conformance
case exist.

## Non-goals and anti-patterns

- No new backend profile, fixture corpus, schema registry, manifest extension,
  capability vocabulary, report DTO, diagnostic envelope, exception hierarchy,
  redaction policy, controller, store, or workflow is part of issue #28.
- Do not copy canonical fixtures into this repository, override production
  corpus roots, hand-append `ConformanceCaseResult` objects, or reconstruct a
  report with `dataclasses.replace`/`asdict`.
- Do not use a local probe inventory as a second capability table. It links
  manifest-derived addresses to executed evidence; it does not restate support.
- Do not let a fake driver satisfy native readiness, let a native skip count as
  pass, or let an unsupported source control coexist with an affirmative
  manifest claim for that control.
- Do not conflate backend conformance, source reproduction, realization,
  deterministic replay, outcome equivalence, research validity, or readiness.
- Do not conflate reset, restart, replay, cleanup, source termination, Gym
  truncation, evaluator cutoff, participant termination, logical time, and
  verified clean state.
- Do not expose native action coordinates, masks, observations, reward vectors,
  hidden/evaluator-only truth, credentials, object representations, logs,
  exceptions, tracebacks, paths, argv, or environments in a portable artifact.
- Do not add global random seeding, import-time source discovery, a floating
  source selection, a permissive availability fallback, or network-dependent PR
  tests.
- This issue does not patch or requalify CyberBattleSim, change the authored
  scenario or manifest claims, implement RAES time support, make the empty extra
  acquire native source, or create an HTTP/CLI/service surface.
