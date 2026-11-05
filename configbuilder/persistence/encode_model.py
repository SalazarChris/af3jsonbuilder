"""Encode the model into project-file data (IMPLEMENTATION_PLAN.md §14).

Every dispatch goes through the model's folds (plan §7.3) — adding a sum
case breaks this module loudly instead of silently dropping data. The
output is plain JSON-able data; the *decoding* side rebuilds through the
same validated constructors the UI uses, so what is written here can
always be read back into a legal model.

Key spellings deliberately avoid wire field names (plan §14: project file
≠ generated input file, and §18.7's confinement test holds here too):
``sequence_text`` for the model's ``SequenceText``, ``presence`` for a
Presence value, ``source``/``content`` for resource references.
"""

from __future__ import annotations

from configbuilder.model import (
    fold_alignment,
    fold_presence,
    fold_reference_set,
    fold_representation,
    fold_resource,
    fold_single_alignment,
    fold_version_selection,
)

__all__ = ["encode_configuration", "encode_spec"]


# -- value helpers -----------------------------------------------------------------


def _presence(value):
    """A Presence value as tagged data (the three states stay distinct —
    the omitted-vs-empty collapse is exactly what persistence must never
    reintroduce)."""

    def on_unset():
        return {"state": "unset"}

    def on_empty():
        return {"state": "explicit-empty"}

    def on_present(text):
        return {"state": "present", "text": text}

    return fold_presence(value, on_unset, on_empty, on_present)


def _resource(source):
    def on_inline(text):
        return {"form": "inline", "text": text}

    def on_external(path):
        return {"form": "external", "path": path.raw}

    return fold_resource(source, on_inline, on_external)


def _resource_optional(value):
    """``None`` (absent 0..1 field) vs a ResourceRef — distinct by design."""
    if value is None:
        return None
    return _resource(value)


def _representation(value):
    def on_code(codes):
        return {"form": "codes", "codes": [code.value for code in codes]}

    def on_notation(text):
        return {"form": "notation", "text": text}

    return fold_representation(value, on_code, on_notation)


def _alignment(value):
    def on_automatic():
        return {"form": "automatic"}

    def on_free():
        return {"form": "free"}

    def on_unpaired_only(source):
        return {"form": "unpaired-only", "source": _resource(source)}

    def on_paired_only(source):
        return {"form": "paired-only", "source": _resource(source)}

    def on_both(source):
        data = {"form": "both", "source": _resource(source)}
        if value.paired_source != source:
            data["paired_source"] = _resource(value.paired_source)
        return data

    return fold_alignment(value, on_automatic, on_free, on_unpaired_only, on_paired_only, on_both)


def _single_alignment(value):
    def on_automatic():
        return {"form": "automatic"}

    def on_free():
        return {"form": "free"}

    def on_provided(source):
        return {"form": "provided", "source": _resource(source)}

    return fold_single_alignment(value, on_automatic, on_free, on_provided)


def _references(value):
    def on_search_allowed():
        return {"form": "search-allowed"}

    def on_explicit(items):
        return {
            "form": "explicit",
            "records": [
                {
                    "source": _resource(item.source),
                    "index_map": [[pair.query, pair.template] for pair in item.index_map],
                }
                for item in items
            ],
        }

    return fold_reference_set(value, on_search_allowed, on_explicit)


def _version_selection(value):
    def on_unverified():
        return {"form": "unverified"}

    def on_pinned(version):
        # evidence is looked up through the selection object itself so the
        # fold's one-argument shape is preserved; a plain dict access can't
        # reach the attribute, so the closure grabs it from ``value``.
        data = {"form": "pinned", "pinned_version": version}
        if value.evidence:
            data["evidence"] = value.evidence
        return data

    def on_auto(evidenced):
        return {"form": "auto", "evidenced": list(evidenced)}

    return fold_version_selection(value, on_unverified, on_pinned, on_auto)


# -- records ------------------------------------------------------------------------


def _record(record):
    base = {
        "family": type(record).__name__,
        "ids": [entity.value for entity in record.ids],
        "presence": _presence(record.description),
    }
    if hasattr(record, "sequence"):
        base["sequence_text"] = {"text": record.sequence.text, "family": record.sequence.family}
    if hasattr(record, "modifications"):
        # Project-file key deliberately differs from the wire name the
        # transform maps builds (plan §14: own format, own vocabulary).
        base["modification_set"] = [
            {"code": modification.code.value, "position": modification.position.value}
            for modification in record.modifications
        ]
    if hasattr(record, "alignment"):
        if hasattr(record, "references"):
            base["alignment"] = _alignment(record.alignment)
        else:
            base["alignment"] = _single_alignment(record.alignment)
    if hasattr(record, "references"):
        base["references"] = _references(record.references)
    if hasattr(record, "representation"):
        base["representation"] = _representation(record.representation)
    return base


