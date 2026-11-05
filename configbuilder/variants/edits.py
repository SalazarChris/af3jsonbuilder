"""Variant edit vocabulary (IMPLEMENTATION_PLAN.md §12.1, spec §15).

Edits are typed, immutable data — reviewable before application,
persistable into the project file, and answerable ("what differs between
these variants?") without diffing two documents. The vocabulary covers
exactly the variant-relevant dimensions of spec §15 and nothing else:
job name, job description, seeds, sequences, modifications, alignments
(pairing and single), references, component representations and copy counts, records
themselves, linkages, the component definition, and the format target.

``record_key`` is the record's primary ``EntityId``, resolved through the
configuration's ``IdentityRegistry`` (``registry.resolve_strict``) — never
a list position (plan §12.1). Resolving at application time means an edit
survives earlier edits that added or removed other records.

Every edit is frozen, hashable, and equal-by-value so expansion is
deterministic and edit lists can be persisted and compared. Application
returns a new ``Configuration``; nothing is mutated (plan §12.4).
"""

from __future__ import annotations

from configbuilder.identity import EntityId, IdentityError, Multiplicity
from configbuilder.model import (
    AlignmentPairing,
    ByCode,
    ByNotation,
    ComponentCode,
    ComponentRecord,
    Configuration,
    duplex_partner,
    External,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    FormatTarget,
    fold_alignment,
    fold_presence,
    fold_reference_set,
    fold_representation,
    fold_resource,
    fold_single_alignment,
    fold_version_selection,
    Inline,
    Linkage,
    ModificationRecord,
    reverse_complement,
    Position,
    ReferenceSet,
    SeedSet,
    SequenceText,
    SingleAlignment,
    Unset,
    is_presence,
)

__all__ = [
    "AddLinkage",
    "describe_edit",
    "AddModification",
    "AddRecord",
    "EDIT_CLASSES",
    "EditError",
    "RemoveLinkage",
    "RemoveModification",
    "RemoveRecord",
    "SetAlignment",
    "SetComponentDefinition",
    "SetComponentRepresentation",
    "SetComponentCount",
    "SetDescription",
    "SetFormatTarget",
    "SetJobDescription",
    "SetName",
    "SetReferences",
    "SetSeeds",
    "SetSequence",
    "SetSingleAlignment",
    "apply_edit",
    "record_for_key",
]
class EditError(Exception):
    """Raised when an edit cannot be applied (unknown record key, wrong
    family for the edit, malformed payload). This is a programming or
    project-content error surfaced at expansion time — validation findings
    are a separate vocabulary."""


def record_for_key(configuration: Configuration, record_key: EntityId):
    """Resolve a record key to its record through identity (plan §12.1).

    The registry is the authority: the record whose multiplicity contains
    ``record_key`` is the edit target, so an edit never depends on list
    position. A key the registry does not hold is an ``EditError`` —
    expansion-time refusal, not a raw identity exception.
    """
    if not isinstance(record_key, EntityId):
        raise EditError("record_key must be an EntityId")
    try:
        multiplicity = configuration.identity.multiplicity_of(record_key)
    except IdentityError as error:
        raise EditError(
            "record key %r is not assigned in the registry: %s" % (record_key.value, error)
        ) from error
    for record in configuration.records:
        if record.ids.primary == multiplicity.primary:
            return record
    raise EditError(
        "registry holds %r but no record claims it; registry and records disagree"
        % (record_key.value,)
    )


def _replace_record(configuration, old, new):
    """Records with a new tuple where ``old`` is replaced by ``new``."""
    records = tuple(new if record is old else record for record in configuration.records)
    return configuration.with_records(records)


def _check_record_family(edit_name, record, expected_types, text):
    if not isinstance(record, expected_types):
        raise EditError(
            "%s targets %s, which is not a %s"
            % (edit_name, record.ids.primary.value, text)
        )


class _EditBase:
    """Common edit machinery: immutable, value-equal, repr-able."""

    __slots__ = ()

    def __setattr__(self, name, value):
        raise EditError("edits are immutable")

    def _fields(self):
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return (type(self).__name__, self._fields()) == (
                type(other).__name__,
                other._fields(),
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._fields()))

    def __repr__(self) -> str:
        return "%s(%s)" % (
            type(self).__name__,
            ", ".join(repr(value) for value in self._fields()),
        )


