"""Adversarial checks for the installed offline bundle verifier."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from raes_adapters import bundle_verifier
from raes_adapters.entrypoint import main


def _entry(
    path: str, content: bytes, media_type: str = "application/octet-stream"
) -> dict[str, object]:
    return {
        "media_type": media_type,
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _write_inventory(root: Path, entries: list[dict[str, object]]) -> None:
    (root / "inventory.json").write_text(
        json.dumps({"artifacts": entries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_flat_bundle_and_all_renderers_are_deterministic(tmp_path: Path) -> None:
    payload = b"bounded evidence\n"
    (tmp_path / "evidence.bin").write_bytes(payload)
    _write_inventory(tmp_path, [_entry("evidence.bin", payload)])

    card = bundle_verifier.verify_bundle(tmp_path)

    assert card.status == "verified"
    assert bundle_verifier.render_card(card, "json") == bundle_verifier.render_card(card, "json")
    assert "integrity-only" in bundle_verifier.render_card(card, "terminal")
    assert "Semantic fidelity: not assessed" in bundle_verifier.render_card(card, "markdown")


def test_transitive_inventory_closure_is_verified(tmp_path: Path) -> None:
    child = tmp_path / "run"
    child.mkdir()
    evidence = b"{}\n"
    (child / "evidence.json").write_bytes(evidence)
    _write_inventory(child, [_entry("evidence.json", evidence, "application/json")])
    child_inventory = (child / "inventory.json").read_bytes()
    _write_inventory(
        tmp_path,
        [_entry("run/inventory.json", child_inventory, "application/json")],
    )

    card = bundle_verifier.verify_bundle(tmp_path)

    assert card.inventories == 2
    assert card.entries == 2


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("tamper", "bundle.inventory.member-mismatch"),
        ("extra", "bundle.inventory.membership-mismatch"),
        ("missing", "bundle.inventory.member-missing"),
        ("traversal", "bundle.inventory.path-invalid"),
        ("duplicate", "bundle.inventory.duplicate-path"),
    ],
)
def test_invalid_membership_and_tampering_are_rejected(
    tmp_path: Path, mutation: str, code: str
) -> None:
    payload = b"evidence"
    (tmp_path / "item").write_bytes(payload)
    entries = [_entry("item", payload)]
    if mutation == "tamper":
        entries[0]["sha256"] = "0" * 64
    elif mutation == "extra":
        (tmp_path / "extra").write_bytes(b"x")
    elif mutation == "missing":
        entries[0]["path"] = "absent"
    elif mutation == "traversal":
        entries[0]["path"] = "../item"
    elif mutation == "duplicate":
        entries.append(dict(entries[0]))
    _write_inventory(tmp_path, entries)

    with pytest.raises(bundle_verifier.BundleInvalid, match=code):
        bundle_verifier.verify_bundle(tmp_path)


def test_symlink_is_rejected_even_when_not_in_inventory(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.write_bytes(b"outside")
    (tmp_path / "link").symlink_to(outside)
    _write_inventory(tmp_path, [])

    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.filesystem.symlink"):
        bundle_verifier.verify_bundle(tmp_path)


def test_entrypoint_uses_documented_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_inventory(tmp_path, [])
    assert main(["verify-bundle", "--bundle", str(tmp_path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified"

    (tmp_path / "extra").write_bytes(b"x")
    assert main(["verify-bundle", "--bundle", str(tmp_path)]) == 3
    assert "status: invalid" in capsys.readouterr().out
    assert main(["verify-bundle"]) == 2
    assert "usage.invalid" in capsys.readouterr().err


def test_verify_dispatch_does_not_import_simulator_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inventory(tmp_path, [])
    imported: list[str] = []
    original = __import__

    def guarded(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith(("CybORG", "cyberbattle", "nasim")):
            imported.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded)
    assert main(["verify-bundle", "--bundle", str(tmp_path)]) == 0
    assert imported == []


def test_fixed_admission_limits_match_the_public_contract() -> None:
    assert bundle_verifier.MAX_FILES == 100_000
    assert bundle_verifier.MAX_INVENTORIES == 100_000
    assert bundle_verifier.MAX_ENTRIES == 200_000
    assert bundle_verifier.MAX_UNIQUE_BYTES == 4 * 1024**3
    assert bundle_verifier.MAX_ARTIFACT_BYTES == 500 * 1024
    assert bundle_verifier.MAX_INVENTORY_BYTES == 16 * 1024**2
    assert bundle_verifier.MAX_DEPTH == 32
    assert bundle_verifier.MAX_PATH_BYTES == 1_024


@pytest.mark.parametrize(
    ("limit", "value", "code"),
    [
        ("MAX_FILES", 0, "bundle.limit.files"),
        ("MAX_INVENTORIES", 0, "bundle.limit.inventories"),
        ("MAX_ENTRIES", 0, "bundle.limit.entries"),
        ("MAX_UNIQUE_BYTES", 0, "bundle.limit.unique-bytes"),
        ("MAX_ARTIFACT_BYTES", 0, "bundle.limit.artifact-bytes"),
        ("MAX_INVENTORY_BYTES", 0, "bundle.limit.inventory-bytes"),
        ("MAX_DEPTH", 0, "bundle.limit.depth"),
        ("MAX_PATH_BYTES", 1, "bundle.inventory.path-invalid"),
    ],
)
def test_every_admission_limit_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit: str,
    value: int,
    code: str,
) -> None:
    payload = b"x"
    (tmp_path / "item").write_bytes(payload)
    _write_inventory(tmp_path, [_entry("item", payload)])
    monkeypatch.setattr(bundle_verifier, limit, value)

    with pytest.raises(bundle_verifier.BundleInvalid, match=code):
        bundle_verifier.verify_bundle(tmp_path)


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        b'{"artifacts":{},"extra":1}',
        b'{"artifacts":{}}',
        b'{"artifacts":[],"artifacts":[]}',
    ],
)
def test_malformed_inventories_are_rejected(tmp_path: Path, payload: bytes) -> None:
    (tmp_path / "inventory.json").write_bytes(payload)

    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.inventory"):
        bundle_verifier.verify_bundle(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("media_type", ""),
        ("size_bytes", True),
        ("size_bytes", -1),
        ("sha256", "A" * 64),
        ("sha256", "0" * 63),
        ("path", "/item"),
        ("path", "../item"),
        ("path", "./item"),
        ("path", "item\\other"),
        ("path", "item//other"),
        ("path", "item\x00suffix"),
    ],
)
def test_malformed_inventory_entries_are_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    payload = b"x"
    (tmp_path / "item").write_bytes(payload)
    entry = _entry("item", payload)
    entry[field] = value
    _write_inventory(tmp_path, [entry])

    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.inventory"):
        bundle_verifier.verify_bundle(tmp_path)


def test_inventory_entry_requires_exact_keys(tmp_path: Path) -> None:
    payload = b"x"
    (tmp_path / "item").write_bytes(payload)
    entry = _entry("item", payload)
    del entry["media_type"]
    _write_inventory(tmp_path, [entry])

    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.inventory.entry-malformed"):
        bundle_verifier.verify_bundle(tmp_path)


def test_special_files_are_rejected(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable")
    os.mkfifo(tmp_path / "pipe")
    _write_inventory(tmp_path, [])

    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.filesystem.special-file"):
        bundle_verifier.verify_bundle(tmp_path)


def test_root_must_be_a_real_directory_with_an_inventory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.root.invalid"):
        bundle_verifier.verify_bundle(missing)

    regular = tmp_path / "regular"
    regular.write_bytes(b"x")
    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.root.invalid"):
        bundle_verifier.verify_bundle(regular)

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.inventory.missing"):
        bundle_verifier.verify_bundle(empty)

    target = tmp_path / "target"
    target.mkdir()
    _write_inventory(target, [])
    root_link = tmp_path / "root-link"
    root_link.symlink_to(target, target_is_directory=True)
    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.root.invalid"):
        bundle_verifier.verify_bundle(root_link)


def test_mutation_during_hashing_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inventory(tmp_path, [])
    original = bundle_verifier._identity
    calls = 0

    def changing_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
        nonlocal calls
        calls += 1
        identity = original(info)
        if calls == 5:
            return (*identity[:-1], identity[-1] + 1)
        return identity

    monkeypatch.setattr(bundle_verifier, "_identity", changing_identity)
    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.filesystem.mutated"):
        bundle_verifier.verify_bundle(tmp_path)


def test_files_added_while_hashing_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inventory(tmp_path, [])
    original = bundle_verifier._inventory_payload

    def mutate(record: bundle_verifier._FileRecord) -> list[object]:
        result = original(record)
        (tmp_path / "late-file").write_bytes(b"late")
        return result

    monkeypatch.setattr(bundle_verifier, "_inventory_payload", mutate)
    with pytest.raises(bundle_verifier.BundleInvalid, match="bundle.filesystem.mutated"):
        bundle_verifier.verify_bundle(tmp_path)


def test_verification_is_read_only(tmp_path: Path) -> None:
    payload = b"evidence"
    (tmp_path / "item").write_bytes(payload)
    _write_inventory(tmp_path, [_entry("item", payload)])
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()
    }

    bundle_verifier.verify_bundle(tmp_path)

    after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()}
    assert after == before


def test_cards_are_stable_and_disclose_only_integrity(tmp_path: Path) -> None:
    _write_inventory(tmp_path, [])
    card = bundle_verifier.verify_bundle(tmp_path)
    counts = card.payload()["counts"]
    assert isinstance(counts, dict)
    assert bundle_verifier.render_card(card, "json") == json.dumps(
        card.payload(), sort_keys=True, separators=(",", ":")
    )
    assert bundle_verifier.render_card(card, "terminal") == "\n".join(
        (
            "status: verified",
            "code: bundle.integrity.verified",
            "claim: integrity-only",
            f"files: {counts['files']}",
            f"inventories: {counts['inventories']}",
            f"entries: {counts['entries']}",
            f"unique-bytes: {counts['unique_bytes']}",
            "semantic-fidelity: not-assessed",
            "capture-completeness: not-assessed",
        )
    )
    markdown = bundle_verifier.render_card(card, "markdown")
    assert markdown.startswith("# Bundle integrity card\n")
    assert "Semantic fidelity: not assessed" in markdown
    assert "Capture completeness: not assessed" in markdown


def test_invalid_output_does_not_echo_sensitive_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "customer-token-should-not-leak"
    _write_inventory(tmp_path, [_entry(secret, b"absent")])

    assert main(["verify-bundle", "--bundle", str(tmp_path)]) == 3
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_unexpected_failures_use_exit_70(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_bundle: Path) -> bundle_verifier.VerificationCard:
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(bundle_verifier, "verify_bundle", fail)
    assert main(["verify-bundle", "--bundle", str(tmp_path)]) == 70
    captured = capsys.readouterr()
    assert "internal.failure" in captured.err
    assert "sensitive internal detail" not in captured.err
