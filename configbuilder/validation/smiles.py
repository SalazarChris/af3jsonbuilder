"""SMILES notation grammar — the notation half of ligand validation.

Two different questions hide behind the phrase "is this SMILES valid?":

* **grammar** — is this text SMILES notation at all? Decidable here, from the
  notation alone: no chemistry, no valence, no perception.
* **chemistry** — does the notation describe a molecule a toolkit will accept?
  Not decidable here, and deliberately left to the external system that owns it
  (plan §9.2, §9.6): AlphaFold 3 parses SMILES with RDKit, which is not a
  dependency of this builder.

This module answers only the first, and answers it **conservatively**: it
refuses what cannot be SMILES, and accepts everything it cannot rule out. A
user must never be blocked from writing a job by a notation this check merely
fails to understand, so there is no valence, aromaticity, or element-vocabulary
reasoning — only mmCIF-style lexical certainty:

* the characters SMILES is written with (nothing else: no spaces, commas, `~`),
  and no bond symbol standing where an atom is needed (``=C``, ``CC=``);
* balanced parentheses and brackets, and no empty bracket;
* ring-closure numbers, each used twice (`1`, ..., `9`, or a two-digit `%nn`),
  and never as the first character;
* unbracketed atoms drawn from the organic subset, so a component code or a
  protein sequence typed into a ligand field is not silently stored as a
  molecule (``ATP``, ``MKTAYIAK``).

Bracketed atom expressions (``[Zn+2]``, ``[13CH4]``, ``[nH]``, ``[$1]``) are
accepted as written: their contents are chemistry, not grammar. ``H`` and ``h``
outside brackets are tolerated although technically not in the organic subset,
again erring on the side of accepting input.

``parses`` is the predicate; ``notation_problem`` names the defect, which is
what the user is told.
"""

from __future__ import annotations

from typing import Optional

__all__ = ["notation_problem", "parses"]

# The characters a SMILES string is written with, plus the ones this check
# tolerates because rejecting them would risk refusing valid input.
_PUNCTUATION = set("()[]=#-+@/\\*:%.")

# The unbracketed atoms: the organic subset of the SMILES specification (both
# cases: uppercase aliphatic, lowercase aromatic), plus the tolerated H/h.
_ORGANIC_SUBSET = frozenset(
    ("B", "C", "N", "O", "P", "S", "F", "Cl", "Br", "I")
    + ("b", "c", "n", "o", "p", "s")
    + ("H", "h", "*")
)

_RING_DIGITS = "0123456789"

# Bond symbols: a bond joins two atoms, so it can never be the first or last
# character of the notation.
_BOND_SYMBOLS = set("-=#:/\\")


def notation_problem(text: str) -> Optional[str]:
    """Why ``text`` is not SMILES notation, or ``None`` when it may be.

    ``None`` means "this check has no complaint" — never "this is a molecule".
    """
    if not isinstance(text, str) or not text.strip():
        return "it is empty"
    if text != text.strip():
        return "it has leading or trailing whitespace"
    if text[0] in _RING_DIGITS or text[0] == "%":
        return "it starts with a ring-closure number, which needs an atom first"
    if text[0] in _BOND_SYMBOLS:
        return "it starts with a bond symbol, which needs an atom first"
    if text[-1] in _BOND_SYMBOLS:
        return "it ends with a bond symbol, with no atom for it to bond to"
    problem = _character_problem(text)
    if problem is not None:
        return problem
    problem = _balance_problem(text)
    if problem is not None:
        return problem
    problem = _ring_closure_problem(text)
    if problem is not None:
        return problem
    return _atom_problem(text)


def parses(text: str) -> bool:
    """Whether ``text`` is notation this check has no complaint about."""
    return notation_problem(text) is None


def _character_problem(text: str) -> Optional[str]:
    for character in text:
        if character.isascii() and (character.isalnum() or character in _PUNCTUATION):
            continue
        return "it contains %r, which is not a SMILES character" % character
    return None


def _balance_problem(text: str) -> Optional[str]:
    """Parentheses and brackets: balanced, never nested the wrong way."""
    depth = 0
    brackets = 0
    empty_bracket = False
    for character in text:
        if character == "[":
            if brackets:
                return "a bracket is opened inside another bracket"
            brackets = 1
            empty_bracket = True
            continue
        if character == "]":
            if not brackets:
                return "a bracket is closed without being opened"
            if empty_bracket:
                return "a bracket contains no atom"
            brackets = 0
            continue
        if brackets:
            empty_bracket = False
            continue  # inside [ ] the contents are chemistry, not grammar
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return "a parenthesis is closed without being opened"
    if brackets:
        return "a bracket is never closed"
    if depth:
        return "a parenthesis is never closed"
    return None


def _ring_closure_problem(text: str) -> Optional[str]:
    """Every ring-closure number opens exactly one ring, so it appears twice.

    Digits inside brackets are isotopes or charges (``[13CH4]``, ``[Fe+2]``)
    and are not ring closures; ``%`` introduces a two-digit closure number.
    """
    counts = {}
    index = 0
    brackets = 0
    length = len(text)
    while index < length:
        character = text[index]
        index += 1
        if character == "[":
            brackets = 1
            continue
        if character == "]":
            brackets = 0
            continue
        if brackets:
            continue
        if character == "%":
            if index + 2 > length or not all(
                text[index + offset] in _RING_DIGITS for offset in (0, 1)
            ):
                return "'%' must be followed by exactly two digits"
            number = text[index : index + 2]
            index += 2
            counts[number] = counts.get(number, 0) + 1
            continue
        if character in _RING_DIGITS:
            counts[character] = counts.get(character, 0) + 1
    for number in sorted(counts):
        if counts[number] % 2:
            return "ring-closure number %s is opened but never closed" % number
    return None


def _atom_problem(text: str) -> Optional[str]:
    """Unbracketed atoms must come from the organic subset.

    A run of letters outside brackets is one atom symbol (``C``, ``Cl``) or
    several (``CC``, ``c1ccccc1``); every symbol taken from it has to be one
    SMILES writes without brackets, which is what makes ``ATP`` and ``ZN``
    refusals rather than component codes stored as notation.
    """
    run = ""
    brackets = 0
    for character in text:
        if character == "[":
            brackets = 1
            problem = _letters_problem(run)
            run = ""
            if problem is not None:
                return problem
            continue
        if character == "]":
            brackets = 0
            continue
        if brackets:
            continue
        if character.isalpha() and character.isascii():
            run += character
            continue
        problem = _letters_problem(run)
        run = ""
        if problem is not None:
            return problem
    return _letters_problem(run)


def _letters_problem(run: str) -> Optional[str]:
    """Read a run of letters as the atom symbols it must be made of."""
    index = 0
    while index < len(run):
        pair = run[index : index + 2]
        if len(pair) == 2 and pair in _ORGANIC_SUBSET:
            index += 2
            continue
        single = run[index]
        if single in _ORGANIC_SUBSET:
            index += 1
            continue
        return (
            "the atom %r in %r is not one SMILES writes without brackets"
            % (single, run)
        )
    return None
