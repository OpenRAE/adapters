# CybORG/CAGE-2 Scenario2 SDL guardrails

GitHub issue #77 is the authority for this requirement-free change. It authors
the full CAGE Challenge 2 Scenario2 as portable RAES SDL beside the CybORG
adapter and makes that same scenario consumable by the adapter realization and
the installed `cage2-research` pack. This note fixes the ownership, validation,
realization, security, and drift boundaries; it defines no new schema and is not
an implementation plan.

## Canonical artifact and authority

The canonical authored module belongs at
`src/raes_adapters/cyborg/scenario/cage2-scenario2.sdl.yaml`, matching the
existing backend-local scenario convention used by NASim, CyberBattleSim, and
PrimAITE. Its scenario identity, module identity/version, instantiated snapshot
digest, source-profile identity, adapter mapping version, pack identity/version,
and pack set digest are distinct values. A path is only a locator.

The `cage2-research` pack may carry a checked-in SDL snapshot because the pack
validator and installed researcher command require a pack-local artifact. That
snapshot is not a second authoring source: it must be byte-for-byte equal to the
canonical backend-local module and guarded by an equality check. The replacement
uses reviewed pack version 2.0.0 with updated scenario/task/spec references and
a rederived content manifest and set digest. Descriptions identify the full
Scenario2 apparatus rather than the former synthetic single-host smoke topology.

RAES owns every SDL field and semantic rule. The module must use the published
`sdl-yaml/v1` surface and include an explicit published `module` descriptor so
`raes sdl publish` can package it. Keep the RAES-owned `raes.lock.json` beside
the canonical module and verify it through `raes sdl verify-imports`. Scenario2
is a fixed selected source case, so the default is a self-contained module with
no imports and no invented parameters. A later real source-defined variation
may use existing SDL variables/variation points and module parameters; pack,
seed, trial-length, and red-policy choices remain experiment/apparatus controls.

## Source truth and semantic boundaries

Author from the exact source closure already owned by
`qualification.json`, `CAGE2_SOURCE_26CE1C1`,
`cage2-source-ledger.jsonl`, and `cage2-loss-disclosures.md`. The selected
Scenario2 and image-file paths/digests are source evidence, not runtime inputs or
portable metadata. Any additionally consumed image fact must have an atomic
ledger row joined to its already-qualified file and selector; the broad presence
of a `services` coverage label is not proof that every selected image was
reviewed.

The SDL carries portable topology, hosts, service/vulnerability intent,
synthetic identities/accounts and privilege intent, Blue/Red/Green participant
roles, initial-knowledge and observation boundaries, portable action contracts,
propositions/assertions, and objective truth. Preserve all source-defined roles;
Green is not merged into user hosts merely because the issue explicitly names
Red and Blue. Keep these concepts separate:

- source-native host/session/image objects versus stable portable declarations;
- participants versus backend, evaluator, policy implementation, and caller;
- authored objective truth versus source reward components, cumulative score,
  derived measures, termination, conformance, and equivalence;
- synthetic account intent versus learned credentials, native sessions, and
  hidden truth; and
- the selected port mismatch and other qualification defects versus a silently
  repaired scenario.

Reward definitions, episode cutoffs, red-policy variants, stochastic controls,
and evaluator/run protocol remain in the published experiment artifacts. Do not
hide inconvenient semantics in descriptions, arbitrary metadata, native YAML
keys, or a CAGE-specific SDL extension.

## Canonical incumbents to reuse

| Concern | Required incumbent |
| --- | --- |
| SDL shape and semantics | Pinned `raes==3.3.0`, `raes.parse_sdl_file()`, instantiation and canonical digest APIs, `compile_scenario_runtime_model()`, `admit_instantiated_scenario()`, and the published schema bundle. |
| Module composition/publication | `raes sdl resolve`, the RAES lockfile/trust policy, `raes sdl verify-imports`, and `raes sdl publish` to a temporary OCI layout. Do not add a local resolver, lock format, publisher, or schema copy. |
| Source and loss evidence | `load_qualification()`, `CAGE2_SOURCE_26CE1C1`, the existing strict CybORG source-ledger validator, qualification verifier, and loss disclosures. Do not force the CybORG rows through another backend's incompatible row vocabulary. |
| Scenario pipeline pattern | The parse -> instantiate -> canonical digest -> compile -> admit sequence already centralized in `_scenario_ledger.ScenarioLedger`, while retaining CybORG's existing ledger rules. Reuse the sequence and RAES APIs rather than another scenario parser or target catalog. |
| Runtime planning | `RuntimeManager.plan()`, published provisioning/orchestration/evaluation plans, and the manifest's realization envelope and capability validation. |
| CybORG realization | `CyborgScenarioDescriptor`, `validate_scenario_resources()`, `translate_scenario()`, `CyborgProvisioner`, and `SourceInstalledCyborgDriver`; the qualified native Scenario2 file remains evidence, not a caller-supplied runtime path. |
| Participant/evaluation joins | Existing CybORG participant addresses/action contracts/observation boundaries, compiled evaluation resources, `CyborgParticipantRuntime`, and `CyborgEvaluator`. Consume or prove equality with the compiled scenario declarations; do not maintain an unrelated second objective or participant catalog. |
| Pack admission | `raes-env-packs==3.6.2` validation/release checks, descriptor-confined reads, content-manifest derivation/validation, strict task/spec/participant models, and the existing researcher CLI's scenario digest and artifact joins. |
| Errors and output | Published RAES `Diagnostic`/`ApplyResult`, existing bounded researcher exit mapping, atomic writes, mode-`0700` output confinement, native-stream suppression, and sealed relative inventories. |
| Packaging and workflow | Hatch package resources in the single distribution, one `uv.lock`, existing tests and clean-install distribution probes, and the canonical Nox graph. No new CI workflow or Nox validation family is needed. |

