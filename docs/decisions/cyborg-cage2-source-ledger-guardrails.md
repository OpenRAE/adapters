# CybORG/CAGE-2 source-ledger guardrails

Issue #13 is the authority for this deliverable. This note fixes the repository,
contract, validation, and claim boundaries the implementation must respect. It
does not author the ledger, classify a source fact, define a row schema, or
describe an implementation plan.

## Keep source, mapping, and claim authority separate

The deliverable is backend-local evidence under `raes_adapters.cyborg`:

- `qualification.json` remains the only owner of the selected profile id,
  repository, commit and tree identities, selected-file digests, legal
  disposition, stochastic-source inventory, known defects, runtime evidence,
  maintainer admission, and attainable claim strength.
- `cage2-source-ledger.jsonl` accounts for facts consumed from that selection
  and binds mapped facts only to published RAES SDL, contract, or evidence
  surfaces.
- `cage2-loss-disclosures.md` explains each lossy fact and identifies the
  ADR-069 equivalence tier or tiers whose claims it weakens.

The ledger repeats immutable source coordinates because each row must be
reviewable in isolation, but deterministic joins must prove that those
coordinates equal the qualification-owned selection. It is not a second source
profile, legal record, RAES contract, backend manifest, or experiment artifact.

A target reference means “this published surface can carry the mapped fact.”
It does not prove that a corresponding SDL scenario, experiment input, backend,
run result, evidence record, or equivalence claim exists. None is authored by
issue #13.

## Close the source and target joins

| Concern | Canonical owner and required join |
| --- | --- |
| Profile identity | `qualification.json.profile_id` and `source` own the selection. The ledger is validated against one explicit profile selection; no row may choose another repository, version label, tag, branch, or commit. |
| Source path and bytes | `qualification.json.selected_files` owns path-to-SHA-256 identity. Every ledger path and digest must join exactly. A newly consumed action, observation, reward, scheduler, or other source file must first be added to that qualified set and verified by the existing qualification driver. |
| Source selector | A selector must identify a YAML path, Python symbol, bounded line range, or document section unambiguously. Selector reachability is checked against the detached qualified checkout without importing or executing upstream code. Free-form descriptions are rationale, not selectors. |
| Portable target | Resolve SDL and contract references from `raes_contracts.contracts.schema_bundle()`, including `sdl-authoring-input-v1`; do not maintain a second list of SDL sections, contract ids, model names, properties, or enums. |
| Loss strength | Use ADR-069 §7's five tiers: authored-source, contract, execution-control, state/observation, and outcome/evaluation. These are issue-local claim labels, not a new RAES vocabulary. A loss may weaken more than one tier, and the ledger and disclosure must agree exactly. |
| Legal and attribution evidence | The pinned license files and `qualification.json.legal` own the source/legal facts. Ledger provenance rows cite those facts structurally. A downstream environment pack projects them into its own `environment-pack-provenance/v3` source row and runs `raes-pack-validate`; this repository neither copies that schema nor depends on the pack distribution. |

`qualification.json` is backend evidence, not a published RAES semantic
surface. A legal or packaging fact can therefore be explicitly out of semantic
mapping scope while retaining a machine-resolvable evidence reference to the
qualification record. It must not be mislabeled as a RAES target or hidden in
`mapping_rule` prose.

The currently qualified file set contains Scenario2, scenario images,
evaluation, the legacy wrapper, and selected simple agents. It does not contain
the complete action, observation, reward, admissibility, or turn-scheduling
implementation surface required by issue #13. The implementation must extend
the qualification-owned `selected_files` closure for every additionally
consumed file; placing unmatched digests only in the ledger would create a
competing pin authority.

## Preserve two-dimensional coverage

The accepted design has two independent completeness axes:

- source families: Scenario2 and images, actions, observations, rewards,
  wrappers, agents, evaluation, and provenance/licensing; and
- fact facets: topology, hosts, services, accounts, privileges, roles,
  participants, initial knowledge, visibility, hidden truth, actions,
  admissibility, turn order, trial lengths, termination, red variants, seeds,
  stochastic controls, reward components, objectives, and derived measures.

Validation must fail when either required axis has a gap. A broad row such as
“Scenario2 mapped” must not satisfy topology, hosts, services, accounts,
privileges, roles, visibility, and hidden truth simultaneously without
separately reviewable fact selectors. Keep each row atomic enough that one
source fact has one disposition and one reviewable transformation. Split a fact
that requires materially different targets or dispositions.

The only dispositions are the issue's `mapped`, `out-of-scope`, and
`loss-disclosed`:

- `mapped` requires a resolvable published RAES target and no loss reference;
- `out-of-scope` requires a bounded rationale and no RAES target or loss
  reference; and
