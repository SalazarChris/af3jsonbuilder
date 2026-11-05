"""Traceability registry (IMPLEMENTATION_PLAN.md §3).

The single translation point between neutral internal names, mapping IDs,
and human-facing UI wording. Implemented as data; it is the only source the
UI consults for labels (plan §3.1), and a completeness test asserts every
canonical model type appears here with a mapping ID and a UI label (plan
§6.1 tests).
"""

from __future__ import annotations

from typing import Dict, Tuple

__all__ = ["TraceabilityEntry", "label_for", "mapping_ids_for", "registry_entries"]


class TraceabilityEntry:
    """One row of the plan §3 table."""

    __slots__ = ("internal_type", "family_tag", "mapping_ids", "ui_label")

    def __init__(self, internal_type: str, family_tag: str, mapping_ids: Tuple[str, ...], ui_label: str) -> None:
        self.internal_type = internal_type
        self.family_tag = family_tag
        self.mapping_ids = mapping_ids
        self.ui_label = ui_label

    def __repr__(self) -> str:
        return "TraceabilityEntry(%r -> %r %r)" % (self.internal_type, self.mapping_ids, self.ui_label)


_REGISTRY = (
    TraceabilityEntry("Configuration", "", ("MAP-001",), "Job"),
    TraceabilityEntry("ConfigurationMetadata", "", ("MAP-002", "MAP-101"), "Job details"),
    TraceabilityEntry("SeedSet", "", ("MAP-003", "MAP-102"), "Reproducibility seeds"),
    TraceabilityEntry("Record", "", ("MAP-004",), "Molecule"),
    TraceabilityEntry("FamilyARecord", "DataFamilyA", ("MAP-005",), "Protein chain"),
    TraceabilityEntry("FamilyBRecord", "DataFamilyB", ("MAP-006",), "RNA chain"),
    TraceabilityEntry("FamilyCRecord", "DataFamilyC", ("MAP-007",), "DNA strand"),
    TraceabilityEntry("ComponentRecord", "ComponentFamilyA", ("MAP-008",), "Ligand or ion"),
    TraceabilityEntry("ModificationRecord", "ModificationFamilyA", ("MAP-009", "MAP-204"), "Chemical modification"),
    TraceabilityEntry("AlignmentAutomatic", "", ("MAP-601",), "Automatic MSA search"),
    TraceabilityEntry("AlignmentFree", "", ("MAP-604",), "No alignment"),
    TraceabilityEntry("AlignmentUnpairedOnly", "", ("MAP-602",), "Unpaired MSA only"),
    TraceabilityEntry("AlignmentPairedOnly", "", ("MAP-603",), "Paired MSA only"),
    TraceabilityEntry("AlignmentBoth", "", ("MAP-605",), "Paired and unpaired MSA"),
    TraceabilityEntry("SingleAutomatic", "", ("MAP-601",), "Automatic RNA MSA search"),
    TraceabilityEntry("SingleFree", "", ("MAP-604",), "No RNA MSA"),
    TraceabilityEntry("SingleProvided", "", ("MAP-606",), "Custom RNA MSA"),
    TraceabilityEntry("ByCode", "", ("MAP-402", "MAP-405"), "Component codes"),
    TraceabilityEntry("ByNotation", "", ("MAP-403",), "SMILES notation"),
    TraceabilityEntry("ReferenceRecord", "", ("MAP-011", "MAP-1004"), "Structural reference"),
    TraceabilityEntry("ReferenceSet", "", ("MAP-705",), "Structural references"),
    TraceabilityEntry("SearchAllowed", "", ("MAP-705",), "Template search allowed"),
    TraceabilityEntry("Explicit", "", ("MAP-705",), "Explicit templates"),
    TraceabilityEntry("LinkEndpoint", "", ("MAP-801", "MAP-804"), "Bond endpoint"),
    TraceabilityEntry("Linkage", "", ("MAP-013", "MAP-1211"), "Covalent link"),
    TraceabilityEntry("Inline", "", ("MAP-1006",), "Inline content"),
    TraceabilityEntry("External", "", ("MAP-1001",), "File reference"),
    TraceabilityEntry("PathSpec", "", ("MAP-1001",), "File path"),
    TraceabilityEntry("Dialect", "", ("MAP-107",), "Dialect"),
    TraceabilityEntry("FormatTarget", "", ("MAP-107", "MAP-108"), "Format"),
    TraceabilityEntry("Unverified", "", ("MAP-108",), "Version unverified"),
    TraceabilityEntry("Pinned", "", ("MAP-108",), "Pinned version"),
    TraceabilityEntry("Auto", "", ("MAP-108",), "Automatic version"),
    TraceabilityEntry("Seed", "", ("MAP-907",), "Seed"),
    TraceabilityEntry("EntityId", "", ("MAP-901",), "Chain identifier"),
    TraceabilityEntry("Multiplicity", "", ("MAP-902",), "Copies"),
    TraceabilityEntry("Unset", "", ("MAP-601",), "Field omitted"),
    TraceabilityEntry("ExplicitEmpty", "", ("MAP-604",), "Field empty"),
    TraceabilityEntry("Present", "", ("MAP-606",), "Field content"),
    TraceabilityEntry("Position", "", ("MAP-903",), "Residue position"),
    TraceabilityEntry("ResidueRef", "", ("MAP-904",), "Bond residue"),
    TraceabilityEntry("IndexPair", "", ("MAP-905", "MAP-906"), "Index mapping pair"),
    TraceabilityEntry("SequenceText", "", ("MAP-202",), "Sequence"),
    TraceabilityEntry("ComponentCode", "", ("MAP-204",), "Component code"),
    # Plan §3 table rows completed: every mapped concept is registered so
    # the step machine can label any FieldPath variant (§18.7 asserts full
    # registry coverage).
    TraceabilityEntry("ComponentDefinitionSource", "", ("MAP-012",), "Custom chemistry definition"),
    TraceabilityEntry("AlignmentSource", "", ("MAP-010",), "Sequence alignment source"),
    TraceabilityEntry("Variant", "", ("MAP-014",), "Variant"),
    TraceabilityEntry("VariantManifest", "", ("MAP-015",), "Variant report"),
    TraceabilityEntry("OutputReference", "", ("MAP-016",), "Result location"),
    # Error types are registered so every user-visible type has a label
    # (plan §3.1: the UI never falls back to raw internal names).
    TraceabilityEntry("ModelError", "", ("MAP-001",), "Builder error"),
    TraceabilityEntry("PresenceError", "", ("MAP-001",), "Field-state error"),
    TraceabilityEntry("ValueTypeError", "", ("MAP-901",), "Value error"),
    TraceabilityEntry("SequenceTextError", "", ("MAP-202",), "Sequence error"),
    TraceabilityEntry("ResourceRefError", "", ("MAP-1001",), "File-reference error"),
    TraceabilityEntry("AlignmentError", "", ("MAP-601",), "Alignment error"),
    TraceabilityEntry("ReferenceError", "", ("MAP-705",), "Template error"),
    TraceabilityEntry("RecordError", "", ("MAP-004",), "Record error"),
    TraceabilityEntry("ComponentRepresentationError", "", ("MAP-406",), "Ligand-representation error"),
    TraceabilityEntry("ConfigurationError", "", ("MAP-001",), "Configuration error"),
    TraceabilityEntry("TraceabilityEntry", "", ("MAP-001",), "Traceability row"),
)

_BY_TYPE: Dict[str, TraceabilityEntry] = {entry.internal_type: entry for entry in _REGISTRY}


def registry_entries() -> Tuple[TraceabilityEntry, ...]:
    return tuple(_REGISTRY)


def label_for(internal_type: str) -> str:
    """The UI label for an internal type. Raises for unregistered types:
    the UI must never fall back to raw internal names (plan §3.1)."""
    try:
        return _BY_TYPE[internal_type].ui_label
    except KeyError:
        raise KeyError(
            "no traceability entry for %r; every user-visible type must be registered" % internal_type
        )


def mapping_ids_for(internal_type: str) -> Tuple[str, ...]:
    return _BY_TYPE[internal_type].mapping_ids
