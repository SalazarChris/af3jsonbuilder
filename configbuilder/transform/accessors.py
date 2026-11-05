"""Typed accessors (IMPLEMENTATION_PLAN.md §10.2).

The mapping tables name canonical accessors as strings; this module is the
single place that resolves those names against the actual model types and
performs the structural conversions the plan assigns to ``transform``:

- ``AlignmentPairing`` -> the four protein MSA wire fields with the correct
  omitted/empty/populated combination (MAP-601..606, spec §11 protein);
- ``SingleAlignment`` -> the RNA MSA field, inline xor path (MAP-606,
  spec §11 RNA);
- ``ReferenceSet`` -> omitted, or a (possibly empty) list (spec §6.2);
- ``ReferenceRecord.index_map`` -> two parallel 0-based arrays (MAP-703/704);
- ``Multiplicity`` -> single value or list form (spec §7.1);
- ``ComponentRepresentation`` -> exactly one of ccdCodes / smiles (MAP-406);
- ``Position``/``ResidueRef`` -> their stored 1-based values, never adjusted
  (MAP-903/904); ``IndexPair`` -> stored 0-based values, never adjusted.
"""

from __future__ import annotations

from configbuilder.identity import Multiplicity
from configbuilder.model import (
    AlignmentError,
    ComponentRecord,
    Configuration,
    External,
    FamilyARecord,
    FamilyBRecord,
    Inline,
    ExplicitEmpty,
    Present,
    Unset,
    fold_alignment,
    fold_reference_set,
    fold_representation,
    fold_resource,
    fold_single_alignment,
)
from configbuilder.transform.presence import OMITTED

__all__ = ["resolve", "root_field"]


def _msa_resource(source):
    """(inline_text, path_text) for a resource; exactly one is non-None."""

    def on_inline(text):
        return (text, None)

    def on_external(path):
        return (None, path.raw)

    return fold_resource(source, on_inline, on_external)


def _entity_id_field(ids: Multiplicity):
    """Single value or list form per spec §7.1."""
    if ids.count == 1:
        return ids.primary.value
    return [entity.value for entity in ids]


# -- protein MSA (MAP-601..605; spec §11 protein) ------------------------------


def _msa_side_fields(source, side: str):
    """One MSA side from its resource: inline xor path (spec §6.1).

    Returns the wire fields for ``side`` ("unpaired" or "paired"): the
    inline field carries the text for an Inline resource, the path field
    carries the raw path for an External one, and the other field of the
    side is omitted — inline and path are mutually exclusive, so a side
    never emits both and never emits an empty path.
    """
    inline, path = _msa_resource(source)
    if path is not None:
        return {side + "MsaPath": path, side + "Msa": OMITTED}
    if inline is not None:
        return {side + "Msa": inline, side + "MsaPath": OMITTED}
    raise AlignmentError("MSA resource has neither inline text nor a path")


def _protein_msa_fields(record: FamilyARecord):
    """The four protein MSA fields from one AlignmentPairing case.

    Spec §11 (protein): the two MSA fields are conceptually paired — a
    custom MSA is represented with both sides set, the empty side as the
    inline "" — so one-sided model cases emit populated + explicit-empty,
    never a single populated field. Within a side, inline and path are
    mutually exclusive (spec §6.1): a side emits exactly one of the inline
    or the path field, so a path-backed side points at its file and the
    empty counterpart side shows the inline "".
    """

    def on_automatic():
        return {
            "unpairedMsa": OMITTED,
            "unpairedMsaPath": OMITTED,
            "pairedMsa": OMITTED,
            "pairedMsaPath": OMITTED,
        }

    def on_free():
        return {
            "unpairedMsa": "",
            "unpairedMsaPath": OMITTED,
            "pairedMsa": "",
            "pairedMsaPath": OMITTED,
        }

    def on_unpaired_only(source):
        return {
            **_msa_side_fields(source, "unpaired"),
            "pairedMsa": "",
            "pairedMsaPath": OMITTED,
        }

    def on_paired_only(source):
        return {
            "unpairedMsa": "",
            "unpairedMsaPath": OMITTED,
            **_msa_side_fields(source, "paired"),
        }

    def on_both(source):
        # Both sides non-empty (MAP-605). Each side keeps its own resource;
        # a single-source AlignmentBoth reports the same source for both.
        return {
            **_msa_side_fields(source, "unpaired"),
            **_msa_side_fields(record.alignment.paired_source, "paired"),
        }

    return fold_alignment(
        record.alignment,
        on_automatic,
        on_free,
        on_unpaired_only,
        on_paired_only,
        on_both,
    )


