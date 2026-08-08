# NASim researcher run-and-evidence command guardrails

GitHub issue #36 is the authority for this deliverable. This note fixes the
repository-wide boundaries for the NASim `nasim-tiny` surface of the one
installed researcher command. It defines no scenario, experiment,
environment-pack, participant, evidence, or backend semantics and is not an
implementation plan. Mode dispatch is shared across backends; the NASim adapter
owns every NASim-local semantic and inherits no other backend's participant
surface, red variants, seeds, or evidence claims.

## Readiness facts that must remain visible

Three current facts constrain what the NASim surface can honestly claim:

- `raes==2.0.0` publishes the SDL, experiment authoring/task/run/study,
  apparatus, participant implementation, evidence, derived-measure,
  associated-artifact, diagnostic, runtime, and conformance contracts needed for
  orchestration. It does not install an environment-pack parser. Pack validation
  must call the published `raes_env_packs` owner; this repository must not create
  a substitute pack schema, digest convention, provenance model, or validator.
- The `nasim` extra pins and installs the qualified native NASim source
  (`nasim==0.12.0` with its `gymnasium`/`numpy` pins) alongside the published
  environment-pack validator. Unlike CybORG, the qualified source is present
  after a clean install, so the command can construct and drive a native NASim
  attacker episode and run its conformance probe directly. Before any import the
  command must reuse `verify_selected_nasim_source()` to check the installed
  source tree, files, and version against the immutable qualification; no runtime
  clone, editable checkout, unpinned URL, hidden download, or relabeled driver
  may bridge a verification gap. NASim conformance is an **installed-source
  probe**, not a hermetic injected driver: `nasim_conformance_suite()` delegates
  to `run_nasim_conformance()` over the installed source and reports its own
  `native_conformance` flag and `installed-source-probe` execution basis. A
  probe over the installed source is not a native attacker episode.
- The selected `nasim-tiny` scenario has a single autonomous **red** attacker,
  **no** defender, and no second participant. The packaged `nasim-red-bruteforce`
  policy is a real published `ParticipantImplementationManifestModel` /
  `ParticipantImplementationSelectionModel` bound at `participant.behavior.red`
  to the executable `participant.action-contract.service-exploit` action; an
  unattended example must bind it, not a fixture. The conformance probe's fixed
  request and any deterministic participant fixtures are test evidence, not a
  researcher-selectable red implementation. There is no red variant: the attacker
  is fixed by the admitted implementation. Do not turn the single autonomous
  attacker into a red-variant selection, invent a defender, or turn the action
  contract into backend configuration.

Determinism is a standing non-claim. The `nasim-tiny` static benchmark draws
action success from the process-global legacy NumPy stream, which neither
`make_benchmark` nor the gym reset seed binds (ADR-069). A bound seed satisfies
the declared control cardinality but is never a deterministic-replay claim; the
loss is retained in the run apparatus context's known limitations and the
conformance non-claims and may never be erased.

These are claim boundaries, not reasons to weaken the issue. The implementation
and its examples must say which evidence basis they exercise and must not mark
the issue accepted while the required basis is unavailable.

## One installed shell, distinct semantic owners

The distribution-level console script uses the distribution identity
`raes-adapters` and must not shadow or monkey-patch the upstream `raes` command.
The NASim surface is selected by `--backend nasim-tiny`. Inspection, validation,
and execution share the shell and common bounded error handling but retain
different owners:

| Requested operation or mode | Semantic owner and required disposition |
| --- | --- |
| Inspect | Read installed distribution metadata, the live NASim manifest through `create_nasim_manifest()`, the profiles selected by `load_backend_profile()`, and the immutable NASim qualification/source selection via `load_qualification()` and `NASIM_TINY`. Report actual `native_available` separately from declared support through `verify_selected_nasim_source()`. Do not keep a CLI-owned backend/profile catalog. |
| Validate | Use `raes_env_packs` for pack structure/provenance/digests, RAES parsers and closed models for SDL and experiment artifacts, cross-artifact validators for bindings/apparatus/run relationships, and `RuntimeManager.plan()` for target representability. Validation performs no native construction or participant action. |
| Smoke | Execute one explicitly selected, already admitted run with its exact red implementation, episode control, and single admitted seed. "Smoke" is bounded operational cardinality, not a new profile, task, scenario, red variant, or weaker semantic interpretation. |
| Conformance | Delegate to `nasim_conformance_suite()` / `run_nasim_conformance()` and preserve its canonical report, source-protocol diagnostics, declared weaknesses, execution basis (`installed-source-probe`), and explicit non-claims. It is not an `ExperimentRunModel`, a native attacker episode, or a study member merely because it shares a command. |
| Study | Execute the allocation declared by the admitted experiment authoring/study artifacts, produce one validated `ExperimentRunModel` per run, and validate the final `ExperimentStudyModel` through `validate_experiment_study_against_tasks_and_runs()`. The mode may not synthesize an allocation, silently truncate conditions, or turn a batch summary into a scientific claim. |

