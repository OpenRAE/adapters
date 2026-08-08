# PrimAITE conformance-composition guardrails

GitHub issue #42 is the authority for this deliverable. This note fixes how
published RAES backend conformance composes with PrimAITE-local mapping,
control, leakage, and readiness evidence. It defines no new RAES profile,
fixture corpus, manifest schema, diagnostic envelope, or implementation plan.

## Keep the claims separate

The published RAES profile, fixtures, runner, report type, diagnostics, and
bounded claim remain authoritative. PrimAITE probes add source-protocol and
adapter-runtime evidence; they do not extend backend conformance.

| Result | Meaning and owner |
| --- | --- |
| Backend conformance | The exact `BackendConformanceReport` returned by `run_target_conformance()` for the profile selected from the live manifest, serialized only by `backend_conformance_report_payload()`. |
| PrimAITE source-protocol reproduction | Adapter-local executable evidence for the qualified `DATA_MANIPULATION` selection: source/ledger identity, reset and stochastic dispositions, action representability, observation withholding, evaluator-owned reward withholding, terminal semantics, cleanup, and leakage. |
| Research/readiness claim | A bounded interpretation of qualification, the public experiment protocol, loss disclosures, and declared weaknesses. It never upgrades the run to deterministic replay, source equivalence, live-native conformance, or scientific validity. |

Do not collapse these into one aggregate `passed` value. The canonical report's
`passed`, cases, gaps, limitations, `native_conformance`, and non-claims remain
intact. Local probe diagnostics, evidence references, weakness references, and
reproduction commands accompany the report as disclosure data.

Every published fixture selected by the manifest's RAES backend profile must
pass, unless the published runner itself returns a machine-readable unsupported
disposition with a non-contradictory manifest claim. Adapter code may not relabel
a failed canonical case as unsupported, append local cases to
`BackendConformanceReport.cases`, or copy profile/corpus roots into this
repository.

## Compose the existing owners

Implementation must build on these incumbents:

| Concern | Canonical incumbent and required use |
| --- | --- |
| Manifest and profile authority | `create_primaite_manifest()`, `BackendManifest`, RAES capability models, `backend_manifest_v2_model()`, `backend_manifest_payload()`, `profile_for_manifest()`, `run_fixture_suite()`, `run_target_conformance()`, published corpus roots, and `raes_adapters.base.run_conformance_probe()`. No golden manifest payload, copied supported-contract table, local profile, or production root override. |
| Target and runtime gates | `create_primaite_target()`, `build_runtime_target()`, `RuntimeTarget`, `RuntimeManager`, and `RuntimeControlPlane`. Exercise portable state transitions through public RAES gates; do not import RAES private backend-call helpers. |
| Source identity and coverage | `DATA_MANIPULATION`, `EvidenceSelection`, `LEDGER`, `load_qualification()`, `validate_all()`, `load_loss_disclosures()`, `qualification.json`, `public-protocol.md`, SDL, experiment task/spec, source ledger, and loss disclosures. Read the selected values and pinned digests; do not transcribe them into a probe catalog. |
| Installed-source admission | `PrimaiteDriver` and `raes_adapters._source_admission`: distribution version, artifact identity, complete import-root digest, selected-file digests, and module-origin checks before any native import. The current live driver fails closed after verification; tests may inject a driver but cannot make that run native-live. |
| Shared gym mechanics | `_gym_backend.conformance`, `_conformance_support`, `GymEpisodeOrchestrator`, `GymEvaluator`, `execute_gym_cleanup`, base lifecycle, and base cleanup/redaction helpers. Extend narrow shared seams when a touched path already matches them; do not fork traversal, report projection, cleanup receipt construction, or participant lifecycle logic. |
| PrimAITE-specific surfaces | `PrimaiteProvisioner`, `PrimaiteParticipantRuntime`, `PrimaiteEvaluator`, `execute_primaite_cleanup`, and the fail-closed `PrimaiteDriverProtocol`. Their job is source-selection joins and bounded PrimAITE projection, not another RAES controller family. |
| Action and observation | `ParticipantActionAdmissionRequest`, `ParticipantValidatedActionSelection`, `ParticipantNativeActionExecution`, `ParticipantActionResultModel`, `ParticipantObservationEnvelopeModel`, participant exposure/history validators, and the existing PrimAITE action-representability boundary. No native `Discrete(78)` id, flattened `Box(1652)` value, action mask, `info`, or hidden state crosses. |
| Evaluation and reward | `PrimaiteEvaluator`, `ExperimentCaptureSpecModel`, `ExperimentEvidenceRecordModel`, proposition truth/result models, and `_experiment_evidence`. Reward remains evaluator-only and withheld until source-member evidence closes; do not project a score or derived reward measure merely because a fake driver returns a number. |
| Cleanup | `TrialCleanupPlanModel`, `CleanupCapabilities`, `require_cleanup_plan_capability()`, `execute_cleanup()`, `TrialCleanupReceiptModel`, and `validate_trial_cleanup_receipt()`. Close/reset/verify are private driver operations; cleanup evidence is a receipt, not a native state dump. |
| Diagnostics and leakage | RAES `Diagnostic`, `diagnostic_model()`, `diagnostic_payload()`, `ApplyResult`, shared `diagnostic_address()`, `redact_native_value()`, and `bounded_context_label()`. Use pointer-addressed, input-free diagnostics and validate before serialization. Add no diagnostic or exception hierarchy. |
| Reports and artifacts | `backend_conformance_report_payload()`, `write_backend_conformance_report()`, and `atomic_write_json_artifact()` when artifacts are written. Use explicit confined output roots and relative references; do not check in generated reports or create an evidence repository. |
| Packaging and workflow | `pyproject.toml`, the empty dependency-light `primaite` extra, the single `uv.lock`, `_extras()`, `_verification_envs()`, `_tests()`, `_distributions()`, `probe_installed_identity.py`, `.github/workflows/ci.yml`, `PR Gate`, and `nox -s verify`. Add no second lockfile, combined-extra install, parallel workflow, or unenforced CI job. |