# -- root-level edits ----------------------------------------------------------


class SetName(_EditBase):
    """The job name (spec §15: job name — metadata/naming)."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise EditError("SetName requires a non-empty name")
        object.__setattr__(self, "_name", name)

    def _fields(self):
        return (self._name,)


class SetJobDescription(_EditBase):
    """The job-level description Presence (spec §15: descriptions).

    The plan §12.1 sketch calls this ``SetDescription``; the record-level
    edit of the same intent is spelled out as ``SetRecordDescription``
    semantics inside ``SetDescription`` below.
    """

    __slots__ = ("_description",)

    def __init__(self, description) -> None:
        if not is_presence(description):
            raise EditError("SetJobDescription requires a Presence value")
        object.__setattr__(self, "_description", description)

    def _fields(self):
        return (self._description,)


class SetDescription(_EditBase):
    """A record's chain description (spec §15: descriptions).

    ``Presence`` value form: ``Present(text)`` / ``ExplicitEmpty()`` /
    ``Unset()`` — mirroring the model's presence algebra.
    """

    __slots__ = ("_record_key", "_description")

    def __init__(self, record_key: EntityId, description) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("SetDescription record_key must be an EntityId")
        if not is_presence(description):
            raise EditError("SetDescription requires a Presence value")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(self, "_description", description)

    def _fields(self):
        return (self._record_key, self._description)


class SetSeeds(_EditBase):
    """The model seed list (spec §15: random seeds)."""

    __slots__ = ("_seeds",)

    def __init__(self, seeds) -> None:
        if not isinstance(seeds, SeedSet):
            try:
                seeds = SeedSet(list(seeds))
            except TypeError:
                raise EditError("SetSeeds requires a SeedSet or a list of seeds") from None
        object.__setattr__(self, "_seeds", seeds)

    def _fields(self):
        return (self._seeds,)


class SetComponentDefinition(_EditBase):
    """The root user-CCD source (spec §15: user CCD content/path).

    ``Inline(text)`` / ``External(path)`` / ``None`` — the last removes the
    definition entirely (``component_definition`` is 0..1, MAP-1203).
    """

    __slots__ = ("_definition",)

    def __init__(self, definition) -> None:
        if definition is not None and not isinstance(definition, (Inline, External)):
            raise EditError("SetComponentDefinition requires Inline, External, or None")
        object.__setattr__(self, "_definition", definition)

    def _fields(self):
        return (self._definition,)


class SetFormatTarget(_EditBase):
    """The dialect/version selection (spec §15: naming-adjacent; plan §10.3)."""

    __slots__ = ("_format_target",)

    def __init__(self, format_target: FormatTarget) -> None:
        if not isinstance(format_target, FormatTarget):
            raise EditError("SetFormatTarget requires a FormatTarget")
        object.__setattr__(self, "_format_target", format_target)

    def _fields(self):
        return (self._format_target,)


# -- record-level edits (resolved via record_key) --------------------------------


class SetSequence(_EditBase):
    """A polymer record's sequence (spec §15: protein/RNA/DNA sequences)."""

    __slots__ = ("_record_key", "_text")

    def __init__(self, record_key: EntityId, text: SequenceText) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("SetSequence record_key must be an EntityId")
        if not isinstance(text, SequenceText):
            raise EditError("SetSequence requires a SequenceText")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(self, "_text", text)

    def _fields(self):
        return (self._record_key, self._text)


class AddModification(_EditBase):
    """Append one modification to a polymer record (spec §15: polymer
    modifications)."""

    __slots__ = ("_record_key", "_modification")

    def __init__(self, record_key: EntityId, code: ComponentCode, position: Position) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("AddModification record_key must be an EntityId")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(
            self, "_modification", ModificationRecord(code=code, position=position)
        )

    def _fields(self):
        return (self._record_key, self._modification)


class RemoveModification(_EditBase):
    """Remove the modification at ``index`` (declared-order, stable within
    one expansion run — not a wire or sequence position)."""

    __slots__ = ("_record_key", "_index")

    def __init__(self, record_key: EntityId, index: int) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("RemoveModification record_key must be an EntityId")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise EditError("RemoveModification index must be a non-negative int")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(self, "_index", index)

    def _fields(self):
        return (self._record_key, self._index)