## Realization boundary

The current backend is intentionally narrower than the required document. It
accepts only `network` and `node` provisioning resources, rejects enriched node
services, vulnerabilities, asset values, and other detail, rejects account
placements, maps every Linux/Windows host through two generic images, and emits
fixed participant/session declarations. A full Scenario2 document therefore
cannot satisfy “consumed by the CybORG adapter realization” merely because it
parses, publishes, or passes pack validation.

Acceptance requires the exact canonical scenario to pass the full published
planning and backend-admission path and to reach the existing driver seam in a
dependency-free realization test. Planning diagnostics, `CyborgProvisioner`
validation, and apply/translation must all succeed for the selected Scenario2
facts. The implementation must not obtain that result by deleting SDL sections,
filtering compiled resources before the Provisioner, weakening exact-key checks,
or silently ignoring unsupported detail.

Widen the existing backend-local mapping only for facts it can validate and
materialize through the qualified selected images, sessions, and participant
surfaces. Update the realization envelope, manifest capabilities/constraints,
representability validation, and translation together; a capability claim may
not move ahead of executable evidence. Native image/session names stay behind
the mapping boundary and may not become arbitrary target configuration. The
OS-family fallback is not sufficient for hosts whose selected images carry
different services or vulnerabilities.

Scenario-authored objectives enter through the compiled evaluation plan. The
legacy `cage2_evaluation_plan()` remains only as a fallback for objective-free
generic conformance fixtures; the full Scenario2 path does not use its
`provision.node.user-host` subject. Participant addresses, action contracts,
observation boundaries, and the three-role order remain joined to the authored
surface.

The operational-service proposition is observed through the qualified Blue
availability reward component for `op-server-0`. Its authored evidence
requirement is mapped backend-locally to the existing reward-component source
row, and the driver retains a finite zero availability component so healthy
service state is evidence rather than absence of evidence. Proposition,
assertion, and objective outcomes must be asserted end to end; the presence of
evidence records alone is insufficient.

The specialized Scenario2 projection is selected by the RAES canonical
instantiated-SDL digest and a binding built from the RAES compiler and planner,
not by a second adapter-defined resource-set digest. The binding carries the
compiled provisioning closure, participant action contracts, starting-account
placements, initial knowledge, allowed subnets, observation boundaries, and
objectives. Exact Scenario2-shaped provisioning resources without that binding
fail closed. Native action lists, initial visibility, allowed subnets, and
starting sessions derive from the binding; only the qualified backend mapping
from those portable declarations to native CybORG names remains local.

## Cross-cutting security and operational path

