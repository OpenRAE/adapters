# CyberBattleSim environment-pack and researcher-command guardrails

GitHub issue #29 is the authority for this deliverable. This note fixes the
repository-wide boundaries for the `cyberbattlesim-chain` environment pack and
its surface in the one installed researcher command. It defines no RAES,
environment-pack, participant, evidence, backend, or release schema and is not
an implementation plan.

## Selected truth and current capability gap

The deliverable is one projection of the already selected public protocol:
`CyberBattleChain-v0`, size 10, the `CredentialCacheExploiter` red participant,
the `ScanAndReimageCompromisedMachines` source-internal defender, the selected
episode controls and stochastic limitations, and the existing evaluation task.
The canonical owners are `qualification.json`, `public-protocol.md`,
`CYBERBATTLE_CHAIN`, the scenario/source ledger, and the published RAES
scenario/task/spec artifacts. Pack content may reference and bind those owners;
it must not restate their native selections as new pack semantics.

One gap must remain explicit until it is actually closed. The live backend
manifest currently declares `supports_autonomous_execution=False`, while the
selected researcher case requires the autonomous `CredentialCacheExploiter`.
The command must not substitute a fixed action, the conformance driver, a first-
available-action script, or a different participant and call the case complete.
The selected upstream participant/evaluator must be integrated through the
existing `CyberBattleSimDriver`, target, participant-runtime, evaluator, and
cleanup boundaries; every source transition must still cross public RAES
admission/result validation. Any changed autonomous-execution claim must be
backed by matching manifest, live-target, hostile-leak, and conformance evidence.
Native policy state, action coordinates, masks, observations, credentials,
reward vectors, and evaluator state remain driver-private. Do not copy or
reimplement the upstream evaluator loop merely to obtain control of it.

The source still has no governed index or release artifact. The
`cyberbattlesim` extra may install the pinned `raes-env-packs` owner, but it must
remain dependency-light with respect to the native simulator. The command never
clones, downloads, patches, or discovers native source; the documented operator
acquisition route installs the exact qualified source and the existing
`CyberBattleSimDriver` source-tree/artifact admission checks it before import or
construction. Native absence or identity mismatch is a bounded readiness
failure, never a fallback to an injected driver under a native label.

## Keep the owners and claims distinct

