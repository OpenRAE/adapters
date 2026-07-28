# raes-adapters plan rules

Mandatory constraints the `/implement` skill applies during the plan phase.

- Plans MUST run the canonical verification graph before declaring completion:
  `uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify`.
- Plans MUST set `ACES_REQUIREMENT_UID` (or use a branch containing a UID such
  as `REP-004`) so requirement governance passes; use `--skip-requirement` only
  for genuine requirement-free maintenance work.
- Plans MUST keep each adapter under `packages/` independent: its own
  `pyproject.toml` and `uv.lock`. Plans MUST NOT introduce a global adapter
  lockfile or a uv workspace (RAES ADR-069 §5).
- Plans that add an adapter MUST add its CI matrix row in
  `.github/workflows/ci.yml` and its `src`/`tests`/`coverage.xml` paths in
  `sonar-project.properties`.
- Plans MUST NOT add CAGE-specific SDL, schemas, profiles, vocabularies, or
  policy gates; adapters consume RAES published contracts (RAES ADR-069 §1).
- Plans MUST keep `sim_adapter_base` free of semantic/protocol/authority
  definitions (RAES ADR-069 §4).
- Plans MUST NOT leak native simulator objects, raw logs, hidden truth, tokens,
  or full tracebacks into portable RAES artifacts (RAES ADR-069 §3).
- Plans with a user-visible change MUST add a fragment under
  `changelog.d/<issue>.<type>.md` (or `changelog.d/+<slug>.<type>.md` for
  issue-free entries); do not edit `CHANGELOG.md` directly.
- Plans that add or amend an accepted ADR MUST update `adr-index.yaml` pins in
  the same change (`tools/check_adr_immutability.py --update`).
