"""Loaders and deterministic validators for the CyberBattleSim scenario evidence.

Issue #26 authors a portable evidence set for the qualified CyberBattleSim case:

- an authored RAES SDL scenario carrying topology/objective truth
  (:func:`load_scenario`), validated and compiled through the pinned
  ``raes==2.0.0`` release;
- a companion published experiment contract pair (:func:`load_experiment_task`,
  :func:`load_experiment_spec`) carrying the reward, evaluator, metric,
  episode/termination, and stochastic intent that RAES excludes from SDL; and
- a pinned source-mapping ledger (:func:`load_source_ledger`) recording how each
  immutable CyberBattleSim source fact reaches a portable RAES surface, or why it
  does not, with every disclosed loss bound to the ADR-069 equivalence tier it
  weakens.

The validators are module-local helpers over checked-in package resources. They
compose the published RAES parser, closed contract models, the published
``schema_bundle`` for target resolution, and the already-qualified
``qualification.json`` pins. They define no new schema, DTO, vocabulary, policy
gate, or exception hierarchy; the disposition, category, and equivalence-tier
labels are issue-local validation labels, not RAES vocabulary.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, cast

import raes  # type: ignore[import-untyped]
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentTaskModel,
    schema_bundle,
)
from raes_contracts.experiment_spec import (  # type: ignore[import-untyped]
    parse_experiment_spec,
)
from raes_processor.compiler import (  # type: ignore[import-untyped]
    compile_scenario_runtime_model,
)

from . import load_qualification, read_public_protocol

_PACKAGE = __package__ or "raes_adapters.cyberbattlesim"


@dataclass(frozen=True)
class EvidenceSelection:
    """One immutable CyberBattleSim evidence selection.

    Per the scenario/ledger guardrails the extension seam is an explicit
    selection identity: a second CyberBattleSim case is another
    ``EvidenceSelection`` passed to the same loaders and validator, not an edit
    to the validation code. Every cross-artifact identity the joins check
    (scenario id + pinned digest, task id, spec id) lives here, so the members
    are validated together rather than as independent singletons.
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


CYBERBATTLE_CHAIN = EvidenceSelection(
    scenario_id="cyberbattlesim-chain",
    scenario_resource=("scenario", "cyberbattle-chain.sdl.yaml"),
    pinned_scenario_digest="sha256:9d696ea7fa23a1e7cf4c1cbc145a7989370dc4e9afff2cd5a17d6d1af887b528",
    task_id="cyberbattlesim-chain-task",
    task_resource=("experiment", "cyberbattle-chain.task.exp.yaml"),
    spec_id="cyberbattlesim-chain-spec",
    spec_resource=("experiment", "cyberbattle-chain.spec.exp.yaml"),
    ledger_resource=("mapping", "source-ledger.jsonl"),
    losses_resource=("mapping", "loss-disclosures.md"),
    protocol_resource="public-protocol.md",
)

# Pinned instantiated-snapshot digest of the default selection's scenario. Any
# change to the scenario source changes this value and fails CI, so the portable
# scenario cannot drift silently from its reviewed form.
PINNED_SCENARIO_DIGEST = CYBERBATTLE_CHAIN.pinned_scenario_digest

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

# Issue-local labels for the ADR-069 tiered-equivalence ladder (see
# loss-disclosures.md); not a new RAES vocabulary.
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

# Native simulator object/array representation markers that must never appear in
# a portable RAES artifact. The native observation-field identifiers are not
# hand-listed here; they are read from the qualification record's recorded
# ``smoke.observation_keys`` (provenance) at scan time. These representation
# markers add object/array reprs and tracebacks. Raw native arrays, reward
# vectors, and action ids are separately excluded *structurally* by the closed
# RAES SDL and experiment models, which have no field to carry them; this scan
# is defense in depth over the native identifier and representation classes.
_NATIVE_REPR_MARKERS: tuple[str, ...] = (
    "traceback (most recent call last)",
    " object at 0x",
    "ndarray(",
    "array([",
    "<cyberbattle",
)

_LOSS_HEADING = re.compile(r"^## (?P<loss_id>\S+)\s*$")
_LOSS_TIER = re.compile(r"^\*\*Equivalence tier:\*\*\s*(?P<tier>\S+)\s*$")


