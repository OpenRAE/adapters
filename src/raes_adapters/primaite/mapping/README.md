# PrimAITE → RAES mapping ledger

**Authored under RAESystem/adapters#40.** This directory is backend-local
traceability evidence for the selected public PrimAITE `data_manipulation` case.
It records how each pinned upstream source fact reaches a portable RAES surface —
the authored SDL scenario or a published experiment contract — or why it does
not. It follows the sibling CybORG and CyberBattleSim mapping directories'
module-local ownership *pattern*; it does not copy their field names or labels
into a shared schema, and no ledger is generalized into `raes_adapters.base`.

Per RAES ADR-069 and `docs/decisions/primaite-scenario-ledger-guardrails.md`,
the mapping is a **pinned ledger** over the immutable source identifiers already
recorded in [`../qualification.json`](../qualification.json). It is package data,
not a public DTO, schema, profile, vocabulary, manifest, or semantic contract.

## Files

- `source-ledger.jsonl` — one JSON object per source fact. Fields:
  - `source_id` — stable, unique row identity.
  - `source_repo`, `source_commit`, `source_path`, `source_selector` — immutable
    upstream coordinate and the symbol/path the fact comes from.
  - `source_digest` — the file SHA-256; it must join the matching
    `qualification.json` `source_files` entry (offline source-drift check — CI
    never fetches a floating branch or executes PrimAITE).
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
`identities`, `participants`, `actions`, `observations`, `controls` (addresses,
ports, services, traffic, firewall/routing behavior), `rewards-objectives`,
`termination`, `evaluator`, `stochastic`, and `provenance-licensing`.

## Governance

Every upstream source fact is `mapped`, explicitly `excluded`, or
`loss-disclosed`. Native simulator state — the `Discrete(78)` action ids and
mask, the flattened `Box(1652)` observation, raw NMNE counts, the info dict,
traffic payloads, hidden truth, and logs — stays `excluded` and source-private
and never enters a portable artifact. That boundary is enforced two ways: the
closed RAES SDL and experiment models have no field to carry native arrays,
reward vectors, or action ids (a structural exclusion), and a deterministic scan
rejects native identifiers (grounded in the qualification record's scripted RED
and GREEN participant refs) and native object/array/traceback representations in
portable content. No claim rests on CI success, a single cumulative reward, or a
top-level seed. The selected profile is admitted; authoring and validating this
evidence set strengthens its provenance without asserting dependency
installability, deterministic replay, conformance, or outcome equivalence.
