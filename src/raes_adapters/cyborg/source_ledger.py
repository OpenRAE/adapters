"""Load and validate the pinned CAGE-2 source-mapping evidence.

Issue #13 owns these backend-local validation labels and resources.  They are
not RAES schemas or vocabularies: portable target authority comes exclusively
from the published ``raes_contracts.contracts.schema_bundle()``.
"""

from __future__ import annotations

import ast
import hashlib
import json
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
_LOSS_HEADING_PREFIX = "## "
_LOSS_TIERS_PREFIX = "**Equivalence tiers weakened:**"
_PYTHON_SELECTOR_PREFIX = "python:"
_TEXT_SELECTOR_PREFIX = "text:"
_LINE_SELECTOR_PREFIX = "lines:"


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
    """Return a string field or a closed empty sentinel."""
    value = row.get(field)
    return value if isinstance(value, str) else ""


def _string_list(row: JsonObject, field: str) -> list[str]:
    """Return a homogeneous string-list field or a closed empty sentinel."""
    value = row.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return cast(list[str], value)


def parse_ledger_rows(text: str) -> list[JsonObject]:
    """Strictly parse bounded JSONL with duplicate-key and finite-number checks."""
    if len(text.encode("utf-8")) > _MAX_LEDGER_BYTES:
        raise ValueError("ledger exceeds the bounded byte limit")

    def _no_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
        """Build an object while refusing duplicate JSON member names."""
        result: JsonObject = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def _reject_non_finite(value: str) -> float:
        """Reject JSON parser extensions for NaN and infinities."""
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


def _loss_heading_id(line: str) -> str | None:
    """Return a strictly bounded ASCII loss id from a Markdown heading."""
    if not line.startswith(_LOSS_HEADING_PREFIX):
        return None
    candidate = line.removeprefix(_LOSS_HEADING_PREFIX).strip()
    allowed = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
    starts = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
    valid = bool(candidate) and candidate[0] in starts and set(candidate) <= allowed
    return candidate if valid else None


def _loss_tiers(line: str) -> set[str] | None:
    """Return the comma-separated tiers from the canonical disclosure line."""
    if not line.startswith(_LOSS_TIERS_PREFIX):
        return None
    raw_tiers = line.removeprefix(_LOSS_TIERS_PREFIX).strip()
    if not raw_tiers:
        return None
    return {tier.strip() for tier in raw_tiers.split(",") if tier.strip()}


