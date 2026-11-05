"""Validation façade (IMPLEMENTATION_PLAN.md §15): ``ValidationService``.

``validate_base`` runs the full catalogue over the open configuration;
``validate_all`` additionally validates every expanded variant with the
drift and identity-stability checks wired up (the comparison data join
plan §9.6 requires); ``status`` exposes the one configuration-status view
that every screen reads.
"""

from __future__ import annotations

from configbuilder.app.results import FailureReason, ConfigurationOutput, VariantValidationOutput
from configbuilder.transform import to_wire, used_version_features
from configbuilder.validation import Tier, ValidationContext
from configbuilder.variants import EditError, VariantSpecError, expand, declared_changes

__all__ = ["GATE_TIERS", "ValidationService"]

# The gate is the configuration-only half of the catalogue: shape, cross-record
# consistency, the target contract, and the preflight checks that ask the local
# world a shallow question (does the configured MSA file exist and is it
# readable; does the configured chemistry checker accept this SMILES). All four
# are decidable without an AF3 run, a prediction, or an output environment, so
# save, preview, generation and the Overview's readiness line can share them.
#
# VARIANT is deliberately absent: its rules compare a variant against its base
# and need the joined wire documents. GenerationService runs them through
# ``validate_all`` before a variant plan is built, and the Variants page shows
# them; they are never a reason for the base save path to refuse.
GATE_TIERS = (Tier.STRUCTURAL, Tier.RELATIONAL, Tier.CONTRACT, Tier.PREFLIGHT)


