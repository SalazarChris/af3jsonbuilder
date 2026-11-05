"""Template mmCIF structure reading — the file half of a template definition.

A protein template is one external mmCIF file plus the user's own 0-based
``query:template`` index pairs. The pairs are validated in
``configbuilder/app/reference_validation.py``; this module answers the other
question a template raises, at the moment its file is chosen: *is this file a
structure at all?* A file that cannot be read as mmCIF is refused there, so a
broken template is never attached to a record and never serialised.

Two checks, strongest first, because the builder runs on the standard library
alone (plan §4) and an optional component may strengthen a check but is never
required for one (§9.6):

1. **gemmi**, the established mmCIF library, when it is importable
   (``pyproject.toml``'s ``templates`` extra installs it). A file it cannot
   parse is not a structure. Its absence is not a failure: the check below
   still runs, so the guarantee does not depend on it.
2. **The bundled lexical scan**, always. mmCIF's own lexical grammar: a
   ``data_`` block, quoted values and ``;`` text fields, a value for every
   data item, and every ``loop_`` row holding exactly as many values as the
   loop declares tags — the defect that makes a truncated file unusable. It
   also requires at least one structural category, so a text file that merely
   contains a ``data_`` line is not mistaken for a structure.

The two tiers are deliberately in agreement on those defects: the bundled
scan applies the same rules the parser names, so whether gemmi happens to be
installed does not change the verdict on a committed fixture. Installing it
can only add strictness for input neither tier has seen.

Neither check makes a mapping biologically correct: the mapping is the user's,
and amino-acid identity is never graded here (a homology template legitimately
carries substitutions). What the checks establish is that AF3 has a structure
to read, and — when the parser is installed — that every ``templateIndices``
value addresses a residue of the template's **full polymer sequence**, the one
that includes residues without atom coordinates (AF3: "unresolved mmCIF
residues must be taken into account when specifying template indices").

That last check needs a real mmCIF reader, so it is available only when gemmi
is installed: the lexical scan can confirm a file is a structure but cannot
enumerate a polymer's residues. ``index_check_available()`` says which level of
checking this environment provides, and the UI repeats it where the indices are
entered, so neither front end claims more than was checked.

Reading belongs to this layer (plan §5.3 rule 8: filesystem access is confined
to ``output`` and ``persistence``), so ``app`` asks this module instead of
opening the file itself.
"""

from __future__ import annotations

from typing import Optional

__all__ = [
    "PolymerChain",
    "index_check_available",
    "library_available",
    "mapping_problem",
    "polymer_chains",
    "structure_problem",
    "template_mapping_problem",
    "template_structure_problem",
]

# The categories that make a file a structural template. A file with a
# ``data_`` block but none of these is not one.
_STRUCTURE_PREFIXES = (
    "_atom_site.",
    "_entity_poly",
    "_struct_asym",
    "_entity.",
    "_pdbx_poly_seq_scheme",
)

_NO_STRUCTURE = (
    "the file is not an mmCIF structure "
    "(it has no _atom_site, _entity_poly, _struct_asym or _entity records)"
)
_NO_BLOCK = "the file is not an mmCIF structure (it has no 'data_' block)"


def structure_problem(text: str) -> Optional[str]:
    """Why ``text`` is not a usable template structure, or ``None`` when it is.

    The bundled lexical scan runs first (it is cheap and deterministic), then
    the established parser when one is installed — an installed parser can only
    add strictness, never turn a refusal into an acceptance.
    """
    problem = _lexical_problem(text)
    if problem is not None:
        return problem
    return _library_problem(text)


def template_structure_problem(path: str) -> Optional[str]:
    """Why the file at ``path`` is not a usable template, or ``None``.

    The reasons are clauses the caller embeds in its own sentence, and they
    keep the project's existing vocabulary: an unreadable file, an empty one,
    text that is not UTF-8, and text that is not a structure.
    """
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
    except OSError:
        return "the file cannot be read"
    if not payload.strip():
        return "the file is empty"
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return "the file is not UTF-8 text"
    return structure_problem(text)


# -- the established parser, when it is installed (plan §9.6) --------------------


_LOADED = False
_LIBRARY = None


def _load_library():
    """gemmi, or ``None`` when it is not importable (patched by tests).

    A separate function so the bundled path can be exercised deliberately, and
    so the import is attempted once per process.
    """
    try:
        import gemmi
    except Exception:  # not installed, or broken: either way, unavailable
        return None
    return gemmi


