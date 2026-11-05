"""Ligand / bond rule checks (spec §19 "Ligand / bond validation", spec §13)."""

from __future__ import annotations

import re

from configbuilder.model import (
    ByNotation,
    ComponentRecord,
    Configuration,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    fold_representation,
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


def _records_by_id(configuration: Configuration):
    """Primary-ID -> record map for endpoint resolution."""
    result = {}
    for record in configuration.records:
        key = _record_key(configuration, record)
        result.setdefault(key, record)
        for entity_id in record.ids:
            result.setdefault(entity_id.value, record)
    return result


# The periodic table, in its standard capitalisation. A SMILES whose whole
# text is one of these symbols denotes a single bare element, and a *charged*
# or bracketed single-atom form denotes an ion — both are CCD-coded ligands in
# this contract, never SMILES (spec §9, MAP-204).
_ELEMENT_SYMBOLS = frozenset(
    """
    H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co
    Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb
    Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re
    Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es
    Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og
    """.split()
)

# A charge suffix in either written order: ``+2`` and ``2+`` are both seen.
_CHARGE = r"(?:[+-]\d*|\d*[+-])"
# A bracketed single atom: [Na+], [Mg+2], [Cl-], [Fe].
_BRACKETED_ION = re.compile(r"^\[([A-Z][a-z]?)(?:%s)?\]$" % _CHARGE)
# A bare charged atom: Na+, Cl-, Mg2+, Mg+2.
_CHARGED_ATOM = re.compile(r"^([A-Z][a-z]?)(?:%s)$" % _CHARGE)
# A bare two-letter element symbol: Na, Mg, Zn, Cl — never a molecule.
_BARE_ELEMENT = re.compile(r"^([A-Z][a-z])$")


def _bare_ion_symbol(notation: str):
    """The element symbol when ``notation`` denotes a bare element or ion
    (``Na``, ``Na+``, ``[Mg+2]``); ``None`` for anything else.

    Only *unambiguous* notations count, so ordinary small molecules are never
    reported as ions: the symbol must be a real element in its standard
    capitalisation, and a single letter is left alone because ``C``/``N``/
    ``O``… are plain SMILES atoms. ``CCO``, ``CO``, ``CC`` and ``CN`` are
    small molecules, not ions, and are never flagged.
    """
    text = notation.strip()
    for pattern in (_BRACKETED_ION, _CHARGED_ATOM, _BARE_ELEMENT):
        match = pattern.match(text)
        if match is not None and match.group(1) in _ELEMENT_SYMBOLS:
            return match.group(1)
    return None


def check_r_bnd_001(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Ions are ligands with a CCD code: the model has no ion entity type;
    every ion-as-ligand ComponentRecord must use ByCode (CCD), not SMILES."""
    for record in configuration.records:
        if isinstance(record, ComponentRecord) and isinstance(record.representation, ByNotation):
            key = _record_key(configuration, record)
            notation = record.representation.text
            symbol = _bare_ion_symbol(notation)
            if symbol is not None:
                _add(
                    report,
                    rule,
                    "The ligand is written as the bare element or ion %r in SMILES form; "
                    "ions are CCD-coded ligands in this contract." % notation.strip(),
                    "SMILES %r names the single element %s" % (notation.strip(), symbol),
                    (FieldPath("ByNotation", key, "smiles"),),
                    suggestion="Use the CCD component code for %s instead, e.g. %r."
                    % (symbol, symbol.upper()),
                )


def check_r_bnd_002(configuration: Configuration, report: Report, rule: Rule) -> None:
    """A SMILES-only ligand cannot be a bond endpoint (MAP-807)."""
    by_id = _records_by_id(configuration)
    for linkage in configuration.linkages:
        for endpoint in (linkage.a, linkage.b):
            record = by_id.get(endpoint.entity.value)
            if isinstance(record, ComponentRecord) and isinstance(record.representation, ByNotation):
                key = _record_key(configuration, record)
                _add(
                    report,
                    rule,
                    "A SMILES-only ligand cannot take part in an explicit bond.",
                    "endpoint %r (residue %d, atom %r) belongs to SMILES ligand %r"
                    % (endpoint.entity.value, endpoint.residue.value, endpoint.atom, key),
                    (FieldPath("LinkEndpoint", endpoint.entity.value, "bond"),),
                    suggestion="Represent the ligand by CCD code to bond it explicitly.",
                )


def _ligand_residue_count(representation) -> int:
    """How many residues one ligand record stands for.

    AF3 numbers a ligand's residues one per CCD code -- ``Ligand.__len__`` in
    ``alphafold3.common.folding_input`` is ``len(ccd_ids)`` -- which is what
    makes a multi-CCD glycan addressable. The official
    ``examples/rnaseb_glycosylated.json`` bonds residues 1..5 of a five-code
    ligand for exactly that reason. A SMILES ligand is a single residue (and
    cannot be a bond endpoint at all -- R-BND-002).
    """
    return fold_representation(
        representation,
        on_code=lambda codes: len(codes),
        on_notation=lambda _text: 1,
    )


def check_r_bnd_003(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Bond endpoints resolve to entity/residue/atom triples: the entity ID
    must resolve through identity, the residue must be 1-based within the
    target (for polymers: within sequence length; for ligands: within the
    number of CCD components, which is 1 for a single-code ligand)."""
    registry = configuration.identity
    by_id = _records_by_id(configuration)
    for linkage in configuration.linkages:
        for endpoint in (linkage.a, linkage.b):
            if not registry.resolve(endpoint.entity):
                _add(
                    report,
                    rule,
                    "Bond endpoint %r does not resolve to any entity in the input." % endpoint.entity.value,
                    "entity %r, residue %d, atom %r unresolved"
                    % (endpoint.entity.value, endpoint.residue.value, endpoint.atom),
                    (FieldPath("LinkEndpoint", endpoint.entity.value, "bond"),),
                )
                continue
            record = by_id.get(endpoint.entity.value)
            if isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord)):
                length = len(record.sequence)
                if not (1 <= endpoint.residue.value <= length):
                    _add(
                        report,
                        rule,
                        "Bond residue %d lies outside the %d-residue sequence of %r."
                        % (endpoint.residue.value, length, endpoint.entity.value),
                        "endpoint residue %d out of range 1..%d" % (endpoint.residue.value, length),
                        (FieldPath("LinkEndpoint", endpoint.entity.value, "bond"),),
                    )
            elif isinstance(record, ComponentRecord):
                count = _ligand_residue_count(record.representation)
                if not (1 <= endpoint.residue.value <= count):
                    if count == 1:
                        _add(
                            report,
                            rule,
                            "A single-residue ligand uses residue 1 for a bond endpoint.",
                            "endpoint on ligand %r uses residue %d" % (endpoint.entity.value, endpoint.residue.value),
                            (FieldPath("LinkEndpoint", endpoint.entity.value, "bond"),),
                        )
                    else:
                        _add(
                            report,
                            rule,
                            "Bond residue %d lies outside the %d-component ligand %r "
                            "(residues are numbered 1..%d, one per CCD code)."
                            % (endpoint.residue.value, count, endpoint.entity.value, count),
                            "endpoint on multi-component ligand %r uses residue %d, expected 1..%d"
                            % (endpoint.entity.value, endpoint.residue.value, count),
                            (FieldPath("LinkEndpoint", endpoint.entity.value, "bond"),),
                        )


