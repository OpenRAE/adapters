# Researcher command

Install the single distribution with the CybORG pack-validation dependency:

```shell
python -m pip install 'raes-adapters[cyborg]'
```

The clean install can immediately produce hermetic conformance evidence; it is
explicitly not a native CybORG experiment:

```shell
mkdir researcher-work && cd researcher-work
raes-adapters inspect --backend cyborg-cage2
raes-adapters run --mode conformance --suite pr --output conformance-evidence
```

The final line prints only a bounded JSON summary. The newly reserved output
root contains canonical conformance reports and an `inventory.json` seal with
relative artifact names, sizes, and SHA-256 digests. An existing output path is
always rejected.

## Validate the packaged example

The wheel includes the symbolic environment-pack identity `cage2-research`.
Validation performs the complete non-native admission path: pack bytes, SDL,
task/spec joins, participant manifest/selection/configuration bindings, controls,
seeds, and runtime planning:

```shell
raes-adapters validate \
  --mode study \
  --pack cage2-research \
  --pack-digest sha256:72925d81fdc570b7b8bfa884b4b85a642f38f97d2cef8939856933439541deab \
  --scenario sdl/cage2-research.sdl.yaml \
  --scenario-digest sha256:58aa6b438c38bb53a5d6636e11835e44ebd6e57b48561e48aa80f0f14bfa6bf2 \
  --task experiment/cage2-research.task.exp.json \
  --experiment experiment/cage2-research.spec.exp.json \
  --red-variant sleep \
  --blue-implementation cyborg-blue-sleep-policy \
  --blue-manifest participant/cyborg-blue-sleep-policy.manifest.json \
  --blue-selection participant/cyborg-blue-sleep-policy.selection.json \
  --blue-configuration participant/cyborg-blue-sleep-policy.configuration.json \
  --trial-length 2 \
  --seed 7 --seed 11 \
  --run-id cage2-validation
```

Native smoke and study modes additionally require the qualified CybORG source
installation documented by the backend qualification. The command never
downloads or clones it. Every declared identity and control is explicit; the
following smoke run executes one admitted seed:

```shell
raes-adapters run \
  --mode smoke \
  --pack cage2-research \
  --pack-digest sha256:72925d81fdc570b7b8bfa884b4b85a642f38f97d2cef8939856933439541deab \
  --scenario sdl/cage2-research.sdl.yaml \
  --scenario-digest sha256:58aa6b438c38bb53a5d6636e11835e44ebd6e57b48561e48aa80f0f14bfa6bf2 \
  --task experiment/cage2-research.task.exp.json \
  --experiment experiment/cage2-research.spec.exp.json \
  --red-variant sleep \
  --blue-implementation cyborg-blue-sleep-policy \
  --blue-manifest participant/cyborg-blue-sleep-policy.manifest.json \
  --blue-selection participant/cyborg-blue-sleep-policy.selection.json \
  --blue-configuration participant/cyborg-blue-sleep-policy.configuration.json \
  --trial-length 2 \
  --seed 7 \
  --run-id cage2-smoke \
  --output cage2-smoke-evidence
```

The reproducible study uses the exact ordered seed allocation declared by the
experiment authoring input:

```shell
raes-adapters run \
  --mode study \
  --pack cage2-research \
  --pack-digest sha256:72925d81fdc570b7b8bfa884b4b85a642f38f97d2cef8939856933439541deab \
  --scenario sdl/cage2-research.sdl.yaml \
  --scenario-digest sha256:58aa6b438c38bb53a5d6636e11835e44ebd6e57b48561e48aa80f0f14bfa6bf2 \
  --task experiment/cage2-research.task.exp.json \
  --experiment experiment/cage2-research.spec.exp.json \
  --red-variant sleep \
  --blue-implementation cyborg-blue-sleep-policy \
  --blue-manifest participant/cyborg-blue-sleep-policy.manifest.json \
  --blue-selection participant/cyborg-blue-sleep-policy.selection.json \
  --blue-configuration participant/cyborg-blue-sleep-policy.configuration.json \
  --trial-length 2 \
  --seed 7 --seed 11 \
  --run-id cage2-study \
  --output cage2-study-evidence
```

