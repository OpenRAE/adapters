# CybORG/CAGE-2 backend qualification guardrails

Issue #12 is the authority for the qualification outcome. This note fixes the
repository and contract boundaries that outcome must respect; it does not select
an upstream revision, define a runtime-profile schema, or describe an
implementation plan.

Maintainer selection admits the CybORG backend. Qualification grades the
selected source, installation path, controls, known losses, and attainable
reproduction claims; it does not veto adapter implementation. A source-installed
backend can be supported while automatic installation through the optional
extra remains unavailable.

## Keep the source closure coherent

The CAGE Challenge 2 repository contains a bundled `CybORG/` source tree,
Scenario2 content, wrappers, evaluation code, and baseline agents. The
standalone CybORG repository is a distinct, evolving source line. A version
label such as "2.1" does not prove that files from the two repositories are the
same.

The selected profile must therefore name one coherent source closure:

- the official repository and full commit id used as the root;
- the root tree id and the selected CybORG subtree identity;
- the simulator's own version declaration as descriptive metadata, not as the
  immutable identity;
- each Scenario2 definition, evaluation entry point, wrapper, baseline red,
  blue, and green agent, packaging file, and dependency declaration by
  commit-qualified path or symbol and content digest where a file exists; and
- every separately sourced file, fork commit, patch, or built artifact with its
  origin, digest, license, and relationship to the root closure.

Do not combine a Challenge 2 scenario from one revision, wrappers or agents from
another, and a standalone CybORG package from a third while calling the result
"CAGE-2". If a mixed closure is unavoidable, it is a composed compatibility
profile: every delta and behavioral limit is explicit, and no equivalence to
the original public profile is implied.

Git commit, Git tree, selected-file digests, installable artifact digest, and
resolved environment are different identities. GitHub-generated archive bytes
alone are not the source authority. The checked-in qualification record should
reference the repository's canonical `uv.lock` by digest and record the
resolved packages needed to interpret the result; it must not become a second
lockfile or dependency solver input.

The qualification record is backend-local evidence under
`raes_adapters.cyborg`. It is distinct from:

- the CAGE-2 mapping ledger, whose rows translate source facts into RAES
  targets and should cite the selected source identities rather than choose a
  second runtime;
- a RAES experiment specification or evidence record, which uses the published
  RAES experiment contracts if one is later emitted;
- a backend manifest or conformance profile, which describes implemented RAES
  capabilities rather than upstream installability; and
- a replication or outcome-equivalence claim, which cannot be established by
  this smoke qualification.

No shared qualification DTO, schema registry, simulator catalog, or profile
loader belongs in `raes_adapters.base`.

## Legal, packaging, and patch boundary

License conclusions are scoped to the exact selected bytes. Record the pinned
license and notice digests, copyright and attribution duties, redistribution
permission for source and built artifacts, retained-output terms, and the
provenance of bundled examples, scenario data, and baseline code. A repository
root license is not by itself evidence that every nested or separately sourced
asset can be redistributed. Dependency licenses and notice obligations remain
part of the resolved profile.

If the `cyborg` extra is populated and advertised as an automatic installation
route, it must be installable from the published `raes-adapters` artifact on the
declared Python/platform boundary. A successful editable checkout, local path
dependency, floating branch or tag, install-time clone, or warm user cache is
not proof of that packaging claim. Keeping the extra empty does not prohibit
the documented source-install route. If official source cannot produce a
publishable immutable dependency, any governed repackaging or maintained fork
must preserve notices and bind:

- the unmodified upstream commit and tree;
- the fork or patch commit, patch digest, and resulting tree/wheel digest;
- the packaging-only and behavioral deltas separately;
- the reason, license, maintenance owner, and update policy; and
- a source-native compatibility test against the original public behavior.

A dependency override, copied source file, monkey patch, or wrapper edit visible
only in setup code is a prohibited silent patch. A patch that changes scenario,
action, observation, scheduling, reward, or termination semantics is not merely
a Python/Gym compatibility patch; it changes the supported behavior boundary
and must be disclosed as such.

