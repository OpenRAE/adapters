# NASim scenario and source-ledger guardrails

Issue #33 is the authority for the deliverable. This note fixes repository and
contract boundaries; it is not an implementation plan and does not author the
scenario or ledger.

## Keep portable authoring separate from source evidence

The evidence set is package-local under `raes_adapters.nasim` and has distinct
owners:

- `qualification.json` remains the immutable source, runtime, legal, and
  admission record; `public-protocol.md` remains selected NASim-native protocol
  evidence.
- The RAES SDL carries only portable scenario meaning: topology, hosts,
  services, vulnerability/identity/credential intent, reachability/firewall,
  participant-visible actions and observations, propositions, and objectives.
- RAES published experiment contracts carry reward/metric definitions,
  evaluator policy, episode controls, termination/truncation, and stochastic
  controls that SDL does not model. Evidence and derived-measure contracts carry
  recorded results only after a run.
- A backend-local ledger maps each pinned fact to one of those existing
  surfaces, excludes it, or loss-discloses it. Loss disclosures state the
  ADR-069 equivalence tier weakened; they never substitute for portable state.

The selected NASim `tiny` scenario is a static benchmark. Do not represent it
as a generated scenario. If a later selected case uses NASim generation, put
the portable parameters in existing SDL variables and variation points, and
validate explicit instantiated assignments; do not add a NASim generator block
or opaque metadata.

## Reuse the canonical validators and evidence pattern

Use the module-local pattern in
`raes_adapters.cyberbattlesim.scenario_ledger` as the closest incumbent, while
keeping NASim field names, resources, and validation inside
`raes_adapters.nasim`. Reuse `load_qualification()`, `read_public_protocol()`,
`importlib.resources`, SHA-256 joins, `raes.parse_sdl_file()`, RAES scenario
instantiation/canonical digest functions,
`raes_processor.compiler.compile_scenario_runtime_model()`, closed experiment
models/parsers, and `raes_contracts.contracts.schema_bundle()`.

The ledger is a bounded, closed JSONL package resource, not a public DTO,
schema, profile, manifest, vocabulary, registry, or RAES semantic contract.
Rows must have a stable unique identity, pinned source coordinate/selector and
digest, one issue-local coverage category, exactly one disposition (`mapped`,
`excluded`, or `loss-disclosed`), a rationale and verification statement, and
a resolvable existing RAES/artifact target or loss reference as applicable.
Target resolution must derive from parsed artifacts and `schema_bundle()`; do
not maintain a second RAES target catalog, contract copy, or JSON Schema.

CI must fail closed for unknown/duplicate fields and JSON keys, non-finite
numbers, blank/duplicate IDs, source/protocol digest drift, invalid selectors
or targets, missing required coverage, invalid disposition shapes, unreferenced
or tierless losses, and portable-native leakage. Source drift is an offline
join to already-qualified checked-in pins: validation must not fetch upstream,
execute NASim, or depend on a network. A newly consumed source file first joins
the reviewed qualification record.

The required categories are topology/state, identities, participants, actions,
observations, controls, rewards/objectives, termination, evaluator, stochastic
policy, and provenance/licensing. The categories and dispositions are
issue-local validation labels, not additions to RAES vocabulary.

## Cross-cutting safety and operations

| Layer | Guardrail |
| --- | --- |
| Authentication/authorization | No HTTP, caller, or mutable control-plane surface is introduced. A future service must use RAES strict control-plane defaults, not this evidence path. |
| Secrets | SDL may express synthetic credential intent only. Never include real/learned credentials, password values, tokens, caches, or secret references; `.secrets` is not an input. |
| Parsing and configuration | SDL uses the bounded RAES parser/semantic validation; experiment files use closed RAES models; ledger JSONL rejects unknown shape. Qualification is canonical: no environment override of source identity or scenario semantics. |
| OS/process exposure | Deterministic validation reads package resources in process: no shell interpolation, upstream import/execution, network fetch, home/cache dependence, or argv/environment dump. |
| Errors and observability | Reuse RAES diagnostics at portable boundaries. Ledger failures expose only row ID, field, and bounded reason—never native values, raw source payloads, paths, logs, or tracebacks. No logger, exception hierarchy, or result envelope is added. |
| Persistence/distribution | Checked-in package data is the only state. Keep resources under `src/raes_adapters/nasim` so the existing Hatch wheel/sdist clean-install proof covers them; add no store, cache, dependency, extra, lockfile, or workflow. |

## Extension seam and boundaries

The sole extension seam is an explicit module-local immutable evidence
selection (artifact paths, IDs, and pinned digests). A second NASim case must
be addable as another selection using the same validator and published RAES
contracts, with its scenario/generator assignments declared in portable
artifacts—not by a central simulator registry or branches in shared plumbing.

Do not add an adapter runtime, generic Gym/Gymnasium wrapper, native action-ID
registry, simulator-specific SDL/schema/profile/manifest, conformance harness,
environment pack, persistence layer, or equivalence claim. Never publish a
Gym reset/step tuple, raw array/object/state, native reward vector or score,
hidden truth, simulator log, environment/argv dump, token, or traceback. Keep
NASim-native terminology in package-local protocol/provenance/mapping evidence.

Do not conflate NASim goal completion with Gym `terminated`, step-limit with
`truncated`, source reward with portable objective or study metric, reset seed
with the global NumPy action-success stream, or a static benchmark with a
generated scenario. Preserve the qualification record's known unbound and
inapplicable stochastic controls as either explicit existing experiment control
status or a loss disclosure; a seed value alone is not deterministic replay.