def _library():
    global _LOADED, _LIBRARY
    if not _LOADED:
        _LIBRARY = _load_library()
        _LOADED = True
    return _LIBRARY


def library_available() -> bool:
    """Whether an established mmCIF parser is importable in this environment."""
    return _library() is not None


def _library_problem(text: str) -> Optional[str]:
    """The established parser's verdict on ``text``, or ``None``.

    ``None`` means either "it parsed" or "there is no parser here"; the
    bundled scan has already had its say in both cases.
    """
    module = _library()
    if module is None:
        return None
    try:
        document = module.cif.read_string(text)
    except Exception as error:  # the library's own way of saying no
        return "the file is not a readable mmCIF structure (%s)" % _reason(error)
    try:
        has_block = any(True for _block in document)
    except Exception:
        # A library whose iteration fails has not told us the file is broken;
        # the bundled scan's verdict stands.
        return None
    if not has_block:
        return _NO_BLOCK
    return None


def _reason(error) -> str:
    """One short line from a parser refusal — never a traceback in the UI."""
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    first = lines[0] if lines else error.__class__.__name__
    return first[:160]


# -- polymer chains and template-index bounds -----------------------------------


class PolymerChain:
    """One polymer entity of a template: its strand id(s), kind and sequence.

    ``sequence`` is the **full** polymer sequence — every residue the file
declares, including those with no ``_atom_site`` row. That is the sequence
AF3's ``templateIndices`` address, so it is the only sequence these bounds
can be checked against.
    """

    __slots__ = ("chain_id", "kind", "sequence")

    def __init__(self, chain_id: str, kind: str, sequence: str) -> None:
        self.chain_id = chain_id
        self.kind = kind
        self.sequence = sequence

    def __repr__(self) -> str:
        return "PolymerChain(%r, %r, %d residues)" % (
            self.chain_id,
            self.kind,
            len(self.sequence),
        )


#: Entity-type prefix → the kind word used in messages.
_POLYMER_KINDS = (
    ("polypeptide", "protein"),
    ("polyribonucleotide", "RNA"),
    ("polydeoxyribonucleotide", "DNA"),
)


def index_check_available() -> bool:
    """Whether template indices can be checked against the template sequence.

    True only when an established mmCIF reader is installed: the bundled
    lexical scan proves a file is a structure but cannot enumerate residues, so
    index bounds against the template's polymer sequence are unknowable there.
    """
    return library_available()


def _kind_of(entity_type: str) -> str:
    lowered = (entity_type or "").strip().lower()
    for prefix, word in _POLYMER_KINDS:
        if lowered.startswith(prefix):
            return word
    return "other"


def _one_letter_sequence(module, block, columns) -> dict:
    """Full polymer sequence per entity id, from the categories that carry it.

    Preference order matters. ``pdbx_seq_one_letter_code_can`` is the canonical
    one-letter form; ``pdbx_seq_one_letter_code`` is the same sequence with
    parenthesised component codes for modified residues; ``_entity_poly_seq``
    is the authoritative residue list (which is exactly what "includes
    unresolved residues" means) and is used when neither poly column is
    present. Every path yields the *same length* for a given entity, because
    all three enumerate the full polymer.
    """
    sequences = {}
    ids = columns.get("entity_id") or []
    canonical = columns.get("pdbx_seq_one_letter_code_can") or []
    plain = columns.get("pdbx_seq_one_letter_code") or []
    for position, entity_id in enumerate(ids):
        text = canonical[position] if position < len(canonical) else ""
        text = (text or "").strip()
        if not text or not text.replace("\n", "").isalpha():
            text = (plain[position] if position < len(plain) else "") or ""
            text = text.strip()
        if text and not text.isalpha():
            text = ""  # e.g. '(MSE)' component codes: derive below instead
        sequences[entity_id] = "".join(text.split())

    if any(not sequence for sequence in sequences.values()):
        derived = _sequence_from_residue_table(module, block)
        for entity_id, sequence in sequences.items():
            if not sequence and entity_id in derived:
                sequences[entity_id] = derived[entity_id]
    return sequences


def _sequence_from_residue_table(module, block) -> dict:
    """Per-entity sequence from ``_entity_poly_seq`` (all declared residues).

    Three-letter codes are translated with the parser's own residue table, so
    nothing here maintains a second chemistry dictionary.
    """
    rows = block.get_mmcif_category("_entity_poly_seq.")
    sequences = {}
    for entity_id, mon_id in zip(
        rows.get("entity_id") or [], rows.get("mon_id") or []
    ):
        information = None
        try:
            information = module.find_tabulated_residue(mon_id)
        except Exception:
            information = None
        letter = getattr(information, "one_letter_code", "") or "X"
        sequences.setdefault(entity_id, []).append(letter.strip() or "X")
    return {key: "".join(value) for key, value in sequences.items()}


