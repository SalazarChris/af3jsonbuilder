"""Structural-reference input rules (application layer).

This module is the one owner of what a usable template definition is:
an external source must be a readable, structurally valid mmCIF file, and
every template must carry at least one parseable, non-negative
``query:template`` pair whose query index addresses the target protein. The
console and the GUI both collect text, but the rules and their wording live
here so ``ConfigurationService.set_references`` enforces them for every
caller.

The file's *content* is judged by ``persistence.mmcif`` (an established
mmCIF parser when one is installed, the bundled lexical scan otherwise): a
file that is not a structure is refused here, before it is attached.

The mapping is the user's own, and is checked in the three ways that are
knowable without grading biology:

- both arrays are present, parallel, and hold non-negative whole numbers;
- every query index addresses a residue of the target protein sequence;
- every template index addresses a residue of the template's **full polymer
  sequence**, the one that counts residues without atom coordinates, and no
  query residue is mapped twice (AF3 builds its mapping with
  ``dict(zip(queryIndices, templateIndices))``, so a duplicate query index
  silently loses a pair there — it is refused here instead).

The last check needs the parser's residue list, so it runs when gemmi is
installed and is reported as unavailable otherwise rather than guessed at from
atom coordinates (``mmcif.index_check_available``). Amino-acid identity is
never compared: a homology template legitimately substitutes residues.
"""

from __future__ import annotations

import os

from configbuilder.model import IndexPair
from configbuilder.persistence.mmcif import (
    index_check_available,
    mapping_problem,
    template_mapping_problem,
    template_structure_problem,
)

__all__ = [
    "ReferenceIssue",
    "file_issue",
    "index_check_available",
    "parse_pair_text",
    "validate_reference",
]

# The wording is the console's existing actionable wording; moving it here
# keeps the refusal identical through the service API and the console.
_FILE_INVALID = (
    "The template file %r cannot be used: %s. "
    "Enter another path or 0 to cancel."
)
_PAIRS_REQUIRED = (
    "At least one query:template pair is required, e.g. 0:5,1:6. "
    "Enter pairs or 0 to cancel."
)
_PAIRS_INVALID = (
    "The index pairs %r cannot be used: %s. "
    "Enter them again or 0 to cancel."
)
_PAIR_SHAPE = "%r is not query:template with non-negative whole numbers"
_PAIR_RANGE = (
    "query index %d is outside the target sequence (length %d; valid 0-%d)"
)
_DUPLICATE_QUERY = (
    "query index %d is mapped more than once; AF3 keeps only one mapping per "
    "query residue, so the duplicate pair would be dropped"
)


class ReferenceIssue:
    """One unusable input, with the field that must be asked for again."""

    __slots__ = ("field", "message")

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message

    def __repr__(self) -> str:
        return "ReferenceIssue(%r, %r)" % (self.field, self.message)


def _file_problem(path: str):
    """Why ``path`` is not a usable template CIF, or ``None`` when it is.

    Existence, file-ness and extension are the naming rules owned here; the
    content — readable, non-empty, UTF-8, and a structure a parser can read —
    is the persistence reader's answer, so this module never opens the file.
    ``the file cannot be read`` therefore still reaches the user exactly as it
    did before, now from the reader.
    """
    if not os.path.exists(path):
        return "the file does not exist"
    if not os.path.isfile(path):
        return "the path is not a regular file"
    if os.path.splitext(path)[1].lower() not in (".cif", ".mmcif"):
        return "the file must end in .cif or .mmcif"
    return template_structure_problem(path)


def file_issue(path: str):
    """A file-field issue for ``path``, or ``None`` when the file is usable."""
    problem = _file_problem(path)
    if problem is None:
        return None
    return ReferenceIssue("file", _FILE_INVALID % (path, problem))


def _pair_label(pair) -> str:
    if isinstance(pair, IndexPair):
        return "%d:%d" % (pair.query, pair.template)
    if isinstance(pair, (tuple, list)) and len(pair) == 2:
        return "%s:%s" % (pair[0], pair[1])
    return str(pair)


def _pairs_label(pairs) -> str:
    return ",".join(_pair_label(pair) for pair in pairs)


