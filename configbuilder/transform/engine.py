"""The transformation engine (IMPLEMENTATION_PLAN.md §10.1, §10.3).

``to_wire(configuration)`` is the only place a wire structure is built
(single-authority rule). It resolves the mapping tables, applies version
selection, and returns an ordered, JSON-ready ``WireDocument`` plus the
external-resource requirements the output layer will need to copy.

Version selection (plan §10.3): ``Unverified`` blocks; ``Pinned(n)`` emits
the evidenced version; ``Auto(evidenced)`` chooses the minimum evidenced
version covering the features used. No version is ever inferred.
"""

from __future__ import annotations

from typing import Tuple

from configbuilder.model import (
    ComponentRecord,
    Configuration,
    External,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    Present,
    fold_version_selection,
)
from configbuilder.transform.mappings import (
    DESCRIPTION_MIN_VERSION,
    DNA_FIELDS,
    LIGAND_FIELDS,
    PATH_FEATURE_MIN_VERSIONS,
    PROTEIN_FIELDS,
    RNA_FIELDS,
    ROOT_FIELDS,
    feature_word,
)
from configbuilder.transform.presence import OMITTED

__all__ = [
    "ExternalResourceRequirement",
    "TransformResult",
    "WireDocument",
    "to_wire",
    "used_version_features",
    "with_emitted_resource_paths",
    "with_wire_job_name",
]


class TransformError(Exception):
    """Raised when transformation cannot proceed (e.g. Unverified policy)."""


class WireDocument(dict):
    """An ordered, JSON-ready mapping (plan MAP-1104)."""


class ExternalResourceRequirement:
    """One external file the generated input references (MAP-1001..1005)."""

    __slots__ = ("kind", "raw_path")

    def __init__(self, kind: str, raw_path: str) -> None:
        self.kind = kind
        self.raw_path = raw_path

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ExternalResourceRequirement):
            return self.kind == other.kind and self.raw_path == other.raw_path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("ExternalResourceRequirement", self.kind, self.raw_path))

    def __repr__(self) -> str:
        return "ExternalResourceRequirement(%r, %r)" % (self.kind, self.raw_path)


class TransformResult:
    """The transform outputs: document, selected version, external files."""

    __slots__ = ("document", "version", "external_resources")

    def __init__(
        self,
        document: WireDocument,
        version: int,
        external_resources: Tuple[ExternalResourceRequirement, ...],
    ) -> None:
        self.document = document
        self.version = version
        self.external_resources = tuple(external_resources)


def _select_version(configuration: Configuration) -> int:
    """Version selection per plan §10.3. Never infers a version."""
    selection = configuration.format_target.version_selection

    def on_unverified():
        raise TransformError(
            "no format version has been verified against the deployment yet; "
            "pin a version observed to be accepted, citing its evidence "
            "record (plan §10.3)"
        )

    def on_pinned(version):
        return version

    def on_auto(evidenced):
        return min(evidenced)

    return fold_version_selection(selection, on_unverified, on_pinned, on_auto)


def used_version_features(configuration: Configuration) -> Tuple[Tuple[str, int, str], ...]:
    """The wire features this configuration uses that have a minimum version.

    ``description`` is the v4 textual field; the external file fields
    (``unpairedMsaPath``, ``pairedMsaPath``, ``mmcifPath``, ``userCCDPath``)
    are the v2/v3 fields that point at a file rather than carrying text. The
    minimum versions come from the mapping layer, never from here.

    Public because the version-feature gate exists twice by design: this
    module refuses to *emit* such a document (``_check_version_features``),
    and ``app`` joins this same answer into validation so readiness cannot
    say "ready" while generation refuses (R-VER-002). Only features the
    configuration actually uses appear — an unset field never does, and a
    path-mode field only while its path mode is active.

    Returns a sorted tuple rather than a set: the facts cross a module
    boundary into validation, and a deterministic order keeps a finding's
    wording (and any test asserting on it) stable. Each row is
    ``(feature, min_version, wording)`` — the wording travels with the name
    so validation can explain the refusal without ever naming a wire field
    itself (plan §10.1; the words live in the mapping layer).
    """
    features = set()
    for record in configuration.records:
        if not isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord, ComponentRecord)):
            continue
        if isinstance(record.description, Present):
            features.add(("description", DESCRIPTION_MIN_VERSION))
    for requirement in _collect_external_resources(configuration):
        min_version = PATH_FEATURE_MIN_VERSIONS.get(requirement.kind)
        if min_version is not None:
            features.add((requirement.kind, min_version))
    return tuple(
        (name, min_version, feature_word(name))
        for name, min_version in sorted(features)
    )