The existing `tests/test_primaite_backend.py`, shared scenario-ledger tests, and
CyberBattleSim/NASim/CybORG conformance suites are precedents for composition
and hostile leakage tests. Reuse their shared mechanics and patterns, not their
source semantics or private driver code.

## Additive probes and evidence closure

Adapter-local probes cover facts RAES cannot infer from the generic profile:
selected source and profile identity, source-ledger coverage, reset and
stochastic stream dispositions, source step ordering, action representability,
observation withholding, evaluator projection and reward withholding, terminal
cutoff semantics, cleanup, and portable-output leakage.

They must not become a second profile table, fixture corpus, schema registry,
manifest authority, or copied capability catalog. Derive affirmative capability
JSON pointers from the live `backend_manifest_payload()` and join each pointer
to stable evidence references only when the owning probes passed. A newly
declared affirmative capability with no explicit evidence requirement must fail
closed as an evidence gap.

Capability evidence is lane-scoped. A deterministic injected-driver PR run may
close the portable-mechanics evidence it actually exercises, with
`native_conformance=false` and explicit non-claims. It must not certify that the
live PrimAITE source runs safely in-process, that CPython 3.12 native evidence
exists, or that stochastic replay/equivalence was achieved. Any no-argument
production-live evidence API remains conservative unless a real, qualified,
isolated live driver supplies passing evidence.

Leakage coverage is the success/failure cross-product over the four declared
backend surfaces: provisioner, orchestrator, participant runtime, and evaluator.
Cleanup is an additional lifecycle boundary. Inspect actual JSON-ready
projections, not `repr`: `ApplyResult`, snapshots, entries, histories,
participant action results, observations, evaluator results, evidence records,
cleanup receipts, diagnostics, canonical reports, and any suite index. Hostile
sentinels must cover native ids, arrays, masks, `info`, reward values/components,
paths, logs, exception text and types, tracebacks, argv/environment data, and
credential-shaped strings.

Portable caller-authored input may survive a successful plan. Failure-path tests
prove rejected or native values are not echoed. A native mutation followed by
projection or RAES validation failure remains failure requiring cleanup; portable
success cannot be synthesized after rollback is impossible.

## Suite and output boundaries

