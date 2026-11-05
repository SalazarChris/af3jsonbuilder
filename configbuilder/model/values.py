"""Canonical value types (IMPLEMENTATION_PLAN.md §7.2).

Each type exists so a contract distinction is unrepresentable to violate
(AUTHORITATIVE_SPEC.md §7, §8; DOMAIN_MAPPING §10, §12, §13):

- ``Position`` (1-based, MAP-903) and ``IndexPair`` (0-based, MAP-905/906)
  are distinct nominal types: a 1-based value can never be passed where a
  0-based value is expected, and vice versa.
- ``Seed`` carries the contract's uint32 range (MAP-907).
- ``SequenceText`` enforces each family's alphabet (MAP-202/302/352).
- ``ComponentCode`` rejects the prefix the contract forbids (MAP-204).
- ``ResourceRef`` keeps inline and external representations distinct
  (MAP-1001..1006) and ``fold_resource`` is its only dispatch.
"""

from __future__ import annotations

import string

from configbuilder.model.errors import ModelError

__all__ = [
    "ComponentCode",
    "External",
    "IndexPair",
    "Inline",
    "PathSpec",
    "Position",
    "ResidueRef",
    "Seed",
    "SequenceText",
    "ValueTypeError",
    "SequenceTextError",
    "ResourceRefError",
    "DnaComplementError",
    "reverse_complement",
    "fold_resource",
    "split_component_codes",
]

_FORBIDDEN_PREFIX = "CCD_"
_PROTEIN_ALPHABET = frozenset(string.ascii_uppercase)
_RNA_ALPHABET = frozenset("ACGU")
_DNA_ALPHABET = frozenset("ACGT")
_UINT32_MAX = 2 ** 32 - 1


class ValueTypeError(ModelError):
    """Raised for invalid value-type construction."""


class SequenceTextError(ValueTypeError):
    """Raised for sequence text violating its family alphabet."""


class ResourceRefError(ValueTypeError):
    """Raised for invalid resource-reference construction."""


class DnaComplementError(ValueTypeError):
    """Raised when a DNA strand's reverse complement cannot be constructed."""


class Position:
    """A 1-based polymer position (MAP-903). A distinct nominal type from
    ``IndexPair`` so the mixed index bases of spec §7 can never be confused."""

    __slots__ = ("_value",)

    def __init__(self, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueTypeError("Position must be a positive integer (1-based), got %r" % (value,))
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> int:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Position):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Position", self._value))

    def __repr__(self) -> str:
        return "Position(%d)" % self._value


class ResidueRef:
    """A 1-based residue reference used by linkages (MAP-904)."""

    __slots__ = ("_value",)

    def __init__(self, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueTypeError("ResidueRef must be a positive integer (1-based), got %r" % (value,))
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> int:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ResidueRef):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("ResidueRef", self._value))

    def __repr__(self) -> str:
        return "ResidueRef(%d)" % self._value


class IndexPair:
    """One (query_index, template_index) pair, both 0-based (MAP-905/906).

    ``ReferenceRecord`` stores pairs, not two parallel arrays, so equal
    length is guaranteed by the data structure (plan §7.4 choice 3);
    ``transform`` splits the pairs at the wire boundary.
    """

    __slots__ = ("_query", "_template")

    def __init__(self, query_index: int, template_index: int) -> None:
        for name, value in (("query_index", query_index), ("template_index", template_index)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueTypeError(
                    "IndexPair %s must be a non-negative integer (0-based), got %r" % (name, value)
                )
        object.__setattr__(self, "_query", query_index)
        object.__setattr__(self, "_template", template_index)

    @property
    def query(self) -> int:
        return self._query

    @property
    def template(self) -> int:
        return self._template

    def __eq__(self, other: object) -> bool:
        if isinstance(other, IndexPair):
            return self._query == other._query and self._template == other._template
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("IndexPair", self._query, self._template))

    def __repr__(self) -> str:
        return "IndexPair(%d, %d)" % (self._query, self._template)


class Seed:
    """A model-execution seed within the contract's uint32 range (MAP-907)."""

    __slots__ = ("_value",)

    def __init__(self, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or not (0 <= value <= _UINT32_MAX):
            raise ValueTypeError(
                "Seed must be an integer in 0..2^32-1, got %r" % (value,)
            )
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> int:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Seed):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Seed", self._value))

    def __repr__(self) -> str:
        return "Seed(%d)" % self._value


class SequenceText:
    """Polymer sequence text, constrained to its family's alphabet
    (MAP-202/302/352). Family is part of the type's identity: the alphabets
    differ (spec §5)."""

    __slots__ = ("_text", "_family")

    _ALPHABETS = {
        "protein": _PROTEIN_ALPHABET,
        "rna": _RNA_ALPHABET,
        "dna": _DNA_ALPHABET,
    }

    def __init__(self, text: str, family: str) -> None:
        if not isinstance(text, str):
            raise SequenceTextError("sequence text must be a string")
        if family not in self._ALPHABETS:
            raise SequenceTextError("unknown sequence family %r" % (family,))
        if not text:
            raise SequenceTextError("sequence text must be non-empty")
        invalid = sorted(set(text) - self._ALPHABETS[family])
        if invalid:
            raise SequenceTextError(
                "%s sequence contains characters outside its alphabet: %r" % (family, invalid)
            )
        object.__setattr__(self, "_text", text)
        object.__setattr__(self, "_family", family)

    @property
    def text(self) -> str:
        return self._text

    @property
    def family(self) -> str:
        return self._family

    def __len__(self) -> int:
        return len(self._text)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SequenceText):
            return self._text == other._text and self._family == other._family
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("SequenceText", self._family, self._text))

    def __repr__(self) -> str:
        return "SequenceText(%r, family=%r)" % (self._text, self._family)


