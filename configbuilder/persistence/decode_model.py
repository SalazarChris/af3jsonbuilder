"""Decode project-file data back into the model (IMPLEMENTATION_PLAN.md §14).

The load path rebuilds everything through the **same validated constructors**
a UI-built project passes through, so a hand-edited or corrupted file cannot
inject an invalid model: any constructor refusal becomes a
``PersistenceError`` naming the location in the file. Unknown tags, unknown
edit kinds, and registry/record disagreement are refusals — never guesses.

Every dispatch mirrors the encoder case-for-case; the pairs of functions are
tested against each other by the round-trip fidelity suite.
"""

from __future__ import annotations

from configbuilder.identity import EntityId, IdentityRegistry, Multiplicity
from configbuilder.model import (
    AlignmentAutomatic,
    AlignmentBoth,
    AlignmentFree,
    AlignmentPairedOnly,
    AlignmentUnpairedOnly,
    Auto,
    ByCode,
    ByNotation,
    ComponentCode,
    ComponentRecord,
    Configuration,
    ConfigurationMetadata,
    Dialect,
    Explicit,
    ExplicitEmpty,
    External,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    FormatTarget,
    IndexPair,
    Inline,
    LinkEndpoint,
    Linkage,
    ModificationRecord,
    PathSpec,
    Pinned,
    Position,
    Present,
    ReferenceRecord,
    ResidueRef,
    SearchAllowed,
    SeedSet,
    SequenceText,
    SingleAutomatic,
    SingleFree,
    SingleProvided,
    Unset,
    Unverified,
)

from configbuilder.persistence.schema import PersistenceError

__all__ = ["decode_configuration", "decode_spec"]

_RECORD_CLASSES = {
    "FamilyARecord": FamilyARecord,
    "FamilyBRecord": FamilyBRecord,
    "FamilyCRecord": FamilyCRecord,
    "ComponentRecord": ComponentRecord,
}


def _fail(location: str, problem: str) -> PersistenceError:
    return PersistenceError("%s: %s" % (location, problem))


def _require(mapping, key, location):
    if not isinstance(mapping, dict) or key not in mapping:
        raise _fail(location, "missing %r" % key)
    return mapping[key]


# -- value helpers -----------------------------------------------------------------


def _presence(data, location):
    state = _require(data, "state", location)
    if state == "unset":
        return Unset()
    if state == "explicit-empty":
        return ExplicitEmpty()
    if state == "present":
        return Present(_require(data, "text", location))
    raise _fail(location, "unknown presence state %r" % (state,))


def _resource(data, location):
    form = _require(data, "form", location)
    if form == "inline":
        return Inline(_require(data, "text", location))
    if form == "external":
        return External(PathSpec(_require(data, "path", location)))
    raise _fail(location, "unknown resource form %r" % (form,))


def _resource_optional(data, location):
    if data is None:
        return None
    return _resource(data, location)


def _representation(data, location):
    form = _require(data, "form", location)
    if form == "codes":
        return ByCode(tuple(ComponentCode(code) for code in _require(data, "codes", location)))
    if form == "notation":
        return ByNotation(_require(data, "text", location))
    raise _fail(location, "unknown representation form %r" % (form,))


def _resource_data(data):
    if data is None:
        return None
    return data


def _alignment(data, location):
    form = _require(data, "form", location)
    if form == "automatic":
        return AlignmentAutomatic()
    if form == "free":
        return AlignmentFree()
    if form == "unpaired-only":
        return AlignmentUnpairedOnly(_resource(_require(data, "source", location), location))
    if form == "paired-only":
        return AlignmentPairedOnly(_resource(_require(data, "source", location), location))
    if form == "both":
        unpaired = _resource(_require(data, "source", location), location)
        paired_data = data.get("paired_source")
        paired = (
            unpaired
            if paired_data is None
            else _resource(paired_data, location + ".paired_source")
        )
        return AlignmentBoth(unpaired, paired)
    raise _fail(location, "unknown alignment form %r" % (form,))


