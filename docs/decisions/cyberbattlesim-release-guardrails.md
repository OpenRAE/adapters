# CyberBattleSim first-release guardrails

GitHub issue #31 is the authority for this release. This note specializes
[ADR-003](adrs/adr-003-single-distribution-and-trusted-publishing.md) for the
first published CyberBattleSim profile. It defines no package, pack, release,
profile, evidence, attestation, or rollback schema and is not an implementation
plan.

## Release blocker: the documented short path is currently inadmissible

The current `cyberbattlesim-chain` task requires `attacker-action-log` and
`availability-series` evidence. RAES 3.3 cannot validate the required
artifact-and-field witness, so `_task_capture_admission_gaps()` deliberately
rejects both `validate` and native `run` before output reservation or simulator
effects. The clean-installed distribution probe requires that exit-3 rejection,
and the researcher documentation assigns the remediation to issue #86.

Issue #31 cannot satisfy “one short episode” while this remains true. The
capture/manifest remediation and its published RAES owner must land before the
release, or issue #31 remains blocked. Do not weaken the authored task, add a
static evidence-reference allowlist, bypass the task/run validator, relabel a
conformance probe as an episode, or resurrect evidence that the current
manifest cannot witness.

## Keep the released identities distinct

One release joins, but never conflates, these authorities:

- the `raes-adapters` distribution version, Release Please tag, wheel, sdist,
  PyPI attestations, and distribution checksums;
- the external `cyberbattlesim-chain` pack name/version, source and release-view
  assets, content digest, and `ENV_PACK_SHA256SUMS`;
- the adapter manifest and RAES-supported profile resolved from the installed
  wheel; and
- the separately installed qualified CyberBattleSim source commit, version,
  complete import-root digest, selected-file digests, dependency artifacts, and
  module origins from `qualification.json`.

`raes-adapters[cyberbattlesim]` intentionally installs the pack validator, not
the native simulator: upstream publishes no governed index or release artifact.
A public-index install can prove the adapter extra and resolve the qualified
source/profile declaration. `native_available=true`, conformance against the
real driver, and a short episode additionally require the separately acquired
qualified native wheel to pass the existing source-admission checks. Do not
claim that the extra installs CyberBattleSim, add a floating VCS/direct URL, or
silently publish the locally qualified native wheel as part of this release.

## Canonical incumbents

| Concern | Required owner and reuse |
| --- | --- |
| Version, changelog, tag, and branch topology | `release-please-config.json`, `.release-please-manifest.json`, `.github/workflows/release-please.yml`, Conventional Commit PR titles, and the reviewed `dev`→`main` promotion / `main`→`dev` back-merge. Do not add another release workflow or hand-edit `CHANGELOG.md`. |
| Distribution and extras | `pyproject.toml`, the single `uv.lock`, ADR-003, `_extras()`, `_verification_envs()`, and `_distributions()`. Build one distribution and test base plus every extra separately; never use `--all-extras` as the isolation proof. |
| Release-policy validation | `tools/check_project_services.py` and its tool tests. Extend this validator for enforceable workflow invariants instead of adding a release-policy checker. |
| Package artifact validation | The canonical `verify` graph, reproducible `uv build`, `twine check --strict`, `probe_installed_identity.py`, installed console scripts, and archive/installed-metadata identity scanning. Inspect both wheel and sdist contents, metadata, README rendering, package data, root license, and notices applicable to what each artifact redistributes. |
| Source and profile resolution | `load_qualification()`, `CYBERBATTLE_CHAIN`, `create_cyberbattlesim_manifest()`, `backend_manifest_payload()`, `backend_profiles_root()`, `load_backend_profile()`, `cyberbattlesim_inspection_payload()`, and `_source_admission`. Derive identities from these owners; do not copy a profile list or source constants into workflow code. |
| External pack | The checked-in pack, `pack.yaml`, `pack.content-manifest.json`, `pack.compatibility.yaml`, the provenance ledger, `raes-pack-validate`, `raes-pack-release check/build`, and `verify_pack_content_digest()`. The pack remains outside wheel/sdist and is acquired only as checksum-bound assets from the same immutable release. |
| Installed run and conformance | The closed `raes-adapters` parser and `_BackendAdapter` registration, confined pack resolution, strict JSON loading, RAES SDL and contract models, participant joins, `_task_capture_admission_gaps()`, `RuntimeManager`, the real `CyberBattleSimDriver`, canonical conformance report projection, and verified cleanup. |
| Portable evidence and integrity | `atomic_write_json_artifact()`, exclusive mode-0700 relative outputs, RAES evidence/run/study models and cross-artifact validators, supplemental-artifact checksum binding, inventory-last sealing, the CyberBattleSim structural leakage checks, and source-ledger native markers. Validate actual serialized files; do not treat a checksum alone as semantic or leakage validation. |
| Failure and observability | Stable CLI exit codes and `_CommandFailure` messages, RAES `DiagnosticModel`, canonical report projection, `redact_native_value()`, and bounded context labels. Native output, exception text, argv/environment mappings, paths, credentials, observations, actions, reward vectors, hidden state, and tracebacks never become release evidence or logs. |
| Release evidence and recovery | GitHub Release distribution/pack checksum assets, PyPI PEP 740 attestations, the release notes, and an append-only update to `cyberbattlesim-native-readiness-record.md` with observed public-install identities and dispositions. A bad release is yanked and superseded; tags, versions, releases, and assets are never overwritten or reused. |