@dataclass(frozen=True)
class LedgerProblem:
    """A single fail-closed validation problem (row id + field + reason only)."""

    row_id: str
    field: str
    reason: str

    def __str__(self) -> str:
        return f"[{self.row_id}] {self.field}: {self.reason}"


# --------------------------------------------------------------------------- #
# resource loaders
# --------------------------------------------------------------------------- #
def _read_text(*parts: str) -> str:
    return files(_PACKAGE).joinpath(*parts).read_text(encoding="utf-8")


def _resource_is_file(name: str) -> bool:
    return bool(files(_PACKAGE).joinpath(name).is_file())


def scenario_source(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> str:
    """Return the authored RAES SDL scenario source verbatim."""
    return _read_text(*selection.scenario_resource)


def experiment_task_source(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> str:
    """Return the published experiment-task contract source verbatim."""
    return _read_text(*selection.task_resource)


def experiment_spec_source(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> str:
    """Return the published experiment-spec contract source verbatim."""
    return _read_text(*selection.spec_resource)


def load_scenario(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> Any:
    """Parse and semantically validate the authored scenario via ``raes``."""
    return raes.parse_sdl(scenario_source(selection), path=None)


def scenario_canonical_digest(
    selection: EvidenceSelection = CYBERBATTLE_CHAIN,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Instantiate the scenario and return its canonical snapshot digest."""
    instantiated = raes.instantiate_scenario(load_scenario(selection), parameters=parameters)
    return cast(str, raes.canonical_instantiated_sdl_digest(instantiated).value)


def load_experiment_task(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> Any:
    """Validate the companion experiment-task contract (closed RAES model)."""
    return ExperimentTaskModel.model_validate(yaml_safe_load(experiment_task_source(selection)))


def load_experiment_spec(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> Any:
    """Validate the companion experiment-spec contract via ``raes_contracts``."""
    return parse_experiment_spec(experiment_spec_source(selection))


def yaml_safe_load(text: str) -> Any:
    # Localized YAML dependency: only the closed experiment-task model needs a
    # raw mapping (the spec has its own parser). Import lazily so a missing yaml
    # never breaks scenario-only callers.
    import yaml  # type: ignore[import-untyped]

    return yaml.safe_load(text)


def parse_ledger_rows(text: str) -> list[dict[str, Any]]:
    """Strictly parse the JSONL ledger, rejecting malformed evidence.

    Fails closed on invalid JSON, a non-object row, duplicate JSON keys, and
    non-finite numbers, so the source ledger cannot carry silently corrupt rows.
    """

    def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError(f"duplicate JSON key: {key!r}")
            seen[key] = value
        return seen

    def _reject_non_finite(value: str) -> float:
        raise ValueError(f"non-finite number is not permitted: {value}")

    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(
            line,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
        if not isinstance(row, dict):
            raise ValueError(f"ledger line {lineno} is not a JSON object")
        rows.append(cast("dict[str, Any]", row))
    return rows


def load_source_ledger(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> list[dict[str, Any]]:
    """Load and strictly parse the pinned source-mapping ledger."""
    return parse_ledger_rows(_read_text(*selection.ledger_resource))


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


def load_loss_disclosures(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> dict[str, str]:
    """Return ``{loss_id: equivalence_tier}`` parsed from the disclosures doc."""
    return parse_loss_disclosures(_read_text(*selection.losses_resource))


# --------------------------------------------------------------------------- #
# target resolution
# --------------------------------------------------------------------------- #
def _contract_indexes(
    bundle: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    title_index: dict[str, dict[str, Any]] = {}
    defs_root: dict[str, dict[str, Any]] = {}
    for schema in bundle.values():
        title = schema.get("title")
        if title:
            title_index[title] = schema
        for name in schema.get("$defs", {}):
            defs_root.setdefault(name, schema)
    return title_index, defs_root


def _follow_ref(root: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    if "$ref" not in node and "items" in node and "$ref" in node["items"]:
        node = node["items"]
    if "$ref" not in node:
        for combinator in ("anyOf", "oneOf"):
            for sub in node.get(combinator, []):
                if "$ref" in sub:
                    node = sub
                    break
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return cast("dict[str, Any]", root["$defs"][ref.split("/")[-1]])
    return node


def resolve_contract_target(path: str, bundle: dict[str, dict[str, Any]]) -> bool:
    head, *rest = path.split(".")
    title_index, defs_root = _contract_indexes(bundle)
    if head in title_index:
        root = node = title_index[head]
    elif head in defs_root:
        root = defs_root[head]
        node = cast("dict[str, Any]", root["$defs"][head])
    else:
        return False
    for index, prop in enumerate(rest):
        properties = node.get("properties", {})
        if prop not in properties:
            return False
        node = properties[prop]
        if index < len(rest) - 1:
            node = _follow_ref(root, node)
    return True


def resolve_sdl_target(body: str, scenario: Any) -> bool:
    _missing = object()
    if "." in body:
        section, key = body.split(".", 1)
        collection = getattr(scenario, section, _missing)
        return isinstance(collection, dict) and key in collection
    return getattr(scenario, body, _missing) is not _missing


def resolve_target(target: str, *, scenario: Any, bundle: dict[str, dict[str, Any]]) -> bool:
    """Resolve a ``raes_target`` against parsed artifacts or the schema bundle."""
    if target.startswith("sdl:"):
        return resolve_sdl_target(target[len("sdl:") :], scenario)
    if target.startswith("contract:"):
        return resolve_contract_target(target[len("contract:") :], bundle)
    if target.startswith("resource:"):
        return _resource_is_file(target[len("resource:") :])
    return False


# --------------------------------------------------------------------------- #
# validators
# --------------------------------------------------------------------------- #
def _string_field(row: dict[str, Any], field: str) -> str | None:
    value = row.get(field)
    return value if isinstance(value, str) and value.strip() else None


def validate_source_ledger(
    rows: list[dict[str, Any]],
    *,
    qualification: dict[str, Any],
    scenario: Any,
    bundle: dict[str, dict[str, Any]],
    losses: dict[str, str],
) -> list[LedgerProblem]:
    """Return every fail-closed problem in the ledger (empty list == valid)."""
    problems: list[LedgerProblem] = []
    source = qualification["source"]
    digest_by_path = {entry["path"]: entry["sha256"] for entry in qualification["source_files"]}

    seen_ids: set[str] = set()
    categories: set[str] = set()
    referenced_losses: set[str] = set()

    for position, row in enumerate(rows):
        row_id = (
            row.get("source_id") if isinstance(row.get("source_id"), str) else f"row[{position}]"
        )
        row_id = cast(str, row_id)

        unknown = set(row) - _ALLOWED_ROW_FIELDS
        for field in sorted(unknown):
            problems.append(LedgerProblem(row_id, field, "unknown ledger field"))

        missing = [f for f in sorted(_REQUIRED_ROW_FIELDS) if _string_field(row, f) is None]
        for field in missing:
            problems.append(LedgerProblem(row_id, field, "missing or blank required field"))
        if missing:
            continue

        if row["source_id"] in seen_ids:
            problems.append(LedgerProblem(row_id, "source_id", "duplicate row id"))
        seen_ids.add(row["source_id"])

        category = row["category"]
        if category not in REQUIRED_CATEGORIES:
            problems.append(LedgerProblem(row_id, "category", f"unknown category {category!r}"))
        categories.add(category)

        if row["source_repo"] != source["repository"]:
            problems.append(
                LedgerProblem(
                    row_id, "source_repo", "does not match qualification source repository"
                )
            )
        if row["source_commit"] != source["commit"]:
            problems.append(
                LedgerProblem(row_id, "source_commit", "does not match qualification source commit")
            )

        # Source-drift integrity join: the path must always be a qualified
        # source file (independent of whether a digest was supplied), and the
        # required digest must match it. Neither check can be bypassed by
        # omitting the optional-looking digest, because it is a required field.
        expected = digest_by_path.get(row["source_path"])
        digest = _string_field(row, "source_digest")
        if expected is None:
            problems.append(LedgerProblem(row_id, "source_path", "not a qualified source file"))
        elif digest is not None and expected != digest:
            problems.append(
                LedgerProblem(
                    row_id,
                    "source_digest",
                    "does not match the qualified file digest (source drift)",
                )
            )

        disposition = row["disposition"]
        if disposition not in DISPOSITIONS:
            problems.append(
                LedgerProblem(row_id, "disposition", f"unknown disposition {disposition!r}")
            )
            continue

        target = _string_field(row, "raes_target")
        loss_ref = _string_field(row, "loss_ref")
        tier = _string_field(row, "equivalence_tier")

        if disposition == "mapped":
            if target is None:
                problems.append(
                    LedgerProblem(row_id, "raes_target", "mapped row must name a resolvable target")
                )
            elif not resolve_target(target, scenario=scenario, bundle=bundle):
                problems.append(
                    LedgerProblem(row_id, "raes_target", f"target does not resolve: {target}")
                )
            if loss_ref is not None or tier is not None:
                problems.append(
                    LedgerProblem(row_id, "loss_ref", "mapped row must not carry loss fields")
                )
        elif disposition == "excluded":
            if target is not None:
                problems.append(
                    LedgerProblem(row_id, "raes_target", "excluded row must not name a target")
                )
            if loss_ref is not None or tier is not None:
                problems.append(
                    LedgerProblem(row_id, "loss_ref", "excluded row must not carry loss fields")
                )
        else:  # loss-disclosed
            if target is not None:
                problems.append(
                    LedgerProblem(
                        row_id, "raes_target", "loss-disclosed row must not name a target"
                    )
                )
            if loss_ref is None:
                problems.append(
                    LedgerProblem(row_id, "loss_ref", "loss-disclosed row must reference a loss")
                )
            elif loss_ref not in losses:
                problems.append(LedgerProblem(row_id, "loss_ref", f"unknown loss {loss_ref!r}"))
            else:
                referenced_losses.add(loss_ref)
                if tier is None:
                    problems.append(
                        LedgerProblem(
                            row_id,
                            "equivalence_tier",
                            "loss-disclosed row must name an equivalence tier",
                        )
                    )
                elif tier not in RECOGNIZED_EQUIVALENCE_TIERS:
                    problems.append(
                        LedgerProblem(row_id, "equivalence_tier", f"unrecognized tier {tier!r}")
                    )
                elif tier != losses[loss_ref]:
                    problems.append(
                        LedgerProblem(
                            row_id,
                            "equivalence_tier",
                            f"tier {tier!r} disagrees with disclosure {loss_ref!r}",
                        )
                    )

    for missing_category in sorted(REQUIRED_CATEGORIES - categories):
        problems.append(
            LedgerProblem("<ledger>", "category", f"required category absent: {missing_category}")
        )

    for loss_id, tier in sorted(losses.items()):
        if tier not in RECOGNIZED_EQUIVALENCE_TIERS:
            reason = (
                "disclosure has no equivalence tier"
                if not tier
                else f"disclosure names unrecognized tier: {tier}"
            )
            problems.append(LedgerProblem(loss_id, "equivalence_tier", reason))

    for unreferenced in sorted(set(losses) - referenced_losses):
        problems.append(
            LedgerProblem(
                unreferenced, "loss_ref", "disclosed loss is not referenced by any source row"
            )
        )

    return problems


def _native_identifier_markers(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> set[str]:
    """Native markers to reject in portable content, grounded in provenance.

    The native observation-field identifiers come from the qualification
    record's recorded ``smoke.observation_keys``; the representation markers are
    the fixed object/array/traceback reprs. Matching is case-insensitive.
    """
    observation_keys = load_qualification()["runtime"]["smoke"]["observation_keys"]
    markers = {str(key).lower() for key in observation_keys}
    markers.update(_NATIVE_REPR_MARKERS)
    return markers


def native_leakage_problems(
    portable_texts: dict[str, str],
    *,
    selection: EvidenceSelection = CYBERBATTLE_CHAIN,
) -> list[LedgerProblem]:
    """Return a problem for every native simulator marker in portable content.

    This enforces the native identifier and object-representation classes. Raw
    native arrays, reward vectors, and action ids are excluded structurally by
    the closed RAES SDL and experiment models rather than by this scan.
    """
    markers = _native_identifier_markers(selection)
    problems: list[LedgerProblem] = []
    for name, text in portable_texts.items():
        lowered = text.lower()
        for marker in sorted(markers):
            if marker in lowered:
                problems.append(
                    LedgerProblem(name, "native-leakage", f"native marker present: {marker}")
                )
    return problems


def _ref_field(reference: Any, field: str) -> Any:
    return getattr(reference, field, None)


def _protocol_artifact_problems(task: Any, protocol_bytes: bytes) -> list[LedgerProblem]:
    """Join the task's protocol artifact reference to the actual protocol bytes."""
    protocol_sha = hashlib.sha256(protocol_bytes).hexdigest()
    protocol_refs = [ref for ref in task.artifact_refs if _ref_field(ref, "role") == "protocol"]
    problems: list[LedgerProblem] = []
    if not protocol_refs:
        problems.append(LedgerProblem("task", "artifact_refs", "no protocol artifact reference"))
    for ref in protocol_refs:
        if _ref_field(_ref_field(ref, "checksum"), "value") != protocol_sha:
            problems.append(
                LedgerProblem("task", "artifact_refs", "protocol checksum does not match resource")
            )
        if _ref_field(ref, "size_bytes") != len(protocol_bytes):
            problems.append(
                LedgerProblem("task", "artifact_refs", "protocol size does not match resource")
            )
    return problems


def validate_selection_joins(
    selection: EvidenceSelection = CYBERBATTLE_CHAIN,
) -> list[LedgerProblem]:
    """Validate the cross-artifact identity joins of one evidence selection.

    Independently valid artifacts are not enough: a stale reference or a drifted
    protocol digest must fail closed. This joins the scenario, task, and spec
    references to the selection's pinned identity and verifies the task's public
    protocol artifact against the actual protocol resource.
    """
    problems: list[LedgerProblem] = []
    scenario = load_scenario(selection)
    task = load_experiment_task(selection)
    spec = load_experiment_spec(selection)
    digest = scenario_canonical_digest(selection)

    def add(where: str, field: str, reason: str) -> None:
        problems.append(LedgerProblem(where, field, reason))

    if scenario.name != selection.scenario_id:
        add("scenario", "name", "scenario name does not match the selection id")
    if digest != selection.pinned_scenario_digest:
        add("scenario", "digest", "canonical digest does not match the selection pin")

    if task.task_id != selection.task_id:
        add("task", "task_id", "task id does not match the selection")
    task_sref = task.scenario_ref
    if _ref_field(task_sref, "ref_id") != selection.scenario_id:
        add("task", "scenario_ref", "task scenario_ref id does not match the scenario")
    if _ref_field(task_sref, "ref_digest") != selection.pinned_scenario_digest:
        add("task", "scenario_ref", "task scenario_ref digest does not match the pin")

    if spec.spec_id != selection.spec_id:
        add("spec", "spec_id", "spec id does not match the selection")
    if _ref_field(spec.task_ref, "ref_id") != selection.task_id:
        add("spec", "task_ref", "spec task_ref does not match the task id")
    spec_sref = _ref_field(spec, "intended_scenario_ref")
    if spec_sref is not None:
        if _ref_field(spec_sref, "ref_id") != selection.scenario_id:
            add("spec", "intended_scenario_ref", "spec scenario_ref id does not match the scenario")
        if _ref_field(spec_sref, "ref_digest") != selection.pinned_scenario_digest:
            add("spec", "intended_scenario_ref", "spec scenario_ref digest does not match the pin")

    # Task public-protocol artifact <-> actual protocol resource, via the
    # incumbent read_public_protocol + SHA-256 join pattern.
    problems.extend(_protocol_artifact_problems(task, read_public_protocol().encode("utf-8")))
    return problems


def validate_scenario_pipeline(
    selection: EvidenceSelection = CYBERBATTLE_CHAIN,
) -> list[LedgerProblem]:
    """Validate that the scenario parses, instantiates, compiles, and admits."""
    problems: list[LedgerProblem] = []
    scenario = load_scenario(selection)
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


def validate_all(selection: EvidenceSelection = CYBERBATTLE_CHAIN) -> list[LedgerProblem]:
    """Run every deterministic check over the checked-in evidence set."""
    problems: list[LedgerProblem] = []
    problems.extend(validate_scenario_pipeline(selection))
    # validate_selection_joins loads (and thus closed-model-validates) the task
    # and spec, and joins every cross-artifact reference.
    problems.extend(validate_selection_joins(selection))
    problems.extend(
        validate_source_ledger(
            load_source_ledger(selection),
            qualification=load_qualification(),
            scenario=load_scenario(selection),
            bundle=schema_bundle(),
            losses=load_loss_disclosures(selection),
        )
    )
    problems.extend(
        native_leakage_problems(
            {
                "scenario": scenario_source(selection),
                "experiment-task": experiment_task_source(selection),
                "experiment-spec": experiment_spec_source(selection),
            },
            selection=selection,
        )
    )
    return problems