class SetAlignment(_EditBase):
    """A protein record's alignment (spec §15: MSA representation)."""

    __slots__ = ("_record_key", "_alignment")

    def __init__(self, record_key: EntityId, alignment) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("SetAlignment record_key must be an EntityId")
        if not isinstance(alignment, AlignmentPairing):
            raise EditError("SetAlignment requires an AlignmentPairing case")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(self, "_alignment", alignment)

    def _fields(self):
        return (self._record_key, self._alignment)


class SetSingleAlignment(_EditBase):
    """An RNA record's single alignment (spec §15: MSA representation)."""

    __slots__ = ("_record_key", "_alignment")

    def __init__(self, record_key: EntityId, alignment) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("SetSingleAlignment record_key must be an EntityId")
        if not isinstance(alignment, SingleAlignment):
            raise EditError("SetSingleAlignment requires a SingleAlignment case")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(self, "_alignment", alignment)

    def _fields(self):
        return (self._record_key, self._alignment)


class SetReferences(_EditBase):
    """A protein record's template reference set (spec §15: templates)."""

    __slots__ = ("_record_key", "_references")

    def __init__(self, record_key: EntityId, references) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("SetReferences record_key must be an EntityId")
        if not isinstance(references, ReferenceSet):
            raise EditError("SetReferences requires a ReferenceSet case")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(self, "_references", references)

    def _fields(self):
        return (self._record_key, self._references)


class SetComponentRepresentation(_EditBase):
    """A ligand record's CCD/SMILES representation (spec §15: ligand CCD
    codes / SMILES)."""

    __slots__ = ("_record_key", "_representation")

    def __init__(self, record_key: EntityId, representation) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("SetComponentRepresentation record_key must be an EntityId")
        if not isinstance(representation, (ByCode, ByNotation)):
            raise EditError("SetComponentRepresentation requires ByCode or ByNotation")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(self, "_representation", representation)

    def _fields(self):
        return (self._record_key, self._representation)


class SetComponentCount(_EditBase):
    """A ligand record's copy count — the quantity/concentration-series
    edit (variant dimension only; the base job's quantity is set at add
    time through ``add_record``'s ``copies``).

    The record is rebuilt with a fresh ``Multiplicity`` of ``count``
    identifiers: the existing primary identifier stays first, so the
    record keeps its identity, and the variant's registry clone gains
    exactly the new copies — allocated through identity, never
    hand-assigned. Trimming (count < current) releases the dropped
    identifiers. Like every edit, application runs on the expanded
    clone; the base configuration is never touched (plan §12.4).
    """

    __slots__ = ("_record_key", "_count")

    def __init__(self, record_key: EntityId, count: int) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("SetComponentCount record_key must be an EntityId")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise EditError("SetComponentCount count must be a whole number of at least 1")
        object.__setattr__(self, "_record_key", record_key)
        object.__setattr__(self, "_count", count)

    def _fields(self):
        return (self._record_key, self._count)


class AddRecord(_EditBase):
    """Add a fully-formed record (spec §15: entity IDs/copy counts).

    The registry gains the record's identifiers (reserved through identity,
    so uniqueness and allocation order stay registry-owned); duplicates of
    already-assigned identifiers are refused, never silently renamed.
    """

    __slots__ = ("_record",)

    def __init__(self, record) -> None:
        if not isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord, ComponentRecord)):
            raise EditError("AddRecord requires a record-family instance")
        object.__setattr__(self, "_record", record)

    def _fields(self):
        return (self._record,)


class RemoveRecord(_EditBase):
    """Remove a record by key; its identifiers are released in the
    variant's registry (plan §8.3: removals release per variant)."""

    __slots__ = ("_record_key",)

    def __init__(self, record_key: EntityId) -> None:
        if not isinstance(record_key, EntityId):
            raise EditError("RemoveRecord record_key must be an EntityId")
        object.__setattr__(self, "_record_key", record_key)

    def _fields(self):
        return (self._record_key,)


