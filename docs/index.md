# RAES adapters

This repository contains a single distribution, `raes-adapters`, that connects
concrete simulator backends to published RAES contracts. It ships shared base
plumbing plus backend modules whose dependencies can live behind separate
extras in one lock once qualified. The reserved `cyborg` extra remains empty
because the selected upstream source needs an unpublished packaging fix.
Backend-local qualification evidence ships fail-closed without making the
native simulator a base dependency.

The shared `raes_adapters.base` module provides plumbing only. RAES remains the
semantic and protocol authority.

## Start here

- [Repository overview](https://github.com/RAESystem/adapters#readme)
- [Contribution guide](https://github.com/RAESystem/adapters/blob/dev/CONTRIBUTING.md)
- [Architecture decisions](decisions/adrs/README.md)
- [CybORG/CAGE-2 runtime qualification guardrails](decisions/cyborg-cage2-runtime-qualification-guardrails.md)
- [CybORG/CAGE-2 source-ledger guardrails](decisions/cyborg-cage2-source-ledger-guardrails.md)
- [CyberBattleSim qualification guardrails](decisions/cyberbattlesim-qualification-guardrails.md)
- [CyberBattleSim scenario and source-ledger guardrails](decisions/cyberbattlesim-scenario-ledger-guardrails.md)
- [Project services](maintainers/project-services.md)

## Verify a checkout

Run the canonical verification graph from the repository root:

```shell
uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify -- --skip-requirement
```

The explicit skip is only for requirement-free maintenance. Requirement-scoped
work supplies its governing requirement UID through Ground Control.
