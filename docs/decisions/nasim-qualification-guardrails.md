# NASim qualification guardrails

Issue #32 is the authority for the qualification evidence. This note fixes the
repository and contract boundaries that work must respect; it neither selects a
NASim revision nor defines an adapter, a RAES scenario, or an implementation
plan.

## Keep the artifacts distinct

NASim is a separate simulator backend. Its source-native qualification,
protocol, and any later adapter belong under `raes_adapters.nasim`; they do not
belong in `raes_adapters.base`, `raes_adapters.cyborg`, or
`raes_adapters.cyberbattlesim`.

The qualification record identifies the immutable upstream source/runtime,
legal and maintenance disposition, defects, patches, maintainer admission, and
attainable claim strength for `RAESystem/research#12`. The public experiment
protocol identifies the selected named scenario or generator configuration,
Gymnasium interface, baseline agent, evaluator, reset, stochastic controls,
metrics, and termination rules. Neither artifact is a RAES schema, backend
manifest, conformance profile, policy gate, or outcome-equivalence claim.

If a machine-readable public protocol is emitted, it must use the published
`raes==2.0.0` experiment contracts, including `ExperimentTaskModel`,
`ExperimentSpecModel`, `ExperimentEpisodeControlModel`,
`ExperimentScenarioSnapshotReferenceModel`,
`ExperimentStochasticControlModel`, `ExperimentEvaluationProtocolModel`, and
their closed parsers/cross-artifact validators. Do not create a NASim profile
DTO, JSON Schema, YAML normalizer, enum catalog, or duplicate validation.

The distributable qualification record belongs in the NASim package tree so it
is included in wheel and sdist builds. Large upstream archives, generated
scenarios, datasets, benchmark notebooks, and model weights are referenced by
immutable identity and digest, not vendored, unless redistribution is necessary
and explicitly permitted.

## Selection and evidence closure

A repository URL, tag, PyPI version, scenario nickname, or benchmark-script
name alone is not immutable. The selected record must bind:

- the official repository, full commit, tree/archive digest, installation
  route, distribution/version where applicable, and the resolved dependency
  graph in the single `uv.lock`;
- Python and platform identities, Gymnasium/Gym interface identity, and every
  selected named benchmark scenario or exact generator inputs/implementation;
- selected baseline/planning/RL agent, evaluator/benchmark script, reset mode,
  seeds, metric definitions, result aggregation, and each termination condition
  by commit-qualified path or symbol plus file digest where applicable;
- explicit values and every observed source default that affects a run;
- every simulator, scenario-generator, Python, NumPy, action-space, baseline
  policy, evaluator, and dependency stochastic source, distinguishing applied,
  unsupported, unbound, and unknown controls;
- licenses and notices at the selected bytes; redistribution, attribution,
  retained-output, external-download, cache, dataset, and model-weight terms;
  maintenance/archive state; known defects; and evidence supporting each
  conclusion; and
- maintainer admission and separate grades for source identity,
  configuration/control attestation, run evidence, and outcome reproduction.

An immutable Git source and a publishable dependency are different facts. Do
not put a floating Git reference, local path, install-time clone, or unverified
direct URL in the `nasim` extra. If no official install route reproduces the
selected bytes, disclose the gap; it limits reconstruction claims but does not
override the maintainer's admission decision.

Any compatibility patch is part of the selected identity: record the original
commit, patch and resulting-tree/artifact digests, purpose, license, semantic
effect, and unmodified-versus-patched behavior. An import-time monkey patch,
dependency override, notebook edit, or copied source that is absent from the
record is a prohibited silent patch.

## Reuse existing repository boundaries

Use `pyproject.toml`, the one `uv.lock`, ADR-003, `_extras()`, and
`_verification_envs()` in `noxfile.py` for packaging and isolation. Add only a
`nasim` optional extra; verify base and every extra independently. Add a uv
`conflicts` declaration only for a demonstrated, recorded incompatibility. Do
not add a second distribution, lockfile, workspace, dependency group, or
combined-extras environment.

Use `_distributions()` and `tools/probe_installed_identity.py` for the
built-wheel, throwaway-environment proof, and the existing `policy`, `docs`,
and `verify` nox graph for repository validation. Qualification must not add a
parallel workflow, qualification validator, cache authority, database, or
backend-independent registry. Checked-in immutable evidence plus explicit
temporary directories are sufficient; `ControlPlaneStore` is the RAES owner if
a later portable runtime actually needs durable state.

For any later portable boundary, reuse RAES `Diagnostic`, `DiagnosticModel`,
and `ApplyResult`. Native errors, rejected values, observations, rewards,
action identifiers, object representations, raw logs, paths, environment or
argument dumps, hidden state, and tracebacks must not enter RAES artifacts.
Use the existing base redaction helpers for bounded local failure hygiene; do
not introduce a NASim exception hierarchy or result envelope.

## Clean source-native smoke and security

The smoke exercises the selected upstream API before adapter normalization: it
constructs the selected environment, performs reset and one representative
valid action/step, records only structural observation and reward/result facts,
and reaches each selected termination condition through bounded paths. It must
separate Gymnasium `terminated` and `truncated` from simulator success/failure,
maximum-step/time-limit behavior, evaluator cutoffs, agent stopping rules, and
any scenario-generator exhaustion. Record precedence and off-by-one behavior.

Run from an isolated temporary working directory with `PYTHONPATH` cleared and
safe-path behavior enabled. Use argument vectors, explicit confined temporary
and cache paths, a small environment allowlist, timeouts, and bounded output.
Run without network after installation where the selected source permits it.
Unexpected downloads, writes, subprocesses, sockets, cache dependence, or
model-weight fetches are qualification findings, not setup conveniences.

This work adds no HTTP, authentication, authorization, or secret-binding
surface. It must not read credentials, require private downloads, put tokens in
argv, log environment mappings, or preserve home-directory state as evidence.
If a later adapter exposes HTTP, it must use
`raes_runtime.control_plane_api.create_control_plane_app`,
`ControlPlaneSecurityConfig.strict_defaults`, verified identities, target/role
authorization, request-size guards, denial audit, and RAES's redacted exception
handler. Standard logging is limited to bounded operational facts; portable
observability remains RAES diagnostics and experiment evidence contracts.

The extension seam is one immutable selected qualification/protocol identity
passed to a module-local smoke runner. Scenario/generator, agent, evaluator,
seed, metric, and termination settings are read from that selection rather than
repeated in tests, scripts, notebooks, and prose. A second selected protocol
must be addable as another immutable selection without changing the runner or
creating a central simulator registry.

## Non-goals and anti-patterns

- No NASim adapter semantics, RAES SDL, backend manifest, conformance profile,
  evaluator implementation, generic Gym/Gymnasium wrapper, or outcome
  equivalence claim is delivered by qualification.
- Do not modify `raes_adapters.base` or turn it into a simulator catalog,
  generic environment/step model, reward abstraction, action-id registry, or
  native tuple-normalization layer.
- Do not mistake import success, a notebook run, one episode, a seeded reset,
  or a green CI graph for legal usability, deterministic replay, scientific
  validity, source reconstruction, or outcome reproduction.
- Do not conflate a named benchmark scenario with a scenario-generator sample;
  a public baseline with a locally substituted agent; native reward with a
  study metric; or `done` with Gymnasium `terminated`/`truncated`.
- Do not call a default known unless it is source-bound or observed in the
  pinned clean run. Undocumented, version-dependent, platform-dependent, or
  uncontrolled behavior remains a disclosed limitation.
