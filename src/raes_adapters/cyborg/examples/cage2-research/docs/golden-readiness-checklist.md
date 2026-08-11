# CAGE-2 researcher example golden readiness checklist

This checklist plans the final, auditable manual review that may promote the
pack from `built` to `golden`. It is operator-facing readiness evidence, not
participant content. Keep the source boxes unchecked and record completed proof
in the review issue or rehearsal report.

## Golden Definition Of Done

- [ ] `raes-pack-validate --pack .` exits zero for the packaged snapshot.
- [ ] `raes-pack-release check --pack .` checks `cage2-research`, reports the
      pack releasable, and exits zero without a skip.
- [ ] The freshly derived `pack.content-manifest.json` set digest matches the
      pinned digest used by the installed command, distribution probe, tests,
      and researcher walkthrough.
- [ ] The provenance ledger correctly covers the qualified CAGE source and
      evaluation material, RAES contracts, adapter-authored content, generated
      manifest, redistribution, attribution, and explicit exclusions.
- [ ] No native CybORG state, action id or class, reward vector, hidden truth,
      raw log, host path, environment or argument dump, credential, or full
      traceback appears in a portable or participant-visible artifact.
- [ ] The pack-local SDL is byte-identical to the reviewed full Scenario2
      module from issue #77 and its RAES module lock verifies.
- [ ] A clean installed `raes-adapters[cyborg]` command validates the exact
      declared pack, scenario, experiment, task, participant, control, and
      digest identities before native construction.
- [ ] Qualified native rehearsal, reset, cleanup, and portable evidence sealing
      pass for the same controls documented in `docs/researcher-command.md`.

## Final Manual Participant Walkthrough Protocol

- [ ] Read `docs/concepts.md` and `docs/attack-path.md`; confirm that they expose
      only portable Scenario2 intent and make no native or equivalence claim.
- [ ] Confirm the blue sleep-policy selection, manifest, and realized
      configuration agree and remain operator-only.
- [ ] Run the installed validation command from `docs/researcher-command.md`
      with its exact pack, scenario, experiment, task, participant, seed,
      trial-length, red-variant, and digest controls.
- [ ] In the qualified native source environment, run the matching smoke and
      study commands without substituting hidden defaults or alternate controls.
- [ ] Inspect only the sealed portable evidence and relative inventory; confirm
      no native output or host context crossed the boundary.
- [ ] Verify cleanup and that no reusable output directory or native session
      remains after the walkthrough.
- [ ] Record exactly which static, automated-native, and manual claims were
      proven, then set `pack.yaml.status: golden` only if every golden item is
      satisfied.
