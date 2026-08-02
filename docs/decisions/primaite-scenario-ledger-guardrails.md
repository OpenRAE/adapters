# PrimAITE scenario and source-ledger guardrails

Issue #40 is the authority for this deliverable. This note fixes the
repository, contract, validation, and claim boundaries; it neither authors the
scenario/ledger nor provides an implementation plan.

## Separate portable meaning from source evidence

Keep all artifacts package-local under `raes_adapters.primaite`.
`qualification.json` and `public-protocol.md` remain the authority for the
selected PrimAITE v4.0.0 commit, qualified source-file digests, legal facts,
runtime observations, known defects, and bounded claim strength. The new RAES
SDL carries portable scenario meaning only. Published RAES experiment contracts
carry evaluation protocol, numeric reward/metric definitions, fixed-horizon
episode control, scheduling intent, and stochastic controls that SDL does not
own. The JSONL mapping ledger and loss-disclosures document are backend-local
traceability evidence, not a RAES schema, profile, manifest, vocabulary, DTO,
or semantic metadata convention.

In particular, preserve these distinctions: source configuration versus
authored scenario; BLUE's native `Discrete(78)` action number versus portable
action contracts; flattened Gym observation versus participant observation
boundary; objective truth versus scalar reward and derived measure; source
`terminated=False` versus fixed-horizon `truncated`; and RED/GREEN/BLUE actor
identities versus an evaluator or a control-plane caller. Do not put PrimAITE
terms, raw source fields, or unsupported values into SDL metadata to bypass a
published model.

Every consumed source file must first be joined to the qualification-owned
immutable selection. A row repeats repository, commit, path, selector, and
digest for reviewability, but cannot become a second pin authority. If issue
#40 needs files outside `qualification.json.source_files`, extend the reviewed
qualification closure and its exact tests before mapping them. CI remains an
offline integrity join: it must not fetch a branch, import PrimAITE, execute
upstream code, or make network availability part of validation.

## Reuse the existing owners

| Concern | Incumbent to compose |
| --- | --- |
| Source, legal, protocol, and stochastic provenance | `raes_adapters.primaite.load_qualification()`, `read_public_protocol()`, and the SHA-256 resource-join pattern in `tests/test_primaite_qualification.py` |
| SDL parse, semantic validation, instantiation, digest, and compile | pinned `raes==3.3.0`: `raes.parse_sdl_file()`/`parse_sdl()`, instantiation and canonical digest APIs, and `raes_processor.compiler.compile_scenario_runtime_model()` |
| Experiment inputs and portable evaluation | closed published RAES contract models (`extra="forbid"`), `ExperimentTaskModel`, `ExperimentSpecModel`, `parse_experiment_spec()`, and their cross-artifact validators |
| Target resolution | `raes_contracts.contracts.schema_bundle()` plus the parsed authored artifacts; never a local section/model/property catalog |
| Source-ledger mechanics | the module-local strict JSONL, row-id/field/reason, coverage, loss-reference, and negative-test pattern in `raes_adapters.cyberbattlesim.scenario_ledger`, without importing it or copying its backend-specific labels as shared authority |
| Portable failures | existing RAES `Diagnostic`, `DiagnosticModel`, and `ApplyResult` at a later runtime boundary; static validation may return bounded row-id/field/reason problems |
| Native-value failure hygiene | `raes_adapters.base.redaction`; never native exception text, repr, traceback, rejected payload, raw state, path, argv, or environment dump |
| Packaging and verification | package resources under `src/raes_adapters/primaite`, Hatch wheel/sdist inclusion, `_verification_envs()`, existing `tests`, `distributions`, `docs`, `policy`, and `verify` nox sessions |

`raes_adapters.base` remains plumbing: do not put a ledger model, parser,
registry, exception hierarchy, policy gate, persistence store, or simulator
protocol there. Do not add a PrimAITE dependency, extra contents, lockfile,
workflow, native smoke, adapter/backend, manifest, conformance profile, or
environment-pack dependency merely to author static evidence.

## Required fail-closed evidence boundary

