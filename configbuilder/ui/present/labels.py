"""Labels (plan §5.3 rule 6, §16.1, §18.8 formatting tier).

Every user-visible label resolves through the model's traceability
registry — the single translation point between neutral internal names
and human-facing wording (plan §3). Nothing here hard-codes a label; a
string that is neither registry wording nor rule message wording is a
defect the meta-test catches.

This module imports ``model.traceability`` only: ``ui`` may import
``app`` and ``model.traceability`` (plan §5.3 rule 6), and ``present``
is the family whose whole job is label resolution.
"""

from __future__ import annotations

from configbuilder.model.traceability import label_for, mapping_ids_for
from configbuilder.ui.present.strings import text as _text

__all__ = [
    "label",
    "labels",
    "mapping_ids",
    "with_record_label",
    "finding_context_label",
    "finding_reference_label",
    "severity_label",
    "action_description",
    "general_finding_context",
    "SEVERITY_SYMBOLS",
]


def label(type_name: str) -> str:
    """The registry label for an internal type name.

    Unregistered names raise — the UI never falls back to a raw
    internal name (plan §3.1); ``FieldPath`` already refuses to carry
    one, so this only fires for a programming error here.
    """
    return label_for(type_name)


def labels(type_names) -> tuple:
    """Labels for a sequence of type names, in order."""
    return tuple(label_for(name) for name in type_names)


def mapping_ids(type_name: str) -> tuple:
    """The mapping IDs a type's label traces to (for the inspector and
    diagnostics where traceability is shown alongside the wording)."""
    return mapping_ids_for(type_name)


def with_record_label(type_name: str, record_key) -> str:
    """The context label for a finding pointed at a specific record.

    The registry vocabulary plus the chain identifier the registry
    itself allocated — no internal class names (plan §16.6)."""
    base = label_for(type_name)
    if record_key is None:
        return base
    return "%s %s" % (base, record_key)


def finding_context_label(field_path) -> str:
    """The context line for a ``FieldPath`` locator, entirely in
    registry vocabulary: ``"Protein chain A"`` or ``"Job details"``."""
    return with_record_label(field_path.type_name, field_path.record_key)


# Severity is always a word AND a symbol (plan §16.6: meaning survives
# without colour). Both are printed on every finding card.
SEVERITY_SYMBOLS = {"ERROR": "[x]", "WARNING": "[!]", "INFO": "[i]"}

# The plan's exact card tokens: "ERROR  [x]", "WARNING [!]", "INFO [i]".
_SEVERITY_FORMATS = {"ERROR": "%s  %s"}


def severity_label(severity) -> str:
    """``"ERROR  [x]"``-style severity rendering: word, then symbol."""
    name = severity.name if hasattr(severity, "name") else str(severity)
    symbol = SEVERITY_SYMBOLS.get(name, "[?]")
    fmt = _SEVERITY_FORMATS.get(name, "%s %s")
    return fmt % (name, symbol)


def finding_reference_label(number: int, severity, field_path) -> str:
    """The reference line of a jump-to-field finding card:
    ``"3. ERROR [x] — Protein chain A"`` (plan §16.6). The number is the
    token the user types; the wording is registry vocabulary only."""
    return _text("jump.reference") % (
        number,
        severity_label(severity),
        finding_context_label(field_path),
    )


def action_description(description_key: str) -> str:
    """An action's wording, from the string registry (the traceability
    registry is for domain *types*, not chrome)."""
    return _text(description_key)


def general_finding_context() -> str:
    """The group header for findings without a locator."""
    return _text("finding.context.general")