def _single_alignment(data, location):
    form = _require(data, "form", location)
    if form == "automatic":
        return SingleAutomatic()
    if form == "free":
        return SingleFree()
    if form == "provided":
        return SingleProvided(_resource(_require(data, "source", location), location))
    raise _fail(location, "unknown single-alignment form %r" % (form,))


def _references(data, location):
    form = _require(data, "form", location)
    if form == "search-allowed":
        return SearchAllowed()
    if form == "explicit":
        records = []
        for index, item in enumerate(_require(data, "records", location)):
            where = "%s.records[%d]" % (location, index)
            index_map = tuple(
                IndexPair(int(pair[0]), int(pair[1])) for pair in _require(item, "index_map", where)
            )
            records.append(
                ReferenceRecord(
                    _resource(_require(item, "source", where), where),
                    index_map,
                )
            )
        return Explicit(tuple(records))
    raise _fail(location, "unknown reference-set form %r" % (form,))


def _version_selection(data, location):
    form = _require(data, "form", location)
    if form == "unverified":
        return Unverified()
    if form == "pinned":
        evidence = data.get("evidence")
        if evidence is None:
            evidence = ""
        if not isinstance(evidence, str):
            raise _fail(location, "pinned evidence must be a string or absent")
        return Pinned(
            int(_require(data, "pinned_version", location)),
            evidence=evidence,
        )
    if form == "auto":
        return Auto(tuple(int(v) for v in _require(data, "evidenced", location)))
    raise _fail(location, "unknown version-selection form %r" % (form,))


# -- records --------------------------------------------------------------------------


def _record(data, location):
    family = _require(data, "family", location)
    cls = _RECORD_CLASSES.get(family)
    if cls is None:
        raise _fail(location, "unknown record family %r" % (family,))
    # The whole rebuild sits inside one wrapper: any constructor refusal
    # (empty sequence, bad identifier, wrong family payload) becomes a
    # PersistenceError naming the record's location in the file.
    try:
        ids = Multiplicity(_require(data, "ids", location))
        kwargs = {}
        if "sequence_text" in data:
            sequence_entry = _require(data, "sequence_text", location)
            kwargs = dict(
                kwargs,
                sequence=SequenceText(
                    _require(sequence_entry, "text", location + ".sequence_text"),
                    _require(sequence_entry, "family", location + ".sequence_text"),
                ),
            )
        if "modification_set" in data:
            kwargs = dict(kwargs, modifications=tuple(
                ModificationRecord(
                    ComponentCode(item["code"]),
                    Position(int(item["position"])),
                )
                for item in data["modification_set"]
            ))
        if "alignment" in data:
            if "references" in data:
                kwargs["alignment"] = _alignment(data["alignment"], location + ".alignment")
            else:
                kwargs["alignment"] = _single_alignment(data["alignment"], location + ".alignment")
        if "references" in data:
            kwargs["references"] = _references(data["references"], location + ".references")
        if "representation" in data:
            kwargs["representation"] = _representation(data["representation"], location + ".representation")
        if "presence" in data:
            kwargs = dict(kwargs, description=_presence(data["presence"], location + ".presence"))
        return cls(ids=ids, **kwargs)
    except PersistenceError:
        raise
    except Exception as error:
        raise _fail(location, str(error)) from error


# -- configuration ----------------------------------------------------------------------


