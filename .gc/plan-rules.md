# raes-adapters plan rules

Mandatory constraints the `/implement` skill applies during the plan phase.

- Plans MUST run the canonical verification graph before declaring completion:
  `uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify`.
- Plans MUST set `ACES_REQUIREMENT_UID` (or use a branch containing a UID such
  as `REP-004`) so requirement governance passes; use `--skip-requirement` only
  for genuine requirement-free maintenance work.
- Plans MUST keep `raes-adapters` a single distribution: one `pyproject.toml`
  and one `uv.lock`. A simulator whose stack is mutually incompatible with
  another's MUST be isolated with uv's `[tool.uv] conflicts` extras declaration,
  NOT a second lockfile or a uv workspace (ADR-003; RAES ADR-069 §5 as amended,
  RAESystem/rae#949).
- Plans that add a simulator MUST add it as a module under
  `src/raes_adapters/<simulator>/` with an optional extra in `pyproject.toml`;
  `src`/`tests` are already the SonarCloud roots, so no
  `sonar-project.properties` change is needed.
- Plans MUST NOT add CAGE-specific SDL, schemas, profiles, vocabularies, or
  policy gates; adapters consume RAES published contracts (RAES ADR-069 §1).
- Plans MUST keep `raes_adapters.base` free of semantic/protocol/authority
  definitions (RAES ADR-069 §4).
- Plans MUST NOT leak native simulator objects, raw logs, hidden truth, tokens,
  or full tracebacks into portable RAES artifacts (RAES ADR-069 §3).
- Release Please owns `CHANGELOG.md` and the version. Plans MUST NOT edit
  `CHANGELOG.md` by hand or add `changelog.d/` fragments; the release note is the
  Conventional Commit PR title.
- Plans that add or amend an accepted ADR MUST update `adr-index.yaml` pins in
  the same change (`tools/check_adr_immutability.py --update`).