`pyproject.toml` and the single `uv.lock` remain the packaging authorities. The
profile may summarize their resolution and pin their digests, but must not add
a second requirements lock, uv workspace, nested project, or dependency group
standing in for the published extra. Add a uv extras conflict only for a
demonstrated incompatibility with another simulator stack.

The repository currently declares `requires-python = ">=3.12"` while CI selects
Python 3.12. Qualification must not use an environment marker to make the extra
silently empty on another version the distribution claims to support. Either
the selected stack is qualified across the declared boundary or that boundary
is narrowed explicitly and consistently in package metadata, lock resolution,
classifiers, CI, and documentation.

Likewise, `pyproject.toml` currently classifies the distribution as operating
system independent while the canonical CI host is Ubuntu. Record OS, CPU, libc,
and interpreter identity for the proof. A Linux-only smoke does not establish
that the simulator extra is OS independent; either qualify the supported host
matrix or narrow the extra's documented and metadata boundary without changing
the portability claim of the RAES contracts themselves.

## Reuse the canonical boundaries

| Concern | Canonical incumbent | CybORG qualification boundary |
| --- | --- | --- |
| Packaging and resolution | `pyproject.toml`, one `uv.lock`, and ADR-003 | Populate only the existing `cyborg` extra; use frozen resolution and artifact hashes. |
| Base/extra isolation | `_extras()` and `_verification_envs()` in `noxfile.py`, plus `tests/test_cyborg_smoke.py` | Verify base and `cyborg` separately, never with `--all-extras`; base must not install or import the native simulator accidentally. |
| Built-artifact proof | `_distributions()` and `tools/probe_installed_identity.py` | Extend the existing wheel/sdist, throwaway-environment proof for both base and the extra instead of adding another build workflow or probe family. |
| Source-native precedent | `raes_adapters.cyberbattlesim` and `tests/test_cyberbattlesim_qualification.py` | Reuse backend-local evidence ownership, immutable identities, explicit legal/patch/defect decisions, and sanitized smoke summaries; do not copy its JSON shape as a shared schema. |
| CybORG source mapping | `raes_adapters.cyborg.mapping` | Cite one qualification-owned source selection; do not let the mapping ledger and runtime profile select competing revisions. |
| Portable contracts | `ContractModel` (`extra="forbid"`), `parse_experiment_spec`, and RAES cross-artifact validators | Use only if portable experiment/evidence artifacts are emitted. Qualification metadata itself remains backend-local and does not justify a parallel RAES model. |
| Portable source identity | `ExperimentArtifactRefModel` and `ExperimentChecksumModel` | Use their meanings and checksum representation when the selected source is referenced from a RAES artifact; do not overload free-form parameters. |
| Stochastic controls | `ExperimentStochasticControlModel`, `PublicSeedModel`, and `RandomStreamControlBindingModel` | Keep simulator, scenario generator, scheduler, red/green/baseline policy, wrapper/action-space, Python, and NumPy streams distinct. One seed is not complete binding. |
| Failures | RAES `Diagnostic`, `DiagnosticModel`, and `ApplyResult` | Later portable failures use bounded, input-free messages. Native exceptions, rejected actions, observations, object representations, and tracebacks remain backend-local. |
| Durable state | RAES `ControlPlaneStore` | Qualification uses checked-in immutable evidence and explicit ephemeral temporary directories; it introduces no database, cache authority, or evidence repository. |
| Workflow gates | the `policy`, `typecheck`, `tests`, `distributions`, `docs`, and `verify` nox sessions | Keep one canonical graph. Any new CI job would also have to join the `PR Gate` `needs` contract, so qualification belongs in the existing sessions unless isolation cannot otherwise be achieved. |

