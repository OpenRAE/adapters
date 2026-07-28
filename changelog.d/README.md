# Changelog fragments

This project uses [towncrier](https://towncrier.readthedocs.io/) for changelog
management. **Do not edit `CHANGELOG.md` directly** (outside release-collation
commits).

Add a fragment for every user-visible change as
`changelog.d/<issue>.<type>.md` (or `changelog.d/+<slug>.<type>.md` for
issue-free entries), where `<type>` is one of:

- `security` — security fixes
- `added` — new features / surfaces
- `changed` — changes to existing behavior
- `deprecated` — soon-to-be-removed features
- `removed` — removed features
- `fixed` — bug fixes

The fragment body is a single Markdown bullet's worth of prose (no leading
`-`). Example (`changelog.d/636.added.md`):

```
Stand up the raes-adapters monorepo with Ground Control onboarding and a
strict SonarCloud quality gate.
```

At release time, `towncrier build` collates all fragments into `CHANGELOG.md`
and removes them.
