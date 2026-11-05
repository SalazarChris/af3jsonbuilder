"""Entity rule checks (spec §19 "Entity validation").

Sequence alphabets, ligand representations, and cross-record uniqueness.
Position-within-sequence is R-ENT-007 (relational); family membership of
records is already guaranteed by the model's separate family types, so
R-ENT-001 re-affirms it structurally.
"""

from __future__ import annotations

from configbuilder.model import (
    ByCode,
    ByNotation,
    ComponentRecord,
    Configuration,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    is_d_code,
    residue_for_d_code,
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
    """The registry key naming this record: its primary entity ID."""
    try:
        return record.ids.primary.value
    except Exception:
        return "<record>"


def check_r_ent_001(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Entity families are exactly protein/RNA/DNA/ligand: re-affirmed by
    type membership of the four families."""
    for record in configuration.records:
        if not isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord, ComponentRecord)):
            _add(
                report,
                rule,
                "Every entity must be a protein, RNA, DNA, or ligand record.",
                "record of unexpected type %r" % type(record).__name__,
                (FieldPath("Record"),),
            )


def check_r_ent_002(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Entity IDs are unique across the input including copy multiplicity.

    This is the DuplicateIdError conversion point (CHECKLIST.md Phase 4):
    the registry raises DuplicateIdError for an explicit taken-ID
    assignment; the engine catches it here and converts it to a finding —
    the registry never silently renames, and raw identity exceptions never
    reach the UI.
    """
    registry = configuration.identity
    seen = {}
    for record in configuration.records:
        for entity_id in record.ids:
            if entity_id.value in seen:
                _add(
                    report,
                    rule,
                    "Entity identifier %r is used more than once; every copy needs its own ID."
                    % entity_id.value,
                    "identifier %r appears in records %r and %r"
                    % (entity_id.value, seen[entity_id.value], record.ids),
                    (FieldPath("EntityId", entity_id.value, "id"),),
                    suggestion="Rename one of the records so every identifier is unique.",
                )
            else:
                seen[entity_id.value] = record.ids
    # Also surface registry-level duplicate refusals that occurred during
    # interactive construction (e.g. a front end called assign() and was
    # refused): they are converted at this boundary per plan §8.1.
    for value in sorted(getattr(registry, "_pending_duplicate_refusals", ())):
        _add(
            report,
            rule,
            "Entity identifier %r is already in use; it must be changed, not reused." % value,
            "registry refused a duplicate assignment of %r" % value,
            (FieldPath("EntityId", value, "id"),),
        )


def check_r_ent_003(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Entity IDs are uppercase alphabetic (already enforced by EntityId at
    construction; re-affirmed over every record)."""
    for record in configuration.records:
        for entity_id in record.ids:
            if not entity_id.value.isalpha() or not entity_id.value.isupper():
                _add(
                    report,
                    rule,
                    "Entity identifiers must be uppercase letters (A-Z).",
                    "identifier %r is not uppercase alphabetic" % entity_id.value,
                    (FieldPath("EntityId", entity_id.value, "id"),),
                )


def check_r_ent_004(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Protein sequence is one-letter amino-acid alphabetic."""
    for record in configuration.records:
        if isinstance(record, FamilyARecord):
            text = record.sequence.text
            if not text or not all(ch.isalpha() and ch.isupper() for ch in text):
                _add(
                    report,
                    rule,
                    "A protein sequence must contain only one-letter amino-acid codes (A-Z).",
                    "protein sequence of %r contains invalid characters" % _record_key(configuration, record),
                    (FieldPath("SequenceText", _record_key(configuration, record), "protein.sequence"),),
                )


def check_r_ent_005(configuration: Configuration, report: Report, rule: Rule) -> None:
    """RNA sequence uses A, C, G, U."""
    for record in configuration.records:
        if isinstance(record, FamilyBRecord):
            text = record.sequence.text
            if any(ch not in "ACGU" for ch in text):
                _add(
                    report,
                    rule,
                    "An RNA sequence may only contain A, C, G, and U.",
                    "RNA sequence of %r contains characters outside ACGU"
                    % _record_key(configuration, record),
                    (FieldPath("SequenceText", _record_key(configuration, record), "rna.sequence"),),
                )


def check_r_ent_006(configuration: Configuration, report: Report, rule: Rule) -> None:
    """DNA sequence uses A, C, G, T."""
    for record in configuration.records:
        if isinstance(record, FamilyCRecord):
            text = record.sequence.text
            if any(ch not in "ACGT" for ch in text):
                _add(
                    report,
                    rule,
                    "A DNA sequence may only contain A, C, G, and T.",
                    "DNA sequence of %r contains characters outside ACGT"
                    % _record_key(configuration, record),
                    (FieldPath("SequenceText", _record_key(configuration, record), "dna.sequence"),),
                )


def check_r_ent_007(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Modification positions lie within the parent sequence (1-based)."""
    for record in configuration.records:
        if isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord)):
            length = len(record.sequence)
            key = _record_key(configuration, record)
            for modification in record.modifications:
                if modification.position.value > length:
                    _add(
                        report,
                        rule,
                        "Modification at position %d lies beyond the end of the %d-residue sequence."
                        % (modification.position.value, length),
                        "position %d out of range for sequence of length %d on record %r"
                        % (modification.position.value, length, key),
                        (
                            FieldPath(
                                "ModificationRecord",
                                key,
                                "position[%d]" % modification.position.value,
                            ),
                        ),
                        suggestion="Choose a position between 1 and %d." % length,
                    )


def check_r_ent_008(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Modification codes must not carry the CCD_ prefix (spec §8.1)."""
    for record in configuration.records:
        if isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord)):
            key = _record_key(configuration, record)
            for modification in record.modifications:
                code = modification.code.value.upper()
                if code.startswith("CCD_"):
                    _add(
                        report,
                        rule,
                        "Modification codes must not start with 'CCD_'.",
                        "modification on record %r uses code %r" % (key, code),
                        (FieldPath("ComponentCode", key, "ptmType"),),
                        suggestion="Use the plain CCD identifier, e.g. %r." % code[4:],
                    )


def check_r_ent_009(configuration: Configuration, report: Report, rule: Rule) -> None:
    """A ligand has exactly one of CCD codes or SMILES: guaranteed by the
    ByCode/ByNotation sum type; re-affirmed over ComponentRecords."""
    for record in configuration.records:
        if isinstance(record, ComponentRecord):
            if not isinstance(record.representation, (ByCode, ByNotation)):
                _add(
                    report,
                    rule,
                    "A ligand needs exactly one of a component code or a SMILES string.",
                    "representation type %r" % type(record.representation).__name__,
                    (FieldPath("ComponentRecord", _record_key(configuration, record), "ligand"),),
                )


def check_r_ent_010(configuration: Configuration, report: Report, rule: Rule, context=None) -> None:
    """SMILES parses — with a probe: ERROR when it cannot; without one:
    WARNING 'not checked' (plan §9.6).

    A real checker may raise on malformed notation (a parser's normal way of
    saying "no"); that is reported as this rule's blocking finding naming the
    failure, never allowed to escape into the CLI or GUI. An input the
    checker could not parse is not vouched for, so the severity is the same
    as an explicit parse refusal.

    The probe decides only chemical *syntax*: a parseable SMILES string is
    not a promise that the ligand is accepted by the deployment (plan §9.2).
    A probe that can explain itself does: ``smiles_problem`` (optional — the
    bundled grammar probe has it) names the defect in the finding, so the
    user is told what to fix instead of only that something failed.
    """
    from configbuilder.validation.catalogue import Severity
    from configbuilder.validation.engine import ValidationContext
    from configbuilder.validation.ports import NullChemistryProbe

    probe = context.chemistry if isinstance(context, ValidationContext) else None
    available = probe is not None and not isinstance(probe, NullChemistryProbe)
    for record in configuration.records:
        if isinstance(record, ComponentRecord) and isinstance(record.representation, ByNotation):
            key = _record_key(configuration, record)
            smiles = record.representation.text
            if not available:
                # Probe-less runs report "not checked" as a WARNING — never
                # as an ERROR (plan §9.6).
                report.add(
                    Finding(
                        rule_id=rule.rule_id,
                        severity=Severity.WARNING,
                        user_message=(
                            "The SMILES notation of ligand %r was not checked: no chemistry checker is available."
                            % key
                        ),
                        diagnostic="SMILES text %r; probe unavailable" % smiles,
                        paths=(FieldPath("ByNotation", key, "smiles"),),
                        suggestion="Install a chemistry checker to have SMILES validated.",
                    )
                )
                continue
            try:
                parsed = probe.parses_smiles(smiles)
            except Exception as error:  # the checker is external code
                _add(
                    report,
                    rule,
                    "The SMILES notation of ligand %r could not be checked: the chemistry checker failed on it." % key,
                    "SMILES text %r raised %s: %s" % (smiles, type(error).__name__, error),
                    (FieldPath("ByNotation", key, "smiles"),),
                    suggestion="Correct the SMILES notation; the checker could not parse it.",
                )
                continue
            if not parsed:
                detail = _probe_detail(probe, smiles)
                _add(
                    report,
                    rule,
                    "The SMILES notation of ligand %r could not be parsed%s."
                    % (key, detail),
                    "SMILES text %r failed to parse%s" % (smiles, detail),
                    (FieldPath("ByNotation", key, "smiles"),),
                    suggestion="Correct the SMILES notation, or use a component code instead.",
                )


def check_r_ent_011(configuration: Configuration, report: Report, rule: Rule) -> None:
    """A D-form replaces exactly the canonical residue it is the D-form of.

    The check covers imported jobs too: a D component on a position whose
    residue is different (or on a non-protein chain, or on glycine) is not a
    representable residue replacement and blocks generation with this rule.
    An out-of-range position is R-ENT-007's finding, so this rule leaves it
    to that one and never reports the same defect twice.
    """
    for record in configuration.records:
        modifications = tuple(getattr(record, "modifications", ()) or ())
        d_modifications = [
            modification
            for modification in modifications
            if is_d_code(modification.code.value)
        ]
        if not d_modifications:
            continue
        key = _record_key(configuration, record)
        if not isinstance(record, FamilyARecord):
            for modification in d_modifications:
                _add(
                    report,
                    rule,
                    "D-amino-acid component %s can only replace a residue on a protein chain; %r carries it."
                    % (modification.code.value, key),
                    "D-form %s on non-protein record %r"
                    % (modification.code.value, key),
                    (
                        FieldPath(
                            "ModificationRecord",
                            key,
                            "ptmType[%d]" % modification.position.value,
                        ),
                    ),
                    suggestion="Use a protein chain, or remove the D-form from this entity.",
                )
            continue
        text = record.sequence.text
        for modification in d_modifications:
            position = modification.position.value
            if position > len(text):
                continue  # R-ENT-007 reports the position itself
            residue = text[position - 1]
            expected_residue = residue_for_d_code(modification.code.value)
            if residue == expected_residue:
                continue
            if residue == "G":
                message = (
                    "D-amino-acid component %s cannot replace glycine at position %d of chain %s: glycine is achiral and has no D-form."
                    % (modification.code.value, position, key)
                )
                suggestion = "Remove the D-form from this glycine position."
            else:
                message = (
                    "D-amino-acid component %s is the D-form of %s, but position %d of chain %s is %s."
                    % (
                        modification.code.value,
                        expected_residue,
                        position,
                        key,
                        residue,
                    )
                )
                suggestion = "Use the D-form that matches this residue, or change the position."
            _add(
                report,
                rule,
                message,
                "D-form %s at residue %s on record %r"
                % (modification.code.value, residue, key),
                (
                    FieldPath(
                        "ModificationRecord",
                        key,
                        "ptmType[%d]" % position,
                    ),
                ),
                suggestion=suggestion,
            )


def check_r_ent_012(configuration: Configuration, report: Report, rule: Rule) -> None:
    """At most one modification per polymer position.

    A D-amino acid *replaces* its residue, so two modifications at one
    position ask AF3 for two different components of the same residue at
    once. The position is reported once per extra modification, naming both
    codes, so the user can see which pair to resolve.
    """
    for record in configuration.records:
        if not isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord)):
            continue
        key = _record_key(configuration, record)
        seen = {}
        for modification in record.modifications:
            position = modification.position.value
            previous = seen.get(position)
            if previous is None:
                seen[position] = modification
                continue
            _add(
                report,
                rule,
                "Position %d of chain %s carries more than one modification (%s and %s)."
                % (position, key, previous.code.value, modification.code.value),
                "duplicate modification position %d on record %r" % (position, key),
                (
                    FieldPath(
                        "ModificationRecord", key, "position[%d]" % position
                    ),
                ),
                suggestion="Remove one of the modifications at this position.",
            )


def _probe_detail(probe, smiles: str) -> str:
    """The probe's own explanation, as a trailing clause (or nothing).

    Optional on purpose: a probe that only answers ``parses_smiles`` keeps
    working, and one that can say *why* is quoted. An explanation that raises
    is dropped rather than allowed to break the report.
    """
    explain = getattr(probe, "smiles_problem", None)
    if not callable(explain):
        return ""
    try:
        reason = explain(smiles)
    except Exception:
        return ""
    if not reason:
        return ""
    return ": %s" % reason
