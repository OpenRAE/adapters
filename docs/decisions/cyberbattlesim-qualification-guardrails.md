# CyberBattleSim qualification guardrails

Issue #25 is the authority for the qualification outcome. This note fixes the
repository boundaries the qualification must respect; it is not an experiment
selection, qualification record, or implementation plan.

## Keep the artifacts distinct

CyberBattleSim is a separate simulator backend. Its source-native evidence,
dependency, smoke proof, and any later adapter code belong under
`raes_adapters.cyberbattlesim`; they do not belong in `raes_adapters.cyborg` or
`raes_adapters.base`.

The implementation must not collapse these different artifacts into a generic
"profile":

- The **qualification record** identifies the immutable upstream source/runtime,
  legal and maintenance disposition, known defects, patches, and the
  admissibility decision for `RAESystem/research#12`. It is backend-local
  evidence, not a RAES schema or conformance claim.
- The **public experiment protocol** identifies the selected scenario, baseline
  participant(s), basic defender, evaluator, reset semantics, stochastic
  controls, metrics, and termination rules. If it is emitted in machine-readable
  RAES form, it must use the published experiment contracts from `raes==2.0.0`;
  this repository must not define a parallel protocol DTO or schema.
- A future **backend manifest or conformance profile** describes the implemented
  adapter's RAES capabilities. Qualification of the unmodified upstream source
  does not justify creating one or claiming backend conformance.
- The existing CAGE-2 **source ledger** is mapping evidence for the CybORG
  backend. It is a pattern for module-local evidence ownership, not a schema to
  copy or extend for CyberBattleSim.

The distributable qualification record belongs inside the CyberBattleSim
package tree so it is present in the built wheel and sdist. A docs-only record
would be absent from the current sdist include set. Large upstream source
archives, notebooks, datasets, and model weights must be referenced by immutable
identity and digest rather than vendored unless redistribution is both necessary
and explicitly permitted.

## Immutable identity and legal disposition

A tag, branch, notebook title, example name, or package version alone is not an
immutable source identity. The record must bind:

- the official repository and full commit id, plus the tag/release only as an
  alias;
- the installable distribution name, version, source, and resolved dependency
  graph in the repository's single `uv.lock`;
- the supported Python identity, which must remain compatible with the
  distribution's `requires-python` boundary;
- every selected scenario, environment, participant, defender, evaluator,
  notebook, configuration, vulnerability model, and goal/SLA/termination source
  by commit-qualified path or symbol and content digest where a file exists;
- every explicit value and every observed upstream default that affects the
  run;
- external downloads, datasets, weights, caches, and network access, including
  an explicit "none";
- upstream and dependency licenses at the pinned revisions, attribution and
  notice duties, redistribution permission, retained-output permission,
  maintenance/archive status, and the evidence used for each conclusion; and
- a dated `admissible` or `not admissible` decision for
  `RAESystem/research#12`, scoped to exactly the recorded source and protocol.

An immutable Git source and a publishable Python dependency are separate
questions. Do not put a floating Git reference, local path, install-time clone,
or unverified direct URL into the published extra. If the official source has no
publishable installation route that reproduces the selected commit, the record
must expose that gap; an empty or Python-excluded extra is not a passing
qualification.

Compatibility patches are part of the identity. Record the unmodified commit,
patch digest, patched-tree or resulting-artifact digest, purpose, license,
semantic effect, and the behavior of both unmodified and patched source. A
monkey patch, dependency override, edited notebook, or copied source file that
is only visible in setup code is a silent patch and is prohibited.

## Reuse the existing contract and verification boundaries