def _check_version_features(configuration: Configuration, version: int, evidenced: Tuple[int, ...]) -> None:
    """A feature needing a version above the pin is an error naming the
    feature — the version is never silently raised (plan §10.3)."""
    for feature_name, min_version, _word in used_version_features(configuration):
        if version < min_version:
            raise TransformError(
                "feature %r requires format version %d, but the evidenced "
                "selection is %d; a new verification run is needed (plan §10.3)"
                % (feature_name, min_version, version)
            )


def _prune_omitted(mapping):
    """Drop OMITTED entries; assert no None ever reaches the document."""
    result = {}
    for key, value in mapping.items():
        if value is OMITTED:
            continue
        if value is None:
            raise TransformError("wire value for %r is None; omitted fields must be OMITTED" % key)
        result[key] = value
    return result


def _record_table(record):
    if isinstance(record, FamilyARecord):
        return "protein", PROTEIN_FIELDS
    if isinstance(record, FamilyBRecord):
        return "rna", RNA_FIELDS
    if isinstance(record, FamilyCRecord):
        return "dna", DNA_FIELDS
    if isinstance(record, ComponentRecord):
        return "ligand", LIGAND_FIELDS
    raise TransformError("unknown record family %r" % type(record).__name__)


def _collect_external_resources(configuration: Configuration):
    """Every external file this configuration references (MAP-1001..1005)."""
    requirements = []
    for record in configuration.records:
        if isinstance(record, FamilyARecord):
            from configbuilder.model import AlignmentBoth, AlignmentPairedOnly, AlignmentUnpairedOnly

            alignment = record.alignment
            if isinstance(alignment, (AlignmentUnpairedOnly, AlignmentPairedOnly, AlignmentBoth)):
                # The requirement kind is the wire field that references the
                # file (MAP-1001/1002). AlignmentBoth carries an independent
                # source per side, so each side names its own file; a
                # single-source both keeps the historical same-file result.
                if not isinstance(alignment, AlignmentPairedOnly):
                    source = alignment.source
                    if isinstance(source, External):
                        requirements.append(
                            ExternalResourceRequirement("unpairedMsaPath", source.path.raw)
                        )
                if not isinstance(alignment, AlignmentUnpairedOnly):
                    paired_source = (
                        alignment.paired_source
                        if isinstance(alignment, AlignmentBoth)
                        else alignment.source
                    )
                    if isinstance(paired_source, External):
                        requirements.append(
                            ExternalResourceRequirement("pairedMsaPath", paired_source.path.raw)
                        )
            from configbuilder.model import Explicit

            if isinstance(record.references, Explicit):
                for item in record.references.items:
                    if isinstance(item.source, External):
                        requirements.append(
                            ExternalResourceRequirement("mmcifPath", item.source.path.raw)
                        )
        elif isinstance(record, FamilyBRecord):
            from configbuilder.model import SingleProvided

            if isinstance(record.alignment, SingleProvided):
                source = record.alignment.source
                if isinstance(source, External):
                    requirements.append(
                        ExternalResourceRequirement("unpairedMsaPath", source.path.raw)
                    )
    definition = configuration.component_definition
    if isinstance(definition, External):
        requirements.append(ExternalResourceRequirement("userCCDPath", definition.path.raw))
    return tuple(requirements)