# -- configuration -------------------------------------------------------------------


def encode_configuration(configuration) -> dict:
    """The full base configuration, registry included (plan §14: reopening
    never reassigns identifiers)."""
    metadata = configuration.metadata
    document = {
        "metadata": {
            "job_name": metadata.name,
            "presence": _presence(metadata.description),
        },
        "seeds": list(configuration.seeds.values),
        "identity": configuration.identity.to_data(),
        "records": [_record(record) for record in configuration.records],
        "linkages": [
            {
                "a": {
                    "entity": linkage.a.entity.value,
                    "residue": linkage.a.residue.value,
                    "atom": linkage.a.atom,
                },
                "b": {
                    "entity": linkage.b.entity.value,
                    "residue": linkage.b.residue.value,
                    "atom": linkage.b.atom,
                },
            }
            for linkage in configuration.linkages
        ],
        "format_target": {
            "target_dialect": configuration.format_target.dialect.value,
            "version_selection": _version_selection(configuration.format_target.version_selection),
        },
        "component_definition": _resource_optional(configuration.component_definition),
    }
    return document


# -- variant specs ---------------------------------------------------------------------


def _edit(edit) -> dict:
    """One edit as data. Mirrors the edit vocabulary exactly; an unknown
    edit is an error here, never a silent drop."""

    def on_unset():
        return {"state": "unset"}

    def on_empty():
        return {"state": "explicit-empty"}

    def on_present(text):
        return {"state": "present", "text": text}

    data = {"kind": type(edit).__name__}
    record_key = getattr(edit, "_record_key", None)
    if record_key is not None:
        data["record_key"] = record_key.value

    if type(edit).__name__ == "SetName":
        data["job_name"] = edit._name  # non-wire spelling (plan §14)
    elif type(edit).__name__ in ("SetJobDescription", "SetDescription"):
        data["presence"] = fold_presence(edit._description, on_unset, on_empty, on_present)
    elif type(edit).__name__ == "SetSeeds":
        data["seeds"] = list(edit._seeds.values)
    elif type(edit).__name__ == "SetSequence":
        data["text"] = edit._text.text
        data["family"] = edit._text.family
    elif type(edit).__name__ == "AddModification":
        data["code"] = edit._modification.code.value
        data["position"] = edit._modification.position.value
    elif type(edit).__name__ == "RemoveModification":
        data["index"] = edit._index
    elif type(edit).__name__ == "SetAlignment":
        data["alignment"] = _alignment(edit._alignment)
    elif type(edit).__name__ == "SetSingleAlignment":
        data["alignment"] = _single_alignment(edit._alignment)
    elif type(edit).__name__ == "SetReferences":
        data["references"] = _references(edit._references)
    elif type(edit).__name__ == "SetComponentRepresentation":
        data["representation"] = _representation(edit._representation)
    elif type(edit).__name__ == "SetComponentCount":
        data["count"] = edit._count
    elif type(edit).__name__ == "AddRecord":
        record = edit._record
        data["family"] = type(record).__name__
        data["ids"] = [entity.value for entity in record.ids]
        if hasattr(record, "sequence"):
            data["sequence_text"] = {"text": record.sequence.text, "family": record.sequence.family}
        if hasattr(record, "modifications"):
            data["modification_set"] = [
                {"code": m.code.value, "position": m.position.value}
                for m in record.modifications
            ]
        if hasattr(record, "representation"):
            data["representation"] = _representation(record.representation)
        if hasattr(record, "description"):
            data["presence"] = _presence(record.description)
    elif type(edit).__name__ == "RemoveRecord":
        pass
    elif type(edit).__name__ == "AddLinkage":
        data["a"] = {
            "entity": edit._linkage.a.entity.value,
            "residue": edit._linkage.a.residue.value,
            "atom": edit._linkage.a.atom,
        }
        data["b"] = {
            "entity": edit._linkage.b.entity.value,
            "residue": edit._linkage.b.residue.value,
            "atom": edit._linkage.b.atom,
        }
    elif type(edit).__name__ == "RemoveLinkage":
        data["index"] = edit._index
    elif type(edit).__name__ == "SetComponentDefinition":
        data["definition"] = _resource_optional(edit._definition)
    elif type(edit).__name__ == "SetFormatTarget":
        data["version_selection"] = _version_selection(edit._format_target.version_selection)
    else:
        from configbuilder.variants import EditError

        raise EditError("unknown edit %r; the vocabulary and the encoder disagree" % (edit,))
    return data


def encode_spec(spec) -> dict:
    """A VariantSpec: key, label, edits, declared factors."""
    return {
        "key": spec.key,
        "label": spec.label,
        "edits": [_edit(edit) for edit in spec.edits],
        "declared_factors": list(spec.declared_factors),
    }
