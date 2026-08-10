# CybORG/CAGE-2 packaged example guardrails

GitHub issues #21 and #77 are the authority for this requirement-free
deliverable. The issue threads supersede the original proposal for an editable
`environments/cyborg-cage2/` tree: reusable pack source belongs in its owning
federated catalog, while this repository retains adapter realization and
backend-native evidence and consumes released pack identity. The concrete scope
here is the existing installed, digest-sealed `cage2-research` snapshot under
`raes_adapters.cyborg`.

This note fixes ownership, identity, validation, security, packaging, and claim
boundaries. It defines no environment-pack, SDL, experiment, participant,
adapter, evidence, or release schema and is not an implementation plan.

## Scope correction and semantic authority

The installed example began as the bounded researcher smoke surface created by
issue #20. Issue #77 replaces that placeholder with the full reviewed CAGE
Challenge 2 Scenario2 portable projection, keeps the canonical authored module
beside the adapter, and reseals the byte-identical pack snapshot as version
2.0.0. The selected source remains the qualified source closure rather than
legacy RAESystem/rae#637 content copied or reinterpreted without evidence.

- RAES owns SDL, experiment, participant, associated-artifact, runtime, and
  conformance semantics.
- `raes-env-packs==3.6.2` owns pack schemas, templates, validation, release
  boundaries, leak checks, and content identity.
- `raes_adapters.cyborg` owns simulator source admission, translation,
  execution, projection, qualification, and installed example realization.
- `RAESystem/env-packs` remains format/tooling-only and receives no scenario
  content.
- This repository does not add a top-level competing editable pack or claim
  first-party catalog authority.

The NASim `nasim-tiny` example is a useful format precedent for the published
compatibility manifest and golden checklist. Its simulator semantics, attacker
model, native dependency, status evidence, and claims are not CybORG authority.

## Identity and drift boundary

Keep these identities distinct:

- pack name/version from validated `pack.yaml`;
- associated-artifact manifest id and set digest;
- SDL artifact path and instantiated semantic digest;
- experiment, task, and participant contract identities and digests;
- qualified CAGE repository/commit/tree/file identities;
- adapter distribution/version and backend profile;
- run/study ids and evidence inventory identity; and
- local package-resource path, which is only a locator.

Every checked-in pack member is covered by `pack.content-manifest.json`.
`derive_pack_content_manifest()` recomputes byte digests, sizes, and the set
digest; `validate_pack_content_manifest()` and the researcher command bind the
declared bytes before planning or execution. The same set digest must appear in
tests, the clean-install distribution probe, and the researcher walkthrough.

A self-consistent manifest proves current snapshot identity, not state,
observation, or outcome equivalence with the native source. Issue #77 supplies
the reviewed Scenario2 replacement content; the pack retains explicit
non-claims because apparatus completeness is not a replication result.

## Compatibility, provenance, and release boundaries

`pack.compatibility.yaml` is static publication metadata, not backend
configuration. It may identify a supported qualified runtime profile and
provider distribution, but it must not select a driver class, native source
path, patch, wrapper, import root, action id, or target configuration.

The release boundary is disjoint:

- participant-visible: portable SDL, experiment/task inputs, and bounded
  concepts/activity documentation;
- operator-only: participant manifest/selection/configuration, provenance and
  licensing review, and the golden-readiness checklist;
- restricted/oracle and commercial: empty unless real content and an explicit
  publication decision later justify them.

The provenance ledger records the qualified CAGE source and evaluation material,
referenced research context, RAES contract input, adapter-authored content,
manifest generation, redistribution/attribution duties, and explicit
exclusions. It does not copy RAES schemas or source-ledger validators and does
not redistribute paper content or native CybORG bytes.

Status follows evidence:

- `draft`: static content without an exercised reference realization;
- `built`: the current packaged example, whose installed command, automated
  rehearsal, digest admission, cleanup, and portable evidence surfaces exist;
- `golden`: only after the full manual checklist and the stronger Scenario2
  conditions it names have actually been proven.

Unchecked golden-checklist boxes are plans, not evidence.

## Canonical incumbents

| Concern | Reused owner |
| --- | --- |
| Pack validation/release | `raes-pack-validate`, `raes-pack-release check`, `validate_pack()`, manifest derivation/validation, and the published compatibility/provenance schemas. |
| RAES artifacts | Strict SDL, experiment/task, participant, associated-artifact, diagnostic, runtime, run/study, and evidence models from pinned `raes==3.3.0`. |
| Source evidence | `qualification.json`, `cage2-source-ledger.jsonl`, loss disclosures, source-ledger validation, and exact-source qualification. |
| Runtime admission | Researcher CLI dispatch, `RuntimeManager.plan()`, `RunControls`, CybORG target/driver/provisioner/participant/evaluator surfaces, and verified cleanup. |
| Errors/output | Existing stable exit mapping, bounded diagnostics, atomic artifact writes, mode-`0700` relative output confinement, native stream suppression, and final inventory sealing. |
| Packaging/workflow | One `pyproject.toml`, one `uv.lock`, Hatch package resources, clean-install archive probes, and the canonical Nox verification graph. |

No new helper, schema, registry, exception hierarchy, store, command assembler,
workflow, or `raes_adapters.base` semantic surface is needed.

## Security and operational gates

Before native construction, the existing stack must continue to enforce:

- strict descriptor-anchored pack reads and exact content-manifest digest;
- closed RAES model validation and exact scenario/task/spec/participant joins;
- published participant/operator release partitioning and participant leak scan;
- qualified source tree, selected-file, and module-origin verification;
- no ambient driver, source, patch, seed, participant, or control selection;
- no secret, credential, `.env`, arbitrary import, runtime download, or shell
  interpolation;
- bounded errors with no rejected values, absolute paths, argv/environment,
  native values, raw logs, exception causes, or tracebacks;
- unique invocation-relative output roots, validated atomic writes, no
  force/resume/append, and a relative final inventory.

The example may expose stable objective ids and a participant-safe overview. It
must not expose native state, hidden truth, action ids/classes, reward vectors,
operator controls, evaluator answers, source checkout details, or next-step
hints in participant-visible artifacts.

## Extension seam and non-goals

Future Scenario2 revisions must use another reviewed pack version and set
digest. They must update authored artifacts and identity data without modifying
pack schemas, adding CAGE-specific SDL, changing adapter dispatch, or weakening
current validators.

This issue adds no emulator, cloud range, web service, daemon, scoreboard,
training framework, plugin loader, runtime downloader, credential flow,
deterministic-replay claim, state/observation/outcome equivalence claim,
replication result, or scientific-validity claim. It does not create catalog
content, a second distribution or lockfile, or a new semantic authority in this
repository.