def polymer_chains(text: str):
    """``(parser, chains, problem)`` for one mmCIF document.

    ``parser`` is ``"gemmi"`` when an established reader produced the chains
    and ``"lexical"`` when only the bundled scan ran (``chains`` is then empty
    and ``problem`` is ``None``: the structure verdict has already been given
    by :func:`structure_problem`). A ``problem`` is returned when the document
    cannot be read into chains at all.
    """
    module = _library()
    if module is None:
        return "lexical", (), None
    try:
        document = module.cif.read_string(text)
        block = next(iter(document))
    except Exception as error:
        return "gemmi", (), "the template cannot be read as mmCIF (%s)" % _reason(error)
    if block is None:
        return "gemmi", (), "the template has no mmCIF data block"
    try:
        columns = block.get_mmcif_category("_entity_poly.")
    except Exception as error:
        return "gemmi", (), "the template's polymer records cannot be read (%s)" % _reason(error)
    sequences = _one_letter_sequence(module, block, columns)
    chains = []
    entity_ids = columns.get("entity_id") or []
    types = columns.get("type") or []
    strands = columns.get("pdbx_strand_id") or []
    for position, entity_id in enumerate(entity_ids):
        kind = _kind_of(types[position] if position < len(types) else "")
        sequence = sequences.get(entity_id, "")
        strand = (strands[position] if position < len(strands) else "") or entity_id
        for chain_id in [part.strip() for part in str(strand).split(",") if part.strip()]:
            chains.append(PolymerChain(chain_id, kind, sequence))
    return "gemmi", tuple(chains), None


def _pair_indices(pair):
    """``(query, template)`` of one pair, in either supported shape.

    ``IndexPair`` is the model type, but a two-item sequence is accepted so a
    caller (or a test) that has not built one still gets its bounds checked.
    Anything else raises: silently skipping an unreadable pair would report
    "the mapping is fine" about a mapping that was never examined.
    """
    query = getattr(pair, "query", None)
    template = getattr(pair, "template", None)
    if query is not None and template is not None:
        return int(query), int(template)
    if isinstance(pair, (tuple, list)) and len(pair) == 2:
        return int(pair[0]), int(pair[1])
    raise TypeError("a template index pair must be an IndexPair or (query, template), got %r" % (pair,))


def mapping_problem(text: str, pairs, query_length: int) -> Optional[str]:
    """Why ``pairs`` cannot address ``text``'s template chain, or ``None``.

    The clause is embedded by the caller in its own sentence. Bounds are checked
    against the template's **full polymer sequence** (unresolved residues
    included) and against the query's length; amino-acid identity is not
    compared, because homology templates legitimately substitute residues.

    Returns ``None`` when no established parser is installed: without one the
    template's residues are not knowable, and guessing a length from atom
    coordinates would be exactly the off-by-three error this check exists to
    prevent. Callers report which level of checking ran
    (:func:`index_check_available`) rather than implying the stronger one.
    """
    parser, chains, problem = polymer_chains(text)
    if problem is not None:
        return problem
    if parser != "gemmi":
        return None
    proteins = [chain for chain in chains if chain.kind == "protein"]
    if not proteins:
        return "the template contains no protein chain (AF3 templates are protein chains)"
    if len(proteins) > 1:
        return (
            "the template contains %d protein chains; AF3 accepts only a "
            "single-chain template" % len(proteins)
        )
    length = len(proteins[0].sequence)
    if length == 0:
        return "the template's protein chain declares no residues"
    for pair in pairs:
        query, template = _pair_indices(pair)
        if template >= length:
            return (
                "template index %d is outside the template polymer sequence "
                "(length %d; valid 0-%d)" % (template, length, length - 1)
            )
        if query >= query_length:
            return (
                "query index %d is outside the protein sequence "
                "(length %d; valid 0-%d)" % (query, query_length, query_length - 1)
            )
    return None


def template_mapping_problem(path: str, pairs, query_length: int) -> Optional[str]:
    """The file-based case of :func:`mapping_problem`.

    An unreadable file is not this function's verdict: the structure check owns
    that message, so this returns ``None`` rather than repeating a weaker one.
    """
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
    except OSError:
        return None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return mapping_problem(text, pairs, query_length)


