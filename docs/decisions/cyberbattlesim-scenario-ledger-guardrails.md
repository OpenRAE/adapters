# CyberBattleSim scenario and source-ledger guardrails

Issue #26 is the authority for the deliverable. This note fixes the repository
and contract boundaries the implementation must respect; it is not an
implementation plan and does not author the scenario or ledger.

## Keep the artifacts and claims separate

The deliverable is a package-local evidence set under
`raes_adapters.cyberbattlesim`, not one overloaded document:

- `qualification.json` remains the source of truth for the selected repository,
  commit, tree, archive and file digests, legal disposition, known defects, and
  admissibility outcome.
- `public-protocol.md` remains source-native evidence for the selected
  CyberBattleSim case.
- The authored RAES SDL carries portable scenario meaning only.
- Published RAES experiment contracts carry pre-run episode, evaluator,
  metric, capture, and stochastic intent that RAES deliberately excludes from
  SDL.
- The source ledger is backend-local traceability evidence. It explains how
  pinned source facts reach those portable surfaces, or why they do not.
- Loss disclosures bound the strength of the applicable ADR-069 equivalence
  tier; they are not substitute portable state.

The issue's request for SDL covering rewards, termination, and stochastic
controls must therefore be read as a request for one portable scenario
artifact set. RAES 2.0.0 rejects SDL scoring/reward sections. Objective truth
may be authored in SDL, while numeric reward, evaluator metrics, episode
cutoffs, and random-stream controls belong in companion published experiment
contracts.

The current qualification is `not-admissible`. Authoring and validating this
evidence set does not change that decision and must not be described as
installability, runnable adapter support, deterministic replay, backend
conformance, or scientific equivalence.

## Reuse the published semantic owners

| Source concern | Canonical portable owner |
| --- | --- |
| Fixed topology, nodes, services, reachability, vulnerabilities, identities, accounts, roles, and credential intent | Existing SDL `nodes`, `infrastructure`, `relationships`, `vulnerabilities`, `entities`, `accounts`, and related closed models |
| Generated topology choices | SDL `variables` and `variation_points`, followed by RAES instantiation; not a CyberBattleSim generator block or opaque `metadata` |
| Initial attacker position or ownership, defender detection/reimage behavior, and availability | SDL agents, propositions, assertions, objectives, action contracts, observation boundaries, behavior specifications, outcome interpretation, workflows, and evidence requirements as their source semantics require |
| Participant-visible actions and observations | SDL `action_contracts`, `observation_boundaries`, `behavior_specifications`, and `agents`; native action ids, masks, tuples, caches, and hidden state remain source-private |
| Objective satisfaction | SDL propositions, assertions, and objectives |
| Reward components, cumulative reward, evaluator policy, and study metrics | `ExperimentTaskModel.evaluation_protocol`, `ExperimentEvaluationProtocolModel`, and `ExperimentMetricDefinitionModel`; later run output uses evidence and derived-measure contracts |
| Turn order, source-native termination, evaluator cutoff, episode count, and selected participant variant | `ExperimentSpecModel.run_plan`, `ExperimentEpisodeControlModel`, and the published reference models it composes |
| Seeds and stochastic entry points | One `ExperimentStochasticControlModel` per source; add `RandomStreamControlBindingModel` only when an admitted executable profile truly governs that source |
| Captured observations and calculated results | `ExperimentCaptureSpecModel`, `ExperimentEvidenceRecordModel`, and `ExperimentDerivedMeasureModel`; do not fabricate run evidence during authoring |
| Repository, file, protocol, license, and notice provenance | Existing qualification resources and backend-local mapping evidence; never SDL fields or arbitrary experiment parameters |

Do not use `SDLLineageLedgerModel` for this mapping. That published contract
records the ancestry of the RAES language and its normative artifacts, not the
provenance of one simulator-derived scenario. Likewise, do not mint a backend
manifest or participant implementation manifest before an implementation and
evidence-backed capabilities exist.

## Source-ledger boundary

Follow the existing CybORG directory's module-local ownership pattern, but do
not copy its CAGE-specific field names into a shared schema or generalize either
ledger into `raes_adapters.base`.

The CyberBattleSim ledger is a closed, flat evidence record whose rows carry
only the minimum issue-required facts: a stable row identity, an immutable
source coordinate and selector, source category, one of `mapped`, `excluded`,
or `loss-disclosed`, resolvable RAES target references where applicable, the
mapping or exclusion rationale, verification evidence, and loss references
where applicable. This is package data, not a public DTO, profile, vocabulary,
manifest extension, or semantic contract.

Validation must fail closed on all of the following:

- malformed or unknown row fields, duplicate JSON keys, non-finite numbers,
  blank identities, and duplicate row ids;
- a repository, commit, source path, or digest that does not join to the
  canonical qualification record, and a local protocol digest that does not
  match its recorded digest;
- absence of any issue-required category: topology/state, identities,
  participants, actions, observations, controls, rewards/objectives,
  termination, evaluator facts, stochastic policy, and provenance/licensing;
- a row without exactly one disposition, an excluded row without a rationale,
  or a lossy row without a loss disclosure;
- a mapped target that does not resolve either to an actual validated artifact
  path or to a contract id and property path in
  `raes_contracts.contracts.schema_bundle()`;
- a loss not referenced by a source row, a lossy row without a referenced loss,
  or a loss that does not name the ADR-069 equivalence tier it weakens; and
