# RAES adapters

This repository contains a single distribution, `raes-adapters`, that connects
concrete simulator backends to published RAES contracts. It ships shared base
plumbing plus backend modules whose dependencies can live behind separate
extras in one lock. Maintainer-selected backends are admitted; backend-local
qualification evidence records attainable claim strength and limitations. The
`cyborg` and `cyberbattlesim` extras are dependency-light because their selected
native sources have no governed publishable artifact, so users acquire those
simulators separately and the base install remains independent. The admitted
CybORG backend is supported through its documented source installation despite
the absence of an automatically installed native simulator; its extra installs
the published environment-pack validator used by the researcher command.

The shared `raes_adapters.base` module provides plumbing only. RAES remains the
semantic and protocol authority.

## Start here

- [Repository overview](https://github.com/RAESystem/adapters#readme)
- [Installed researcher command](researcher-command.md)
- [Contribution guide](https://github.com/RAESystem/adapters/blob/dev/CONTRIBUTING.md)
- [Architecture decisions](decisions/adrs/README.md)
- [CybORG/CAGE-2 backend qualification guardrails](decisions/cyborg-cage2-runtime-qualification-guardrails.md)
- [CybORG/CAGE-2 source-ledger guardrails](decisions/cyborg-cage2-source-ledger-guardrails.md)
- [CybORG/CAGE-2 provisioner and backend-manifest guardrails](decisions/cyborg-cage2-provisioner-manifest-guardrails.md)
- [CybORG conformance-composition guardrails](decisions/cyborg-conformance-guardrails.md)
- [CybORG researcher run-and-evidence command guardrails](decisions/cyborg-researcher-command-guardrails.md)
- [CyberBattleSim qualification guardrails](decisions/cyberbattlesim-qualification-guardrails.md)
- [PrimAITE qualification guardrails](decisions/primaite-qualification-guardrails.md)
- [CyberBattleSim scenario and source-ledger guardrails](decisions/cyberbattlesim-scenario-ledger-guardrails.md)
- [CyberBattleSim backend architecture guardrails](decisions/cyberbattlesim-backend-guardrails.md)
- [CyberBattleSim conformance-composition guardrails](decisions/cyberbattlesim-conformance-guardrails.md)
- [Project services](maintainers/project-services.md)

## Verify a checkout

Run the canonical verification graph from the repository root:

```shell
uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify -- --skip-requirement
```

The explicit skip is only for requirement-free maintenance. Requirement-scoped
work supplies its governing requirement UID through Ground Control.
