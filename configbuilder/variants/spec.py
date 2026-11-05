"""Variant specification and lineage (IMPLEMENTATION_PLAN.md §12.1–§12.2).

A ``VariantSpec`` is base + an ordered, typed, serializable list of edits —
reviewable before application and persistable into the project file. The
``declared_factors`` are what the variant is *intended* to change; the
VARIANT-tier drift rule (plan §12.5) compares them against what actually
changed.
"""

from __future__ import annotations

from configbuilder.variants.edits import (
    EDIT_CLASSES,
    AddLinkage,
    AddModification,
    AddRecord,
    RemoveLinkage,
    RemoveModification,
    RemoveRecord,
    SetAlignment,
    SetComponentDefinition,
    SetComponentRepresentation,
    SetComponentCount,
    SetDescription,
    SetFormatTarget,
    SetJobDescription,
    SetName,
    SetReferences,
    SetSeeds,
    SetSequence,
    SetSingleAlignment,
)

__all__ = [
    "Lineage",
    "Variant",
    "VariantSpec",
    "VariantSpecError",
    "declared_changes",
]


class VariantSpecError(Exception):
    """Raised for malformed variant specifications (empty key, duplicate
    keys in a set, unknown edit payloads)."""


class VariantSpec:
    """A named, ordered list of edits over a base configuration."""

    __slots__ = ("_key", "_label", "_edits", "_declared_factors")

    def __init__(self, key: str, label: str, edits, declared_factors=()) -> None:
        if not isinstance(key, str) or not key.strip():
            raise VariantSpecError("variant key must be a non-empty string")
        if not isinstance(label, str) or not label.strip():
            raise VariantSpecError("variant label must be a non-empty string")
        edits = tuple(edits)
        for edit in edits:
            if not isinstance(edit, EDIT_CLASSES):
                raise VariantSpecError(
                    "%r: edit %r is not part of the edit vocabulary" % (key, edit)
                )
        declared_factors = tuple(declared_factors)
        for factor in declared_factors:
            if not isinstance(factor, str) or not factor.strip():
                raise VariantSpecError("declared factors must be non-empty strings")
        object.__setattr__(self, "_key", key)
        object.__setattr__(self, "_label", label)
        object.__setattr__(self, "_edits", edits)
        object.__setattr__(self, "_declared_factors", declared_factors)

    @property
    def key(self) -> str:
        return self._key

    @property
    def label(self) -> str:
        return self._label

    @property
    def edits(self):
        return self._edits

    @property
    def declared_factors(self):
        return self._declared_factors

    def __setattr__(self, name, value):
        raise VariantSpecError("VariantSpec is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, VariantSpec):
            return (
                self._key == other._key
                and self._edits == other._edits
                and self._declared_factors == other._declared_factors
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._key, self._edits, self._declared_factors))

    def __repr__(self) -> str:
        return "VariantSpec(%r, edits=%d)" % (self._key, len(self._edits))


class Lineage:
    """Provenance of one expanded variant (plan §12.2).

    ``base_fingerprint`` is the content hash of the base's wire document,
    so a manifest can prove which base a variant came from. ``applied_edits``
    and ``declared_factors`` travel into the manifest (MAP-015).
    """

    __slots__ = ("_base_fingerprint", "_applied_edits", "_declared_factors")

    def __init__(self, base_fingerprint: str, applied_edits, declared_factors) -> None:
        object.__setattr__(self, "_base_fingerprint", base_fingerprint)
        object.__setattr__(self, "_applied_edits", tuple(applied_edits))
        object.__setattr__(self, "_declared_factors", tuple(declared_factors))

    @property
    def base_fingerprint(self) -> str:
        return self._base_fingerprint

    @property
    def applied_edits(self):
        return self._applied_edits

    @property
    def declared_factors(self):
        return self._declared_factors

    def __setattr__(self, name, value):
        raise VariantSpecError("Lineage is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Lineage):
            return (
                self._base_fingerprint == other._base_fingerprint
                and self._applied_edits == other._applied_edits
                and self._declared_factors == other._declared_factors
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._base_fingerprint, self._applied_edits, self._declared_factors))

    def __repr__(self) -> str:
        return "Lineage(base=%s, edits=%d)" % (self._base_fingerprint[:12], len(self._applied_edits))


class Variant:
    """One expansion result: key, label, fully materialised configuration,
    and lineage (plan §12.2)."""

    __slots__ = ("_key", "_label", "_configuration", "_lineage")

    def __init__(self, key: str, label: str, configuration, lineage: Lineage) -> None:
        object.__setattr__(self, "_key", key)
        object.__setattr__(self, "_label", label)
        object.__setattr__(self, "_configuration", configuration)
        object.__setattr__(self, "_lineage", lineage)

    @property
    def key(self) -> str:
        return self._key

    @property
    def label(self) -> str:
        return self._label

    @property
    def configuration(self):
        return self._configuration

    @property
    def lineage(self) -> Lineage:
        return self._lineage

    def __setattr__(self, name, value):
        raise VariantSpecError("Variant is immutable")

    def __repr__(self) -> str:
        return "Variant(%r)" % self._key


# -- declared-change descriptors --------------------------------------------------

_FACTOR_BY_EDIT = {
    SetName: "job_name",
    SetJobDescription: "job_description",
    SetDescription: "chain_description",
    SetSeeds: "seeds",
    SetSequence: "sequence",
    AddModification: "modifications",
    RemoveModification: "modifications",
    SetAlignment: "alignment",
    SetSingleAlignment: "alignment",
    SetReferences: "references",
    SetComponentRepresentation: "ligand_representation",
    SetComponentCount: "component_count",
    AddRecord: "records",
    RemoveRecord: "records",
    AddLinkage: "bonded_atom_pairs",
    RemoveLinkage: "bonded_atom_pairs",
    SetComponentDefinition: "component_definition",
    SetFormatTarget: "format_target",
}


def declared_changes(spec: VariantSpec):
    """What this spec actually changes, as ``(factor, detail)`` pairs.

    ``factor`` is the coarse dimension from spec §15; ``detail`` carries the
    record key (through identity) where the edit targets one record, so the
    drift rule can attribute a wire-level difference to this edit. Details
    are deduplicated and ordered by first appearance.
    """
    changes = []
    seen = set()
    for edit in spec.edits:
        factor = _FACTOR_BY_EDIT.get(type(edit))
        if factor is None:
            raise VariantSpecError(
                "edit %r has no declared-change mapping; extend the vocabulary map"
                % (edit,)
            )
        record_key = getattr(edit, "_record_key", None)
        detail = record_key.value if record_key is not None else None
        key = (factor, detail)
        if key not in seen:
            seen.add(key)
            changes.append(key)
    return tuple(changes)