- any native action id, Gym tuple, raw object/state, credential value, reward
  vector, hidden truth, simulator log, argument/environment dump, token, or full
  traceback in portable content.

Target validity must be derived from parsed artifacts and the published schema
bundle. Do not maintain a second list of RAES sections, contract ids, enums, or
JSON Schemas. The three row dispositions and the required coverage categories
are issue-local validation labels, not new RAES vocabulary.

Source drift is an offline integrity join. CI validates rows against the
already-qualified immutable commit and file digests plus the checked-in protocol
digest; it must not fetch a floating branch, execute upstream code, or turn
network availability into a validation prerequisite. A newly consumed source
file must first become part of the reviewed qualification evidence.

## Compose the existing validation graph

The implementation must build on these incumbents:

- `raes==2.0.0` in `pyproject.toml` and `uv.lock`;
- `raes.parse_sdl_file()` with default semantic validation and parser limits;
- RAES instantiation and canonical digest functions for each representative
  fixed/generated assignment;
- `raes_processor.compiler.compile_scenario_runtime_model()` for compilation
  without inventing a CyberBattleSim backend manifest;
- `ContractModel` (`extra="forbid"`), `parse_experiment_spec()`, and direct
  published-model validation for companion experiment artifacts;
- `schema_bundle()` for published contract identity and target resolution;
- `load_qualification()`, `read_public_protocol()`, `importlib.resources`, and
  the SHA-256 join pattern already exercised by
  `tests/test_cyberbattlesim_qualification.py`;
- the existing `tests` session and canonical `nox -s verify` graph; and
- the existing wheel/sdist and clean-install proof in `_distributions()`.

Ledger-only relational checks may be small module-local helpers or tests. They
must not become a Pydantic model, generated JSON Schema, schema registry,
standalone policy gate, second CI workflow, reusable exception hierarchy, or
parallel conformance harness.

The environment-pack repository owns its own
`environment-pack-provenance/v3` licensing, safety, distribution, and
publication schema. This repository should expose immutable source and legal
facts as package resources; an environment pack maps those facts into its own
provenance ledger and validates them with `raes-pack-validate`. Neither
repository should import or duplicate the other's schema, and no runtime
dependency between the distributions is justified.

## Cross-cutting security and operational boundary

| Layer | Required treatment |
| --- | --- |
| Authentication/authorization | None is introduced: these are static local artifacts with no HTTP, control-plane caller, or runtime mutation surface. A later service must reuse RAES runtime strict defaults rather than this path. |
| Secret handling | SDL may express synthetic account and credential intent, never a real password, learned credential, credential cache, token, or secret reference value. The repository secret store is not an input. |
| Input shape and parsing | SDL passes through the bounded RAES YAML parser and semantic validator; experiment artifacts pass through closed RAES models; ledger parsing is strict UTF-8/JSONL with duplicate-key and unknown-field rejection. |
| Configuration and environment | The qualification selection is canonical. No environment variable may override source identity or semantics. Verification uses the frozen project lock and `--skip-requirement` for this requirement-free issue. |
| OS/process exposure | Validation runs in process over checked-in package resources. It performs no checkout-relative upstream import, shell interpolation, network fetch, home-cache write, or native simulator execution, and places no sensitive value in argv or environment output. |
| Errors and observability | Reuse RAES exceptions/diagnostics at their existing boundaries. Ledger failures identify only the row id and field/reason; they do not echo source payloads or native values. No new logger, portable log envelope, or full traceback artifact is needed. |
| Persistence | Checked-in immutable package data is the only durable state. Do not add a database, cache, repository service, `ControlPlaneStore`, or evidence store for static authoring evidence. |
| Distribution | Keep artifacts under the package tree so the existing Hatch wheel/sdist and clean-install checks prove their presence. Do not add another distribution, lockfile, optional extra, or dependency for this issue. |

## Extension seam

The validator's external parameter is the explicit module-local artifact root
or selection identity. Scenario size and the fixed/generated choice belong in
SDL variables/variation points and explicit instantiation inputs, not duplicated
Python branches. A second CyberBattleSim scenario should be addable as another
immutable selection using the same validator and published RAES contracts,
without editing a central simulator registry or the current selection's
evidence.

## Gotchas, non-goals, and anti-patterns

- Do not treat the source-native `size=10` topology, a generated topology
  family, and an instantiated canonical snapshot as the same artifact.
- Do not publish learned credentials merely because SDL has an `accounts`
  section; SDL records credential intent, while native discovered material
  remains hidden.
- Do not turn the smoke reward `14.0`, winning reward `5000.0`, or a cumulative
  reward into an SDL score, objective truth, study metric, or equivalence claim
  without the explicit evaluator mapping.
- Do not collapse source termination, attacker ownership, defender SLA failure,
  defender eviction, evaluator cutoff, Gym `terminated`, and Gym `truncated`.
  Preserve source precedence and the known off-by-one limitation.
- Do not attach an executable random-stream binding to the four recorded
  CyberBattleSim randomness sources while the public evaluator drops or omits
  those bindings. Descriptive controls must retain that loss.
- Do not combine the historical benchmark snapshot with the newer selected
  source commit as though they were one run.
- Do not add an adapter, simulator dependency/extra, backend or participant
  manifest, runtime smoke, conformance profile, evidence run, environment pack,
  persistence layer, or equivalence claim in issue #26.
- Do not change `raes_adapters.base`, `raes_adapters.cyborg`, the RAES contract
  corpus, or environment-pack schemas for mapping convenience.