The release workflow installs the public `raes-adapters[cyborg]` artifact on
Python 3.12. While the extra is empty, that is a distribution-isolation check,
not a claim that it installs CybORG. Source qualification and clean built-wheel
smoke belong in the canonical nox graph, not a second release path.

## Native smoke and observability boundary

The smoke operates on the selected source-native API before any RAES adapter
normalization. It must cover construction of Scenario2, reset, representative
participation by red, blue, and green, normal progress, the selected termination
path, and cleanup. Record scheduling and API semantics precisely:

- distinguish one participant action from a complete environment turn;
- retain the selected blue/green/red execution order rather than relying on an
  incidental call order;
- distinguish the core CybORG result from legacy Gym four-tuples and any
  Gymnasium or PettingZoo normalization;
- distinguish reward vector, scalar aggregation, evaluation score, termination,
  truncation/time limit, evaluator cutoff, and explicit close/cleanup; and
- bind every stochastic entry point observed during reset and stepping.

The checked-in smoke result is a bounded structural summary: profile id,
source/artifact/lock digests, interpreter and platform identity, selected API
and wrapper identities, role participation, type/shape/arity facts, step count,
termination reason/class, and pass/fail status. It must not contain native
state, complete observations, hidden truth, action ids or object
representations, reward vectors, raw logs, environment or argument dumps,
credentials, or full tracebacks. A digest proves the identity of a named source
or artifact; hashing a native-state dump does not make that state portable.

The extension seam is the immutable selected-profile identity passed to a
module-local source-native smoke driver. Scenario paths, wrapper choice, role
agents, seeds, representative actions, and termination bounds come from that
one selection rather than being repeated across tests, scripts, and prose. A
future patched profile or another CAGE scenario should be addable as another
immutable selection without changing the runner or inventing a central
simulator registry.

## Security boundary

Qualification is local simulator execution and introduces no HTTP,
authentication, authorization, or secret-binding surface. It must use public
sources and must not require credentials, private downloads, or user-home cache
state. Installation may use the package index; the source-native runtime must
be able to execute without network access unless an unavoidable access is
recorded as part of the profile.

Commands use argument vectors rather than shell interpolation. Temporary and
cache paths are explicit, the working directory is isolated, `PYTHONPATH` is
cleared, and safe-path behavior is enabled. Do not place tokens in process
arguments, log environment mappings, or archive subprocess output wholesale.
Unexpected filesystem writes, runtime downloads, subprocesses, or socket use
are qualification findings.

If later adapter work adds an HTTP surface, it must reuse
`ControlPlaneSecurityConfig.strict_defaults`, verified identities, target/role
authorization, request-size guards, denial audit, and the redacted exception
handler from `raes_runtime`. Qualification creates no alternate controller or
weaker endpoint. Standard module logging is for bounded local operational facts;
portable observability remains RAES diagnostics and evidence contracts.

## Non-goals and anti-patterns

- No adapter implementation, RAES SDL scenario, backend manifest, conformance
  profile, evaluator implementation, or outcome-equivalence claim is part of
  qualification.
- No native CybORG package becomes a base dependency, and
  `raes_adapters.cyborg` must remain importable without the extra by keeping
  native imports lazy and narrow. Do not catch broad `ImportError` in a way that
  makes a broken installed extra look absent.
- Do not treat import success, one unseeded episode, a notebook run, or a green
  canonical graph as proof of determinism, legal usability, public
  installability, or CAGE-2 equivalence.
- Do not make the legacy Gym wrapper the RAES backend protocol, normalize tuple
  differences without recording them, or reuse native action ids as portable
  action identities.
- Do not duplicate dependency pins in prose/tests, duplicate source selection
  in the mapping ledger, introduce a qualification exception hierarchy, or add
  permissive parsing for a backend-local record.
- Do not vendor the whole upstream repository, datasets, submissions, images,
  or examples merely to obtain a few qualified runtime files. Any vendoring
  must be necessary, minimal, provenance-bound, and legally permitted.
