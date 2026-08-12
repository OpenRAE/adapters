# Capability and evidence-claim integrity guardrails

GitHub issue #84 is the authority for this repository-wide correction. This
note fixes the claim boundaries every adapter, shared helper, command, and
conformance lane must respect. It defines no new RAES contract, capability,
evidence type, status vocabulary, or implementation plan.

## Keep four claims distinct

An authored task requirement, a backend capability declaration, a captured
run artifact, and a post-run satisfaction claim are different facts with
different owners:

- `ExperimentTaskModel` owns what evidence the author requires. A requirement
  is demand, not proof that an adapter can capture it.
- The published RAES `BackendManifest` and capability models own what the
  selected production target advertises. A capability is admissible only when
  its production component and capture path are executable; a constraint,
  source-ledger row, injected driver, or planned feature is not a substitute.
- `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, and
  `ExperimentArtifactRefModel` describe what one run actually emitted. A file
  containing an evaluator summary is not an action log, availability series,
  host-compromise series, or reward-component record merely because all of
  them concern the same episode.
- `validate_experiment_run_against_task()` owns the task/run satisfaction join.
  Conformance, qualification, source admission, cleanup, or a successful run
  cannot bypass that join or manufacture its inputs.

The pinned RAES contract validates a semantic `satisfies_refs` entry by
reference identity. `ExperimentEvidenceSatisfactionReferenceModel` cannot
express required-field coverage or the availability, redaction, withholding,
or loss status of those fields. Therefore a generic authored evidence concept
must not be placed in `satisfies_refs` until the applicable published RAES
contract can express and validate the complete artifact-and-field witness.
Current researcher tasks that require such a concept must fail closed even if
that makes an adapter or example temporarily non-runnable. An exact authored
artifact identity remains admissible only where the existing RAES validator
can verify its identity and any authored digest/path constraints directly.

## Canonical incumbents

| Concern | Canonical owner and required use |
| --- | --- |
| Manifest and capability shape | RAES `BackendManifest`, `BackendCapabilitySet`, component capability models, `backend_manifest_payload()`, capability-admission helpers, and `RuntimeTarget` presence/signature validation. Do not add an adapter capability schema or infer support from component existence alone. |
| Runtime admission | `RuntimeManager.plan()`, public target components, `ApplyResult`, snapshot-transition validation, participant admission/history validation, evaluator result validation, and cleanup receipt validation. Every affirmative production claim must survive its applicable public execution path. |
| Experiment evidence | RAES capture-spec, evidence-record, derived-measure, artifact, run, and task models plus `_experiment_evidence.py` and `_researcher_support.py` for mechanics only. Backend-local code owns source projection; shared helpers must not assign semantic evidence identities. |
| Task/run joins | `validate_experiment_run_against_task()` and `validate_experiment_study_against_tasks_and_runs()`. Do not copy their join logic or predeclare a positive result in `_BackendAdapter`, a manifest constraint, or a pack file. |
| Manifest conformance | `run_conformance_probe()`, canonical RAES report projection/writer, and executable adapter-local probes. `affirmative_capability_pointers()` is inventory only; a static pointer-to-reference table and one broad pass flag are not proof that each leaf was exercised. |
| Source truth | Backend qualification records, source admission, scenario/source ledgers, and loss disclosures. These establish provenance and bounded source facts; they do not satisfy per-run capture requirements. |
| Failures and disclosure | RAES `Diagnostic`/`DiagnosticModel`, `diagnostic_model()`, `ApplyResult`, stable command exit codes, and `base.redaction`. Missing, unavailable, withheld, redacted, lossy, unsupported, and failed must remain distinct non-success dispositions. |
| Persistence | `atomic_write_json_artifact()`, the RAES conformance report writer, exclusive confined output roots, and inventory-last sealing. Runtime state remains behind RAES runtime/control-plane ownership; no evidence registry, cache, or adapter store is introduced. |
| Verification | Existing repository tests, clean-installed distribution probes, the single nox graph, and the `PR Gate`. Negative tests must exercise every registered adapter and shared command path, not a hand-maintained subset that silently omits the next adapter. |

Backend manifests may contain declarative values, but those values are not
self-authenticating. Shared constructors such as standard evaluator,
orchestrator, or cleanup capability builders may factor shape only after the
caller supplies truth established by the production path. They must not grant
support merely because several gym-style adapters are expected to share it.
Likewise, reporting every PrimAITE capability as an open conformance gap does
not make its affirmative production manifest truthful; an inadmissible adapter
is allowed to break.

## Validation and security path

| Layer the design passes | Required treatment |
| --- | --- |
| Authentication and authorization | The current researcher command is local and adds no auth surface. Participant authority still comes from exact manifest/selection/configuration joins and public participant admission. Any later network surface must use the RAES strict-default control-plane security, verified identity, role/target authorization, request limits, denial audit, and redacted exception handling; adapters do not add endpoints. |
| Secrets and environment bindings | No claim path reads credentials, a secret store, `.env`, or ambient configuration. Do not add token options or environment-selected capability/evidence overrides. Native credentials, action details, observations, rewards, argv, environment maps, and source paths never enter portable evidence or diagnostics. |
| Static input and config shape | Reuse closed `argparse` choices, per-backend required/foreign argument checks, pack digest validation, confined child resolution, duplicate-key-rejecting JSON loading, RAES SDL parsing, closed contract models, participant joins, target config normalizers, and selected-source admission. No arbitrary import, driver, profile, schema, or capture map is caller-selectable. |
| Runtime validators | Preserve manifest/component checks, capability admission, plan/resource/dependency validation, `ApplyResult` shape, snapshot transitions, participant action/result/history joins, evaluator/proposition checks, and cleanup verification. A native transition with an unverifiable projection is failure, not partial evidence satisfaction. |
| OS and process exposure | Keep relative confined outputs, exclusive mode-0700 creation, atomic publication, no shell interpolation or runtime download, clean-install isolation, cleared `PYTHONPATH`, `PYTHONSAFEPATH=1`, and discarded native stdout/stderr. Do not put evidence payloads, credentials, or native paths in argv or filenames. |
| Error envelopes and observability | Reuse bounded `_CommandFailure` messages, RAES diagnostics, canonical report projection, and default-deny redaction. Logs and terminal output may carry safe identities, pointers, counts, and dispositions only. Never serialize exception text, rejected values, native output, object representations, or tracebacks. |
| Artifact publication | Validate RAES models and task/run joins before sealing success; write the final inventory last. A checksum proves byte identity, not semantic completeness or safety. Failure, cleanup failure, or an unsatisfied requirement cannot be published with a successful disposition. |

## Extension seam

The extension seam is the existing backend strategy boundary, parameterized by
the live `BackendManifest`, the authored `ExperimentTaskModel`, and the actual
validated evidence records/artifact bytes from that run. A future published
RAES satisfaction contract may be consumed there without changing authored
task semantics or adding a repository schema. Until that owner can validate
field-level witnesses and negative data-quality states, the seam returns no
semantic satisfaction claim and lets the canonical task/run validator reject
the run.

A future adapter registers with the existing command/target strategy and is
automatically included by repository-wide claim-integrity tests. It must not
require editing a global evidence allowlist, standard capability grant, copied
schema, or backend-name conditional.

## Gotchas and anti-patterns

- Do not retain `evidence_satisfies_refs`, a backend-name evidence allowlist,
  unconditional `supports_* = True`, or a test-only/injected-driver bypass.
- Do not promote a source-ledger reference, capability pointer, conformance
  evidence id, capture-spec declaration, content checksum, or evidence-record
  existence into per-run satisfaction.
- Do not let an evaluator summary satisfy an action/observation/time-series
  requirement when those records and required fields were not emitted.
- Do not treat missing, unavailable, redacted, withheld, lossy, unknown,
  unsupported, partial, or unverified as aliases for satisfied.
- Do not define a local field-witness DTO, evidence status enum, validator,
  exception hierarchy, manifest extension, profile, registry, or persistence
  service to work around a missing RAES contract.
- Do not make positive tests depend only on current adapters. Mutation and
  negative cases must catch a new manifest leaf, a new adapter registration,
  an omitted artifact, missing required content, a negative data-quality state,
  and a static reference reintroduced through any shared path.

## Non-goals and boundaries

Issue #84 does not implement missing action logs, availability or compromise
series, reward-component capture, source qualification, deterministic replay,
scientific equivalence, or new researcher backends. It does not rewrite
authored task semantics merely to keep current examples runnable.

It also does not add or change a RAES schema, capability vocabulary, evidence
type, status model, validator, profile, diagnostic envelope, controller, store,
HTTP surface, console script, distribution, lockfile, or workflow. If a
published RAES contract cannot express and verify the required claim, the
repository records the gap by failing closed rather than creating local
authority.