- `loss-disclosed` requires a referenced disclosure and a nonempty set of
  recognized weakened tiers. A partial mapping must identify the valid target
  separately from the lost portion rather than making one ambiguous row.

Strict row validation must reject malformed JSONL, duplicate JSON keys,
non-object rows, non-finite values, unknown fields, blank required values,
duplicate row ids, unknown source families or fact facets, unknown
dispositions, unresolved selectors, source/profile/digest drift, unresolved
RAES targets, orphan disclosures, undisclosed losses, and disagreement between
row and disclosure tiers.

Automation can prove the checked-in inventory is closed, classified, joined,
and drift-free. It cannot discover every semantic fact hidden in arbitrary
upstream Python or prose. Initial semantic completeness remains a review
obligation against the accepted two-axis checklist; after acceptance, immutable
file digests ensure changed source bytes force that review to run again. Do not
claim that category presence alone proves source exhaustiveness.

## Reuse published semantic owners

| Source concern | Published owner |
| --- | --- |
| Topology, hosts, services, accounts, roles, privileges, reachability, initial scenario knowledge, and objective truth | Existing `sdl-authoring-input-v1` sections and closed RAES SDL models, including infrastructure, nodes, relationships, entities, accounts, agents, propositions, assertions, objectives, action contracts, observation boundaries, behavior specifications, and evidence requirements as applicable |
| Participant-visible actions and admissibility | SDL action contracts plus published participant action/admission, execution, lifecycle, and joint-action contracts; native classes, ids, masks, and Gym spaces remain source-private |
| Visibility, observations, and hidden truth | SDL observation boundaries and published participant observation/shared-state/evidence contracts; hidden truth is classified and bounded, never copied into a portable payload |
| Turn order, logical steps, trial length, termination, participant/red-variant selection, seeds, and stochastic declarations | `experiment-authoring-input-v1` / `ExperimentSpecModel`, its run plan, episode control, allocation, conditions, and stochastic-control models |
| Reward components, evaluator policy, cumulative score, objectives, outcomes, and derived measures | `ExperimentTaskModel.evaluation_protocol`, evaluation-result, evidence-record, derived-measure, run, and study contracts; reward is not SDL objective truth |
| Source identity and checksums when a later portable artifact cites them | Published experiment artifact-reference and checksum contracts; source licensing remains pack-domain publication evidence |

Do not use `SDLLineageLedgerModel`: it records the ancestry of the RAES
language and its normative artifacts, not the provenance of one
simulator-derived mapping. Do not add a CAGE-specific SDL section, metadata
convention, contract, vocabulary, manifest block, evidence type, or profile.

## Compose existing repository validation

The implementation must build on these incumbents:

- `load_qualification()` and package-resource loading in
  `raes_adapters.cyborg`;
- `tools/verify_cyborg_qualification.py` for the detached immutable checkout,
  selected-file digest verification, path confinement, sanitized subprocess
  environment, bounded errors, and source reachability;
- `tests/test_cyborg_qualification.py` and
  `tests/test_cyborg_qualification_driver.py` for exact source/legal/runtime
  joins and security regressions;
- `raes==2.0.0`, `ContractModel`'s closed-model behavior, and
  `raes_contracts.contracts.schema_bundle()` for published target authority;
- the strict JSONL, coverage, loss-reference, and negative-test pattern in
  `raes_adapters.cyberbattlesim.scenario_ledger`, without importing one backend
  from the other or copying its incompatible category, disposition, or
  equivalence vocabulary;
- `importlib.resources` and the existing Hatch wheel/sdist layout so the ledger
  and disclosures remain installed package resources; and
- the existing `tests`, `distributions`, `docs`, and canonical `nox -s verify`
  graph. No second workflow, conformance runner, or policy gate is needed.

The CybORG row and loss rules remain module-local. Do not move them into
`raes_adapters.base`, create a shared ledger DTO/schema/registry, or import the
CyberBattleSim validator as a cross-backend dependency. The reusable authority
is RAES's published schema bundle and the qualification selection; the
backend-specific classifications intentionally remain separate.

Parsing failures may use ordinary bounded `ValueError`/`RuntimeError` behavior,
and relational validation may return small row-id/field/reason problems as the
existing precedent does. Do not create an exception hierarchy, diagnostic
envelope, logger family, or error DTO. If a later portable runtime exposes a
failure, it must use RAES `Diagnostic`/`ApplyResult` boundaries.

## Cross-cutting security and operational boundary

