# raes-adapters

[![Documentation](https://readthedocs.org/projects/raes-adapters/badge/?version=latest)](https://raes-adapters.readthedocs.io/en/latest/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/RAESystem/adapters/badge)](https://scorecard.dev/viewer/?uri=github.com/RAESystem/adapters)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects?as=badge&url=https%3A%2F%2Fgithub.com%2FRAESystem%2Fadapters)](https://www.bestpractices.dev/projects?as=entry&url=https%3A%2F%2Fgithub.com%2FRAESystem%2Fadapters)

A single distribution, **`raes-adapters`**, that qualifies and realizes
[RAES](https://github.com/RAESystem/rae) scenarios against concrete simulator
backends. It ships shared adapter plumbing plus one importable module per
simulator. Implemented simulator dependencies are exposed as optional extras;
qualification evidence bounds the claims made for each selected backend.
Maintainer selection determines admission: a qualification record documents
source identity, attainable evidence, limitations, and claim strength, but it
does not veto implementation of a selected simulator.

RAES — Reproducible Agentic Environments System — is the semantic authority.
Its scope is agentic environments generally: cyber, AI security, AI safety,
testing, research, and evaluation are examples of what an environment can model,
not the boundary of the model. Adapters here translate between a specific
simulator backend and the published RAES contracts; the shared surfaces speak in
participants, observations, actions, resources, controls, evaluation, provenance,
evidence, replay boundaries, and conformance.

This repository hosts the adapter *implementations* and their build/CI mechanics.
It consumes published RAES contracts and never adds SDL, schemas, profiles,
vocabularies, or policy gates of its own (RAES ADR-069 §1). Backend-specific
concepts — including CybORG and CAGE-2 — stay inside the module that owns them
and never define the shared semantic boundary (ADR-002).

## Install

```bash
pip install raes-adapters  # shared base plumbing + qualification evidence
```

The selected CybORG backend is admitted and usable through its documented
source installation. The `cyborg` extra key is dependency-light. Issue
[#12](https://github.com/RAESystem/adapters/issues/12) qualified the official
CAGE Challenge 2 source and a packaging-only fix, but the upstream wheel omits
the version and Scenario2 runtime data. The fixed wheel passed a clean Python
3.12 smoke locally, but it is not a governed public artifact and the
distribution's declared Python/platform range is not yet qualified. Those
limitations bound installability and reproducibility claims; they do not veto
the maintainer-selected backend. Until that fix is published, install the
pinned CAGE-2 source at
commit `26ce1c1253fa9e2e73f25e6a7f2da32860c11257`, apply
`src/raes_adapters/cyborg/cage2-wheel-package-data.patch`, and install its
`CybORG/` package into the environment. The adapter validates the installed
version and selected source-file digests before constructing the backend.
The empty dependency list avoids advertising an editable checkout,
install-time clone, or unpublished wheel as an automatic installation route.

The `cyberbattlesim` extra is likewise dependency-light. The
[qualification record](src/raes_adapters/cyberbattlesim/qualification.json)
binds Microsoft's legally usable, runnable source and admits the selected
profile. Because no official index/release artifact exists, users install the
pinned simulator source separately. Unbound random streams and open benchmark
findings remain explicit limits on deterministic-replay and outcome claims.

## One distribution, optional simulator extras

RAES owns the *contracts* an adapter must honor; how this repository packages,
locks, and releases its code is a local decision (RAES ADR-069 §5 as amended —
see [RAESystem/rae#949](https://github.com/RAESystem/rae/issues/949) — and
[ADR-003](docs/decisions/adrs/adr-003-single-distribution-and-trusted-publishing.md)).
`raes-adapters` is one distribution: `raes_adapters.base` is always installed,
and each simulator is an optional module (`raes_adapters.cyborg`, ...) whose
heavy, mutually-incompatible dependencies live behind an extra. A single
`uv.lock` covers the tree; a future simulator with a conflicting stack is
isolated with uv's `conflicts` extras declaration, not a separate lockfile.

## Shared adapter plumbing

`raes_adapters.base` is available from the base installation and composes the
published RAES APIs directly:

- `build_runtime_target` constructs `raes_runtime.RuntimeTarget` from a
  published manifest and component set, leaving all shape checks to RAES.
- `apply_logical_clock_transition` dispatches a caller-selected transition
  through `ReferenceTimeRuntime`; adapters must explicitly map native events and
  supply exact coordinates.
- `apply_seed_controls` applies an ordered list of published stochastic-control
  bindings through driver-local callables and returns RAES diagnostics for
  applied, unbound, unsupported, and failed controls. Application alone is not
  a replay claim.
- `execute_cleanup` admits a published cleanup plan, runs driver-local
  operations in dependency order, and returns a validated
  `TrialCleanupReceiptModel`. Operations are synchronous and remain responsible
  for native timeout and verification mechanics.
- `project_action`, `project_observation`, and `project_evaluation` provide
  typed direction-specific callable seams. Observation and evaluation outputs
  must pass a caller-supplied RAES validator; native failures never become
  portable fallback values.
- `redact_native_value` is default-deny and never renders arbitrary objects.
  `bounded_context_label` admits only short, grammar-checked, intentionally safe
  labels.
- `run_conformance_probe` returns the exact `BackendConformanceReport` from the
  published RAES target runner without adding profiles, fixtures, cases, or
  claims.

These helpers do not define simulator concepts, portable DTOs, schemas,
backend protocols, diagnostic envelopes, stores, policy gates, or conformance
authority.

## Layout

```text
raes-adapters/
  pyproject.toml               # the raes-adapters distribution (build + deps + extras)
  noxfile.py                   # canonical verification graph
  src/raes_adapters/
    base/                      # shared adapter plumbing (ADR-069 §4)
    cyberbattlesim/            # immutable qualification + selected public protocol
      scenario/                # authored RAES SDL scenario (portable topology/objective truth)
      experiment/              # published experiment contracts (reward/evaluator/stochastic intent)
      mapping/                 # pinned CyberBattleSim → RAES source ledger + loss disclosures
    cyborg/                    # CybORG qualification, patch evidence, and future backend
      mapping/                 # pinned CAGE-2 → RAES source ledger (REP-003)
      profiles/                # conformance profile overrides
  tests/                       # pytest suite for the distribution
  release-please-config.json   # Release Please: versioning + CHANGELOG from main
  .github/workflows/           # CI + PR-title lint + Release Please publish
  docs/decisions/adrs/         # repo-local ADRs (pinned)
```

## Program status

This repository was stood up under **REP-002** (RAES issue #636). Shared
plumbing and the CyberBattleSim backend are implemented; remaining simulator
backends land issue by issue:

| Requirement | Scope |
|-------------|-------|
| REP-001 (#635) | Design: RAES ADR-069 + `cage-2-replication-design.md` |
| **REP-002 (#636)** | **This standup: distribution, CI, GC onboarding, strict Sonar** |
| REP-003 | CAGE-2 RAES SDL scenario + pinned mapping ledger |
| REP-004 | CybORG backend + `raes_adapters.base` implementation |
| REP-005 | Replicated runs + tiered equivalence evidence |

## CyberBattleSim qualification

Issue [#25](https://github.com/RAESystem/adapters/issues/25) selects the
official Microsoft source at commit
`854d6966607fb68645651f55b0f97221bd293e0d` and one public
`CyberBattleChain-v0` protocol with the credential-cache baseline and basic
defender. The shipped
[protocol](src/raes_adapters/cyberbattlesim/public-protocol.md) fixes the exact
scenario, participant, evaluator, seed obligations, metrics, and termination
semantics. The separate
[architecture guardrails](docs/decisions/cyberbattlesim-qualification-guardrails.md)
explain why this evidence is not an adapter manifest or RAES conformance claim.

Issue [#26](https://github.com/RAESystem/adapters/issues/26) authors the
portable evidence set for that case: an authored RAES SDL scenario
(`scenario/cyberbattle-chain.sdl.yaml`) that validates and compiles against
`raes==2.0.0`, companion published experiment contracts
(`experiment/`) for the reward, evaluator, metric, episode/termination, and
descriptive stochastic intent that RAES excludes from SDL, and a pinned
[source → RAES mapping ledger](src/raes_adapters/cyberbattlesim/mapping/) whose
rows are each `mapped`, `excluded`, or `loss-disclosed`, with every disclosed
loss bound to the ADR-069 equivalence tier it weakens. Deterministic tests fail
CI on source drift, a missing category, a duplicate row, an unresolvable target,
a broken cross-artifact reference, an undisclosed loss, or leakage of a known
native identifier or object representation (raw native arrays, reward vectors,
and action ids are excluded structurally by the closed RAES models). The
evidence set does not turn source identity into a claim of dependency
installability, deterministic replay, or outcome equivalence;
the [scenario/ledger guardrails](docs/decisions/cyberbattlesim-scenario-ledger-guardrails.md)
fix its boundaries.

## CyberBattleSim backend

Issue [#27](https://github.com/RAESystem/adapters/issues/27) implements a RAES
runtime target for the admitted size-10 `CyberBattleChain-v0` profile:

```python
from raes_adapters.cyberbattlesim.backend import (
    cyberbattlesim_backend_conformance_payload,
    cyberbattlesim_declared_weaknesses,
    cyberbattlesim_source_protocol_diagnostics,
    run_cyberbattlesim_conformance,
)

report = run_cyberbattlesim_conformance(seed=20260729)
payload = cyberbattlesim_backend_conformance_payload(report)
diagnostics = cyberbattlesim_source_protocol_diagnostics()
weaknesses = cyberbattlesim_declared_weaknesses()
```

Target creation is dependency-light and does not import the simulator.
Provisioning verifies the qualified simulator import-root identity and selected
dependency wheel identities, complete installed import-root trees (including
native libraries and unexpected files),
critical-file digests, dependency versions, and module origins for the directly
imported source, Gymnasium, and NumPy packages before importing and constructing
the separately installed source. The locally built simulator wheel is admitted
by its complete root because upstream publishes no reproducible wheel artifact;
direct Gymnasium/NumPy wheel installs must also match the recorded archive hash.
Editable/directory installations, symlinks, unqualified direct dependency
artifacts, absence, or an identity mismatch become a bounded
RAES diagnostic (and a source-backed conformance probe therefore fails rather
than pretending to run). The
reference processor compiles the checked-in scenario against the manifest, and
the shared target then realizes the applicable provisioning, orchestration,
participant, evaluation, observation, and cleanup surfaces.

One admitted attacker action maps to at most one serialized native `env.step`.
The selected scan-and-reimage defender runs source-internally during that step;
it is not exposed as a second participant-admitted transition.
Native observations, masks, credentials, action coordinates, `info`, reward
vectors, and exceptions remain driver-private. Participant observations and
typed action results carry only RAES references admitted by their disclosure
boundary. Because the representative authored topology cannot identify the
selected native action coordinate, requested targets remain intent and are not
echoed as realized effect targets. Cumulative reward is evaluator-owned. Seed
bindings report the Gym environment and action-space streams as applied and the
Python/NumPy global streams as unbound. These controls improve run attestation
and bound repeatability without claiming byte-identical replay of a stochastic
experiment.

The [backend architecture guardrails](docs/decisions/cyberbattlesim-backend-guardrails.md)
record the component ownership, failure hygiene, capability claims, and
acceptance-test mapping.

Issue [#28](https://github.com/RAESystem/adapters/issues/28) composes that
runtime target with the published RAES conformance report and adapter-local
source-protocol probes. The backend conformance result remains the exact
`BackendConformanceReport` from RAES and is serialized only through the
published report projector. The CyberBattleSim probes add RAES diagnostics,
manifest-derived capability evidence links, source-ledger validation, and
declared weakness references; they do not create another profile, fixture
corpus, report schema, or research-validity claim. The
[conformance-composition guardrails](docs/decisions/cyberbattlesim-conformance-guardrails.md)
fix those boundaries.

## CybORG/CAGE-2 runtime qualification

Issue [#12](https://github.com/RAESystem/adapters/issues/12) selects the
official CAGE Challenge 2 repository at commit
`26ce1c1253fa9e2e73f25e6a7f2da32860c11257`, including its bundled CybORG 2.1,
Scenario2, evaluator, wrappers, and baseline agents as one source closure. The
[qualification record](src/raes_adapters/cyborg/qualification.json) binds the
source and file digests, dependency resolution, legal decisions, known defects,
and sanitized red/blue/green smoke result. The accompanying
[packaging patch](src/raes_adapters/cyborg/cage2-wheel-package-data.patch) is
qualification evidence only; it is not silently applied or published.

Issue [#15](https://github.com/RAESystem/adapters/issues/15) supplies the
provisioning path for that backend. `create_cyborg_target()` accepts
admitted RAES provisioning plans and deterministically generates the native
CybORG scenario: RAES switches become subnets, VM multiplicity becomes hosts,
infrastructure links become subnet membership, and supported OS families select
digest-verified CybORG images. The portable compiled plan entries and
configuration-bound realization-envelope identity remain in the RAES snapshot;
native CybORG objects stay private. Unsupported or lossy node facts fail before
construction.

Issue [#16](https://github.com/RAESystem/adapters/issues/16) adds aggregate
logical-turn execution. A validated blue action is translated by exact contract
address and drives one source-native turn; the resulting blue, green, and red
occurrences are recorded in declared source order with shared-state, joint-action,
and logical-time joins. B-line, Meander, and Sleep red selections and 30/50/100
step limits are admitted through published RAES control contracts. Invalid input
has no native effect, unprojectable post-step output quarantines the session, and
the portable surfaces exclude native action identifiers, reward data, raw logs,
hidden state, and native object representations. Participant-relative observation
and evaluation remain later roadmap work and are not claimed by this manifest.

The separate
[architecture guardrails](docs/decisions/cyborg-cage2-runtime-qualification-guardrails.md)
define the qualification boundary: source installation and known losses limit
strong replay/equivalence claims, but do not veto adapter construction or
permission to retain an honest partial reproducibility record.

## Development

Requires [`uv`](https://docs.astral.sh/uv/). Repo-wide gates run through nox:

```bash
# full verification graph (hygiene, policy, lint, typecheck, tests, build)
uv tool run --from 'nox[uv]==2026.4.10' nox -s verify

# just the tests (base plus all extras)
uv tool run --from 'nox[uv]==2026.4.10' nox -s tests
```

Activate the git hooks on every fresh clone (hooks are not versioned):

```bash
uv run --project . pre-commit install --install-hooks
```

## Releases

`raes-adapters` uses [Release Please](https://github.com/googleapis/release-please):
each push to `main` maintains a release PR that bumps the version and updates
`CHANGELOG.md` from Conventional Commit history. Merging it tags the release and
publishes the wheel and sdist to PyPI over OIDC Trusted Publishing (no stored
token), then opens a `main`→`dev` back-merge PR. Do not hand-edit `CHANGELOG.md`;
carry the release note in the Conventional Commit PR title.

## Cross-repo workflow

Work here is issue-driven from RAES (ADR-069 §8). Adapter PRs reference the RAES
issue, `REP-001`, ADR-069, the design record, the source-ledger id, conformance
profile id, and seed suite. Cross-repo status is read from linked issues, PRs,
conformance reports, and evidence artifacts — not from comments or docs.

## License

MIT — see [LICENSE](LICENSE).
