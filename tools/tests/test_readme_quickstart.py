from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.check_readme_quickstart import (
    ContractError,
    load_quickstart_contract,
    parse_quickstart_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _readme(*, run_command: str | None = None) -> str:
    command = run_command or (
        "raes-adapters run --mode conformance --suite pr --output cage2-quickstart"
    )
    summary = {
        "disposition": "succeeded",
        "evidence_basis": "hermetic-live",
        "inventory": "inventory.json",
        "mode": "conformance",
        "run_count": 1,
    }
    return f"""\
<!-- readme-quickstart:install -->
```shell
python -m pip install 'raes-adapters[cyborg]'
```

<!-- readme-quickstart:run -->
```shell
{command}
```

<!-- readme-quickstart:output -->
```json
{json.dumps(summary, separators=(",", ":"))}
```

<!-- readme-quickstart:artifacts -->
```text
cage2-quickstart/index.json
cage2-quickstart/inventory.json
cage2-quickstart/runs/cyborg-pr-seed-3/conformance/backend-conformance.json
```
"""


class ReadmeQuickstartTests(unittest.TestCase):
    def test_contract_admits_only_the_documented_closed_commands(self) -> None:
        contract = parse_quickstart_contract(_readme())

        self.assertEqual(
            ("python", "-m", "pip", "install", "raes-adapters[cyborg]"),
            contract.install_argv,
        )
        self.assertEqual(
            (
                "raes-adapters",
                "run",
                "--mode",
                "conformance",
                "--suite",
                "pr",
                "--output",
                "cage2-quickstart",
            ),
            contract.run_argv,
        )
        self.assertEqual("hermetic-live", contract.expected_output["evidence_basis"])
        self.assertEqual(
            (
                "cage2-quickstart/index.json",
                "cage2-quickstart/inventory.json",
                "cage2-quickstart/runs/cyborg-pr-seed-3/conformance/backend-conformance.json",
            ),
            contract.expected_artifacts,
        )

    def test_contract_rejects_shell_syntax_and_output_escape(self) -> None:
        for command in (
            "raes-adapters run --mode conformance --suite pr --output evidence && whoami",
            "raes-adapters run --mode conformance --suite pr --output ../evidence",
            "raes-adapters run --mode conformance --suite pr --output /tmp/evidence",
        ):
            with self.subTest(command=command), self.assertRaises(ContractError):
                parse_quickstart_contract(_readme(run_command=command))

    def test_contract_requires_one_of_each_explicit_marker(self) -> None:
        with self.assertRaises(ContractError):
            parse_quickstart_contract(_readme().replace("<!-- readme-quickstart:output -->", ""))
        with self.assertRaises(ContractError):
            parse_quickstart_contract(_readme() + _readme())

    def test_repository_readme_exposes_the_checked_contract(self) -> None:
        contract = load_quickstart_contract(REPO_ROOT / "README.md")

        self.assertEqual("cage2-quickstart", contract.output_root.as_posix())
        self.assertEqual(1, contract.expected_output["run_count"])

    def test_contract_can_be_loaded_from_an_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(_readme(), encoding="utf-8")

            self.assertEqual(
                "cage2-quickstart",
                load_quickstart_contract(readme).output_root.as_posix(),
            )


if __name__ == "__main__":
    unittest.main()
