# NASim researcher command

The installed `raes-adapters` console script exposes the NASim `nasim-tiny`
backend through the same shell as the other adapters. Select it with
`--backend nasim-tiny`; the mode dispatch (`inspect`, `validate`, `run`) is
shared, while every backend-local semantic — inspection payload, native import
and source verification, packaged pack members, participant admission, run
controls, and archival — resolves through the NASim adapter.

Install the single distribution with the NASim extra:

```shell
python -m pip install 'raes-adapters[nasim]'
```

Unlike the CybORG extra, the `nasim` extra pins and installs the qualified
native NASim source (`nasim==0.12.0`, its `gymnasium`/`numpy` pins, and the
published environment-pack validator). A clean install therefore already has the
qualified source available; the command still verifies the installed source tree
against the backend qualification before any native construction and never
downloads, clones, or patches it.

Inspect the installed identities without constructing the native backend, then
produce conformance evidence:

```shell
mkdir nasim-researcher-work && cd nasim-researcher-work
raes-adapters inspect --backend nasim-tiny
raes-adapters run --backend nasim-tiny --mode conformance --suite pr --output nasim-conformance-evidence
```

`inspect` prints the adapter and backend identities, the NASim qualification
(source commit, version, repository, and ledger), the installed
`native_available` flag, the supported profiles, and the packaged `nasim-tiny`
example.

NASim conformance is an **installed-source probe**, not a hermetic injected
driver. The suite runs the published RAES target conformance probe over the
installed qualified NASim source and preserves its canonical report,
source-protocol diagnostics, declared weaknesses, and explicit non-claims. It is
native-gated: it needs the qualified source that the extra installs, and it is
neither an `ExperimentRunModel` nor a native attacker episode merely because it
shares the command. The conformance run reports `execution_basis`
`installed-source-probe`.

The final line of each run prints only a bounded JSON summary. The newly
reserved output root contains the canonical conformance reports and an
`inventory.json` seal with relative artifact names, sizes, and SHA-256 digests.
An existing output path is always rejected.

## Validate the packaged example

The wheel ships the symbolic environment-pack identity `nasim-tiny` bound to a
single autonomous red bruteforce attacker. NASim declares **no** red variant and
**no** defender: the attacker is fixed by the admitted participant
implementation, so the selection surface is the closed `--participant-*` set —
there is no `--red-variant` and no `--blue-*` flag. Validation performs the
complete admission path without native construction: pack bytes, SDL, task/spec
joins, participant manifest/selection/configuration bindings, controls, seeds,
and runtime planning:

```shell
raes-adapters validate --backend nasim-tiny --mode study \
  --pack nasim-tiny \
  --pack-digest sha256:4b96181c34eeead6a02f31517a313becdb352899a209046efedc8e2637d1c5f2 \
  --scenario sdl/nasim-tiny.sdl.yaml \
  --scenario-digest sha256:a826fd8f812a447dd4c8d346179163f4c5274176ca739bc2802756913a195e2d \
  --experiment experiment/nasim-tiny.spec.exp.json \
  --task experiment/nasim-tiny.task.exp.json \
  --participant-implementation nasim-red-bruteforce \
  --participant-manifest participant/nasim-red-bruteforce.manifest.json \
  --participant-selection participant/nasim-red-bruteforce.selection.json \
  --participant-configuration participant/nasim-red-bruteforce.configuration.json \
  --trial-length 1000 --seed 20260802 --run-id nasim-tiny-run
```

Every declared identity and control is explicit. The pack identity `nasim-tiny`
resolves to the packaged example; any other value is treated as a caller-supplied
pack root. The operator seed must equal a declared stochastic-control value and
satisfy the selected mode's cardinality — one seed for `smoke`, and exactly the
declared `target_run_count` for `study`.

## Native smoke and study runs

Native modes construct and drive the qualified NASim source. The bounded smoke
variant admits exactly one seed and executes a single research run:

```shell
raes-adapters run --backend nasim-tiny --mode smoke \
  --pack nasim-tiny \
  --pack-digest sha256:4b96181c34eeead6a02f31517a313becdb352899a209046efedc8e2637d1c5f2 \
  --scenario sdl/nasim-tiny.sdl.yaml \
  --scenario-digest sha256:a826fd8f812a447dd4c8d346179163f4c5274176ca739bc2802756913a195e2d \
  --experiment experiment/nasim-tiny.spec.exp.json \
  --task experiment/nasim-tiny.task.exp.json \
  --participant-implementation nasim-red-bruteforce \
  --participant-manifest participant/nasim-red-bruteforce.manifest.json \
  --participant-selection participant/nasim-red-bruteforce.selection.json \
  --participant-configuration participant/nasim-red-bruteforce.configuration.json \
  --trial-length 1000 --seed 20260802 --run-id nasim-tiny-run \
  --output nasim-smoke-evidence
```

The reproducible study uses the exact ordered seed allocation declared by the
experiment authoring input and adds the validated study collection record:

```shell
raes-adapters run --backend nasim-tiny --mode study \
  --pack nasim-tiny \
  --pack-digest sha256:4b96181c34eeead6a02f31517a313becdb352899a209046efedc8e2637d1c5f2 \
  --scenario sdl/nasim-tiny.sdl.yaml \
  --scenario-digest sha256:a826fd8f812a447dd4c8d346179163f4c5274176ca739bc2802756913a195e2d \
  --experiment experiment/nasim-tiny.spec.exp.json \
  --task experiment/nasim-tiny.task.exp.json \
  --participant-implementation nasim-red-bruteforce \
  --participant-manifest participant/nasim-red-bruteforce.manifest.json \
  --participant-selection participant/nasim-red-bruteforce.selection.json \
  --participant-configuration participant/nasim-red-bruteforce.configuration.json \
  --trial-length 1000 --seed 20260802 --run-id nasim-tiny-run \
  --output nasim-study-evidence
```

Validation happens before native construction and output reservation. Pack,
scenario, task, experiment, participant, control, or digest disagreement exits
without executing the simulator. Successful native runs retain validated RAES
evidence records, derived measures, participant provenance, archival run
records, bounded diagnostics, summaries, machine/software inventory, and the
final relative inventory. Study mode also retains a validated RAES collection
record; it adds no scientific or equivalence claim.

## Determinism is not claimed

NASim's `nasim-tiny` static benchmark draws action success from the
process-global legacy NumPy stream, which neither `make_benchmark` nor the gym
reset seed binds for a static benchmark (ADR-069). A bound seed satisfies the
declared control cardinality but is **never** a deterministic-replay claim. This
loss is retained in the run apparatus context as a known limitation and in the
conformance non-claims; it is disclosed, not erased. The command asserts no
deterministic replay, state/observation equivalence, outcome equivalence, or
scientific validity from a controlled seed, a green run, a conformance report, or
a reproducible command line.

## Exit status

| Exit | Meaning |
| --- | --- |
| `0` | The requested operation completed and required evidence was sealed. |
| `2` | Closed command-line usage error. |
| `3` | Pack, identity, digest, participant, binding, or control validation failed. |
| `4` | Output confinement, exclusivity, or reuse check failed. |
| `5` | Native execution or verified cleanup failed (including an unavailable qualified NASim source). |
| `6` | Portable artifact persistence or inventory sealing failed. |
| `70` | Unexpected internal failure, reported without exception details. |

Terminal errors use stable codes and bounded messages. They never echo input
paths, native state, hidden truth, raw logs, environment contents, or a full
traceback.
