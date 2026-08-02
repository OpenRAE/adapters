"""Deterministic evidence loaders and validators for the PrimAITE scenario set.

Issue #40 authors a portable evidence set over the already-qualified PrimAITE
``data_manipulation`` case (issue #39):

* an authored RAES SDL scenario (:func:`scenario_source` / :func:`load_scenario`)
  carrying portable topology and objective truth, validated, instantiated,
  compiled, and admitted through the pinned ``raes==3.3.0`` release;
* companion published experiment contracts (:func:`load_experiment_task`,
  :func:`load_experiment_spec`) carrying the reward, metric, evaluator,
  fixed-horizon episode, and stochastic intent RAES excludes from SDL; and
* a pinned source-mapping ledger (:func:`load_ledger`) recording how every
  immutable PrimAITE source fact reaches a portable RAES surface, or why it does
  not, with each disclosed loss bound to the ADR-069 equivalence tier it weakens.

The validators are module-local helpers over checked-in package resources. They
compose the published RAES parser, the closed experiment contract models, the
published ``schema_bundle`` for target resolution, and the qualified
``qualification.json`` pins. They mint no new schema, DTO, vocabulary, policy
gate, or exception hierarchy; the disposition, category, and equivalence-tier
values are issue-local validator labels, not RAES vocabulary. The module mirrors
the *pattern* of the sibling CybORG and CyberBattleSim ledgers without importing
them or treating their backend-specific labels as shared authority (per
``docs/decisions/primaite-scenario-ledger-guardrails.md``).
"""

from __future__ import annotations

import hashlib
import json
import re
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

from . import load_qualification, read_public_protocol

# A decoded JSON document. Named rather than ``Any`` so the ledger rows and the
# schema-bundle walk carry a concrete (if dynamic) type.
type Json = None | bool | int | float | str | list["Json"] | dict[str, "Json"]
type JsonMap = dict[str, "Json"]

_PACKAGE = __package__ or "raes_adapters.primaite"


class Selection(NamedTuple):
    """One immutable PrimAITE evidence selection.

    The extension seam is an explicit selection identity, not a validator edit:
    a second public PrimAITE case is another :class:`Selection` handed to the
    same loaders and checks. Every cross-artifact identity the joins verify lives
    here so the members validate together: the scenario id and its pinned
    canonical digest, the task and spec ids, and a pinned content digest for each
    companion resource (task, spec, ledger, and loss-disclosures) so a
    semantically valid edit to a reviewed companion cannot stay green without
    updating this immutable selection. The public protocol is pinned separately
    through the task's protocol artifact reference (see :func:`_protocol_join`).
    """

    scenario_id: str
    scenario_digest: str
    scenario_parts: tuple[str, ...]
    task_id: str
    task_parts: tuple[str, ...]
    task_digest: str
    spec_id: str
    spec_parts: tuple[str, ...]
    spec_digest: str
    ledger_parts: tuple[str, ...]
    ledger_digest: str
    losses_parts: tuple[str, ...]
    losses_digest: str
    protocol_name: str


DATA_MANIPULATION = Selection(
    scenario_id="primaite-data-manipulation",
    scenario_digest="sha256:8f4c20885bbc3822587b38dc6c76c77915ecd225a2d753e54a1819c8370c80da",
    scenario_parts=("scenario", "data-manipulation.sdl.yaml"),
    task_id="primaite-data-manipulation-task",
    task_parts=("experiment", "data-manipulation.task.exp.yaml"),
    task_digest="sha256:44907d86daf43903bc98ac434492815fbe429a5fcc6b2341d9099b3e0ce5c2ba",
    spec_id="primaite-data-manipulation-spec",
    spec_parts=("experiment", "data-manipulation.spec.exp.yaml"),
    spec_digest="sha256:46d1bb9e0115045aefbdab0545fc692e809219c433b0be5a48e74cde4dd2e798",
    ledger_parts=("mapping", "source-ledger.jsonl"),
    ledger_digest="sha256:2fb69956b6a4ffedf891f0bda69c5599abf4074518050fa6aa1282a6de79af77",
    losses_parts=("mapping", "loss-disclosures.md"),
    losses_digest="sha256:2472dc77ef96f2cf3d08c90d2fffe0d386baa514d160fb84303cabc89e2fb50b",
    protocol_name="public-protocol.md",
)

