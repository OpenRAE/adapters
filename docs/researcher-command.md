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
  --pack-digest sha256:1006e46a05a2fbafa0457743765d684dbfef652cda78733f39ea066ba34246e1 \
  --scenario sdl/cage2-research.sdl.yaml \
  --scenario-digest sha256:926f13857da070f1ebdc3afbb3193c7c13f4aa9fe324b3eb93e1c2595871abda \
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
  --pack-digest sha256:1006e46a05a2fbafa0457743765d684dbfef652cda78733f39ea066ba34246e1 \
  --scenario sdl/cage2-research.sdl.yaml \
  --scenario-digest sha256:926f13857da070f1ebdc3afbb3193c7c13f4aa9fe324b3eb93e1c2595871abda \
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
  --pack-digest sha256:1006e46a05a2fbafa0457743765d684dbfef652cda78733f39ea066ba34246e1 \
  --scenario sdl/cage2-research.sdl.yaml \
  --scenario-digest sha256:926f13857da070f1ebdc3afbb3193c7c13f4aa9fe324b3eb93e1c2595871abda \
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