The ledger may use only the issue-local labels `mapped`, `excluded`, and
`loss-disclosed`, and its required coverage categories. They are validator
labels, not RAES vocabulary. Each atomic row has a stable unique id; immutable
source coordinate and digest; category; exactly one disposition; rationale and
verification; a resolvable RAES target when mapped; or a referenced disclosure
and matching ADR-069 equivalence tier when lossy. Exclusions have a bounded
rationale and no target/loss fields.

Reject malformed UTF-8/JSONL, duplicate JSON keys, non-finite values,
non-object rows, unknown or blank fields, duplicate ids, unqualified
source-path/digest/repository/commit values, missing categories, unresolved
targets, an excluded row with a target, a mapped row without a target, orphan
or tierless disclosures, and an undisclosed loss. Resolve targets against the
parsed SDL/experiment artifacts or the pinned schema bundle; do not create a
second JSON Schema, Pydantic DTO, enum, target list, or standalone validator.

The ledger must cover topology/state; identities; participants; actions;
observations; controls (including addresses, ports, services, traffic,
firewall/routing behavior); rewards/objectives; termination; evaluator;
stochastic policy; and provenance/licensing. Category presence alone does not
prove semantic exhaustiveness: source/configuration, simulator implementation,
agent code, evaluator, and public protocol must each be reviewed for the facts
they contribute. A partial transformation is split into a mapped fact and a
separate loss-disclosed fact, never hidden in mapping prose.

No portable content may contain native action ids, Gym tuples, flattened arrays,
raw object/state, `info`, traffic payload, hidden truth, credential value/cache,
reward vector, simulator log, token, argv/environment dump, or traceback.
Structural exclusion by closed RAES models is primary; a deterministic,
qualification-grounded leakage scan is defense in depth. Do not manufacture
run evidence while authoring; captures, evidence records, and derived measures
are only published contracts for a later execution.

## Cross-cutting security and operational layers

| Layer | Required treatment |
| --- | --- |
| Authentication and authorization | None is introduced: checked-in static resources have no HTTP, control-plane caller, mutation API, or auth surface. A later service must use RAES runtime strict defaults and target/role authorization. |
| Secret handling | Public source only. SDL may express synthetic account/credential intent but never real, learned, cached, or resolved values. The repository secret store is not an input. |
| Parser and shape gates | Bounded RAES SDL parsing/semantic validation and compiler; closed experiment models; strict JSONL with duplicate-key/non-finite/unknown-field rejection; schema-bundle target resolution; cross-artifact digest joins. |
| Config and environment | The immutable qualification selection is the sole identity input. No environment variable, CLI option, working-directory discovery, floating ref, or local config overrides pins, semantics, target resolution, or loss tiers. |
| OS/process exposure | In-process, offline resource validation only. No native import/execution, shell interpolation, upstream checkout, network fetch, home-cache write, subprocess, or sensitive argv/environment output. Existing qualification's isolated temporary HOME and sanitized invocation remain its own native-smoke boundary. |
| Errors and observability | Errors name only a bounded row id, field, and reason; reusable portable errors use existing RAES diagnostics. No logger family, raw log artifact, error envelope, native exception text, or traceback is added. |
| Persistence and distribution | Checked-in package data is the only durable state. Existing Hatch wheel/sdist and clean-install proof verify presence. No database, cache authority, repository service, audit log, or second CI workflow. |

## Extension seam, non-goals, and gotchas

The sole external seam is an explicit immutable module-local evidence selection:
the qualification identity plus scenario, task/spec, ledger, and loss-resource
identities (and their pinned canonical artifact digests). A future public
PrimAITE case is another selection passed to the same module-local validation
entry point—not a central registry, environment override, or branch in a
hand-maintained contract catalog. Scenario variability belongs in published SDL
variables/variation points and explicit RAES instantiation inputs, not Python
branches or native config blocks.

Non-goals are a PrimAITE adapter/runtime, participant implementation, simulator
installation or execution, manifest/profile, persistence layer, environment
pack, schema extension, deterministic replay, scientific validity, conformance,
or outcome-equivalence claim. Do not silently fix the broken light-route seeded
reset, uncontrolled Python/NumPy/GREEN policy randomness, dependency drift, or
fixed-horizon-only termination. Each retained limitation must be mapped or
loss-disclosed at the tier it weakens; a green ledger or source digest does not
erase it.
