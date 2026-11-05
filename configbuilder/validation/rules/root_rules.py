"""Root-level rule checks (spec §19 "Root-level validation").

Each function appends findings to the given ``report``; nothing raises for
user-fixable conditions. Functions have no access to the filesystem.
"""

from __future__ import annotations

import re

from configbuilder.model import Configuration
from configbuilder.validation.catalogue import Rule
from configbuilder.validation.report import FieldPath, Finding, Report

_UINT32_MAX = 2 ** 32 - 1
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")


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


def check_r_root_001(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Dialect is exactly 'alphafold3'; the model's Dialect enum already
    guarantees it, so the check re-affirms the invariant."""
    dialect = configuration.format_target.dialect.value
    if dialect != "alphafold3":
        _add(
            report,
            rule,
            "The output dialect must be alphafold3.",
            "dialect is %r" % dialect,
            (FieldPath("Dialect"),),
        )


def check_r_root_002(configuration: Configuration, report: Report, rule: Rule) -> None:
    """The selected JSON version is one of the supported input versions.

    This is the availability half of the version contract, and the half this
    rule's summary always described but never checked. The *explicitness*
    half — ``Unverified`` — belongs to R-VER-001 alone, so one missing
    selection produces one finding (plan §10.3, spec §18).
    """
    from configbuilder.model import Auto, SUPPORTED_INPUT_VERSIONS, Unverified

    selection = configuration.format_target.version_selection
    if isinstance(selection, Unverified):
        # R-VER-001 reports the missing explicit selection; nothing is
        # selected here to check for availability.
        return
    if isinstance(selection, Auto):
        selected = min(selection.evidenced)
        reason = "the automatic selection resolves to version %d" % selected
    else:
        selected = selection.version
        reason = "version %d was selected explicitly" % selected
    if selected in SUPPORTED_INPUT_VERSIONS:
        return
    supported = ", ".join(str(version) for version in SUPPORTED_INPUT_VERSIONS)
    _add(
        report,
        rule,
        "JSON version %d is not a supported input version; this builder emits %s."
        % (selected, supported),
        "%s, outside SUPPORTED_INPUT_VERSIONS %s" % (reason, (SUPPORTED_INPUT_VERSIONS,)),
        (FieldPath("FormatTarget", None, "version_selection"),),
        suggestion="Choose one of the supported versions (%s) in the job settings."
        % (supported,),
    )


def check_r_root_003(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Job name non-empty and sanitizeable."""
    name = configuration.metadata.name
    if not name or not name.strip():
        _add(
            report,
            rule,
            "The job name must not be empty.",
            "name is empty",
            (FieldPath("ConfigurationMetadata", None, "name"),),
        )
    elif not _SAFE_NAME.match(name):
        _add(
            report,
            rule,
            "The job name contains characters that cannot form a file name.",
            "name %r is not filename-safe" % name,
            (FieldPath("ConfigurationMetadata", None, "name"),),
            suggestion="Use letters, digits, spaces, dots, dashes, or underscores.",
        )


def check_r_root_004(configuration: Configuration, report: Report, rule: Rule) -> None:
    """At least one model seed."""
    if len(configuration.seeds) == 0:
        _add(
            report,
            rule,
            "At least one model seed is required.",
            "seed list is empty",
            (FieldPath("SeedSet", None, "seeds"),),
        )


def check_r_root_005(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Seeds within uint32."""
    for index, seed in enumerate(configuration.seeds.seeds):
        if not (0 <= seed.value <= _UINT32_MAX):
            _add(
                report,
                rule,
                "Model seeds must lie between 0 and 4,294,967,295.",
                "seed at position %d is %d" % (index, seed.value),
                (FieldPath("Seed", None, "seeds[%d]" % index),),
            )


def check_r_root_006(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Records are the entity container. In the canonical model this means
    an empty record list is a finding: every entity lives in 'sequences'."""
    if len(configuration.records) == 0:
        _add(
            report,
            rule,
            "The input defines no entities; at least one protein, RNA, DNA, or ligand record is required.",
            "records tuple is empty",
            (FieldPath("Configuration", None, "records"),),
        )


def check_r_root_007(configuration: Configuration, report: Report, rule: Rule) -> None:
    """userCCD xor userCCDPath: the model's single component_definition field
    already guarantees mutual exclusion; this re-affirms it."""
    definition = configuration.component_definition
    if definition is not None:
        from configbuilder.model import External as ExternalRef, Inline as InlineRef

        if not isinstance(definition, (InlineRef, ExternalRef)):
            _add(
                report,
                rule,
                "The custom component definition must be inline text or a file path, not both or neither.",
                "component_definition has unexpected type %r" % type(definition).__name__,
                (FieldPath("Inline", None, "userCCD"),),
            )
