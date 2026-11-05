"""The presence algebra (IMPLEMENTATION_PLAN.md §7.3).

The external contract distinguishes four states for several optional
fields (AUTHORITATIVE_SPEC.md §6.2, §6.3; MAP-601..606): omitted, present
with the contract's empty value, present with content, and (for fields the
contract does not admit at all) absent from the model itself. ``Unset`` and
``ExplicitEmpty`` are never interchangeable — not here, not in the
transformer, not in the serializer, not in persistence (plan §2 rule 6).

``None`` is never used to mean either of them: ``Optional`` is banned for
contract-bearing model fields, enforced by an architecture test (plan §7.3).
"""

from __future__ import annotations

from configbuilder.model.errors import ModelError

__all__ = ["ExplicitEmpty", "Presence", "Present", "Unset", "fold_presence"]


class PresenceError(ModelError):
    """Raised for invalid presence construction or unknown fold cases."""


class Unset:
    """The field is omitted from the wire document entirely."""

    __slots__ = ()

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "Unset"

    def __reduce__(self):
        return (Unset,)


class ExplicitEmpty:
    """The field is present with the contract's empty value (e.g. ``""``)."""

    __slots__ = ()

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ExplicitEmpty"

    def __reduce__(self):
        return (ExplicitEmpty,)


class Present:
    """The field is present with content."""

    __slots__ = ("value",)

    def __init__(self, value) -> None:
        if isinstance(value, (Unset, ExplicitEmpty, Present)):
            raise PresenceError("Presence cannot nest: got %r" % (value,))
        object.__setattr__(self, "value", value)

    def __setattr__(self, name, value):  # frozen in practice
        raise PresenceError("Present is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Present):
            return self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Present", self.value))

    def __repr__(self) -> str:
        return "Present(%r)" % (self.value,)


Presence = ("Unset", "ExplicitEmpty", "Present")


def is_presence(value) -> bool:
    return isinstance(value, (Unset, ExplicitEmpty, Present))


def fold_presence(value, on_unset, on_empty, on_present):
    """The only dispatch over ``Presence`` (plan §7.3).

    Every consumer — validation, transform, variants, persistence — calls
    this fold instead of testing types itself. Adding a case breaks every
    call site loudly; an unrecognised value raises here rather than falling
    through a silent default, which would be exactly the omitted-vs-empty
    collapse the contract forbids (spec §6.3).
    """
    if isinstance(value, Unset):
        return on_unset()
    if isinstance(value, ExplicitEmpty):
        return on_empty()
    if isinstance(value, Present):
        return on_present(value.value)
    raise PresenceError("fold_presence: unknown presence value %r" % (value,))