class AddLinkage(_EditBase):
    """Append a linkage (spec §15: bonded atom pairs). Endpoints must
    resolve in the registry after prior edits have applied."""

    __slots__ = ("_linkage",)

    def __init__(self, linkage: Linkage) -> None:
        if not isinstance(linkage, Linkage):
            raise EditError("AddLinkage requires a Linkage")
        object.__setattr__(self, "_linkage", linkage)

    def _fields(self):
        return (self._linkage,)


class RemoveLinkage(_EditBase):
    """Remove the linkage at ``index`` (stable declaration order)."""

    __slots__ = ("_index",)

    def __init__(self, index: int) -> None:
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise EditError("RemoveLinkage index must be a non-negative int")
        object.__setattr__(self, "_index", index)

    def _fields(self):
        return (self._index,)


# -- record reconstruction ------------------------------------------------------------
# Record reconstruction is a model service: the frozen record types expose
# ``with_*`` methods that rebuild through their validated constructors, so
# this module never re-assembles record fields by hand and never needs to
# know a family's field list (plan §7.4: families own their fields).


# -- application -----------------------------------------------------------------


def apply_edit(edit, configuration: Configuration) -> Configuration:
    """Apply one edit, returning a new ``Configuration``.

    Pure: no mutation, no IO, no randomness. ``record_key`` edits resolve
    through the registry at application time.
    """
    if isinstance(edit, SetName):
        return configuration.with_named(edit._name)

    if isinstance(edit, SetJobDescription):
        return configuration.with_job_description(edit._description)

    if isinstance(edit, SetDescription):
        record = record_for_key(configuration, edit._record_key)
        replacement = record.with_description(edit._description)
        return _replace_record(configuration, record, replacement)

    if isinstance(edit, SetSeeds):
        return configuration.with_seeds(edit._seeds)

    if isinstance(edit, SetComponentDefinition):
        return configuration.with_component_definition(edit._definition)

    if isinstance(edit, SetFormatTarget):
        return configuration.with_format_target(edit._format_target)

    if isinstance(edit, SetSequence):
        record = record_for_key(configuration, edit._record_key)
        _check_record_family("SetSequence", record, (FamilyARecord, FamilyBRecord, FamilyCRecord), "polymer record")
        # The partner is read from the state *before* the edit: afterwards the
        # strand no longer matches its own complement (DNA duplex feature).
        partner = duplex_partner(configuration, record)
        configuration = _replace_record(configuration, record, record.with_sequence(edit._text))
        if partner is None:
            return configuration
        return _replace_record(
            configuration, partner, partner.with_sequence(reverse_complement(edit._text))
        )

    if isinstance(edit, AddModification):
        record = record_for_key(configuration, edit._record_key)
        _check_record_family(
            "AddModification", record, (FamilyARecord, FamilyBRecord, FamilyCRecord), "polymer record"
        )
        replacement = record.with_modifications(
            record.modifications + (edit._modification,)
        )
        return _replace_record(configuration, record, replacement)

    if isinstance(edit, RemoveModification):
        record = record_for_key(configuration, edit._record_key)
        # Every sibling record edit checks the family first; this case did
        # not, so an edit aimed at a record with no modification list (a
        # ligand) escaped as an ``AttributeError`` out of expansion
        # (BUG-023) instead of the EditError every caller handles.
        _check_record_family(
            "RemoveModification",
            record,
            (FamilyARecord, FamilyBRecord, FamilyCRecord),
            "polymer record",
        )
        modifications = list(record.modifications)
        if edit._index >= len(modifications):
            raise EditError(
                "RemoveModification index %d out of range (%d modifications on %s)"
                % (edit._index, len(modifications), record.ids.primary.value)
            )
        del modifications[edit._index]
        replacement = record.with_modifications(tuple(modifications))
        return _replace_record(configuration, record, replacement)

    if isinstance(edit, SetAlignment):
        record = record_for_key(configuration, edit._record_key)
        _check_record_family("SetAlignment", record, (FamilyARecord,), "protein record")
        replacement = record.with_alignment(edit._alignment)
        return _replace_record(configuration, record, replacement)

    if isinstance(edit, SetSingleAlignment):
        record = record_for_key(configuration, edit._record_key)
        _check_record_family("SetSingleAlignment", record, (FamilyBRecord,), "RNA record")
        replacement = record.with_alignment(edit._alignment)
        return _replace_record(configuration, record, replacement)

    if isinstance(edit, SetReferences):
        record = record_for_key(configuration, edit._record_key)
        _check_record_family("SetReferences", record, (FamilyARecord,), "protein record")
        replacement = record.with_references(edit._references)
        return _replace_record(configuration, record, replacement)

    if isinstance(edit, SetComponentRepresentation):
        record = record_for_key(configuration, edit._record_key)
        _check_record_family(
            "SetComponentRepresentation", record, (ComponentRecord,), "ligand record"
        )
        replacement = record.with_representation(edit._representation)
        return _replace_record(configuration, record, replacement)

    if isinstance(edit, SetComponentCount):
        record = record_for_key(configuration, edit._record_key)
        _check_record_family(
            "SetComponentCount", record, (ComponentRecord,), "ligand record"
        )
        current = [entity.value for entity in record.ids]
        if edit._count == len(current):
            return configuration
        if edit._count < len(current):
            # Trim: release the surplus identifiers in the variant's own
            # registry clone (cloned at expansion start) and rebuild.
            registry = configuration.identity.clone()
            registry.release_multiplicity(
                Multiplicity(current[edit._count:]), missing_ok=True
            )
            replacement = ComponentRecord(
                ids=Multiplicity(current[:edit._count]),
                representation=record.representation,
                description=None
                if isinstance(record.description, Unset)
                else record.description,
            )
            configuration = configuration.with_identity(registry)
            return _replace_record(configuration, record, replacement)
        # Grow: allocate the new copies through the variant's registry
        # clone. The existing identifiers stay (the record keeps its
        # identity); the fresh letters come from identity, never by hand.
        registry = configuration.identity.clone()
        fresh = [
            registry.allocate(owner="set_component_count")
            for _ in range(edit._count - len(current))
        ]
        replacement = ComponentRecord(
            ids=Multiplicity(current + [entity.value for entity in fresh]),
            representation=record.representation,
            description=None
            if isinstance(record.description, Unset)
            else record.description,
        )
        configuration = configuration.with_identity(registry)
        return _replace_record(configuration, record, replacement)

    if isinstance(edit, AddRecord):
        record = edit._record
        # Clone before mutate: the base's registry is shared with the base
        # configuration and every sibling variant (plan §12.4 isolation).
        registry = configuration.identity.clone()
        for entity in record.ids:
            if registry.is_taken(entity.value):
                raise EditError(
                    "AddRecord: identifier %r is already assigned; identifiers are "
                    "refused, never silently renamed (plan §8.1)" % entity.value
                )
        registry.reserve_multiplicity(record.ids)
        configuration = configuration.with_identity(registry)
        return configuration.with_records(configuration.records + (record,))

    if isinstance(edit, RemoveRecord):
        record = record_for_key(configuration, edit._record_key)
        # A DNA duplex is one user-level entity: removing either strand
        # removes the pair, exactly as the base-edit path does (DNA duplex
        # feature). A lone strand removes on its own.
        partner = duplex_partner(configuration, record)
        doomed = (record,) if partner is None else (record, partner)
        # Clone before mutate (plan §12.4): releasing in place would drain
        # the identifier out of the base and every sibling variant.
        registry = configuration.identity.clone()
        for target in doomed:
            registry.release_multiplicity(target.ids, missing_ok=True)
        configuration = configuration.with_identity(registry)
        records = tuple(r for r in configuration.records if r not in doomed)
        configuration = configuration.with_records(records)
        # Linkages referencing a removed record must go: an endpoint that
        # no longer resolves would be a dangling reference.
        gone = {entity for target in doomed for entity in target.ids}
        linkages = tuple(
            linkage
            for linkage in configuration.linkages
            if linkage.a.entity not in gone and linkage.b.entity not in gone
        )
        if len(linkages) != len(configuration.linkages):
            configuration = configuration.with_linkages(linkages)
        return configuration

    if isinstance(edit, AddLinkage):
        linkage = edit._linkage
        registry = configuration.identity
        for endpoint in (linkage.a, linkage.b):
            registry.resolve_strict(endpoint.entity)
        return configuration.with_linkages(configuration.linkages + (linkage,))

    if isinstance(edit, RemoveLinkage):
        linkages = list(configuration.linkages)
        if edit._index >= len(linkages):
            raise EditError(
                "RemoveLinkage index %d out of range (%d linkages)"
                % (edit._index, len(linkages))
            )
        del linkages[edit._index]
        return configuration.with_linkages(tuple(linkages))

    raise EditError("unknown edit %r" % (edit,))


