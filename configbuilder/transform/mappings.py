"""Field-mapping tables (IMPLEMENTATION_PLAN.md §10.2).

One table per record family plus the root. Every row is
``(canonical_accessor, wire_field, mapping_id, emission_rule, min_version)``;
the engine below is generic over these rows, so adding a field is a table
row plus its accessor — never a new code path.

Emission rules come from the presence algebra:

- ``OMIT_IF_UNSET``        Unset -> omitted; value -> field
- ``OMIT_IF_UNSET_ELSE_EMPTY``  Unset -> omitted; ExplicitEmpty -> contract's
                            empty value; value -> field
- ``INLINE_XOR_PATH``      one resource: inline field or path field, the
                            other omitted
- ``ALWAYS``               field is always emitted (root contract fields)

Wire field names live here and in ``wire.py`` — nowhere else in the code
base (plan §10.1: the single-authority rule).
"""

from __future__ import annotations

from typing import Tuple

from configbuilder.transform.presence import EmissionRule

__all__ = [
    "ROOT_FIELDS",
    "PROTEIN_FIELDS",
    "RNA_FIELDS",
    "DNA_FIELDS",
    "LIGAND_FIELDS",
    "DESCRIPTION_MIN_VERSION",
    "MSA_PATH_MIN_VERSION",
    "TEMPLATE_PATH_MIN_VERSION",
    "USER_CCD_PATH_MIN_VERSION",
    "PATH_FEATURE_MIN_VERSIONS",
    "FEATURE_WORDS",
    "feature_word",
]

# Features added by later input versions (AlphaFold 3 docs/input.md,
# "Versions"): v2 added the external MSA and template file fields, v3 the
# external user-CCD field, v4 the textual description fields.
MSA_PATH_MIN_VERSION = 2
TEMPLATE_PATH_MIN_VERSION = 2
USER_CCD_PATH_MIN_VERSION = 3

# The description fields are confirmed in JSON v4 only (MAP-206, MAP-306,
# MAP-356, MAP-404: "CONFIRMED in JSON v4").
DESCRIPTION_MIN_VERSION = 4

# Wire fields that point at an external file, and the input version that
# introduced them. The engine derives the *used* features from the external
# resource requirements, so these numbers live here once.
PATH_FEATURE_MIN_VERSIONS = {
    "unpairedMsaPath": MSA_PATH_MIN_VERSION,
    "pairedMsaPath": MSA_PATH_MIN_VERSION,
    "mmcifPath": TEMPLATE_PATH_MIN_VERSION,
    "userCCDPath": USER_CCD_PATH_MIN_VERSION,
}

# How each version-sensitive feature is named when something has to explain a
# refusal to a user ("this job uses …"). The keys are the wire field names
# *this* table already holds and the versions above are keyed by, so a wire
# name never has to be spelled outside ``transform`` (plan §10.1); the words
# are plain English for whoever quotes them (today: R-VER-002's finding, which
# validation builds from the facts ``used_version_features`` hands it).
FEATURE_WORDS = {
    "description": "a per-entity description",
    "unpairedMsaPath": "an external MSA file (unpairedMsaPath)",
    "pairedMsaPath": "an external paired-MSA file (pairedMsaPath)",
    "mmcifPath": "an external template structure file (mmcifPath)",
    "userCCDPath": "an external custom-CCD definition file (userCCDPath)",
}


def feature_word(feature_name: str) -> str:
    """The plain-English name of one version-sensitive feature.

    A feature this table does not know is still named by its own field, so a
    new mapping row is explained before its wording is written down.
    """
    return FEATURE_WORDS.get(feature_name, "the %s field" % feature_name)

# (accessor-name, wire-field, mapping-id, emission-rule, min-version)
#
# ``accessor-name`` names the canonical value the row reads; the engine maps
# these names onto typed accessors in one place (``wire.py``). Root rows
# read the configuration; family rows read the record object. An empty
# accessor marks a compound-constructed row: a structural container (the
# root ``sequences`` list) or an entry sub-field (modification entry keys),
# which the engine builds as part of a parent value instead of resolving
# independently.

ROOT_FIELDS: Tuple[Tuple[str, str, str, EmissionRule, int], ...] = (
    ("metadata.name", "name", "MAP-101", EmissionRule.ALWAYS, 1),
    ("seeds.values", "modelSeeds", "MAP-102", EmissionRule.ALWAYS, 1),
    # MAP-103 is the structural container field; the engine emits it from the
    # record list itself (each entity is a one-key object), so this row only
    # records the mapping — it has no accessor and is never resolved.
    ("", "sequences", "MAP-103", EmissionRule.ALWAYS, 1),    ("dialect.value", "dialect", "MAP-107", EmissionRule.ALWAYS, 1),
    ("format_target.version", "version", "MAP-108", EmissionRule.ALWAYS, 1),
    ("component_definition.inline", "userCCD", "MAP-105", EmissionRule.INLINE_XOR_PATH, 1),
    ("component_definition.path", "userCCDPath", "MAP-106", EmissionRule.INLINE_XOR_PATH, USER_CCD_PATH_MIN_VERSION),
    ("bond_pairs", "bondedAtomPairs", "MAP-104", EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY, 1),
)