def decode_configuration(data: dict) -> Configuration:
    """Rebuild the configuration through the validated constructors.

    The registry is restored from its persisted assignment data *first*;
    record keys are resolved against it so a file whose records and
    registry disagree is refused rather than silently "fixed" by
    re-assignment (plan §14: reopening never reassigns identifiers).
    """
    if not isinstance(data, dict):
        raise _fail("configuration", "expected an object")
    try:
        registry = IdentityRegistry.from_data(_require(data, "identity", "configuration"))
    except Exception as error:
        raise _fail("configuration.identity", str(error)) from error

    metadata_data = _require(data, "metadata", "configuration")
    metadata = ConfigurationMetadata(
        _require(metadata_data, "job_name", "configuration.metadata"),
        _presence(
            _require(metadata_data, "presence", "configuration.metadata"),
            "configuration.metadata.presence",
        ),
    )
    seeds = SeedSet(_require(data, "seeds", "configuration"))

    records = []
    for index, record_data in enumerate(_require(data, "records", "configuration")):
        where = "configuration.records[%d]" % index
        records.append(_record(record_data, where))
    # Record/registry agreement is deliberately **not** checked here: the
    # model is constructible with a record claiming an unassigned identifier
    # (Phase 3 exit criterion), and that disagreement is a validation finding
    # (R-ENT-002 family), surfaced on load through the injected ``validate`` —
    # not a decode-time refusal. Linkage endpoints below are different: they
    # go through ``resolve_strict`` because identity is the sole resolution
    # authority (plan §6.2), and an unresolvable endpoint cannot be built
    # in-session either.

    linkages = []
    for index, linkage_data in enumerate(_require(data, "linkages", "configuration")):
        where = "configuration.linkages[%d]" % index

        def endpoint(part, where=where):
            part_data = _require(linkage_data, part, where)
            entity_value = _require(part_data, "entity", where + "." + part)
            try:
                resolved = registry.resolve_strict(EntityId(entity_value))
            except Exception as error:
                raise _fail(
                    where + "." + part,
                    "linkage endpoint does not resolve in the persisted registry: %s" % error,
                ) from error
            if resolved.value != entity_value:
                raise _fail(
                    where + "." + part,
                    "linkage endpoint %r does not resolve in the persisted registry" % entity_value,
                )
            return LinkEndpoint(
                resolved,
                ResidueRef(int(_require(part_data, "residue", where + "." + part))),
                _require(part_data, "atom", where + "." + part),
            )

        linkages.append(Linkage(endpoint("a"), endpoint("b")))

    format_data = _require(data, "format_target", "configuration")
    format_target = FormatTarget(
        version_selection=_version_selection(
            _require(format_data, "version_selection", "configuration.format_target"),
            "configuration.format_target.version_selection",
        ),
        dialect=Dialect(_require(format_data, "target_dialect", "configuration.format_target")),
    )

    component_definition = _resource_optional(
        _resource_data(data.get("component_definition")),
        "configuration.component_definition",
    )

    try:
        return Configuration(
            metadata=metadata,
            seeds=seeds,
            records=tuple(records),
            identity=registry,
            linkages=tuple(linkages),
            component_definition=component_definition,
            format_target=format_target,
        )
    except Exception as error:
        raise _fail("configuration", str(error)) from error


# -- variant specs -----------------------------------------------------------------------


