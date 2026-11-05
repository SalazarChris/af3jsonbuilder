"""Deserialize an AF3 wire document into the canonical model (§7, JSON import).

``to_wire`` is the single authority that maps the canonical model onto the
AF3 contract (plan §10.1). This module is its inverse for supported content:
an imported document is rebuilt **through the model's own validated
constructors** (identity, seeds, records, alignments, references), so an
imported configuration is indistinguishable from a UI-built one and a file
can never inject an invalid model.

Unsupported content is **never silently discarded**:

- unknown *families* are a hard refusal (the task's own example: "The file
  contains an entity type that this builder does not currently support");
- content the model cannot legally hold (bad alphabet, duplicate id,
  missing seeds, a bond to an undefined entity) raises ``WireImportError``
  — the import stops, nothing is half-converted;
- fields this builder does not model are reported as ``ImportNote`` rows:
  the user sees exactly what was not imported and chooses whether to
  proceed (§19: import with warning, never silent).

DNA imports as the file's own strand list — one ``FamilyCRecord`` per
strand, no complementing (duplication belongs to record creation, not to
import; §8).
"""

from __future__ import annotations

from configbuilder.identity import DuplicateIdError, EntityId, IdentityRegistry, Multiplicity
from configbuilder.model import (
    Configuration,
    ConfigurationError,
    ConfigurationMetadata,
    Dialect,
    ExplicitEmpty,
    ModelError,
    Present,
    SeedSet,
    Unset,
)
from configbuilder.model.alignment import (
    AlignmentBoth,
    AlignmentFree,
    AlignmentPairedOnly,
    AlignmentUnpairedOnly,
    SingleFree,
    SingleProvided,
)
from configbuilder.model.configuration import FormatTarget, Pinned
from configbuilder.model.records import (
    ByCode,
    ByNotation,
    ComponentRecord,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    LinkEndpoint,
    Linkage,
    ModificationRecord,
)
from configbuilder.model.references import Explicit, ReferenceRecord
from configbuilder.model.values import (
    ComponentCode,
    External,
    IndexPair,
    Inline,
    PathSpec,
    Position,
    ResidueRef,
    Seed,
    SequenceText,
)

__all__ = ["WireImportError", "ImportNote", "from_wire"]

_SUPPORTED_FAMILIES = ("protein", "rna", "dna", "ligand")

# Wire fields each family may carry beyond those the importer reads
# explicitly; anything else inside a known family becomes an ImportNote.
_KNOWN_FAMILY_FIELDS = {
    "protein": frozenset(
        {"id", "sequence", "modifications", "unpairedMsa", "unpairedMsaPath",
         "pairedMsa", "pairedMsaPath", "templates", "description"}
    ),
    "rna": frozenset(
        {"id", "sequence", "modifications", "unpairedMsa", "unpairedMsaPath", "description"}
    ),
    "dna": frozenset({"id", "sequence", "modifications", "description"}),
    "ligand": frozenset({"id", "ccdCodes", "smiles", "description"}),
}
_KNOWN_ROOT_FIELDS = frozenset(
    {"name", "modelSeeds", "sequences", "bondedAtomPairs", "userCCD", "userCCDPath",
     "dialect", "version"}
)


class WireImportError(Exception):
    """The document cannot be represented in the canonical model."""


class ImportNote:
    """One wire field this builder does not model (§19).

    ``field`` names where the content lives (``sequences[2].ionCoord``);
    ``detail`` is a user-facing sentence. Notes are advisory: the user
    chooses cancel vs. import-with-warning over the whole set.
    """

    __slots__ = ("field", "detail")

    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        self.detail = detail

    def __repr__(self) -> str:
        return "ImportNote(%r)" % (self.field,)


_MAX_SEED = (1 << 32) - 1


def _reject(message: str) -> None:
    raise WireImportError(message)


