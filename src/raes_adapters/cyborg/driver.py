"""Private in-process construction driver for the selected CybORG backend."""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import threading
from contextlib import suppress
from importlib import import_module, invalidate_caches
from importlib.machinery import PathFinder
from pathlib import Path
from typing import Any, Protocol, cast

from . import load_qualification
from .scenario import CyborgScenarioDescriptor, translate_scenario

_NATIVE_RANDOM_LOCK = threading.Lock()


class CyborgDriver(Protocol):
    """Backend-local driver seam; native handles never cross this protocol."""

    def construct(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
    ) -> object:
        """Construct and return one private native CybORG backend handle."""

    def cleanup(self, handle: object) -> bool:
        """Try to release one owned native handle idempotently."""


class SourceInstalledCyborgDriver:
    """Construct a generated scenario with a user-installed selected CybORG source."""

    def __init__(self, *, expected_version: str) -> None:
        self._expected_version = expected_version
        self._binding_lock = threading.Lock()
        self._runtime_workspace: tempfile.TemporaryDirectory[str] | None = None
        self._cyborg_type: Any = None

    def construct(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
    ) -> object:
        """Construct the selected backend while keeping native values private."""

        cyborg_type = self._native_binding()
        scenario = translate_scenario(descriptor)
        native: Any = None
        scenario_path: Path | None = None
        try:
            scenario_path = self._write_scenario(scenario)
            with _NATIVE_RANDOM_LOCK:
                random_state = random.getstate()
                try:
                    if seed is not None:
                        random.seed(seed)
                    native = cyborg_type(str(scenario_path), "sim")
                    if seed is not None:
                        native.set_seed(seed)
                    native.reset()
                finally:
                    random.setstate(random_state)
        except Exception:
            if native is not None:
                self.cleanup(native)
            raise RuntimeError("CybORG backend construction failed.") from None
        finally:
            if scenario_path is not None:
                scenario_path.unlink(missing_ok=True)
        return native

    @staticmethod
    def cleanup(handle: object) -> bool:
        """Shut down an owned CybORG backend without inspecting native output."""

        try:
            cast(Any, handle).shutdown()
        except Exception:
            return False
        return True

    def _native_binding(self) -> Any:
        """Load the constructor from a private snapshot of verified source bytes."""

        with self._binding_lock:
            if self._cyborg_type is not None:
                return self._cyborg_type
            package_root = self._resolve_verified_package_root()
            workspace = tempfile.TemporaryDirectory(prefix="raes-cyborg-runtime-")
            verified_root = Path(workspace.name) / "CybORG"
            try:
                shutil.copytree(
                    package_root,
                    verified_root,
                    ignore=shutil.ignore_patterns(
                        "__pycache__",
                        "*.pyc",
                        "*.pyo",
                        "*.so",
                        "*.pyd",
                        "*.dll",
                        "*.dylib",
                    ),
                )
                self._verify_selected_files(verified_root)
                self._verify_python_source_tree(verified_root)
                package = self._import_verified_snapshot(verified_root)
                version = str(package.CYBORG_VERSION)
                package_file = Path(str(package.__file__)).resolve()
                if package_file.parent != verified_root:
                    raise ValueError
                if version != self._expected_version:
                    raise RuntimeError(
                        "The installed CybORG backend version does not match the selected profile."
                    )
                cyborg_type = package.CybORG
            except RuntimeError:
                workspace.cleanup()
                raise
            except Exception:
                workspace.cleanup()
                raise RuntimeError(
                    "The selected CybORG backend is not installed through its documented "
                    "source route."
                ) from None
            self._runtime_workspace = workspace
            self._cyborg_type = cyborg_type
            return cyborg_type

    @staticmethod
    def _import_verified_snapshot(package_root: Path) -> Any:
        """Import only from the private source snapshot, never installed bytecode."""

        if any(name == "CybORG" or name.startswith("CybORG.") for name in sys.modules):
            raise RuntimeError(
                "CybORG was imported before the selected source snapshot was verified."
            )
        parent = str(package_root.parent)
        sys.path.insert(0, parent)
        invalidate_caches()
        try:
            package = cast(Any, import_module("CybORG"))
        finally:
            with suppress(ValueError):
                sys.path.remove(parent)
            invalidate_caches()
        return package

    @staticmethod
    def _write_scenario(scenario: dict[str, dict[str, object]]) -> Path:
        """Write one private canonical JSON document accepted by CybORG's YAML loader."""

        descriptor, raw_path = tempfile.mkstemp(prefix="raes-cyborg-", suffix=".json")
        path = Path(raw_path)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    scenario,
                    stream,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.write("\n")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path

    @classmethod
    def _resolve_verified_package_root(cls) -> Path:
        """Resolve and verify package bytes without executing CybORG code."""

        try:
            spec = PathFinder.find_spec("CybORG")
            if spec is None or spec.origin is None or spec.submodule_search_locations is None:
                raise ValueError
            package_file = Path(spec.origin).resolve()
            package_root = package_file.parent
            search_locations = {
                Path(location).resolve() for location in spec.submodule_search_locations
            }
            if (
                package_file.name != "__init__.py"
                or search_locations != {package_root}
                or not package_file.is_file()
            ):
                raise ValueError
        except Exception:
            raise RuntimeError(
                "The selected CybORG backend is not installed through its documented source route."
            ) from None
        cls._verify_selected_files(package_root)
        cls._verify_python_source_tree(package_root)
        return package_root

    @staticmethod
    def _verify_selected_files(package_root: Path) -> None:
        """Prove the installed runtime files match the maintainer-selected source."""

        prefix = "CybORG/CybORG/"
        selected = [
            item
            for item in load_qualification()["selected_files"]
            if str(item["path"]).startswith(prefix)
        ]
        for item in selected:
            relative = Path(str(item["path"]).removeprefix(prefix))
            candidate = (package_root / relative).resolve()
            valid = (
                not relative.is_absolute()
                and candidate.is_relative_to(package_root)
                and candidate.is_file()
            )
            if not valid or hashlib.sha256(candidate.read_bytes()).hexdigest() != item["sha256"]:
                raise RuntimeError(
                    "The installed CybORG backend source does not match the selected profile."
                )

    @staticmethod
    def _verify_python_source_tree(package_root: Path) -> None:
        """Verify every importable CybORG source file before package execution."""

        try:
            integrity = load_qualification()["runtime"]["integrity"]
            expected_count = int(integrity["python_source_count"])
            expected_digest = str(integrity["python_source_tree_sha256"])
            files = sorted(
                package_root.rglob("*.py"),
                key=lambda path: path.relative_to(package_root).as_posix(),
            )
            digest = hashlib.sha256()
            for path in files:
                resolved = path.resolve()
                if not resolved.is_relative_to(package_root) or not resolved.is_file():
                    raise ValueError
                relative = path.relative_to(package_root).as_posix()
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(hashlib.sha256(resolved.read_bytes()).digest())
            valid = len(files) == expected_count and digest.hexdigest() == expected_digest
        except Exception:
            valid = False
        if not valid:
            raise RuntimeError(
                "The installed CybORG backend source does not match the selected profile."
            )


__all__ = [
    "CyborgDriver",
    "SourceInstalledCyborgDriver",
]
