# CybORG reward, objective, and outcome projection guardrails

GitHub issue #18 is the authority for this increment. This note fixes the
scientific-concept boundaries, source-fact commit rule, validation path,
exposure policy, and claim limits that implementation must preserve. It adds no
adapter contract and is not an implementation plan. The transaction,
quarantine, terminal, stochastic, participant-isolation, and source-selection
rules in the existing CybORG guardrail notes remain in force.

## Keep the scientific concepts separate

The pinned source computes reward during an aggregate native turn. That timing
does not make every related fact one score or give the participant access to
evaluator truth.

| Concept | Canonical carrier and boundary |
| --- | --- |
| Source reward component | A separately named, source-row-backed evaluator fact. Preserve its source sign, one-shot/persistent behavior, and step boundary. Never export the native reward mapping/vector. |
| Cumulative source score | A derived measure over committed per-step components, and an evaluation result `score` only where the compiled result contract permits scoring. It is not a pass/fail result. |
| Objective/proposition satisfaction | `PropositionTruthResultModel`, including observed/declared basis, polarity, evidence, temporal context, indeterminacy, and loss. Missing facts produce `unknown` or `unsupported`, not false. |
| Evaluation lifecycle | `EvaluationResultStateModel` and `EvaluationHistoryEventModel`, validated against the operation's compiled `EvaluationResultContract` and `EvaluationExecutionContract`. Failed lifecycle state carries no score or passed value. |
| Participant outcome | `ParticipantOutcomeInterpretationRecordModel` / `ParticipantOutcomeReportModel`, only when an admitted interpretation rule and participant-visible sources support it. These models deliberately have no score or reward field. |
| Workflow success | Existing workflow execution state/history. A completed step limit or clean stop is not objective satisfaction or participant success. |
| Backend conformance | The published RAES conformance runner/report only. Evaluator output and matching source arithmetic do not extend its finite claim. |
| Derived measure or margin | A distinct `ExperimentDerivedMeasureModel` with a revisioned metric/method and evidence refs. RAES 2.0.0 has no generic free-form margin field; do not hide a margin in result `detail` or metadata. |
| Replication/equivalence claim | A separately governed claim over an eligible evidence set. It must retain the qualification and loss disclosures; no component or total proves equivalence by itself. |

Host compromise, restore, critical impact, terminal state, and score are also
distinct facts. A host-compromise predicate can support a proposition result
without becoming a participant observation. Restore intent, restore execution,
restore cost, and restored state are not interchangeable. Critical impact may
persist across source steps; a terminal step may still carry reward. Preserve
the selected calculator's exact timing and arithmetic rather than inferring
these facts from action names or from the final total.

## One capture and commit boundary

The verified `SourceInstalledCyborgDriver` is the only layer permitted to
inspect the exact selected native result/calculator surfaces. During the one
serialized aggregate turn it may construct a strict backend-private projection
containing only allowlisted finite scalars, booleans, stable portable joins, and
fact availability. Native mappings, vectors, observations, truth dictionaries,
objects, ids, and representations are discarded at that boundary.

Projected evaluation facts follow the same all-or-nothing commit as action,
participant history, observation staging, shared state, workflow, and logical
time. A fact from an effectful turn is visible to the evaluator only after the
complete portable candidate passes validation. Projection or validation
failure returns the predecessor snapshot, publishes no evidence from that
turn, and quarantines the already-mutated native session. Retry, receipt replay,
status readback, or repeated evaluator reconciliation must not count the turn a
second time.

The active episode's sanitized fact history and accumulators are ephemeral
session mechanics under the existing `CyborgProvisioner.execution_transaction`
lock and lifecycle. They reset/reconstruct/stop with the aggregate session and
must not be written to `RuntimeSnapshot.metadata`, `ApplyResult.details`, a
participant cache, a new repository, or a process-global singleton. The RAES
snapshot carries portable evaluation state; `ControlPlaneStore` remains the
durable snapshot, receipt, idempotency, and audit owner.

## Canonical incumbents to compose

