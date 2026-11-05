"""VARIANT-tier rule checks (IMPLEMENTATION_PLAN.md §12.5, §9.2).

These rules compare a variant against its base. Plan §5.3 rule 2 keeps
``validation`` and ``transform`` independent, so the comparison inputs are
handed over as plain data through ``ValidationContext``:

- ``context.variant_documents`` — mapping of variant key to that variant's
  wire document (built by ``app`` via ``transform``);
- ``context.base_document`` — the base's wire document;
- ``context.variant_declared_changes`` — mapping of variant key to the
  ``(factor, detail)`` pairs ``variants.declared_changes`` derived from the
  spec (``detail`` is the record key where the edit targets one);
- ``context.variant_registries`` — mapping of variant key to the variant's
  own ``IdentityRegistry`` (for identity stability).

Where the context lacks the facts, the rule reports "not checked" as a
WARNING rather than pretending the variant is clean (plan §9.6: a check
that could not run is *reported*, never silently green). The engine runs
base-level validation with a plain context, so these rules simply report
their skip condition there — base validation is not variant validation.
"""

from __future__ import annotations

from configbuilder.model import (
    Configuration,
)
from configbuilder.validation.catalogue import Rule, Severity
from configbuilder.validation.report import FieldPath, Finding, Report

__all__ = ["check_r_var_001", "check_r_var_002"]


def _add(report: Report, rule: Rule, user_message: str, diagnostic: str, paths=(), suggestion: str = "", severity=None) -> None:
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


def _leaf_paths(prefix, base_value, variant_value, out):
    """Collect the paths of leaves that differ between two JSON-like values."""
    if isinstance(base_value, dict) and isinstance(variant_value, dict):
        for key in sorted(set(base_value) | set(variant_value)):
            _leaf_paths(prefix + (str(key),), base_value.get(key), variant_value.get(key), out)
    elif isinstance(base_value, list) and isinstance(variant_value, list):
        if len(base_value) != len(variant_value):
            out.add(prefix + ("<length: %d vs %d>" % (len(base_value), len(variant_value)),))
        for index in range(min(len(base_value), len(variant_value))):
            _leaf_paths(prefix + ("[%d]" % index,), base_value[index], variant_value[index], out)
    else:
        if base_value != variant_value:
            out.add(prefix)


def _attribute(factor, path):
    """Does this declared (factor, detail) pair plausibly own this wire path?

    The mapping is deliberately coarse: it attributes by *region* of the
    document (root fields, the entity list, per-record sub-objects). A
    declared sequence edit on record ``A`` therefore covers differences
    inside ``sequences[*].protein`` — while a seeds edit never covers a
    sequence difference.
    """
    region = path[0] if path else ""

    root_field_factors = {
        "job_name": {"name"},
        "job_description": set(),  # never emitted to the wire
        "seeds": {"modelSeeds"},
        "component_definition": {"userCCD", "userCCDPath"},
        "format_target": {"dialect", "version"},
        "bonded_atom_pairs": {"bondedAtomPairs"},
    }
    if factor in root_field_factors:
        return region in root_field_factors[factor] or region == ""

    if factor in ("sequence", "modifications", "alignment", "references", "chain_description"):
        return region == "sequences"
    if factor in ("ligand_representation", "component_count"):
        # A copy-count edit changes the id list (and possibly the id
        # length) on the ligand's entity — the same sequences region.
        return region == "sequences"
    if factor == "records":
        return region == "sequences"
    return False


def check_r_var_001(configuration: Configuration, report: Report, rule: Rule, context) -> None:
    """Undrifted comparison (plan §12.5): every wire difference between a
    variant and the base must be attributable to a declared edit."""
    documents = getattr(context, "variant_documents", None)
    base_document = getattr(context, "base_document", None)
    declared = getattr(context, "variant_declared_changes", None)
    if not documents or base_document is None or declared is None:
        _add(
            report,
            rule,
            "Variant drift could not be checked: wire documents were not provided to the validator.",
            "context lacks variant_documents / base_document / variant_declared_changes",
            (FieldPath("Configuration", None, ""),),
            severity=Severity.WARNING,
        )
        return

    for key in sorted(documents):
        differences = set()
        _leaf_paths((), base_document, documents[key], differences)
        unattributed = []
        for path in sorted(differences):
            if not any(_attribute(factor, path) for factor, _detail in declared.get(key, ())):
                unattributed.append("/".join(path))
        if unattributed:
            _add(
                report,
                rule,
                "Variant %r changed fields that no declared edit explains." % key,
                "unattributed wire differences: %s; declared: %s"
                % (", ".join(unattributed[:8]), sorted(declared.get(key, ()))),
                (FieldPath("Configuration", key, ""),),
                "Declare the change in the variant's edits, or undo it; "
                "undeclared drift invalidates the comparison.",
            )


def check_r_var_002(configuration: Configuration, report: Report, rule: Rule, context) -> None:
    """Identity stability (plan §8.3, §12.4): the record identifiers a
    variant holds must be the base's, possibly grown by declared AddRecord
    edits and shrunk by declared RemoveRecord edits — never silently
    re-ordered, re-numbered, or reused after release."""
    registries = getattr(context, "variant_registries", None)
    declared = getattr(context, "variant_declared_changes", None)
    if not registries or declared is None:
        _add(
            report,
            rule,
            "Variant identity stability could not be checked: variant registries were not provided.",
            "context lacks variant_registries / variant_declared_changes",
            (FieldPath("Configuration", None, ""),),
            severity=Severity.WARNING,
        )
        return

    base_registry = getattr(context, "base_registry", None)
    if base_registry is None:
        # Single-configuration callers pass no explicit base; the
        # validated configuration is then the base itself.
        base_registry = configuration.identity
    base_ids = [entity.value for entity in base_registry.order()]
    for key in sorted(registries):
        registry = registries[key]
        variant_ids = [entity.value for entity in registry.order()]
        removed = {
            detail
            for factor, detail in declared.get(key, ())
            if factor == "records" and detail is not None
        }
        base_remaining = [value for value in base_ids if value not in removed]
        # Every identifier the base held (minus declared removals) must
        # still be held, in order, by the variant's registry.
        if variant_ids[: len(base_remaining)] != base_remaining:
            _add(
                report,
                rule,
                "Variant %r changed record identifiers that no declared edit explains." % key,
                "base ids %s vs variant ids %s (declared removals: %s)"
                % (base_ids, variant_ids, sorted(removed)),
                (FieldPath("EntityId", key, ""),),
                "Record identifiers must survive expansion unchanged (plan §12.3); "
                "add or remove records through declared edits only.",
            )
