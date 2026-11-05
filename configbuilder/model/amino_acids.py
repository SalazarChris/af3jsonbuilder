"""Amino-acid stereochemical forms: the L/D CCD registry (MAP-009, MAP-204).

A D-amino acid is not an ordinary post-translational modification: it is a
*residue replacement*, expressed in AF3 through the same protein
``modifications`` entry (``ptmType`` + ``ptmPosition``) with the D-form's own
CCD component id. This module is the single home of those ids, so no front end
and no service hard-codes a mapping.

Every D-form below is a standard CCD component with type ``D-peptide linking``
(verified against the Chemical Component Dictionary). The one-letter codes are
the canonical residues those components replace. Glycine is achiral and
therefore has no D-form: it is deliberately absent from ``D_AMINO_ACIDS``.
"""

from __future__ import annotations

__all__ = [
    "AMINO_ACID_NAMES",
    "D_AMINO_ACIDS",
    "D_AMINO_ACID_NAMES",
    "L_AMINO_ACIDS",
    "d_code_for",
    "d_name_for_code",
    "has_d_form",
    "is_d_code",
    "residue_for_d_code",
]

#: The standard L-form component for every canonical one-letter code (the
#: existing behaviour, unchanged). Glycine's L-form is ``GLY``.
L_AMINO_ACIDS = {
    "A": "ALA",
    "R": "ARG",
    "N": "ASN",
    "D": "ASP",
    "C": "CYS",
    "Q": "GLN",
    "E": "GLU",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "L": "LEU",
    "K": "LYS",
    "M": "MET",
    "F": "PHE",
    "P": "PRO",
    "S": "SER",
    "T": "THR",
    "W": "TRP",
    "Y": "TYR",
    "V": "VAL",
}

#: One-letter code -> the CCD component id of its D-form. Glycine is absent
#: because it is achiral; every other canonical amino acid is present.
D_AMINO_ACIDS = {
    "A": "DAL",
    "R": "DAR",
    "N": "DSG",
    "D": "DAS",
    "C": "DCY",
    "Q": "DGN",
    "E": "DGL",
    "H": "DHI",
    "I": "DIL",
    "L": "DLE",
    "K": "DLY",
    "M": "MED",
    "F": "DPN",
    "P": "DPR",
    "S": "DSN",
    "T": "DTH",
    "W": "DTR",
    "Y": "DTY",
    "V": "DVA",
}

#: One-letter code -> the amino acid's ordinary name, for display.
AMINO_ACID_NAMES = {
    "A": "Alanine",
    "R": "Arginine",
    "N": "Asparagine",
    "D": "Aspartic acid",
    "C": "Cysteine",
    "Q": "Glutamine",
    "E": "Glutamic acid",
    "G": "Glycine",
    "H": "Histidine",
    "I": "Isoleucine",
    "L": "Leucine",
    "K": "Lysine",
    "M": "Methionine",
    "F": "Phenylalanine",
    "P": "Proline",
    "S": "Serine",
    "T": "Threonine",
    "W": "Tryptophan",
    "Y": "Tyrosine",
    "V": "Valine",
}

#: CCD component id -> ``"D-<name>"``, for display and for recognising a code.
D_AMINO_ACID_NAMES = {
    code: "D-%s" % AMINO_ACID_NAMES[residue] for residue, code in D_AMINO_ACIDS.items()
}

#: The inverse mapping, built once so a code can always find its residue.
_D_CODE_TO_RESIDUE = {code: residue for residue, code in D_AMINO_ACIDS.items()}


def has_d_form(residue: str) -> bool:
    """True when the canonical residue has a D-form (glycine never does)."""
    return residue in D_AMINO_ACIDS


def d_code_for(residue: str):
    """The D-form CCD id for a canonical residue, or ``None``."""
    return D_AMINO_ACIDS.get(residue)


def is_d_code(code: str) -> bool:
    """True when ``code`` is one of the known D-form CCD ids."""
    return code in _D_CODE_TO_RESIDUE


def residue_for_d_code(code: str):
    """The canonical one-letter residue a D-form code replaces, or ``None``."""
    return _D_CODE_TO_RESIDUE.get(code)


def d_name_for_code(code: str):
    """``"D-Arginine"`` for ``DAR``, or ``None`` when the code is not a D-form."""
    return D_AMINO_ACID_NAMES.get(code)
