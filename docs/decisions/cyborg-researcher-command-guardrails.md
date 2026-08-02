# CybORG researcher run-and-evidence command guardrails

GitHub issue #20 is the authority for this deliverable. This note fixes the
repository-wide boundaries for one installed researcher command. It defines no
scenario, experiment, environment-pack, participant, evidence, or backend
semantics and is not an implementation plan.

## Readiness facts that must remain visible

Three current facts constrain what the command can honestly claim:

- `raes==2.0.0` publishes the SDL, experiment authoring/task/run/study,
  apparatus, participant implementation, evidence, derived-measure,
  associated-artifact, diagnostic, runtime, and conformance contracts needed
  for orchestration. It does not install an environment-pack parser or the
  `raes-pack-validate` command referenced by the source-ledger guidance. Pack
  validation must call the published pack owner when that dependency is
  available; this repository must not create a substitute pack schema, digest
  convention, provenance model, or validator.
- The `cyborg` extra installs the compatible published environment-pack
  validator but no native simulator. `SourceInstalledCyborgDriver` supports
  the documented, separately installed, pinned source route, while the
  installed-wheel conformance suite uses an injected hermetic driver and
  reports `native_conformance=false`. A clean install can produce honest
  hermetic conformance evidence now, but it cannot be described as a native
  CybORG episode. If issue #20 requires the clean install itself to execute a
  native episode, acceptance is blocked until a governed installable CybORG
  artifact exists; no runtime clone, editable checkout, unpinned URL, hidden
  download, or injected-driver relabeling may bridge that gap.
- The adapter accepts already validated external blue actions. It does not ship
  a production blue participant implementation, manifest, configuration, or
  policy runner. The deterministic participant fixtures and the conformance
  probe's fixed Sleep request are test evidence, not a researcher-selectable
  blue implementation. An unattended example must bind a real selected
  `ParticipantImplementationManifestModel` and
  `ParticipantImplementationSelectionModel` to an executable participant
  implementation outside the CybORG driver. Do not turn a native blue agent or
  a hard-coded action into backend configuration.

These are claim boundaries, not reasons to weaken the issue. The implementation
and its examples must say which evidence basis they exercise and must not mark
the issue accepted while the required basis is unavailable.

## One installed shell, distinct semantic owners

The distribution-level console script should use the distribution identity
`raes-adapters`; it must not shadow or monkey-patch the upstream `raes` command.
Inspection, validation, and execution may share that shell and common bounded
error handling, but they retain different owners:

| Requested operation or mode | Semantic owner and required disposition |
| --- | --- |
| Inspect | Read installed distribution metadata, the live backend manifest through `BackendRegistry` / `register_cyborg_backend()`, the published profile selected by `profile_for_manifest()`, and the immutable CybORG qualification/source selection. Report actual verified availability separately from declared support. Do not keep a CLI-owned backend/profile catalog. |
| Validate | Use the published environment-pack validator for pack structure/provenance/digests, RAES parsers and closed models for SDL and experiment artifacts, cross-artifact validators for bindings/apparatus/run relationships, and `RuntimeManager.plan()` for target representability. Validation performs no native construction or participant action. |
| Smoke | Execute one explicitly selected, already admitted run/condition with its exact red variant, blue implementation, episode control, stochastic-control policy, and seed. “Smoke” is bounded operational cardinality, not a new profile, task, scenario, or weaker semantic interpretation. |
| Conformance | Delegate to `run_cyborg_conformance_suite()` and preserve its canonical report, adapter diagnostics, weaknesses, execution basis, and non-claims. It is not an `ExperimentRunModel`, a native episode, or a study member merely because it shares a command. |
| Study | Execute the allocation declared by the admitted experiment authoring/study artifacts, produce one validated `ExperimentRunModel` per run, and validate the final `ExperimentStudyModel` against its tasks and eligible runs. The mode may not synthesize an allocation, silently truncate conditions, or turn a batch summary into a scientific claim. |

