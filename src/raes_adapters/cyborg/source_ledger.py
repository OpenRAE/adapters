"""Load and validate the pinned CAGE-2 source-mapping evidence.

Issue #13 owns these backend-local validation labels and resources.  They are
not RAES schemas or vocabularies: portable target authority comes exclusively
from the published ``raes_contracts.contracts.schema_bundle()``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any, NamedTuple, cast

from raes_contracts.contracts import schema_bundle  # type: ignore[import-untyped]

from . import load_qualification

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

_PACKAGE = __package__ or "raes_adapters.cyborg"
_MAX_LEDGER_BYTES = 1_000_000
_MAX_LEDGER_ROWS = 1_000
_MAX_LINE_BYTES = 64_000
_LOSS_HEADING = re.compile(r"^## (?P<loss_id>[a-z0-9][a-z0-9-]*)\s*$")
_LOSS_TIERS = re.compile(r"^\*\*Equivalence tiers weakened:\*\*\s*(?P<tiers>.+?)\s*$")
_LINE_SELECTOR = re.compile(r"^lines:(?P<start>[1-9]\d*)-(?P<end>[1-9]\d*)$")


class EvidenceSelection(NamedTuple):
    """One immutable module-local CAGE-2 mapping evidence selection."""

    qualification_profile_id: str
    ledger_resource: tuple[str, ...]
    losses_resource: tuple[str, ...]


CAGE2_SOURCE_26CE1C1 = EvidenceSelection(
    qualification_profile_id="cage2-cyborg-2.1-source-26ce1c1",
    ledger_resource=("mapping", "cage2-source-ledger.jsonl"),
    losses_resource=("mapping", "cage2-loss-disclosures.md"),
)

DISPOSITIONS = frozenset({"mapped", "out-of-scope", "loss-disclosed"})
REQUIRED_SOURCE_FAMILIES = frozenset(
    {
        "scenario",
        "actions",
        "observations",
        "rewards",
        "wrappers",
        "agents",
        "evaluation",
        "provenance-licensing",
    }
)
REQUIRED_FACT_FACETS = frozenset(
    {
        "topology",
        "hosts",
        "services",
        "accounts",
        "privileges",
        "roles",
        "participants",
        "initial-knowledge",
        "visibility",
        "hidden-truth",
        "actions",
        "admissibility",
        "turn-order",
        "trial-lengths",
        "termination",
        "red-variants",
        "seeds",
        "stochastic-controls",
        "reward-components",
        "objectives",
        "derived-measures",
        "licensing",
        "attribution",
    }
)
RECOGNIZED_EQUIVALENCE_TIERS = frozenset(
    {
        "authored-source",
        "contract",
        "execution-control",
        "state/observation",
        "outcome/evaluation",
    }
)

_REQUIRED_ROW_FIELDS = frozenset(
    {
        "source_id",
        "source_family",
        "fact_facet",
        "source_repo",
        "source_version",
        "source_path",
        "source_selector",
        "source_digest",
        "disposition",
        "mapping_rule",
        "verification",
    }
)
_OPTIONAL_ROW_FIELDS = frozenset(
    {
        "raes_target",
        "qualification_ref",
        "loss_disclosure",
        "equivalence_tiers",
    }
)
_ALLOWED_ROW_FIELDS = _REQUIRED_ROW_FIELDS | _OPTIONAL_ROW_FIELDS


class LedgerProblem(NamedTuple):
    """A bounded source-ledger validation problem."""

    row_id: str
    field: str
    reason: str

    def __str__(self) -> str:
        """Render only the bounded row, field, and reason."""
        return f"[{self.row_id}] {self.field}: {self.reason}"


def _read_text(*parts: str) -> str:
    """Read an installed package resource as UTF-8."""
    return files(_PACKAGE).joinpath(*parts).read_text(encoding="utf-8")


def _string(row: JsonObject, field: str) -> str:
    value = row.get(field)
    return value if isinstance(value, str) else ""


def _string_list(row: JsonObject, field: str) -> list[str]:
    value = row.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return cast(list[str], value)


def parse_ledger_rows(text: str) -> list[JsonObject]:
    """Strictly parse bounded JSONL with duplicate-key and finite-number checks."""
    if len(text.encode("utf-8")) > _MAX_LEDGER_BYTES:
        raise ValueError("ledger exceeds the bounded byte limit")

    def _no_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
        result: JsonObject = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def _reject_non_finite(value: str) -> float:
        raise ValueError(f"non-finite number is not permitted: {value}")

    rows: list[JsonObject] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
            raise ValueError(f"ledger line {line_number} exceeds the bounded byte limit")
        value = json.loads(
            line,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
        if not isinstance(value, dict):
            raise ValueError(f"ledger line {line_number} is not a JSON object")
        rows.append(cast(JsonObject, value))
        if len(rows) > _MAX_LEDGER_ROWS:
            raise ValueError("ledger exceeds the bounded row limit")
    return rows


def load_source_ledger(
    selection: EvidenceSelection = CAGE2_SOURCE_26CE1C1,
) -> list[JsonObject]:
    """Load the selected CAGE-2 JSONL ledger."""
    return parse_ledger_rows(_read_text(*selection.ledger_resource))


def parse_loss_disclosures(text: str) -> dict[str, set[str]]:
    """Parse every disclosure heading and its exact weakened-tier set."""
    disclosures: dict[str, set[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = _LOSS_HEADING.match(line)
        if heading:
            if current is not None:
                disclosures.setdefault(current, set())
            current = heading.group("loss_id")
            continue
        tier_line = _LOSS_TIERS.match(line)
        if tier_line and current is not None:
            disclosures[current] = {
                tier.strip() for tier in tier_line.group("tiers").split(",") if tier.strip()
            }
            current = None
    if current is not None:
        disclosures.setdefault(current, set())
    return disclosures


def load_loss_disclosures(
    selection: EvidenceSelection = CAGE2_SOURCE_26CE1C1,
) -> dict[str, set[str]]:
    """Load the selected disclosure id-to-weakened-tiers mapping."""
    return parse_loss_disclosures(_read_text(*selection.losses_resource))


def _resolve_json_pointer(root: JsonValue, pointer: str) -> bool:
    if pointer == "":
        return True
    if not pointer.startswith("/"):
        return False
    current = root
    for raw_part in pointer.removeprefix("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if part not in current:
                return False
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return False
            current = current[index]
        else:
            return False
    return True


def resolve_raes_target(target: str, bundle: dict[str, JsonObject]) -> bool:
    """Resolve ``<published-schema-id>#<JSON-pointer>`` through ``schema_bundle``."""
    schema_id, separator, pointer = target.partition("#")
    if not separator or schema_id not in bundle:
        return False
    return _resolve_json_pointer(bundle[schema_id], pointer)


