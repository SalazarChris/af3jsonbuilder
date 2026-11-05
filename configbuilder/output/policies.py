"""Output policies (IMPLEMENTATION_PLAN.md §13.3, §13.5).

Policies are data, not switches scattered through code: the plan records
which policy was in force, and the manifest repeats it because the policy
changes the meaning of emitted path strings. Defaults are the safe ones —
``Fail`` refuses to destroy files, ``CopyIntoAssets`` is the only policy
whose output survives a machine transfer (plan §4.2 workflow).
"""

from __future__ import annotations

from typing import Tuple

__all__ = [
    "OverwritePolicy",
    "PathPolicy",
    "Action",
    "OVERWRITE_POLICIES",
    "PATH_POLICIES",
    "POLICY_CONFLICT",
    "FORMAT_POLICIES",
]


class _Policy:
    """A closed set of named alternatives, carried as plain frozen strings.

    A tiny value type rather than ``enum.Enum``: policies serialize into
    the manifest and project file as their names, and equality-by-value is
    exactly string equality.
    """

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_name", name)

    def __setattr__(self, name, value):
        raise AttributeError("policies are immutable")

    @property
    def name(self) -> str:
        return self._name

    def __eq__(self, other: object) -> bool:
        if isinstance(other, type(self)):
            return self._name == other._name
        return NotImplemented

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._name))

    def __repr__(self) -> str:
        return "%s.%s" % (type(self).__name__, self._name)


class OverwritePolicy(_Policy):
    """What ``execute`` does when a planned file already exists (§13.3)."""

    __slots__ = ()


class PathPolicy(_Policy):
    """How external resource paths are emitted (§13.5)."""

    __slots__ = ()


OVERWRITE_POLICIES: Tuple[OverwritePolicy, ...] = (
    OverwritePolicy("Fail"),
    OverwritePolicy("Skip"),
    OverwritePolicy("Overwrite"),
    OverwritePolicy("Versioned"),
)
PATH_POLICIES: Tuple[PathPolicy, ...] = (
    PathPolicy("CopyIntoAssets"),
    PathPolicy("RelativeToOutput"),
    PathPolicy("AsGiven"),
)

POLICY_CONFLICT = OverwritePolicy("Fail")  # the default, named for clarity at call sites
FORMAT_POLICIES = (OverwritePolicy, PathPolicy)


def Action(name: str):
    """One of the four planned actions (§13.3): create / overwrite / skip /
    conflict. Carried as a plain string; ``plan`` produces only these four."""
    if name not in ("create", "overwrite", "skip", "conflict"):
        raise ValueError("unknown plan action %r" % (name,))
    return name
