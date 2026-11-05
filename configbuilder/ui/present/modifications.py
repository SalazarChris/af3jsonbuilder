"""Modification display text, shared by both front ends.

A D-amino acid enters the model exactly like any other modification (a CCD
code plus a 1-based position), so nothing in the data distinguishes it from a
PTM. The *display* must: the user has to see that the row is a residue form,
not an added group. The registry that knows the D-form names lives in
``model``; this module only turns a code into the matching row text, once, so
the desktop table and the console list cannot drift apart.
"""

from __future__ import annotations

from configbuilder.model import D_AMINO_ACIDS, d_name_for_code

__all__ = ["d_amino_acid_options", "modification_code_text"]


def modification_code_text(code: str) -> str:
    """A modification code as the list shows it.

    Ordinary PTMs are unchanged (``"SEP"``); a D-form gains its name so the
    residue replacement is recognisable — ``"DAR (D-Arginine)"``.
    """
    name = d_name_for_code(code)
    if name is None:
        return code
    return "%s (%s)" % (code, name)


def d_amino_acid_options():
    """The supported ``(residue, code, name)`` D-form rows, ordered by residue.

    Read from the model's registry — this module never owns a mapping of its
    own — so a console list and the desktop's resolver cannot disagree about
    which residue resolves to which CCD code.
    """
    return tuple(
        (residue, code, d_name_for_code(code))
        for residue, code in sorted(D_AMINO_ACIDS.items())
    )