## Publication boundary

Publication is irreversible, while a public-index smoke necessarily runs after
publication. All preventable failures therefore belong before the OIDC publish:
the exact released commit and tag/version join, canonical verification, two
independent builds with byte-equal wheel/sdist results, strict metadata/README
validation, archive content and legal-attribution inspection, clean installed
imports and entry points, per-extra dependency isolation, local pack release
gates, and a real-native rehearsal once the task evidence blocker is closed.

The publish job receives only those validated artifacts. It retains the
protected `pypi` environment and job-local `id-token: write`; the build and smoke
jobs get no publishing identity. `skip-existing` and asset clobbering remain
forbidden. PEP 740 attestations and checksums attest bytes and provenance, not
profile support, leakage safety, conformance, or scientific validity.

After publication, install the exact version from the public index in a clean
supported environment with no checkout or local link. Separately admit the
qualified native source; acquire both pack archives and their checksum manifest
from the same release; verify asset checksums, pack content identity, and pack
release gates; then run installed inspection, real-source conformance, the
documented short episode, RAES model/task joins, inventory verification,
structural leakage checks, and cleanup verification. A failure here makes the
release failed readiness evidence and invokes yank/supersede guidance; it must
not be reported as a successful release merely because upload succeeded.

The apparatus-readiness relationship to `OpenRAE/research#14` is a governed
cross-repository issue link, not a new credential scope for the publishing
workflow. Likewise, the `main`→`dev` resynchronization remains a normal reviewed
PR whose required checks pass; release automation must not merge it, force-push,
or rely on an administrative bypass as the steady-state path.

## Cross-cutting security path

| Layer the design passes | Required treatment |
| --- | --- |
| Authentication and authorization | Release Please uses only its contents/PR token; PyPI publication uses OIDC in the protected `pypi` environment; GitHub Release attachment uses the job token. No token is accepted by the adapter command or written to argv, artifacts, checksums, logs, or readiness evidence. Cross-repository linking remains outside the publisher identity. |
| Secret and environment binding | No PyPI API token, native credential, `.env`, home secret/cache, or environment-selected source/profile is an input. Keep action checkout credentials disabled. Native subprocesses, if used for the manual/public smoke, inherit a small allowlisted environment with cleared `PYTHONPATH` and safe-path behavior; never dump the environment. |
| Static configuration and parsers | Release Please config/manifest, exact version/tag validation, `pyproject.toml`, frozen lock resolution, pack validators/digest checks, the closed CLI parser, confined child paths, duplicate-key-rejecting JSON, RAES SDL/contracts, participant joins, manifest/profile validation, and source qualification all fail closed before effects. |
| Runtime and portable-result validators | `RuntimeManager` and target component validators, participant action/result/history joins, evaluator models, task/run and study joins, cleanup receipts, canonical conformance serialization, inventory recomputation, model validation, and leakage scanning must all pass. Missing/unavailable/withheld/unsupported is not success. |
| OS/process exposure | Use isolated temporary working directories, exclusive relative outputs, argument vectors rather than shell interpolation, bounded public downloads, no runtime source discovery, no checkout on the public-index proof, cleared `PYTHONPATH`, `PYTHONSAFEPATH=1`, suppressed native stdout/stderr, and no host path in portable files. |
| Error envelopes and logging | Emit only bounded codes, safe public identities, counts, and dispositions. Do not echo rejected tag/config values before shape admission, native exceptions, raw tool output containing private values, object representations, environment/argument maps, absolute paths, or tracebacks. |
| Persistence and publication | GitHub/PyPI artifacts and the existing readiness record are the only durable release evidence. The pack and run inventories are checksum indexes, not stores. Do not add a database, cache, evidence registry, mutable “latest” artifact, or second release ledger. |