# -- RNA MSA (MAP-606; spec §11 RNA) --------------------------------------------


def _rna_msa_value(record: FamilyBRecord, want_path: bool):
    """The RNA MSA field value for the inline or the path wire field.

    Automatic -> both omitted; MSA-free -> inline "" ; custom -> exactly
    one of inline text or path, per the resource's own representation.
    """
    alignment = record.alignment

    def on_automatic():
        return OMITTED

    def on_free():
        return OMITTED if want_path else ""

    def on_provided(source):
        inline, path = _msa_resource(source)
        if want_path:
            return path if path is not None else OMITTED
        return inline if inline is not None else OMITTED

    return fold_single_alignment(alignment, on_automatic, on_free, on_provided)


# -- shared conversions ----------------------------------------------------------


def _modification_entry(modification, code_field: str, position_field: str):
    """The wire modification entry: 1-based position as stored.

    Field names are family-specific (MAP-903 vs MAP-304/354): protein uses
    ``ptmType``/``ptmPosition``; RNA and DNA use ``modificationType`` /
    ``basePosition`` (spec §8: lines "RNA modifications use
    ``modificationType`` + 1-based ``basePosition``", likewise DNA).
    """
    return {
        code_field: modification.code.value,
        position_field: modification.position.value,
    }


_PROTEIN_MOD_FIELDS = ("ptmType", "ptmPosition")
_NUCLEIC_MOD_FIELDS = ("modificationType", "basePosition")


def _modifications_list(record):
    if not record.modifications:
        return OMITTED
    if isinstance(record, FamilyARecord):
        code_field, position_field = _PROTEIN_MOD_FIELDS
    else:
        code_field, position_field = _NUCLEIC_MOD_FIELDS
    return [_modification_entry(m, code_field, position_field) for m in record.modifications]


def _templates_field(record: FamilyARecord):
    """ReferenceSet -> omitted / list; index_map -> parallel arrays with the
    stored 0-based values, never adjusted (MAP-703/704). Both arrays are
    always emitted, empty when the mapping has no pairs: the AlphaFold 3
    parser indexes ``queryIndices`` directly, so a template entry without
    the arrays is rejected (``KeyError``), while a pair of empty arrays is a
    legitimate empty mapping."""

    def on_search_allowed():
        return OMITTED

    def on_explicit(items):
        templates = []
        for item in items:

            def on_inline(text):
                return {"mmcif": text}

            def on_external(path):
                return {"mmcifPath": path.raw}

            entry = fold_resource(item.source, on_inline, on_external)
            entry["queryIndices"] = [pair.query for pair in item.index_map]
            entry["templateIndices"] = [pair.template for pair in item.index_map]
            templates.append(entry)
        return templates

    return fold_reference_set(record.references, on_search_allowed, on_explicit)


def _ligand_representation_fields(record: ComponentRecord):
    """Exactly one of ccdCodes / smiles (MAP-406)."""
    return fold_representation(
        record.representation,
        on_code=lambda codes: {"ccdCodes": [code.value for code in codes]},
        on_notation=lambda text: {"smiles": text},
    )