# The complete vocabulary, in plan §12.1 order. ``spec.py`` derives the
# declared-change descriptor from this; a new edit class must join both.
EDIT_CLASSES = (
    SetName,
    SetJobDescription,
    SetDescription,
    SetSeeds,
    SetSequence,
    AddModification,
    RemoveModification,
    SetAlignment,
    SetSingleAlignment,
    SetReferences,
    SetComponentRepresentation,
    SetComponentCount,
    AddRecord,
    RemoveRecord,
    AddLinkage,
    RemoveLinkage,
    SetComponentDefinition,
    SetFormatTarget,
)


def describe_edit(edit) -> dict:
    """The edit as a JSON-ready dictionary for persistence and the manifest
    (plan §13.6 per-variant ``applied edits``; MAP-015).

    Every edit round-trips through this form: ``describe`` is the project
    file's representation of a variant definition. Values are model values
    (EntityId, Presence cases, sum types), so a restored edit is rebuilt by
    the same validated constructors that built it the first time.

    The keys here are deliberately **not** wire field names (plan §14:
    project file ≠ generated input file): ``job_name`` where the wire says
    ``name``, ``presence`` where the wire says ``description``, and so on —
    the two vocabularies can never be confused or merged.
    """
    record_key = getattr(edit, "_record_key", None)
    base = {"kind": type(edit).__name__}
    if record_key is not None:
        base["record_key"] = record_key.value
    if isinstance(edit, SetName):
        return {**base, "job_name": edit._name}
    if isinstance(edit, SetJobDescription):
        return {**base, "presence": describe_edit._presence(edit._description)}
    if isinstance(edit, SetDescription):
        return {**base, "presence": describe_edit._presence(edit._description)}
    if isinstance(edit, SetSeeds):
        return {**base, "seeds": list(edit._seeds.values)}
    if isinstance(edit, SetSequence):
        return {**base, "text": edit._text.text, "family": edit._text.family}
    if isinstance(edit, (AddModification, RemoveModification)):
        if isinstance(edit, AddModification):
            return {
                **base,
                "code": edit._modification.code.value,
                "position": edit._modification.position.value,
            }
        return {**base, "index": edit._index}
    if isinstance(edit, SetAlignment):
        return {**base, "alignment": describe_edit._alignment(edit._alignment)}
    if isinstance(edit, SetSingleAlignment):
        return {**base, "alignment": describe_edit._single(edit._alignment)}
    if isinstance(edit, SetReferences):
        return {**base, "references": describe_edit._references(edit._references)}
    if isinstance(edit, SetComponentRepresentation):
        return {**base, "representation": describe_edit._representation(edit._representation)}
    if isinstance(edit, SetComponentCount):
        return {**base, "count": edit._count}
    if isinstance(edit, AddRecord):
        record = edit._record
        ids = [entity.value for entity in record.ids]
        entry = {**base, "family": type(record).__name__, "ids": ids}
        if hasattr(record, "sequence"):
            entry["sequence_text"] = {"text": record.sequence.text, "family": record.sequence.family}
        if hasattr(record, "representation"):
            entry["representation"] = describe_edit._representation(record.representation)
        if hasattr(record, "description"):
            entry["presence"] = describe_edit._presence(record.description)
        return entry
    if isinstance(edit, RemoveRecord):
        return base
    if isinstance(edit, (AddLinkage, RemoveLinkage)):
        if isinstance(edit, AddLinkage):
            return {
                **base,
                "a": describe_edit._endpoint(edit._linkage.a),
                "b": describe_edit._endpoint(edit._linkage.b),
            }
        return {**base, "index": edit._index}
    if isinstance(edit, SetComponentDefinition):
        if edit._definition is None:
            return {**base, "definition": None}

        def on_inline(text):
            return {"form": "inline", "text": text}

        # ``fold_resource`` hands the handler the PathSpec itself.
        def on_external(path):
            return {"form": "external", "path": path.raw}

        return {**base, "definition": fold_resource(edit._definition, on_inline, on_external)}
    if isinstance(edit, SetFormatTarget):
        selection = edit._format_target.version_selection

        def on_unverified():
            return {"form": "Unverified"}

        def on_pinned(version):
            return {"form": "Pinned", "pinned_version": version}

        def on_auto(evidenced):
            return {"form": "Auto", "evidenced": list(evidenced)}

        return {**base, "version_selection": fold_version_selection(selection, on_unverified, on_pinned, on_auto)}
    raise EditError("unknown edit %r" % (edit,))


