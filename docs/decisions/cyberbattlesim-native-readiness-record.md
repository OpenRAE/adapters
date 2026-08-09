# CyberBattleSim chain native-readiness record

Date: 2026-08-08
Issue: OpenRAE/adapters#29
Disposition: passing; pack status `built`

This record covers the real installed researcher path described in
[`cyberbattlesim-researcher-command.md`](../cyberbattlesim-researcher-command.md).
It is adapter-readiness evidence, not a golden-record, benchmark-comparability,
deterministic-replay, outcome-equivalence, or scientific-validity claim.

## Admitted identities

| Item | Admitted identity |
| --- | --- |
| Pack | `cyberbattlesim-chain` `1.0.0`, content digest `sha256:08ae7e997b50bb396c290c4a5537a65e9e7d8b8e6abc97d1ff65022c4258e417` |
| Scenario | canonical instantiated SDL digest `sha256:9d696ea7fa23a1e7cf4c1cbc145a7989370dc4e9afff2cd5a17d6d1af887b528` |
| Task/spec bytes | SHA-256 `6588ac115931b8de7052d52ccb94bbd258c5e6c78ffb9d5f5d1c0570f9236ce5` / `c31d2f4376ad7877d756e6a572a5e9e344b0899c4e8e996e1b5f57eaa78be391` |
| Participant | `cyberbattlesim-red-credential-cache`; manifest/selection/configuration SHA-256 `2ea827eb709a036b1721a91fabce787a320845bf26e3e6f0a0e5e768e7f9d93b` / `ce920ca6362b37e8cde6af12190ee9b84e9ea3c3fc89842d31366f0ec6031935` / `2b5e0fd0ef0be839af33763199e76192196a4928ca555a230af0f685c38eeced` |
| Native source | CyberBattleSim `0.1.0`, commit `854d6966607fb68645651f55b0f97221bd293e0d`, tree `4271b137ab2de593be52d7afb0a51bee59045a45`, complete `cyberbattle` root digest `1b8bf39a7cb9c172b51b5223dfac13b9d01e166b34dc2bb29297cddb254a06fe` |
| Runtime | CPython `3.12.3`, Gymnasium `0.29.1`, NumPy `1.26.4`, RAES `3.3.0`, `raes-env-packs` `3.6.2` |
| Installed adapter wheel | `raes_adapters-0.0.0-py3-none-any.whl`, SHA-256 `397739f17c736adb0e9e38ec217f70dde55fd6f4db3ce51d69625b4c30c76d35` |

## Executed gates and result

The isolated installed command reported native source admission available,
validated the exact external pack and participant joins, and executed smoke
mode with seed `20260729`, maximum `600` transitions, and the selected
`CredentialCacheExploiter` policy through RAES action admission and evaluation.
The source terminated after `151` transitions. The sanitized evaluator summary
reported cumulative attacker reward `5628`; one evidence record and one derived
measure were sealed.

Pack validation, the release check, installed-command validation, native
execution, inventory sealing, and cleanup all passed. The final inventory
SHA-256 is `a6fb3eea0af441ddade7c7df99a7d880241c976d15dd56ea614de7a2d6e188a6`.
A bounded scan of every sealed artifact found no host path, native sentinel, or
traceback. Native stdout and stderr were discarded by the command boundary.

The golden-readiness checklist remains unchecked. Advancing from `built` to
`golden` still requires its full manual participant-equivalent walkthrough and
durable golden evidence.