def to_wire(configuration: Configuration) -> TransformResult:
    """Build the ordered wire document for a validated configuration.

    Pure: no filesystem, no clock, no randomness, no global state.
    Total on validated input: nothing here raises for user-fixable
    conditions; those are validation findings first.
    """
    version = _select_version(configuration)
    _check_version_features(configuration, version, ())

    document = WireDocument()
    # Root fields in mapping-table order.
    root_values = {}
    for accessor, wire_field, _mapping_id, rule, min_version in ROOT_FIELDS:
        if version < min_version:
            continue
        if not accessor:
            # Structural container row (e.g. ``sequences``); the engine
            # builds it from the record list, not from an accessor.
            continue
        from configbuilder.transform.accessors import root_field

        root_values[wire_field] = root_field(configuration, accessor)
    pruned = _prune_omitted(root_values)
    for key in ("name", "modelSeeds", "sequences", "bondedAtomPairs", "userCCD", "userCCDPath", "dialect", "version"):
        if key in pruned:
            document[key] = pruned[key]

    # sequences in record order; each entity is a one-key object.
    entities = []
    for record in configuration.records:
        family, table = _record_table(record)
        from configbuilder.transform.accessors import resolve

        resolved = resolve(configuration, table, record, version)
        entity = _prune_omitted(resolved)
        entities.append({family: entity})
    document["sequences"] = entities

    # version selection sets the wire version field.
    document["version"] = version

    # Root key order per spec §4 example.
    ordered = WireDocument()
    for key in ("name", "modelSeeds", "sequences", "bondedAtomPairs", "userCCD", "userCCDPath", "dialect", "version"):
        if key in document:
            ordered[key] = document[key]
    # Preserve any extra keys deterministically at the end (there are none
    # today; the mapping tables cover the whole contract).
    for key in document:
        if key not in ordered:
            ordered[key] = document[key]

    return TransformResult(ordered, version, _collect_external_resources(configuration))


# -- reviewed-plan adjustments (plan §13.2, §13.5) ---------------------------------
#
# The generation flow (plan §15 step 4→5) applies two wire-level agreements
# *after* validation and *before* encoding. They live here, not in ``app``:
# §10.1's single-authority rule says a wire structure is built only inside
# ``transform``, and these functions assign wire keys.


def with_wire_job_name(document: WireDocument, job_name: str) -> WireDocument:
    """Set the wire ``name`` field to the derived name the directory and
    filename will use (plan §13.2: the value inside the file and the path
    outside it agree).

    Validation runs on the un-overridden semantic documents; the override
    happens afterwards, so drift comparison never sees it.
    """
    adjusted = WireDocument(document)
    adjusted["name"] = job_name
    return adjusted


def with_emitted_resource_paths(document: WireDocument, emitted_paths) -> WireDocument:
    """Rewrite external resource path strings to their emitted forms
    (plan §13.5 path policies), as resolved by the output planner.

    ``emitted_paths`` maps ``wire_field -> {raw_path: emitted_path}``. The
    planner returns one ``ResourceEntry`` per ``(wire_field, raw_path)``,
    so a path value shared by several wire fields is rewritten only under
    the fields it actually appears in — an ``AlignmentBoth`` file that
    feeds both ``unpairedMsaPath`` and ``pairedMsaPath`` gets each field's
    own resolved form. A raw path that equals its emitted form is left
    untouched (still a pure function: same input, same output).
    """
    if not emitted_paths:
        return document

    def rewrite(value):
        # Copy-on-write: the input document is never mutated (the previous
        # implementation wrote through the shallow copy into the caller's
        # nested dicts), and the field name gates the rewrite, so a sequence
        # string that happens to equal a path is untouched.
        if isinstance(value, dict):
            result = WireDocument() if isinstance(value, WireDocument) else {}
            for key, item in value.items():
                field_paths = emitted_paths.get(key)
                if (
                    isinstance(item, str)
                    and field_paths is not None
                    and item in field_paths
                ):
                    result[key] = field_paths[item]
                else:
                    result[key] = rewrite(item)
            return result
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        return value

    # Every field the planner named is rewritten wherever it occurs: a
    # chain's alignment paths, a template entry's ``mmcifPath`` (nested under
    # ``templates``), and the root ``userCCDPath`` alike.
    return WireDocument(rewrite(document))
