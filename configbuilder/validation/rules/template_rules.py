"""Template rule checks (spec §19 "Template validation", spec §12)."""

from __future__ import annotations

from configbuilder.model import (
    Configuration,
    Explicit,
    FamilyARecord,
)
from configbuilder.validation.catalogue import Rule
from configbuilder.validation.report import FieldPath, Finding, Report


def _add(report: Report, rule: Rule, user_message: str, diagnostic: str, paths=(), suggestion: str = "") -> None:
    report.add(
        Finding(
            rule_id=rule.rule_id,
            severity=rule.severity,
            user_message=user_message,
            diagnostic=diagnostic,
            paths=paths,
            suggestion=suggestion,
        )
    )


def _record_key(configuration: Configuration, record) -> str:
    try:
        return record.ids.primary.value
    except Exception:
        return "<record>"


def _explicit_templates(record: FamilyARecord):
    """Explicit reference set for a record, or None when search is allowed."""
    if isinstance(record.references, Explicit):
        return record.references
    return None


def check_r_tpl_001(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Templates are supported only on protein chains. RNA (FamilyB) carries
    no reference field at all, and DNA (FamilyC) neither — structurally
    guaranteed. Re-affirm: no non-protein record exposes templates."""
    for record in configuration.records:
        if not isinstance(record, FamilyARecord):
            key = _record_key(configuration, record)
            if hasattr(record, "references"):
                _add(
                    report,
                    rule,
                    "Templates are only supported on protein chains.",
                    "record %r of type %r carries templates" % (key, type(record).__name__),
                    (FieldPath("ReferenceRecord", key, "templates"),),
                )


def check_r_tpl_002(configuration: Configuration, report: Report, rule: Rule) -> None:
    """mmcif and mmcifPath mutually exclusive per template: each reference
    holds exactly one resource — the Inline/External sum guarantees it."""
    for record in _protein_records(configuration):
        key = _record_key(configuration, record)
        explicit = _explicit_templates(record)
        if explicit is None:
            continue
        for index, template in enumerate(explicit.items):
            source = template.source
            if not hasattr(source, "text") and not hasattr(source, "path"):
                _add(
                    report,
                    rule,
                    "Each template must be either inline mmCIF or a file path, not both or neither.",
                    "template %d on record %r has source type %r" % (index, key, type(source).__name__),
                    (FieldPath("ReferenceRecord", key, "templates[%d]" % index),),
                )


def _protein_records(configuration: Configuration):
    return [r for r in configuration.records if isinstance(r, FamilyARecord)]


def check_r_tpl_003(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Query/template indices are 0-based and never arithmetic-adjusted:
    every IndexPair is stored as given; re-affirm non-negativity."""
    for record in _protein_records(configuration):
        key = _record_key(configuration, record)
        explicit = _explicit_templates(record)
        if explicit is None:
            continue
        for index, template in enumerate(explicit.items):
            for pair_index, pair in enumerate(template.index_map):
                if pair.query < 0 or pair.template < 0:
                    _add(
                        report,
                        rule,
                        "Template mapping indices are 0-based and must not be negative.",
                        "template %d, pair %d on record %r is (%d, %d)"
                        % (index, pair_index, key, pair.query, pair.template),
                        (FieldPath("IndexPair", key, "queryIndices[%d]" % pair_index),),
                    )


def check_r_tpl_004(configuration: Configuration, report: Report, rule: Rule) -> None:
    """The template index mapping is parallel by construction (IndexPair);
    re-affirm equal pairing — the model cannot store unequal arrays."""
    for record in _protein_records(configuration):
        key = _record_key(configuration, record)
        explicit = _explicit_templates(record)
        if explicit is None:
            continue
        for index, template in enumerate(explicit.items):
            for pair_index, pair in enumerate(template.index_map):
                if pair.query is None or pair.template is None:
                    _add(
                        report,
                        rule,
                        "Every template mapping entry needs both a query and a template index.",
                        "template %d, pair %d on record %r is incomplete" % (index, pair_index, key),
                        (FieldPath("IndexPair", key, "queryIndices[%d]" % pair_index),),
                    )


def check_r_tpl_005(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Up to 20 templates per protein chain."""
    LIMIT = 20
    for record in _protein_records(configuration):
        key = _record_key(configuration, record)
        explicit = _explicit_templates(record)
        if explicit is None:
            continue
        if len(explicit.items) > LIMIT:
            _add(
                report,
                rule,
                "At most %d templates are supported per protein chain." % LIMIT,
                "record %r carries %d templates" % (key, len(explicit.items)),
                (FieldPath("ReferenceSet", key, "templates"),),
                suggestion="Remove excess templates or merge them.",
            )
