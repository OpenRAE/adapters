# CAGE-2 → ACES mapping ledger

**Authored under REP-003 (ACES issue for the CAGE-2 scenario + mapping).** This
directory is a placeholder standup under REP-002.

Per ACES ADR-069 §2 and `docs/decisions/cage-2-replication-design.md`, the
mapping from upstream CAGE-2/CybORG source facts to portable ACES artifacts is a
**pinned ledger** over immutable upstream source identifiers.

## Files

- `cage2-source-ledger.jsonl` — one JSON object per source fact. Each row records
  `source_id`, `source_repo`, `source_version`, `source_path`, `source_selector`,
  optional `source_digest`, `cage_fact_type`, `aces_target`, `mapping_rule`,
  `loss_disclosure`, and `verification` (see the design record for field
  definitions). Empty until REP-003.
- `cage2-loss-disclosures.md` — narrative loss disclosures for source facts ACES
  cannot carry exactly. A disclosed gap weakens the replication claim; it is
  never backfilled with raw CybORG logs or prose-only evidence.

Every upstream source fact must be mapped, explicitly declared out of scope, or
loss-disclosed. No claim may rest on CI success or a single cumulative score.