| Concern | Canonical incumbent | Qualification boundary |
| --- | --- | --- |
| Portable experiment shape | `raes_contracts.contracts.ExperimentTaskModel`, `ExperimentSpecModel`, and `ExperimentEpisodeControlModel` | Reuse only when a machine-readable public protocol is emitted; do not add local models or permissive parsing. |
| Scenario, apparatus, and artifact identity | `ExperimentScenarioSnapshotReferenceModel`, `ExperimentApparatusConstraintModel`, `ExperimentApparatusContextModel`, `ExperimentArtifactRefModel`, and `ExperimentChecksumModel` | Use digest-qualified references with the meaning and checksum representation required by the published models. Do not overload arbitrary parameters with source or license metadata. |
| Seeds and stochastic entry points | `ExperimentStochasticControlModel`, `PublicSeedModel`, and `RandomStreamControlBindingModel` | Record each simulator, topology, scheduler, action-space, baseline-policy, and evaluator source separately. One top-level seed is not evidence that all randomness is controlled. |
| Metrics and evidence | `ExperimentEvaluationProtocolModel`, `ExperimentMetricDefinitionModel`, `ExperimentEvidenceRecordModel`, and `ExperimentDerivedMeasureModel` | Keep native reward, evaluator result, metric, and derived measure distinct. A cumulative reward is not automatically the study metric. |
| Closed validation | `ContractModel` (`extra="forbid"`), `parse_experiment_spec`, and the experiment cross-artifact validators | Validate through RAES; do not duplicate JSON Schema, YAML normalization, enum catalogs, or validation logic. |
| Backend failures | RAES `Diagnostic`, `DiagnosticModel`, and `ApplyResult` | Portable failures use bounded, input-free messages. Native exception text, rejected values, raw observations, and full tracebacks remain backend-local and are not copied into a portable artifact. |
| Packaging and isolation | `pyproject.toml`, one `uv.lock`, ADR-003, `_extras()`, and `_verification_envs()` in `noxfile.py` | Add only the `cyberbattlesim` extra; verify base and every simulator extra separately. Add a uv extras conflict only when incompatibility is real and recorded. |
| Clean installation | `_distributions()` in `noxfile.py` and `probe_installed_identity.py` | Extend the existing built-wheel, throwaway-environment proof. The source-native smoke must run from the installed artifact with no checkout import path, not from an editable install or notebook working directory. |
| Repository policy | the `policy`, `docs`, and `verify` nox sessions | Reuse the existing gates. Do not add a second qualification workflow or validator; a new CI job would also have to join the `PR Gate` contract. |
| Durable runtime state | RAES `ControlPlaneStore` | Qualification uses checked-in immutable records and ephemeral temporary directories. It does not introduce a database, cache authority, evidence repository, or backend-independent store. |

The source-native smoke must exercise the upstream API before adapter
normalization: reset, one representative valid action/step, the returned
observation and reward/result shapes, and a bounded path to every selected
termination condition. It must record the native API arity and termination
semantics without publishing raw native state. Execute from an isolated
temporary working directory with `PYTHONPATH` cleared and safe-path behavior
enabled, and run without network after installation where the upstream source
permits it. Unexpected runtime downloads or writes are qualification findings,
not setup conveniences.

The extension seam is the selected qualification/protocol artifact identity
passed to a module-local smoke runner. Scenario, participant, evaluator, seed,
metric, or termination values must be read from that one canonical selection,
not repeated in tests, scripts, notebooks, and prose. A second admissible public
protocol should be addable as another immutable selection without changing the
runner or inventing a central simulator registry.

## Security and observability boundary

This qualification is a local library execution and introduces no HTTP or
authentication surface. It must not read credentials, depend on private
downloads, place tokens in process arguments or environment dumps, or retain
home-directory caches as evidence. Commands use argument vectors rather than
shell interpolation, temporary paths are explicit, and captured output is a
bounded structural summary.

If later adapter work exposes a runtime HTTP surface, it must reuse
`ControlPlaneSecurityConfig.strict_defaults`, verified identities, target/role
authorization, request-size guards, denial audit, and the redacted exception
handler from `raes_runtime`; qualification does not create a weaker path around
them.

Use standard module logging only for local operational detail. Portable
observability uses RAES diagnostics and experiment evidence contracts. Do not
log or archive native object representations, complete observations, hidden
truth, action ids, reward vectors, environment/argument dumps, secrets, or full
tracebacks as RAES evidence. Sanitized source-native facts may state types,
field names, dimensions, termination booleans, and stable digests when those
facts are sufficient to prove the smoke behavior.

## Non-goals and anti-patterns

- No CyberBattleSim adapter semantics, RAES SDL scenario, backend manifest,
  conformance profile, or equivalence claim is implemented by qualification.
- No change to `raes_adapters.base`, no reuse of the CybORG module as a generic
  cyber namespace, and no shared simulator registry is justified.
- No second distribution, lockfile, uv workspace, dependency group standing in
  for a published extra, or combined-extras verification environment is allowed.
- Do not lower the repository's Python boundary, hide an incompatibility behind
  an environment marker, or let an unrelated simulator extra resolve the
  CyberBattleSim dependency transitively.
- Do not treat a successful import, notebook execution, single episode, or CI
  pass as proof of reproducibility, determinism, legal usability, scientific
  validity, or admissibility.
- Do not conflate simulator `done`/`terminated`/`truncated`, goal satisfaction,
  defender SLA failure, maximum steps, evaluator cutoff, and participant stop
  conditions. Record their identities, precedence, and off-by-one behavior.
- Do not call an upstream default "known" unless it is bound to source evidence
  or observed in the pinned clean run; undocumented and platform-dependent
  defaults remain explicit limitations.
