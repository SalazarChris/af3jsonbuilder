"""Record families and linkages (IMPLEMENTATION_PLAN.md §7.4, §7.5).

Families are separate types carrying only the fields the contract grants
them; no shared base adds capability (plan §2.1). Three deliberate modelling
choices from plan §7.4:

1. ``FamilyCRecord`` has no alignment field at all (DOMAIN_MAPPING §6 note).
2. ``ModificationRecord`` stores code and position only; base identity stays
   in the parent sequence (DOMAIN_MAPPING §8's four concepts stay separate).
3. ``ReferenceRecord.index_map`` stores pairs, not parallel arrays.

Whether a modification position lies within the parent sequence is a
RELATIONAL validation rule (R-ENT-007), not a model invariant: the model
stays constructible without validation (Phase 3 exit criterion).
"""

from __future__ import annotations

from typing import Protocol, Tuple

from configbuilder.identity import EntityId, Multiplicity
from configbuilder.model.alignment import (
    AlignmentAutomatic,
    AlignmentPairing,
    AlignmentError,
    SingleAlignment,
    SingleAutomatic,
)
from configbuilder.model.errors import ModelError
from configbuilder.model.presence import Unset, is_presence
from configbuilder.model.references import (
    Explicit,
    ReferenceError,
    SearchAllowed,
)
from configbuilder.model.values import (
    ComponentCode,
    Position,
    ResidueRef,
    SequenceText,
    reverse_complement,
)

__all__ = [
    "ByCode",
    "ByNotation",
    "ComponentRecord",
    "ComponentRepresentationError",
    "FamilyARecord",
    "FamilyBRecord",
    "FamilyCRecord",
    "duplex_partner",
    "LinkEndpoint",
    "Linkage",
    "ModificationRecord",
    "RecordError",
    "Record",
    "fold_representation",
]


class RecordError(ModelError):
    """Raised for invalid record or linkage construction."""


class ComponentRepresentationError(RecordError):
    """Raised for invalid component-representation construction."""


class Record(Protocol):
    """Minimal protocol: identity and descriptive metadata only (MAP-004)."""

    ids: Multiplicity
    description: object  # a Presence value: Unset | ExplicitEmpty | Present


class ModificationRecord:
    """A chemical replacement: component code + 1-based position (MAP-009).

    The four concepts of DOMAIN_MAPPING §8 stay separate by construction:
    residue identity lives in the parent sequence, chemistry here.
    """

    __slots__ = ("_code", "_position")

    def __init__(self, code: ComponentCode, position: Position) -> None:
        if not isinstance(code, ComponentCode):
            raise RecordError("code must be a ComponentCode")
        if not isinstance(position, Position):
            raise RecordError("position must be a Position (1-based)")
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_position", position)

    @property
    def code(self) -> ComponentCode:
        return self._code

    @property
    def position(self) -> Position:
        return self._position

    def __setattr__(self, name, value):
        raise RecordError("ModificationRecord is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ModificationRecord):
            return self._code == other._code and self._position == other._position
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("ModificationRecord", self._code, self._position))

    def __repr__(self) -> str:
        return "ModificationRecord(%r, %r)" % (self._code.value, self._position.value)


class ByCode:
    """The ligand's CCD representation: one or more component codes
    (MAP-402/405, MAP-1208). Ions use this form."""

    __slots__ = ("_codes",)

    def __init__(self, codes: Tuple[ComponentCode, ...]) -> None:
        if not isinstance(codes, tuple):
            codes = tuple(codes)
        if not codes:
            raise ComponentRepresentationError("ByCode requires at least one component code")
        for code in codes:
            if not isinstance(code, ComponentCode):
                raise ComponentRepresentationError("codes must be ComponentCode values")
        object.__setattr__(self, "_codes", codes)

    @property
    def codes(self) -> Tuple[ComponentCode, ...]:
        return self._codes

    def __setattr__(self, name, value):
        raise ComponentRepresentationError("ByCode is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ByCode):
            return self._codes == other._codes
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("ByCode", self._codes))

    def __repr__(self) -> str:
        return "ByCode(%r)" % ([c.value for c in self._codes],)


