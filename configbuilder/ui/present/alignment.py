"""Alignment/MSA wording, shared by both front ends.

The model's alignment cases are the same ones the console menu and the
desktop's entity table show. Naming them once here keeps a menu label and a
table cell from disagreeing, and gives the console a way to say *which* MSA
setting an entity currently carries instead of a vague "keep the current one".
"""

from __future__ import annotations

from configbuilder.model import (
    AlignmentAutomatic,
    AlignmentBoth,
    AlignmentFree,
    AlignmentPairedOnly,
    AlignmentUnpairedOnly,
    SingleAutomatic,
    SingleFree,
    SingleProvided,
)
from configbuilder.ui.present.strings import text as _text

__all__ = ["alignment_label", "alignment_label_key"]

#: Alignment case -> the registry wording for it.
_LABEL_KEYS = {
    AlignmentAutomatic: "menu.msa_mode_auto",
    AlignmentFree: "menu.msa_mode_free",
    AlignmentUnpairedOnly: "menu.msa_mode_unpaired",
    AlignmentPairedOnly: "menu.msa_mode_paired",
    AlignmentBoth: "menu.msa_mode_both",
    SingleAutomatic: "menu.msa_mode_auto",
    SingleFree: "menu.msa_mode_free",
    SingleProvided: "menu.msa_mode_provided",
}


def alignment_label_key(alignment):
    """The registry key for one alignment case, or ``None`` when unrecognised."""
    return _LABEL_KEYS.get(type(alignment))


def alignment_label(alignment) -> str:
    """The registry's wording for ``alignment``, or ``""`` when it has none."""
    key = alignment_label_key(alignment)
    return _text(key) if key is not None else ""
