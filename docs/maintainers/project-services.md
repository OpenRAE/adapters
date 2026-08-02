# Project services

The repository-owned configuration for each service lives in the default
branch. Service-side settings must match these identifiers.

- GitHub repository: [`OpenRAE/adapters`](https://github.com/OpenRAE/adapters)
- Read the Docs project: `raes-adapters`
- PyPI distribution name: `raes-adapters` — the single published distribution
  (shared base plumbing plus optional per-simulator extras, e.g.
  `raes-adapters[cyborg]`). It is built and published from `main` by Release
  Please; the root project is the distribution, not tooling-only.
- PyPI Trusted Publisher workflow: `release-please.yml`
- PyPI environment: `pypi`
- SonarCloud project key: `RAESystem_adapters`
- OpenSSF Scorecard URI: `github.com/OpenRAE/adapters`
- OpenSSF Best Practices lookup: `https://github.com/OpenRAE/adapters`

Publication uses PyPI Trusted Publishing over GitHub OIDC (no stored API token):
configure the `raes-adapters` Trusted Publisher for repository
`OpenRAE/adapters`, workflow `release-please.yml`, and environment `pypi`.

Provision a `RELEASE_PLEASE_TOKEN` repository secret — a GitHub App installation
token or a fine-grained PAT with `contents` + `pull-requests` write — so the
Release Please and `main`→`dev` back-merge PRs trigger the required checks
(`PR Gate`) instead of needing an administrative merge. The workflow falls back
to the built-in `GITHUB_TOKEN` when the secret is absent, but that path relies on
an admin merge and should not be the steady-state release process.

The protected `main` and `dev` branches require `CodeQL`, `Lint PR title`, and
`PR Gate`. Both branches require an up-to-date pull request, dismiss stale
reviews, and prohibit force-pushes and deletion.
