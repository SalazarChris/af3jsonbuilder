"""Alignment sum types (IMPLEMENTATION_PLAN.md §7.3).

``AlignmentPairing`` is the architectural answer to the contract's
"both set or both unset" rule (AUTHORITATIVE_SPEC.md §11, MAP-601..606):
the illegal half-set combination cannot be instantiated. ``SingleAlignment``
is the RNA form (MAP-601/604/606); DNA has no alignment representation at
all (DOMAIN_MAPPING §6 note) and its record type carries no field for one.
"""

from __future__ import annotations

from configbuilder.model.errors import ModelError
from configbuilder.model.values import External, Inline

__all__ = [
    "AlignmentBoth",
    "AlignmentError",
    "AlignmentFree",
    "AlignmentAutomatic",
    "AlignmentPairing",
    "AlignmentUnpairedOnly",
    "AlignmentPairedOnly",
    "SingleAlignment",
    "SingleAutomatic",
    "SingleFree",
    "SingleProvided",
    "fold_alignment",
    "fold_single_alignment",
]

_UNSET_SENTINEL = "unset"


class AlignmentError(ModelError):
    """Raised for invalid alignment construction or unknown fold cases."""


class _AlignmentBase:
    __slots__ = ()

    def __setattr__(self, name, value):
        raise AlignmentError("alignment cases are immutable")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and type(self) is type(other)

    def __hash__(self) -> int:
        return hash(type(self).__name__)


class AlignmentAutomatic(_AlignmentBase):
    """Neither MSA field is emitted; the pipeline searches automatically
    (MAP-601)."""


class AlignmentFree(_AlignmentBase):
    """Both fields emitted empty: fully MSA-free (MAP-604)."""


class _OneSided(_AlignmentBase):
    """Base for one-populated-one-empty cases; holds exactly one source."""

    __slots__ = ("_source",)

    def __init__(self, source) -> None:
        if not isinstance(source, (Inline, External)):
            raise AlignmentError(
                "%s requires an Inline or External source" % type(self).__name__
            )
        object.__setattr__(self, "_source", source)

    @property
    def source(self):
        return self._source

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return self._source == other._source
        return NotImplemented

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._source))


class AlignmentUnpairedOnly(_OneSided):
    """Unpaired populated, paired emitted empty (MAP-602)."""


class AlignmentPairedOnly(_OneSided):
    """Paired populated, unpaired emitted empty (MAP-603; contract marks
    this an expert case)."""


class AlignmentBoth(_AlignmentBase):
    """Both sides non-empty (MAP-605), each with its own source.

    ``source`` is the unpaired side and ``paired_source`` the paired side.
    A single-source construction keeps the historical behaviour: the same
    resource feeds both sides. Supplying ``paired_source`` lets a paired
    A3M and an unpaired A3M name different files (or different inline text)
    instead of silently treating the two as interchangeable.
    """

    __slots__ = ("_source", "_paired_source")

    def __init__(self, source, paired_source=None) -> None:
        paired = source if paired_source is None else paired_source
        for label, value in (("unpaired", source), ("paired", paired)):
            if not isinstance(value, (Inline, External)):
                raise AlignmentError(
                    "AlignmentBoth requires an Inline or External %s source" % label
                )
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_paired_source", paired)

    @property
    def source(self):
        """The unpaired side (historical name for the first source)."""
        return self._source

    @property
    def unpaired_source(self):
        return self._source

    @property
    def paired_source(self):
        return self._paired_source

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return (
                self._source == other._source
                and self._paired_source == other._paired_source
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._source, self._paired_source))

    def __repr__(self) -> str:
        return "AlignmentBoth(unpaired=%r, paired=%r)" % (
            self._source,
            self._paired_source,
        )


AlignmentPairing = (
    AlignmentAutomatic,
    AlignmentFree,
    AlignmentUnpairedOnly,
    AlignmentPairedOnly,
    AlignmentBoth,
)


def fold_alignment(value, on_automatic, on_free, on_unpaired_only, on_paired_only, on_both):
    """The only dispatch over ``AlignmentPairing`` (plan §7.3)."""
    if isinstance(value, AlignmentAutomatic):
        return on_automatic()
    if isinstance(value, AlignmentFree):
        return on_free()
    if isinstance(value, AlignmentUnpairedOnly):
        return on_unpaired_only(value.source)
    if isinstance(value, AlignmentPairedOnly):
        return on_paired_only(value.source)
    if isinstance(value, AlignmentBoth):
        return on_both(value.source)
    raise AlignmentError("fold_alignment: unknown alignment value %r" % (value,))


class SingleAutomatic(_AlignmentBase):
    """RNA MSA unset: automatic search (MAP-601)."""


class SingleFree(_AlignmentBase):
    """RNA MSA emitted empty: MSA-free (MAP-604)."""


class SingleProvided(_OneSided):
    """RNA custom MSA: inline or file-backed (MAP-606)."""


SingleAlignment = (SingleAutomatic, SingleFree, SingleProvided)


def fold_single_alignment(value, on_automatic, on_free, on_provided):
    """The only dispatch over ``SingleAlignment`` (plan §7.3)."""
    if isinstance(value, SingleAutomatic):
        return on_automatic()
    if isinstance(value, SingleFree):
        return on_free()
    if isinstance(value, SingleProvided):
        return on_provided(value.source)
    raise AlignmentError("fold_single_alignment: unknown alignment value %r" % (value,))