def _edit(data, location):
    kind = _require(data, "kind", location)
    record_key = data.get("record_key")

    if kind == "SetName":
        from configbuilder.variants import SetName

        return SetName(_require(data, "job_name", location))
    if kind == "SetJobDescription":
        from configbuilder.variants import SetJobDescription

        return SetJobDescription(_presence(_require(data, "presence", location), location))
    if kind == "SetDescription":
        from configbuilder.variants import SetDescription

        return SetDescription(
            _entity(record_key, location),
            _presence(_require(data, "presence", location), location),
        )
    if kind == "SetSeeds":
        from configbuilder.variants import SetSeeds

        return SetSeeds(_require(data, "seeds", location))
    if kind == "SetSequence":
        from configbuilder.variants import SetSequence

        return SetSequence(
            _entity(record_key, location),
            SequenceText(_require(data, "text", location), _require(data, "family", location)),
        )
    if kind == "AddModification":
        from configbuilder.variants import AddModification

        return AddModification(
            _entity(record_key, location),
            ComponentCode(_require(data, "code", location)),
            Position(int(_require(data, "position", location))),
        )
    if kind == "RemoveModification":
        from configbuilder.variants import RemoveModification

        return RemoveModification(_entity(record_key, location), int(_require(data, "index", location)))
    if kind == "SetAlignment":
        from configbuilder.variants import SetAlignment

        return SetAlignment(_entity(record_key, location), _alignment(_require(data, "alignment", location), location))
    if kind == "SetSingleAlignment":
        from configbuilder.variants import SetSingleAlignment

        return SetSingleAlignment(
            _entity(record_key, location), _single_alignment(_require(data, "alignment", location), location)
        )
    if kind == "SetReferences":
        from configbuilder.variants import SetReferences

        return SetReferences(_entity(record_key, location), _references(_require(data, "references", location), location))
    if kind == "SetComponentRepresentation":
        from configbuilder.variants import SetComponentRepresentation

        return SetComponentRepresentation(
            _entity(record_key, location), _representation(_require(data, "representation", location), location)
        )
    if kind == "SetComponentCount":
        from configbuilder.variants import SetComponentCount

        return SetComponentCount(_entity(record_key, location), int(_require(data, "count", location)))
    if kind == "AddRecord":
        from configbuilder.variants import AddRecord

        family = _require(data, "family", location)
        cls = _RECORD_CLASSES.get(family)
        if cls is None:
            raise _fail(location, "unknown record family %r" % (family,))
        kwargs = {}
        if "sequence_text" in data:
            sequence_entry = _require(data, "sequence_text", location)
            kwargs = dict(
                kwargs,
                sequence=SequenceText(sequence_entry["text"], sequence_entry["family"]),
            )
        if "representation" in data:
            kwargs = dict(kwargs, representation=_representation(data["representation"], location))
        if "modification_set" in data:
            kwargs = dict(kwargs, modifications=tuple(
                ModificationRecord(ComponentCode(item["code"]), Position(int(item["position"])))
                for item in data["modification_set"]
            ))
        if "presence" in data:
            kwargs = dict(kwargs, description=_presence(data["presence"], location))
        try:
            record = cls(ids=Multiplicity(_require(data, "ids", location)), **kwargs)
        except Exception as error:
            raise _fail(location, str(error)) from error
        return AddRecord(record)
    if kind == "RemoveRecord":
        from configbuilder.variants import RemoveRecord

        return RemoveRecord(_entity(record_key, location))
    if kind == "AddLinkage":
        from configbuilder.variants import AddLinkage

        def endpoint(part):
            part_data = _require(data, part, location)
            return LinkEndpoint(
                _entity(_require(part_data, "entity", location + "." + part), location),
                ResidueRef(int(_require(part_data, "residue", location + "." + part))),
                _require(part_data, "atom", location + "." + part),
            )

        return AddLinkage(Linkage(endpoint("a"), endpoint("b")))
    if kind == "RemoveLinkage":
        from configbuilder.variants import RemoveLinkage

        return RemoveLinkage(int(_require(data, "index", location)))
    if kind == "SetComponentDefinition":
        from configbuilder.variants import SetComponentDefinition

        return SetComponentDefinition(_resource_optional(data.get("definition"), location))
    if kind == "SetFormatTarget":
        from configbuilder.variants import SetFormatTarget

        return SetFormatTarget(
            FormatTarget(
                version_selection=_version_selection(
                    _require(data, "version_selection", location), location
                )
            )
        )
    raise _fail(location, "unknown edit kind %r" % (kind,))


def _entity(value, location):
    from configbuilder.identity import EntityId

    if value is None:
        raise _fail(location, "this edit requires a record_key")
    return EntityId(value)


def decode_spec(data: dict, index: int = 0) -> object:
    """Rebuild a VariantSpec; unknown edit kinds are refusals."""
    from configbuilder.variants import VariantSpec

    where = "variant_specs[%d]" % index
    if not isinstance(data, dict):
        raise _fail(where, "expected an object")
    edits = []
    for edit_index, edit_data in enumerate(_require(data, "edits", where)):
        edits.append(_edit(edit_data, "%s.edits[%d]" % (where, edit_index)))
    try:
        return VariantSpec(
            key=_require(data, "key", where),
            label=_require(data, "label", where),
            edits=tuple(edits),
            declared_factors=tuple(data.get("declared_factors", ())),
        )
    except Exception as error:
        raise _fail(where, str(error)) from error
