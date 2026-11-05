"""Validation package: rule catalogue, engine, findings, report (plan §6.3).

Phase 1 delivered the catalogue as data; Phase 4 adds the engine, the
finding vocabulary, and the executable rule checks.
"""

from configbuilder.validation.catalogue import (
    Evidence,
    Rule,
    RULES,
    Severity,
    Tier,
    TIER_ORDER,
    get_rule,
    rules_by_tier,
)
from configbuilder.validation.engine import (
    ValidationContext,
    convert_identity_error,
    validate,
)
from configbuilder.validation.ports import (
    BundledChemistryProbe,
    ChemistryProbe,
    FilesystemPort,
    NullChemistryProbe,
    NullFilesystemPort,
    OsFilesystemPort,
)
from configbuilder.validation.report import FieldPath, Finding, Report

__all__ = [
    # catalogue
    "Evidence",
    "Rule",
    "RULES",
    "Severity",
    "Tier",
    "TIER_ORDER",
    "get_rule",
    "rules_by_tier",
    # engine
    "ValidationContext",
    "convert_identity_error",
    "validate",
    # ports
    "BundledChemistryProbe",
    "ChemistryProbe",
    "FilesystemPort",
    "NullChemistryProbe",
    "NullFilesystemPort",
    "OsFilesystemPort",
    # report
    "FieldPath",
    "Finding",
    "Report",
]