| Layer the artifact passes | Required treatment |
| --- | --- |
| Authentication/authorization | None is introduced: this is public checked-in content and local in-process validation. A future service must reuse RAES strict-default control-plane security; this issue adds no endpoint or caller policy. |
| Secret and signing surface | Accounts contain synthetic intent only—no passwords, credential material, learned access, tokens, secret references, native session ids, or hidden values. CI publication is an unsigned temporary-layout proof; do not read a secret store or pass `--private-key`/private material through argv or environment. |
| SDL parser/semantic shape | Bounded RAES decoding, closed typed construction, semantic validation, instantiation, compilation, and admission own the shape. Unknown fields and invalid references fail closed; no permissive YAML loader or duplicate local validation schema is added. |
| Import/trust shape | `resolve` writes the RAES lockfile; `verify-imports` checks the lock, trust policy, and expansion. Keep Scenario2 self-contained unless a reviewed published module is genuinely reused; never add floating/network/working-directory imports. |
| Source evidence shape | Qualification and ledger validators bind repository, commit, selected path/digest, selector, disposition, and loss. SDL authoring never fetches, imports, or executes upstream source at runtime. |
| Pack/config shape | Pack validation, exact set digest, path confinement, strict JSON loading, canonical scenario digest, task/spec scenario refs, participant refs, seeds, cutoff, and red-variant admission all remain mandatory before output or native construction. No environment variable or free-form metadata overrides these identities. |
| Manifest/plan/result shape | RAES manifest and realization-envelope validators gate advertised support; `RuntimeManager`, `CyborgProvisioner`, participant runtime, and evaluator validate plans and `ApplyResult` transitions. Invalid portable output never becomes a success receipt. |
| OS/process exposure | Validation is in process and reads repo/package resources. CLI arguments contain only public repo/temp paths. Publication writes to a temporary output directory. Native execution retains verified-source snapshotting, private `mkstemp` scenario serialization, immediate unlink, RNG isolation, and no runtime download, shell interpolation, or broad environment forwarding. |
| Errors/observability | Use bounded RAES diagnostics and current stable CLI failures. Never echo rejected SDL/source values, source checkout or absolute native paths, argv/environment dumps, native objects, raw logs, exception causes, stdout/stderr, or tracebacks. No logger or exception hierarchy is added. |
| Persistence/distribution | Checked-in package resources, the RAES lockfile, and pack manifests are the only durable state. OCI layouts and runtime scenarios are temporary. Add no database, cache authority, repository service, `ControlPlaneStore`, second distribution, or lockfile family. |

## Identity, drift, and verification gates

One accepted edit must keep the canonical SDL bytes, pack snapshot bytes,
module/lock metadata, instantiated digest, task/spec scenario references, pack
compatibility asset path, associated-artifact checksum/size, pack set digest,
CLI/test constants, and clean-install probes in agreement. The existing
immutable `CAGE2_SOURCE_26CE1C1` evidence selection and
`CyborgScenarioDescriptor` profile/source/mapping-version fields are the
extension seam: bind the scenario resource and digest to that selected evidence
without turning either identity into the other.

The acceptance gates are cumulative:

- RAES parse/semantic validation, instantiation, canonical digest, compilation,
  and admission;
- `raes sdl resolve`, `raes sdl verify-imports`, and unsigned
  `raes sdl publish` against a temporary staged module/output;
- existing CybORG source-ledger and qualification checks;
- full `RuntimeManager` planning plus Provisioner validation/apply/translation
  of the canonical scenario through a fake driver, including all three subnets
  and exact host membership;
- pack validation/release, exact canonical-to-pack byte equality, all
  cross-artifact joins, and installed-resource presence; and
- the existing canonical `nox -s verify -- --skip-requirement` graph.

A future CAGE scenario or source revision is another explicit immutable
selection and mapping version, not an edit that silently changes this selection,
an environment override, a central simulator registry, or a new SDL schema.

## Gotchas and anti-patterns

- Do not confuse the current `cage2-research` pack name with the Scenario2 SDL
  identity, or the canonical source path with the pack-local snapshot path.
- Do not declare completion from green SDL/pack gates while runtime planning
  still reports accounts unsupported or Provisioner apply still rejects rich
  node detail.
- Do not point the driver directly at the qualified native Scenario2 YAML. The
  runtime remains a deterministic projection of admitted RAES plans.
- Do not copy native image/session/action ids into portable metadata or accept
  them as caller configuration. Keep exact selected mappings backend-local.
- Do not infer all host services from `Internal_image.yaml`; join each consumed
  image fact to its qualified file/selector and retain the User3 port defect.
- Do not duplicate objectives, participant/action addresses, schema pointers,
  parser rules, diagnostics, pack validators, workflow logic, or digest
  algorithms in a second table or helper.
- Do not commit generated OCI layouts, runtime temporary scenarios, native logs,
  hidden truth, reward vectors, source objects, environment/argv dumps, keys, or
  tracebacks.
- Do not add imports or module parameters merely as future-proofing. The selected
  Scenario2 source is fixed; use the existing selection seam for the next case.

## Non-goals and implementation boundaries

- This preflight does not author the SDL, lockfile, pack replacement, runtime
  mapping, tests, or publication output.
- It does not redefine RAES semantics, add a CAGE-specific schema/profile/
  vocabulary, or move backend meaning into `raes_adapters.base`.
- It does not requalify CybORG, change the selected source commit, repair source
  defects, publish a native wheel, or weaken existing loss disclosures.
- It does not add arbitrary scenario/image selection, a generic CybORG YAML
  loader, another simulator abstraction, runtime download, HTTP/API surface,
  authentication flow, secret/signing service, persistence layer, or CI
  workflow.
- A valid, publishable, executable Scenario2 mapping is not deterministic replay,
  state/observation equivalence, outcome equivalence, a replication result, or a
  scientific-validity claim.
