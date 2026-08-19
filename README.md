# RAES adapters

[![Documentation](https://readthedocs.org/projects/raes-adapters/badge/?version=latest)](https://raes-adapters.readthedocs.io/en/latest/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/OpenRAE/adapters/badge)](https://scorecard.dev/viewer/?uri=github.com/OpenRAE/adapters)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects?as=badge&url=https%3A%2F%2Fgithub.com%2FOpenRAE%2Fadapters)](https://www.bestpractices.dev/projects?as=entry&url=https%3A%2F%2Fgithub.com%2FOpenRAE%2Fadapters)

`raes-adapters` connects simulator backends to the published contracts of
[RAES](https://github.com/RAESystem/rae), the Reproducible Agentic
Environments System. A researcher can use an adapter to validate a packaged
scenario, inspect the selected simulator source and profile, exercise the
adapter boundary, and retain portable evidence from an admitted run.

Those operations do not by themselves prove deterministic replay, scientific
validity, state or observation equivalence, outcome equivalence, or production
security. Each claim is limited by the selected environment pack, source pins,
participant artifacts, runtime controls, and retained evidence.

## Quickstart: verify the CAGE-2 adapter boundary

Start in a fresh Python 3.12 virtual environment on Linux or macOS. Install the
published distribution and its CAGE-2 pack-validation dependency:

<!-- readme-quickstart:install -->
```shell
python -m pip install 'raes-adapters[cyborg]'
```

Run the short, hermetic CAGE-2 conformance suite from an empty working
directory:

<!-- readme-quickstart:run -->
```shell
raes-adapters run --mode conformance --suite pr --output cage2-quickstart
```

The command prints one bounded JSON object:

<!-- readme-quickstart:output -->
```json
{"disposition":"succeeded","evidence_basis":"hermetic-live","inventory":"inventory.json","mode":"conformance","run_count":1}
```

It creates exactly these files:

<!-- readme-quickstart:artifacts -->
```text
cage2-quickstart/index.json
cage2-quickstart/inventory.json
cage2-quickstart/runs/cyborg-pr-seed-3/conformance/backend-conformance.json
```

The portable Scenario 2 input remains inside the installed `cage2-research`
environment pack at `sdl/cage2-research.sdl.yaml`; the
[checked-in example pack](https://github.com/OpenRAE/adapters/tree/dev/src/raes_adapters/cyborg/examples/cage2-research)
is its reviewable source. `index.json` records the conformance run and its
declared gaps, `backend-conformance.json` is the portable RAES conformance
report, and `inventory.json` seals both files by relative path, size, and
SHA-256 digest.

This is a successful adapter conformance run, not a native CybORG episode. Its
evidence basis is `hermetic-live`, every report states
`native_conformance=false`, and the fixed seed `3` belongs to the conformance
suite rather than a study design. The built-wheel gate executes this README
contract before merge; after publication, the release workflow repeats it
from the exact version on the public package index.

## What a green result means

| Question | Evidence needed | What the quickstart establishes |
| --- | --- | --- |
| Is the scenario valid? | The environment pack, SDL, task, experiment, participant joins, and their digests validate against published contracts. | The conformance probes validate the packaged CAGE-2 source ledger and adapter fixtures. They do not execute the packaged native study task. |
| Does the adapter conform? | A finite backend-conformance report records the exercised cases, execution basis, diagnostics, and capability gaps. | Yes, for the checked hermetic cases. It is not native-live conformance. |
| Did a simulator run complete? | The native runtime was admitted, the requested episodes completed, cleanup was verified, portable artifacts validated, and the inventory was sealed last. | No. The quickstart never imports or executes CybORG. |
| What research claim is supported? | A declared method joins source, scenario, participants, controls, observations, analysis, limitations, and retained evidence. | No study claim. `run_count: 1` is a conformance count, not an experimental result. |

## Run or adapt a simulator study

Native CAGE-2 `validate`, smoke, and study requests currently fail closed
before runtime planning. The packaged task requires semantic reward-component
evidence, while the pinned RAES contract cannot yet verify the required
artifact fields and negative data-quality states. The task is not weakened to
make a demo pass, and the `cyborg` extra does not install the unpublished
patched CybORG wheel.

The [full installed-command and reproduction recipe](https://raes-adapters.readthedocs.io/en/latest/researcher-command/)
records the native source prerequisite, the complete command shapes, exit
codes, evidence layout, and the frozen 3 trial-length × 3 Red-policy × 1,000
episode public CAGE-2 protocol. Use it to review or prepare a study; a native
run becomes admissible only when all declared evidence requirements validate.

Study controls are authored artifacts, not free-form convenience flags:

- **Agent:** select a declared Red variant. A different Blue implementation
  needs its own manifest, selection, configuration, source provenance, and a
  resealed pack.
- **Seed:** smoke and study seeds must be declared by the experiment. A seed
  controls only the random streams the source and adapter can bind; it is not a
  deterministic-replay guarantee.
- **Trial length:** it must match a declared experiment condition. Changing it
  changes the study design and requires updated authored artifacts and digests.
- **Environment pack:** select a published pack identity and content digest.
  Changing scenario or participant content creates a new pack version; it is
  not an ambient path override.

See the [researcher guide](https://raes-adapters.readthedocs.io/en/latest/researcher-guide/)
for a task-first explanation of those controls and the evidence needed before
interpreting a result.

## Current adapters and evidence

This table is a reader index, not a second support registry. The linked
qualification, pack, and conformance records remain authoritative.

| Adapter/profile | Install and execution maturity | Current evidence status |
| --- | --- | --- |
| CybORG / CAGE-2 Scenario 2 | Adapter, example pack, and hermetic conformance are available. Native CybORG requires the separately installed pinned source plus an unpublished packaging-only fix. | Source qualified; pack status `built`; hermetic conformance with `native_conformance=false`; native researcher task evidence-gate blocked. |
| NASim / tiny | The `nasim` extra installs the pinned simulator stack and the source-backed conformance boundary is available. | Qualified source and conformance evidence; the current packaged researcher task is evidence-gate blocked before native study execution. |
| CyberBattleSim / chain | Adapter and reproduction tooling are implemented; native source is installed separately because upstream publishes no governed wheel. | Source/profile admitted, conformance evidence retained, and a bounded baseline reproduction record exists; the packaged researcher task is evidence-gate blocked. |
| PrimAITE / data manipulation | Qualified backend module; no researcher CLI selection is exposed. Native in-process execution remains fail-closed. | Conformance uses an injected non-native driver and makes no native-conformance claim. |

## Limitations

- **Simulator abstraction:** portable RAES records deliberately omit native
  state, gym/PettingZoo tuples, action IDs, reward vectors, object
  representations, raw logs, hidden truth, and full tracebacks. That protects
  the portable boundary but cannot demonstrate native state equivalence.
- **Stochasticity:** declared seeds do not bind every simulator, policy,
  Python, NumPy, or Gym random stream. Repeated outcomes can vary, and a seed
  is not deterministic replay.
- **Source pins:** evidence applies to the qualified repository, commit, files,
  patches, and package graph. A different source tree needs requalification.
- **Unsupported facts:** missing participant artifacts, unverifiable evidence
  witnesses, capability gaps, and source inconsistencies remain explicit
  losses. Successful validation never upgrades an unsupported claim.
- **Compute cost:** the full CAGE-2 reproduction schedules 9,000 episodes and
  retains per-slot evidence. Estimate runtime and storage before starting it;
  the quickstart is intentionally not that workload.
- **Non-production scope:** these adapters are research and evaluation
  apparatus. Conformance is not a security certification, operational defense
  guarantee, or authorization to deploy an agent in production.

## Citation and provenance

For a paper or evidence bundle, record the `raes-adapters` version, environment
pack name/version/content digest, adapter qualification profile and source
commit, participant artifact digests, experiment controls, and the retained
`inventory.json`. Cite the repository release and the upstream simulator; do
not cite a mutable branch as the executed identity. The CAGE-2
[qualification record](https://github.com/OpenRAE/adapters/blob/dev/src/raes_adapters/cyborg/qualification.json)
and pack
[provenance ledger](https://github.com/OpenRAE/adapters/blob/dev/src/raes_adapters/cyborg/examples/cage2-research/docs/provenance-ledger.yaml)
show the current source and artifact bindings.

## Troubleshooting

- **Package version cannot be found:** use Python 3.12 and confirm that a
  release exists on the configured public package index. Do not substitute an
  editable checkout when claiming a published-distribution reproduction.
- **Output unavailable:** choose a new relative output directory. Existing,
  absolute, traversing, or symlink-escaping paths are rejected.
- **Evidence unverifiable (exit 3):** this is the current fail-closed native
  study boundary, not an installation failure. Review the researcher command
  and task evidence requirements; do not remove them.
- **Native source unavailable:** the `cyborg` extra validates the pack but does
  not download CybORG. Follow the pinned source qualification before attempting
  native execution.
- **Unexpected internal failure (exit 70):** retain the bounded error code,
  package version, command shape, and inventory if present. Do not publish
  native logs or environment dumps in an issue.

More diagnosis and all stable exit codes are in the
[researcher command reference](https://raes-adapters.readthedocs.io/en/latest/researcher-command/#exit-status).

## Developing an adapter

Build, CI, repository layout, packaging, release, governance, and contributor
mechanics are intentionally outside this researcher path. Start with the
[developer index](https://raes-adapters.readthedocs.io/en/latest/maintainers/)
and [CONTRIBUTING](https://github.com/OpenRAE/adapters/blob/dev/CONTRIBUTING.md).
RAES owns the semantic contracts; backend concepts remain inside their adapter
module, and `raes_adapters.base` remains plumbing rather than authority.