PROTEIN_FIELDS: Tuple[Tuple[str, str, str, EmissionRule, int], ...] = (
    ("ids", "id", "MAP-201", EmissionRule.ALWAYS, 1),
    ("sequence.text", "sequence", "MAP-202", EmissionRule.ALWAYS, 1),
    ("modifications", "modifications", "MAP-203", EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY, 1),
    ("", "ptmType", "MAP-204", EmissionRule.ALWAYS, 1),
    ("", "ptmPosition", "MAP-205", EmissionRule.ALWAYS, 1),
    (
        "alignment.unpaired_msa",
        "unpairedMsa",
        "MAP-207",
        EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY,
        1,
    ),
    (
        "alignment.unpaired_msa_path",
        "unpairedMsaPath",
        "MAP-208",
        EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY,
        MSA_PATH_MIN_VERSION,
    ),
    (
        "alignment.paired_msa",
        "pairedMsa",
        "MAP-209",
        EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY,
        1,
    ),
    (
        "alignment.paired_msa_path",
        "pairedMsaPath",
        "MAP-210",
        EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY,
        MSA_PATH_MIN_VERSION,
    ),
    ("templates", "templates", "MAP-211", EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY, 1),
    (
        "description",
        "description",
        "MAP-206",
        EmissionRule.OMIT_IF_UNSET,
        DESCRIPTION_MIN_VERSION,
    ),
)

RNA_FIELDS: Tuple[Tuple[str, str, str, EmissionRule, int], ...] = (
    ("ids", "id", "MAP-301", EmissionRule.ALWAYS, 1),
    ("sequence.text", "sequence", "MAP-302", EmissionRule.ALWAYS, 1),
    ("modifications", "modifications", "MAP-303", EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY, 1),
    ("", "modificationType", "MAP-304", EmissionRule.ALWAYS, 1),
    ("", "basePosition", "MAP-305", EmissionRule.ALWAYS, 1),
    (
        "alignment.unpaired_msa",
        "unpairedMsa",
        "MAP-307",
        EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY,
        1,
    ),
    (
        "alignment.unpaired_msa_path",
        "unpairedMsaPath",
        "MAP-308",
        EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY,
        MSA_PATH_MIN_VERSION,
    ),
    (
        "description",
        "description",
        "MAP-306",
        EmissionRule.OMIT_IF_UNSET,
        DESCRIPTION_MIN_VERSION,
    ),
)

DNA_FIELDS: Tuple[Tuple[str, str, str, EmissionRule, int], ...] = (
    ("ids", "id", "MAP-351", EmissionRule.ALWAYS, 1),
    ("sequence.text", "sequence", "MAP-352", EmissionRule.ALWAYS, 1),
    ("modifications", "modifications", "MAP-353", EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY, 1),
    ("", "modificationType", "MAP-354", EmissionRule.ALWAYS, 1),
    ("", "basePosition", "MAP-355", EmissionRule.ALWAYS, 1),
    (
        "description",
        "description",
        "MAP-356",
        EmissionRule.OMIT_IF_UNSET,
        DESCRIPTION_MIN_VERSION,
    ),
)

LIGAND_FIELDS: Tuple[Tuple[str, str, str, EmissionRule, int], ...] = (
    ("ids", "id", "MAP-401", EmissionRule.ALWAYS, 1),
    ("representation.codes", "ccdCodes", "MAP-402", EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY, 1),
    ("representation.smiles", "smiles", "MAP-403", EmissionRule.OMIT_IF_UNSET_ELSE_EMPTY, 1),
    (
        "description",
        "description",
        "MAP-404",
        EmissionRule.OMIT_IF_UNSET,
        DESCRIPTION_MIN_VERSION,
    ),
    # MAP-405: an ion is represented through the same ``ccdCodes`` field as
    # MAP-402 — the table records the alias rather than a second wire field.
    ("", "ccdCodes", "MAP-405", EmissionRule.ALWAYS, 1),
    # MAP-406: the exactly-one-representation constraint between MAP-402 and
    # MAP-403 (CCD vs SMILES sum type), not an emittable field of its own.
    ("", "", "MAP-406", EmissionRule.ALWAYS, 1),
)

FAMILY_TABLES = {
    "protein": PROTEIN_FIELDS,
    "rna": RNA_FIELDS,
    "dna": DNA_FIELDS,
    "ligand": LIGAND_FIELDS,
}