Validation happens before native construction and output reservation. Pack,
scenario, task, experiment, participant, control, or digest disagreement exits
without executing the simulator. Successful native runs retain validated RAES
evidence records, derived measures, participant provenance, archival run
records, bounded diagnostics, summaries, machine/software inventory, and the
final relative inventory. Study mode also retains a validated RAES collection
record; it adds no scientific or equivalence claim.

## Reproduce the public CAGE-2 evaluation protocol

The frozen issue-22 path is separate from the two-seed example above. It
predeclares and executes the complete 3 trial-length × 3 Red-policy × 1,000
episode matrix, using one study-scoped Python random stream initialized with
seed 153. It compares the observed RAES-mediated cumulative Blue reward against
the published CCS Sleeper table and retains every scheduled slot, terminal
disposition, confidence-interval input, and evidence join:

```shell
raes-adapters reproduce \
  --phase declare \
  --source-root <raes-adapters-checkout> \
  --output cage2-reproduction-declaration

raes-adapters reproduce \
  --phase run \
  --source-root <raes-adapters-checkout> \
  --output cage2-study-output
```

The run phase requires the separately installed qualified CybORG source and
does not fetch it. The declaration freezes source disagreements as losses: the
checked-in evaluator says 100 episodes and binds no seed, whereas the public
validation description says 1,000 episodes and `random.seed(153)`. The observed
Blue implementation is a public Sleep-policy behavioral reconstruction; it is
not represented as the unavailable submitted-agent artifact.

Each valid run contains compressed, deterministic JSON with the complete
referenced RAES evidence records, derived measures, objective and proposition
results, and archival run record. Compression changes storage only. Every file
and transitive inventory is SHA-256 sealed, every compressed record is parsed
and model-validated offline, and no native observations, state, reward vectors,
logs, or random state are published.

Within a condition, the source-native session is retained and reset so the
single seeded stream continues exactly as declared. Portable RAES snapshots are
not retained across those resets: each scheduled slot starts a fresh archival
run and cannot inherit another slot's action or evidence history.

Recompute the aggregates and six separately-subjected evidence tiers in an
installed environment that has no CybORG source and needs no network access:

```shell
raes-adapters reproduce \
  --phase verify \
  --bundle <exported-study-output> \
  --output cage2-recomputed
```

The result supports an exact, bounded, or failed outcome-reproduction finding
according to the predeclared method. It deliberately does not infer state or
observation equivalence, backend identity, deterministic replay, conformance,
or submitted-agent identity from score similarity. Those limits make the
export usable as honest apparatus and outcome-reproduction evidence rather
than a proof-of-concept smoke run. The adapter does not prescribe where a
research project retains or publishes that export.

Because the public submitted CCS Sleeper artifact is unavailable, a matching
result is specifically a behavioral-baseline outcome reproduction: it shows
that the RAES-mediated Scenario 2 apparatus reproduces the published sleeping
baseline distribution within the frozen rule. It is not a replication of an
unavailable submitted implementation, and `tiers.json` keeps that distinction
in the strongest supported claim.

## Exit status

| Exit | Meaning |
| --- | --- |
| `0` | The requested operation completed and required evidence was sealed. |
| `2` | Closed command-line usage error. |
| `3` | Pack, identity, digest, participant, binding, or control validation failed. |
| `4` | Output confinement, exclusivity, or reuse check failed. |
| `5` | Native execution or verified cleanup failed. |
| `6` | Portable artifact persistence or inventory sealing failed. |
| `70` | Unexpected internal failure, reported without exception details. |

Terminal errors use stable codes and bounded messages. They never echo input
paths, native state, hidden truth, raw logs, environment contents, or a full
traceback.