def _pairs_invalid(display, reason: str) -> ReferenceIssue:
    return ReferenceIssue("pairs", _PAIRS_INVALID % (display, reason))


def _parse_index(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def _range_issue(query: int, sequence_length: int) -> str:
    return _PAIR_RANGE % (query, sequence_length, sequence_length - 1)


def parse_pair_text(raw: str, sequence_length: int):
    """Parse comma-separated ``query:template`` text.

    Returns ``(IndexPair tuple, None)`` or ``(None, ReferenceIssue)``.
    """
    if not raw.strip():
        return None, ReferenceIssue("pairs", _PAIRS_REQUIRED)
    pairs = []
    for token in raw.split(","):
        token = token.strip()
        left, separator, right = token.partition(":")
        if not separator:
            return None, _pairs_invalid(raw, _PAIR_SHAPE % token)
        if not left.isdigit():
            return None, _pairs_invalid(raw, _PAIR_SHAPE % left)
        if not right.isdigit():
            return None, _pairs_invalid(raw, _PAIR_SHAPE % right)
        query = int(left)
        template = int(right)
        if query >= sequence_length:
            return None, _pairs_invalid(
                raw, _range_issue(query, sequence_length)
            )
        pairs.append(IndexPair(query, template))
    return tuple(pairs), None


def _validate_pairs(pairs, sequence_length: int):
    pairs = tuple(pairs)
    if not pairs:
        return None, ReferenceIssue("pairs", _PAIRS_REQUIRED)
    display = _pairs_label(pairs)
    validated = []
    for pair in pairs:
        if isinstance(pair, IndexPair):
            validated.append(pair)
            continue
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            return None, _pairs_invalid(
                display, _PAIR_SHAPE % _pair_label(pair)
            )
        query = _parse_index(pair[0])
        if query is None:
            return None, _pairs_invalid(display, _PAIR_SHAPE % pair[0])
        template = _parse_index(pair[1])
        if template is None:
            return None, _pairs_invalid(display, _PAIR_SHAPE % pair[1])
        if query >= sequence_length:
            return None, _pairs_invalid(
                display, _range_issue(query, sequence_length)
            )
        validated.append(IndexPair(query, template))
    return tuple(validated), None


def _mapping_issue(pairs, sequence_length: int, path, inline):
    """The mapping's own problems: duplicates, then bounds against the file.

    A duplicate query index is refused for every source, because AF3's
    ``dict(zip(...))`` would drop one of the pairs without saying so. Bounds
    are left to :mod:`configbuilder.persistence.mmcif`, which answers only when
    it can actually read the template's residues.
    """
    display = _pairs_label(pairs)
    seen = set()
    for pair in pairs:
        if pair.query in seen:
            return _pairs_invalid(display, _DUPLICATE_QUERY % pair.query)
        seen.add(pair.query)
    problem = None
    if path:
        problem = template_mapping_problem(path, pairs, sequence_length)
    elif inline:
        problem = mapping_problem(inline, pairs, sequence_length)
    if problem is not None:
        return _pairs_invalid(display, problem)
    return None


def validate_reference(entry, sequence_length: int):
    """Validate one front-end reference input.

    Returns ``(IndexPair tuple, None)`` or ``(None, ReferenceIssue)``.
    ``entry`` is an app ``ReferenceInput``; its ``pairs`` may be a tuple of
    ``(query, template)`` values or raw comma-separated pair text, and its
    structure travels either as ``external_path`` or as ``inline_text``.
    """
    path = getattr(entry, "external_path", None)
    if path:
        issue = file_issue(path)
        if issue is not None:
            return None, issue
    pairs = getattr(entry, "pairs", ())
    if isinstance(pairs, str):
        pairs, issue = parse_pair_text(pairs, sequence_length)
    else:
        pairs, issue = _validate_pairs(pairs, sequence_length)
    if issue is not None:
        return None, issue
    issue = _mapping_issue(
        pairs, sequence_length, path, getattr(entry, "inline_text", None)
    )
    if issue is not None:
        return None, issue
    return pairs, None