def _bond_entry(linkage):
    """A bondedAtomPairs entry: (entity, residue, atom) triples with the
    stored 1-based residue values (MAP-801..806, MAP-904)."""
    return [
        [linkage.a.entity.value, linkage.a.residue.value, linkage.a.atom],
        [linkage.b.entity.value, linkage.b.residue.value, linkage.b.atom],
    ]


def _description_value(record):
    """Presence -> wire: Present -> text; ExplicitEmpty -> ""; Unset ->
    omitted. Never None (spec §6.2)."""
    if isinstance(record.description, Present):
        return record.description.value
    if isinstance(record.description, ExplicitEmpty):
        return ""
    if isinstance(record.description, Unset):
        return OMITTED
    raise ValueError("unknown description presence %r" % (record.description,))


# -- field resolution -------------------------------------------------------------


def _field_value(configuration: Configuration, record, accessor: str, version: int):
    """Resolve one family mapping-table accessor to its wire value."""
    if accessor == "ids":
        return _entity_id_field(record.ids)
    if accessor == "sequence.text":
        return record.sequence.text
    if accessor == "modifications":
        return _modifications_list(record)
    if accessor == "description":
        return _description_value(record)
    if accessor in (
        "alignment.unpaired_msa",
        "alignment.unpaired_msa_path",
        "alignment.paired_msa",
        "alignment.paired_msa_path",
    ):
        if isinstance(record, FamilyBRecord):
            # RNA: a single MSA field, inline xor path (MAP-307/308).
            return _rna_msa_value(record, want_path=accessor.endswith("path"))
        # Protein: the four paired MSA fields (MAP-207..210).
        fields = _protein_msa_fields(record)
        key = {
            "alignment.unpaired_msa": "unpairedMsa",
            "alignment.unpaired_msa_path": "unpairedMsaPath",
            "alignment.paired_msa": "pairedMsa",
            "alignment.paired_msa_path": "pairedMsaPath",
        }[accessor]
        return fields[key]
    if accessor == "templates":
        return _templates_field(record)
    if accessor == "representation.codes":
        return _ligand_representation_fields(record).get("ccdCodes", OMITTED)
    if accessor == "representation.smiles":
        return _ligand_representation_fields(record).get("smiles", OMITTED)
    raise KeyError("unresolved accessor %r" % accessor)


def root_field(configuration: Configuration, accessor: str):
    """Resolve one root mapping-table accessor to its wire value."""
    if accessor == "metadata.name":
        return configuration.metadata.name
    if accessor == "seeds.values":
        return list(configuration.seeds.values)
    if accessor == "":
        raise KeyError("root structural rows have no accessor")
    if accessor == "dialect.value":
        return configuration.format_target.dialect.value
    if accessor == "format_target.version":
        return OMITTED  # supplied by the version-selection step
    if accessor == "component_definition.inline":
        definition = configuration.component_definition
        if definition is None:
            return OMITTED
        if isinstance(definition, Inline):
            return definition.text
        return OMITTED
    if accessor == "component_definition.path":
        definition = configuration.component_definition
        if definition is None:
            return OMITTED
        if isinstance(definition, External):
            return definition.path.raw
        return OMITTED
    if accessor == "bond_pairs":
        if not configuration.linkages:
            return OMITTED
        return [_bond_entry(linkage) for linkage in configuration.linkages]
    raise KeyError("unresolved root accessor %r" % accessor)


def resolve(configuration: Configuration, table, record, version: int):
    """Resolve a whole mapping table to a {wire_field: value} mapping with
    OMITTED markers for omitted fields.

    Compound rows (empty accessor) are skipped: their wire fields are built
    as part of a parent value — entry sub-fields, aliases of another field,
    or the root ``sequences`` container — never resolved independently.
    """
    resolved = {}
    for accessor, wire_field, _mapping_id, rule, min_version in table:
        if not accessor:
            continue
        if version < min_version:
            resolved[wire_field] = OMITTED
            continue
        resolved[wire_field] = _field_value(configuration, record, accessor, version)
    return resolved