| Concern | Required incumbent |
| --- | --- |
| Source authority | `qualification.json`, `SourceInstalledCyborgDriver`'s selected-file/tree verification, `CAGE2_SOURCE_26CE1C1`, `load_source_ledger`/`validate_all`, and source-ledger rows `control-turn-order`, `reward-components`, `reward-objectives`, `evaluation-derived-measures`, plus applicable loss disclosures. |
| Evaluation protocol | Published `Evaluator`, `EvaluationPlan`/`EvaluationOp`, admitted operation payloads and startup order. Do not add a CybORG evaluation-plan DTO or public `evaluate_step` protocol. |
| Runtime results | `EvaluationResultContract`, `EvaluationExecutionContract`, `EvaluationResultStateModel`, `EvaluationHistoryEventModel`, and `evaluation_result_contract_diagnostics`. Preserve resource address/type/run/history joins. |
| Objective truth | `PropositionTruthResultModel` and `proposition_truth_contract_diagnostics`. Use its evidence, temporal, polarity, probe-binding, unsupported, indeterminacy, and loss rules; do not create a bool-only objective result. |
| Evidence and measures | `ExperimentCaptureSpecModel`, `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, typed experiment references, and `project_evaluation`. Construct the closed RAES models and link every measure to concrete evidence records. |
| Participant outcomes and isolation | Existing CybORG participant runtime, participant outcome interpretation/report models, participant-scoped retrieval views, compiled observation/exposure policy, and participant history validators. Evaluator-only facts never enter participant observations, action results, histories, status, or outcome reports. |
| Target/capabilities | `EvaluatorCapabilities`, `BackendCapabilitySet`, `BackendManifest`, `backend_manifest_payload`, `RuntimeTargetComponents`, `build_runtime_target`, and runtime target-shape/signature checks. Declare only executable sections, predicate families, evidence channels, time domains, scoring, and objective support. |
| Failure and observability | RAES `Diagnostic`/`ApplyResult`, existing bounded CybORG diagnostic style, and base default-deny projection/redaction helpers. Reuse the RAES result envelope; add no exception hierarchy or local diagnostic DTO. |
| Scientific run artifacts | Published experiment run/task/study, traceability, validity, stochastic-control, and result-summary contracts when a run artifact is in scope. The adapter does not invent a parallel evidence bundle or claim schema. |
| Verification | Existing CybORG source-ledger and qualification tests, target/manager integration tests, `_verification_envs()`, clean-install distribution proof, strict docs/policy gates, and canonical `nox -s verify`. Add no second workflow or simulator-specific lock. |

`CyberBattleSimEvaluator` is the closest repository example for evaluator
reconciliation, typed evidence, derived measures, bounded failures, and target
composition. Reuse those RAES-owned shapes and runtime gates, but do not copy
its source-specific single-summary semantics, task identity, metric, wall-clock
assumptions, stochastic limitations, or proposition policy into CybORG.

The current RAES `Evaluator` protocol publicly exposes evaluation
result/history lifecycle, but not capture-spec, evidence-record, or
derived-measure retrieval methods. Typed component accessors like the existing
CyberBattleSim example may demonstrate model construction, but are not by
themselves a published RAES emission path. If acceptance requires those
artifacts through a portable runtime/export boundary, use an existing RAES run
artifact path that carries the exact models; if no applicable public path
exists, record an upstream contract gap rather than creating a CybORG schema or
smuggling artifacts through status, details, or snapshot metadata.

## Traceability, aggregation, and limitations

Every evidence record and measure must join the admitted run, participant
episode where applicable, logical step, controlling action instance, evaluation
resource, selected source profile/commit, exact source-ledger row ids, and a
revisioned derivation method. Use typed RAES references and ids derived from
canonical portable coordinates. Never derive identity from native ids, paths,
dict order, object hashes, `str`, or `repr`.

Keep one evidence-bearing value per scientific meaning. Component measures are
not encoded as an ordered vector; cumulative score is derived from the exact
committed component sequence. Preserve the pinned source's numeric operation
and order, including signs, terminal-step contribution, restore-cost timing,
and persistent-impact behavior. Do not silently change source float semantics
with absolute values, sign normalization, rounding, Decimal conversion, or a
different summation algorithm. Reject non-finite or wrong-typed native values
before publication.

Cross-check representative component rows and cumulative totals against both
the pinned upstream calculators and the validated source-ledger selection.
Tests must independently catch sign inversion, omitted/double-counted terminal
reward, reset carry-over, restore charged at the wrong step, persistent impact
treated as one-shot, component/total disagreement, and replay double-counting.
A total that happens to match while its components or joins are wrong is a
failure.

Unavailable, withheld, stale, contradictory, or unmapped source facts are data,
not zero. Use the applicable `missing`/`withheld` derived-measure status,
`unknown`/`unsupported` proposition outcome, indeterminacy/loss disclosure, or
failed evaluation check. Do not publish a partial total as complete. Every
redacted/withheld evidence record includes the contract-required loss
disclosure, and every stronger claim retains `loss-evaluation-seed-unbound`,
`loss-blue-policy-artifact-unbound`, `loss-native-observation-boundary`, and
`loss-remove-success-misreport` where relevant.

## Cross-cutting security and whole-repository path

| Layer the design passes | Required treatment |
| --- | --- |
| Closed target config | `_normalized_config` and `_validate_selection` remain the profile/version/commit/ledger/seed/driver authority and reject unknown keys. Metric meaning, aggregation, trial length, terminal policy, and derivation version come from selected source plus admitted RAES artifacts, not env vars or target flags. |
| Source and native shape checks | Verified source snapshot, exact selected native types, the existing native-random lock, aggregate session lock, and strict private projection fail closed. No unverified fallback, runtime import string, arbitrary calculator, or caller-supplied native field selector. |
| RAES parsers/validators | Plan address/domain validation; compiled result/execution contracts; closed evidence/measure/proposition/outcome models; manifest controlled vocabularies and supported-contract checks; manager backend-result, changed-address, snapshot-transition, evaluation-result, proposition-truth, participant, workflow, shared-state, and time validators all remain authoritative. Adapter validation covers only selected-source representability and arithmetic consistency. |
| Authentication/authorization | Issue #18 adds no route or controller. In-process evaluator authority does not grant participant visibility. Any later network path must reuse RAES `create_control_plane_app` with `ControlPlaneSecurityConfig.strict_defaults`, verified identity, role/target authorization, request-size limits, denial audit, and redacted exception handling; no adapter endpoint. |
| Secret/exposure surface | No secret is required or read. Credentials, sessions, hidden truth, native observations, policy state, entropy, tokens, environment values, and evaluator-only host detail never enter participant-visible output or portable artifacts. Only deliberately projected semantic facts and typed refs cross the evaluator boundary. |
| OS/process surface | Reuse the in-process verified private source snapshot and temporary scenario workspace. Add no subprocess, shell, network fetch, plugin discovery, inherited-env forwarding, argv payload, stdout/stderr capture, or persistent native file. Paths and temporary names never become evidence refs. |
| Error/log envelope | Use stable bounded diagnostics containing only published addresses, safe stages/dispositions, and counts. Never interpolate native values, reward structures, hidden facts, rejected payloads, exception text/args/causes, paths, object types from hostile values, logs, or tracebacks. Logging, if added, uses the same allowlist. |
| Persistence/export | `RuntimeSnapshot` evaluation carriers and `ControlPlaneStore` own portable runtime persistence; published experiment artifact contracts own archival output. No adapter DB, evidence repository, replay cache, custom serializer, or free-form status/details export. |
| Packaging/workflow | Preserve lazy CybORG imports, the single `pyproject.toml`/`uv.lock`, existing qualification verifier, source-ledger package resources, tests/type/lint/docs/policy/distribution sessions, and canonical verification graph. |

## Extension seam

The extension seam is a selected-profile, revisioned projection from one
committed aggregate-turn fact set to named metric/proposition bindings supplied
by admitted RAES evaluation resources. The binding is keyed by source-ledger
row, metric/proposition address, derivation version, and portable run/episode/
step/action coordinates. It is backend-private mechanics, not a generic metric
registry or new portable schema.

A future reviewed source revision, new reward component, objective predicate,
trial length, red variant, or multi-run statistic should add a source mapping
and derivation binding without changing RAES result/evidence models, participant
isolation, session ownership, persistence, diagnostics, or conformance claims.
Multi-episode mean and sample standard deviation belong at the experiment
analysis/study seam over eligible per-run measures; they must not be folded into
the per-step accumulator.

## Gotchas and anti-patterns

- Do not expose a reward vector/map, native state delta, host truth payload, or
  a “sanitized” native object. Construct closed RAES models from allowlisted
  facts.
- Do not treat `Results.done`, wrapper cutoff, admitted step limit, evaluator
  cutoff, participant termination, and workflow completion as one terminal bit.
- Do not infer compromise, successful restore, impact, objective satisfaction,
  or participant success from the submitted/native action name or native
  success flag.
- Do not use one total for evaluator pass/fail, participant outcome, workflow
  success, backend conformance, scenario correctness, or semantic equivalence.
- Do not put components, margins, provenance, loss, or semantic joins in
  `detail`, `metadata`, logs, Markdown-only prose, or ad hoc dictionaries because
  a published RAES carrier is inconvenient.
- Do not duplicate RAES evidence, result, truth, outcome, reference,
  diagnostic, exception, validation, persistence, or claim schemas in
  `raes_adapters.base` or `raes_adapters.cyborg`.
- Do not repair the selected Remove misreport, seed gap, blue-policy artifact
  gap, or other qualified source defect to make an outcome look complete.

## Non-goals and implementation boundaries

- No new RAES schema, SDL vocabulary, evaluator protocol, conformance profile,
  fixture corpus, exception hierarchy, store, audit service, or policy gate.
- No participant access to evaluator-only facts and no portable native reward
  structure, hidden state, observation, action id, object representation, raw
  log, environment/argv dump, token, path, or traceback.
- No claim of deterministic replay, exact state/observation equivalence,
  outcome/evaluation equivalence, scenario correctness, semantic equivalence,
  scientific validity, or backend conformance from this projection.
- No reproduction of the upstream 100-episode harness, PPO training/loading,
  leaderboard, study analysis, or replication-claim adjudication unless a
  separately admitted RAES experiment/study requires it.
- No new simulator dependency delivery, patched artifact publication, populated
  `cyborg` extra, network service, or durable adapter state.