def _presence(value):
    def on_unset():
        return {"form": "Unset"}

    def on_empty():
        return {"form": "ExplicitEmpty"}

    def on_present(unwrapped):
        return {"form": "Present", "value": unwrapped}

    return fold_presence(value, on_unset, on_empty, on_present)


def _alignment(alignment):
    def on_automatic():
        return {"form": "Automatic"}

    def on_free():
        return {"form": "Free"}

    def on_unpaired(source):
        return {"form": "UnpairedOnly", "source": describe_edit._resource(source)}

    def on_paired(source):
        return {"form": "PairedOnly", "source": describe_edit._resource(source)}

    def on_both(source):
        data = {"form": "Both", "source": describe_edit._resource(source)}
        if alignment.paired_source != source:
            data["paired_source"] = describe_edit._resource(alignment.paired_source)
        return data

    # fold_alignment's parameter order is (automatic, free, unpaired,
    # paired, both) — matching the fold, not the case list above.
    return fold_alignment(alignment, on_automatic, on_free, on_unpaired, on_paired, on_both)


def _single(alignment):
    def on_automatic():
        return {"form": "Automatic"}

    def on_free():
        return {"form": "Free"}

    def on_provided(source):
        return {"form": "Provided", "source": describe_edit._resource(source)}

    return fold_single_alignment(alignment, on_automatic, on_free, on_provided)


