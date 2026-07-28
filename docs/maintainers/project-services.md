# Project services

The repository-owned configuration for each service lives in the default
branch. Service-side settings must match these identifiers.

- GitHub repository: [`RAESystem/adapters`](https://github.com/RAESystem/adapters)
- Read the Docs project: `raes-adapters`
- PyPI distribution name (reserved, not yet published): `raes-adapters` —
  the root project is virtual and builds no artifact; issue #4 wires up
  publication. Published adapter distributions are `sim-adapter-base` and
  `raes-adapter-cyborg`.
- SonarCloud project key: `RAESystem_adapters`
- OpenSSF Scorecard URI: `github.com/RAESystem/adapters`
- OpenSSF Best Practices lookup: `https://github.com/RAESystem/adapters`

The protected `main` and `dev` branches require `CodeQL`, `Lint PR title`, and
`PR Gate`. Both branches require an up-to-date pull request, dismiss stale
reviews, and prohibit force-pushes and deletion.
