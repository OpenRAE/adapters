# PrimAITE qualification guardrails

Issue #39 is the authority for the qualification outcome. This note fixes the
repository and contract boundaries that outcome must respect; it does not select
an upstream revision, define a profile schema, or describe an implementation
plan.

Maintainer selection admits the PrimAITE source and public experiment profile.
Qualification records what RAES can attest or reproduce and explicitly grades
any limitation. It does not veto later adapter work or make RAES invent missing
simulator behavior.

## Keep the artifacts and claims separate

Place qualification evidence under `raes_adapters.primaite`. It is backend-local
package data, distinct from all of the following:

- a public, source-native experiment protocol, which names the chosen use case,
  YAML configuration, red/green/blue agents, traffic model, action and
  observation spaces, evaluator, rewards, seeds, metrics, and termination;
- a future RAES SDL, published experiment contract, backend manifest, or
  conformance profile, each of which is owned by published RAES contracts and
  must be supported by later implementation evidence; and
- CybORG and CyberBattleSim qualification records and ledgers, which are
  precedents for local ownership rather than schemas to copy or generalize.

The record must bind the official repository, full commit and tree ids, archive
digest, installable distribution/wheel identity, selected files and symbols,
resolved dependency graph, Python and host identity, and every observed or
configured default that changes behavior. A tag, release label, use-case name,
notebook title, package version, or YAML filename alone is not immutable.

Qualification must separately identify the unmodified source and every patch.
For a compatibility patch, record the patch and resulting tree/artifact
digests, purpose, license, semantic effect, and a bounded comparison with the
unmodified source. A dependency override, monkey patch, edited example, copied
file, or setup-time mutation that is not recorded is a prohibited silent patch.

Record license, notices/attribution, redistribution and retained-output rights,
external downloads, datasets, model weights, cache behavior, archive/
maintenance state, known upstream defects, and the evidence supporting each
conclusion. Refer to large upstream artifacts by immutable identity and digest;
do not vendor them unless necessary and explicitly permitted.

## Reuse the canonical boundaries

| Concern | Canonical incumbent | Required use |
| --- | --- | --- |
| Backend-local qualification evidence | `raes_adapters.cyborg.qualification` and `raes_adapters.cyberbattlesim` | Use package resources and small accessors; do not create a shared profile loader, DTO, registry, or schema. |
| Packaging and isolation | `pyproject.toml`, one `uv.lock`, ADR-003, `_extras()` and `_verification_envs()` in `noxfile.py` | Add only `primaite`; keep base and every extra independently resolvable. Add a uv `conflicts` declaration only for a demonstrated, recorded incompatibility. |
| Clean built-artifact proof | `_distributions()` and `tools/probe_installed_identity.py` | Extend the existing wheel/sdist, throwaway-venv proof rather than adding a second install workflow. The native smoke runs outside the checkout with `PYTHONPATH` cleared and safe-path/isolation enabled. |
| Portable experiment artifacts | `ExperimentTaskModel`, `ExperimentSpecModel`, `parse_experiment_spec`, `ContractModel` (`extra="forbid"`), and RAES cross-artifact validation | Use only if machine-readable RAES protocol/evidence is emitted; do not define local YAML/JSON schemas, permissive parsing, or duplicate validation. |
| Artifact/provenance identity | `ExperimentArtifactRefModel`, `ExperimentChecksumModel`, `ExperimentScenarioSnapshotReferenceModel`, and apparatus models | Use published meanings and checksum forms when source identity is referenced in RAES artifacts; keep legal and qualification metadata backend-local. |
| Stochastic control | `ExperimentStochasticControlModel`, `PublicSeedModel`, and `RandomStreamControlBindingModel` | Record simulator, use-case/topology, traffic, scheduler, action/observation-space, red/green/blue policy, evaluator, Python, NumPy and library RNGs separately. A top-level seed is not evidence of complete control. |
| Metrics and outcomes | `ExperimentEvaluationProtocolModel`, `ExperimentMetricDefinitionModel`, `ExperimentEvidenceRecordModel`, and `ExperimentDerivedMeasureModel` | Keep native reward, evaluator output, study metric, evidence, and derived measure distinct. |
| Failures and diagnostics | RAES `Diagnostic`, `DiagnosticModel`, `ApplyResult`, plus `raes_adapters.base.redaction` | Later portable errors use bounded, input-free diagnostics; never carry native exception text, rejected values, raw observations, reward vectors, action ids, object reprs, paths, env dumps, or tracebacks. |
| Durable state and workflow | Checked-in package resources, ephemeral temp directories, and the `policy`, `typecheck`, `tests`, `distributions`, `docs`, and `verify` nox sessions | Do not add a database, cache authority, evidence service, standalone validator, or CI workflow. |

`raes_adapters.base` remains plumbing only. This issue does not justify a
generic simulator protocol, qualification exception hierarchy, backend catalog,
schema registry, or shared persistence layer.

## Native smoke, security, and observability

The source-native smoke precedes adapter normalization. From the documented
supported route it must construct the selected case, reset with the selected
seed, issue one representative valid action/step, and record bounded facts about
the returned observation and reward/result shapes. It must exercise a bounded
path to every selected termination behavior and record their identity,
precedence, and off-by-one semantics. It must also disclose undisclosed
defaults, incompatibilities, runtime downloads/writes, network access,
subprocesses, and stochastic sources.

This is a local library execution: no HTTP, authentication, authorization, or
secret-binding surface is introduced. Public sources only; no credentials,
private downloads, token-bearing argv, environment dumps, or home-cache
evidence. Use argument vectors, explicit temporary/cache paths, isolated
working directories, frozen resolution, and bounded structural output. A later
runtime service must use RAES runtime strict defaults, verified identities,
target/role authorization, request-size guards, denial audit, and its redacted
exception handler; qualification creates no alternate path.

Use ordinary module logging only for bounded local operational facts. Portable
observability belongs to RAES diagnostics and experiment-evidence contracts.
Native state, traffic contents, hidden truth, learned credentials, full action
or observation payloads, raw logs, tracebacks, and full reward vectors remain
source-private. A digest of a native-state dump does not make it portable.

## Extension seam and boundaries

The one extension seam is an explicit module-local immutable selection identity
passed to the source-native smoke runner. Source paths, use case, YAML files,
agents, traffic configuration, evaluator, seed, representative action, metric,
and termination bounds come from that selection, not repeated across tests,
scripts, notebooks, and prose. A second public PrimAITE profile must be
addable as another selection without editing a central registry or altering the
first profile.

Non-goals: adapter semantics, RAES SDL, backend manifest, conformance profile,
participant implementation, persistence, environment-pack content, and any
claim of deterministic replay, scientific validity, or outcome equivalence.

Do not treat a successful import, notebook, one episode, or green CI as proof
of reproducibility, legal usability, public installability, determinism, or
equivalence. Do not conflate source-native `done`/`terminated`/`truncated`,
scenario success/failure, reward thresholds, evaluator cutoffs, max steps, and
participant stop conditions. Do not lower the repository Python boundary, hide
an incompatibility in an environment marker, make PrimAITE a base dependency,
or use another simulator extra to satisfy it transitively.