def _references(references):
    def on_allowed():
        return {"form": "SearchAllowed"}

    def on_explicit(items):
        return {
            "form": "Explicit",
            "items": [
                {
                    "source": describe_edit._resource(item.source),
                    "index_map": [
                        [pair.query, pair.template] for pair in item.index_map
                    ],
                }
                for item in items
            ],
        }

    return fold_reference_set(references, on_allowed, on_explicit)


def _representation(representation):
    def on_code(codes):
        return {"form": "ByCode", "codes": [code.value for code in codes]}

    def on_notation(text):
        return {"form": "ByNotation", "text": text}

    return fold_representation(representation, on_code, on_notation)


def _resource(source):
    def on_inline(text):
        return {"form": "inline", "text": text}

    # ``fold_resource`` hands the handler the PathSpec itself.
    def on_external(path):
        return {"form": "external", "path": path.raw}

    return fold_resource(source, on_inline, on_external)


def _endpoint(endpoint):
    return {
        "entity": endpoint.entity.value,
        "residue": endpoint.residue.value,
        "atom": endpoint.atom,
    }


# The helpers are attached to ``describe_edit`` so the dispatcher above can
# reach them without adding seven more public names to the module namespace.
#
# They are assigned *bare*, not through ``staticmethod``. ``describe_edit`` is a
# function, not a class, so there is no bound-method descriptor to neutralise,
# and wrapping them in ``staticmethod`` made every call site raise
# ``TypeError: 'staticmethod' object is not callable`` on Python 3.9: the
# ``staticmethod`` object itself only became callable in 3.10. ``requires-python``
# is ``>=3.9`` and the CI matrix runs 3.9, so the wrapper silently broke variant
# alignment, template and description round-tripping on the project's own
# declared floor -- 29 tests failed there and none of them failed on 3.11.
describe_edit._presence = _presence
describe_edit._alignment = _alignment
describe_edit._single = _single
describe_edit._references = _references
describe_edit._representation = _representation
describe_edit._resource = _resource
describe_edit._endpoint = _endpoint