def resolve_qualification_ref(reference: str, qualification: dict[str, Any]) -> bool:
    """Resolve a qualification-owned evidence JSON pointer."""
    prefix = "qualification.json#"
    if not reference.startswith(prefix):
        return False
    return _resolve_json_pointer(cast(JsonValue, qualification), reference.removeprefix(prefix))


def _selector_shape_is_valid(selector: str) -> bool:
    if selector.startswith("python:"):
        return bool(selector.removeprefix("python:").strip())
    if selector.startswith("text:"):
        return bool(selector.removeprefix("text:").strip())
    match = _LINE_SELECTOR.fullmatch(selector)
    return bool(match and int(match.group("start")) <= int(match.group("end")))


def _python_selector_exists(source: str, selector: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    wanted = selector.removeprefix("python:")
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.add(node.name)
        if isinstance(node, ast.ClassDef):
            symbols.update(
                f"{node.name}.{child.name}"
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return wanted in symbols


def _selector_exists(path: Path, selector: str) -> bool:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    if selector.startswith("python:"):
        return _python_selector_exists(source, selector)
    if selector.startswith("text:"):
        return selector.removeprefix("text:") in source
    match = _LINE_SELECTOR.fullmatch(selector)
    if not match:
        return False
    start = int(match.group("start"))
    end = int(match.group("end"))
    return start <= end <= len(source.splitlines())


def validate_source_checkout(
    source_root: Path,
    rows: list[dict[str, Any]] | list[JsonObject],
) -> list[LedgerProblem]:
    """Verify row paths, digests, and selectors against a detached source checkout."""
    root = source_root.resolve()
    problems: list[LedgerProblem] = []
    for raw_row in rows:
        row = cast(dict[str, Any], raw_row)
        source_id = row.get("source_id")
        row_id = source_id if isinstance(source_id, str) else "<unknown>"
        source_path = row.get("source_path")
        source_digest = row.get("source_digest")
        selector = row.get("source_selector")
        if not isinstance(source_path, str):
            problems.append(LedgerProblem(row_id, "source_path", "missing source path"))
            continue
        relative = Path(source_path)
        candidate = (root / relative).resolve()
        if relative.is_absolute() or not candidate.is_relative_to(root) or not candidate.is_file():
            problems.append(LedgerProblem(row_id, "source_path", "source path is not confined"))
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if not isinstance(source_digest, str) or digest != source_digest:
            problems.append(LedgerProblem(row_id, "source_digest", "source digest drift"))
        if not isinstance(selector, str) or not _selector_exists(candidate, selector):
            problems.append(LedgerProblem(row_id, "source_selector", "selector does not resolve"))
    return problems


def validate_source_ledger(
    rows: list[JsonObject],
    *,
    qualification: dict[str, Any],
    bundle: dict[str, JsonObject],
    losses: dict[str, set[str]],
) -> list[LedgerProblem]:
    """Validate row shape, coverage, source joins, targets, and disclosures."""
    problems: list[LedgerProblem] = []
    selected_files = {
        item["path"]: item["sha256"]
        for item in qualification.get("selected_files", [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("sha256"), str)
    }
    source = qualification.get("source", {})
    expected_repo = source.get("repository") if isinstance(source, dict) else None
    expected_version = source.get("commit") if isinstance(source, dict) else None
    seen_ids: set[str] = set()
    source_families: set[str] = set()
    fact_facets: set[str] = set()
    referenced_losses: set[str] = set()

    for index, row in enumerate(rows, start=1):
        row_id = _string(row, "source_id") or f"<row-{index}>"
        unknown_fields = sorted(set(row) - _ALLOWED_ROW_FIELDS)
        problems.extend(
            LedgerProblem(row_id, field, "unknown row field") for field in unknown_fields
        )
        for field in sorted(_REQUIRED_ROW_FIELDS):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(LedgerProblem(row_id, field, "missing or blank required value"))
        for field in ("raes_target", "qualification_ref", "loss_disclosure"):
            if field in row:
                value = row[field]
                if not isinstance(value, str) or not value.strip():
                    problems.append(
                        LedgerProblem(row_id, field, "optional value must be a nonblank string")
                    )
        if "equivalence_tiers" in row:
            raw_tiers = row["equivalence_tiers"]
            if (
                not isinstance(raw_tiers, list)
                or not raw_tiers
                or not all(isinstance(tier, str) and tier.strip() for tier in raw_tiers)
                or len(set(cast(list[str], raw_tiers))) != len(raw_tiers)
            ):
                problems.append(
                    LedgerProblem(
                        row_id,
                        "equivalence_tiers",
                        "tier set must be a nonempty unique string list",
                    )
                )

        if row_id in seen_ids:
            problems.append(LedgerProblem(row_id, "source_id", "duplicate source id"))
        seen_ids.add(row_id)

        source_family = _string(row, "source_family")
        fact_facet = _string(row, "fact_facet")
        disposition = _string(row, "disposition")
        if source_family not in REQUIRED_SOURCE_FAMILIES:
            problems.append(LedgerProblem(row_id, "source_family", "unknown source family"))
        else:
            source_families.add(source_family)
        if fact_facet not in REQUIRED_FACT_FACETS:
            problems.append(LedgerProblem(row_id, "fact_facet", "unknown fact facet"))
        else:
            fact_facets.add(fact_facet)
        if disposition not in DISPOSITIONS:
            problems.append(LedgerProblem(row_id, "disposition", "unknown disposition"))

        if _string(row, "source_repo") != expected_repo:
            problems.append(LedgerProblem(row_id, "source_repo", "source profile mismatch"))
        if _string(row, "source_version") != expected_version:
            problems.append(LedgerProblem(row_id, "source_version", "source profile mismatch"))
        path = _string(row, "source_path")
        expected_digest = selected_files.get(path)
        if expected_digest is None:
            problems.append(LedgerProblem(row_id, "source_path", "path is not qualified"))
        elif _string(row, "source_digest") != expected_digest:
            problems.append(LedgerProblem(row_id, "source_digest", "qualified digest drift"))
        if not _selector_shape_is_valid(_string(row, "source_selector")):
            problems.append(LedgerProblem(row_id, "source_selector", "invalid selector shape"))

        target = _string(row, "raes_target")
        qualification_ref = _string(row, "qualification_ref")
        loss_id = _string(row, "loss_disclosure")
        tiers = set(_string_list(row, "equivalence_tiers"))
        if target and not resolve_raes_target(target, bundle):
            problems.append(LedgerProblem(row_id, "raes_target", "target does not resolve"))
        if qualification_ref and not resolve_qualification_ref(qualification_ref, qualification):
            problems.append(
                LedgerProblem(
                    row_id, "qualification_ref", "qualification reference does not resolve"
                )
            )

        if disposition == "mapped":
            if not target:
                problems.append(LedgerProblem(row_id, "raes_target", "mapped row requires target"))
            if loss_id or tiers:
                problems.append(
                    LedgerProblem(row_id, "loss_disclosure", "mapped row cannot declare a loss")
                )
        elif disposition == "out-of-scope":
            if target:
                problems.append(
                    LedgerProblem(row_id, "raes_target", "out-of-scope row cannot map a target")
                )
            if loss_id or tiers:
                problems.append(
                    LedgerProblem(
                        row_id,
                        "loss_disclosure",
                        "out-of-scope row cannot declare a loss",
                    )
                )
        elif disposition == "loss-disclosed":
            if not loss_id:
                problems.append(
                    LedgerProblem(
                        row_id, "loss_disclosure", "loss-disclosed row requires reference"
                    )
                )
            else:
                referenced_losses.add(loss_id)
            unknown_tiers = tiers - RECOGNIZED_EQUIVALENCE_TIERS
            if not tiers or unknown_tiers:
                problems.append(
                    LedgerProblem(row_id, "equivalence_tiers", "unrecognized or missing tier")
                )
            if loss_id and losses.get(loss_id) != tiers:
                problems.append(
                    LedgerProblem(row_id, "equivalence_tiers", "tier set disagrees with disclosure")
                )

    for missing in sorted(REQUIRED_SOURCE_FAMILIES - source_families):
        problems.append(LedgerProblem("<coverage>", "source_family", f"missing {missing}"))
    for missing in sorted(REQUIRED_FACT_FACETS - fact_facets):
        problems.append(LedgerProblem("<coverage>", "fact_facet", f"missing {missing}"))
    for loss_id, tiers in losses.items():
        if not tiers or tiers - RECOGNIZED_EQUIVALENCE_TIERS:
            problems.append(
                LedgerProblem(loss_id, "equivalence_tiers", "disclosure has invalid tier set")
            )
        if loss_id not in referenced_losses:
            problems.append(LedgerProblem(loss_id, "loss_disclosure", "orphan disclosure"))
    return problems


def validate_all(
    selection: EvidenceSelection = CAGE2_SOURCE_26CE1C1,
) -> list[LedgerProblem]:
    """Validate the selected installed evidence set without network access."""
    qualification = load_qualification()
    if qualification.get("profile_id") != selection.qualification_profile_id:
        return [
            LedgerProblem(
                "<selection>",
                "qualification_profile_id",
                "qualification profile mismatch",
            )
        ]
    return validate_source_ledger(
        load_source_ledger(selection),
        qualification=qualification,
        bundle=cast(dict[str, JsonObject], schema_bundle()),
        losses=load_loss_disclosures(selection),
    )
