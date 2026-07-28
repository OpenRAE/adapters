# ADR-002: RAES Authority, ADR Migration, and Adapter Boundaries

## Status

accepted

Supersedes ADR-000 and ADR-001.

## Date

2026-07-28

## Classification

Classification: FM2
Required artifacts: ADR, changelog fragment, whole-tree and distribution
identity verification, installed-distribution verification
Waivers: No compatibility alias, copied contract corpus, local schema or
profile authority, runtime migration service, persistence registry, or new
exception hierarchy is introduced.

## Context

Issue #5 requires one atomic hard cut to RAES as the repository's sole current
identity and semantic authority: the tracked tree, built distributions, and
installed metadata must carry no retired identity in anything this repository
currently asserts.

The existing accepted ADRs contain pinned pre-cutover wording. They are not
current guidance, and they are also not disposable: ADR-000 is the decision that
made accepted ADRs durable and citable in the first place. A cutover that
deleted them to clear a scan would break the guarantee it was enforcing.

Two tracked identities are not owned by this repository and cannot be rewritten
here. The Ground Control project identifier in `.ground-control.yaml` is an
immutable key in an external system of record: `PUT /api/v1/projects/{id}`
updates only `name` and `description`, and every REP-series requirement and
traceability link resolves through that identifier. The requirement-governance
environment variable is a Ground Control workflow contract, emitted from a
single constant to the repository-authored gates of four consuming repositories;
renaming it in this repository alone would leave the gate reading a variable the
workflow never sets, silently degrading requirement governance to a skip. Both
are live external identities, not historical wording, and both are outside the
blast radius a single-repository cutover can safely change.

The governed `raes==2.0.0` distribution already publishes the neutral
contracts, schemas, profiles, fixtures, backend protocols, diagnostics,
conformance runners, runtime security, and persistence interfaces adapters
need. Recreating any of those surfaces here would create a competing
authority.

The cutover also broadens repository framing from one cyber-range replication
to reproducible agentic environments generally. CybORG and CAGE-2 remain valid
backend-specific evidence, but cannot define the shared semantic boundary.

## Decision

RAES is the only current authority. Every relevant independent package declares
an exact direct dependency on `raes==2.0.0` and resolves it from PyPI in that
package's own `uv.lock`. The root project remains tooling-only; there is no
workspace or shared adapter dependency resolution.

Repository code consumes the public owners in `raes_contracts`,
`raes_backend_protocols`, `raes_conformance`, and, when runtime services are
needed, `raes_runtime`. It does not copy or wrap their models into local DTOs,
define another schema or profile registry, fork contract validation, introduce
a parallel diagnostic or exception hierarchy, or treat local fixtures as
portable authority. Adapter-specific probes are additive and report through
RAES diagnostics and conformance reports.

The shared model keeps these concepts distinct:

- authored RAES SDL scenario;
- admitted instantiated scenario and canonical snapshot;
- typed provisioning, orchestration, and evaluation plans;
- backend realization and runtime projections;
- participant implementation and participant-visible observations/actions;
- evidence, derived measures, and bounded conformance or replay claims.

`sim_adapter_base` remains convenience plumbing for simulator adapters. It may
factor transport-neutral target construction, clock/seed control, projection,
redaction hygiene, and conformance-probe composition, but owns none of the
concepts, contracts, schemas, policies, stores, or claims above. CybORG-native
state, identifiers, tuples, rewards, object representations, logs, hidden
truth, process arguments, environment dumps, credentials, and tracebacks stay
behind the CybORG projection boundary.

Portable outputs pass through the RAES closed contract models and semantic
conformance gates. Backend failures use the RAES `Diagnostic` and
`ApplyResult` boundary with bounded, input-free messages; native exception
text, rejected payloads, and tracebacks are not portable output. Any runtime
HTTP surface reuses RAES strict-default authentication, request-size, role,
target, denial-audit, and redacted-error controls. Any durable runtime state
reuses the RAES control-plane store boundary rather than adding a repository
store.

One fail-closed identity policy owns the retired-token matcher. It scans both
tracked path names and file bytes, then reuses the same matcher for wheel and
sdist member names and bytes plus installed distribution metadata. The
canonical verification graph builds and installs every publishable package in
a clean temporary environment outside the source tree, proves current imports
and RAES corpus/conformance access, and proves retired imports are absent. The
matcher and negative-import probes assemble retired spellings from nonmatching
fragments so their own tracked source needs no exemption. The policy has no
path-prefix exemption, directory or generated-file exclusion, compatibility
alias, or changed-files-only mode.

The single exception is the identity register. Following the upstream RAES
migration guide, an entry is admissible only as an exact path, a content digest,
a record class, an owner, a rationale, and an occurrence count, and the gate
fails closed when the digest drifts, when the occurrence count changes, or when
an entry is malformed. The register carries no path prefixes, globs, or
directory exemptions. It admits exactly two record classes:

- `external-identity` — a live identity this repository provably does not own,
  recorded with the condition that retires it. These entries are a closing
  checklist, not a resting place.
- `historical-record` — a decision superseded by this ADR and retained unchanged
  because it accurately records what was decided at the time. These entries are
  permanent, and the retained document must state plainly that it is history
  rather than current guidance.

The two classes are deliberately distinct: an external identity is a debt to be
paid off, while a historical record is an asset to be preserved. Neither may
excuse retired identity in current, owned guidance.

On acceptance, this ADR supersedes ADR-000 and ADR-001 while preserving their
current decisions to use pinned ADRs, keep independent package lockfiles,
compose published conformance, and keep the shared base non-authoritative. The
superseded documents are **retained** in the tracked tree, marked `superseded`
with a pointer to this ADR. Per the ADR governance they leave the pinned index
set, and their content is instead digest-pinned as `historical-record` entries
in the identity register, so the pre-cutover wording they contain cannot drift.

Deleting them was considered and rejected: ADR-000 established accepted ADRs as
durable, content-pinned records, and erasing the very decisions that created
that guarantee to satisfy a name scan would trade the repository's auditability
for a cleaner grep. Relying on git history alone breaks citation from issues,
PRs, and downstream decisions.

Repository-owned service identity is validated through the existing
`check_project_services.py` boundary. Service-side changes must be verified
against the exact repository, documentation, quality, scorecard, package, and
release identities before the cutover is declared complete; repository prose
alone is not evidence of external provisioning.

The extension seam is target discovery, not an identity registry. Verification
enumerates adapter projects from `packages/*/pyproject.toml` and passes explicit
tracked roots or built archives to the one scanner. A future adapter therefore
gets the same identity, build, installation, and isolation checks without a
new validator family, while retaining its own dependency declaration and lock.

## Alternatives Considered

- **Mechanical repository-wide replacement.** Rejected because contracts,
  package metadata, accepted ADR pins, installed imports, generated artifacts,
  and external service bindings have different owners and verification
  boundaries.
- **Delete the superseded ADRs.** Rejected: it satisfies a whole-tree scan by
  destroying the decision record ADR-000 promised to keep, and breaks external
  citation from issues, PRs, and downstream decisions. They are retained, marked
  superseded, and digest-pinned as historical records instead.
- **Blanket-exempt the ADR directory.** Rejected because a directory exemption
  would silently cover every future document; only these two exact files are
  pinned, by digest and occurrence count.
- **Rename the externally-owned identities from this repository alone.**
  Rejected because the Ground Control project identifier is immutable through
  its API and the requirement-governance variable is set by a shared workflow
  constant; a unilateral rename would not produce a working gate, it would
  produce a gate that silently stops enforcing.
- **Widen this change to the four-repository variable rename and a Ground
  Control project migration.** Rejected for this issue: it reverses the
  repository-scoped boundary of #5, and a project migration would move every
  REP-series requirement and traceability link. Tracked instead as the
  register's closing condition.
- **Keep aliases, forwarding imports, or dual-read configuration.** Rejected
  because the cutover is intentionally breaking and ambiguous precedence would
  create validation and input-smuggling risks.
- **Copy RAES models, schemas, fixtures, or validators into this repository.**
  Rejected because the published distribution already owns them.
- **Centralize adapter dependencies in one workspace or lockfile.** Rejected
  because simulator dependency stacks remain independently resolved.

## Non-Goals And Boundaries

- No CybORG backend behavior, CAGE-2 mapping content, authored scenario, or
  replication evidence is implemented by this decision.
- No new RAES semantic concept, contract, schema, profile, fixture corpus,
  manifest format, protocol, conformance claim, or semantic policy gate is
  defined here.
- No automatic rewrite of persisted artifacts, discovery or destruction of
  predecessor host resources, or cross-version data migration is provided.
- No generic adapter persistence service, audit-log authority, runtime identity
  registry, or release credential path is introduced.
- A successful rename, build, test, or conformance run does not by itself prove
  scientific reproducibility, exact replay, backend equivalence, or outcome
  equivalence.

## Consequences

The change is intentionally breaking for distributions, imports,
configuration, workflow identifiers, and metadata. Downstream users must move
atomically to the RAES release and current adapter identities.

Build and clean-install checks become part of the canonical graph, increasing
verification cost but preventing editable source paths from hiding packaging
defects. External services remain separately owned and need explicit
reconciliation evidence.

The repository stays small in semantic scope: backend-specific translation and
projection live in adapters, shared plumbing factors mechanics, and RAES
remains the single portable authority.

Issue #5's zero-retired-identity criterion is therefore met for everything this
repository owns, and explicitly not met for the two registered external
identities. That residue is stated rather than presented as a clean result. It
closes when Ground Control renames the requirement-governance variable across
its four consuming repositories and offers a project-identifier migration; at
that point both entries are removed and the register is empty.
