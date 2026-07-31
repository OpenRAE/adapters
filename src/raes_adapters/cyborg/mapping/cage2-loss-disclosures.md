# CAGE-2 → RAES loss disclosures

These disclosures accompany the source selection
`cage2-cyborg-2.1-source-26ce1c1`. Each heading is a stable ledger reference;
the machine-readable tier line binds the precise ADR-069 claim tiers weakened.
A disclosure permits a bounded claim with the stated weakness. It does not
erase a qualification limitation, prevent use of the selected backend, or
establish any equivalence tier.

## loss-scenario-user3-port-mismatch

**Equivalence tiers weakened:** authored-source, state/observation

The pinned `linux_user_host_image1.yaml` uses local port 3389 for the User3
SQL-injection path, while the maintained successor documents 3390. The ledger
preserves the selected bytes and flags the conflict. A later authored scenario
must choose and justify one value; it cannot claim exact source and
state/observation equivalence for both.

## loss-native-observation-boundary

**Equivalence tiers weakened:** contract, state/observation

CybORG exposes mutable native observation and true-state dictionaries,
simulator enums, process/session records, and wrapper arrays. RAES can carry
bounded visibility projections, observation references, redaction policy, and
evidence references, but those native values and representations are
deliberately not portable. Exact native-payload identity is therefore not a
permitted contract or state/observation claim.

## loss-remove-success-misreport

**Equivalence tiers weakened:** state/observation, outcome/evaluation

The selected `Remove` implementation initializes a successful observation even
when no suspicious process is removed. The mapping records the intended
defensive action and retains the defect; it does not silently reinterpret the
native success flag as an observed state transition or successful outcome.

## loss-wrapper-cutoff-semantics

**Equivalence tiers weakened:** execution-control

`ChallengeWrapper.max_steps` forces its legacy `done` flag when the wrapper
counter reaches the bound. That cutoff is distinct from a source terminal
condition, evaluator trial length, Gym truncation, participant action count,
and cleanup. Until an experiment contract binds those facts separately, an
exact execution-control claim is not permitted.

## loss-evaluation-seed-unbound

**Equivalence tiers weakened:** execution-control, outcome/evaluation

The pinned evaluator does not bind simulator, Python, NumPy, Gym action-space,
or blue-policy random streams. The qualification smoke's seed 3 is a different
two-step source-native probe and cannot fill this gap. Evaluation results
therefore cannot support deterministic execution-control or reproducible
outcome/evaluation claims.

## loss-blue-policy-artifact-unbound

**Equivalence tiers weakened:** authored-source, execution-control, outcome/evaluation

The evaluator instantiates `BlueLoadAgent` without an immutable trained model
artifact. Its fallback creates a fresh PPO policy against Scenario1b, not the
selected Scenario2 evaluation condition. The blue implementation, model bytes,
training provenance, and stochastic state are unbound, so policy-dependent
source, execution, and outcome claims remain unsupported.