# Pinned canonical instantiated-snapshot digest of the default selection. Any
# edit to the scenario changes this value and fails CI, so the portable scenario
# cannot drift silently from its reviewed form.
PINNED_SCENARIO_DIGEST = DATA_MANIPULATION.scenario_digest

DISPOSITIONS = frozenset({"mapped", "excluded", "loss-disclosed"})

# The issue-required coverage categories; every one must appear at least once.
CATEGORIES = frozenset(
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

# Issue-local labels for the ADR-069 tiered-equivalence ladder (see
# loss-disclosures.md); not a new RAES vocabulary.
EQUIVALENCE_TIERS = frozenset({"reproducibility", "deterministic-replay", "outcome-equivalence"})

_REQUIRED_FIELDS = (
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
)
_OPTIONAL_FIELDS = ("raes_target", "loss_ref", "equivalence_tier")
_ALLOWED_FIELDS = frozenset(_REQUIRED_FIELDS) | frozenset(_OPTIONAL_FIELDS)
_BLANK_FIELD = "missing or blank required field"

# Object/array/traceback serialization markers that must never appear in a
# portable artifact. Unlike CyberBattleSim's named observation dict, PrimAITE's
# BLUE observation is a flattened Box with no field identifiers, so the native
# *identifier* markers are grounded instead in the qualification record's
# scripted RED and GREEN participant refs (see :func:`_native_markers`); a raw
# flattened array, action id, or reward vector is additionally excluded
# structurally by the closed RAES SDL and experiment models.
_REPR_MARKERS: tuple[str, ...] = (
    "traceback (most recent call last)",
    " object at 0x",
    "ndarray(",
    "array([",
    "dtype(",
    "<primaite",
)

_HEADING = re.compile(r"^##\s+(?P<loss>\S+)\s*$")
_TIER_LINE = re.compile(r"^\*\*Equivalence tier:\*\*\s*(?P<tier>\S+)\s*$")


class LedgerProblem(NamedTuple):
    """One fail-closed validation problem: row id, field, and reason only."""

    row_id: str
    field: str
    reason: str

    def __str__(self) -> str:
        """Render as ``[row_id] field: reason``."""
        return f"[{self.row_id}] {self.field}: {self.reason}"


# --------------------------------------------------------------------------- #
# typed JSON accessors
# --------------------------------------------------------------------------- #
def _obj(value: Json) -> JsonMap:
    """The value as a JSON object, or an empty object."""
    return value if isinstance(value, dict) else {}


def _seq(value: Json) -> list[Json]:
    """The value as a JSON array, or an empty list."""
    return value if isinstance(value, list) else []


def _text(value: Json) -> str:
    """The value as a string, or the empty string."""
    return value if isinstance(value, str) else ""


def _nonblank(row: JsonMap, field: str) -> str | None:
    """A non-blank string field, else ``None``."""
    value = row.get(field)
    if isinstance(value, str) and value.strip():
        return value
    return None


# --------------------------------------------------------------------------- #
# package-resource loaders
# --------------------------------------------------------------------------- #
def _read(*parts: str) -> str:
    """Read a package resource as UTF-8 text."""
    return files(_PACKAGE).joinpath(*parts).read_text(encoding="utf-8")


def _is_resource(name: str) -> bool:
    """Whether the named package resource exists as a file."""
    return bool(files(_PACKAGE).joinpath(name).is_file())


def content_digest(*parts: str) -> str:
    """The ``sha256:``-prefixed digest of a package resource's UTF-8 bytes."""
    return "sha256:" + hashlib.sha256(_read(*parts).encode("utf-8")).hexdigest()


def scenario_source(selection: Selection = DATA_MANIPULATION) -> str:
    """The authored RAES SDL scenario source, verbatim."""
    return _read(*selection.scenario_parts)


def experiment_task_source(selection: Selection = DATA_MANIPULATION) -> str:
    """The published experiment-task contract source, verbatim."""
    return _read(*selection.task_parts)


def experiment_spec_source(selection: Selection = DATA_MANIPULATION) -> str:
    """The published experiment-spec contract source, verbatim."""
    return _read(*selection.spec_parts)


def _load_yaml(text: str) -> Json:
    """Parse YAML into a JSON-like value (lazy import)."""
    import yaml  # type: ignore[import-untyped]

    return cast("Json", yaml.safe_load(text))


def load_scenario(selection: Selection = DATA_MANIPULATION) -> raes.Scenario:
    """Parse and semantically validate the authored scenario through ``raes``."""
    return raes.parse_sdl(scenario_source(selection), path=None)


def instantiated_digest(selection: Selection = DATA_MANIPULATION) -> str:
    """Instantiate the scenario and return its canonical snapshot digest."""
    snapshot = raes.instantiate_scenario(load_scenario(selection))
    return cast(str, raes.canonical_instantiated_sdl_digest(snapshot).value)


def load_experiment_task(selection: Selection = DATA_MANIPULATION) -> ExperimentTaskModel:
    """Validate the companion experiment-task contract (closed RAES model)."""
    return ExperimentTaskModel.model_validate(_load_yaml(experiment_task_source(selection)))


def load_experiment_spec(selection: Selection = DATA_MANIPULATION) -> ExperimentSpecModel:
    """Validate the companion experiment-spec contract via ``raes_contracts``."""
    return parse_experiment_spec(experiment_spec_source(selection))


def parse_ledger(text: str) -> list[JsonMap]:
    """Strictly parse the JSONL ledger, rejecting corrupt evidence.

    Fails closed on invalid JSON, a non-object row, duplicate keys within a row,
    and the non-finite JSON constants, so a silently corrupt row cannot pass.
    """

    def _unique_keys(pairs: list[tuple[str, Json]]) -> JsonMap:
        built: JsonMap = {}
        for key, value in pairs:
            if key in built:
                raise ValueError(f"duplicate JSON key: {key!r}")
            built[key] = value
        return built

    def _no_constants(token: str) -> float:
        raise ValueError(f"non-finite JSON number is not permitted: {token}")

    rows: list[JsonMap] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        decoded = json.loads(raw, object_pairs_hook=_unique_keys, parse_constant=_no_constants)
        if not isinstance(decoded, dict):
            raise ValueError(f"ledger line {number} is not a JSON object")
        rows.append(cast("JsonMap", decoded))
    return rows


def load_ledger(selection: Selection = DATA_MANIPULATION) -> list[JsonMap]:
    """Load and strictly parse the pinned source-mapping ledger."""
    return parse_ledger(_read(*selection.ledger_parts))


def parse_disclosures(text: str) -> dict[str, str]:
    """Parse the disclosures document into ``{loss_id: equivalence_tier}``.

    Every ``## <loss_id>`` heading is retained; a heading with no tier line keeps
    an empty tier so it fails closed downstream rather than silently vanishing.
    """
    tiers: dict[str, str] = {}
    pending: str | None = None
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            if pending is not None:
                tiers.setdefault(pending, "")
            pending = heading.group("loss")
            continue
        matched = _TIER_LINE.match(line)
        if matched and pending is not None:
            tiers[pending] = matched.group("tier")
            pending = None
    if pending is not None:
        tiers.setdefault(pending, "")
    return tiers


def load_disclosures(selection: Selection = DATA_MANIPULATION) -> dict[str, str]:
    """Return ``{loss_id: equivalence_tier}`` parsed from the disclosures doc."""
    return parse_disclosures(_read(*selection.losses_parts))


# --------------------------------------------------------------------------- #
# RAES target resolution
# --------------------------------------------------------------------------- #
def _sdl_target(body: str, scenario: raes.Scenario) -> bool:
    """Resolve ``section`` or ``section.key`` against the parsed SDL scenario."""
    absent = object()
    section, _, key = body.partition(".")
    value = getattr(scenario, section, absent)
    if value is absent:
        return False
    if key:
        return isinstance(value, dict) and key in value
    return True


def _defs_of(schema: JsonMap) -> JsonMap:
    """The ``$defs`` block of a schema, as an object."""
    return _obj(schema.get("$defs"))


def _deref(root: JsonMap, node: JsonMap) -> JsonMap:
    """Follow a ``$ref`` on a property node, through ``items``/``anyOf``/``oneOf``."""
    candidate = node
    if "$ref" not in candidate:
        nested = _obj(candidate.get("items"))
        if "$ref" in nested:
            candidate = nested
    if "$ref" not in candidate:
        for keyword in ("anyOf", "oneOf"):
            for option in _seq(candidate.get(keyword)):
                option_obj = _obj(option)
                if "$ref" in option_obj:
                    candidate = option_obj
                    break
    ref = candidate.get("$ref")
    prefix = "#/$defs/"
    if isinstance(ref, str) and ref.startswith(prefix):
        return _obj(_defs_of(root).get(ref[len(prefix) :]))
    return candidate


def _contract_roots(bundle: dict[str, JsonMap]) -> tuple[dict[str, JsonMap], dict[str, JsonMap]]:
    """Index the schema bundle by contract title and by ``$defs`` class name."""
    by_title: dict[str, JsonMap] = {}
    by_def: dict[str, JsonMap] = {}
    for schema in bundle.values():
        title = schema.get("title")
        if isinstance(title, str):
            by_title[title] = schema
        for name in _defs_of(schema):
            by_def.setdefault(name, schema)
    return by_title, by_def


def _contract_target(path: str, bundle: dict[str, JsonMap]) -> bool:
    """Resolve ``Contract.property.path`` against the published schema bundle."""
    head, *steps = path.split(".")
    by_title, by_def = _contract_roots(bundle)
    if head in by_title:
        root = node = by_title[head]
    elif head in by_def:
        root = by_def[head]
        node = _obj(_defs_of(root).get(head))
    else:
        return False
    last = len(steps) - 1
    for depth, prop in enumerate(steps):
        properties = _obj(node.get("properties"))
        if prop not in properties:
            return False
        node = _obj(properties.get(prop))
        if depth < last:
            node = _deref(root, node)
    return True


def resolve_target(target: str, *, scenario: raes.Scenario, bundle: dict[str, JsonMap]) -> bool:
    """Resolve a ``raes_target`` against parsed artifacts or the schema bundle."""
    scheme, _, body = target.partition(":")
    if scheme == "sdl":
        return _sdl_target(body, scenario)
    if scheme == "contract":
        return _contract_target(body, bundle)
    if scheme == "resource":
        return _is_resource(body)
    return False


# --------------------------------------------------------------------------- #
# ledger row validation
# --------------------------------------------------------------------------- #
def _digest_index(qualification: JsonMap) -> dict[str, str]:
    """Map every qualified source path to its recorded SHA-256 digest."""
    index: dict[str, str] = {}
    for entry in _seq(qualification.get("source_files")):
        record = _obj(entry)
        index[_text(record.get("path"))] = _text(record.get("sha256"))
    return index


def _shape_problems(row: JsonMap, row_id: str) -> list[LedgerProblem]:
    """Unknown and missing/blank required fields for one row."""
    unknown = [
        LedgerProblem(row_id, field, "unknown ledger field")
        for field in sorted(set(row) - _ALLOWED_FIELDS)
    ]
    missing = [
        LedgerProblem(row_id, field, _BLANK_FIELD)
        for field in _REQUIRED_FIELDS
        if _nonblank(row, field) is None
    ]
    return unknown + missing


def _source_problems(
    row: JsonMap, row_id: str, source: JsonMap, digests: dict[str, str]
) -> list[LedgerProblem]:
    """Source-identity and offline source-drift join problems for one row."""
    problems: list[LedgerProblem] = []
    if row.get("source_repo") != source.get("repository"):
        problems.append(
            LedgerProblem(row_id, "source_repo", "does not match the qualified source repository")
        )
    if row.get("source_commit") != source.get("commit"):
        problems.append(
            LedgerProblem(row_id, "source_commit", "does not match the qualified source commit")
        )
    expected = digests.get(_text(row.get("source_path")))
    recorded = _nonblank(row, "source_digest")
    if expected is None:
        problems.append(LedgerProblem(row_id, "source_path", "not a qualified source file"))
    elif recorded is not None and recorded != expected:
        problems.append(
            LedgerProblem(row_id, "source_digest", "does not match the qualified digest (drift)")
        )
    return problems


class _RowFields(NamedTuple):
    """The disposition-relevant optional fields of one row, pre-extracted."""

    target: str | None
    loss_ref: str | None
    tier: str | None


def _mapped_problems(
    row_id: str, extra: _RowFields, *, scenario: raes.Scenario, bundle: dict[str, JsonMap]
) -> list[LedgerProblem]:
    """A ``mapped`` row needs a resolvable target and no loss fields."""
    problems: list[LedgerProblem] = []
    if extra.target is None:
        problems.append(LedgerProblem(row_id, "raes_target", "mapped row must name a target"))
    elif not resolve_target(extra.target, scenario=scenario, bundle=bundle):
        problems.append(
            LedgerProblem(row_id, "raes_target", f"target does not resolve: {extra.target}")
        )
    if extra.loss_ref is not None or extra.tier is not None:
        problems.append(LedgerProblem(row_id, "loss_ref", "mapped row must not carry loss fields"))
    return problems


def _excluded_problems(row_id: str, extra: _RowFields) -> list[LedgerProblem]:
    """An ``excluded`` row carries neither a target nor loss fields."""
    problems: list[LedgerProblem] = []
    if extra.target is not None:
        problems.append(LedgerProblem(row_id, "raes_target", "excluded row must not name a target"))
    if extra.loss_ref is not None or extra.tier is not None:
        problems.append(
            LedgerProblem(row_id, "loss_ref", "excluded row must not carry loss fields")
        )
    return problems


def _loss_problems(
    row_id: str, extra: _RowFields, *, disclosures: dict[str, str], referenced: set[str]
) -> list[LedgerProblem]:
    """A ``loss-disclosed`` row needs a known loss ref and its agreeing tier."""
    problems: list[LedgerProblem] = []
    if extra.target is not None:
        problems.append(
            LedgerProblem(row_id, "raes_target", "loss-disclosed row must not name a target")
        )
    if extra.loss_ref is None:
        problems.append(
            LedgerProblem(row_id, "loss_ref", "loss-disclosed row must reference a loss")
        )
        return problems
    if extra.loss_ref not in disclosures:
        problems.append(LedgerProblem(row_id, "loss_ref", f"unknown loss {extra.loss_ref!r}"))
        return problems
    referenced.add(extra.loss_ref)
    if extra.tier is None:
        problems.append(LedgerProblem(row_id, "equivalence_tier", "loss row must name a tier"))
    elif extra.tier not in EQUIVALENCE_TIERS:
        problems.append(
            LedgerProblem(row_id, "equivalence_tier", f"unrecognized tier {extra.tier!r}")
        )
    elif extra.tier != disclosures[extra.loss_ref]:
        problems.append(
            LedgerProblem(
                row_id,
                "equivalence_tier",
                f"tier {extra.tier!r} disagrees with disclosure {extra.loss_ref!r}",
            )
        )
    return problems


class _Pass(NamedTuple):
    """Shared inputs and running accumulators for one ledger validation pass."""

    source: JsonMap
    digests: dict[str, str]
    scenario: raes.Scenario
    bundle: dict[str, JsonMap]
    disclosures: dict[str, str]
    ids: set[str]
    categories: set[str]
    referenced: set[str]


def _disposition_problems(row: JsonMap, row_id: str, state: _Pass) -> list[LedgerProblem]:
    """Dispatch to the disposition-specific target/loss checks for one row."""
    extra = _RowFields(
        target=_nonblank(row, "raes_target"),
        loss_ref=_nonblank(row, "loss_ref"),
        tier=_nonblank(row, "equivalence_tier"),
    )
    disposition = row.get("disposition")
    if disposition == "mapped":
        return _mapped_problems(row_id, extra, scenario=state.scenario, bundle=state.bundle)
    if disposition == "excluded":
        return _excluded_problems(row_id, extra)
    if disposition == "loss-disclosed":
        return _loss_problems(
            row_id, extra, disclosures=state.disclosures, referenced=state.referenced
        )
    return [LedgerProblem(row_id, "disposition", f"unknown disposition {disposition!r}")]


def _row_problems(row: JsonMap, position: int, state: _Pass) -> list[LedgerProblem]:
    """Validate one row: shape, identity, source join, category, disposition."""
    raw = row.get("source_id")
    row_id = raw if isinstance(raw, str) and raw.strip() else f"row[{position}]"

    shape = _shape_problems(row, row_id)
    if any(problem.reason == _BLANK_FIELD for problem in shape):
        return shape

    problems = list(shape)
    identity = _text(row.get("source_id"))
    if identity in state.ids:
        problems.append(LedgerProblem(row_id, "source_id", "duplicate row id"))
    state.ids.add(identity)

    category = _text(row.get("category"))
    if category not in CATEGORIES:
        problems.append(LedgerProblem(row_id, "category", f"unknown category {category!r}"))
    state.categories.add(category)

    problems += _source_problems(row, row_id, state.source, state.digests)
    problems += _disposition_problems(row, row_id, state)
    return problems


def _missing_categories(seen: set[str]) -> list[LedgerProblem]:
    """A problem for every required category absent from the ledger."""
    return [
        LedgerProblem("<ledger>", "category", f"required category absent: {name}")
        for name in sorted(CATEGORIES - seen)
    ]


def _disclosure_problems(disclosures: dict[str, str], referenced: set[str]) -> list[LedgerProblem]:
    """Disclosures with a bad/absent tier or with no referencing row."""
    problems: list[LedgerProblem] = []
    for loss_id, tier in sorted(disclosures.items()):
        if tier not in EQUIVALENCE_TIERS:
            reason = (
                "disclosure has no equivalence tier"
                if not tier
                else f"disclosure names unrecognized tier: {tier}"
            )
            problems.append(LedgerProblem(loss_id, "equivalence_tier", reason))
    for orphan in sorted(set(disclosures) - referenced):
        problems.append(
            LedgerProblem(orphan, "loss_ref", "disclosed loss is not referenced by any row")
        )
    return problems


def validate_ledger(
    rows: list[JsonMap],
    *,
    qualification: JsonMap,
    scenario: raes.Scenario,
    bundle: dict[str, JsonMap],
    disclosures: dict[str, str],
) -> list[LedgerProblem]:
    """Every fail-closed problem in the ledger (an empty list means valid)."""
    state = _Pass(
        source=_obj(qualification.get("source")),
        digests=_digest_index(qualification),
        scenario=scenario,
        bundle=bundle,
        disclosures=disclosures,
        ids=set(),
        categories=set(),
        referenced=set(),
    )
    problems: list[LedgerProblem] = []
    for position, row in enumerate(rows):
        problems += _row_problems(row, position, state)
    problems += _missing_categories(state.categories)
    problems += _disclosure_problems(disclosures, state.referenced)
    return problems


# --------------------------------------------------------------------------- #
# native-leakage scan (grounded in qualification provenance)
# --------------------------------------------------------------------------- #
def _native_markers() -> set[str]:
    """Native markers to reject in portable content, grounded in provenance.

    The identifier markers are the scripted RED and GREEN participant refs
    recorded under ``protocol.selection.participants`` — distinctive native
    config identities the portable artifacts rename away from. The generic BLUE
    ``defender`` seat ref is deliberately not a marker: it is a plain defensive
    role token that legitimately recurs in portable vocabulary, so it would
    false-positive rather than catch pasted native state. The representation
    markers cover raw object/array/traceback leakage. Matching is
    case-insensitive.
    """
    participants = _obj(
        _obj(_obj(load_qualification().get("protocol")).get("selection")).get("participants")
    )
    markers: set[str] = set(_REPR_MARKERS)
    markers.add(_text(_obj(participants.get("red")).get("ref")).lower())
    for green in _seq(participants.get("green")):
        markers.add(_text(_obj(green).get("ref")).lower())
    markers.discard("")
    return markers


def native_leakage_problems(portable: dict[str, str]) -> list[LedgerProblem]:
    """A problem for every native PrimAITE marker found in portable content.

    Raw native arrays, action ids, reward vectors, and info dicts are excluded
    structurally by the closed RAES SDL and experiment models; this scan is
    defense in depth over the native-identifier and object-representation
    classes.
    """
    markers = _native_markers()
    problems: list[LedgerProblem] = []
    for name, text in portable.items():
        lowered = text.lower()
        problems += [
            LedgerProblem(name, "native-leakage", f"native marker present: {marker}")
            for marker in sorted(markers)
            if marker in lowered
        ]
    return problems


# --------------------------------------------------------------------------- #
# cross-artifact selection joins
# --------------------------------------------------------------------------- #
def _scenario_join(
    scenario: raes.Scenario, digest: str, selection: Selection
) -> list[LedgerProblem]:
    """Join the loaded scenario identity and digest to the selection pin."""
    problems: list[LedgerProblem] = []
    if scenario.name != selection.scenario_id:
        problems.append(LedgerProblem("scenario", "name", "name does not match the selection id"))
    if digest != selection.scenario_digest:
        problems.append(LedgerProblem("scenario", "digest", "canonical digest does not match pin"))
    return problems


def _task_join(task: ExperimentTaskModel, selection: Selection) -> list[LedgerProblem]:
    """Join the task identity and its scenario reference to the selection."""
    problems: list[LedgerProblem] = []
    if task.task_id != selection.task_id:
        problems.append(LedgerProblem("task", "task_id", "task id does not match the selection"))
    reference = task.scenario_ref
    if getattr(reference, "ref_id", None) != selection.scenario_id:
        problems.append(LedgerProblem("task", "scenario_ref", "scenario_ref id does not match"))
    if getattr(reference, "ref_digest", None) != selection.scenario_digest:
        problems.append(LedgerProblem("task", "scenario_ref", "scenario_ref digest does not match"))
    return problems


def _spec_join(spec: ExperimentSpecModel, selection: Selection) -> list[LedgerProblem]:
    """Join the spec identity and its task/scenario references to the selection."""
    problems: list[LedgerProblem] = []
    if spec.spec_id != selection.spec_id:
        problems.append(LedgerProblem("spec", "spec_id", "spec id does not match the selection"))
    if getattr(spec.task_ref, "ref_id", None) != selection.task_id:
        problems.append(LedgerProblem("spec", "task_ref", "task_ref does not match the task"))
    reference = getattr(spec, "intended_scenario_ref", None)
    if reference is None:
        return problems
    if getattr(reference, "ref_id", None) != selection.scenario_id:
        problems.append(LedgerProblem("spec", "intended_scenario_ref", "scenario_ref id mismatch"))
    if getattr(reference, "ref_digest", None) != selection.scenario_digest:
        problems.append(
            LedgerProblem("spec", "intended_scenario_ref", "scenario_ref digest mismatch")
        )
    return problems


def _protocol_join(task: ExperimentTaskModel, protocol: bytes) -> list[LedgerProblem]:
    """Join the task's protocol artifact reference to the actual protocol bytes."""
    digest = hashlib.sha256(protocol).hexdigest()
    references = [ref for ref in task.artifact_refs if getattr(ref, "role", None) == "protocol"]
    problems: list[LedgerProblem] = []
    if not references:
        problems.append(LedgerProblem("task", "artifact_refs", "no protocol artifact reference"))
    for ref in references:
        if getattr(getattr(ref, "checksum", None), "value", None) != digest:
            problems.append(
                LedgerProblem("task", "artifact_refs", "protocol checksum does not match resource")
            )
        if getattr(ref, "size_bytes", None) != len(protocol):
            problems.append(
                LedgerProblem("task", "artifact_refs", "protocol size does not match resource")
            )
    return problems


def _resource_pin_problems(selection: Selection) -> list[LedgerProblem]:
    """Join each companion resource's current content digest to its pin.

    The scenario is pinned by its canonical instantiated digest and the protocol
    by the task's artifact reference; this closes the boundary over the remaining
    reviewed companions (task, spec, ledger, and loss-disclosures) so a
    semantically valid edit to any of them cannot stay green without updating the
    immutable selection.
    """
    pinned = (
        ("task", selection.task_parts, selection.task_digest),
        ("spec", selection.spec_parts, selection.spec_digest),
        ("ledger", selection.ledger_parts, selection.ledger_digest),
        ("losses", selection.losses_parts, selection.losses_digest),
    )
    problems: list[LedgerProblem] = []
    for name, parts, expected in pinned:
        if content_digest(*parts) != expected:
            problems.append(
                LedgerProblem(name, "content_digest", "resource content does not match the pin")
            )
    return problems


def validate_joins(selection: Selection = DATA_MANIPULATION) -> list[LedgerProblem]:
    """Validate the cross-artifact identity joins of one evidence selection.

    Independently valid artifacts are not enough: a stale reference, a drifted
    protocol digest, or a silently edited companion resource must fail closed.
    This joins the scenario, task, and spec identities to the selection pin,
    verifies the task's protocol artifact against the actual protocol bytes, and
    pins the content of every companion resource.
    """
    scenario = load_scenario(selection)
    task = load_experiment_task(selection)
    spec = load_experiment_spec(selection)
    problems = _scenario_join(scenario, instantiated_digest(selection), selection)
    problems += _task_join(task, selection)
    problems += _spec_join(spec, selection)
    problems += _protocol_join(task, read_public_protocol().encode("utf-8"))
    problems += _resource_pin_problems(selection)
    return problems


# --------------------------------------------------------------------------- #
# scenario pipeline + top-level validation
# --------------------------------------------------------------------------- #
def validate_scenario_pipeline(selection: Selection = DATA_MANIPULATION) -> list[LedgerProblem]:
    """Validate that the scenario parses, instantiates, compiles, and admits."""
    problems: list[LedgerProblem] = []
    scenario = load_scenario(selection)
    snapshot = raes.instantiate_scenario(scenario)
    digest = cast(str, raes.canonical_instantiated_sdl_digest(snapshot).value)
    if digest != selection.scenario_digest:
        problems.append(
            LedgerProblem("scenario", "digest", f"canonical digest drifted to {digest}")
        )
    runtime = compile_scenario_runtime_model(snapshot)
    for diagnostic in getattr(runtime, "diagnostics", []):
        problems.append(LedgerProblem("scenario", "compile", str(diagnostic)))
    raes.admit_instantiated_scenario(snapshot)
    return problems


def validate_all(selection: Selection = DATA_MANIPULATION) -> list[LedgerProblem]:
    """Run every deterministic check over the checked-in evidence set."""
    problems: list[LedgerProblem] = []
    problems += validate_scenario_pipeline(selection)
    # validate_joins loads (and thus closed-model-validates) the task and spec
    # and joins every cross-artifact reference.
    problems += validate_joins(selection)
    problems += validate_ledger(
        load_ledger(selection),
        qualification=cast("JsonMap", load_qualification()),
        scenario=load_scenario(selection),
        bundle=schema_bundle(),
        disclosures=load_disclosures(selection),
    )
    problems += native_leakage_problems(
        {
            "scenario": scenario_source(selection),
            "experiment-task": experiment_task_source(selection),
            "experiment-spec": experiment_spec_source(selection),
        }
    )
    return problems
