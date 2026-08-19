# RAES adapters

`raes-adapters` connects concrete simulator backends to published RAES
contracts. Start with the installed conformance quickstart, then select the
researcher command or evidence recipe that matches the claim you need to make.
Scenario validity, adapter conformance, native run completion, and scientific
evidence are separate boundaries.

## Start here

- [Repository overview](https://github.com/OpenRAE/adapters#readme)
- [Researcher guide](researcher-guide.md)
- [Installed researcher command](researcher-command.md)
- [Offline bundle verifier](bundle-verifier.md)
- [NASim researcher command](nasim-researcher-command.md)
- [CyberBattleSim researcher command](cyberbattlesim-researcher-command.md)
- [CyberBattleSim baseline reproduction](cyberbattlesim-baseline-reproduction.md)
- [Contribution guide](https://github.com/OpenRAE/adapters/blob/dev/CONTRIBUTING.md)
- [Developer index](maintainers/index.md)
- [Architecture decisions](decisions/adrs/README.md)
- [CybORG/CAGE-2 backend qualification guardrails](decisions/cyborg-cage2-runtime-qualification-guardrails.md)
- [CybORG/CAGE-2 source-ledger guardrails](decisions/cyborg-cage2-source-ledger-guardrails.md)
- [CybORG/CAGE-2 Scenario2 SDL guardrails](decisions/cyborg-cage2-scenario2-sdl-guardrails.md)
- [CybORG/CAGE-2 provisioner and backend-manifest guardrails](decisions/cyborg-cage2-provisioner-manifest-guardrails.md)
- [CybORG conformance-composition guardrails](decisions/cyborg-conformance-guardrails.md)
- [CybORG researcher run-and-evidence command guardrails](decisions/cyborg-researcher-command-guardrails.md)
- [CybORG/CAGE-2 protocol-reproduction guardrails](decisions/cyborg-cage2-protocol-reproduction-guardrails.md)
- [Offline evidence-bundle verifier guardrails](decisions/offline-bundle-verifier-guardrails.md)
- [CybORG/CAGE-2 downstream environment-pack guardrails](decisions/cyborg-cage2-example-pack-guardrails.md)
- [NASim researcher run-and-evidence command guardrails](decisions/nasim-researcher-command-guardrails.md)
- [CyberBattleSim qualification guardrails](decisions/cyberbattlesim-qualification-guardrails.md)
- [PrimAITE qualification guardrails](decisions/primaite-qualification-guardrails.md)
- [PrimAITE scenario and source-ledger guardrails](decisions/primaite-scenario-ledger-guardrails.md)
- [PrimAITE backend architecture guardrails](decisions/primaite-backend-guardrails.md)
- [PrimAITE conformance-composition guardrails](decisions/primaite-conformance-guardrails.md)
- [NASim qualification guardrails](decisions/nasim-qualification-guardrails.md)
- [NASim scenario and source-ledger guardrails](decisions/nasim-scenario-ledger-guardrails.md)
- [NASim backend architecture guardrails](decisions/nasim-backend-guardrails.md)
- [NASim conformance-composition guardrails](decisions/nasim-conformance-guardrails.md)
- [CyberBattleSim scenario and source-ledger guardrails](decisions/cyberbattlesim-scenario-ledger-guardrails.md)
- [CyberBattleSim backend architecture guardrails](decisions/cyberbattlesim-backend-guardrails.md)
- [CyberBattleSim conformance-composition guardrails](decisions/cyberbattlesim-conformance-guardrails.md)
- [CyberBattleSim environment-pack and researcher-command guardrails](decisions/cyberbattlesim-researcher-command-guardrails.md)
- [CyberBattleSim baseline-reproduction guardrails](decisions/cyberbattlesim-baseline-reproduction-guardrails.md)
- [CyberBattleSim first-release guardrails](decisions/cyberbattlesim-release-guardrails.md)
- [CyberBattleSim chain native-readiness record](decisions/cyberbattlesim-native-readiness-record.md)
- [Project services](maintainers/project-services.md)

## Verify a checkout

Run the canonical verification graph from the repository root:

```shell
uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify -- --skip-requirement
```

The explicit skip is only for requirement-free maintenance. Requirement-scoped
work supplies its governing requirement UID through Ground Control.