class ValidationService:
    """Runs validation over the open project, base and variants."""

    def __init__(self, projects, filesystem=None, chemistry=None, run_preflight=True) -> None:
        self._projects = projects
        self._filesystem = filesystem
        self._chemistry = chemistry
        self._run_preflight = run_preflight

    def _configuration(self):
        project = self._projects._require_project()
        return project.configuration if project is not None else None

    def _context(self, base_document=None, variants=(), configuration=None):
        """The join point: validation stays independent of transform and
        variants (plan §5.3 rule 2), so ``app`` hands it the comparison
        data as plain values.

        ``configuration`` (when given) also brings the version-sensitive
        features that configuration uses — the mapping layer's own answer —
        so R-VER-002 refuses exactly what the generation gate would refuse.
        """
        context = ValidationContext(
            filesystem=self._filesystem,
            chemistry=self._chemistry,
            run_preflight=self._run_preflight,
            used_version_features=(
                used_version_features(configuration) if configuration is not None else None
            ),
        )
        if base_document is not None:
            context.base_document = base_document
            context.variant_documents = {
                variant.key: to_wire(variant.configuration).document for variant in variants
            }
            context.variant_declared_changes = {
                spec.key: declared_changes(spec) for spec in self._projects._specs()
            }
            context.variant_registries = {
                variant.key: variant.configuration.identity for variant in variants
            }
            context.variant_seeds = {
                variant.key: list(variant.configuration.seeds.values) for variant in variants
            }
        return context

    def validate_configuration(self, configuration, tiers=None) -> ConfigurationOutput:
        """Validate one configuration, optionally restricted to ``tiers``.

        Save, preview, generation and the status view all pass
        :data:`GATE_TIERS`; the Variants page's review keeps the full
        catalogue (``validate_all``). This is the same engine and the same
        context join either way, so a rule can never block one surface and
        pass another.
        """
        from configbuilder.validation import validate

        kwargs = {"tiers": tuple(tiers)} if tiers is not None else {}
        report = validate(
            configuration,
            self._context(configuration=configuration),
            **kwargs,
        )
        return ConfigurationOutput(ok=not report.blocking(), report=report)

    def validate_base(self, tiers=None) -> ConfigurationOutput:
        configuration = self._configuration()
        if configuration is None:
            return ConfigurationOutput(
                ok=False,
                failure_reason=FailureReason.NOT_OPEN,
                message="no project is open",
            )
        return self.validate_configuration(configuration, tiers=tiers)

    def status(self):
        """The one configuration-status view over the open project.

        Menu display, the Overview page, save, and JSON generation all read
        this (``app.status.build_status``): the field rows a user sees and
        the gate's verdict travel together, so a front end cannot show
        "ready" while save refuses, nor refuse without saying which
        information is missing.

        Runs exactly :data:`GATE_TIERS` — the same rule set save, preview
        and generation use — so "ready" and "this job can be written" are
        the same question. Variant-tier findings are not part of a base
        readiness verdict; the Variants page validates variants with the
        full catalogue. ``None`` when no project is open — there is nothing
        to describe.
        """
        from configbuilder.app.status import build_status

        configuration = self._configuration()
        if configuration is None:
            return None
        outcome = self.validate_base(tiers=GATE_TIERS)
        if outcome.report is None:
            return None
        return build_status(configuration, outcome.report.blocking())

    def validate_all(self, only=None) -> VariantValidationOutput:
        """Validate the base and every expanded variant (§15 step 3).

        ``only`` (an iterable of keys) restricts the variant half to that
        subset — the subset-export route shares it. The base is always
        validated: every variant derives from it. The full catalogue runs
        here (gate tiers plus the variant comparison), which is why this is
        the variant path's authoritative validation rather than a display
        convenience.

        The variant checks need wire documents; building them here costs
        one transform per variant, which ``GenerationService.plan``
        reuses instead of recomputing (its documents come from the same
        pure function, so the results are identical).
        """
        project = self._projects._require_project()
        if project is None:
            return VariantValidationOutput(
                ConfigurationOutput(
                    ok=False,
                    failure_reason=FailureReason.NOT_OPEN,
                    message="no project is open",
                )
            )
        specs = project.specs
        if only is not None:
            keys = tuple(only)
            known = {spec.key for spec in specs}
            unknown = [key for key in keys if key not in known]
            if unknown:
                return VariantValidationOutput(
                    ConfigurationOutput(
                        ok=False,
                        failure_reason=FailureReason.UNKNOWN_RECORD,
                        message="no variant keyed %r exists" % (unknown[0],),
                    )
                )
            specs = tuple(spec for key in keys for spec in specs if spec.key == key)
        return self.validate_specs(specs)

    def validate_specs(self, specs) -> VariantValidationOutput:
        """``validate_all`` over an **explicit** spec tuple.

        The one-step ligand file flow builds its specs and writes their
        files in the same pass, without ever committing them to the project
        (no persistent variant list is part of that workflow). Its variants
        still get the authoritative validation — base first, then each
        variant against its own comparison data — through exactly this
        method, so a batch cannot be written on a weaker check than an
        in-memory variant would be.
        """
        project = self._projects._require_project()
        if project is None:
            return VariantValidationOutput(
                ConfigurationOutput(
                    ok=False,
                    failure_reason=FailureReason.NOT_OPEN,
                    message="no project is open",
                )
            )
        from configbuilder.validation import validate

        specs = tuple(specs)
        base_report = validate(
            project.configuration,
            self._context(configuration=project.configuration),
        )
        if base_report.blocking():
            return VariantValidationOutput(base_report)
        try:
            variants = expand(project.configuration, specs)
        except (EditError, VariantSpecError) as error:
            # A committed variant that cannot expand is a user condition, not
            # a crash: the base half above is still reported, the variant half
            # says why it was not validated. Letting the refusal escape here
            # took the whole session down from Review → Validate (BUG-022).
            return VariantValidationOutput(
                base_report,
                failure_reason=FailureReason.EXPANSION_FAILED,
                message=str(error),
            )
        base_document = to_wire(project.configuration).document
        variant_documents = {variant.key: to_wire(variant.configuration).document for variant in variants}
        # Each variant is validated against a context that carries only
        # its own comparison data and the base's: the engine runs one
        # ``validate`` call per variant configuration, and the VARIANT-
        # tier rules describe every document in the context they see. A
        # shared context would attribute sibling variants' differences
        # to each report (the batch-generation bug) — per-variant
        # contexts keep every report about its own variant.
        declared_by_key = {spec.key: declared_changes(spec) for spec in specs}
        variant_reports = {}
        for variant in variants:
            context = self._context(configuration=variant.configuration)
            context.base_document = base_document
            context.base_registry = project.configuration.identity
            context.variant_documents = {variant.key: variant_documents[variant.key]}
            context.variant_declared_changes = {variant.key: declared_by_key[variant.key]}
            context.variant_registries = {variant.key: variant.configuration.identity}
            context.variant_seeds = {variant.key: list(variant.configuration.seeds.values)}
            variant_reports[variant.key] = validate(variant.configuration, context)
        return VariantValidationOutput(
            base_report,
            variant_reports,
            variant_documents,
            base_document,
        )


