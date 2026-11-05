"""MSA rule checks (spec §19 "MSA validation", spec §6.2).

One-sided alignment cases are legal wire states (spec §6.2 names them);
the half-set *absent-versus-empty* confusion the contract forbids is
unrepresentable in the model's sum type, so R-MSA-001/R-MSA-002 re-affirm
dispatchability rather than reject named cases.
"""

from __future__ import annotations

from configbuilder.model import (
    AlignmentAutomatic,
    AlignmentBoth,
    AlignmentFree,
    AlignmentPairedOnly,
    AlignmentUnpairedOnly,
    Configuration,
    External,
    FamilyARecord,
    FamilyBRecord,
    Inline,
    SingleProvided,
)
from configbuilder.validation.catalogue import Rule, Severity
from configbuilder.validation.report import FieldPath, Finding, Report


def _add(
    report: Report,
    rule: Rule,
    user_message: str,
    diagnostic: str,
    paths=(),
    suggestion: str = "",
    severity=None,
) -> None:
    report.add(
        Finding(
            rule_id=rule.rule_id,
            severity=severity if severity is not None else rule.severity,
            user_message=user_message,
            diagnostic=diagnostic,
            paths=paths,
            suggestion=suggestion,
        )
    )


def _protein_records(configuration: Configuration):
    return [r for r in configuration.records if isinstance(r, FamilyARecord)]


def _rna_records(configuration: Configuration):
    return [r for r in configuration.records if isinstance(r, FamilyBRecord)]


def _record_key(configuration: Configuration, record) -> str:
    try:
        return record.ids.primary.value
    except Exception:
        return "<record>"


