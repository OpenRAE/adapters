"""Shared loaders and deterministic validators for backend scenario evidence.

A qualified simulator case ships a portable evidence set under its backend
package:

- an authored RAES SDL scenario carrying topology/objective truth
  (:meth:`ScenarioLedger.load_scenario`), validated and compiled through the
  pinned ``raes==2.0.0`` release;
- a companion published experiment contract pair
  (:meth:`ScenarioLedger.load_experiment_task`,
  :meth:`ScenarioLedger.load_experiment_spec`) carrying the reward, evaluator,
  metric, episode/termination, and stochastic intent that RAES excludes from
  SDL; and
- a pinned source-mapping ledger (:meth:`ScenarioLedger.load_source_ledger`)
  recording how each immutable source fact reaches a portable RAES surface, or
  why it does not, with every disclosed loss bound to the ADR-069 equivalence
  tier it weakens.

The machinery is backend-agnostic. Each backend module binds one
:class:`ScenarioLedger` to its package, qualification/protocol loaders, and
native-leakage markers, exactly as ``raes_adapters._qualification`` shares the
qualification-evidence loaders. The validators compose the published RAES
parser, closed contract models, the published ``schema_bundle`` for target
resolution, and the already-qualified ``qualification.json`` pins. They define
no new schema, DTO, vocabulary, policy gate, or exception hierarchy; the
disposition, category, and equivalence-tier labels are issue-local validation
labels, not RAES vocabulary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from importlib.resources import files
from typing import NamedTuple, cast

import raes  # type: ignore[import-untyped]
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentSpecModel,
    ExperimentTaskModel,
    schema_bundle,
)
from raes_contracts.experiment_spec import parse_experiment_spec  # type: ignore[import-untyped]
from raes_processor.compiler import compile_scenario_runtime_model  # type: ignore[import-untyped]

# A decoded JSON value and object. Used instead of ``Any`` so the ledger and
# schema-bundle traversal carry a concrete (if dynamic) type.
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

_DEFS = "$defs"
_REF = "$ref"
_DEFS_PREFIX = "#/$defs/"


class EvidenceSelection(NamedTuple):
    """One immutable backend evidence selection.

    Per the scenario/ledger guardrails the extension seam is an explicit
    selection identity: a second case is another ``EvidenceSelection`` passed to
    the same loaders and validator, not an edit to the validation code. Every
    cross-artifact identity the joins check (scenario id + pinned digest, task
    id, spec id) lives here, so the members are validated together rather than
    as independent singletons.
    """

    scenario_id: str
    scenario_resource: tuple[str, ...]
    pinned_scenario_digest: str
    task_id: str
    task_resource: tuple[str, ...]
    spec_id: str
    spec_resource: tuple[str, ...]
    ledger_resource: tuple[str, ...]
    losses_resource: tuple[str, ...]
    protocol_resource: str


DISPOSITIONS = frozenset({"mapped", "excluded", "loss-disclosed"})

REQUIRED_CATEGORIES = frozenset(
    {
        "topology-state",
        "identities",
        "participants",
        "actions",
        "observations",
        "controls",
        "rewards-objectives",
        "termination",
        "evaluator",
        "stochastic",
        "provenance-licensing",
    }
)

# Issue-local labels for the ADR-069 tiered-equivalence ladder (see each
# backend's loss-disclosures.md); not a new RAES vocabulary.
RECOGNIZED_EQUIVALENCE_TIERS = frozenset(
    {"reproducibility", "deterministic-replay", "outcome-equivalence"}
)

_REQUIRED_ROW_FIELDS = frozenset(
    {
        "source_id",
        "source_repo",
        "source_commit",
        "source_path",
        "source_selector",
        "source_digest",
        "category",
        "disposition",
        "mapping_rule",
        "verification",
    }
)
_OPTIONAL_ROW_FIELDS = frozenset({"raes_target", "loss_ref", "equivalence_tier"})
_ALLOWED_ROW_FIELDS = _REQUIRED_ROW_FIELDS | _OPTIONAL_ROW_FIELDS

_MISSING_FIELD_REASON = "missing or blank required field"

# Native simulator object/array representation markers that must never appear in
# a portable RAES artifact, common to every backend. Backends add their own
# native identifier markers (native field names or action-class symbols) and the
# ``<backend`` object-repr prefix. Raw native arrays, reward vectors, and action
# ids are separately excluded *structurally* by the closed RAES SDL and
# experiment models, which have no field to carry them; this scan is defense in
# depth over the native identifier and representation classes.
COMMON_NATIVE_REPR_MARKERS: tuple[str, ...] = (
    "traceback (most recent call last)",
    " object at 0x",
    "ndarray(",
    "array([",
)

_LOSS_HEADING = re.compile(r"^## (?P<loss_id>\S+)\s*$")
_LOSS_TIER = re.compile(r"^\*\*Equivalence tier:\*\*\s*(?P<tier>\S+)\s*$")


class LedgerProblem(NamedTuple):
    """A single fail-closed validation problem (row id + field + reason only)."""

    row_id: str
    field: str
    reason: str

    def __str__(self) -> str:
        """Render the problem as ``[row_id] field: reason``."""
        return f"[{self.row_id}] {self.field}: {self.reason}"


# --------------------------------------------------------------------------- #
# JSON helpers
# --------------------------------------------------------------------------- #
def _as_object(value: JsonValue) -> JsonObject:
    """Return the value when it is a JSON object, else an empty object."""
    return value if isinstance(value, dict) else {}


def _as_list(value: JsonValue) -> list[JsonValue]:
    """Return the value when it is a JSON array, else an empty list."""
    return value if isinstance(value, list) else []


def _as_str(value: JsonValue) -> str:
    """Return the value when it is a string, else the empty string."""
    return value if isinstance(value, str) else ""


# --------------------------------------------------------------------------- #
# resource loaders
# --------------------------------------------------------------------------- #
def read_text(package: str, *parts: str) -> str:
    """Read a package resource as UTF-8 text."""
    return files(package).joinpath(*parts).read_text(encoding="utf-8")


def resource_is_file(package: str, name: str) -> bool:
    """Return whether the named package resource exists as a file."""
    return bool(files(package).joinpath(name).is_file())


def _yaml_safe_load(text: str) -> JsonValue:
    """Parse YAML text into a JSON-like value (lazy ``yaml`` import)."""
    import yaml  # type: ignore[import-untyped]

    return cast("JsonValue", yaml.safe_load(text))


def parse_ledger_rows(text: str) -> list[JsonObject]:
    """Strictly parse the JSONL ledger, rejecting malformed evidence.

    Fails closed on invalid JSON, a non-object row, duplicate JSON keys, and
    non-finite numbers, so the source ledger cannot carry silently corrupt rows.
    """

    def _no_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
        """Build a JSON object, rejecting duplicate keys."""
        seen: JsonObject = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError(f"duplicate JSON key: {key!r}")
            seen[key] = value
        return seen

    def _reject_non_finite(value: str) -> float:
        """Reject NaN/Infinity JSON constants."""
        raise ValueError(f"non-finite number is not permitted: {value}")

    rows: list[JsonObject] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(
            line, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_non_finite
        )
        if not isinstance(row, dict):
            raise ValueError(f"ledger line {lineno} is not a JSON object")
        rows.append(cast("JsonObject", row))
    return rows


def parse_loss_disclosures(text: str) -> dict[str, str]:
    """Parse the disclosures doc into ``{loss_id: equivalence_tier}``.

    Every ``## <loss_id>`` heading is preserved. A heading with no equivalence
    tier line is recorded with an empty tier so it fails closed downstream
    (unrecognized tier / disagreement) rather than silently disappearing.
    """
    disclosures: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = _LOSS_HEADING.match(line)
        if heading:
            if current is not None:
                disclosures.setdefault(current, "")
            current = heading.group("loss_id")
            continue
        tier = _LOSS_TIER.match(line)
        if tier and current is not None:
            disclosures[current] = tier.group("tier")
            current = None
    if current is not None:
        disclosures.setdefault(current, "")
    return disclosures


# --------------------------------------------------------------------------- #
# target resolution
# --------------------------------------------------------------------------- #
def _contract_indexes(
    bundle: dict[str, JsonObject],
) -> tuple[dict[str, JsonObject], dict[str, JsonObject]]:
    """Index the schema bundle by contract title and by ``$defs`` class name."""
    title_index: dict[str, JsonObject] = {}
    defs_root: dict[str, JsonObject] = {}
    for schema in bundle.values():
        title = schema.get("title")
        if isinstance(title, str):
            title_index[title] = schema
        for name in _as_object(schema.get(_DEFS)):
            defs_root.setdefault(name, schema)
    return title_index, defs_root


def _follow_ref(root: JsonObject, node: JsonObject) -> JsonObject:
    """Follow a ``$ref`` (through list items or any/oneOf) into the bundle defs."""
    if _REF not in node and _REF in _as_object(node.get("items")):
        node = _as_object(node.get("items"))
    if _REF not in node:
        for combinator in ("anyOf", "oneOf"):
            for sub in _as_list(node.get(combinator)):
                sub_object = _as_object(sub)
                if _REF in sub_object:
                    node = sub_object
                    break
    ref = node.get(_REF)
    if isinstance(ref, str) and ref.startswith(_DEFS_PREFIX):
        return _as_object(_as_object(root.get(_DEFS)).get(ref.split("/")[-1]))
    return node


def resolve_contract_target(path: str, bundle: dict[str, JsonObject]) -> bool:
    """Resolve a ``Contract.property.path`` against the published schema bundle."""
    head, *rest = path.split(".")
    title_index, defs_root = _contract_indexes(bundle)
    if head in title_index:
        root = node = title_index[head]
    elif head in defs_root:
        root = defs_root[head]
        node = _as_object(_as_object(root.get(_DEFS)).get(head))
    else:
        return False
    for index, prop in enumerate(rest):
        properties = _as_object(node.get("properties"))
        if prop not in properties:
            return False
        node = _as_object(properties.get(prop))
        if index < len(rest) - 1:
            node = _follow_ref(root, node)
    return True


def resolve_sdl_target(body: str, scenario: raes.Scenario) -> bool:
    """Resolve a ``section`` or ``section.key`` against the parsed SDL scenario."""
    missing = object()
    if "." in body:
        section, key = body.split(".", 1)
        collection = getattr(scenario, section, missing)
        return isinstance(collection, dict) and key in collection
    return getattr(scenario, body, missing) is not missing


def resolve_target(
    target: str, *, package: str, scenario: raes.Scenario, bundle: dict[str, JsonObject]
) -> bool:
    """Resolve a ``raes_target`` against parsed artifacts or the schema bundle."""
    prefix, _, body = target.partition(":")
    if prefix == "sdl":
        return resolve_sdl_target(body, scenario)
    if prefix == "contract":
        return resolve_contract_target(body, bundle)
    return prefix == "resource" and resource_is_file(package, body)


# --------------------------------------------------------------------------- #
# ledger validation
# --------------------------------------------------------------------------- #
def _string_field(row: JsonObject, field: str) -> str | None:
    """Return a non-blank string field, or None when missing/blank/non-string."""
    value = row.get(field)
    return value if isinstance(value, str) and value.strip() else None


def _row_shape_problems(row: JsonObject, row_id: str) -> list[LedgerProblem]:
    """Report unknown and missing/blank required fields for one row."""
    problems = [
        LedgerProblem(row_id, field, "unknown ledger field")
        for field in sorted(set(row) - _ALLOWED_ROW_FIELDS)
    ]
    problems += [
        LedgerProblem(row_id, field, _MISSING_FIELD_REASON)
        for field in sorted(_REQUIRED_ROW_FIELDS)
        if _string_field(row, field) is None
    ]
    return problems


def _row_source_problems(
    row: JsonObject, row_id: str, source: JsonObject, digest_by_path: dict[str, str]
) -> list[LedgerProblem]:
    """Report source-identity and offline source-drift join problems for one row."""
    problems: list[LedgerProblem] = []
    if row["source_repo"] != source.get("repository"):
        problems.append(
            LedgerProblem(row_id, "source_repo", "does not match qualification source repository")
        )
    if row["source_commit"] != source.get("commit"):
        problems.append(
            LedgerProblem(row_id, "source_commit", "does not match qualification source commit")
        )
    expected = digest_by_path.get(_as_str(row["source_path"]))
    digest = _string_field(row, "source_digest")
    if expected is None:
        problems.append(LedgerProblem(row_id, "source_path", "not a qualified source file"))
    elif digest is not None and expected != digest:
        problems.append(
            LedgerProblem(
                row_id, "source_digest", "does not match the qualified file digest (source drift)"
            )
        )
    return problems


def _mapped_row_problems(
    row_id: str,
    target: str | None,
    loss_ref: str | None,
    tier: str | None,
    *,
    package: str,
    scenario: raes.Scenario,
    bundle: dict[str, JsonObject],
) -> list[LedgerProblem]:
    """Problems for a ``mapped`` row: a resolvable target and no loss fields."""
    problems: list[LedgerProblem] = []
    if target is None:
        problems.append(
            LedgerProblem(row_id, "raes_target", "mapped row must name a resolvable target")
        )
    elif not resolve_target(target, package=package, scenario=scenario, bundle=bundle):
        problems.append(LedgerProblem(row_id, "raes_target", f"target does not resolve: {target}"))
    if loss_ref is not None or tier is not None:
        problems.append(LedgerProblem(row_id, "loss_ref", "mapped row must not carry loss fields"))
    return problems


def _excluded_row_problems(
    row_id: str, target: str | None, loss_ref: str | None, tier: str | None
) -> list[LedgerProblem]:
    """Problems for an ``excluded`` row: no target and no loss fields."""
    problems: list[LedgerProblem] = []
    if target is not None:
        problems.append(LedgerProblem(row_id, "raes_target", "excluded row must not name a target"))
    if loss_ref is not None or tier is not None:
        problems.append(
            LedgerProblem(row_id, "loss_ref", "excluded row must not carry loss fields")
        )
    return problems


def _loss_row_problems(
    row_id: str,
    target: str | None,
    loss_ref: str | None,
    tier: str | None,
    *,
    losses: dict[str, str],
    referenced: set[str],
) -> list[LedgerProblem]:
    """Problems for a ``loss-disclosed`` row: a known loss ref and an agreeing tier."""
    problems: list[LedgerProblem] = []
    if target is not None:
        problems.append(
            LedgerProblem(row_id, "raes_target", "loss-disclosed row must not name a target")
        )
    if loss_ref is None:
        problems.append(
            LedgerProblem(row_id, "loss_ref", "loss-disclosed row must reference a loss")
        )
        return problems
    if loss_ref not in losses:
        problems.append(LedgerProblem(row_id, "loss_ref", f"unknown loss {loss_ref!r}"))
        return problems
    referenced.add(loss_ref)
    if tier is None:
        problems.append(
            LedgerProblem(row_id, "equivalence_tier", "loss-disclosed row must name a tier")
        )
    elif tier not in RECOGNIZED_EQUIVALENCE_TIERS:
        problems.append(LedgerProblem(row_id, "equivalence_tier", f"unrecognized tier {tier!r}"))
    elif tier != losses[loss_ref]:
        problems.append(
            LedgerProblem(
                row_id, "equivalence_tier", f"tier {tier!r} disagrees with disclosure {loss_ref!r}"
            )
        )
    return problems


def _row_disposition_problems(
    row: JsonObject,
    row_id: str,
    *,
    package: str,
    scenario: raes.Scenario,
    bundle: dict[str, JsonObject],
    losses: dict[str, str],
    referenced: set[str],
) -> list[LedgerProblem]:
    """Dispatch to the disposition-specific target/loss checks for one row."""
    disposition = row["disposition"]
    target = _string_field(row, "raes_target")
    loss_ref = _string_field(row, "loss_ref")
    tier = _string_field(row, "equivalence_tier")
    if disposition == "mapped":
        problems = _mapped_row_problems(
            row_id, target, loss_ref, tier, package=package, scenario=scenario, bundle=bundle
        )
    elif disposition == "excluded":
        problems = _excluded_row_problems(row_id, target, loss_ref, tier)
    elif disposition == "loss-disclosed":
        problems = _loss_row_problems(
            row_id, target, loss_ref, tier, losses=losses, referenced=referenced
        )
    else:
        problems = [LedgerProblem(row_id, "disposition", f"unknown disposition {disposition!r}")]
    return problems


def _digest_by_path(qualification: JsonObject) -> dict[str, str]:
    """Map each qualified source path to its recorded SHA-256 digest."""
    result: dict[str, str] = {}
    for entry in _as_list(qualification.get("source_files")):
        obj = _as_object(entry)
        result[_as_str(obj.get("path"))] = _as_str(obj.get("sha256"))
    return result


class _LedgerContext(NamedTuple):
    """Shared inputs and running accumulators for one ledger validation pass.

    Bundling these keeps :func:`_validate_row` to a small parameter list; the
    ``seen_ids``/``categories``/``referenced`` sets accumulate across rows.
    """

    package: str
    source: JsonObject
    digest_by_path: dict[str, str]
    scenario: raes.Scenario
    bundle: dict[str, JsonObject]
    losses: dict[str, str]
    seen_ids: set[str]
    categories: set[str]
    referenced: set[str]


def _validate_row(row: JsonObject, position: int, context: _LedgerContext) -> list[LedgerProblem]:
    """Validate one ledger row (shape, identity, source join, disposition)."""
    raw_id = row.get("source_id")
    row_id = raw_id if isinstance(raw_id, str) else f"row[{position}]"
    shape = _row_shape_problems(row, row_id)
    if any(problem.reason == _MISSING_FIELD_REASON for problem in shape):
        return shape

    problems = list(shape)
    source_id = _as_str(row["source_id"])
    if source_id in context.seen_ids:
        problems.append(LedgerProblem(row_id, "source_id", "duplicate row id"))
    context.seen_ids.add(source_id)

    category = _as_str(row["category"])
    if category not in REQUIRED_CATEGORIES:
        problems.append(LedgerProblem(row_id, "category", f"unknown category {category!r}"))
    context.categories.add(category)

    problems += _row_source_problems(row, row_id, context.source, context.digest_by_path)
    problems += _row_disposition_problems(
        row,
        row_id,
        package=context.package,
        scenario=context.scenario,
        bundle=context.bundle,
        losses=context.losses,
        referenced=context.referenced,
    )
    return problems


def _coverage_problems(categories: set[str]) -> list[LedgerProblem]:
    """Report any required coverage category absent from the ledger."""
    return [
        LedgerProblem("<ledger>", "category", f"required category absent: {category}")
        for category in sorted(REQUIRED_CATEGORIES - categories)
    ]


def _disclosure_problems(losses: dict[str, str], referenced: set[str]) -> list[LedgerProblem]:
    """Report disclosures with a bad/absent tier or with no referencing row."""
    problems: list[LedgerProblem] = []
    for loss_id, tier in sorted(losses.items()):
        if tier not in RECOGNIZED_EQUIVALENCE_TIERS:
            reason = (
                "disclosure has no equivalence tier"
                if not tier
                else f"disclosure names unrecognized tier: {tier}"
            )
            problems.append(LedgerProblem(loss_id, "equivalence_tier", reason))
    for unreferenced in sorted(set(losses) - referenced):
        problems.append(
            LedgerProblem(
                unreferenced, "loss_ref", "disclosed loss is not referenced by any source row"
            )
        )
    return problems


def validate_source_ledger(
    rows: list[JsonObject],
    *,
    package: str,
    qualification: JsonObject,
    scenario: raes.Scenario,
    bundle: dict[str, JsonObject],
    losses: dict[str, str],
) -> list[LedgerProblem]:
    """Return every fail-closed problem in the ledger (empty list == valid)."""
    context = _LedgerContext(
        package=package,
        source=_as_object(qualification.get("source")),
        digest_by_path=_digest_by_path(qualification),
        scenario=scenario,
        bundle=bundle,
        losses=losses,
        seen_ids=set(),
        categories=set(),
        referenced=set(),
    )

    problems: list[LedgerProblem] = []
    for position, row in enumerate(rows):
        problems += _validate_row(row, position, context)
    problems += _coverage_problems(context.categories)
    problems += _disclosure_problems(losses, context.referenced)
    return problems


# --------------------------------------------------------------------------- #
# native-leakage scan
# --------------------------------------------------------------------------- #
def native_leakage_problems(
    markers: Iterable[str], portable_texts: Mapping[str, str]
) -> list[LedgerProblem]:
    """Return a problem for every native simulator marker in portable content.

    This enforces the native identifier and object-representation classes. Raw
    native arrays, reward vectors, and action ids are excluded structurally by
    the closed RAES SDL and experiment models rather than by this scan. Markers
    are matched case-insensitively; the caller supplies already-lowercased
    markers grounded in the backend's provenance.
    """
    ordered = sorted(set(markers))
    problems: list[LedgerProblem] = []
    for name, text in portable_texts.items():
        lowered = text.lower()
        problems += [
            LedgerProblem(name, "native-leakage", f"native marker present: {marker}")
            for marker in ordered
            if marker in lowered
        ]
    return problems


# --------------------------------------------------------------------------- #
# cross-artifact selection joins
# --------------------------------------------------------------------------- #
def _scenario_join_problems(
    scenario: raes.Scenario, digest: str, selection: EvidenceSelection
) -> list[LedgerProblem]:
    """Join the loaded scenario identity and digest to the selection pin."""
    problems: list[LedgerProblem] = []
    if scenario.name != selection.scenario_id:
        problems.append(
            LedgerProblem("scenario", "name", "scenario name does not match the selection id")
        )
    if digest != selection.pinned_scenario_digest:
        problems.append(
            LedgerProblem("scenario", "digest", "canonical digest does not match the selection pin")
        )
    return problems


def _task_join_problems(
    task: ExperimentTaskModel, selection: EvidenceSelection
) -> list[LedgerProblem]:
    """Join the task identity and its scenario reference to the selection."""
    problems: list[LedgerProblem] = []
    if task.task_id != selection.task_id:
        problems.append(LedgerProblem("task", "task_id", "task id does not match the selection"))
    scenario_ref = task.scenario_ref
    if getattr(scenario_ref, "ref_id", None) != selection.scenario_id:
        problems.append(
            LedgerProblem("task", "scenario_ref", "task scenario_ref id does not match scenario")
        )
    if getattr(scenario_ref, "ref_digest", None) != selection.pinned_scenario_digest:
        problems.append(
            LedgerProblem("task", "scenario_ref", "task scenario_ref digest does not match the pin")
        )
    return problems


def _spec_join_problems(
    spec: ExperimentSpecModel, selection: EvidenceSelection
) -> list[LedgerProblem]:
    """Join the spec identity and its task/scenario references to the selection."""
    problems: list[LedgerProblem] = []
    if spec.spec_id != selection.spec_id:
        problems.append(LedgerProblem("spec", "spec_id", "spec id does not match the selection"))
    if getattr(spec.task_ref, "ref_id", None) != selection.task_id:
        problems.append(LedgerProblem("spec", "task_ref", "spec task_ref does not match the task"))
    scenario_ref = getattr(spec, "intended_scenario_ref", None)
    if scenario_ref is None:
        return problems
    if getattr(scenario_ref, "ref_id", None) != selection.scenario_id:
        problems.append(
            LedgerProblem("spec", "intended_scenario_ref", "spec scenario_ref id does not match")
        )
    if getattr(scenario_ref, "ref_digest", None) != selection.pinned_scenario_digest:
        problems.append(
            LedgerProblem("spec", "intended_scenario_ref", "spec scenario_ref digest mismatch")
        )
    return problems


def _protocol_artifact_problems(
    task: ExperimentTaskModel, protocol_bytes: bytes
) -> list[LedgerProblem]:
    """Join the task's protocol artifact reference to the actual protocol bytes."""
    protocol_sha = hashlib.sha256(protocol_bytes).hexdigest()
    protocol_refs = [ref for ref in task.artifact_refs if getattr(ref, "role", None) == "protocol"]
    problems: list[LedgerProblem] = []
    if not protocol_refs:
        problems.append(LedgerProblem("task", "artifact_refs", "no protocol artifact reference"))
    for ref in protocol_refs:
        if getattr(getattr(ref, "checksum", None), "value", None) != protocol_sha:
            problems.append(
                LedgerProblem("task", "artifact_refs", "protocol checksum does not match resource")
            )
        if getattr(ref, "size_bytes", None) != len(protocol_bytes):
            problems.append(
                LedgerProblem("task", "artifact_refs", "protocol size does not match resource")
            )
    return problems


