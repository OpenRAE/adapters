# ADR-003: Single `raes-adapters` Distribution and Trusted Publishing

## Status

proposed

This decision becomes eligible for acceptance after the Release Please dry run
and the external PyPI name, owner, environment, and Trusted Publisher checks
below have evidence. Until then, repository prose is not proof that a PyPI name
is reserved or that a publisher is configured.

## Date

2026-07-28

## Classification

Classification: FM2
Required artifacts: ADR
Waivers: this ADR records the packaging and release boundary; the concrete
credential, first PyPI project, and distribution upload are operational evidence
produced by issue #4's implementation and the first release.

## Context

Issue #4 adopts Release Please for versioning and changelog management and
publishes this repository to PyPI. It also settles the packaging model.

RAES ADR-069 §5 additionally prescribed the *packaging topology* of this
repository — a monorepo of independent adapter projects, one lockfile and
virtualenv each, no shared lock, and a specific CI matrix. That is a downstream
implementation detail, not a RAES contract. RAES owns the contracts an adapter
must honor (§1 authority, §3 backend-protocol conformance, §4 the shared base is
plumbing not authority, and no simulator-private leakage); it should not dictate
how an adapter repository packages, locks, or releases. There will be many
adapter repositories — public, private, separate — and only some published. The
§5 packaging mandate is amended upstream (RAESystem/rae#949); this ADR records
the local decision that follows.

## Decision

### 1. One distribution, optional per-simulator extras

`raes-adapters` is a single published distribution. `raes_adapters.base` is the
always-installed shared plumbing; each simulator is an optional module
(`raes_adapters.cyborg`, ...) whose dependencies are an extra
(`raes-adapters[cyborg]`). One `pyproject.toml` and one `uv.lock` own the tree.
`[project].version` is canonical; `raes_adapters.__version__` derives from
installed distribution metadata and is never an independently edited authority.

The isolation §5 sought is preserved as an *outcome*, not a mechanism: a
simulator with a mutually-incompatible stack is separated with uv's `conflicts`
extras declaration so it cannot gate another simulator in the single lock. This
replaces per-adapter lockfiles without reintroducing a workspace or a lock
shared across unrelated repositories. The root project is the distribution;
there is no separate tooling-only virtual project and no umbrella/meta-package
over other distributions.

### 2. Release Please owns versioning and the changelog

Release Please (release-type `python`, single component `.`, package
`raes-adapters`, tags `vX.Y.Z`) is the sole version and release-note controller.
It maintains a reviewed release PR on `main`, bumps `[project].version`, and
updates `CHANGELOG.md` from Conventional Commit history. Towncrier, its
fragments, template, dependency, and the hand-edited changelog are removed in the
same cutover; there is no second release-note authority.
`tools/check_pr_title.py` validates the Conventional Commit shape
(type / optional scope / breaking marker / lowercase subject) so history drives
correct versions; it does not compute versions.

### 3. Build, validation, and publication boundary

Build and publish are separate jobs. The build job checks out the exact released
commit (`persist-credentials: false`), builds a reproducible wheel and sdist with
a fixed `SOURCE_DATE_EPOCH`, validates metadata and README rendering, records
SHA-256 checksums, and hands only those files to the publish job. The publish job
uses the protected `pypi` GitHub environment with job-local `id-token: write` and
no broader write, downloads the validated artifacts, and invokes the
full-SHA-pinned official PyPA publishing action over OIDC Trusted Publishing. No
PyPI username, password, or API token is stored; PyPA publish attestations
(PEP 740) are produced by default.

Retries fail closed: `skip-existing` is not used, so a duplicate or conflicting
upload is a hard stop, never a silent success that masks a partial or repeated
release. A post-publish smoke job installs the exact released version from the
public PyPI index into a clean environment and exercises the public imports. A
bad release is yanked and superseded by a higher version; tags, releases, and
uploaded files are never overwritten or reused.

### 4. Protected-branch topology

The Release Please action runs only on pushes to protected `main`, maintains a
reviewed release PR, and creates tags and Releases only after that PR merges.
Feature PRs merge to `dev`; the `dev`→`main` promotion uses a merge commit so the
Conventional Commit subjects Release Please reads survive. After a release,
automation opens one normal `main`→`dev` back-merge PR and never merges it,
force-pushes, or rewrites a protected branch.

### 5. Validation ownership

`tools/check_project_services.py` remains the single repository-service
validator. It is extended to check the Release Please config, manifest, and
workflow boundary (OIDC-only, protected `pypi` environment, full-SHA action pins,
no stored token, no silent `skip-existing`); no second release-config validator
is added. The `noxfile.py` `distributions` session remains the
build / clean-install / identity proof, now over the single distribution.

## Alternatives Considered

- **Keep the ADR-069 §5 per-adapter monorepo.** Rejected: §5's packaging mandate
  over-reaches into a downstream repo; RAES owns contracts, not packaging
  (amended in RAESystem/rae#949). A single distribution fits a repo with one
  published adapter and a shared base far better than N lockfiles.
- **Per-adapter distributions.** Rejected: multiplies PyPI projects, Trusted
  Publishers, and release ceremony for no benefit at this scale; extras give the
  same optionality under one name.
- **Umbrella meta-package over separate distributions.** Rejected: the adapters
  are not independently published, so an umbrella would depend on unpublished
  projects.
- **One global lock / uv workspace across simulators.** Rejected: incompatible
  simulator stacks would gate one another. uv `conflicts` extras isolate them in
  the single lock without that coupling.
- **Stored PyPI API token.** Rejected in favor of OIDC Trusted Publishing.
- **`skip-existing` for retries.** Rejected: it can turn a partial or conflicting
  upload into an apparent success.

## Non-Goals And Boundaries

- No adapter runtime behavior, RAES contract, backend protocol, schema,
  conformance profile, fixture, diagnostic envelope, or simulator mapping is
  defined here.
- No compatibility alias, forwarding import, or retired distribution is
  published.
- Release Please does not publish to PyPI, manage rollback, or reconcile
  branches; those stay explicit workflow and maintainer boundaries.
- Publication proves package identity, artifact integrity, installability,
  provenance, and release-process conformance only — not scientific
  reproducibility or backend equivalence.

## Consequences

The repository publishes one unambiguous distribution with a single version,
changelog, tag, artifact set, provenance chain, and PyPI identity. Adding a
simulator is one module plus one extra (and, if needed, one `conflicts` entry),
not a new project, lockfile, and CI-matrix row. The cost is a stricter release
boundary — lock freshness, reproducibility, metadata completeness, attestation,
public-index verification, and back-merge review — and a first-publication
dependency on the external `raes-adapters` Trusted Publisher, which a pending
publisher claims but does not fully reserve until first upload.