The PR suite is deterministic, offline, dependency-light, and clean-installable
under the `primaite` extra. It uses a fully constructed `RuntimeTarget`, an
explicit injected driver, fixed ordered seeds, published RAES conformance,
source-protocol diagnostics, adapter-local probes, capability-evidence closure,
declared weaknesses, leakage checks, report projection, and cleanup. It must not
derive seed, case order, corpus roots, or suite tier from time, PR number,
hashing, global random state, test order, or environment variables.

The broader study/readiness tier may use the same report and local evidence
shape but cannot run live PrimAITE in-process under the current architecture.
Live readiness remains blocked until a separately reviewed worker/process
isolation boundary and bounded CPython 3.12 qualification evidence exist. Source
absence, source mismatch, unsupported path confinement, or cleanup failure is an
explicit readiness result, never a fallback to the injected driver under a
native label.

Machine-readable output may coordinate the evidence, but it must preserve
ownership:

- the canonical report is serialized only through
  `backend_conformance_report_payload()` and persisted only through the RAES
  report writer;
- local diagnostics are validated with `diagnostic_model()` and serialized with
  `diagnostic_payload()`;
- capability evidence is pointer-to-reference data derived from the live
  manifest, not copied capability values;
- declared weaknesses are derived from qualification limitations and selected
  loss disclosures, not a second list; and
- reproduction commands are fixed argv arrays with no shell interpolation,
  secrets, absolute paths, or environment dumps.

An operational index must not introduce a second report schema, profile, case
family, diagnostic envelope, or aggregate `passed` field.

## Manual native-readiness protocol

The manual integration lane is the documented hands-on gate where the same
adapter conformance composition is checked against the real simulator on the
qualified runtime, never a stand-in. It must explicitly construct a real
`PrimaiteDriver` and a complete `RuntimeTarget`, run `run_primaite_conformance()`
through that target, serialize the canonical report through
`backend_conformance_report_payload()`, collect
`primaite_source_protocol_diagnostics()` and the fail-closed manifest capability
disclosure, validate every local diagnostic, and verify cleanup. It does not
replace the deterministic injected-driver CI probe; it exercises the same
composition against installed PrimAITE.

Under the current architecture that lane cannot complete: the live driver
verifies source identity and then refuses in-process construction, so **native
readiness remains blocked** pending a separately reviewed worker/process
isolation boundary and bounded CPython 3.12 qualification evidence. Missing
source, a mismatched installation, unsupported path confinement, or cleanup
failure is an explicit readiness result, never a fallback to the deterministic
injected-driver lane under a native label. The emitted report, diagnostics,
evidence references, and cleanup receipt **must not contain native action
coordinates**, observations, reward vectors, hidden state, object
representations, paths, environment dumps, or tracebacks; the operator records
only the command, qualified identities, dispositions, and cleanup result.

## Cross-cutting security and whole-repository path

| Layer the design passes | Required treatment |
| --- | --- |
| Authentication and authorization | Local conformance introduces no route, daemon, controller, or caller authority. In-process work uses `RuntimeManager`/`RuntimeControlPlane`. Any later network exposure must use `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`, verified identities, role/target authorization, request-size limits, denial audit, and the redacted exception handler. |
| Secret handling | No probe reads a secret store or accepts credentials. Do not read user or repository secrets, bind source identity from environment, or expose tokens, learned credentials, credential-shaped sentinels, environment data, argv, or secret references in diagnostics, evidence, logs, filenames, reports, or suite indexes. |
| Static parsing and config shape | `EvidenceSelection`, strict scenario-ledger validation, RAES SDL parsing/compilation, closed experiment/manifest models, realization-envelope validators, profile/corpus loaders, and `RuntimeTarget` presence/signature checks all run. No arbitrary import path, native config path, environment-selected seed/profile/corpus, permissive enum, copied schema, or native action id bypasses them. |
| Source and OS boundary | The current live driver verifies source identity and then refuses in-process construction because PrimAITE writes platform application/session/log directories on import and the qualified runtime is CPython 3.11. Do not mutate process-global `HOME`, cwd, `sys.path`, or platformdirs state to work around this. Clean-install conformance runs from an isolated directory with `-I`, cleared `PYTHONPATH`, and `PYTHONSAFEPATH=1`. |
| Runtime and result envelopes | `RuntimeManager`/`RuntimeControlPlane` validate plans, snapshots, `ApplyResult`, changed addresses, participant/action/history linkage, evaluator/proposition state, cleanup receipts, and operation statuses where applicable. Adapter probes add only selected-PrimAITE representability and private projection checks. |
| Error envelopes | Catch native failures at the component/driver boundary before RAES generic diagnostics can include hostile exception context. Emit fixed, pointer-addressed RAES diagnostics with bounded messages. Never include exception strings, hostile type names, args, causes, locals, paths, stdout/stderr, logs, tracebacks, rejected native values, or source payloads. |
| Logging and observability | Portable observability is RAES reports, validated diagnostics, evidence references, declared weaknesses, cleanup receipts, and fixed reproduction argv. Logging, if added, is limited to safe operation names, published pointers, counts, and dispositions. |
| Persistence and artifacts | `ControlPlaneStore` remains the runtime persistence seam. Conformance artifacts are validated portable JSON beneath an explicit confined output root. No native dump, hash of a native dump, cache, database, evidence repository, or checked-in generated report is added. |
| Repository workflow | Keep the single distribution/lock, isolated extras, strict lint/type/test/docs/policy gates, installed-wheel proof, CI `PR Gate`, and requirement-free `--skip-requirement` posture. A scheduled/full tier extends the existing workflow pattern and does not masquerade as required PR conformance unless included in `PR Gate`. |