| Concern | Canonical owner and required boundary |
| --- | --- |
| Pack format, provenance, visibility, content identity, and release views | The pinned `raes-env-packs` template and its `validate_pack()`, `verify_pack_content_digest()`, `raes-pack-validate`, and `raes-pack-release check` gates. Do not copy its schemas, diagnostic type, digest convention, leak scanner, or release builder. |
| Scenario semantics | The published RAES SDL parser/compiler/contracts and the canonical `cyberbattle-chain.sdl.yaml`. The pack carries the canonical bytes under its `sdl/` member; it defines no semantics and causes no scenario content to be added to `RAESystem/env-packs`. |
| Source and mapping evidence | `load_qualification()`, `CYBERBATTLE_CHAIN`, `scenario_ledger.py`, `mapping/source-ledger.jsonl`, `mapping/loss-disclosures.md`, and `public-protocol.md`. Pack provenance references these immutable sources and records pack-local redistribution/exclusion decisions; it does not copy the ledger shape into another authority. |
| Experiment and participant selection | Published `ExperimentSpecModel`, `ExperimentTaskModel`, participant manifest/selection/configuration models, `validate_participant_configuration_selection()`, `realize_participant_configuration()`, `canonical_contract_digest()`, and their cross-artifact validators. The autonomous red participant binds `participant.behavior.red`; the source-internal defender and evaluator are not researcher-selectable participants. |
| Runtime implementation | `create_cyberbattlesim_target()`, `CyberBattleSimDriver`, `RuntimeManager`, the four target components, public operation receipts/status, and verified cleanup. Gym ids, Python symbols, source-native defender/evaluator parameters, driver classes, module paths, and source installation paths stay in backend qualification/implementation, never pack semantics or CLI-injected configuration. |
| Evaluation and evidence | `CyberBattleSimEvaluator`, the existing experiment task, `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, run/study validators, and the model-first helpers in `_experiment_evidence.py` and `_researcher_support.py`. Reward, objective truth, terminal cause, evidence, measure, conformance, readiness, and scientific validity remain distinct. |
| Associated artifacts | When the pack claims non-semantic artifact identity, use RAES `AssociatedArtifactManifestModel`, `associated_artifact_set_digest()`, and `validate_associated_artifact_manifest()` and let pack validation enforce the manifest pointer. Omit the manifest when there is no associated artifact set and state why; never invent a pack-local artifact identity schema. |
| Installed command | The existing `raes-adapters` parser, `_BackendAdapter` dispatch, external pack-path admission, stable exit mapping, bounded `_CommandFailure` projection, and common native-run/artifact pipeline. Add CyberBattleSim-local selections in `raes_adapters.cyberbattlesim`; do not add a second console script or put backend semantics in `cli.py` or `raes_adapters.base`. |
| Persistence and observability | `RuntimeManager.destroy()`, `atomic_write_json_artifact()`, canonical conformance report writers, exclusive output reservation, and the inventory written last as the seal. There is no adapter database, resume store, cache authority, replay repository, or second receipt store. |
| Verification and release | The single `pyproject.toml`/`uv.lock`, existing nox sessions and `_distributions()`, current `PR Gate`, and the existing Release Please build/publish workflow plus `check_project_services.py`. Extend these incumbents rather than adding another lock, workflow, policy validator, or unenforced job. |

The pack's authored task/spec, reference build, automated rehearsal, researcher
walkthrough, command validation, smoke run, seeded batch, and recorded native
readiness result must all resolve to the same scenario snapshot digest, episode
controls, participant implementation/configuration, objective/evaluation task,
and evaluator selection. Prose or scripts may point to the canonical owners but
must not carry a second editable set of defaults. A mismatch is a validation
failure, not a documented variation.

The top-level pack is the publication owner of the SDL used by the researcher
workflow. The installed backend currently retains the same SDL and companion
experiment evidence as package resources for scenario-ledger and conformance
checks. Those are identity-bound mirrors, not independently editable scenarios:
repository tests must compare their parsed models and canonical scenario digest
and fail on drift. Pack-relative references use the pack's `sdl/` location; a
path relocation must not become a semantic fork or a second task/protocol.

## External pack and release boundary

The source pack lives only at `environments/cyberbattlesim-chain/`. It is not a
package resource and must be absent from both wheel and Python sdist members.
The installed command consumes an already acquired pack directory through the
existing external path seam; it must not stage a hidden package copy or execute
pack-provided code. The exact pack name, version, content digest, scenario
snapshot digest, task/spec identity, and participant selection form a backend-
local immutable operational selection, not a new portable DTO or schema.

Clean acquisition uses a versioned repository/GitHub Release artifact produced
from the exact reviewed tag, with a checksum and the pack content digest. Build
the standalone release asset through `raes-pack-release`, keep it outside the
PyPI `dist/` directory, attach it through the existing release workflow, and
retain the current no-clobber retry rule. The repository release tag and pack
version are separate identities and must not be silently equated.
The researcher command does no network acquisition; documentation acquires and
unpacks the immutable artifact first, then `raes-pack-validate`,
`raes-pack-release check`, and the command independently verify it. A branch
archive, floating URL, mutable cache, caller digest without a selected expected
digest, or directory name without byte verification is not admission.

`pack.yaml.status` follows evidence, not feature intent:

- `draft` while no real native reference build has stood up;
- `built` only after the selected qualified source and real adapter command have
  completed the documented build/run path; and
- `golden` only after the full participant-equivalent objective path, matching
  automated rehearsal and manual researcher walkthrough, leak checks, cleanup,
  and durable rehearsal evidence all pass.

Pack validation, conformance, an injected-driver test, or one source import does
not by itself earn `built` or `golden`. The unchecked golden-readiness checklist
stays a template; the actual run is recorded separately with exact pack,
adapter, native source, controls, participant, evaluator, and artifact digests.

## Validation and security path

The command fails before native construction unless every applicable layer
passes:

| Cross-cutting layer | Required treatment |
| --- | --- |
| Authentication and participant authority | This is a local command with no remote route, daemon, or new authentication surface. Operator invocation is not participant authorization: the compiled red behavior, exact manifest/selection/configuration joins, exposure policy, target/generation join, and public participant admission establish what the autonomous participant may do. Any later HTTP surface must reuse RAES strict-default security, verified identities, role/target authorization, request limits, denial audit, and redacted errors. |
| Secrets and environment bindings | The selected case requires no secret. Add no token/credential option, secret resolver, ambient `.env`, user-home discovery, arbitrary environment binding, or secret value in argv. Pack provenance and bindings use the published sensitivity/value-kind gates. Credentials learned inside CyberBattleSim remain native state and never enter terminal output, artifacts, diagnostics, filenames, logs, argv, or environment dumps. |
| CLI/config shape | Keep `argparse` choices and per-backend required/foreign-argument checks closed. Values may select only published pack members and declared controls; they cannot select an import path, driver/evaluator class, source tree, native scenario, profile/corpus root, or arbitrary module. Unsupported controls and participant surfaces fail before output reservation and native construction. |
| Pack and parser gates | Run canonical pack validation and selected content-digest verification, then confined child resolution, strict duplicate-key JSON loading, bounded RAES SDL parsing/instantiation, closed contract-model validation, and associated-artifact validation when declared. Never execute `build/`, `tests/`, hooks, or validators from an untrusted acquired pack as part of command admission. |
| Cross-artifact joins | Require expected pack name/version/digest; canonical scenario digest and path; task/spec/scenario joins; exact artifact URI/role/checksum/size coverage; participant manifest/selection/configuration/digest joins; declared episode control; exact ordered seed allocation; and mode cardinality. Matching names without matching bytes are insufficient. |
| Native source and runtime gates | Verify the complete selected distribution roots, direct-install provenance, versions, source tree/files, symlink policy, and module origins before native import. Run through `RuntimeTarget`/`RuntimeManager` and public target components so capability, plan, snapshot transition, participant/action/history, evaluation, receipt/status, and cleanup validation remain active. A native mutation followed by an invalid projection is failure requiring cleanup. |
| OS/process exposure | Use no shell interpolation, runtime download, plugin discovery, inherited environment dump, or checkout import. Clean/native rehearsal uses an isolated working directory, cleared `PYTHONPATH`, `PYTHONSAFEPATH=1`, explicit argument vectors, bounded time/output, and no network after acquisition. Native stdout/stderr is redirected and discarded, never retained as evidence or error detail. |
| Error envelope | Reuse the command's exit mapping and stable bounded messages, RAES `DiagnosticModel`/`diagnostic_model()`, `ApplyResult`, and canonical report projections. Never emit rejected values or paths, Pydantic input rendering, exception type/text/causes, native stdout/stderr, object representations, or tracebacks. Cleanup or inventory failure cannot be downgraded to a successful run. |
| Logging and portable observability | Portable observability is validated run/study records, evidence, derived measures, bounded diagnostics, operation receipts/status, non-claims, provenance, and the final inventory. Logs and terminal JSON are limited to safe identities, counts, modes, dispositions, and relative artifact names; no plans, pack contents, actions/arguments, observations, rewards, native state, paths, random state, argv, or environment mappings. |
| Persistence and output confinement | Use invocation-relative output, exclusive race-safe creation, reject existing files/directories/symlinks, validate before atomic publication, retain a bounded failure in the unique failed directory, and write the inventory last. No overwrite, `--force`, resume, append, partial-batch continuation, automatic deletion, or reuse of unsafe output exists. |
| Pack visibility and leak gates | `pack.compatibility.yaml` and `raes-pack-release` own participant/public versus operator/oracle/private pack views. Native source is external provenance, not a new pack tier. Exercise actual release views and every portable command projection with hostile native/restricted sentinels; prove participant/public output excludes operator/evaluator/restricted content and all native representations. Hashing a native value does not make it portable. |

The compatibility manifest indexes boundaries and validation commands; it does
not define an evaluator oracle, scoring rule, lifecycle policy, or backend
configuration. Provenance must cover every upstream and generated source,
excluded artifact, license/notice obligation, safety review, retained-output
decision, redistribution decision, and publication-review gate. Native source
is referenced, not redistributed inside the pack. Source-ledger references must
resolve to the existing immutable ledger and qualification facts.

## Extension seam

The required seam is a closed backend-local selection: expected external pack
identity/version/content digest and acquisition reference; scenario snapshot;
task/spec; red participant implementation/configuration; episode control;
ordered seed allocation; native qualification/protocol selection; and mode/run
id. Its fields resolve to published owners and are validated at the boundary;
it is not serialized as a new contract.

A future CyberBattleSim case or pack version adds another immutable selection
and published artifacts. It must not require editing the existing pack, adding
a pack/scenario registry to `raes_adapters.base`, duplicating the command
workflow, or branching shared code on native object types. Pack location must
remain a strategy of the command adapter (external-only here, package resource
for legacy examples), not an assumption that every backend bundles content in
the wheel.

## Gotchas and anti-patterns

- Do not let the fake/injected conformance driver, a fixed-action test policy,
  or a source-native evaluator that bypasses RAES satisfy the researcher run or
  manual native-readiness claim.
- Do not claim autonomous execution while the manifest says otherwise, or
  change the manifest without executable capability-to-evidence closure and
  hostile failure/leak tests.
- Do not conflate participant, source-internal defender, operator, evaluator,
  pack validator, or release publisher; do not expose evaluator/hidden facts to
  the participant view.
- Do not conflate pack version, repository tag, adapter version, backend
  manifest version, source commit/tree/wheel, scenario snapshot digest,
  associated-artifact set digest, participant configuration digest, run id, or
  inventory digest.
- Do not put Gym ids, Python symbols, native action coordinates, simulator
  configuration, runtime implementation selection, or source paths into SDL or
  compatibility metadata to make dispatch easier.
- Do not infer deterministic replay from seed acceptance. Preserve separate
  dispositions for Gym environment, action-space, Python random, and NumPy
  streams and the existing public-evaluator seed-loss limitation.
- Do not turn reward, terminal state, objective truth, evidence, derived
  measure, conformance, readiness, rehearsal success, or scientific validity
  into one `passed` field.
- Do not add a local pack/schema/provenance/associated-artifact/experiment/
  participant/inventory model, exception hierarchy, profile, registry, store,
  release validator, or workflow because a published owner is inconvenient.
- Do not execute acquired pack scripts during validation, trust a filename or
  mutable URL, write before admission, use absolute artifact URIs, serialize a
  native snapshot, or retain raw native logs and call them evidence.

## Non-goals and implementation boundaries

- No new RAES or environment-pack semantics, SDL extension, vocabulary,
  profile, fixture corpus, diagnostic envelope, evidence type, participant or
  backend protocol, scoring rule, lifecycle policy, or scientific claim.
- No scenario content in `RAESystem/env-packs`, pack content in the Python
  wheel/sdist, second distribution, lockfile, console script, second release
  workflow, service, endpoint, scheduler, database, or cache.
- No runtime source clone/download, published native wheel, silent patch,
  editable checkout authority, arbitrary participant/plugin import, or
  environment-selected implementation.
- No notebook/UI/training/leaderboard product, remote execution service, or new
  authentication system.
- No deterministic replay, state/observation equivalence, outcome equivalence,
  benchmark comparability, or scientific validity claim follows from a green
  validation, run, rehearsal, conformance report, or reproducible command line.
