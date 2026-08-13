"""Parity checks for shared private inventory producer plumbing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from raes_adapters import cli
from raes_adapters._inventory import inventory_document, inventory_entry
from raes_adapters.cyborg import reproduction


def _entry(path: str, content: bytes, media_type: str) -> dict[str, object]:
    return {
        "media_type": media_type,
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _canonical_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def test_generic_producer_wrapper_preserves_exact_inventory_bytes(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    json_content = b'{"value":1}\n'
    binary_content = b"\x00portable"
    (nested / "record.json").write_bytes(json_content)
    (tmp_path / "artifact.bin").write_bytes(binary_content)
    expected = {
        "artifacts": [
            _entry("artifact.bin", binary_content, "application/octet-stream"),
            _entry("nested/record.json", json_content, "application/json"),
        ]
    }

    assert cli._seal_inventory(tmp_path) == expected
    assert (tmp_path / "inventory.json").read_bytes() == _canonical_bytes(expected)


def test_cyborg_compatibility_wrappers_preserve_media_types_and_bytes(tmp_path: Path) -> None:
    markdown_content = b"# Result\n"
    gzip_content = b"compressed"
    markdown = tmp_path / "report.md"
    compressed = tmp_path / "attempt.json.gz"
    markdown.write_bytes(markdown_content)
    compressed.write_bytes(gzip_content)
    expected = {
        "artifacts": [
            _entry("attempt.json.gz", gzip_content, "application/gzip"),
            _entry("report.md", markdown_content, "text/markdown"),
        ]
    }

    assert reproduction._inventory_entry(tmp_path, compressed) == expected["artifacts"][0]
    assert reproduction._seal_inventory(tmp_path, [markdown, compressed]) == expected
    assert (tmp_path / "inventory.json").read_bytes() == _canonical_bytes(expected)


def test_private_primitives_have_no_simulator_or_contract_authority(tmp_path: Path) -> None:
    artifact = tmp_path / "record.json"
    artifact.write_bytes(b"{}\n")

    assert inventory_entry(tmp_path, artifact)["path"] == "record.json"
    assert inventory_document(tmp_path, [artifact]) == {
        "artifacts": [inventory_entry(tmp_path, artifact)]
    }

    source = (Path(__file__).parents[1] / "src/raes_adapters/_inventory.py").read_text(
        encoding="utf-8"
    )
    assert "raes_" not in source
    assert "cyborg" not in source.casefold()
    assert "nasim" not in source.casefold()
    assert "cyberbattlesim" not in source.casefold()
