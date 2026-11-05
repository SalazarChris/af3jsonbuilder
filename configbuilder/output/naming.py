"""Deterministic naming (IMPLEMENTATION_PLAN.md §13.2, spec §9.6).

``slug`` is the single pure function every generated name goes through:
lower-cased, restricted to a character set legal on POSIX and Windows,
separator-collapsed, length-capped. Underscores are avoided in generated
component-style names because the contract documents them as problematic
(spec §9.6) — ``-`` is the separator. The derived name is what the
directory, the file, and the job-name field all carry, so the value inside
the file and the path outside it agree (spec §16).

The allowed set is deliberately a **allowlist** (not "anything but
reserved characters"): ``a-z0-9-``. It needs no Windows-reservation logic
(``CON``, ``NUL``, drive letters), no shell-quoting thought, and it makes
case-insensitive collision detection meaningful.

Determinism: no clock, no randomness, no locale. The same text always
yields the same slug.
"""

from __future__ import annotations

import re
from typing import Tuple

__all__ = ["NameError", "MAX_SLUG_LENGTH", "slug", "variant_directory_name", "variant_file_name"]

MAX_SLUG_LENGTH = 64

_ALLOWED = re.compile(r"[^a-z0-9-]+")


class NameError(Exception):
    """Raised when a name input cannot be slugged at all (empty after
    cleaning). Callers pick a fallback; naming never invents content."""


def slug(text: str, max_length: int = MAX_SLUG_LENGTH) -> str:
    """Lower-case, clean, and cap ``text`` into a filesystem-safe slug.

    Steps, in order: lowercase; replace non-alphanumerics with ``-``;
    collapse runs of ``-``; strip leading/trailing ``-``; cap the length on
    a separator boundary. Pure and deterministic.
    """
    if not isinstance(text, str):
        raise NameError("slug input must be a string")
    cleaned = _ALLOWED.sub("-", text.lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if not cleaned:
        raise NameError("cannot derive a filesystem name from %r" % (text,))
    if len(cleaned) > max_length:
        # Keep the head; a trailing separator from the cut is dropped. Two
        # texts truncating to the same slug is a *collision*, resolved by
        # the planner's deterministic numeric suffix (plan §13.2), not by
        # throwing content away here.
        cleaned = cleaned[:max_length].rstrip("-")
        if not cleaned:
            raise NameError("slug of %r collapsed to nothing at length %d" % (text, max_length))
    return cleaned


def variant_directory_name(project_slug: str, variant_key: str) -> str:
    """``<project_slug>__<variant_key>`` (plan §13.1 layout)."""
    return "%s__%s" % (slug(project_slug), slug(variant_key))


def variant_file_name(project_slug: str, variant_key: str) -> str:
    """The input file is named after its directory (plan §13.1)."""
    return variant_directory_name(project_slug, variant_key) + ".json"


def casefold_conflicts(names: Tuple[str, ...]) -> dict:
    """Map each lower-cased name to the names that fold onto it.

    Planning uses this to treat case-differing names as collisions
    everywhere (plan §13.2): the same project must produce the same layout
    on Windows and Linux.
    """
    folded = {}
    for name in names:
        folded.setdefault(name.lower(), []).append(name)
    return {key: tuple(values) for key, values in folded.items() if len(values) > 1}
