# Developer index

This index is for adapter implementers, contributors, release maintainers, and
repository operators. Researchers should start with the
[README](https://github.com/OpenRAE/adapters#readme) and
[researcher guide](../researcher-guide.md).

## Architecture boundary

RAES owns the published semantic contracts. This repository adapts concrete
simulators to those contracts:

- backend concepts stay under `src/raes_adapters/<simulator>/`;
- `raes_adapters.base` contains composition plumbing, not schemas, profiles,
  backend protocols, diagnostic envelopes, stores, or policy authority;
- portable artifacts exclude native simulator objects, raw logs, hidden truth,
  arguments/environment dumps, tokens, and full tracebacks; and
- accepted repository decisions are recorded under `docs/decisions/adrs/` and
  content-pinned in `adr-index.yaml`.

Start with [ADR-002](../decisions/adrs/adr-002-raes-authority-and-adapter-boundaries.md)
and [ADR-003](../decisions/adrs/adr-003-single-distribution-and-trusted-publishing.md).
Backend design notes under `docs/decisions/` record source-specific evidence
and guardrails; they are authority records, not researcher tutorials.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/raes_adapters/base/` | Shared adapter plumbing over published RAES APIs. |
| `src/raes_adapters/<simulator>/` | Backend implementation, qualification, mappings, profiles, and packaged examples. |
| `tests/` | Distribution and backend behavior tests. |
| `tools/` and `tools/tests/` | Repository policy and project-service checks. |
| `docs/decisions/` | Accepted ADRs plus backend-scoped design/evidence guardrails. |
| `noxfile.py` | Canonical local and CI verification graph. |
| `.github/workflows/` | Parallel PR gates and Trusted Publishing release automation. |

## Local development

Follow [CONTRIBUTING](https://github.com/OpenRAE/adapters/blob/dev/CONTRIBUTING.md)
for environment setup, hooks, change conventions, and backend additions. The
canonical completion command is:

```shell
uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify -- --skip-requirement
```

Use `--skip-requirement` only for genuine requirement-free maintenance. Normal
issue work supplies the governing requirement UID through Ground Control.

The graph runs hygiene, policy, lint, strict typing, tests with coverage,
clean-built distribution probes, and strict documentation. CI runs the same
sessions as independent jobs joined by the `PR Gate`; see
[continuous integration](ci.md) for targeted reproduction commands.

## Packaging and releases

`raes-adapters` is one distribution with optional per-simulator extras and one
`uv.lock`. A mutually incompatible simulator stack is isolated through uv
extras conflicts rather than a second distribution, workspace, or lockfile.

Release Please owns the version and `CHANGELOG.md` from Conventional Commit
history. Trusted Publishing builds and verifies the tagged commit, publishes
through PyPI OIDC, attaches immutable distributions/checksums, and runs the
exact-version public-index smoke. Do not hand-edit the changelog, create a
changelog fragment, store a PyPI token, or silently replace an existing release
artifact. Service identities and workflow boundaries are listed under
[project services](project-services.md).

## Add or change an adapter

1. Keep native imports behind the backend module boundary so the base install
   remains usable.
2. Reuse published RAES contracts and existing repository helpers; do not add a
   local semantic model or shared backend registry.
3. Bind qualification to immutable source evidence and disclose unsupported
   facts or losses rather than promoting them through static claims.
4. Add behavioral tests at the narrowest boundary and extend the clean-wheel
   proof for installed behavior.
5. Update researcher documentation when a command, output, support statement,
   limitation, or evidence interpretation changes.
6. Add or amend an ADR only for a durable repository decision; regenerate the
   ADR pin in the same change.

## Governance and services

- [Contribution guide](https://github.com/OpenRAE/adapters/blob/dev/CONTRIBUTING.md)
- [Continuous integration](ci.md)
- [Project services](project-services.md)
- [ADR overview](../decisions/adrs/README.md)
- [Repository issue tracker](https://github.com/OpenRAE/adapters/issues)
