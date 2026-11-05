"""Structural references (IMPLEMENTATION_PLAN.md §7.3, §7.4; spec §12).

``ReferenceSet`` distinguishes "template search allowed" (field omitted)
from "explicitly template-free" (empty list) — spec §6.2 applied to
templates, MAP-705. ``ReferenceRecord.index_map`` stores ``(query,
template)`` pairs, both 0-based (MAP-703/704, MAP-905/906), so the parallel
arrays of the wire are derived, and equal length is structural.
"""

from __future__ import annotations

from typing import Tuple

from configbuilder.model.errors import ModelError
from configbuilder.model.values import External, Inline, IndexPair

__all__ = ["ReferenceError", "ReferenceRecord", "ReferenceSet", "fold_reference_set"]


class ReferenceError(ModelError):
    """Raised for invalid reference construction or unknown fold cases."""


class ReferenceRecord:
    """One structural template: source plus the 0-based index mapping
    (MAP-011)."""

    __slots__ = ("_source", "_index_map")

    def __init__(self, source, index_map: Tuple[IndexPair, ...]) -> None:
        if not isinstance(source, (Inline, External)):
            raise ReferenceError("source must be an Inline or External resource")
        if not isinstance(index_map, tuple):
            index_map = tuple(index_map)
        for pair in index_map:
            if not isinstance(pair, IndexPair):
                raise ReferenceError("index_map entries must be IndexPair values")
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_index_map", index_map)

    @property
    def source(self):
        return self._source

    @property
    def index_map(self) -> Tuple[IndexPair, ...]:
        return self._index_map

    def __setattr__(self, name, value):
        raise ReferenceError("ReferenceRecord is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ReferenceRecord):
            return self._source == other._source and self._index_map == other._index_map
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("ReferenceRecord", self._source, self._index_map))

    def __repr__(self) -> str:
        return "ReferenceRecord(source=%r, pairs=%d)" % (self._source, len(self._index_map))


class _ReferenceSetBase:
    __slots__ = ()

    def __setattr__(self, name, value):
        raise ReferenceError("reference-set cases are immutable")


class SearchAllowed(_ReferenceSetBase):
    """The templates field is omitted; template search is allowed (MAP-705)."""

    __slots__ = ()

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __reduce__(self):
        return (SearchAllowed,)


class Explicit(_ReferenceSetBase):
    """The templates field is present; an empty tuple means explicitly none."""

    __slots__ = ("_items",)

    def __init__(self, items: Tuple[ReferenceRecord, ...]) -> None:
        if not isinstance(items, tuple):
            items = tuple(items)
        for item in items:
            if not isinstance(item, ReferenceRecord):
                raise ReferenceError("Explicit requires ReferenceRecord items")
        object.__setattr__(self, "_items", items)

    @property
    def items(self) -> Tuple[ReferenceRecord, ...]:
        return self._items

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Explicit):
            return self._items == other._items
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Explicit", self._items))

    def __repr__(self) -> str:
        return "Explicit(%d templates)" % len(self._items)


ReferenceSet = (SearchAllowed, Explicit)


def fold_reference_set(value, on_search_allowed, on_explicit):
    """The only dispatch over ``ReferenceSet`` (plan §7.3)."""
    if isinstance(value, SearchAllowed):
        return on_search_allowed()
    if isinstance(value, Explicit):
        return on_explicit(value.items)
    raise ReferenceError("fold_reference_set: unknown reference-set value %r" % (value,))
