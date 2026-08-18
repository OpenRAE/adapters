# Researcher guide

Use this guide after completing the README conformance quickstart. The
quickstart proves that an installed adapter can emit bounded RAES conformance
evidence; it does not execute a simulator study.

## Choose the evidence you need

Before selecting a command, decide which statement the work must support:

| Intended statement | Minimum evidence boundary |
| --- | --- |
| The authored scenario and experiment are well-formed. | Validate the environment pack, SDL, task, experiment, participants, controls, and all content digests. |
| The adapter exercises selected RAES backend contracts. | Retain a conformance report with its execution basis, cases, diagnostics, capability gaps, and declared non-claims. |
| A native run completed. | Admit the pinned simulator source, complete every scheduled run, verify cleanup, validate the portable records, and seal the inventory last. |
| A result reproduces or supports a research claim. | Predeclare the method and comparison rule, retain the complete evidence joins, account for losses and stochastic controls, and report only the strongest tier the evidence supports. |

Do not infer a stronger row from a successful weaker row. In particular,
scenario validity is not conformance, conformance is not native completion,
and native completion is not scientific validity.

## Work with the CAGE-2 pack

The installed `cage2-research` pack carries the portable Scenario 2 SDL, task,
experiment, Blue participant manifest/selection/configuration, compatibility
record, content manifest, and provenance ledger. The
[checked-in pack](https://github.com/OpenRAE/adapters/tree/dev/src/raes_adapters/cyborg/examples/cage2-research)
is the review surface; installed package resources are the execution surface.

The current pack has status `built`, not `golden`. Its native task remains
fail-closed because the pinned RAES contract cannot validate the task's
semantic reward-component witness. Pack validity and source qualification do
not override that gate.

## Change a study deliberately

### Participant implementation

A Red policy can be selected only when the pack declares that variant. A new
Blue implementation needs a published participant manifest, selection, and
configuration whose identities and digests join the task and pack. Record the
implementation source or model bytes; do not represent an unavailable
submitted artifact through a similarly behaving substitute.

### Seed allocation

Seeds belong to the experiment design. Record which random streams each seed
actually controls and disclose the unbound streams. A shared numeric seed does
not imply deterministic replay across simulator, policy, Python, NumPy, or Gym
state.

### Trial length

Trial length is part of the declared condition, not an arbitrary cutoff. A new
length changes termination and comparison semantics, so update the experiment,
task joins, pack content manifest, and digests before execution.

### Environment pack

Changing the scenario, task, participant, or experiment creates a new pack
identity/version. Validate and reseal it through the published environment-pack
tools. The researcher CLI intentionally has no ambient profile root, arbitrary
driver import, hidden default, or runtime download seam.

## CAGE-2 reproduction boundary

The [installed researcher command](researcher-command.md) documents both the
two-seed authored example and the frozen public protocol reproduction. The
public protocol schedules 3 trial lengths × 3 Red variants × 1,000 episodes and
uses the declared study-scoped Python stream initialized with seed 153. It is a
substantial compute and storage workload, not a quickstart.

The public submitted Blue artifact is unavailable. The retained comparison can
therefore support only the predeclared behavioral-baseline outcome tier; it
cannot establish submitted-agent identity, state or observation equivalence,
deterministic replay, or native conformance from score similarity.

## Limitations to carry into a report

- Portable artifacts exclude native state, observations, action identifiers,
  reward vectors, object representations, raw logs, hidden truth, environment
  dumps, and tracebacks.
- Stochastic controls are partial wherever the pinned source exposes no binding
  seam.
- Qualification applies only to its repository, commit, selected files,
  patches, interpreter/platform evidence, and dependency graph.
- Capability gaps and missing evidence witnesses remain negative facts; a
  successful adjacent check does not satisfy them.
- Full studies can be expensive in episodes, wall time, memory, and evidence
  storage. Estimate all four before execution.
- The apparatus is not a production control, security certification, or
  operational defense guarantee.

## Citation and provenance checklist

Record these identities with the retained evidence:

1. `raes-adapters` release version and artifact hash;
2. RAES and environment-pack dependency versions;
3. environment pack name, version, content digest, and compatibility record;
4. adapter qualification profile, upstream repository, source commit, and any
   admitted patch digest;
5. scenario, task, experiment, and participant artifact digests;
6. run controls, seed allocation, runtime/software inventory, and declared
   losses; and
7. the final `inventory.json` plus the archive or repository location that
   preserves the referenced files.

Cite an immutable release and the upstream simulator project. A branch name or
working-tree path is useful context but is not an executed artifact identity.

## Troubleshooting

### The package is not available

Confirm Python 3.12, the configured public package index, and the requested
release. An editable checkout is suitable for development but must not be
reported as a published-distribution reproduction.

### The output path is rejected

Every output root is invocation-relative, new, and exclusively reserved. Use a
new directory name. Absolute paths, parent traversal, reuse, and resolved
symlink escape are rejected before evidence writes.

### Validation exits with status 3

Read the stable error code. For the current CAGE-2 native task,
`researcher.validation.evidence-unverifiable` is expected: validation stopped
before runtime planning because the evidence witness cannot be verified. Do
not remove the requirement or replace it with a local allowlist.

### Native source is unavailable

The `cyborg` extra installs pack validation, not CybORG. Native execution needs
the exact separately installed qualified source and packaging fix recorded in
the qualification. The adapter does not clone, download, or select source from
an ambient environment variable.

### A run fails

Retain the bounded command error, package/source identities, and any sealed
portable inventory. Do not attach native logs, raw observations, environment
contents, tokens, or full tracebacks. The [exit-status table](researcher-command.md#exit-status)
separates usage, validation, output, native execution, artifact, and internal
failures.
