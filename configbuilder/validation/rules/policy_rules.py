"""Version-selection and INFO-only policy rule checks (plan §10.3, spec §14,
spec §19 final section).

Policy rules (R-POL-*) always emit their informational finding: they exist
so a non-rule can never silently turn into a gate (plan §9.3).
"""

from __future__ import annotations

from configbuilder.model import (
    Auto,
    Configuration,
    Unverified,
)
from configbuilder.validation.catalogue import Rule, Severity
from configbuilder.validation.report import FieldPath, Finding, Report


def _feature_rows(features):
    """The joined version-feature facts, each as ``(name, version, wording)``.

    The naming and the wording are both the mapping layer's: ``transform``
    hands ``app`` ``(feature, minimum version, plain-English name)`` rows and
    ``app`` joins them into this context, so nothing here spells a wire field
    (plan §10.1) — this rule only compares a number and quotes the words.
    """
    for row in features:
        name, min_version = row[0], row[1]
        wording = row[2] if len(row) > 2 else "the %s field" % name
        yield name, min_version, wording


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


def check_r_ver_001(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Save and generation need an explicit format version: ``Unverified`` is
    the blocking state, and the version is never inferred from documentation,
    examples, releases, or defaults.

    This is the single blocking check for "no version selected"; whether the
    selected version is supported is R-ROOT-002. No deployment evidence, run
    or observation is consulted — an explicit ``Pinned``/``Auto`` selection
    is the whole requirement (plan §10.3, spec §18).
    """
    from configbuilder.model import SUPPORTED_INPUT_VERSIONS

    if isinstance(configuration.format_target.version_selection, Unverified):
        supported = ", ".join(str(version) for version in SUPPORTED_INPUT_VERSIONS)
        _add(
            report,
            rule,
            "No JSON format version is selected for this job.",
            "version selection is Unverified (no explicit target supplied)",
            (FieldPath("Unverified", None, "version_selection"),),
            suggestion="Choose a JSON version (%s) in the job settings." % (supported,),
        )


def check_r_ver_002(configuration: Configuration, report: Report, rule: Rule, context=None) -> None:
    """A feature requiring a version above the selected one is an error naming
    the feature — the version is never silently raised.

    The facts are the mapping layer's (``((feature, minimum version), ...)``
    computed by ``transform`` from the same tables that gate emission) and
    arrive through the context, joined by ``app``. Validation therefore
    refuses exactly what generation refuses, which is what keeps the
    readiness verdict from contradicting the JSON preview and the save path.

    A pin's evidence reference is optional recorded provenance, never a
    condition for generating output; an ``Auto`` selection that spans no
    evidenced version is still reported here.
    """
    selection = configuration.format_target.version_selection
    if isinstance(selection, Unverified):
        # R-VER-001 already blocks this: there is no selected version to
        # compare a feature against, and reporting twice helps nobody.
        return
    if isinstance(selection, Auto):
        if not selection.evidenced:
            _add(
                report,
                rule,
                "The automatic version selection includes no evidenced versions.",
                "Auto has an empty evidenced set",
                (FieldPath("Auto", None, "version_selection"),),
            )
            return
        # The engine's own Auto semantics: the minimum evidenced version.
        effective = min(selection.evidenced)
    else:
        effective = selection.version

    features = getattr(context, "used_version_features", None) if context is not None else None
    if features is None:
        _add(
            report,
            rule,
            "Version-feature consistency could not be checked: the features this job uses were not provided to the validator.",
            "context lacks used_version_features (the transform-side join)",
            (FieldPath("FormatTarget", None, "version_selection"),),
            severity=Severity.WARNING,
        )
        return

    for feature_name, min_version, feature_words in _feature_rows(features):
        if effective < min_version:
            _add(
                report,
                rule,
                "This job uses %s, which is written from input version %d, but the job is "
                "set to version %d. Raise the job's JSON version, or remove the field."
                % (feature_words, min_version, effective),
                "feature %r requires version %d, selected version is %d"
                % (feature_name, min_version, effective),
                (FieldPath("FormatTarget", None, "version_selection"),),
                suggestion="Pin version %d or later in the job's settings (the version is never changed automatically)."
                % min_version,
            )


def check_r_pol_001(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Seed-list uniqueness is project policy: report duplicates as INFO."""
    values = configuration.seeds.values
    seen = set()
    duplicates = sorted({v for v in values if v in seen or seen.add(v)})
    if duplicates:
        _add(
            report,
            rule,
            "The seed list contains duplicate values (allowed; uniqueness is a project policy, not a requirement).",
            "duplicated seed values: %s" % duplicates,
            (FieldPath("SeedSet", None, "modelSeeds"),),
        )