## Extension seam

The release workflow should resolve the existing authorities once into job
outputs: distribution tag/version from Release Please and pack root, name,
version, content digest, and generated asset names from the validated pack. Pass
those values through build, publish, public acquisition, and evidence output;
do not add a release-descriptor file or schema. Source/profile identity remains
derived at runtime from the installed qualification and manifest. Do not repeat
`cyberbattlesim-chain-1.0.0`, its digest, or a profile id independently across
workflow steps, docs, and tests. A future external pack or revised pack version
should change its canonical pack metadata, not require copying a new set of
release commands.

Per-extra verification remains data-driven by `_extras()`. Adding the next
simulator extra must automatically retain base and unrelated-extra coverage and
honor any explicit uv `conflicts` declaration without editing a CyberBattleSim-
specific combined environment.

## Gotchas and anti-patterns

- Do not confuse locally built artifact rehearsal, public-index installation,
  native-source admission, profile resolution, pack validation, conformance, a
  short episode, cleanup, leakage safety, apparatus readiness, and scientific
  reproduction. Each is a separate disposition.
- Do not let a post-publish retry install an unpinned later version, use a local
  wheel fallback, or download pack assets from a different tag.
- Do not make “reproducible” mean only setting `SOURCE_DATE_EPOCH`; build twice
  in independent roots and compare the wheel and sdist bytes.
- Do not validate only the wheel. The sdist, installed metadata, console entry
  point, package resources, external pack assets, checksums, and applicable
  license/notice material are independent failure surfaces.
- Do not scan only raw text or only checksums. Recompute inventories, validate
  JSON through the published RAES models and joins, and apply the existing
  structural/native-marker leakage gates to the serialized portable tree.
- Do not publish raw simulator output, the native wheel, source archives,
  credentials, host/provider metadata, or private scratch as release evidence.
- Do not hard-code an optimistic support table. Render claims from the admitted
  qualification/manifest/pack facts and preserve the no-index-artifact,
  incomplete-random-stream, benchmark-defect, platform, and non-equivalence
  limitations.
- The workflow currently points to missing `docs/maintainers/releasing.md`.
  Put first-release prerequisites, public-smoke evidence, yank/supersede, and
  partial-publication recovery in that existing intended runbook location; do
  not create competing release instructions.
- The manual-dispatch tag check must validate the complete tag grammar, not rely
  on a permissive shell glob, before using or logging the value. Pin adversarial
  cases in `tools/check_project_services.py` tests.

## Non-goals and boundaries

Issue #31 does not add a RAES schema, conformance profile, fixture corpus,
capability/evidence vocabulary, diagnostic or exception hierarchy, source
qualification, native simulator distribution, environment-pack schema, second
Python distribution, lockfile, release workflow, publisher credential, HTTP
surface, controller, repository/store, or runtime download feature.

It does not make the pack golden, establish deterministic replay, state or
observation equivalence, outcome equivalence, benchmark comparability, or
scientific validity. It does not close `OpenRAE/research#14`, merge protected
branches, or make an uploaded version safe to overwrite.