_DNA_COMPLEMENTS = {"A": "T", "T": "A", "G": "C", "C": "G"}


def _require_dna_sequence(sequence) -> SequenceText:
    """Validation helper: refuse anything that is not a DNA sequence."""
    if not isinstance(sequence, SequenceText):
        raise DnaComplementError("reverse complement requires a SequenceText")
    if sequence.family != "dna":
        raise DnaComplementError(
            "reverse complement is defined for dna sequences only, got %r" % (sequence.family,)
        )
    return sequence


def reverse_complement(sequence: SequenceText) -> SequenceText:
    """The reverse complement of a DNA strand, as a new ``SequenceText``.

    Orientation contract (DNA duplex feature): both AF3 DNA entities are
    conventional 5'-to-3' sequences, so the partner of a strand is its
    reverse complement — complement each base, then reverse — never a
    per-position complement.

    Raises ``DnaComplementError`` for anything that is not a DNA-family
    ``SequenceText``. Validation is delegated to ``SequenceText`` itself,
    so alphabet discipline stays in one place.
    """
    _require_dna_sequence(sequence)
    complemented = "".join(_DNA_COMPLEMENTS[base] for base in sequence.text)
    return SequenceText(complemented[::-1], "dna")


class ComponentCode:
    """A component code value; rejects the prefix the contract forbids
    (spec §8.1: standalone AF3 rejects a code beginning with ``CCD_``)."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise ValueTypeError("ComponentCode must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueTypeError("ComponentCode must be non-empty")
        if stripped.upper().startswith(_FORBIDDEN_PREFIX):
            raise ValueTypeError(
                "ComponentCode must not start with %r (spec §8.1)" % _FORBIDDEN_PREFIX
            )
        # A component code is matched against CCD component IDs, so the
        # canonical (stripped) form is stored; this is normalization of
        # builder-side data, not user content modification (plan §16.5
        # preserves free text, not identifier fields).
        object.__setattr__(self, "_value", stripped)

    @property
    def value(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ComponentCode):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("ComponentCode", self._value))

    def __repr__(self) -> str:
        return "ComponentCode(%r)" % self._value


def split_component_codes(text: str) -> "tuple[str, ...]":
    """The component codes in ``text``, in the order written.

    Whitespace, commas and semicolons separate the components of one
    multi-component ligand (a glycan, an ion/water group), so the entity form
    and the file reader must read the same text the same way: this is that one
    tokenizer, and validation of each token stays ``ComponentCode``'s.

    Returns the raw tokens (empty tuple for empty text); callers keep their own
    wording for "nothing typed" and for a token the code type refuses.
    """
    return tuple(text.replace(",", " ").replace(";", " ").split())


class PathSpec:
    """A raw user path plus its normalization metadata (plan §7.2).

    The path is preserved verbatim: the builder never rewrites user paths.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: str) -> None:
        if not isinstance(raw, str) or not raw.strip():
            raise ResourceRefError("PathSpec requires a non-empty path string")
        object.__setattr__(self, "_raw", raw)

    @property
    def raw(self) -> str:
        return self._raw

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PathSpec):
            return self._raw == other._raw
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("PathSpec", self._raw))

    def __repr__(self) -> str:
        return "PathSpec(%r)" % self._raw


class Inline:
    """Inline content of an external-resource-valued field (MAP-1006 form)."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        if not isinstance(text, str):
            raise ResourceRefError("Inline content must be a string")
        object.__setattr__(self, "text", text)

    def __setattr__(self, name, value):
        raise ResourceRefError("Inline is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Inline):
            return self.text == other.text
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Inline", self.text))

    def __repr__(self) -> str:
        return "Inline(%r...)" % self.text[:12] if len(self.text) > 12 else "Inline(%r)" % self.text


class External:
    """An external file reference for an external-resource-valued field
    (MAP-1001..1005 form)."""

    __slots__ = ("path",)

    def __init__(self, path: PathSpec) -> None:
        if not isinstance(path, PathSpec):
            raise ResourceRefError("External requires a PathSpec")
        object.__setattr__(self, "path", path)

    def __setattr__(self, name, value):
        raise ResourceRefError("External is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, External):
            return self.path == other.path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("External", self.path))

    def __repr__(self) -> str:
        return "External(%r)" % (self.path.raw,)


def fold_resource(value, on_inline, on_external):
    """The only dispatch over ``ResourceRef`` (plan §7.3)."""
    if isinstance(value, Inline):
        return on_inline(value.text)
    if isinstance(value, External):
        return on_external(value.path)
    raise ResourceRefError("fold_resource: unknown resource value %r" % (value,))
