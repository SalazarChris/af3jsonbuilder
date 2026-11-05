"""Canonical internal model (IMPLEMENTATION_PLAN.md §6.1, §7).

Imports nothing from project modules except ``identity`` value types
(plan §5.3 rule 1). The dangerous states of the external contract are
unrepresentable here rather than validated after the fact.
"""

from configbuilder.model.alignment import (
    AlignmentAutomatic,
    AlignmentBoth,
    AlignmentError,
    AlignmentFree,
    AlignmentPairedOnly,
    AlignmentPairing,
    AlignmentUnpairedOnly,
    SingleAlignment,
    SingleAutomatic,
    SingleFree,
    SingleProvided,
    fold_alignment,
    fold_single_alignment,
)
from configbuilder.model.configuration import (
    DEFAULT_INPUT_VERSION,
    SUPPORTED_INPUT_VERSIONS,
    Auto,
    Configuration,
    ConfigurationError,
    ConfigurationMetadata,
    Dialect,
    FormatTarget,
    Pinned,
    SeedSet,
    Unverified,
    VersionSelection,
    fold_version_selection,
)
from configbuilder.model.amino_acids import (
    AMINO_ACID_NAMES,
    D_AMINO_ACIDS,
    D_AMINO_ACID_NAMES,
    L_AMINO_ACIDS,
    d_code_for,
    d_name_for_code,
    has_d_form,
    is_d_code,
    residue_for_d_code,
)
from configbuilder.model.errors import ModelError
from configbuilder.model.presence import (
    ExplicitEmpty,
    PresenceError,
    Present,
    Unset,
    fold_presence,
    is_presence,
)
from configbuilder.model.records import (
    ByCode,
    ByNotation,
    ComponentRecord,
    ComponentRepresentationError,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    LinkEndpoint,
    Linkage,
    ModificationRecord,
    Record,
    RecordError,
    duplex_partner,
    fold_representation,
)
from configbuilder.model.references import (
    Explicit,
    ReferenceError,
    ReferenceRecord,
    ReferenceSet,
    SearchAllowed,
    fold_reference_set,
)
from configbuilder.model.traceability import (
    TraceabilityEntry,
    label_for,
    mapping_ids_for,
    registry_entries,
)
from configbuilder.model.values import (
    ComponentCode,
    DnaComplementError,
    External,
    IndexPair,
    Inline,
    PathSpec,
    Position,
    ResidueRef,
    ResourceRefError,
    Seed,
    SequenceText,
    SequenceTextError,
    ValueTypeError,
    fold_resource,
    reverse_complement,
    split_component_codes,
)

__all__ = [
    # presence
    "ExplicitEmpty", "Present", "Unset", "PresenceError", "fold_presence", "is_presence",
    # values
    "ComponentCode", "split_component_codes",
    "External", "IndexPair", "Inline", "PathSpec", "Position",
    "ResidueRef", "Seed", "SequenceText", "ValueTypeError", "SequenceTextError",
    "ResourceRefError", "DnaComplementError", "reverse_complement", "fold_resource",
    # alignment
    "AlignmentAutomatic", "AlignmentFree", "AlignmentUnpairedOnly",
    "AlignmentPairedOnly", "AlignmentBoth", "AlignmentPairing",
    "SingleAutomatic", "SingleFree", "SingleProvided", "SingleAlignment",
    "AlignmentError", "fold_alignment", "fold_single_alignment",
    # references
    "SearchAllowed", "Explicit", "ReferenceRecord", "ReferenceSet",
    "ReferenceError", "fold_reference_set",
    # records
    "Record", "FamilyARecord", "FamilyBRecord", "FamilyCRecord",
    "ComponentRecord", "ModificationRecord", "ByCode", "ByNotation",
    "ComponentRepresentationError", "RecordError", "LinkEndpoint", "Linkage",
    "duplex_partner", "fold_representation",
    # configuration
    "Configuration", "ConfigurationMetadata", "SeedSet", "FormatTarget",
    "Dialect", "Unverified", "Pinned", "Auto", "VersionSelection",
    "ConfigurationError", "fold_version_selection",
    "SUPPORTED_INPUT_VERSIONS", "DEFAULT_INPUT_VERSION",
    # amino-acid forms
    "L_AMINO_ACIDS", "D_AMINO_ACIDS", "AMINO_ACID_NAMES", "D_AMINO_ACID_NAMES",
    "has_d_form", "d_code_for", "d_name_for_code", "is_d_code", "residue_for_d_code",
    # errors
    "ModelError",
    # traceability
    "TraceabilityEntry", "label_for", "mapping_ids_for", "registry_entries",
]
