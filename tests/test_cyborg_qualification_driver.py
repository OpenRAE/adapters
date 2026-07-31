from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.verify_cyborg_qualification import (
    normalized_wheel_sha256,
    python_source_tree_identity,
    sanitized_subprocess_env,
    validate_adapter_smoke,
    validate_reproducer_runtime,
    validate_smoke,
)


class NormalizedWheelDigestTests(unittest.TestCase):
    def test_zip_timestamps_do_not_change_normalized_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.whl"
            second = root / "second.whl"
            for path, timestamp in (
                (first, (2020, 1, 1, 0, 0, 0)),
                (second, (2026, 7, 30, 0, 0, 0)),
            ):
                with zipfile.ZipFile(path, "w") as archive:
                    info = zipfile.ZipInfo("CybORG/version.txt", timestamp)
                    archive.writestr(info, "2.1\n")

            self.assertEqual(
                normalized_wheel_sha256(first),
                normalized_wheel_sha256(second),
            )


class PythonSourceTreeIdentityTests(unittest.TestCase):
    def test_initializer_and_nested_runtime_sources_are_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "__init__.py").write_text("VERSION = '2.1'\n", encoding="utf-8")
            nested = root / "Agents"
            nested.mkdir()
            runtime = nested / "runtime.py"
            runtime.write_text("ACTIVE = True\n", encoding="utf-8")

            count, original = python_source_tree_identity(root)
            runtime.write_text("ACTIVE = False\n", encoding="utf-8")
            changed_count, changed = python_source_tree_identity(root)

            self.assertEqual(count, 2)
            self.assertEqual(changed_count, 2)
            self.assertNotEqual(original, changed)


class SanitizedEnvironmentTests(unittest.TestCase):
    def test_only_non_secret_process_inputs_are_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = os.environ.get("QUALIFICATION_TEST_TOKEN")
            os.environ["QUALIFICATION_TEST_TOKEN"] = "must-not-propagate"
            try:
                environment = sanitized_subprocess_env(root)
            finally:
                if previous is None:
                    os.environ.pop("QUALIFICATION_TEST_TOKEN", None)
                else:
                    os.environ["QUALIFICATION_TEST_TOKEN"] = previous

            self.assertNotIn("QUALIFICATION_TEST_TOKEN", environment)
            self.assertEqual(environment["HOME"], str(root / "home"))
            self.assertEqual(environment["UV_CACHE_DIR"], str(root / "uv-cache"))
            self.assertEqual(environment["PYTHONPATH"], "")
            self.assertEqual(environment["PYTHONSAFEPATH"], "1")
            self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")


class SmokeValidationTests(unittest.TestCase):
    def test_exact_bounded_structural_result_passes(self) -> None:
        expected = {
            "seed": 3,
            "step_count": 2,
            "done_sequence": [False, True],
            "role_actions": {"blue": ["Sleep", "Sleep"]},
        }
        validate_smoke(dict(expected), expected)

    def test_native_state_or_shape_drift_fails(self) -> None:
        expected = {"seed": 3, "step_count": 2}

        with self.assertRaisesRegex(RuntimeError, "smoke result"):
            validate_smoke({"seed": 3, "step_count": 2, "native_state": {}}, expected)
        with self.assertRaisesRegex(RuntimeError, "smoke result"):
            validate_smoke({"seed": 3, "step_count": 3}, expected)

    def test_adapter_smoke_accepts_only_bounded_construction_and_cleanup(self) -> None:
        expected = {
            "backend": "cyborg-cage2",
            "constructed": True,
            "cleaned": True,
            "recorded_resources": 2,
            "realization_recorded": True,
        }

        validate_adapter_smoke(dict(expected), expected)

        with self.assertRaisesRegex(RuntimeError, "adapter smoke"):
            validate_adapter_smoke(
                {**expected, "native_handle": "must-not-cross"},
                expected,
            )


class RuntimeValidationTests(unittest.TestCase):
    evidence = {
        "python": "3.12.3",
        "platform": {
            "system": "Linux",
            "kernel": "6.8.0-117-generic",
            "machine": "x86_64",
            "libc": "glibc-2.39",
        },
    }

    def test_same_runtime_family_accepts_ci_patch_and_kernel_variation(self) -> None:
        validate_reproducer_runtime(
            actual_python="3.12.11",
            actual_platform={
                "system": "Linux",
                "kernel": "6.11.0-1018-azure",
                "machine": "x86_64",
                "libc": "glibc-2.39",
            },
            evidence_runtime=self.evidence,
        )

    def test_different_python_or_platform_family_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "runtime is incompatible"):
            validate_reproducer_runtime(
                actual_python="3.13.1",
                actual_platform={
                    "system": "Linux",
                    "kernel": "6.8.0",
                    "machine": "x86_64",
                    "libc": "glibc-2.39",
                },
                evidence_runtime=self.evidence,
            )
        with self.assertRaisesRegex(RuntimeError, "runtime is incompatible"):
            validate_reproducer_runtime(
                actual_python="3.12.3",
                actual_platform={
                    "system": "Darwin",
                    "kernel": "25.0.0",
                    "machine": "arm64",
                    "libc": "libSystem",
                },
                evidence_runtime=self.evidence,
            )


if __name__ == "__main__":
    unittest.main()
