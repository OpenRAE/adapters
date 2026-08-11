# CyberBattleSim baseline reproduction

Issue [OpenRAE/adapters#30](https://github.com/OpenRAE/adapters/issues/30)
collects the qualified `CyberBattleChain-v0` credential-cache baseline through
two deliberately different lanes: the unmodified upstream
`epsilon_greedy_search` evaluator and the RAES-mediated researcher path. The
result is a content-addressed public data bundle for OpenRAE/research#14 and
OpenRAE/research#20, not a deterministic-replay or outcome-equivalence claim.

## Required apparatus

Use CPython 3.12 with the repository's locked `cyberbattlesim` extra, plus a
wheel built from Microsoft CyberBattleSim commit
`854d6966607fb68645651f55b0f97221bd293e0d`. The installed wheel must pass the
adapter's complete-root, selected-file, version, dependency-artifact, symlink,
and module-origin admission checks. A directory or editable simulator install
is rejected.

The experiment needs no GPU, model weights, external dataset, or network after
source, wheel, and dependency acquisition. Four x86-64 vCPUs, 16 GiB RAM, and
20 GiB of free disk are ample. Collection records logical CPU count, physical
memory, operating system, Python, installed distributions, source identity,
wheel digest, and environment-pack digest without retaining a host name, IP,
provider identifier, path, or provider log.

## Frozen sequence

Run from an isolated checkout root. Every output is exclusive and must be a new
invocation-relative directory.

```bash
mkdir reproduction-work
python -m raes_adapters.cyberbattlesim.reproduction declare \
  --output reproduction-work/declaration
python -m raes_adapters.cyberbattlesim.reproduction native \
  --declaration reproduction-work/declaration \
  --output reproduction-work/native-oracle
```

The declaration preallocates ten source-native and ten RAES-mediated run and
attempt IDs, with retry budget zero. It embeds a validated RAES
`ExperimentStudyModel`, references the published task/spec, pins all apparatus
and runner bytes, declares actual random-stream dispositions, and fixes the
aggregation, missingness, bootstrap, tolerance, and six-tier policies. The
native command invokes the exact upstream evaluator once for its ten-episode
schedule. Native reward vectors exist only in private scratch; portable rows
retain cumulative reward, steps, availability, and a source-backed terminal
cause. The upstream evaluator carries its `steps_done` epsilon-decay counter
across episode boundaries. The mediated collector therefore passes the sum of
prior completed mediated steps into each next episode; a failed attempt consumes
only the steps it actually completed and is never retried.

The first terminalized 20-attempt series under declaration
`825dde3b4cd66f228e0f93157a2add35e3c9a822a7adac1d8ffd322b32116232`
is rejected from final publication. Its byte-oriented leak gate treated the
names of fields explicitly listed in RAES `withheld_refs` as if native values
had leaked. The scanner bound into that declaration was not changed in place.
The replacement declaration discloses the rejection and allocates disjoint
`cbs-r2-*` run and attempt identities while leaving the source, conditions,
metrics, aggregation, tolerances, and tier policy unchanged. The structural
gate permits those names only as withheld-reference strings; the same names as
JSON keys, embedded payload strings, or non-JSON content still fail closed.

Revision 2, declaration
`f09ec5759021cf1d5de9b260e0299934bf6f6cc4161b822e8f5f0b76bdb96b53`,
is retained as an immutable negative result. It exposed two adapter apparatus
defects: the mediated driver discarded source-provided network availability and
collapsed all source termination to a generic cause, while its ten independent
processes restarted epsilon decay at zero instead of matching the native
ten-episode batch. Its reward comparison was bounded, its step interval crossed
the frozen tolerance, and its availability/cause comparisons were unavailable.
The corrected `cbs-r3-*` selection binds the predecessor declaration and
inventory identities, but does not edit that bundle, widen a tolerance, change
random-stream bindings, or reinterpret the old result.

Every stage also writes `bench-notes.json`. Each closed note has an RFC 3339
UTC timestamp with millisecond precision, phase, severity, stable event code,
concise observation, disposition, and relative evidence references. Collection
writes start and terminalization observations as they happen. Failures remain
timestamped and visible, but exception text, raw native output, host paths,
credentials, and provider identifiers never become notes. The issue thread is
the timestamped record for apparatus and development observations that precede
the frozen declaration.

Review and commit the unchanged declaration, completed `protocol.json`, native
rows, and oracle before any mediated attempt. If those bytes or any declared
artifact change, discard the unrun schedule and start a new declaration.

Then collect the mediated lane against the exact admitted pack:

```bash
python -m raes_adapters.cyberbattlesim.reproduction mediated \
  --oracle reproduction-work/native-oracle \
  --pack environments/cyberbattlesim-chain \
  --output reproduction-work/mediated
```

Each mediated attempt invokes the installed researcher command independently,
passes the exact pack/scenario/task/spec/participant joins, admits every policy
proposal through RAES, evaluates through the adapter, verifies cleanup, seals
its portable evidence, and continues to terminalize later IDs after a failed
attempt. In addition to cumulative reward and step count, the evaluator retains
only the source's finite `[0,1]` `network_availability` value for every committed
step and a source-backed reconstructed terminal cause. Those values are written
to `episode-outcome.json`, whose SHA-256 digest is bound by exactly one RAES
evidence record. Missing, malformed, non-finite, out-of-range, length-mismatched,
or unbound outcome evidence fails closed; no raw source `info` is published.

Finally use the full `declaration_sha256` from the completed protocol as the
output directory name:

```bash
python -m raes_adapters.cyberbattlesim.reproduction finalize \
  --oracle reproduction-work/native-oracle \
  --mediated reproduction-work/mediated \
  --output packages/cyberbattlesim_adapter/reproduction/<declaration_sha256>
python -m raes_adapters.cyberbattlesim.reproduction verify \
  --bundle packages/cyberbattlesim_adapter/reproduction/<declaration_sha256>
```

`finalize` assembles a new root once, recomputes lane summaries and 10,000
counter-addressed SHA-256 percentile-bootstrap resamples, evaluates the six
predeclared tiers, validates digest-bound JSON-Pointer citations, scans the
allowlisted public projection, retains the timestamped verification disposition,
and writes `inventory.json` last. `verify` is a pure offline read: it does not
import CyberBattleSim, contact a network, mutate the bench notes, or read
credentials, caches, provider logs, or private scratch.

## Interpreting the bundle

All 20 scheduled attempts stay in the denominator and end `valid`, `invalid`,
`failed`, or `excluded`. Missing metrics are never imputed. Numeric bounded
reproduction requires the complete 95% mean-difference interval to fit inside
the frozen band: steps ±60, cumulative reward ±500, mean availability ±0.05,
and terminal-cause proportion ±0.10. Criteria are not widened after observing
the native oracle.

The six tier results are separate: authored-source, contract,
execution-control, state-observation, outcome-evaluation, and disclosure. A
passing integrity or contract tier cannot erase stochastic, topology,
observation, evaluator-path, metric-availability, packaging, or upstream
limitations. The bundle makes no claim of deterministic replay, exact state or
observation equivalence, cross-simulator equality, agent ranking, benchmark
comparability, outcome equivalence, or general scientific reproducibility.