Mode selection is therefore dispatch to existing owners, not a value that
changes scenario meaning. Red variant, blue implementation, trial length, and
seed policy must be explicit selections of pack-declared RAES values. CLI flags
may name those selections and require exact agreement; they must not inject
undeclared values into a target, rewrite a pack, or hide defaults. Source-native
terminal state, the declared logical-step limit, batch cardinality, and cleanup
remain separate facts.

## Canonical incumbents to compose

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Installed identity | `raes_adapters.__version__`, `importlib.metadata`, `load_qualification()`, `CAGE2_SOURCE_26CE1C1`, the source-ledger loaders/validators, and the source-tree checks already used by `SourceInstalledCyborgDriver`. Extract or expose one backend-local verification helper if inspection needs it; do not copy the digest algorithm or execute CybORG before verification. |
| Backend and supported profiles | `BackendRegistry`, `register_cyborg_backend()`, `create_cyborg_manifest()`, `backend_manifest_v2_model()`, `backend_manifest_payload()`, `profile_for_manifest()`, and `required_contracts()`. The manifest and published profile corpus are authoritative; no CLI profile table or golden payload is permitted. |
| Scenario and plan | The published environment-pack validator when a pack is supplied; otherwise `parse_sdl_file()` / the RAES SDL parser, closed SDL models, `RuntimeManager.plan()`, `ArtifactAvailabilityContext`, the compiled model, manifest admission, and realization-envelope checks. The command must not parse native Scenario2 as portable scenario truth. |
| Experiment controls | `parse_experiment_spec()`, `ExperimentSpecModel`, `ExperimentTaskModel`, `ExperimentEpisodeControlModel`, `ExperimentRedVariantSelectionModel`, `ExperimentRunAllocationPlanModel`, `ExperimentStochasticControlModel`, and the task/spec cross-references. Preserve the distinction between authoring input, task, run, and study. |
| Participant binding | `ParticipantImplementationManifestModel`, `ParticipantImplementationSelectionModel`, `validate_experiment_binding_targets()`, `realize_participant_configuration()`, `validate_participant_configuration_selection()`, compiled participant behaviors/decision surfaces, and public `RuntimeControlPlane` participant admission. Do not use `sample_participant_action_admission_request()` or deterministic fixture manifests in production. |
| Runtime execution | `create_cyborg_target()`, its closed `_normalized_config()` / `_validate_selection()` gate, `RuntimeManager`, `RuntimeControlPlane`, `ControlPlaneStore`, public operation receipts/status, participant episode/action methods, and the existing CybORG Provisioner/Orchestrator/ParticipantRuntime/Evaluator/TimeRuntime components. Do not call private backend-call helpers or bypass manager/control-plane result validation. |
| Evidence and measures | `CyborgEvaluator.evidence_records()` and `.derived_measures()`, `ExperimentCaptureSpecModel`, `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, `ExperimentRunTraceabilityModel`, and the task evidence requirements. Native reward, projected evidence, derived measure, result summary, participant outcome, conformance, and equivalence are never synonyms. |
| Archival provenance | `ExperimentApparatusContextModel`, `validate_experiment_apparatus_context_against_manifests()`, `ParticipantImplementationProvenanceModel`, `RealizedBindingProvenanceModel`, `ExperimentRunModel`, `validate_experiment_run_against_task()`, `validate_experiment_run_time_model()`, `ExperimentStudyModel`, and `validate_experiment_study_against_tasks_and_runs()`. Exact adapter/RAES/backend/source/pack/scenario/config/participant identities must resolve through these carriers rather than a free-form provenance dictionary. |
| Artifact attachment and inventory | `ExperimentArtifactRefModel`, `AssociatedArtifactManifestModel`, `associated_artifact_set_digest()`, and `validate_associated_artifact_manifest()` for exact non-semantic attachments to run/study parents. Conformance retains its existing operational index. A directory inventory may point to canonical owner files, but it must not add semantic fields, another schema family, or an aggregate `passed` claim. Use portable URNs/references and relative names, never host-absolute artifact URIs. |
| Diagnostics and projection | RAES `Diagnostic`, `diagnostic_model()`, `diagnostic_payload()`, closed model `model_dump(mode="json")`, `backend_conformance_report_payload()`, `redact_native_value()`, and `bounded_context_label()`. No local diagnostic DTO, portable exception hierarchy, `repr`, `str(exception)`, `asdict`, or raw Pydantic error rendering. |
| Persistence and cleanup | `ControlPlaneStore` is the runtime-state seam; `RuntimeManager.destroy()` and existing component cleanup own teardown. JSON artifacts use `raes_operations.run_artifacts.atomic_write_json_artifact()`; canonical conformance reports use `write_backend_conformance_report()`. Do not add an adapter database, evidence repository, replay cache, or second receipt store. |
| Packaging, examples, and workflow | `[project.scripts]` in the single `pyproject.toml`, package resources via `importlib.resources`, the single `uv.lock`, `_verification_envs()`, `_tests()`, `_distributions()`, `probe_installed_identity.py`, `.github/workflows/ci.yml`, its `PR Gate`, and canonical `nox -s verify`. Installed examples must be real published RAES/pack artifacts and must be exercised from the built wheel in an isolated working directory. |

The existing CyberBattleSim evidence producer is useful only as a repository
precedent for model-first artifact assembly and validation. Its private
`raes.libvirt.scenario-evidence-run/v1` artifact, backend semantics, and
validator are not reusable authority for CybORG.

## Validation and security path

The command must fail before native construction unless every applicable layer
below passes:

| Cross-cutting layer | Required treatment |
| --- | --- |
| Authentication and authorization | This is a local command with no route, remote caller, daemon, or new authentication surface. The local operator selects a run, but participant authority still comes from the compiled participant behavior, implementation selection, exposure policy, target/generation join, and public control-plane admission. A future service must use `create_control_plane_app()` with `ControlPlaneSecurityConfig.strict_defaults`; it must not expose an adapter-specific endpoint. |
| Secret handling and env bindings | The example requires no secret. Do not add token/credential options, read ambient configuration, resolve arbitrary environment bindings, or accept secret values in argv. Pack bindings pass the published binding-target/value-kind/sensitivity checks. A required secret reference is rejected unless a separately published resolver is in scope; its value never enters the command, artifacts, logs, filenames, argv, environment output, or diagnostics. |
| CLI/config shape | The parser is closed: unknown options, modes, controls, and backend names fail. Operational inputs are the mode, safe selection ids, pack/scenario input, and output root. Backend pins still pass `_normalized_config()` / `_validate_selection()`; CLI values cannot select an import path, source directory, profile root, corpus root, driver class, native scenario, or arbitrary module. |
| Pack and file parser | The pack owner validates pack provenance, duplicate members, pin/digest joins, file confinement, and its own closed shapes. The RAES SDL parser rejects duplicate keys and malformed SDL; RAES experiment models reject unknown fields and invalid semantics. `parse_experiment_spec()` alone uses `yaml.safe_load` and is not a duplicate-key gate, so run admission must not bypass the pack owner's stricter parser. `validate_associated_artifact_manifest()` receives explicitly staged bounded readers and performs no URI fetch, traversal, archive extraction, or ambient lookup. Do not use permissive YAML/JSON loading as admission. |
| Scenario/experiment cross-artifact gates | Require pack/scenario snapshot digest agreement, task/spec/scenario refs, explicit binding descriptor coverage, exact apparatus/manifest identity and digest joins, participant configuration joins, seed/stochastic-control declarations, run allocation, and artifact requirements before planning. A matching filename or id without the matching digest is not admission. |
| Runtime gates | Run through `RuntimeManager.plan()` and public manager/control-plane operations so target/manifest/snapshot provenance, capability/resource/dependency admission, component signatures, `ApplyResult`, snapshot transition, changed addresses, workflow, time, participant, observation, evaluation, proposition, receipt/status, and cleanup checks remain active. Backend checks add only selected-CybORG representability and private projection. |
| Native source boundary | Before import, reuse the complete selected-source tree and selected-file verification, private source snapshot, module-origin/version checks, fixed red-agent binding, and private scenario workspace in `SourceInstalledCyborgDriver`. Native objects, state, observations, masks, action ids, rewards, hidden truth, credentials, random state, and paths never become portable inputs or outputs. |
| OS/process and terminal exposure | Use no shell interpolation, runtime download, plugin discovery, inherited environment dump, or user-home discovery. Do not pass secrets or arbitrary config in argv/environment. Native imports and calls may write directly to stdout/stderr, so the outer command must contain or discard native output and emit only its own allowlisted summary; captured native stdout/stderr must never be retained as diagnostics or evidence. An unexpected exception is caught at the outer boundary and never prints a traceback. |
| Error envelope | Convert expected parser, pin, digest, binding, admission, execution, cleanup, and sealing failures to validated RAES diagnostics with stable codes, JSON Pointer addresses, and bounded input-free messages. Never echo rejected values, input paths, exception types/messages/causes, Pydantic `input_value`, raw logs, or tracebacks. Terminal errors contain a stable code, disposition, and at most a relative diagnostic artifact name under the chosen output. |
| Logging and observability | Portable observability is the validated run/study artifacts, evidence records, derived measures, diagnostics, receipts/status, limitations, and inventory. Standard logging, if used, is allowlisted to safe operation names, published ids/pointers, counts, and dispositions. Never log plans, pack contents, actions/arguments, observations, rewards, native state, file-system paths, argv/environment, or random state. |
| Persistence and output confinement | Resolve and validate the chosen output parent, then reserve each run root race-safely and exclusively before execution. Every child name is fixed or uses the shared safe run-id rule. Existing directories, files, and symlinks are rejected; no resume, merge, append, `--force`, or overwrite mode exists. A failed run retains its unique directory and bounded diagnostics and is never reused. Artifacts are validated before atomic publication; the inventory is written last as the seal. |

The existing atomic writers use `os.replace` and therefore prevent partial
files but do allow replacement. Exclusive run-root reservation is an additional
mandatory guard; calling an atomic writer alone does not satisfy the no-overwrite
acceptance criterion. The current conformance `index.json` direct write likewise
must run only inside the newly reserved root when reached through this command.

## Output and exit contract

Each experiment run retains its canonical RAES run provenance, capture/evidence
records, derived measures, result summaries, validated diagnostics, and exact
artifact references. A batch retains those per-run owners plus the validated
study record. Conformance retains the canonical report and existing disclosures
without being wrapped in a fake experiment run. The final inventory records
relative artifact names, media types, byte sizes, and cryptographic digests and
binds them to their run or study parent where the published associated-artifact
contract applies.

Terminal output is deliberately smaller: mode, success/failure disposition,
run/study id, counts, declared evidence basis, and relative inventory location.
It contains no native values, raw logs, full traceback, environment data, or
path outside the selected output.

Use one documented process-exit mapping rather than exception-type-dependent
codes:

| Exit | Meaning |
| --- | --- |
| `0` | Requested inspection, validation, conformance, run, or study completed and all required artifacts were validated and sealed. |
| `2` | Closed command-line usage error. |
| `3` | Pack/scenario/experiment/pin/digest/profile/participant/control validation or admission failed before execution. |
| `4` | Output confinement, exclusivity, or reuse refusal. |
| `5` | Runtime execution or verified cleanup failed. |
| `6` | Portable artifact validation, persistence, inventory, or sealing failed; execution is not reported successful. |
| `70` | Unexpected internal failure, reported without exception details or traceback. |

When more than one failure occurs, cleanup is still attempted and its failure is
retained; a failed cleanup or failed seal can never be downgraded to success.

## Extension seam

The external selection seam is a closed tuple of existing identities: backend
name resolved by `BackendRegistry`, immutable source/qualification selection,
pack and scenario-snapshot digest, task/spec condition, participant
implementation/configuration selection, explicit episode/red-variant controls,
ordered stochastic-control/seed allocation, mode, and unique run id. The tuple
is operational input whose fields resolve to published models; it is not a new
portable DTO or schema.

A future CybORG source closure extends `EvidenceSelection`; a future pack or
blue implementation adds new published artifacts and selections; a future
simulator registers through `BackendRegistry`. None should require editing an
existing scenario/task/run artifact, adding a simulator registry to
`raes_adapters.base`, or branching on native types in the command. Mode dispatch
and backend-local execution stay separate so a new backend does not inherit
CybORG red variants, actions, seeds, or evidence claims.

## Gotchas and anti-patterns

- Do not treat the current hermetic conformance driver as a simulator, native
  readiness, a participant implementation, or experiment evidence.
- Do not import test/conformance probe builders into the command or copy their
  in-code scenario, plan, fixed action, sample participant selection, or
  evaluation plan as production artifacts.
- Do not create a local environment-pack model, scenario digest convention,
  experiment DTO, participant manifest, evidence schema, inventory semantics,
  profile, exception hierarchy, or store because a published owner is awkward
  or absent.
- Do not let `--mode`, a CLI default, or target config redefine red variant,
  blue implementation, trial length, seed allocation, termination, evaluator,
  or metric meaning. Missing explicit selection is a validation failure.
- Do not conflate adapter version, backend manifest version, qualification
  profile, CybORG version, source commit/tree, pack version/digest, scenario
  snapshot digest, participant implementation version/configuration digest,
  and run id.
- Do not conflate authored scenario, native Scenario2 evidence, generated
  CybORG scenario, runtime snapshot, participant observation, evaluator-private
  facts, evidence record, derived measure, result summary, conformance report,
  and study claim.
- Do not infer realized effects or objective satisfaction from native success,
  reward, terminal state, or the known Remove misreport. Preserve source-ledger
  losses and qualification limitations in provenance and non-claims.
- Do not derive seeds or run ids from wall time, process id, directory contents,
  global random state, environment variables, or implicit defaults. Random run
  ids may ensure uniqueness but do not define the experiment seed policy.
- Do not write first and validate later, serialize arbitrary snapshots/native
  objects, use absolute file URIs, hash a native dump and call it portable, or
  print a path merely because it was supplied by the user.
- Do not offer `--force`, resume, append, partial batch continuation into an old
  directory, or automatic cleanup/deletion of a failed artifact directory.
- Do not add a second CLI dependency solely for formatting, a second workflow,
  another lockfile, an adapter endpoint, or a background scheduler.

## Non-goals and implementation boundaries

- No training framework, leaderboard, notebook-only API, web UI, remote
  service, daemon, production scheduler, or authentication system.
- No new RAES or environment-pack schema, SDL extension, vocabulary, profile,
  fixture corpus, diagnostic envelope, evidence type, derived-measure meaning,
  participant protocol, backend protocol, or scientific claim.
- No runtime source clone/download, unpublished patched artifact, editable
  install, arbitrary participant/plugin import, or environment-selected source.
- No native state, hidden truth, raw native log, full traceback, reward vector,
  action id/class, object representation, credential, argv/environment dump, or
  host path in portable artifacts or terminal output.
- No generic cross-backend runner in `raes_adapters.base`. Shared code is limited
  to existing plumbing; CybORG execution and evidence selection stay in
  `raes_adapters.cyborg`, while the installed shell only coordinates owners.
- No deterministic replay, state/observation equivalence, outcome equivalence,
  or scientific validity claim follows from a controlled seed, a green run, a
  conformance report, or a reproducible command line.

Acceptance must include subprocess-level tests over the installed console
script for clean working-directory execution, every exit class, output races
and reuse, hostile native stdout/stderr and exceptions, environment/path
sentinels, exact identity/digest retention, participant-binding rejection,
cleanup failure, persisted artifact validation, and short-run/batch examples.
Extend the existing `tests` and `_distributions()` paths and run the canonical
verification graph with the requirement-free governance flag; do not create a
parallel acceptance workflow.