# -- the bundled lexical scan, always -------------------------------------------


def _lexical_problem(text: str) -> Optional[str]:
    """mmCIF's lexical grammar, and the structure it must contain."""
    scan = _Scan()
    return scan.run(text)


def _tokens(line: str):
    """One line's tokens: whitespace-separated, with quotes grouping.

    An mmCIF quoted value ends at the end of its line, so an unterminated
    quote simply ends the value there. A ``#`` outside quotes starts a comment
    that runs to the end of the line.
    """
    tokens = []
    length = len(line)
    index = 0
    while index < length:
        character = line[index]
        if character.isspace():
            index += 1
            continue
        if character == "#":
            break
        if character in "'\"":
            index += 1
            start = index
            while index < length and line[index] != character:
                index += 1
            tokens.append(line[start:index])
            index += 1
            continue
        start = index
        while index < length and not line[index].isspace():
            index += 1
        tokens.append(line[start:index])
    return tokens


class _Scan:
    """One pass over the text, stopping at the first defect it can name."""

    def __init__(self) -> None:
        self._block = False
        self._structure = False
        self._in_loop = False
        self._tags = ()
        self._values = 0
        self._loop_line = 0

    def _end_loop(self) -> Optional[str]:
        """Apply the loop rule: complete rows of exactly the declared width."""
        tagged = len(self._tags)
        self._in_loop = False
        if tagged and self._values % tagged:
            problem = (
                "the file is not a usable mmCIF structure (the loop starting at "
                "line %d declares %d tags, and its values do not form complete "
                "rows of that size)" % (self._loop_line, tagged)
            )
            self._tags = ()
            self._values = 0
            return problem
        self._tags = ()
        self._values = 0
        return None

    def _start_loop(self, line_number: int) -> None:
        self._in_loop = True
        self._tags = ()
        self._values = 0
        self._loop_line = line_number

    def _note_tag(self, token: str) -> None:
        if token.startswith(_STRUCTURE_PREFIXES):
            self._structure = True

    @staticmethod
    def _text_field_follows(lines, index: int) -> bool:
        """Whether the next meaningful line opens a ``;`` text field.

        A data item's value may sit on the following line only as a text
        field, which begins with ``;`` at column 0. Anything else after a tag
        that carries no value is the parser's own complaint ("has no value").
        """
        total = len(lines)
        while index < total:
            line = lines[index]
            if not line.strip() or line.lstrip().startswith("#"):
                index += 1
                continue
            return line.startswith(";")
        return False

    def run(self, text: str) -> Optional[str]:
        lines = text.splitlines()
        total = len(lines)
        index = 0
        while index < total:
            raw = lines[index]
            number = index + 1
            index += 1
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            if raw.startswith(";"):
                # A ';' text field: one value, from column 0 to the next ';'
                # at column 0. It may contain anything, '#' included.
                while index < total and not lines[index].startswith(";"):
                    index += 1
                index += 1
                if self._in_loop:
                    self._values += 1
                continue
            tokens = _tokens(raw)
            if not tokens:
                continue
            first = tokens[0]
            if first == "loop_":
                problem = self._end_loop()
                if problem is not None:
                    return problem
                self._start_loop(number)
                continue
            if first.startswith("data_") or first.startswith("save_") or first == "stop_":
                problem = self._end_loop()
                if problem is not None:
                    return problem
                if first.startswith("data_"):
                    self._block = True
                continue
            if first.startswith("_"):
                if self._in_loop:
                    if self._values:
                        # A tag after values ends the loop; the row rule is
                        # applied before this tag is read as a data item.
                        problem = self._end_loop()
                        if problem is not None:
                            return problem
                    else:
                        self._tags += tuple(tokens)
                        for token in tokens:
                            self._note_tag(token)
                        continue
                self._note_tag(first)
                if len(tokens) > 1 or self._text_field_follows(lines, index):
                    continue
                return (
                    "the file is not a usable mmCIF structure (the data item %s "
                    "at line %d has no value)" % (first, number)
                )
            if self._in_loop:
                self._values += len(tokens)
            # A bare value outside a loop is tolerated: this scan rejects what
            # cannot be a structure, it does not grade mmCIF style.
        problem = self._end_loop()
        if problem is not None:
            return problem
        if not self._block:
            return _NO_BLOCK
        if not self._structure:
            return _NO_STRUCTURE
        return None