def check_r_msa_001(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Protein unpaired/paired fields are both set or both unset — the four
    legal states of spec §6.2; the sum type admits exactly those."""
    for record in _protein_records(configuration):
        key = _record_key(configuration, record)
        if not isinstance(record.alignment, (AlignmentAutomatic, AlignmentFree, AlignmentUnpairedOnly, AlignmentPairedOnly, AlignmentBoth)):
            _add(
                report,
                rule,
                "The protein MSA state of record %r is not one of the four contract states." % key,
                "alignment type %r" % type(record.alignment).__name__,
                (FieldPath("FamilyARecord", key, "unpairedMsa"),),
            )


def check_r_msa_002(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Inline and path are mutually exclusive per MSA field: each one-sided
    case carries exactly one resource; assert it stays that way."""
    for record in _protein_records(configuration) + _rna_records(configuration):
        key = _record_key(configuration, record)
        if isinstance(record.alignment, (AlignmentUnpairedOnly, AlignmentPairedOnly, AlignmentBoth)):
            source = record.alignment.source
            if not isinstance(source, (Inline, External)):
                _add(
                    report,
                    rule,
                    "A custom MSA must be either inline text or a file path, not both or neither.",
                    "source type %r on record %r" % (type(source).__name__, key),
                    (FieldPath("Inline", key, "unpairedMsa"),),
                )


def _first_sequence(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(">"):
            return stripped
    return ""


def _custom_sources(alignment):
    """Every user-supplied MSA resource in one alignment state.

    Protein one-sided and both-sided states carry their sources directly;
    an RNA ``provided`` state carries one the same way, so the resource
    rules below see every explicitly configured file regardless of family.
    """
    if isinstance(alignment, AlignmentBoth):
        return (alignment.source, alignment.paired_source)
    if isinstance(alignment, (AlignmentUnpairedOnly, AlignmentPairedOnly)):
        return (alignment.source,)
    if isinstance(alignment, SingleProvided):
        return (alignment.source,)
    return ()


def check_r_msa_003(configuration: Configuration, report: Report, rule: Rule, context=None) -> None:
    """Custom MSA *content* is required to be A3M — shallow check: every line
    is either a FASTA header or an A3M-alphabet sequence line. Advisory
    (WARNING by evidence DOCUMENTED); the external system owns deep
    interpretation (plan §9.2).

    Inline text is the only content this rule can see: a file-backed source
    carries no text in the model and the filesystem port answers existence
    questions only, so R-MSA-006 owns configured files. Both sides of an
    AlignmentBoth are checked: they may carry different inline text.
    """
    for record in _protein_records(configuration) + _rna_records(configuration):
        key = _record_key(configuration, record)

        def visit(source, key=key):
            if isinstance(source, Inline):
                content = source.text
                for line_no, line in enumerate(content.splitlines(), start=1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith(">"):
                        continue
                    if any(ch not in "ABCDEFGHIKLMNPQRSTUVWXYZacgustwykmedbzx-" for ch in stripped):
                        _add(
                            report,
                            rule,
                            "The custom MSA of record %r contains characters outside the A3M alphabet on line %d." % (key, line_no),
                            "line %d: %r" % (line_no, stripped[:40]),
                            (FieldPath("Inline", key, "unpairedMsa"),),
                        )

        for source in _custom_sources(record.alignment):
            visit(source)


def check_r_msa_004(configuration: Configuration, report: Report, rule: Rule) -> None:
    """The first sequence of a custom MSA should equal the query sequence —
    shallow, advisory. Inline sources are checked; file-backed sources are
    reported as not readable here (the engine's preflight pass handles
    files) so this check stays filesystem-free."""
    for record in _protein_records(configuration) + _rna_records(configuration):
        key = _record_key(configuration, record)
        query = record.sequence.text
        for source in _custom_sources(record.alignment):
            if isinstance(source, Inline):
                first = _first_sequence(source.text)
                if first and first.replace("-", "") != query:
                    _add(
                        report,
                        rule,
                        "The first sequence of the custom MSA should match the query sequence of record %r." % key,
                        "first MSA sequence %r does not match query %r" % (first[:40], query[:40]),
                        (FieldPath("Inline", key, "unpairedMsa"),),
                        suggestion="Check that the MSA's first entry is the query itself.",
                    )


def check_r_msa_005(configuration: Configuration, report: Report, rule: Rule) -> None:
    """After removing lowercase insertions, a custom MSA should form a
    rectangular alignment — shallow, advisory, inline sources only."""
    for record in _protein_records(configuration) + _rna_records(configuration):
        key = _record_key(configuration, record)
        for source in _custom_sources(record.alignment):
            if isinstance(source, Inline):
                widths = set()
                for line in source.text.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith(">"):
                        continue
                    aligned = "".join(ch for ch in stripped if not ch.islower())
                    widths.add(len(aligned))
                if len(widths) > 1:
                    _add(
                        report,
                        rule,
                        "The custom MSA of record %r is not rectangular after removing lowercase insertions." % key,
                        "aligned row widths differ: %s" % sorted(widths),
                        (FieldPath("Inline", key, "unpairedMsa"),),
                        suggestion="Pad all aligned sequences to the same length with gap characters.",
                    )


def check_r_msa_006(configuration: Configuration, report: Report, rule: Rule, context=None) -> None:
    """Every configured external MSA file is a usable local file.

    ``Automatic`` and ``Free`` configure no file, so they are never reported
    here: the deployment searches for an MSA, and demanding a path would
    refuse the most common configuration. A source-carrying state
    (``unpaired`` / ``paired`` / ``both`` / RNA ``provided``) does name a
    file, and the input is not ready while that file cannot be read — the
    export points at it, and the copy step would fail later anyway.

    Shallow by design (plan §9.2/§9.5): the filesystem port answers
    exists / regular file / readable / non-empty and nothing is parsed. With
    no port the rule reports "not checked" as a WARNING instead of inventing
    an error (plan §9.6).
    """
    from configbuilder.validation.ports import NullFilesystemPort

    filesystem = getattr(context, "filesystem", None) if context is not None else None
    unavailable = filesystem is None or isinstance(filesystem, NullFilesystemPort)
    for record in _protein_records(configuration) + _rna_records(configuration):
        key = _record_key(configuration, record)
        seen = set()
        for source in _custom_sources(record.alignment):
            if not isinstance(source, External):
                continue
            raw_path = source.path.raw
            if raw_path in seen:
                # One file feeding both sides of ``both`` is one resource.
                continue
            seen.add(raw_path)
            if unavailable:
                _add(
                    report,
                    rule,
                    "The MSA file of record %r could not be checked here (no filesystem access)." % key,
                    "path %r; filesystem port unavailable" % raw_path,
                    (FieldPath("External", key, "unpairedMsa"),),
                    severity=Severity.WARNING,
                )
            elif not filesystem.is_readable_file(raw_path):
                _add(
                    report,
                    rule,
                    "The MSA file of record %r is not usable: %r is missing, empty, "
                    "unreadable, or not a regular file." % (key, raw_path),
                    "path %r failed the readable non-empty regular-file check" % raw_path,
                    (FieldPath("External", key, "unpairedMsa"),),
                    suggestion=(
                        "Correct the path in the record's alignment settings, or write "
                        "the file before saving; automatic search and no-MSA states "
                        "need no file."
                    ),
                )