class ByNotation:
    """The ligand's SMILES representation (MAP-403); mutually exclusive
    with ``ByCode`` by construction (MAP-406, MAP-1209)."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ComponentRepresentationError("ByNotation requires non-empty text")
        object.__setattr__(self, "_text", text)

    @property
    def text(self) -> str:
        return self._text

    def __setattr__(self, name, value):
        raise ComponentRepresentationError("ByNotation is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ByNotation):
            return self._text == other._text
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("ByNotation", self._text))

    def __repr__(self) -> str:
        return "ByNotation(%r)" % self._text


def fold_representation(value, on_code, on_notation):
    """The only dispatch over ``ComponentRepresentation`` (plan §7.3)."""
    if isinstance(value, ByCode):
        return on_code(value.codes)
    if isinstance(value, ByNotation):
        return on_notation(value.text)
    raise ComponentRepresentationError(
        "fold_representation: unknown representation %r" % (value,)
    )


class _RecordBase:
    """Common machinery only: frozen fields, identity, description. Adds no
    family capability (plan §2.1)."""

    __slots__ = ("_ids", "_description")

    def _init_common(self, ids: Multiplicity, description) -> None:
        if not isinstance(ids, Multiplicity):
            raise RecordError("ids must be a Multiplicity")
        if not is_presence(description):
            raise RecordError("description must be a Presence value (Unset/ExplicitEmpty/Present)")
        object.__setattr__(self, "_ids", ids)
        object.__setattr__(self, "_description", description)

    def __setattr__(self, name, value):
        raise RecordError("%s is immutable" % type(self).__name__)

    @property
    def ids(self) -> Multiplicity:
        return self._ids

    @property
    def description(self):
        return self._description

    def _common_key(self):
        return (type(self).__name__, self._ids, self._description)

    # Reconstruction is a model service (plan §7.4: families own their
    # fields): every family implements ``with_description`` and whatever
    # ``with_*`` methods its granted fields support, each rebuilding
    # through the validated constructor. Callers — variant edits, future
    # phases — never re-assemble record fields by hand.

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return self._common_key() == other._common_key()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._common_key())


def _validated_modifications(modifications) -> Tuple[ModificationRecord, ...]:
    if not isinstance(modifications, tuple):
        modifications = tuple(modifications)
    for mod in modifications:
        if not isinstance(mod, ModificationRecord):
            raise RecordError("modifications must be ModificationRecord values")
    return modifications


class FamilyARecord(_RecordBase):
    """Protein chain (MAP-005): sequence, modifications, pairing alignment,
    structural references."""

    __slots__ = ("_sequence", "_modifications", "_alignment", "_references")

    def __init__(
        self,
        ids: Multiplicity,
        sequence: SequenceText,
        modifications: Tuple[ModificationRecord, ...] = (),
        alignment=None,
        references=None,
        description=None,
    ) -> None:
        self._init_common(ids, Unset() if description is None else description)
        if not isinstance(sequence, SequenceText) or sequence.family != "protein":
            raise RecordError("FamilyARecord requires a protein SequenceText")
        alignment = AlignmentAutomatic() if alignment is None else alignment
        if not isinstance(alignment, AlignmentPairing):
            raise AlignmentError("alignment must be an AlignmentPairing case")
        references = SearchAllowed() if references is None else references
        if not isinstance(references, (SearchAllowed, Explicit)):
            raise ReferenceError("references must be a ReferenceSet case")
        object.__setattr__(self, "_sequence", sequence)
        object.__setattr__(self, "_modifications", _validated_modifications(modifications))
        object.__setattr__(self, "_alignment", alignment)
        object.__setattr__(self, "_references", references)

    @property
    def sequence(self) -> SequenceText:
        return self._sequence

    @property
    def modifications(self) -> Tuple[ModificationRecord, ...]:
        return self._modifications

    @property
    def alignment(self):
        return self._alignment

    @property
    def references(self):
        return self._references

    def with_description(self, description):
        """This record with a new description Presence; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            modifications=self._modifications,
            alignment=self._alignment,
            references=self._references,
            description=description,
        )

    def with_sequence(self, sequence: SequenceText) -> "FamilyARecord":
        """This record with a new protein sequence; all else preserved."""
        return type(self)(
            ids=self._ids,
            description=self._description,
            modifications=self._modifications,
            alignment=self._alignment,
            references=self._references,
            sequence=sequence,
        )

    def with_modifications(self, modifications) -> "FamilyARecord":
        """This record with a new modification tuple; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            alignment=self._alignment,
            references=self._references,
            description=self._description,
            modifications=modifications,
        )

    def with_alignment(self, alignment) -> "FamilyARecord":
        """This record with a new AlignmentPairing case; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            modifications=self._modifications,
            references=self._references,
            description=self._description,
            alignment=alignment,
        )

    def with_references(self, references) -> "FamilyARecord":
        """This record with a new ReferenceSet case; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            modifications=self._modifications,
            alignment=self._alignment,
            description=self._description,
            references=references,
        )

    def _key(self):
        return (
            self._common_key(),
            self._sequence,
            self._modifications,
            self._alignment,
            self._references,
        )

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        return "FamilyARecord(ids=%r, len=%d, mods=%d)" % (
            [e.value for e in self._ids],
            len(self._sequence),
            len(self._modifications),
        )


class FamilyBRecord(_RecordBase):
    """RNA chain (MAP-006): sequence, modifications, single alignment."""

    __slots__ = ("_sequence", "_modifications", "_alignment")

    def __init__(
        self,
        ids: Multiplicity,
        sequence: SequenceText,
        modifications: Tuple[ModificationRecord, ...] = (),
        alignment=None,
        description=None,
    ) -> None:
        self._init_common(ids, Unset() if description is None else description)
        if not isinstance(sequence, SequenceText) or sequence.family != "rna":
            raise RecordError("FamilyBRecord requires an rna SequenceText")
        alignment = SingleAutomatic() if alignment is None else alignment
        if not isinstance(alignment, SingleAlignment):
            raise AlignmentError("alignment must be a SingleAlignment case")
        object.__setattr__(self, "_sequence", sequence)
        object.__setattr__(self, "_modifications", _validated_modifications(modifications))
        object.__setattr__(self, "_alignment", alignment)

    @property
    def sequence(self) -> SequenceText:
        return self._sequence

    @property
    def modifications(self) -> Tuple[ModificationRecord, ...]:
        return self._modifications

    @property
    def alignment(self):
        return self._alignment

    def with_description(self, description):
        """This record with a new description Presence; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            modifications=self._modifications,
            alignment=self._alignment,
            description=description,
        )

    def with_sequence(self, sequence: SequenceText) -> "FamilyBRecord":
        """This record with a new RNA sequence; all else preserved."""
        return type(self)(
            ids=self._ids,
            description=self._description,
            alignment=self._alignment,
            sequence=sequence,
            modifications=self._modifications,
        )

    def with_modifications(self, modifications) -> "FamilyBRecord":
        """This record with a new modification tuple; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            alignment=self._alignment,
            description=self._description,
            modifications=modifications,
        )

    def with_alignment(self, alignment) -> "FamilyBRecord":
        """This record with a new SingleAlignment case; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            modifications=self._modifications,
            description=self._description,
            alignment=alignment,
        )

    def _key(self):
        return (self._common_key(), self._sequence, self._modifications, self._alignment)

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        return "FamilyBRecord(ids=%r, len=%d, mods=%d)" % (
            [e.value for e in self._ids],
            len(self._sequence),
            len(self._modifications),
        )


