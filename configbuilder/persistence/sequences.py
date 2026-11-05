"""Sequence-list and SMILES file reading — batch-variant input adapters.

Filesystem access is confined to ``output`` and ``persistence`` (plan
§5.3 rule 8), so the batch-variant feature reads its input files here
and ``app`` stays IO-free.

Supported formats:

**Sequence files (.txt):**
  One biological sequence per line (protein, DNA, RNA):
  - blank (or whitespace-only) lines are ignored;
  - surrounding whitespace on a line is stripped;
  - Windows and Unix line endings both work (text mode + ``splitlines``);
  - a UTF-8 byte-order mark is accepted and dropped, so a file saved with
    an editor that writes one reads the same as any other;
  - comments are deliberately **not** part of the format: a ``#`` line is
    simply a line that will fail sequence validation, reported with its
    line number like any other invalid entry.

**SMILES files (.smiles or .txt):**
  One ligand per line, with optional name:
  - Format 1 (name + SMILES): ``<name> <SMILES>`` (name and SMILES separated by whitespace)
  - Format 2 (SMILES only): ``<SMILES>`` (no name, auto-generated)
  - blank lines are ignored;
  - lines starting with ``#`` are treated as comments and ignored;
  - surrounding whitespace is stripped.

**CCD code files (.txt):**
  One ligand per line, given as component code(s):
  - a line's tokens (whitespace, commas or semicolons) are the components of
    **one** ligand, the contract's multi-component form
    (``NAG NAG BMA MAN MAN``);
  - blank lines and ``#`` comment lines are ignored;
  - surrounding whitespace is stripped, interior separators are not touched.

Reading never interprets a sequence, SMILES or component code — validation
belongs to the model, applied by the caller (``VariantService``). This module
only turns file bytes into numbered, cleaned entries.
"""

from __future__ import annotations

import os
from typing import Tuple

from configbuilder.persistence.store import PersistenceError

__all__ = [
    "parse_code_text",
    "parse_sequence_text",
    "parse_smiles_text",
    "read_code_file",
    "read_sequence_file",
    "read_smiles_file",
]


def _numbered_lines(payload: str, skip_comments: bool) -> Tuple[Tuple[int, str], ...]:
    """``(1-based line number, stripped text)`` for every usable line.

    One loop for the three list formats this module reads, so their line
    handling (blank lines, Windows/Unix endings, surrounding whitespace)
    cannot drift apart. Only the ``#`` comment rule differs, and it is the
    caller's: a sequence list has no comment syntax.
    """
    numbered = []
    for number, line in enumerate(payload.splitlines(), start=1):
        text = line.strip()
        if not text or (skip_comments and text.startswith("#")):
            continue
        numbered.append((number, text))
    return tuple(numbered)


def parse_sequence_text(payload: str) -> Tuple[Tuple[int, str], ...]:
    """The usable lines of file text as ``(line_number, text)`` pairs.

    Line numbers are 1-based file lines, preserved so the caller can
    report an invalid entry at its exact position. Blank lines never
    reach the result; a ``#`` line is **not** a comment here — comments are
    deliberately not part of the sequence format, so it is reported as an
    invalid entry with its line number like any other.
    """
    return _numbered_lines(payload, skip_comments=False)


def parse_code_text(payload: str) -> Tuple[Tuple[int, str], ...]:
    """The usable lines of a CCD code file as ``(line_number, text)`` pairs.

    A line keeps its interior separators: ``NAG NAG BMA MAN MAN`` is one
    ligand made of five components, and only the model's tokenizer decides
    where a component boundary is. ``#`` lines are comments here (a code file
    is a hand-written list, like a SMILES file), and blank lines are skipped.
    """
    return _numbered_lines(payload, skip_comments=True)


def read_code_file(path: str) -> Tuple[Tuple[int, str], ...]:
    """Read a CCD code list, or raise ``PersistenceError``.

    The failure vocabulary matches the other readers: a missing, unreadable or
    non-UTF-8 file is a ``PersistenceError`` naming the cause, and a directory
    says so instead of reporting a permissions problem the user does not have.
    """
    if os.path.isdir(path):
        raise PersistenceError("that path is a directory, not a CCD code file")
    try:
        # ``utf-8-sig`` reads plain UTF-8 unchanged and drops a leading
        # byte-order mark, which is what an editor on Windows may save.
        with open(path, "r", encoding="utf-8-sig") as handle:
            payload = handle.read()
    except OSError as error:
        raise PersistenceError("CCD code file cannot be read: %s" % error) from error
    except UnicodeDecodeError as error:
        raise PersistenceError("CCD code file is not UTF-8 text: %s" % error) from error
    return parse_code_text(payload)


def read_sequence_file(path: str) -> Tuple[Tuple[int, str], ...]:
    """Read a sequence-list file, or raise ``PersistenceError``.

    The failure vocabulary matches project files: a missing, unreadable,
    or non-UTF-8 file is a ``PersistenceError`` naming the cause — never
    a raw ``OSError`` leaking into the application layer.
    """
    if os.path.isdir(path):
        # A folder is an ordinary slip at the file picker — its listing
        # shows directories too. Windows reports reading one as
        # ``Permission denied``, which points the user at a permissions
        # problem they do not have.
        raise PersistenceError("that path is a directory, not a sequence file")
    try:
        # ``utf-8-sig`` reads plain UTF-8 unchanged and drops a leading
        # byte-order mark, which is what an editor on Windows may save.
        with open(path, "r", encoding="utf-8-sig") as handle:
            payload = handle.read()
    except OSError as error:
        raise PersistenceError("sequence file cannot be read: %s" % error) from error
    except UnicodeDecodeError as error:
        raise PersistenceError("sequence file is not UTF-8 text: %s" % error) from error
    return parse_sequence_text(payload)


def parse_smiles_text(payload: str) -> Tuple[Tuple[int, str, str], ...]:
    """The usable lines of a SMILES file as ``(line_number, name, smiles)`` tuples.

    Line numbers are 1-based file lines, preserved so the caller can
    report an invalid entry at its exact position.
    
    Format:
    - ``<name> <SMILES>`` → (line, name, smiles)
    - ``<SMILES>`` → (line, "ligand_N", smiles) where N is the 1-based index
    - blank lines and ``#`` comment lines are skipped
    """
    numbered = []
    ligand_index = 0
    for number, line in enumerate(payload.splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        parts = text.split(None, 1)  # Split on whitespace, max 1 split
        if len(parts) == 2:
            name, smiles = parts
            numbered.append((number, name, smiles))
        elif len(parts) == 1:
            ligand_index += 1
            numbered.append((number, "ligand_%d" % ligand_index, parts[0]))
        else:
            # Shouldn't happen, but handle gracefully
            numbered.append((number, "ligand_%d" % (ligand_index + 1), text))
    return tuple(numbered)


def read_smiles_file(path: str) -> Tuple[Tuple[int, str, str], ...]:
    """Read a SMILES file, or raise ``PersistenceError``.

    Returns ``(line_number, name, smiles)`` tuples.
    """
    if os.path.isdir(path):
        raise PersistenceError("that path is a directory, not a SMILES file")
    try:
        # ``utf-8-sig`` reads plain UTF-8 unchanged and drops a leading
        # byte-order mark, which is what an editor on Windows may save.
        with open(path, "r", encoding="utf-8-sig") as handle:
            payload = handle.read()
    except OSError as error:
        raise PersistenceError("SMILES file cannot be read: %s" % error) from error
    except UnicodeDecodeError as error:
        raise PersistenceError("SMILES file is not UTF-8 text: %s" % error) from error
    return parse_smiles_text(payload)
