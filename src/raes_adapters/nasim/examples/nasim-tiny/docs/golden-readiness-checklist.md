# NASim tiny golden readiness checklist

This checklist plans the final, auditable manual review that promotes the pack
from `built` to `golden`. It is operator-facing readiness evidence, not
participant content.

## Golden Definition Of Done

The pack is golden only when every item below is checked by a human reviewer.

- [ ] `raes_env_packs.validate_pack` returns `ok` for the pack.
- [ ] `raes-pack-validate --pack .` exits zero (static contract, SDL, provenance,
      manifest, golden-checklist, anti-extension gates all green).
- [ ] `raes-pack-release check --pack .` reports the pack RELEASABLE and PASS.
- [ ] The pinned `pack.content-manifest.json` `set_digest` matches freshly
      derived pack bytes.
- [ ] Provenance licensing and attribution for the NASim MIT upstream are
      correct, and the ADR-069 determinism-loss disclosure is present and
      unweakened.
- [ ] No native NASim symbol (flat action index, raw observation vector,
      host access-level state) appears in any portable artifact.

## Final Manual Participant Walkthrough Protocol

A reviewer performs the participant-facing walkthrough before promotion.

- [ ] Read `docs/concepts.md` and `docs/attack-path.md` and confirm they
      describe only portable, participant-safe content.
- [ ] Confirm the red bruteforce participant selection resolves against the SDL
      attacker agent and its observation boundary.
- [ ] Confirm the experiment task and spec describe the reward, evaluator, and
      independent termination causes without asserting deterministic replay.
- [ ] Confirm the two sensitive hosts and the compromise objective read
      correctly from the instantiated scenario.
