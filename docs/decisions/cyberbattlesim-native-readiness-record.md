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

## Baseline reproduction evidence — 2026-08-10

Issue [OpenRAE/adapters#30](https://github.com/OpenRAE/adapters/issues/30)
executed the exact source-native and installed RAES-mediated paths from an
offline CPython 3.12.3 environment on four x86-64 vCPUs with 16 GiB RAM. The
apparatus used implementation commit
`bf1cbff7bfeace506324910651697ef7b00b5de6`, adapter wheel SHA-256
`52550a728936151208dd6875b5112b274edd9e3b93e844e34f34497026aa1808`,
and upstream wheel SHA-256
`d921703d77b82f14aeaff223cfeaf3753916b1518119d474dfd5e4444170b9a5`.
The admitted pack digest was
`sha256:66493882579d5cba87248c5722782ff5ded5f0d7423f4e559f15bfb61712a905`.

The accepted declaration is
`f09ec5759021cf1d5de9b260e0299934bf6f6cc4161b822e8f5f0b76bdb96b53`.
All ten source-native and ten mediated attempts terminalized valid with cleanup
verified and zero retries. The final 128-file bundle passed structural leakage
scanning, contract validation, digest-bound citation validation, inventory
verification, and independent offline recomputation. Its inventory file
SHA-256 is
`4653bc5afbf501f005f997df782f73f282cccbe28f9cbe176d5a9c3f5970a292`.

The scientific result is deliberately not described as passing overall:

| Tier or metric | Result |
| --- | --- |
| Authored source / contract / disclosure | passed / passed / passed |
| Execution control / state-observation | weakened / weakened |
| Outcome-evaluation | failed |
| Cumulative reward | bounded; mean difference 19.2, 95% interval `[-91.8025, 130.1025]` within ±500 |
| Steps to termination | outside tolerance; mean difference 33.5, 95% interval `[-55.0, 119.5]` exceeds ±60 |
| Availability / terminal cause | unavailable because the mediated evaluator does not retain them |

The first 20-attempt series remains retained under declaration
`825dde3b4cd66f228e0f93157a2add35e3c9a822a7adac1d8ffd322b32116232`
with a machine-readable rejection record. Its bound byte scanner could not
distinguish RAES `withheld_refs` names from native values, so its criteria and
scanner were not edited in place; the accepted revision used disjoint
identities and unchanged scientific conditions.

## Corrective baseline reproduction — 2026-08-11

Revision 3 ran from implementation commit
`e5d6aff625047037f5a94a9635d92966413055b7` using the exact adapter wheel with
SHA-256
`150c3b69a91d766d7863feb01e443257ad646e7f9cddcb2727a58c8c6137793d`.
Its declaration is
`c588a174ab97ef1e4d863b743a02213e9527b7731cfbdc897d6602d72362bebf`.
All ten source-native and ten mediated attempts terminalized valid with zero
retries. The final 138-file bundle passes independent offline recomputation,
evidence-reference and citation checks, the bounded leakage scan, regular-tree
checks, and inventory verification. Its `inventory.json` SHA-256 is
`20eec98ff44f09e3b3466e0c57af2a960cf9886cdfcd9d5add5f5392172fa8dd`.

Revision 3 corrected the apparatus defects without changing the frozen
tolerances or stochastic bindings: the mediated lane now retains one
checksum-bound sanitized availability/cause artifact per episode and carries
the upstream evaluator's cumulative epsilon-step schedule across its isolated
processes. The observed result is:

| Tier or metric | Result |
| --- | --- |
| Authored source / contract / disclosure | passed / passed / passed |
| Execution control / state-observation | weakened / weakened |
| Outcome-evaluation | failed |
| Cumulative reward | outside tolerance; mean difference `-488.6`, 95% interval `[-1558.015, 90.6]` exceeds +/-500 |
| Steps to termination | outside tolerance; mean difference `51.4`, 95% interval `[-48.5, 153.8025]` exceeds +/-60 |
| Mean availability | bounded; mean difference `-0.0008853231676272388`, 95% interval `[-0.010524172216097161, 0.00887836373877486]` within +/-0.05 |
| Terminal cause | bounded; source `defender-sla` proportion `1.0`, mediated `0.9` plus `0.1` evaluator cutoff, within +/-0.10 |

One mediated attempt reached the declared 600-step cutoff with cumulative
reward `512`; the other nine mediated attempts average about `258.8` steps and
`5699.2` reward. This single retained row drives both interval failures. It was
not excluded or retried. Because the compared paths have explicitly different
and partly unbound random-stream dispositions, the exact path is not
deterministically attributable. The result supports readiness and research
diagnosis, but not outcome equivalence; a stronger claim requires a separately
declared stochastic-control and sample-size design.

Together, these records supply the CyberBattleSim apparatus/readiness slice for
[OpenRAE/research#14](https://github.com/OpenRAE/research/issues/14) and the
content-addressed, recomputable publication slice for
[OpenRAE/research#20](https://github.com/OpenRAE/research/issues/20). It does
not by itself close corpus-wide readiness, complete the paper, assign a
persistent identifier, mark the environment pack golden, or establish
deterministic replay or outcome equivalence.
