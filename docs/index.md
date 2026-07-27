# RAES adapters

This repository contains independent adapter projects that connect concrete
simulator backends to published RAES contracts. Each adapter owns its dependency
environment and lockfile so incompatible simulator dependencies remain isolated.

The shared `sim_adapter_base` package provides plumbing only. RAES remains the
semantic and protocol authority.

## Start here

- [Repository overview](https://github.com/RAESystem/adapters#readme)
- [Contribution guide](https://github.com/RAESystem/adapters/blob/dev/CONTRIBUTING.md)
- [Architecture decisions](decisions/adrs/README.md)
- [Project services](maintainers/project-services.md)

## Verify a checkout

Run the canonical verification graph from the repository root:

```shell
uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify -- --skip-requirement
```

The explicit skip is only for requirement-free maintenance. Requirement-scoped
work supplies its governing requirement UID through Ground Control.