class FamilyCRecord(_RecordBase):
    """DNA strand (MAP-007): sequence and modifications only. Deliberately
    carries no alignment and no reference field (DOMAIN_MAPPING §6 note):
    the contract grants none, so the type cannot hold one."""

    __slots__ = ("_sequence", "_modifications")

    def __init__(
        self,
        ids: Multiplicity,
        sequence: SequenceText,
        modifications: Tuple[ModificationRecord, ...] = (),
        description=None,
    ) -> None:
        self._init_common(ids, Unset() if description is None else description)
        if not isinstance(sequence, SequenceText) or sequence.family != "dna":
            raise RecordError("FamilyCRecord requires a dna SequenceText")
        object.__setattr__(self, "_sequence", sequence)
        object.__setattr__(self, "_modifications", _validated_modifications(modifications))

    @property
    def sequence(self) -> SequenceText:
        return self._sequence

    @property
    def modifications(self) -> Tuple[ModificationRecord, ...]:
        return self._modifications

    def with_description(self, description):
        """This record with a new description Presence; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            modifications=self._modifications,
            description=description,
        )

    def with_sequence(self, sequence: SequenceText) -> "FamilyCRecord":
        """This record with a new DNA sequence; all else preserved."""
        return type(self)(
            ids=self._ids,
            description=self._description,
            sequence=sequence,
            modifications=self._modifications,
        )

    def with_modifications(self, modifications) -> "FamilyCRecord":
        """This record with a new modification tuple; all else preserved."""
        return type(self)(
            ids=self._ids,
            sequence=self._sequence,
            description=self._description,
            modifications=modifications,
        )

    def complement(self) -> "FamilyCRecord":
        """The partner strand of this DNA record: same identity and
        metadata, reverse-complement sequence (DNA duplex feature).

        Both strands of a duplex are conventional 5'-to-3' sequences, so
        the partner is the reverse complement of this strand's sequence —
        the direction is decided here at the lowest boundary that knows
        the record shape, never in a front end. Modifications carry over
        unchanged: mapping a modification to the opposite strand is a
        domain decision the caller must make deliberately, not something
        ``complement`` may guess.

        Raises ``DnaComplementError`` from the sequence layer if the
        sequence is not DNA (unrepresentable by the type, so this only
        guards corrupt paths).
        """
        return type(self)(
            ids=self._ids,
            sequence=reverse_complement(self._sequence),
            modifications=self._modifications,
            description=self._description,
        )

    def _key(self):
        return (self._common_key(), self._sequence, self._modifications)

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        return "FamilyCRecord(ids=%r, len=%d, mods=%d)" % (
            [e.value for e in self._ids],
            len(self._sequence),
            len(self._modifications),
        )


def duplex_partner(configuration, record):
    """The other strand of the DNA duplex ``record`` belongs to, or ``None``.

    A DNA entry is committed as **two consecutive** DNA records — the given
    strand and its reverse complement (DNA duplex feature), allocated back
    to back. That construction is the only definition of a duplex the model
    has, so the partner is read back from it: the adjacent record that is a
    DNA strand *and* is exactly this record's reverse complement. Both
    directions are checked, so either strand of the pair answers with the
    other.

    ``None`` means this record is a lone strand — an imported single DNA
    chain, or a record that is not a DNA strand at all — and callers must
    then change nothing else. Requiring the complement to match keeps two
    independently entered DNA entries from being mistaken for a pair: adding
    ``ATGC`` and later adding ``GCAT`` yields two separate duplexes, each
    pairing only with the strand allocated beside it.

    Duck-typed on purpose: a DNA strand is recognised by carrying a ``dna``
    sequence, which keeps this a structural question rather than a
    record-family dispatch (``tests/architecture/test_model_rules.py``).
    """
    sequence = getattr(record, "sequence", None)
    if sequence is None or getattr(sequence, "family", None) != "dna":
        return None
    records = configuration.records
    index = next(
        (position for position, existing in enumerate(records) if existing is record),
        None,
    )
    if index is None:
        return None
    expected = reverse_complement(sequence).text
    for neighbour in (index + 1, index - 1):
        if not 0 <= neighbour < len(records):
            continue
        candidate = records[neighbour]
        if candidate is record:
            continue
        candidate_sequence = getattr(candidate, "sequence", None)
        if candidate_sequence is None or getattr(candidate_sequence, "family", None) != "dna":
            continue
        if candidate_sequence.text == expected:
            return candidate
    return None


class ComponentRecord(_RecordBase):
    """Ligand / ion-as-ligand (MAP-008): exactly one representation
    (MAP-406)."""

    __slots__ = ("_representation",)

    def __init__(self, ids: Multiplicity, representation, description=None) -> None:
        self._init_common(ids, Unset() if description is None else description)
        if not isinstance(representation, (ByCode, ByNotation)):
            raise ComponentRepresentationError(
                "representation must be ByCode or ByNotation"
            )
        object.__setattr__(self, "_representation", representation)

    @property
    def representation(self):
        return self._representation

    def with_description(self, description):
        """This record with a new description Presence; all else preserved."""
        return type(self)(ids=self._ids, description=description, representation=self._representation)

    def with_representation(self, representation) -> "ComponentRecord":
        """This record with a new ByCode/ByNotation representation; all else
        preserved."""
        return type(self)(ids=self._ids, description=self._description, representation=representation)

    def _key(self):
        return (self._common_key(), self._representation)

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        return "ComponentRecord(ids=%r, %r)" % (
            [e.value for e in self._ids],
            self._representation,
        )


class LinkEndpoint:
    """One bond endpoint: entity, 1-based residue, atom name
    (MAP-801..803/804..806)."""

    __slots__ = ("_entity", "_residue", "_atom")

    def __init__(self, entity: EntityId, residue: ResidueRef, atom: str) -> None:
        if not isinstance(entity, EntityId):
            raise RecordError("entity must be an EntityId")
        if not isinstance(residue, ResidueRef):
            raise RecordError("residue must be a ResidueRef (1-based)")
        if not isinstance(atom, str) or not atom.strip():
            raise RecordError("atom must be a non-empty atom name")
        object.__setattr__(self, "_entity", entity)
        object.__setattr__(self, "_residue", residue)
        object.__setattr__(self, "_atom", atom)

    @property
    def entity(self) -> EntityId:
        return self._entity

    @property
    def residue(self) -> ResidueRef:
        return self._residue

    @property
    def atom(self) -> str:
        return self._atom

    def __setattr__(self, name, value):
        raise RecordError("LinkEndpoint is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LinkEndpoint):
            return (
                self._entity == other._entity
                and self._residue == other._residue
                and self._atom == other._atom
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("LinkEndpoint", self._entity, self._residue, self._atom))

    def __repr__(self) -> str:
        return "LinkEndpoint(%r, %d, %r)" % (self._entity.value, self._residue.value, self._atom)


class Linkage:
    """An explicit covalent link between two endpoints (MAP-013, MAP-1211).

    Stored at the configuration root, not on a record: an endpoint pair may
    span two records and must have exactly one owner (plan §7.5)."""

    __slots__ = ("_a", "_b")

    def __init__(self, a: LinkEndpoint, b: LinkEndpoint) -> None:
        if not isinstance(a, LinkEndpoint) or not isinstance(b, LinkEndpoint):
            raise RecordError("linkage endpoints must be LinkEndpoint values")
        object.__setattr__(self, "_a", a)
        object.__setattr__(self, "_b", b)

    @property
    def a(self) -> LinkEndpoint:
        return self._a

    @property
    def b(self) -> LinkEndpoint:
        return self._b

    def __setattr__(self, name, value):
        raise RecordError("Linkage is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Linkage):
            return (self._a, self._b) == (other._a, other._b)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Linkage", self._a, self._b))

    def __repr__(self) -> str:
        return "Linkage(%r, %r)" % (self._a, self._b)