def parse_loss_disclosures(text: str) -> dict[str, set[str]]:
    """Parse every disclosure heading and its exact weakened-tier set."""
    disclosures: dict[str, set[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = _loss_heading_id(line)
        if heading is not None:
            if current is not None:
                disclosures.setdefault(current, set())
            current = heading
            continue
        tiers = _loss_tiers(line)
        if tiers is not None and current is not None:
            disclosures[current] = tiers
            current = None
    if current is not None:
        disclosures.setdefault(current, set())
    return disclosures


def load_loss_disclosures(
    selection: EvidenceSelection = CAGE2_SOURCE_26CE1C1,
) -> dict[str, set[str]]:
    """Load the selected disclosure id-to-weakened-tiers mapping."""
    return parse_loss_disclosures(_read_text(*selection.losses_resource))


def _json_pointer_step(current: JsonValue, part: str) -> tuple[bool, JsonValue]:
    """Resolve one decoded JSON-pointer segment."""
    if isinstance(current, dict) and part in current:
        return True, current[part]
    if isinstance(current, list) and part.isdigit():
        index = int(part)
        if index < len(current):
            return True, current[index]
    return False, current


def _resolve_json_pointer(root: JsonValue, pointer: str) -> bool:
    """Resolve a JSON pointer without exposing the referenced value."""
    if pointer != "" and not pointer.startswith("/"):
        return False
    current = root
    for raw_part in [] if pointer == "" else pointer.removeprefix("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        valid, current = _json_pointer_step(current, part)
        if not valid:
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
    """Validate a selector's bounded syntax without opening its source."""
    if selector.startswith(_PYTHON_SELECTOR_PREFIX):
        valid = bool(selector.removeprefix(_PYTHON_SELECTOR_PREFIX).strip())
    elif selector.startswith(_TEXT_SELECTOR_PREFIX):
        valid = bool(selector.removeprefix(_TEXT_SELECTOR_PREFIX).strip())
    else:
        valid = _line_selector_bounds(selector) is not None
    return valid


def _line_selector_bounds(selector: str) -> tuple[int, int] | None:
    """Parse a positive inclusive line range without regex backtracking."""
    if not selector.startswith(_LINE_SELECTOR_PREFIX):
        return None
    start_text, separator, end_text = selector.removeprefix(_LINE_SELECTOR_PREFIX).partition("-")
    valid = (
        bool(separator)
        and start_text.isascii()
        and end_text.isascii()
        and start_text.isdigit()
        and end_text.isdigit()
        and not start_text.startswith("0")
        and not end_text.startswith("0")
    )
    if not valid:
        return None
    start, end = int(start_text), int(end_text)
    return (start, end) if start <= end else None


def _python_selector_exists(source: str, selector: str) -> bool:
    """Resolve a top-level Python class/function or class method via the AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    wanted = selector.removeprefix(_PYTHON_SELECTOR_PREFIX)
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
    """Resolve one supported selector against UTF-8 source text."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        exists = False
    else:
        bounds = _line_selector_bounds(selector)
        if selector.startswith(_PYTHON_SELECTOR_PREFIX):
            exists = _python_selector_exists(source, selector)
        elif selector.startswith(_TEXT_SELECTOR_PREFIX):
            exists = selector.removeprefix(_TEXT_SELECTOR_PREFIX) in source
        elif bounds is not None:
            _, end = bounds
            exists = end <= len(source.splitlines())
        else:
            exists = False
    return exists


def _confined_source_path(root: Path, source_path: str) -> Path | None:
    """Resolve a relative regular-file path confined beneath the source root."""
    relative = Path(source_path)
    candidate = (root / relative).resolve()
    confined = not relative.is_absolute() and candidate.is_relative_to(root) and candidate.is_file()
    return candidate if confined else None


def _validate_checkout_row(root: Path, row: dict[str, Any]) -> list[LedgerProblem]:
    """Validate one ledger row against a detached qualified checkout."""
    source_id = row.get("source_id")
    row_id = source_id if isinstance(source_id, str) else "<unknown>"
    source_path = row.get("source_path")
    if not isinstance(source_path, str):
        return [LedgerProblem(row_id, "source_path", "missing source path")]

    candidate = _confined_source_path(root, source_path)
    if candidate is None:
        return [LedgerProblem(row_id, "source_path", "source path is not confined")]

    problems: list[LedgerProblem] = []
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if row.get("source_digest") != digest:
        problems.append(LedgerProblem(row_id, "source_digest", "source digest drift"))
    selector = row.get("source_selector")
    if not isinstance(selector, str) or not _selector_exists(candidate, selector):
        problems.append(LedgerProblem(row_id, "source_selector", "selector does not resolve"))
    return problems


def validate_source_checkout(
    source_root: Path,
    rows: list[dict[str, Any]] | list[JsonObject],
) -> list[LedgerProblem]:
    """Verify row paths, digests, and selectors against a detached source checkout."""
    root = source_root.resolve()
    problems: list[LedgerProblem] = []
    for raw_row in rows:
        problems.extend(_validate_checkout_row(root, cast(dict[str, Any], raw_row)))
    return problems


class _LedgerValidationContext(NamedTuple):
    """Immutable dependencies shared by per-row ledger validation."""

    selected_files: dict[str, str]
    expected_repo: str | None
    expected_version: str | None
    qualification: dict[str, Any]
    bundle: dict[str, JsonObject]
    losses: dict[str, set[str]]


def _validation_context(
    qualification: dict[str, Any],
    bundle: dict[str, JsonObject],
    losses: dict[str, set[str]],
) -> _LedgerValidationContext:
    """Build exact qualification and contract joins for ledger validation."""
    selected_files = {
        item["path"]: item["sha256"]
        for item in qualification.get("selected_files", [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("sha256"), str)
    }
    source = qualification.get("source", {})
    source_repo = source.get("repository") if isinstance(source, dict) else None
    source_version = source.get("commit") if isinstance(source, dict) else None
    expected_repo = source_repo if isinstance(source_repo, str) else None
    expected_version = source_version if isinstance(source_version, str) else None
    return _LedgerValidationContext(
        selected_files,
        expected_repo,
        expected_version,
        qualification,
        bundle,
        losses,
    )


def _tiers_field_is_valid(raw_tiers: JsonValue) -> bool:
    """Accept only a nonempty unique list of nonblank tier strings."""
    if not isinstance(raw_tiers, list) or not raw_tiers:
        return False
    strings = [tier for tier in raw_tiers if isinstance(tier, str)]
    return (
        len(strings) == len(raw_tiers)
        and all(tier.strip() for tier in strings)
        and len(set(strings)) == len(strings)
    )


def _validate_row_shape(row: JsonObject, row_id: str) -> list[LedgerProblem]:
    """Validate the row's closed field set and scalar/list value shapes."""
    problems = [
        LedgerProblem(row_id, field, "unknown row field")
        for field in sorted(set(row) - _ALLOWED_ROW_FIELDS)
    ]
    problems.extend(
        LedgerProblem(row_id, field, "missing or blank required value")
        for field in sorted(_REQUIRED_ROW_FIELDS)
        if not isinstance(row.get(field), str) or not cast(str, row[field]).strip()
    )
    problems.extend(
        LedgerProblem(row_id, field, "optional value must be a nonblank string")
        for field in ("raes_target", "qualification_ref", "loss_disclosure")
        if field in row and (not isinstance(row[field], str) or not cast(str, row[field]).strip())
    )
    if "equivalence_tiers" in row and not _tiers_field_is_valid(row["equivalence_tiers"]):
        problems.append(
            LedgerProblem(
                row_id,
                "equivalence_tiers",
                "tier set must be a nonempty unique string list",
            )
        )
    return problems


def _validate_classification(
    row: JsonObject,
    row_id: str,
    source_families: set[str],
    fact_facets: set[str],
) -> list[LedgerProblem]:
    """Validate classification values and record their coverage."""
    problems: list[LedgerProblem] = []
    source_family = _string(row, "source_family")
    fact_facet = _string(row, "fact_facet")
    disposition = _string(row, "disposition")
    if source_family in REQUIRED_SOURCE_FAMILIES:
        source_families.add(source_family)
    else:
        problems.append(LedgerProblem(row_id, "source_family", "unknown source family"))
    if fact_facet in REQUIRED_FACT_FACETS:
        fact_facets.add(fact_facet)
    else:
        problems.append(LedgerProblem(row_id, "fact_facet", "unknown fact facet"))
    if disposition not in DISPOSITIONS:
        problems.append(LedgerProblem(row_id, "disposition", "unknown disposition"))
    return problems


def _validate_source_join(
    row: JsonObject,
    row_id: str,
    context: _LedgerValidationContext,
) -> list[LedgerProblem]:
    """Validate profile identity, qualified file identity, and selector syntax."""
    problems: list[LedgerProblem] = []
    if _string(row, "source_repo") != context.expected_repo:
        problems.append(LedgerProblem(row_id, "source_repo", "source profile mismatch"))
    if _string(row, "source_version") != context.expected_version:
        problems.append(LedgerProblem(row_id, "source_version", "source profile mismatch"))
    path = _string(row, "source_path")
    expected_digest = context.selected_files.get(path)
    if expected_digest is None:
        problems.append(LedgerProblem(row_id, "source_path", "path is not qualified"))
    elif _string(row, "source_digest") != expected_digest:
        problems.append(LedgerProblem(row_id, "source_digest", "qualified digest drift"))
    if not _selector_shape_is_valid(_string(row, "source_selector")):
        problems.append(LedgerProblem(row_id, "source_selector", "invalid selector shape"))
    return problems


def _validate_references(
    row: JsonObject,
    row_id: str,
    context: _LedgerValidationContext,
) -> list[LedgerProblem]:
    """Resolve optional RAES and qualification evidence references."""
    problems: list[LedgerProblem] = []
    target = _string(row, "raes_target")
    qualification_ref = _string(row, "qualification_ref")
    if target and not resolve_raes_target(target, context.bundle):
        problems.append(LedgerProblem(row_id, "raes_target", "target does not resolve"))
    if qualification_ref and not resolve_qualification_ref(
        qualification_ref,
        context.qualification,
    ):
        problems.append(
            LedgerProblem(
                row_id,
                "qualification_ref",
                "qualification reference does not resolve",
            )
        )
    return problems


def _validate_mapped_disposition(
    row_id: str,
    target: str,
    loss_id: str,
    tiers: set[str],
) -> list[LedgerProblem]:
    """Enforce the target-only shape of a fully mapped row."""
    problems: list[LedgerProblem] = []
    if not target:
        problems.append(LedgerProblem(row_id, "raes_target", "mapped row requires target"))
    if loss_id or tiers:
        problems.append(
            LedgerProblem(row_id, "loss_disclosure", "mapped row cannot declare a loss")
        )
    return problems


def _validate_out_of_scope_disposition(
    row_id: str,
    target: str,
    loss_id: str,
    tiers: set[str],
) -> list[LedgerProblem]:
    """Enforce the no-target/no-loss shape of an out-of-scope row."""
    problems: list[LedgerProblem] = []
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
    return problems


def _validate_loss_disclosed_disposition(
    row_id: str,
    loss_id: str,
    tiers: set[str],
    losses: dict[str, set[str]],
    referenced_losses: set[str],
) -> list[LedgerProblem]:
    """Enforce exact disclosure references and recognized weakened tiers."""
    problems: list[LedgerProblem] = []
    if loss_id:
        referenced_losses.add(loss_id)
    else:
        problems.append(
            LedgerProblem(row_id, "loss_disclosure", "loss-disclosed row requires reference")
        )
    if not tiers or tiers - RECOGNIZED_EQUIVALENCE_TIERS:
        problems.append(LedgerProblem(row_id, "equivalence_tiers", "unrecognized or missing tier"))
    if loss_id and losses.get(loss_id) != tiers:
        problems.append(
            LedgerProblem(row_id, "equivalence_tiers", "tier set disagrees with disclosure")
        )
    return problems


def _validate_disposition(
    row: JsonObject,
    row_id: str,
    context: _LedgerValidationContext,
    referenced_losses: set[str],
) -> list[LedgerProblem]:
    """Dispatch the row to its closed disposition validator."""
    disposition = _string(row, "disposition")
    target = _string(row, "raes_target")
    loss_id = _string(row, "loss_disclosure")
    tiers = set(_string_list(row, "equivalence_tiers"))
    if disposition == "mapped":
        problems = _validate_mapped_disposition(row_id, target, loss_id, tiers)
    elif disposition == "out-of-scope":
        problems = _validate_out_of_scope_disposition(row_id, target, loss_id, tiers)
    elif disposition == "loss-disclosed":
        problems = _validate_loss_disclosed_disposition(
            row_id,
            loss_id,
            tiers,
            context.losses,
            referenced_losses,
        )
    else:
        problems = []
    return problems


def _coverage_problems(
    source_families: set[str],
    fact_facets: set[str],
) -> list[LedgerProblem]:
    """Report every missing source-family and fact-facet coverage label."""
    problems = [
        LedgerProblem("<coverage>", "source_family", f"missing {missing}")
        for missing in sorted(REQUIRED_SOURCE_FAMILIES - source_families)
    ]
    problems.extend(
        LedgerProblem("<coverage>", "fact_facet", f"missing {missing}")
        for missing in sorted(REQUIRED_FACT_FACETS - fact_facets)
    )
    return problems


def _disclosure_problems(
    losses: dict[str, set[str]],
    referenced_losses: set[str],
) -> list[LedgerProblem]:
    """Report invalid tier sets and disclosures not referenced by ledger rows."""
    problems = [
        LedgerProblem(loss_id, "equivalence_tiers", "disclosure has invalid tier set")
        for loss_id, tiers in losses.items()
        if not tiers or tiers - RECOGNIZED_EQUIVALENCE_TIERS
    ]
    problems.extend(
        LedgerProblem(loss_id, "loss_disclosure", "orphan disclosure")
        for loss_id in losses
        if loss_id not in referenced_losses
    )
    return problems


def validate_source_ledger(
    rows: list[JsonObject],
    *,
    qualification: dict[str, Any],
    bundle: dict[str, JsonObject],
    losses: dict[str, set[str]],
) -> list[LedgerProblem]:
    """Validate row shape, coverage, source joins, targets, and disclosures."""
    context = _validation_context(qualification, bundle, losses)
    problems: list[LedgerProblem] = []
    seen_ids: set[str] = set()
    source_families: set[str] = set()
    fact_facets: set[str] = set()
    referenced_losses: set[str] = set()

    for index, row in enumerate(rows, start=1):
        row_id = _string(row, "source_id") or f"<row-{index}>"
        problems.extend(_validate_row_shape(row, row_id))
        if row_id in seen_ids:
            problems.append(LedgerProblem(row_id, "source_id", "duplicate source id"))
        seen_ids.add(row_id)
        problems.extend(_validate_classification(row, row_id, source_families, fact_facets))
        problems.extend(_validate_source_join(row, row_id, context))
        problems.extend(_validate_references(row, row_id, context))
        problems.extend(_validate_disposition(row, row_id, context, referenced_losses))

    problems.extend(_coverage_problems(source_families, fact_facets))
    problems.extend(_disclosure_problems(losses, referenced_losses))
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