Mode selection is dispatch to existing owners, not a value that changes scenario
meaning. The single red implementation, trial length, and seed policy must be
explicit selections of pack-declared RAES values. CLI `--participant-*` flags may
name those selections and require exact agreement; they must not inject undeclared
values into a target, rewrite a pack, or hide defaults. The NASim surface admits
exactly the `--participant-*` arguments and requires the CybORG `--red-variant` /
`--blue-*` arguments absent, so neither backend inherits the other's participant
surface.

## Canonical incumbents to compose

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Installed identity | `raes_adapters.__version__`, `importlib.metadata`, `load_qualification()` (NASim), `NASIM_TINY`, `read_source_revision()`, and the installed source-tree/file/version checks in `verify_selected_nasim_source()` / `NasimDriverProtocol`. Do not copy the digest algorithm or import NASim before verification. |
| Backend and supported profiles | `BackendRegistry`, `create_nasim_manifest()`, `backend_manifest_payload()`, `backend_profiles_root()`, and `load_backend_profile()`. The manifest and published profile corpus are authoritative; no CLI profile table or golden payload is permitted. |
| Scenario and plan | `raes_env_packs.validate_pack()` / `verify_pack_content_digest()` when a pack is supplied; `raes.parse_sdl_file()`, `instantiate_scenario()`, `canonical_instantiated_sdl_digest()`, closed SDL models, `RuntimeManager.plan()`, `nasim_orchestration_plan()`, and `nasim_evaluation_plan()`. The command must not parse a native NASim scenario as portable scenario truth. |
| Experiment controls | `parse`/`model_validate` into `ExperimentSpecModel`, `ExperimentTaskModel`, the `run_plan.episode_control`, and the declared `stochastic_controls`, plus the task/spec cross-references. NASim declares no red-variant model; preserve the distinction between authoring input, task, run, and study. |
| Participant binding | `ParticipantImplementationManifestModel`, `ParticipantImplementationSelectionModel`, `validate_participant_configuration_selection()`, `realize_participant_configuration()`, `canonical_contract_digest()`, the fixed `participant.behavior.red` address, and public runtime participant admission. Do not use `ParticipantActionAdmissionRequest` sample builders or fixture manifests in production, and do not admit a second or defending participant. |
| Runtime execution | `create_nasim_target()`, `RuntimeManager`, the target's `provisioner`/`orchestrator`/`participant_runtime`/`evaluator` components, `RuntimeSnapshot`, `OrchestrationPlan`, public operation receipts/status, and participant episode/action methods. NASim ships no time-runtime component and resets only through the participant lifecycle, so the objective is evaluated at episode end through `nasim_evaluation_plan()`; do not call private backend helpers or bypass manager/control-plane result validation. |
| Evidence and measures | `evaluator.evidence_records()` and `.derived_measures()`, `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, and the task evidence requirements. The `cumulative_attacker_reward` result summary, projected evidence, derived measure, conformance, and equivalence are never synonyms. |
| Archival provenance | The apparatus context projection, `ParticipantImplementationProvenanceModel`, `ExperimentRunModel`, `validate_experiment_run_against_task()`, `ExperimentStudyModel`, and `validate_experiment_study_against_tasks_and_runs()`. Exact adapter/RAES/backend/source/pack/scenario/config/participant identities must resolve through these carriers rather than a free-form provenance dictionary. |
| Artifact attachment and inventory | `ExperimentArtifactRefModel` for exact non-semantic attachments to run/study parents; the directory inventory points to canonical owner files with relative names and adds no semantic field, schema family, or aggregate `passed` claim. Use portable references and relative names, never host-absolute artifact URIs. |
| Diagnostics and projection | RAES `DiagnosticModel`, `diagnostic_model()`, `diagnostic_payload()`, closed model `model_dump(mode="json")`, `nasim_backend_conformance_payload()`, and `write_backend_conformance_report()`. No local diagnostic DTO, portable exception hierarchy, `repr`, `str(exception)`, or raw Pydantic error rendering. |
| Persistence and cleanup | `RuntimeManager.destroy()` and existing component cleanup own teardown. JSON artifacts use `atomic_write_json_artifact()`; canonical conformance reports use `write_backend_conformance_report()`. Do not add an adapter database, evidence repository, replay cache, or second receipt store. |
| Packaging, examples, and workflow | The `nasim` entry under `[project.optional-dependencies]` in the single `pyproject.toml`, package resources via `importlib.resources`, the single `uv.lock`, and canonical `nox -s verify`. Installed examples must be the real published RAES/pack artifacts under `raes_adapters.nasim/examples/nasim-tiny` and must be exercised from the built wheel in an isolated working directory. |

The CybORG and CyberBattleSim evidence producers are useful only as repository
precedents for model-first artifact assembly and validation. Their backend
semantics, red variants, drivers, and validators are not reusable authority for
NASim.

## Validation and security path

The command must fail before native construction unless every applicable layer
below passes:

| Cross-cutting layer | Required treatment |
| --- | --- |
| Authentication and authorization | This is a local command with no route, remote caller, daemon, or new authentication surface. The local operator selects a run, but participant authority comes from the compiled red behavior, implementation selection, exposure policy, target/generation join, and public runtime admission. |
| Secret handling and env bindings | The example requires no secret. Do not add token/credential options, read ambient configuration, resolve arbitrary environment bindings, or accept secret values in argv. Pack bindings pass the published binding-target/value-kind/sensitivity checks; a required secret reference is rejected unless a separately published resolver is in scope, and its value never enters the command, artifacts, logs, filenames, argv, environment, or diagnostics. |
| CLI/config shape | The parser is closed: unknown options, modes, controls, and backend names fail. Operational inputs are the mode, safe selection ids, pack/scenario input, and output root. The NASim surface admits only the `--participant-*` arguments and requires `--red-variant`/`--blue-*` absent. CLI values cannot select an import path, source directory, profile root, corpus root, driver class, native scenario, or arbitrary module. |
| Pack and file parser | `raes_env_packs` validates pack provenance, duplicate members, pin/digest joins, file confinement, and its own closed shapes. The RAES SDL parser rejects duplicate keys and malformed SDL; RAES experiment models reject unknown fields; strict JSON loading rejects duplicate keys. Pack children resolve without traversal. Do not use permissive YAML/JSON loading as admission. |
| Scenario/experiment cross-artifact gates | Require pack/scenario snapshot digest agreement, task/spec/scenario refs, explicit artifact-binding coverage against the spec's `artifact_refs` (exact URI, role, algorithm, checksum, and byte size), participant configuration joins, seed declarations, run allocation, and episode control before planning. A matching filename or id without the matching digest is not admission. |
| Runtime gates | Run through `RuntimeManager.plan()` and public manager/component operations so target/manifest/snapshot provenance, capability/resource/dependency admission, `ApplyResult`, snapshot transition, workflow, participant, observation, evaluation, receipt/status, and cleanup checks remain active. Backend checks add only selected-NASim representability and private projection. |
| Native source boundary | Before import, reuse the complete `verify_selected_nasim_source()` source-tree, file, and version verification. Native objects, state, observations, masks, action ids, rewards, hidden truth, random state, and paths never become portable inputs or outputs. |
| OS/process and terminal exposure | Use no shell interpolation, runtime download, plugin discovery, inherited environment dump, or user-home discovery. Native imports and calls may write to stdout/stderr, so the command redirects and discards native output and emits only its own allowlisted summary; captured native stdout/stderr is never retained as diagnostics or evidence. An unexpected exception is caught at the outer boundary and never prints a traceback. |
| Error envelope | Convert expected parser, pin, digest, binding, admission, execution, cleanup, and sealing failures to validated RAES diagnostics with stable codes and bounded input-free messages. Never echo rejected values, input paths, exception types/messages/causes, Pydantic `input_value`, raw logs, or tracebacks. |
| Logging and observability | Portable observability is the validated run/study artifacts, evidence records, derived measures, diagnostics, receipts/status, limitations, and inventory. Never log plans, pack contents, actions/arguments, observations, rewards, native state, file-system paths, argv/environment, or random state. |
| Persistence and output confinement | Resolve and validate the chosen output parent, then reserve each run root race-safely and exclusively before execution. Existing directories, files, and symlinks are rejected; no resume, merge, append, `--force`, or overwrite mode exists. A failed run retains its unique directory and bounded diagnostics and is never reused. Artifacts are validated before atomic publication; the inventory is written last as the seal. |

## Output and exit contract

Each experiment run retains its canonical RAES run provenance, capture/evidence
records, derived measures, result summaries, validated diagnostics, and exact
artifact references. A batch retains those per-run owners plus the validated
study record. Conformance retains the canonical report and existing disclosures
without being wrapped in a fake experiment run. The final inventory records
relative artifact names, media types, byte sizes, and cryptographic digests.

Terminal output is deliberately smaller: mode, success/failure disposition,
run/study id, counts, declared evidence basis, and relative inventory location.
It contains no native values, raw logs, full traceback, environment data, or path
outside the selected output.

The command uses one documented process-exit mapping rather than
exception-type-dependent codes:

| Exit | Meaning |
| --- | --- |
| `0` | Requested inspection, validation, conformance, run, or study completed and all required artifacts were validated and sealed. |
| `2` | Closed command-line usage error. |
| `3` | Pack/scenario/experiment/pin/digest/profile/participant/control validation or admission failed before execution. |
| `4` | Output confinement, exclusivity, or reuse refusal. |
| `5` | Runtime execution or verified cleanup failed, including an unavailable or unverified qualified NASim source. |
| `6` | Portable artifact validation, persistence, inventory, or sealing failed; execution is not reported successful. |
| `70` | Unexpected internal failure, reported without exception details or traceback. |

When more than one failure occurs, cleanup is still attempted and its failure is
retained; a failed cleanup or failed seal can never be downgraded to success.

## Extension seam

The external selection seam is a closed tuple of existing identities: backend
name resolved through the adapter registry, immutable source/qualification
selection, pack and scenario-snapshot digest, task/spec condition, red
participant implementation/configuration selection, explicit episode control,
ordered seed allocation, mode, and unique run id. The tuple is operational input
whose fields resolve to published models; it is not a new portable DTO or schema.

A future NASim scenario, red implementation, or benchmark adds new published
artifacts and selections; a future simulator registers its own adapter. None
should require editing an existing scenario/task/run artifact, adding a simulator
registry to `raes_adapters.base`, or branching on native types in the command.
Mode dispatch and backend-local execution stay separate so NASim never inherits
another backend's red variants, defenders, actions, seeds, or evidence claims,
and no backend inherits NASim's single-attacker surface or ADR-069 determinism
loss.

## Gotchas and anti-patterns

- Do not treat the installed-source conformance probe as a native attacker
  episode, native readiness, a participant implementation, or experiment
  evidence.
- Do not import test/conformance probe builders into the command or copy their
  in-code scenario, plan, fixed action, sample participant selection, or
  evaluation plan as production artifacts.
- Do not create a local environment-pack model, scenario digest convention,
  experiment DTO, participant manifest, evidence schema, inventory semantics,
  profile, exception hierarchy, or store because a published owner is awkward or
  absent.
- Do not let `--mode`, a CLI default, or target config redefine the red
  implementation, trial length, seed allocation, termination, evaluator, or
  metric meaning. Missing explicit selection is a validation failure. Do not
  invent a red variant or a defender for a single-attacker scenario.
- Do not conflate adapter version, backend manifest version, NASim version,
  source commit/tree, pack version/digest, scenario snapshot digest, participant
  implementation version/configuration digest, and run id.
- Do not infer a deterministic replay, realized effect, or objective
  satisfaction from a bound seed, native success, reward, or terminal state. The
  ADR-069 global-NumPy determinism loss must survive in provenance and
  non-claims.
- Do not derive seeds or run ids from wall time, process id, directory contents,
  global random state, environment variables, or implicit defaults.
- Do not write first and validate later, serialize arbitrary snapshots/native
  objects, use absolute file URIs, hash a native dump and call it portable, or
  print a path merely because it was supplied by the user.
- Do not offer `--force`, resume, append, partial batch continuation into an old
  directory, or automatic cleanup/deletion of a failed artifact directory.
- Do not add a second CLI dependency solely for formatting, a second workflow,
  another lockfile, an adapter endpoint, or a background scheduler.

## Non-goals and implementation boundaries

- No training framework, leaderboard, notebook-only API, web UI, remote service,
  daemon, production scheduler, or authentication system.
- No new RAES or environment-pack schema, SDL extension, vocabulary, profile,
  fixture corpus, diagnostic envelope, evidence type, derived-measure meaning,
  participant protocol, backend protocol, or scientific claim.
- No runtime source clone/download, unpublished patched artifact, editable
  install, arbitrary participant/plugin import, or environment-selected source.
- No native state, hidden truth, raw native log, full traceback, reward vector,
  action id/class, object representation, credential, argv/environment dump, or
  host path in portable artifacts or terminal output.
- No generic cross-backend runner in `raes_adapters.base`. Shared code is limited
  to the mode-dispatch shell and existing plumbing; NASim execution and evidence
  selection stay in `raes_adapters.nasim`, while the installed shell only
  coordinates owners.
- No deterministic replay, state/observation equivalence, outcome equivalence,
  or scientific validity claim follows from a controlled seed, a green run, a
  conformance report, or a reproducible command line.