def _require_mapping(value, where: str) -> dict:
    if not isinstance(value, dict):
        _reject("%s must be a JSON object" % where)
    return value


def _require_int(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _reject("%s must be an integer" % where)
    return value


def _id_texts(value, where):
    """The ``id`` field's single-or-list form → list of id texts (spec §7.1)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return list(value)
    _reject("%s must be an id string or a list of id strings" % where)


def _resource(value, where: str):
    """A wire resource value → ``Inline`` / ``External``; ``None`` when absent.

    A non-empty string is a path (``External``); an object with text
    content is inline. The empty string means *explicitly empty* — a
    meaningful wire value the importer maps per-field.
    """
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        return External(PathSpec(value))
    if isinstance(value, dict):
        for key in ("text", "content", "data"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return Inline(text)
        path = value.get("path")
        if isinstance(path, str) and path.strip():
            return External(PathSpec(path))
        _reject("%s carries neither inline text nor a path" % where)
    _reject("%s must be a path string or inline text" % where)


def _import_modifications(entity, where: str):
    """``modifications`` → ModificationRecord tuple; protein and nucleic
    spellings (``ptmType``/``ptmPosition`` vs ``modificationType``/
    ``basePosition``) both accepted (MAP-203..205 / 303..305 / 353..355)."""
    rows = entity.get("modifications")
    if rows is None:
        return ()
    if not isinstance(rows, list):
        _reject("%s modifications must be a list" % where)
    records = []
    for index, row in enumerate(rows):
        row = _require_mapping(row, "%s modification %d" % (where, index))
        code_text = row.get("ptmType") or row.get("modificationType") or row.get("modType")
        if not isinstance(code_text, str) or not code_text.strip():
            _reject("%s modification %d has no modification code" % (where, index))
        position = _require_int(
            row.get("ptmPosition", row.get("basePosition", row.get("modPosition"))),
            "%s modification %d position" % (where, index),
        )
        if position < 1:
            _reject("%s modification %d position must be 1-based" % (where, index))
        try:
            records.append(ModificationRecord(ComponentCode(code_text.strip()), Position(position)))
        except (ValueError, TypeError) as error:
            _reject("%s modification %d: %s" % (where, index, error))
    return tuple(records)


def _import_description(entity):
    """Wire ``description`` → Presence (MAP-206): absent → Unset, ""
    → ExplicitEmpty, text → Present."""
    if "description" not in entity:
        return Unset()
    text = entity.get("description")
    if text is None or text == "":
        return ExplicitEmpty()
    if not isinstance(text, str):
        _reject("description must be a string")
    return Present(text)


def _import_alignment(entity, where: str, notes):
    """Protein MSA fields → AlignmentPairing (MAP-601..605), the exact
    inverse of ``_protein_msa_fields``:

    - all four fields absent/empty-of-content → no alignment (automatic);
    - ``unpairedMsa: ""`` + ``pairedMsa: ""`` → AlignmentFree;
    - one side populated, the other inline "" → one-sided case;
    - both sides populated → AlignmentBoth with independent per-side
      sources, so different paired and unpaired files survive the import.
    """
    unpaired = _inline_field(entity.get("unpairedMsa"), "%s unpairedMsa" % where)
    if unpaired is None:
        unpaired = _resource(entity.get("unpairedMsaPath"), "%s unpairedMsaPath" % where)
    paired = _inline_field(entity.get("pairedMsa"), "%s pairedMsa" % where)
    if paired is None:
        paired = _resource(entity.get("pairedMsaPath"), "%s pairedMsaPath" % where)
    free_marked = entity.get("unpairedMsa", None) == "" and entity.get("pairedMsa", None) == ""
    if unpaired is not None and paired is not None:
        return AlignmentBoth(source=unpaired, paired_source=paired)
    if unpaired is not None:
        return AlignmentUnpairedOnly(source=unpaired)
    if paired is not None:
        return AlignmentPairedOnly(source=paired)
    if free_marked:
        return AlignmentFree()
    return None


def _inline_field(value, where: str):
    """An inline-content wire field: a non-empty string **is the content**
    (never a path). Paths travel only in the companion ``*Path`` field."""
    if value is None:
        return None
    if not isinstance(value, str):
        _reject("%s must be inline text" % where)
    if not value.strip():
        return None
    return Inline(value)


def _import_single_alignment(entity, where: str):
    """RNA's single MSA field → SingleProvided / SingleFree (MAP-307/308)."""
    if entity.get("unpairedMsa", None) == "" and "unpairedMsaPath" not in entity:
        return SingleFree()
    single = _inline_field(entity.get("unpairedMsa"), "%s unpairedMsa" % where)
    if single is None:
        single = _resource(entity.get("unpairedMsaPath"), "%s unpairedMsaPath" % where)
    if single is None:
        return None
    return SingleProvided(source=single)


def _import_references(entity, where: str):
    """``templates`` → ReferenceSet (MAP-705/706): absent → SearchAllowed,
    present list → Explicit (empty list = explicitly none).

    A template's structure travels **either** inline as ``mmcif`` text or as
    an ``mmcifPath``; AlphaFold 3's own parser refuses a row that sets both
    (``Only one of mmcif/mmcifPath can be set.``), so this importer refuses it
    too, with the location in the message. Both forms are accepted: the inline
    one is what AF3's own ``Template.to_dict`` emits, and it is the shape this
    builder writes for a reference attached from memory, so a document must be
    readable whichever form it carries. The ``queryIndices``/``templateIndices``
    arrays are 0-based and parallel (MAP-703/704)."""
    rows = entity.get("templates")
    if rows is None:
        return None
    if not isinstance(rows, list):
        _reject("%s templates must be a list" % where)
    records = []
    for index, row in enumerate(rows):
        location = "%s template %d" % (where, index)
        row = _require_mapping(row, location)
        inline = row.get("mmcif")
        external = row.get("mmcifPath")
        if inline is not None and external is not None:
            _reject(
                "%s sets both mmcif and mmcifPath; exactly one is allowed"
                % location
            )
        if inline is not None:
            source = _inline_field(inline, "%s mmcif" % location)
            if source is None:
                _reject("%s has empty mmcif text; supply the structure or a path" % location)
        else:
            source = _resource(external, location)
            if source is None:
                _reject(
                    "%s has neither mmcif text nor an mmcifPath" % location
                )
        queries = row.get("queryIndices")
        templates = row.get("templateIndices")
        if queries is None and templates is None:
            queries, templates = [], []
        if not isinstance(queries, list) or not isinstance(templates, list):
            _reject("%s template %d index arrays must be lists" % (where, index))
        if len(queries) != len(templates):
            _reject(
                "%s template %d has %d query indices but %d template indices"
                % (where, index, len(queries), len(templates))
            )
        pairs = []
        for pair_index, (query, template) in enumerate(zip(queries, templates)):
            query = _require_int(query, "%s template %d queryIndices[%d]" % (where, index, pair_index))
            template = _require_int(template, "%s template %d templateIndices[%d]" % (where, index, pair_index))
            if query < 0 or template < 0:
                _reject("%s template %d indices are 0-based; negative values are invalid" % (where, index))
            pairs.append(IndexPair(query, template))
        records.append(ReferenceRecord(source=source, index_map=tuple(pairs)))
    return Explicit(items=tuple(records))


def _import_ligand_representation(entity, where: str):
    """``ccdCodes`` / ``smiles`` → ByCode / ByNotation (MAP-402/403/406)."""
    codes = entity.get("ccdCodes")
    smiles = entity.get("smiles")
    if codes is not None and smiles is not None:
        _reject("%s carries both ccdCodes and smiles; exactly one representation is allowed" % where)
    if codes is not None:
        if isinstance(codes, str):
            codes = [codes]
        if not isinstance(codes, list) or not codes:
            _reject("%s ccdCodes must be a non-empty code or list of codes" % where)
        try:
            return ByCode(tuple(ComponentCode(str(code).strip()) for code in codes))
        except (ValueError, TypeError) as error:
            _reject("%s: %s" % (where, error))
    if smiles is not None:
        if not isinstance(smiles, str) or not smiles.strip():
            _reject("%s smiles must be a non-empty string" % where)
        try:
            return ByNotation(smiles.strip())
        except (ValueError, TypeError) as error:
            _reject("%s: %s" % (where, error))
    _reject("%s carries neither ccdCodes nor smiles; it cannot be represented" % where)


def _import_entity(family: str, payload, where: str, notes):
    """One wire entity → its record list. DNA yields one record per strand
    entry in the file (no complementing, §8)."""
    entity = _require_mapping(payload, where)
    for key in sorted(entity):
        if key not in _KNOWN_FAMILY_FIELDS[family]:
            notes.append(
                ImportNote(
                    "%s.%s" % (where, key),
                    "field %r on this %s entity is not supported for editing and was not imported"
                    % (key, family),
                )
            )
    id_texts = _id_texts(entity.get("id"), "%s id" % where)

    # Read once, before the family dispatch: §4's ``description`` applies to
    # protein, RNA, DNA *and* ligand entries, so every branch below must carry
    # it through. Reading it after the ligand branch (as this did) silently
    # dropped a ligand's description, and the DNA branch never passed it on.
    description = _import_description(entity)

    if family == "ligand":
        representation = _import_ligand_representation(entity, where)
        return [
            ComponentRecord(
                ids=Multiplicity(id_texts),
                representation=representation,
                description=description,
            )
        ]

    sequence = entity.get("sequence")
    if not isinstance(sequence, str) or not sequence:
        _reject("%s has no sequence; a polymer entity requires one" % where)
    try:
        text = SequenceText(sequence, family)
    except ModelError as error:
        _reject("%s: %s" % (where, error))

    modifications = _import_modifications(entity, where)

    if family == "dna":
        return [
            FamilyCRecord(
                ids=Multiplicity(id_texts),
                sequence=text,
                modifications=modifications,
                description=description,
            )
        ]

    if family == "rna":
        return [
            FamilyBRecord(
                ids=Multiplicity(id_texts),
                sequence=text,
                modifications=modifications,
                alignment=_import_single_alignment(entity, where),
                description=description,
            )
        ]

    return [
        FamilyARecord(
            ids=Multiplicity(id_texts),
            sequence=text,
            modifications=modifications,
            alignment=_import_alignment(entity, where, notes),
            references=_import_references(entity, where),
            description=description,
        )
    ]


def _root_seeds(document) -> SeedSet:
    seeds = document.get("modelSeeds")
    if not isinstance(seeds, list) or not seeds:
        _reject("modelSeeds must be a non-empty list of integers")
    values = []
    for index, seed in enumerate(seeds):
        seed = _require_int(seed, "modelSeeds[%d]" % index)
        if seed < 0 or seed > _MAX_SEED:
            _reject("modelSeeds[%d] is outside the uint32 seed range" % index)
        values.append(Seed(seed))
    try:
        return SeedSet(tuple(values))
    except ConfigurationError as error:
        _reject(str(error))


def _root_linkages(document, registry):
    """``bondedAtomPairs`` → Linkage tuple (MAP-801..806). Each entry is a
    pair of ``[entityId, residue, atom]`` triples; 1-based residues; every
    referenced entity must exist in the file."""
    rows = document.get("bondedAtomPairs")
    if rows is None:
        return ()
    if not isinstance(rows, list):
        _reject("bondedAtomPairs must be a list")

    def endpoint(side, where: str) -> LinkEndpoint:
        if not isinstance(side, list) or len(side) != 3:
            _reject("%s must be [entityId, residue, atom]" % where)
        id_text, residue, atom = side
        if not isinstance(id_text, str):
            _reject("%s entityId must be a string" % where)
        if not registry.is_taken(id_text):
            _reject("%s references entity %r, which the file does not define" % (where, id_text))
        residue = _require_int(residue, "%s residue" % where)
        if not isinstance(atom, str) or not atom.strip():
            _reject("%s atom must be a non-empty name" % where)
        try:
            return LinkEndpoint(EntityId(id_text), ResidueRef(residue), atom)
        except (ModelError, ValueError) as error:
            _reject("%s: %s" % (where, error))

    linkages = []
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != 2:
            _reject("bondedAtomPairs[%d] must be a pair of [entityId, residue, atom] entries" % index)
        linkages.append(
            Linkage(
                endpoint(row[0], "bondedAtomPairs[%d] first entry" % index),
                endpoint(row[1], "bondedAtomPairs[%d] second entry" % index),
            )
        )
    return tuple(linkages)


def _root_component_definition(document, notes):
    """``userCCD`` / ``userCCDPath`` → the component-definition resource."""
    inline_text = document.get("userCCD")
    path_text = document.get("userCCDPath")
    if inline_text not in (None, "") and path_text not in (None, ""):
        notes.append(
            ImportNote(
                "userCCDPath",
                "both userCCD and userCCDPath are present; this builder keeps one, "
                "so the path was not imported",
            )
        )
    inline = _inline_field(inline_text, "userCCD")
    if inline is not None:
        return inline
    return _resource(path_text, "userCCDPath")


def _root_version(document, notes):
    """Wire ``version``/``dialect`` → Pinned (the file's own choice is
    preserved; changing it is the version menu's job)."""
    version = _require_int(document.get("version"), "version")
    if version < 1:
        _reject("version must be a positive integer")
    dialect = document.get("dialect")
    if dialect is not None and dialect != Dialect.STANDALONE_AF3:
        notes.append(
            ImportNote(
                "dialect",
                "dialect %r is not the supported %r dialect; the content imports but the "
                "output will carry the supported dialect" % (dialect, Dialect.STANDALONE_AF3),
            )
        )
    return Pinned(version)


def _looks_absolute(value: str) -> bool:
    """Whether a wire path is already absolute (POSIX or a Windows drive/UNC)."""
    if value.startswith(("/", "\\")):
        return True
    return len(value) > 2 and value[1] == ":" and value[2] in "/\\"


def _absolute_resource_path(value, base_dir: str):
    """``value`` as a path under ``base_dir`` unless it is already absolute.

    String work only: this package imports no filesystem modules (the
    architecture test enforces it), and a wire path is a string anyway. The
    result uses ``/`` separators, which every platform — and AF3 — accepts.
    """
    if not isinstance(value, str) or not value.strip():
        return value
    if _looks_absolute(value):
        return value
    return "%s/%s" % (base_dir.rstrip("/\\"), value.replace("\\", "/"))


def rebase_resource_paths(document, base_dir: str):
    """Resolve a document's **relative** resource paths against its own folder.

    An AF3 file's relative paths mean "relative to this file": a job saved
    with ``CopyIntoAssets`` points at ``assets/<template>.cif`` beside the
    JSON, and reopening that JSON must still find the file. Importing the
    document unchanged left the path relative to the *process's* working
    directory, so a re-save of a self-contained job was refused with
    "resource source 'assets/...' is missing".

    ``from_wire`` stays a pure document-to-model mapping; this is the one
    place that knows where the document lives. Absolute paths are returned
    untouched, so a document that already names its files absolutely is
    unaffected. Only the path-valued fields are touched (the mapping's own
    closed set), and the same dictionary object is returned.
    """
    from configbuilder.transform.mappings import PATH_FEATURE_MIN_VERSIONS

    if not isinstance(document, dict) or not isinstance(base_dir, str):
        return document

    def _rebase_entity(payload):
        if not isinstance(payload, dict):
            return
        for field in PATH_FEATURE_MIN_VERSIONS:
            if field in payload:
                payload[field] = _absolute_resource_path(payload[field], base_dir)
        templates = payload.get("templates")
        if isinstance(templates, list):
            for row in templates:
                if isinstance(row, dict) and "mmcifPath" in row:
                    row["mmcifPath"] = _absolute_resource_path(
                        row["mmcifPath"], base_dir
                    )

    if "userCCDPath" in document:
        document["userCCDPath"] = _absolute_resource_path(
            document["userCCDPath"], base_dir
        )
    sequences = document.get("sequences")
    if isinstance(sequences, list):
        for wrapper in sequences:
            if not isinstance(wrapper, dict):
                continue
            for payload in wrapper.values():
                _rebase_entity(payload)
    return document


def from_wire(document):
    """Rebuild a canonical ``Configuration`` from an AF3 wire document.

    Returns ``(configuration, notes)``. Raises ``WireImportError`` when the
    document cannot be represented — every constructor refusal (alphabet,
    duplicate id, missing seeds, unknown family, a bond to an undefined
    entity) surfaces as that error with the file location in the message.
    Unknown-but-tolerable fields come back as ``ImportNote`` rows instead.

    The rebuild runs through the same validated constructors the builder
    uses, so the result is always a legal model.
    """
    document = _require_mapping(document, "the document")

    notes = []
    for key in sorted(document):
        if key not in _KNOWN_ROOT_FIELDS:
            notes.append(
                ImportNote(
                    key,
                    "top-level field %r is not supported for editing and was not imported" % (key,),
                )
            )

    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        _reject("name must be a non-empty string")
    seeds = _root_seeds(document)
    format_target = FormatTarget(version_selection=_root_version(document, notes))

    sequences = document.get("sequences", [])
    if not isinstance(sequences, list):
        _reject("sequences must be a list")

    # Pass 1: every id, in wire order, so registry assignment matches the
    # file and duplicate/invalid ids are refused before anything is built.
    entity_specs = []
    ordered_ids = []
    for index, entity_wrapper in enumerate(sequences):
        wrapper = _require_mapping(entity_wrapper, "sequences[%d]" % index)
        if len(wrapper) != 1:
            _reject("sequences[%d] must be an object with exactly one entity-type key" % index)
        family, payload = next(iter(wrapper.items()))
        if family not in _SUPPORTED_FAMILIES:
            _reject(
                "sequences[%d]: entity type %r is not supported by this builder; "
                "the file was not modified" % (index, family)
            )
        payload = _require_mapping(payload, "sequences[%d].%s" % (index, family))
        id_texts = _id_texts(payload.get("id"), "sequences[%d].%s id" % (index, family))
        ordered_ids.extend(id_texts)
        entity_specs.append((index, family, payload))

    registry = IdentityRegistry()
    for id_text in ordered_ids:
        try:
            registry.assign(id_text, owner="record")
        except DuplicateIdError as error:
            _reject(str(error))
        except (ValueError, TypeError) as error:
            _reject("sequences contains an invalid id: %s" % (error,))

    # Pass 2: build the records through their validated constructors.
    records = []
    for index, family, payload in entity_specs:
        records.extend(_import_entity(family, payload, "sequences[%d].%s" % (index, family), notes))

    linkages = _root_linkages(document, registry)
    component_definition = _root_component_definition(document, notes)

    try:
        configuration = Configuration(
            metadata=ConfigurationMetadata(name.strip()),
            seeds=seeds,
            records=tuple(records),
            identity=registry,
            linkages=tuple(linkages),
            component_definition=component_definition,
            format_target=format_target,
        )
    except (ModelError, ConfigurationError, ValueError, TypeError) as error:
        _reject(str(error))
    return configuration, tuple(notes)