def check_r_pol_002(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Seed ordering is preserved as given; sorting is a project choice."""
    values = configuration.seeds.values
    if list(values) != sorted(values):
        _add(
            report,
            rule,
            "The seed list is not sorted (allowed; order is preserved exactly as given).",
            "seed order %s" % (list(values),),
            (FieldPath("SeedSet", None, "modelSeeds"),),
        )


def check_r_pol_003(configuration: Configuration, report: Report, rule: Rule) -> None:
    """The chain-ID allocation algorithm is a project choice; report the
    registry's allocation shape for transparency."""
    _add(
        report,
        rule,
        "Chain identifiers were allocated by the project's deterministic allocator (this is a project choice, not a contract rule).",
        "registry holds %d identifiers" % len(configuration.identity.order()),
    )


def check_r_pol_004(configuration: Configuration, report: Report, rule: Rule) -> None:
    """The fixed set of 10 seeds is a comparison policy."""
    count = len(configuration.seeds)
    if count != 10:
        _add(
            report,
            rule,
            "The project's comparison policy fixes 10 model seeds (not an AF3 requirement).",
            "seed count is %d" % count,
            (FieldPath("SeedSet", None, "modelSeeds"),),
        )


def check_r_pol_005(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Biological validity of a requested modification site is out of scope."""
    _add(
        report,
        rule,
        "The biological validity of requested modification sites is not checked (out of scope).",
        "INFO-only rule; spec §21 non-goals",
    )


def check_r_pol_006(configuration: Configuration, report: Report, rule: Rule) -> None:
    """Scientific plausibility of a modification is out of scope."""
    _add(
        report,
        rule,
        "The scientific plausibility of modifications is not checked (out of scope).",
        "INFO-only rule; spec §21 non-goals",
    )


def check_r_pol_007(configuration: Configuration, report: Report, rule: Rule, context=None) -> None:
    """Seed-set stability across variants (spec §15 factor 2): a variant that
    changes the shared seed set is an experiment-design hazard — the seed
    sets stop being comparable. Reported per policy severity."""
    base_seeds = list(configuration.seeds.values)
    variant_seeds = getattr(context, "variant_seeds", None) if context is not None else None
    if not variant_seeds:
        _add(
            report,
            rule,
            "Seed-set stability is reported per variant as a project policy; no variants were provided.",
            "base seed set: %s" % (base_seeds,),
            (FieldPath("SeedSet", None, "modelSeeds"),),
        )
        return
    for key in sorted(variant_seeds):
        if list(variant_seeds[key]) != base_seeds:
            _add(
                report,
                rule,
                "Variant %r changes the seed set; the model sets will no longer be comparable."
                % key,
                "base %s vs variant %s" % (base_seeds, list(variant_seeds[key])),
                (FieldPath("SeedSet", key, "modelSeeds"),),
                suggestion="Keep the shared seed set identical across variants being compared.",
            )
    if not any(list(variant_seeds[key]) != base_seeds for key in variant_seeds):
        _add(
            report,
            rule,
            "The seed set is identical across all provided variants (comparable).",
            "base seed set: %s" % (base_seeds,),
            (FieldPath("SeedSet", None, "modelSeeds"),),
        )
