"""Identifier value types (IMPLEMENTATION_PLAN.md §6.2, §7.2).

The format constraint is the contract's own (AUTHORITATIVE_SPEC.md §7.1,
MAP-901): uppercase alphabetic identifiers. Format is enforced at
construction, so an invalid identifier is unrepresentable rather than a
validation finding waiting to happen.

This module imports nothing from other project modules (plan §5.3 rule 1).
"""

from __future__ import annotations

import string
from typing import Tuple

__all__ = ["EntityId", "Multiplicity"]

_ALLOWED = frozenset(string.ascii_uppercase)


class EntityId:
    """An immutable, format-validated entity identifier (MAP-901).

    Uppercase alphabetic only. Comparison and hashing are by value, so an
    ``EntityId`` is interchangeable with its equal anywhere a reference is
    resolved.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("EntityId value must be a string")
        if not value or not all(ch in _ALLOWED for ch in value):
            raise ValueError(
                "EntityId must be non-empty and uppercase alphabetic, got %r" % (value,)
            )
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EntityId):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "EntityId(%r)" % (self._value,)


class Multiplicity:
    """An ordered, deduplicated set of copy identifiers (MAP-902).

    Spec §7.1: a single identifier or a list of identifiers expresses copy
    multiplicity of one entity. The model always carries the list form;
    ``transform`` later emits single-value form when there is exactly one
    identifier. Every identifier in the multiplicity is reserved, so
    uniqueness holds across copies as well as across records (plan §8.2).
    """

    __slots__ = ("_ids",)

    def __init__(self, ids) -> None:
        seen = set()
        ordered = []
        for candidate in ids:
            entity_id = candidate if isinstance(candidate, EntityId) else EntityId(candidate)
            if entity_id in seen:
                raise ValueError("duplicate identifier in multiplicity: %r" % (entity_id.value,))
            seen.add(entity_id)
            ordered.append(entity_id)
        if not ordered:
            raise ValueError("a multiplicity requires at least one identifier")
        object.__setattr__(self, "_ids", tuple(ordered))

    @property
    def ids(self) -> Tuple[EntityId, ...]:
        return self._ids

    @property
    def primary(self) -> EntityId:
        """The first identifier; the stable record handle (plan §12.1)."""
        return self._ids[0]

    @property
    def count(self) -> int:
        return len(self._ids)

    def contains(self, entity_id: EntityId) -> bool:
        return entity_id in self._ids

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Multiplicity):
            return self._ids == other._ids
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._ids)

    def __len__(self) -> int:
        return len(self._ids)

    def __iter__(self):
        return iter(self._ids)

    def __repr__(self) -> str:
        return "Multiplicity(%r)" % ([entity.value for entity in self._ids],)
