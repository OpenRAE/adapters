# CAGE-2 → RAES mapping ledger

This backend-local evidence bridges the source closure qualified by issue #12
to the published RAES surfaces that can carry each CAGE-2 fact. It does not
author an SDL scenario or experiment or establish equivalence. Maintainer
selection admits the backend; this ledger grades what RAES can record and what
remains lossy.

Per RAES ADR-069 §2 and `docs/decisions/cage-2-replication-design.md`, the
mapping from upstream CAGE-2/CybORG source facts to portable RAES artifacts is a
**pinned ledger** over immutable upstream source identifiers.

## Files

- `cage2-source-ledger.jsonl` — one JSON object per source fact. Each row records
  a unique id, source family, fact facet, qualified repository/commit/path/digest,
  verifiable selector, disposition, mapping rule, and verification. A mapped or
  partially mapped fact cites a published schema-bundle id plus JSON pointer.
  Qualification-owned legal evidence uses a `qualification.json` pointer rather
  than pretending it is RAES semantics.
- `cage2-loss-disclosures.md` — narrative loss disclosures for source facts RAES
  cannot carry exactly. Each disclosure has a machine-parsed set of weakened
  ADR-069 equivalence tiers that must exactly match its ledger rows.

The module-local validator enforces both completeness axes from the accepted
design: source families (Scenario2/images, actions, observations, rewards,
wrappers, agents, evaluation, and provenance/licensing) and semantic facets
(topology through derived measures plus licensing/attribution). It rejects
malformed or open-ended rows, duplicate ids, coverage gaps, unclassified facts,
source-profile/digest drift, unresolved published targets, selector failures,
and missing/orphan/mismatched loss disclosures. The qualification reproducer
also checks every selector against a detached checkout without importing or
executing upstream code.

Every fact is `mapped`, `out-of-scope`, or `loss-disclosed`. Native state,
observations, hidden truth, action ids, reward vectors, object representations,
raw logs, environment data, and tracebacks remain outside portable artifacts.
No claim may rest on a green validator, CI success, native-log similarity, or a
single cumulative score.
