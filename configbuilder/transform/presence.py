"""Presence algebra application at the wire boundary (plan §10.2).

The model's ``Unset | ExplicitEmpty | Present`` states reach the wire as
distinct structures:

==================  ==================================================
canonical state     wire emission
==================  ==================================================
``Unset``           field omitted from the entity object
``ExplicitEmpty``   field present with the contract's empty value
``Present(value)``  field present with the converted value
==================  ==================================================

``None`` never crosses this module's output: an omitted field is *absent
from the mapping*, not present-with-null. That is the whole point of the
presence algebra (spec §6.2, §6.3).
"""

from __future__ import annotations

import enum

__all__ = ["EmissionRule", "Omitted", "OMITTED"]


class Omitted:
    """Internal marker: the field is absent from the wire object.

    Distinct from ``None`` on purpose — a wire value of ``None`` would be
    emitted as JSON null, which is a *present* field, not an omitted one.
    """

    __slots__ = ()

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "OMITTED"

    def __reduce__(self):
        return (Omitted,)


OMITTED = Omitted()


class EmissionRule(enum.Enum):
    """How a canonical value becomes wire presence (plan §10.2 table)."""

    #: The field is always emitted with its (converted) value.
    ALWAYS = "ALWAYS"
    #: Unset -> omitted; anything else -> emitted with its value.
    OMIT_IF_UNSET = "OMIT_IF_UNSET"
    #: Unset -> omitted; ExplicitEmpty -> the contract's empty value for
    #: the field's type ("" for strings, [] for lists); value -> emitted.
    OMIT_IF_UNSET_ELSE_EMPTY = "OMIT_IF_UNSET_ELSE_EMPTY"
    #: One resource: the inline field or the path field is emitted, the
    #: sibling is omitted. Never both, never neither.
    INLINE_XOR_PATH = "INLINE_XOR_PATH"