## Extension seam

The extension seam is an immutable `EvidenceSelection`, an explicit suite/seed
tier, a driver factory for that selection, and a declared execution basis.
Source protocol, stochastic streams, action representability, evaluator facts,
terminal controls, and weakness references are read from the selection and its
driver; they are not stored in a cross-simulator registry.

The obvious future action variation belongs in a governed typed argument shape
arriving through `ParticipantValidatedActionSelection`. The obvious future live
runtime variation belongs at a reviewed worker/process boundary plus a new
qualified selection/runtime evidence record. Neither requires a generic Gym
driver, a base simulator protocol, a manifest extension, or an opaque options
mapping.

## Gotchas and anti-patterns

- Do not treat a fake driver, successful import, clean install, source smoke, or
  finite green suite as live-native conformance or deterministic replay.
- Do not use the broad BLUE action contracts to choose a native `Discrete(78)`
  operation, and do not expose native action ids or option dictionaries as the
  missing selector.
- Do not project the flattened `Box(1652)` observation, action mask, native
  `info`, hidden state, reward components, or cumulative reward. Current reward
  evidence is a withholding disclosure, not a score.
- Do not conflate the PrimAITE source protocol selection with the published RAES
  backend conformance profile.
- Do not invent RAES logical time for PrimAITE. Serialized source step order and
  fixed-horizon truncation are source-protocol facts unless a published time
  runtime, declaration, reset mapping, and evidence-backed manifest claim exist.
- Do not rewrite the current fail-closed live-driver boundary by mutating
  process-global paths, importing PrimAITE at module import time, installing the
  RL/Torch stack opportunistically, or hiding Python-runtime mismatch behind a
  manifest note.
- Do not serialize native values and redact afterward, use `str(result)` as a
  leakage oracle, or rely only on the generic report redaction gate.
- Do not duplicate RAES schemas, validators, capability vocabularies, diagnostic
  envelopes, exception hierarchies, lifecycle controllers, stores, conformance
  cases, workflow logic, or fixture roots.
- Do not import CybORG, CyberBattleSim, or NASim backend code as a PrimAITE
  dependency. Shared mechanics belong in shared helpers only when the touched
  behavior is already cross-backend and semantics-free.
- Do not create a second CI workflow, per-adapter lockfile, combined-extra
  environment, runtime network install, subprocess launcher, plugin discovery,
  database, cache, or evidence service for this issue.

## Non-goals

Issue #42 does not implement live PrimAITE execution, requalify PrimAITE for
CPython 3.12, approve worker-process isolation, revise the authored scenario,
invent precise action variants, close observation/reward source-member evidence,
or establish deterministic replay, outcome equivalence, source equivalence, or
scientific validity.

It also does not add a backend profile, fixture corpus, manifest extension,
schema registry, capability vocabulary, report DTO, diagnostic envelope,
exception hierarchy, redaction policy, store, controller, HTTP surface, CLI,
daemon, dependency graph, second distribution, second lockfile, or separate
workflow.
