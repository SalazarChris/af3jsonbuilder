"""The validation engine (IMPLEMENTATION_PLAN.md §9.2).

Executes the catalogue in tier order (STRUCTURAL → RELATIONAL → CONTRACT →
VARIANT → PREFLIGHT); a failing rule never stops later tiers, and every
rule that could not run is reported as skipped — never silently green.

At the engine boundary, identity exceptions raised by user-caused
conditions are converted to findings (CHECKLIST.md Phase 4):
``identity.DuplicateIdError`` maps to R-ENT-002. The registry keeps its
raise-based contract; raw identity exceptions never reach the UI.
"""

from __future__ import annotations

from configbuilder.identity import DuplicateIdError, IdentityError
from configbuilder.model import Configuration
from configbuilder.validation.catalogue import Rule, TIER_ORDER, get_rule, rules_by_tier
from configbuilder.validation.ports import NullChemistryProbe, NullFilesystemPort
from configbuilder.validation.report import FieldPath, Finding, Report

__all__ = ["DuplicateIdError", "ValidationContext", "convert_identity_error", "validate"]


def convert_identity_error(error: IdentityError):
    """Map an identity exception onto its catalogue rule as a finding.

    The DuplicateIdError → R-ENT-002 wiring promised in CHECKLIST.md
    (Phase 4) lives here: the registry refuses a duplicate assignment
    (plan §8.1, never silently renamed); the engine converts the refusal
    into the R-ENT-002 ERROR finding. Other identity errors map to their
    own rules; an unmappable error is re-raised — it is a programming
    error, not a user condition.
    """

    if isinstance(error, DuplicateIdError):
        rule = get_rule("R-ENT-002")
        return Finding(
            rule_id=rule.rule_id,
            severity=rule.severity,
            user_message=(
                "An entity identifier is already in use; it must be changed, not reused."
            ),
            diagnostic=str(error),
            paths=(FieldPath("EntityId", None, "id"),),
            suggestion="Rename one of the records so every identifier is unique.",
        )
    raise error


class ValidationContext:
    """Ports and per-run flags handed to rules that need the outside world.

    PREFLIGHT rules run shallow: with the null ports, file-backed checks
    report "not readable here" as a WARNING, never a false ERROR (plan
    §9.6); disable preflight entirely with ``run_preflight=False``.
    """

    def __init__(
        self,
        filesystem=None,
        chemistry=None,
        run_preflight: bool = True,
        variant_documents=None,
        base_document=None,
        variant_declared_changes=None,
        variant_registries=None,
        variant_seeds=None,
        base_registry=None,
        used_version_features=None,
    ) -> None:
        self.filesystem = filesystem if filesystem is not None else NullFilesystemPort()
        self.chemistry = chemistry if chemistry is not None else NullChemistryProbe()
        self.run_preflight = run_preflight
        # Plan §5.3 rule 2 keeps validation independent of transform, so
        # VARIANT-tier comparison inputs arrive as plain data (joined by app):
        self.variant_documents = variant_documents  # {key: wire document}
        self.base_document = base_document
        self.variant_declared_changes = variant_declared_changes  # {key: [(factor, detail), ...]}
        self.variant_registries = variant_registries  # {key: IdentityRegistry}
        self.variant_seeds = variant_seeds  # {key: [seed values]}
        # The true base registry, joined by ``app`` so the identity-
        # stability rule compares a variant against the base it expanded
        # from. When absent the rule falls back to the validated
        # configuration's own registry (single-variant callers).
        self.base_registry = base_registry
        # The version-sensitive features this configuration uses, as
        # ``((feature name, minimum version), ...)`` — the mapping layer's
        # own answer, computed by ``transform`` and joined here by ``app``
        # (the same pattern as the VARIANT inputs above). ``None`` means the
        # join did not happen, and R-VER-002 then reports "not checked" as a
        # WARNING rather than pretending the pin covers everything.
        self.used_version_features = used_version_features


def _run_rule(rule: Rule, configuration: Configuration, report: Report, context: ValidationContext) -> None:
    """Invoke one rule's check function by convention:
    ``configbuilder.validation.rules.<family>_rules.check_<lowercase-id>``.
    R-ENT-002 is special-cased as the DuplicateIdError conversion point.
    """
    from configbuilder.validation import rules as rules_pkg

    family = {
        "R-ROOT": "root_rules",
        "R-ENT": "entity_rules",
        "R-MSA": "msa_rules",
        "R-TPL": "template_rules",
        "R-BND": "bond_rules",
        "R-VER": "policy_rules",
        "R-POL": "policy_rules",
        "R-VAR": "variant_rules",
    }.get(rule.rule_id.rsplit("-", 1)[0])
    if family is None:
        report.mark_skipped(rule, "no rule module for family")
        return
    function_name = "check_" + rule.rule_id.lower().replace("-", "_")
    module = getattr(rules_pkg, family)
    function = getattr(module, function_name, None)
    if function is None:
        report.mark_skipped(rule, "check function %s missing" % function_name)
        return
    try:
        import inspect

        parameter_count = len(inspect.signature(function).parameters)
        if parameter_count >= 4:
            function(configuration, report, rule, context)
        else:
            function(configuration, report, rule)
    except DuplicateIdError as error:
        # The engine boundary conversion (CHECKLIST.md Phase 4).
        report.add(convert_identity_error(error))
    except IdentityError as error:
        report.add(convert_identity_error(error))


def validate(
    configuration: Configuration,
    context: ValidationContext = None,
    tiers: tuple = TIER_ORDER,
) -> Report:
    """Run every catalogue rule over ``configuration`` in tier order.

    Later tiers always run despite earlier findings; PREFLIGHT runs last
    and only when ``context.run_preflight`` is set. The returned ``Report``
    carries findings and the list of skipped rules.
    """
    from configbuilder.validation.report import Report as _Report

    report = _Report()
    context = context if context is not None else ValidationContext()
    for tier in tiers:
        if tier.name == "PREFLIGHT" and not context.run_preflight:
            for rule in rules_by_tier()[tier]:
                report.mark_skipped(rule, "preflight disabled by policy")
            continue
        for rule in rules_by_tier()[tier]:
            _run_rule(rule, configuration, report, context)
    return report
