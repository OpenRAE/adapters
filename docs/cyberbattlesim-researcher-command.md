# CyberBattleSim researcher command

The installed `raes-adapters` command exposes the selected
`CyberBattleChain-v0` researcher case as `--backend cyberbattlesim-chain`. The
environment pack is a checksum-bound GitHub Release asset; it is intentionally
outside the wheel and sdist. The command never downloads a pack or discovers an
unreviewed source tree.

## Install and inspect

Install the adapter surface and pack validator:

```bash
python -m pip install 'raes-adapters[cyberbattlesim]'
raes-adapters inspect --backend cyberbattlesim-chain
```

`inspect` does not import or construct CyberBattleSim. It reports whether the
pinned native source is available and byte-verified, along with the qualified
source commit and supported RAES profiles.

The native simulator remains separately installed because upstream publishes no
selected index or release artifact. Build or acquire the wheel from commit
`854d6966607fb68645651f55b0f97221bd293e0d`, verify the complete identity
recorded in `qualification.json`, then install that wheel. The qualified wheel
digest is:

```text
sha256:6e5f855a999ccfcb93f643dda9cbf7ac679640c67df246f4750c344acf2e2138
```

## Acquire the external pack

Download `cyberbattlesim-chain-1.0.0.tar.gz`,
`cyberbattlesim-chain-1.0.0-views.tar.gz`, and `ENV_PACK_SHA256SUMS` from the
same `raes-adapters` GitHub Release. Verify both published assets before
extracting the pack:

```bash
sha256sum --check --strict ENV_PACK_SHA256SUMS
tar -xzf cyberbattlesim-chain-1.0.0.tar.gz
raes-pack-validate --pack cyberbattlesim-chain
raes-pack-release check --pack cyberbattlesim-chain
```

The admitted pack content digest is:

```text
sha256:08ae7e997b50bb396c290c4a5537a65e9e7d8b8e6abc97d1ff65022c4258e417
```

An asset with different bytes is rejected even if it is otherwise a valid
environment pack.

## Validate the run

From the directory containing the extracted pack:

```bash
raes-adapters validate --backend cyberbattlesim-chain --mode smoke \
  --pack cyberbattlesim-chain \
  --pack-digest sha256:08ae7e997b50bb396c290c4a5537a65e9e7d8b8e6abc97d1ff65022c4258e417 \
  --scenario sdl/cyberbattlesim-chain.sdl.yaml \
  --scenario-digest sha256:9d696ea7fa23a1e7cf4c1cbc145a7989370dc4e9afff2cd5a17d6d1af887b528 \
  --experiment experiment/cyberbattlesim-chain.spec.exp.json \
  --task experiment/cyberbattlesim-chain.task.exp.json \
  --participant-implementation cyberbattlesim-red-credential-cache \
  --participant-manifest participant/cyberbattlesim-red-credential-cache.manifest.json \
  --participant-selection participant/cyberbattlesim-red-credential-cache.selection.json \
  --participant-configuration participant/cyberbattlesim-red-credential-cache.configuration.json \
  --trial-length 600 --seed 20260729 --run-id cyberbattlesim-smoke
```

Validation binds the pack, scenario, experiment, task, participant artifacts,
source policy identity, trial length, and seed before any output directory or
native execution is created.

## Run the selected case

Use the same arguments with `run`, plus an unused invocation-relative output:

```bash
raes-adapters run --backend cyberbattlesim-chain --mode smoke \
  --pack cyberbattlesim-chain \
  --pack-digest sha256:08ae7e997b50bb396c290c4a5537a65e9e7d8b8e6abc97d1ff65022c4258e417 \
  --scenario sdl/cyberbattlesim-chain.sdl.yaml \
  --scenario-digest sha256:9d696ea7fa23a1e7cf4c1cbc145a7989370dc4e9afff2cd5a17d6d1af887b528 \
  --experiment experiment/cyberbattlesim-chain.spec.exp.json \
  --task experiment/cyberbattlesim-chain.task.exp.json \
  --participant-implementation cyberbattlesim-red-credential-cache \
  --participant-manifest participant/cyberbattlesim-red-credential-cache.manifest.json \
  --participant-selection participant/cyberbattlesim-red-credential-cache.selection.json \
  --participant-configuration participant/cyberbattlesim-red-credential-cache.configuration.json \
  --trial-length 600 --seed 20260729 --run-id cyberbattlesim-smoke \
  --output cyberbattlesim-evidence
```

The exact upstream `CredentialCacheExploiter` proposes each native action. A
proposal does not mutate the simulator: its semantic action must first cross the
RAES participant admission boundary. The existing adapter evaluator projects
the result, and cleanup is always attempted and verified.

Study mode requires ten `--seed 20260729` occurrences, matching the selected
source episode count. Repeated seed labels do not establish deterministic
replay: Python-global and NumPy-global random streams remain unbound by the
public evaluator. The command also makes no scientific-equivalence or outcome-
equivalence claim. Review the pack's operator-only
`docs/golden-readiness-checklist.md` before publishing study evidence.