| Layer | Required treatment |
| --- | --- |
| Authentication and authorization | None is introduced. These are static package resources and local validation, with no controller, caller, HTTP endpoint, or mutation API. A future service reuses RAES runtime strict-default authentication and authorization. |
| Secret handling | Consume public qualified sources only. Record account/credential semantics without real, learned, or cached credential values. Do not read a user secret store or include tokens, private material, hidden-state values, or environment contents in rows or disclosures. |
| Input shape and parsing | Decode UTF-8 JSONL strictly with duplicate-key, finite-number, closed-field, type, blank-value, and size/count checks. Resolve targets from the pinned RAES schema bundle. Parse upstream YAML/Python only for bounded selector reachability; never execute it. |
| Configuration and environment | The explicit qualification profile is the only selection input. No environment variable, CLI flag, working-directory discovery, floating ref, or user config may override source identity, target semantics, or loss tiers. |
| OS and process exposure | Offline ledger validation reads installed resources in process. Source-tree verification reuses the existing detached checkout, sanitized allowlisted environment, argument vectors, isolated temporary directory, timeouts, safe Python path, and path confinement. Do not add shell interpolation or put credentials/source payloads in argv. |
| Errors and observability | Report only bounded stage names or row id, field, and reason. Do not echo source payloads, rejected values, raw subprocess stdout/stderr, native object representations, environment/argument dumps, or full tracebacks. No new operational logger or portable log format is needed. |
| Persistence | Checked-in package resources and the existing qualification record are the only durable state. Temporary source checkouts are ephemeral. Do not add a database, cache authority, repository service, audit log, `ControlPlaneStore`, or evidence store. |
| Distribution and workflow | Keep resources under `src/raes_adapters/cyborg`; prove their installed presence through the existing build/clean-install boundary and run validation through the existing nox sessions. A new CI job would require a `PR Gate` change and is unjustified here. |

## Extension seam

The external parameter is one immutable module-local evidence selection:
qualification profile id plus ledger and loss-resource identities. The current
profile may be the default, but validation must receive that selection
explicitly. A future CAGE scenario, CybORG revision, or reviewed source closure
becomes another selection with its own qualified pins and resources, not an
environment override, central simulator registry entry, or branch in target
resolution.

Source-family and fact-facet coverage are properties of the accepted CAGE-2
design, while RAES target validity follows the pinned `schema_bundle()`. A new
source revision should therefore change selection data and ledger rows; a new
RAES release should change the pinned dependency and be reviewed against its
published bundle. Neither variation should require editing a hand-maintained
contract catalog.

## Gotchas and anti-patterns

- Do not conflate the smoke selection with the evaluation selection. The
  qualification smoke uses seed `3`, two wrapper steps, an external blue Sleep
  action, B-line red, and GreenAgent; the evaluation source declares 100
  episodes, trial lengths 30/50/100, `BlueLoadAgent`, and a three-policy red
  set.
- Do not collapse wrapper `max_steps`, logical environment turns, participant
  actions, evaluator trial cutoffs, source termination, Gym `done`,
  termination, truncation, and cleanup into one fact.
- Do not treat `CybORG.set_seed(3)` as complete stochastic control. The
  qualification already distinguishes simulator/Python random, Gym action
  space, NumPy global state, and the external blue policy, and records the
  evaluator seed as unbound.
- Do not merge backend, evaluator, blue/red/green participant, policy, and
  control-plane caller identities.
- Do not merge authored Scenario2 truth, admitted/runtime state,
  participant-visible observation, hidden truth, evidence, and derived
  measures.
- Do not treat native action classes or ids as portable action identities, or
  action availability as equivalent to admissibility.
- Do not treat reward components, reward vectors, cumulative score, objective
  satisfaction, participant outcome, backend conformance, and equivalence as
  synonyms.
- Do not silently repair the recorded Remove success misreport, Scenario2 port
  mismatch, unbound evaluation seed, legacy Gym behavior, or packaging defect.
  Any affected mapped fact must retain a source row and an appropriately tiered
  loss.
- Do not let a mapped row, a complete ledger, a green validator, or a source
  digest erase a recorded qualification limitation or imply dependency
  installability, deterministic replay, or outcome equivalence.
- Do not put semantic values into free-form metadata, `mapping_rule`,
  `verification`, comments, logs, or Markdown because the intended RAES target
  is inconvenient.

## Non-goals and implementation boundaries

- No CAGE-2 SDL scenario, experiment task/spec/study, backend manifest,
  participant manifest, conformance profile, fixture, run evidence, derived
  measure, environment pack, or equivalence result is authored.
- No CybORG adapter, evaluator, participant runtime, action/observation/reward
  projector, simulator dependency, published patched artifact, or populated
  `cyborg` extra is implemented.
- No RAES schema, SDL extension, contract, vocabulary, profile, diagnostic,
  exception hierarchy, persistence service, or policy gate is introduced.
- No native simulator execution, hidden-state capture, raw log retention,
  environment scan, privileged host operation, or runtime network service is
  added for ledger validation.
- No existing qualification limitation, known defect, legal conclusion, source
  revision, or equivalence claim is changed merely to make the mapping easier.