# --------------------------------------------------------------------------- #
# per-backend binder
# --------------------------------------------------------------------------- #
class ScenarioLedger(NamedTuple):
    """Bind the shared validators to one backend's evidence set.

    The binder holds the backend package (for reading checked-in resources), the
    already-shared qualification loader, the default evidence selection, and a
    callable producing the backend's native-leakage markers. A second case for
    the same backend is another :class:`EvidenceSelection` passed to these
    methods, not an edit to this class.
    """

    selection: EvidenceSelection
    package: str
    load_qualification: Callable[[], dict[str, object]]
    native_markers: Callable[[], set[str]]

    def _select(self, selection: EvidenceSelection | None) -> EvidenceSelection:
        """Return the given selection, or the binder's default."""
        return self.selection if selection is None else selection

    def scenario_source(self, selection: EvidenceSelection | None = None) -> str:
        """Return the authored RAES SDL scenario source verbatim."""
        return read_text(self.package, *self._select(selection).scenario_resource)

    def experiment_task_source(self, selection: EvidenceSelection | None = None) -> str:
        """Return the published experiment-task contract source verbatim."""
        return read_text(self.package, *self._select(selection).task_resource)

    def experiment_spec_source(self, selection: EvidenceSelection | None = None) -> str:
        """Return the published experiment-spec contract source verbatim."""
        return read_text(self.package, *self._select(selection).spec_resource)

    def protocol_source(self, selection: EvidenceSelection | None = None) -> str:
        """Return the selection's public-protocol resource verbatim."""
        return read_text(self.package, self._select(selection).protocol_resource)

    def load_scenario(self, selection: EvidenceSelection | None = None) -> raes.Scenario:
        """Parse and semantically validate the authored scenario via ``raes``."""
        return raes.parse_sdl(self.scenario_source(selection), path=None)

    def scenario_canonical_digest(self, selection: EvidenceSelection | None = None) -> str:
        """Instantiate the scenario and return its canonical snapshot digest."""
        instantiated = raes.instantiate_scenario(self.load_scenario(selection))
        return cast(str, raes.canonical_instantiated_sdl_digest(instantiated).value)

    def load_experiment_task(
        self, selection: EvidenceSelection | None = None
    ) -> ExperimentTaskModel:
        """Validate the companion experiment-task contract (closed RAES model)."""
        return ExperimentTaskModel.model_validate(
            _yaml_safe_load(self.experiment_task_source(selection))
        )

    def load_experiment_spec(
        self, selection: EvidenceSelection | None = None
    ) -> ExperimentSpecModel:
        """Validate the companion experiment-spec contract via ``raes_contracts``."""
        return parse_experiment_spec(self.experiment_spec_source(selection))

    def load_source_ledger(self, selection: EvidenceSelection | None = None) -> list[JsonObject]:
        """Load and strictly parse the pinned source-mapping ledger."""
        return parse_ledger_rows(read_text(self.package, *self._select(selection).ledger_resource))

    def load_loss_disclosures(self, selection: EvidenceSelection | None = None) -> dict[str, str]:
        """Return ``{loss_id: equivalence_tier}`` parsed from the disclosures doc."""
        return parse_loss_disclosures(
            read_text(self.package, *self._select(selection).losses_resource)
        )

    def native_identifier_markers(self) -> set[str]:
        """Native markers to reject in portable content, grounded in provenance."""
        return self.native_markers()

    def native_leakage_problems(self, portable_texts: Mapping[str, str]) -> list[LedgerProblem]:
        """Return a problem for every native simulator marker in portable content."""
        return native_leakage_problems(self.native_identifier_markers(), portable_texts)

    def resolve_target(self, target: str, *, scenario: raes.Scenario) -> bool:
        """Resolve a ``raes_target`` against parsed artifacts or the schema bundle."""
        return resolve_target(
            target, package=self.package, scenario=scenario, bundle=schema_bundle()
        )

    def validate_source_ledger(
        self, rows: list[JsonObject], *, scenario: raes.Scenario, losses: dict[str, str]
    ) -> list[LedgerProblem]:
        """Validate the ledger rows against the qualification, scenario, and losses."""
        return validate_source_ledger(
            rows,
            package=self.package,
            qualification=cast("JsonObject", self.load_qualification()),
            scenario=scenario,
            bundle=schema_bundle(),
            losses=losses,
        )

    def validate_selection_joins(
        self, selection: EvidenceSelection | None = None
    ) -> list[LedgerProblem]:
        """Validate the cross-artifact identity joins of one evidence selection.

        Independently valid artifacts are not enough: a stale reference or a
        drifted protocol digest must fail closed. This joins the scenario, task,
        and spec references to the selection's pinned identity and verifies the
        task's public protocol artifact against the actual protocol resource.
        """
        selection = self._select(selection)
        scenario = self.load_scenario(selection)
        task = self.load_experiment_task(selection)
        spec = self.load_experiment_spec(selection)
        problems = _scenario_join_problems(
            scenario, self.scenario_canonical_digest(selection), selection
        )
        problems += _task_join_problems(task, selection)
        problems += _spec_join_problems(spec, selection)
        problems += _protocol_artifact_problems(
            task, self.protocol_source(selection).encode("utf-8")
        )
        return problems

    def validate_scenario_pipeline(
        self, selection: EvidenceSelection | None = None
    ) -> list[LedgerProblem]:
        """Validate that the scenario parses, instantiates, compiles, and admits."""
        selection = self._select(selection)
        problems: list[LedgerProblem] = []
        scenario = self.load_scenario(selection)
        instantiated = raes.instantiate_scenario(scenario)
        digest = cast(str, raes.canonical_instantiated_sdl_digest(instantiated).value)
        if digest != selection.pinned_scenario_digest:
            problems.append(
                LedgerProblem("scenario", "digest", f"canonical digest drifted to {digest}")
            )
        runtime = compile_scenario_runtime_model(instantiated)
        for diagnostic in getattr(runtime, "diagnostics", []):
            problems.append(LedgerProblem("scenario", "compile", str(diagnostic)))
        raes.admit_instantiated_scenario(instantiated)
        return problems

    def validate_all(self, selection: EvidenceSelection | None = None) -> list[LedgerProblem]:
        """Run every deterministic check over the checked-in evidence set."""
        selection = self._select(selection)
        scenario = self.load_scenario(selection)
        problems: list[LedgerProblem] = []
        problems += self.validate_scenario_pipeline(selection)
        # validate_selection_joins loads (and thus closed-model-validates) the
        # task and spec, and joins every cross-artifact reference.
        problems += self.validate_selection_joins(selection)
        problems += self.validate_source_ledger(
            self.load_source_ledger(selection),
            scenario=scenario,
            losses=self.load_loss_disclosures(selection),
        )
        problems += self.native_leakage_problems(
            {
                "scenario": self.scenario_source(selection),
                "experiment-task": self.experiment_task_source(selection),
                "experiment-spec": self.experiment_spec_source(selection),
            }
        )
        return problems