def check_r_bnd_004(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Bond residue IDs are 1-based (single-residue ligand uses residue 1)."""
    for linkage in configuration.linkages:
        for endpoint in (linkage.a, linkage.b):
            if endpoint.residue.value < 1:
                _add(
                    report,
                    rule,
                    "Bond residue positions are 1-based.",
                    "endpoint on %r uses residue %d" % (endpoint.entity.value, endpoint.residue.value),
                    (FieldPath("ResidueRef", endpoint.entity.value, "bond"),),
                )


def check_r_bnd_005(configuration: Configuration, report: Report, rule: Rule) -> None:
    """All explicit bonds are covalent: the model has one Linkage type; the
    check re-affirms the type of every stored linkage."""
    for linkage in configuration.linkages:
        if type(linkage).__name__ != "Linkage":
            _add(
                report,
                rule,
                "Only covalent bonds are supported by the explicit bond field.",
                "linkage of unexpected type %r" % type(linkage).__name__,
                (FieldPath("Linkage", linkage.a.entity.value, "bond"),),
            )


def check_r_bnd_006(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Polymer-polymer covalent bonds through this field are unsupported
    (DOCUMENTED)."""
    by_id = _records_by_id(configuration)
    for linkage in configuration.linkages:
        left = by_id.get(linkage.a.entity.value)
        right = by_id.get(linkage.b.entity.value)
        if isinstance(left, (FamilyARecord, FamilyBRecord, FamilyCRecord)) and isinstance(
            right, (FamilyARecord, FamilyBRecord, FamilyCRecord)
        ):
            _add(
                report,
                rule,
                "A bond between two polymer chains (%r and %r) is not supported by the explicit bond field."
                % (linkage.a.entity.value, linkage.b.entity.value),
                "both endpoints resolve to polymers",
                (FieldPath("Linkage", linkage.a.entity.value, "bond"),),
            )
