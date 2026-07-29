# CyberBattleSim → RAES mapping ledger

**Authored under RAESystem/adapters#26.** This directory is backend-local
traceability evidence for the selected public CyberBattleSim case. It records
how each pinned upstream source fact reaches a portable RAES surface — the
authored SDL scenario or a published experiment contract — or why it does not.
It follows the CybORG mapping directory's module-local ownership *pattern*; it
does not copy CAGE field names, and neither ledger is generalized into
`raes_adapters.base`.

Per RAES ADR-069 and `docs/decisions/cyberbattlesim-scenario-ledger-guardrails.md`,
the mapping is a **pinned ledger** over the immutable source identifiers already
recorded in [`../qualification.json`](../qualification.json). It is package data,
not a public DTO, schema, profile, vocabulary, or semantic contract.

## Files

- `source-ledger.jsonl` — one JSON object per source fact. Fields:
  - `source_id` — stable, unique row identity.
  - `source_repo`, `source_commit`, `source_path`, `source_selector` — immutable
    upstream coordinate and the symbol/path the fact comes from.
  - `source_digest` (optional) — the file SHA-256; when present it must join the
    matching `qualification.json` `source_files` entry (offline source-drift
    check — CI never fetches a floating branch or executes CyberBattleSim).
  - `category` — one of the required coverage categories (see below).
  - `disposition` — exactly one of `mapped`, `excluded`, `loss-disclosed`.
  - `raes_target` (mapped rows) — a portable surface reference that must resolve
    to an authored artifact element (`sdl:<section>[.<key>]`,
    `resource:<package-file>`) or a published contract property path
    (`contract:<ContractModel>.<property.path>` in
    `raes_contracts.contracts.schema_bundle()`). No second target catalog is
    maintained.
  - `loss_ref` + `equivalence_tier` (loss-disclosed rows) — the disclosure id in
    `loss-disclosures.md` and the ADR-069 tier it weakens.
  - `mapping_rule` — the mapping or exclusion rationale.
  - `verification` — how the fact was checked.
- `loss-disclosures.md` — narrative disclosures for source facts RAES cannot
  carry exactly, each bound to the equivalence tier it weakens.

## Required coverage categories

Every category must appear at least once, or CI fails: `topology-state`,
`identities`, `participants`, `actions`, `observations`, `controls`,
`rewards-objectives`, `termination`, `evaluator`, `stochastic`, and
`provenance-licensing`.

## Governance

Every upstream source fact is `mapped`, explicitly `excluded`, or
`loss-disclosed`. Native simulator state — action ids, Gym tuples, raw
observations, credential caches, reward vectors, hidden truth, and logs — stays
`excluded` and source-private and never enters a portable artifact. That
boundary is enforced two ways: the closed RAES SDL and experiment models have no
field to carry raw native arrays, reward vectors, or action ids (a structural
exclusion), and a deterministic scan rejects known native identifiers (grounded
in the qualification record's recorded observation keys) and native object/array
representations in portable content. No claim rests on CI success, a single
cumulative score, or a top-level seed. The current
qualification is `not-admissible`; authoring and validating this evidence set
does not change that and asserts no installability, replay, conformance, or
equivalence.
