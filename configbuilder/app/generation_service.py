"""Generation (IMPLEMENTATION_PLAN.md §15): ``GenerationService``.

The generation sequence is fixed in exactly one place, in this order:

1. Expand variants.
2. Transform each variant.
3. Encode each wire document.
4. Build the output plan, including collision detection and the manifest
   payload.

The gate runs ``ValidationService.GATE_TIERS`` — structural, relational,
contract and preflight — over the base before anything is expanded, and the
full catalogue (including the variant drift/identity comparison) over every
selected variant before anything is written. Every one of those checks is
decidable in-process: validation does not run AF3 and never consults a
prediction, result directory or completion marker, so a valid configuration
is saved and generated without ever having been executed.

Save, preview and generation run the same gate, and readiness on the Overview
reads it too, so no surface can say "ready" while another refuses.

Everything before ``execute`` is pure planning (plan §13.3): nothing is
written without a plan, and ``execute`` performs writes only — it does
not re-derive content, so what the user reviewed is exactly what is
written. The service returns result objects and writes nothing itself
(plan §5.3 rule 8: filesystem access is confined to ``output`` and
``persistence``).

Two wire-level agreements happen between steps 2 and 3, both through
``transform`` so wire vocabulary never leaks into ``app`` (plan §10.1):

- the job ``name`` field carries the same derived name the directory
  and filename use (plan §13.2) — via ``transform.with_wire_job_name``;
- external resource paths are rewritten to their emitted forms (§13.5
  path policies) — via ``transform.with_emitted_resource_paths``.

The manifest joins the plan as an ordinary planned file (§13.1): same
overwrite policy, atomic write, part of the reviewed layout. Its
``validation_summary`` records the combined base-plus-variant report the
gate produced for exactly the configurations written — and stays empty
when no validator is wired, never inventing a clean run.
"""

from __future__ import annotations

import os

from configbuilder.app.results import (
    BASE_PLAN_KEY,
    ConfigurationPlan,
    FailureReason,
    GenerationPlan,
    LigandBatchOutput,
    PlanOutput,
)
from configbuilder.output import (
    OVERWRITE_POLICIES,
    PATH_POLICIES,
    OverwritePolicy,
    OutputPlan,
    PathPolicy,
    PlanEntry,
    build_manifest,
    plan as plan_output,
    slug as slug_name,
)
from configbuilder.output.execute import execute as execute_plan
from configbuilder.output.naming import (
    variant_directory_name,
    variant_file_name,
)
from configbuilder.output.plan import (
    OsFileView,
    conflict_message,
    decide_action,
    fingerprint,
    resolve_resources_into,
)
from configbuilder.persistence import OutputSettings
from configbuilder.validation import Report
from configbuilder.serialize import encode
from configbuilder.transform import (
    TransformError,
    to_wire,
    with_emitted_resource_paths,
    with_wire_job_name,
)
from configbuilder.variants import (
    EditError,
    VariantSpecError,
    describe_edit,
    expand,
)

__all__ = ["GenerationService"]

_MANIFEST_FILE_NAME = "manifest.json"


class GenerationService:
    """Runs the fixed generation sequence; hands the reviewed plan to
    ``output`` for execution."""

    def __init__(self, projects, variants, filesystem=None, validation=None) -> None:
        self._projects = projects
        self._variants = variants
        # An ``output.FileView`` (read-only) for planning; ``None`` means
        # the real filesystem — exactly ``plan``'s own default.
        self._filesystem = filesystem
        # Optional so tests and scripts can build a deliberately ungated
        # service. The application wiring supplies it; save, preview and
        # generation consult it.
        self._validation = validation

    # -- the gate ---------------------------------------------------------------

    def _gate_base(self):
        if self._validation is None:
            return None
        from configbuilder.app.validation_service import GATE_TIERS

        return self._gate_outcome(
            self._validation.validate_base(tiers=GATE_TIERS),
            "base configuration",
            "base",
        )

    @staticmethod
    def _gate_outcome(outcome, label, scope):
        if outcome.ok:
            return None
        findings = outcome.report.blocking() if outcome.report is not None else ()
        detail = "; ".join(finding.user_message for finding in findings[:2])
        if not detail:
            detail = outcome.message or "validation did not pass"
        return GenerationPlan(
            ok=False,
            failure_reason=FailureReason.VALIDATION_BLOCKED,
            message="%s is not ready — blocking findings: %s" % (label, detail),
            findings=findings,
            refused_scope=scope,
        )

    def _variant_validation(self, only=None):
        """``validate_all`` when a validator is wired, else ``None``.

        The full catalogue with the drift/identity join populated — the same
        call the Variants page makes, so its verdict and generation's cannot
        disagree.
        """
        if self._validation is None:
            return None
        return self._validation.validate_all(only=only)

    @staticmethod
    def _refuse_validation(blocking, message, scope):
        return GenerationPlan(
            ok=False,
            failure_reason=FailureReason.VALIDATION_BLOCKED,
            message=message,
            findings=tuple(blocking),
            refused_scope=scope,
        )

    def _variant_gate(self, detail):
        """Refuse a variant run whose authoritative validation is blocking.

        The base half is checked first (every variant derives from it), then
        each selected variant's own report: drift (R-VAR-001) and identity
        stability (R-VAR-002) are ERROR findings there, and a variant the
        Variants page marks blocked can no longer be generated anyway. The
        comparison uses wire documents built in memory; no AF3 run exists on
        this path.
        """
        if detail is None:
            return None
        if detail.failure_reason is not None:
            return GenerationPlan(
                ok=False,
                failure_reason=detail.failure_reason,
                message=detail.message or "the variant could not be validated",
            )
        base_blocking = (
            detail.base_report.blocking() if detail.base_report is not None else ()
        )
        if base_blocking:
            return self._refuse_validation(
                base_blocking,
                "the base configuration has blocking findings; generate cannot start",
                "base",
            )
        blocking_keys = sorted(
            key for key, report in detail.variant_reports.items() if report.blocking()
        )
        if blocking_keys:
            findings = tuple(
                finding
                for key in blocking_keys
                for finding in detail.variant_reports[key].blocking()
            )
            return self._refuse_validation(
                findings,
                "variant %s has blocking findings; nothing will be written"
                % ", ".join(blocking_keys),
                "variant",
            )
        return None

    @staticmethod
    def _combined_report(detail):
        """What the manifest records: the base report then each variant's.

        ``None`` when validation did not run (an unwired service), so the
        manifest's summary stays empty rather than claiming a clean run.
        """
        if detail is None or detail.base_report is None:
            return None
        combined = Report()
        combined.add_all(detail.base_report.findings)
        for key in sorted(detail.variant_reports):
            combined.add_all(detail.variant_reports[key].findings)
        return combined

    # -- the fixed sequence (§15) ------------------------------------------------

    def show_json(self, key: str = None):
        """The encoded JSON text for the base (``key=None``) or one variant.

        Display-only: it runs the same ``to_wire`` → ``encode`` path the
        export uses, so what the user sees is byte-for-byte what a file
        would contain (plan §15's single-serialization discipline). No
        state changes. Returns ``(text, None)`` on success or
        ``(None, message)`` when nothing can be shown.

        The same gate as save and generation runs first: the preview never
        shows a document that save would refuse, and a variant preview runs
        the full variant comparison too. It needs no JSON run and no output
        environment.
        """
        project = self._projects._require_project()
        if project is None:
            return None, "no project is open"
        if key is None:
            selection = (("base", project.configuration),)
            refused = self._gate_base()
            if refused is not None:
                return None, refused.message
        else:
            previewed = self._variants.preview(key)
            if not previewed.ok:
                return None, previewed.message or "no variant keyed %r" % (key,)
            selection = tuple(
                (variant.key, variant.configuration)
                for variant in previewed.variants
            )
            refused = self._variant_gate(self._variant_validation(only=(key,)))
            if refused is not None:
                return None, refused.message
        try:
            for _name, configuration in selection:
                document = to_wire(configuration).document
                return encode(document).decode("utf-8"), None
        except TransformError as error:
            return None, str(error)
        return None, "nothing to show"

    # -- the front end's scope and policy surface --------------------------

    def output_policy_choices(self):
        """The policy names a front end may offer, in the service's order.

        Names, not policy objects: ``ui`` imports ``app`` only, so the picker
        values travel as the same plain strings the manifest records. An
        empty tuple would mean the policy family is unavailable; both are
        closed sets today.
        """
        return {
            "overwrite": tuple(policy.name for policy in OVERWRITE_POLICIES),
            "path": tuple(policy.name for policy in PATH_POLICIES),
        }

    def output_defaults(self):
        """The open project's own output settings, as policy names.

        These are the defaults the service itself would use when a plan is
        made without an explicit choice, read from ``project.settings`` (the
        safe defaults when a project carries none). The GUI preselects them;
        it never decides them.
        """
        project = self._projects._require_project()
        settings = project.settings if project is not None else None
        return {
            "overwrite": (
                settings.overwrite_policy
                if settings is not None
                else OVERWRITE_POLICIES[0].name
            ),
            "path": (
                settings.path_policy
                if settings is not None
                else PATH_POLICIES[0].name
            ),
        }

    def plan_selection(
        self,
        output_root,
        scope="variants",
        only=None,
        overwrite_policy=None,
        path_policy=None,
    ) -> GenerationPlan:
        """Plan one generation scope, with policy *names* from a picker.

        ``scope`` is the service's own vocabulary: ``"variants"`` plans every
        variant and the manifest (``plan``), ``"selected"`` plans exactly the
        keys in ``only`` (``plan(only=...)``), and ``"base"`` plans the base
        configuration's single file (``plan_base``, no manifest). Policy names
        are matched against the closed policy sets; an unknown name is a
        refused plan, not a silent fallback to a different policy.

        Nothing is written here: this only narrows which existing planning
        method runs and turns the picker's names into policy values.
        """
        overwrite, problem = _named_policy(
            OVERWRITE_POLICIES, OverwritePolicy, overwrite_policy, "overwrite"
        )
        if problem is not None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.INVALID_CHOICE,
                message=problem,
            )
        path_choice, problem = _named_policy(
            PATH_POLICIES, PathPolicy, path_policy, "path"
        )
        if problem is not None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.INVALID_CHOICE,
                message=problem,
            )

        if scope == "base":
            return self.plan_base(
                output_root,
                overwrite_policy=overwrite,
                path_policy=path_choice,
            )
        if scope == "selected":
            keys = tuple(only or ())
            if not keys:
                return GenerationPlan(
                    ok=False,
                    failure_reason=FailureReason.INVALID_CHOICE,
                    message="choose exactly one variant to generate",
                )
            return self.plan(
                output_root,
                overwrite_policy=overwrite,
                path_policy=path_choice,
                only=keys,
            )
        if scope not in ("variants", "all"):
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.INVALID_CHOICE,
                message="unknown generation scope %r" % (scope,),
            )
        return self.plan(
            output_root,
            overwrite_policy=overwrite,
            path_policy=path_choice,
        )

    def plan(self, output_root: str, overwrite_policy=None, path_policy=None, only=None) -> GenerationPlan:
        """Steps 1–6 in exactly this order. Nothing is written here.

        ``only`` (an iterable of variant keys) restricts the run to that
        subset — the selected-export route. The manifest and job names
        are derived from exactly the variants written, so a subset run is
        self-consistent.
        """
        project = self._projects._require_project()
        if project is None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.NOT_OPEN,
                message="no project is open",
            )

        # Gate before expansion: a configuration that fails the core tiers
        # should not produce variant documents or a plan.
        refused = self._gate_base()
        if refused is not None:
            return refused

        # Step 1: expand variants (the base is not implicitly included; §12.2).
        expansion = self._variants.expand(only=only)
        if not expansion.ok:
            return GenerationPlan(
                ok=False,
                failure_reason=expansion.failure_reason,
                message=expansion.message,
            )
        variants = expansion.variants
        if not variants:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.EMPTY_EXPANSION,
                message="there are no variants to generate; add a variant first",
            )

        # The variant run's authoritative validation: one full-catalogue
        # pass over the base and each selected variant, including the
        # R-VAR-001 drift and R-VAR-002 identity comparison the Variants
        # page shows. A blocking variant refuses the whole run before any
        # document is transformed or written, so no partial batch escapes,
        # and the same pass feeds the manifest's validation summary.
        detail = self._variant_validation(only=only)
        refused = self._variant_gate(detail)
        if refused is not None:
            return refused

        # Steps 3–6: transform, encode, plan, manifest. The sequence is
        # shared with every other variant run (``plan_ligand_batch``).
        return self._plan_variants(
            variants, detail, output_root, overwrite_policy, path_policy
        )

    # -- the shared planning sequence (steps 3–6) -----------------------------

    def _plan_variants(
        self, variants, detail, output_root, overwrite_policy=None, path_policy=None
    ) -> GenerationPlan:
        """Steps 3–6 over an already-expanded, already-gated run.

        Extracted unchanged from ``plan`` so every variant source — the
        in-memory specs and the one-step ligand file flow — writes through
        one sequence: one transform, one encode, one planner, one manifest.
        """
        project = self._projects._require_project()
        if project is None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.NOT_OPEN,
                message="no project is open",
            )
        # Step 3: transform each variant, applying the §13.2 name agreement.
        settings = project.settings or OutputSettings()
        overwrite = (
            OverwritePolicy(settings.overwrite_policy)
            if overwrite_policy is None
            else overwrite_policy
        )
        path_choice = (
            PathPolicy(settings.path_policy) if path_policy is None else path_policy
        )
        project_name = project.configuration.metadata.name
        project_slug = slug_name(project_name)

        try:
            base_result = to_wire(project.configuration)
            base_fingerprint = fingerprint(encode(base_result.document))
            documents = {}
            format_versions = {}
            requirements_by_key = {}
            for variant in variants:
                result = to_wire(variant.configuration)
                documents[variant.key] = with_wire_job_name(
                    result.document,
                    variant_directory_name(project_slug, variant.key),
                )
                format_versions[variant.key] = result.version
                requirements_by_key[variant.key] = result.external_resources
        except TransformError as error:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.TRANSFORM_FAILED,
                message=str(error),
            )

        # §13.5 resolution (a planning input to step 5): the emitted path
        # forms must be known before encoding, so a first pure planning pass
        # resolves them — same collision detection, same resource rows. The
        # final pass then decides actions from the real payload bytes.
        probe_plan = plan_output(
            {key: b"" for key in documents},
            output_root,
            project_name,
            overwrite_policy=overwrite,
            path_policy=path_choice,
            resources_by_variant=requirements_by_key,
            filesystem=self._filesystem,
        )
        emitted = {}
        for resource in probe_plan.resources:
            if (
                resource.emitted_path is not None
                and resource.raw_path != resource.emitted_path
            ):
                emitted.setdefault(resource.wire_field, {})[resource.raw_path] = (
                    resource.emitted_path
                )
        documents = {
            key: with_emitted_resource_paths(documents[key], emitted)
            for key in documents
        }

        # Step 5: encode each wire document (the serializer's fixed policy).
        payloads = {key: encode(documents[key]) for key in documents}

        # Step 6: the output plan — collision detection over real payloads
        # (resource rows resolve identically to the probe) and the manifest
        # payload (§13.6).
        planned = plan_output(
            payloads,
            output_root,
            project_name,
            overwrite_policy=overwrite,
            path_policy=path_choice,
            resources_by_variant=requirements_by_key,
            filesystem=self._filesystem,
        )

        variant_records = []
        for variant in variants:
            key = variant.key
            file_name = variant_file_name(project_slug, key)
            entry = _entry_by_file_name(planned, file_name)
            variant_records.append(
                {
                    "key": key,
                    "label": variant.label,
                    "declared_factors": list(variant.lineage.declared_factors),
                    "applied_edits": [
                        describe_edit(edit) for edit in variant.lineage.applied_edits
                    ],
                    "file_name": file_name,
                    "fingerprint": (
                        entry.payload_fingerprint if entry is not None else ""
                    ),
                }
            )
        manifest = build_manifest(
            project_name=project_name,
            base_fingerprint=base_fingerprint,
            format_version=max(format_versions.values()),
            variants=variant_records,
            seed_set=list(project.configuration.seeds.values),
            validation_report=self._combined_report(detail),
            path_policy=path_choice,
            overwrite_policy=overwrite,
            format_target=project.configuration.format_target,
        )
        manifest_payload = encode(manifest.data)

        # The manifest joins the plan as an ordinary planned file (§13.1):
        # it lands at ``<output_root>/<project_slug>/manifest.json``, is
        # subject to the same overwrite policy, and is written atomically
        # by the same executor (§13.3, §13.4).
        manifest_path = os.path.join(output_root, project_slug, _MANIFEST_FILE_NAME)
        manifest_path, manifest_action, manifest_exists = _manifest_decision(
            manifest_payload, overwrite, self._filesystem, manifest_path
        )
        manifest_entry = PlanEntry(
            manifest_path, manifest_action, manifest_payload, manifest_exists
        )
        planned = _plan_with_manifest(planned, manifest_entry)

        if planned.conflicts:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="the plan has conflicts; nothing will be written",
                conflicts=tuple(planned.conflicts),
                warnings=tuple(planned.warnings),
                output_root=output_root,
                project_name=project_name,
            )

        # The review surface: every variant file plus the manifest (its
        # ``variant_key`` is None — the manifest summarises the run). What
        # the user reviewed is exactly what ``execute`` writes.
        variant_count = len(variant_records)
        entries = tuple(
            ConfigurationPlan(
                record["key"],
                entry.path,
                entry.action,
                entry.payload_fingerprint,
            )
            for record, entry in zip(variant_records, planned.entries[:variant_count])
        ) + (
            ConfigurationPlan(
                None,
                manifest_entry.path,
                manifest_entry.action,
                manifest_entry.payload_fingerprint,
            ),
        )
        return GenerationPlan(
            ok=True,
            entries=entries,
            conflicts=(),
            warnings=tuple(planned.warnings),
            manifest_data=manifest,
            format_version=max(format_versions.values()),
            project_name=project_name,
            output_root=output_root,
            reviewed=planned,
        )

    # -- the file-driven input workflow ------------------------------------------

    def plan_input_batch(
        self,
        path: str,
        output_root: str,
        kind: str = "ligand-smiles",
        overwrite_policy=None,
        path_policy=None,
        replace_key=None,
    ) -> GenerationPlan:
        """One input file of ``kind`` → one planned file per entry.

        Nothing is written. The whole planning half of the workflow: read the
        file through the kind's persistence reader, build one independent
        ``base + AddRecord`` spec per entry against a throwaway registry clone,
        validate the base and every variant through the full catalogue, then
        run the same transform/plan/manifest sequence as any other variant
        run.

        ``kind`` is what the user said the file holds
        (``batch_variants.INPUT_KINDS``) — protein, DNA or RNA sequences,
        SMILES ligands, or CCD-coded ligands — and it selects both the reader
        and the record builder, so a sequence can never be serialised as a
        ligand or the reverse.

        ``replace_key`` changes what an entry *is*: by default it adds a new
        entity; naming a base record makes each entry replace that record's
        sequence or representation instead, which is the shape a wild type, a
        placeholder or a lead compound needs. It is passed straight to the
        spec construction (the family check and the edit vocabulary live in
        ``app``), so both modes run this one plan/gate/transform sequence.

        No spec is committed to the project. A second run of the same file
        therefore does not refuse over keys that already exist; the only
        collision left is the output files themselves, which the overwrite
        policy reports (``Fail`` by default) rather than silently replacing.
        """
        project = self._projects._require_project()
        if project is None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.NOT_OPEN,
                message="no project is open",
            )
        if not output_root:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.INVALID_CHOICE,
                message="choose a folder for the generated files",
            )

        # The policies arrive as picker *names* from a front end or as
        # resolved objects from a caller that already made the choice; both
        # mean exactly one thing, and an unknown name is a refusal.
        overwrite, problem = _policy_argument(
            OVERWRITE_POLICIES, OverwritePolicy, overwrite_policy, "overwrite"
        )
        if problem is not None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.INVALID_CHOICE,
                message=problem,
            )
        path_choice, problem = _policy_argument(
            PATH_POLICIES, PathPolicy, path_policy, "path"
        )
        if problem is not None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.INVALID_CHOICE,
                message=problem,
            )

        # The base must be a complete job before its variants mean anything.
        refused = self._gate_base()
        if refused is not None:
            return refused

        _entries, specs, problem = self._variants.input_file_specs(
            path, kind, replace_key
        )
        if problem is not None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.INVALID_CHOICE,
                message=problem,
            )
        if not specs:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.EMPTY_EXPANSION,
                message="the file contains no usable entries",
            )

        try:
            variants = expand(project.configuration, specs)
        except (EditError, VariantSpecError) as error:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.EXPANSION_FAILED,
                message=str(error),
            )

        # The same authoritative validation an in-memory variant gets —
        # base first, then each variant against its own comparison data.
        detail = (
            self._validation.validate_specs(specs)
            if self._validation is not None
            else None
        )
        refused = self._variant_gate(detail)
        if refused is not None:
            return refused

        return self._plan_variants(
            variants, detail, output_root, overwrite, path_choice
        )

    def plan_ligand_batch(
        self, path: str, output_root: str, overwrite_policy=None, path_policy=None
    ) -> GenerationPlan:
        """The SMILES-ligand case of :meth:`plan_input_batch`.

        Kept because it names the case exactly: a caller that only ever reads
        ``name SMILES`` files does not have to know the kind vocabulary to say
        so, and it can never accidentally plan a different kind.
        """
        return self.plan_input_batch(
            path, output_root, "ligand-smiles", overwrite_policy, path_policy
        )

    def generate_input_batch(
        self,
        path: str,
        output_root: str,
        kind: str = "ligand-smiles",
        overwrite_policy=None,
        path_policy=None,
        replace_key=None,
    ):
        """Plan and write one input file of ``kind`` in a single step.

        Returns a ``LigandBatchOutput`` (the same outcome type every batch
        uses): the reviewed plan, what was written, what was skipped, the
        assets copied for the outputs, and any write errors. ``ok`` is True
        only when the plan succeeded **and** every file was written — a
        refusal writes nothing at all (the plan is all-or-nothing), and an
        execution error is reported per file rather than turned into a
        success message.

        ``copied_resources`` travels in the outcome because an asset copy is
        an output file that is not a plan entry: a front end that sums only
        ``written`` cannot report the run's real total.
        """
        plan = self.plan_input_batch(
            path, output_root, kind, overwrite_policy, path_policy, replace_key
        )
        if not plan.ok:
            return LigandBatchOutput(plan=plan, message=plan.message)
        result = self.execute(plan)
        return LigandBatchOutput(
            plan=plan,
            written=result.written,
            skipped=result.skipped,
            copied_resources=result.copied_resources,
            errors=result.errors,
            ok=result.ok and not result.errors,
            message=result.message or "",
        )

    def generate_ligand_batch(
        self, path: str, output_root: str, overwrite_policy=None, path_policy=None
    ):
        """The SMILES-ligand case of :meth:`generate_input_batch`."""
        return self.generate_input_batch(
            path, output_root, "ligand-smiles", overwrite_policy, path_policy
        )

    # -- execution (§15: writes only) --------------------------------------------

    def base_file_path(self, output_root: str) -> str:
        """Where ``plan_base`` writes the open job, without planning it.

        A front end that offers a one-click write has to name the file it is
        about to create *before* the click, and a second copy of the naming
        rule would let that label drift from what is actually written. Both
        routes therefore ask this method (``plan_base`` through the same
        ``_base_paths`` helper). Returns ``""`` when no job is open.
        """
        project = self._projects._require_project()
        if project is None:
            return ""
        return _base_paths(output_root, project.configuration.metadata.name)[2]

    def plan_base(
        self,
        output_root: str,
        overwrite_policy=None,
        path_policy=None,
    ) -> GenerationPlan:
        """The same generation pipeline for the base configuration itself.

        The base job is a complete job: the file is named after the
        project — ``<project>/<project>.json``, with the wire ``name``
        matching the project name (slug form) — through the same
        transform, encode, overwrite/asset discipline, and the same
        planner's decision helpers as a variant run. No variant is
        expanded and none is required: base generation is independent
        of variant creation, and no manifest is written (the manifest
        summarises a variant run; there is no variant). The core tiers
        gate the base before anything is transformed.
        """
        project = self._projects._require_project()
        if project is None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.NOT_OPEN,
                message="no project is open",
            )

        refused = self._gate_base()
        if refused is not None:
            return refused

        settings = project.settings or OutputSettings()
        overwrite = (
            OverwritePolicy(settings.overwrite_policy)
            if overwrite_policy is None
            else overwrite_policy
        )
        path_choice = (
            PathPolicy(settings.path_policy) if path_policy is None else path_policy
        )
        project_name = project.configuration.metadata.name

        # Steps 4–5: transform, resolve the §13.5 resource paths into the
        # project directory, rewrite, then encode. The wire ``name`` is
        # the project's slug — no variant directory component is
        # appended; the value inside the file and the file name agree.
        try:
            project_slug = slug_name(project_name)
            result = to_wire(project.configuration)
        except TransformError as error:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.TRANSFORM_FAILED,
                message=str(error),
            )

        # Step 6: the output plan. The base file sits directly under the
        # project directory (not a per-variant subdirectory), so the plan
        # is assembled from the planner's own decision helpers: same
        # §13.5 path-policy resolution and §13.3 action table.
        filesystem = self._filesystem if self._filesystem is not None else OsFileView()
        _slug, base_dir, base_file = _base_paths(output_root, project_name)
        resources, warnings = resolve_resources_into(
            result.external_resources,
            output_root,
            base_dir,
            path_choice,
            filesystem,
        )
        emitted = {}
        for resource in resources:
            if resource.emitted_path is not None and resource.raw_path != resource.emitted_path:
                emitted.setdefault(resource.wire_field, {})[resource.raw_path] = (
                    resource.emitted_path
                )
        try:
            document = with_emitted_resource_paths(
                with_wire_job_name(result.document, project_slug), emitted
            )
            payload = encode(document)
        except TransformError as error:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.TRANSFORM_FAILED,
                message=str(error),
            )

        file_path, action, exists = decide_action(
            base_file, payload, overwrite, filesystem
        )
        # An identical file is planned as ``overwrite`` too (same bytes, same
        # result). This flag is the difference a front end needs when it wants
        # to ask before replacing and stay silent when nothing changes.
        different_content = bool(
            action == "overwrite" and exists and filesystem.read(file_path) != payload
        )
        conflicts = (conflict_message(file_path),) if action == "conflict" else ()
        if conflicts:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="the plan has conflicts; nothing will be written",
                conflicts=conflicts,
                warnings=tuple(warnings),
                output_root=output_root,
                project_name=project_name,
            )

        # The review surface for execute(): what the user confirmed is
        # exactly what execute() writes (the same discipline as plan()).
        reviewed = OutputPlan(
            project_slug=project_slug,
            output_root=output_root,
            overwrite_policy=overwrite,
            path_policy=path_choice,
            entries=(PlanEntry(file_path, action, payload, exists),),
            resources=resources,
            conflicts=(),
            warnings=tuple(warnings),
        )
        return GenerationPlan(
            ok=True,
            entries=(
                ConfigurationPlan(
                    BASE_PLAN_KEY,
                    file_path,
                    action,
                    reviewed.entries[0].payload_fingerprint,
                    different_content,
                ),
            ),
            conflicts=(),
            warnings=tuple(warnings),
            format_version=result.version,
            project_name=project_name,
            output_root=output_root,
            reviewed=reviewed,
        )

    def plan_save(
        self,
        destination: str,
        name: str = None,
        overwrite: bool = False,
        path_policy=None,
    ) -> GenerationPlan:
        """Plan writing the current configuration to an explicit file path.

        The workflow's save action writes wherever the user asks, not into
        the ``<output>/<slug>/<slug>.json`` layout the bulk generate route
        uses. The *content* discipline is unchanged: the same ``to_wire``
        → ``encode`` path, the same §13.5 resource resolution and §13.3
        action table, and the same ``execute`` writes exactly the reviewed
        bytes. The configuration-only gate runs first; it needs no JSON run
        and no output environment.

        ``name`` overrides the wire ``name`` (the slug of it is what lands
        inside the file) — the variant save uses it so the file carries the
        variant's name while the base job's model name stays untouched.
        ``overwrite`` is the UI's *confirmed* decision: the menu asks before
        replacing an existing file, so the plan may overwrite it.
        """
        project = self._projects._require_project()
        if project is None:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.NOT_OPEN,
                message="no project is open",
            )

        # Saving is an export like any other: the same core tiers apply. No
        # JSON run or output environment is needed for them.
        refused = self._gate_base()
        if refused is not None:
            return refused

        settings = project.settings or OutputSettings()
        chosen_policy = (
            OverwritePolicy("Overwrite")
            if overwrite
            else OverwritePolicy(settings.overwrite_policy)
        )
        path_choice = PathPolicy(settings.path_policy) if path_policy is None else path_policy
        wire_name = name or project.configuration.metadata.name
        # A bare file name has no directory component; resolve it against the
        # working directory so dirname() is never the empty string (which the
        # executor would try to makedirs).
        destination = os.path.abspath(destination)
        try:
            slug_wire = slug_name(wire_name)
            result = to_wire(project.configuration)
        except TransformError as error:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.TRANSFORM_FAILED,
                message=str(error),
            )

        filesystem = self._filesystem if self._filesystem is not None else OsFileView()
        directory = os.path.dirname(destination)
        resources, warnings = resolve_resources_into(
            result.external_resources,
            directory,
            directory,
            path_choice,
            filesystem,
        )
        emitted = {}
        for resource in resources:
            if resource.emitted_path is not None and resource.raw_path != resource.emitted_path:
                emitted.setdefault(resource.wire_field, {})[resource.raw_path] = (
                    resource.emitted_path
                )
        try:
            document = with_emitted_resource_paths(
                with_wire_job_name(result.document, slug_wire), emitted
            )
            payload = encode(document)
        except TransformError as error:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.TRANSFORM_FAILED,
                message=str(error),
            )

        file_path, action, exists = decide_action(
            destination, payload, chosen_policy, filesystem
        )
        conflicts = (conflict_message(file_path),) if action == "conflict" else ()
        if conflicts:
            return GenerationPlan(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="the file already exists with different content; nothing was written",
                conflicts=conflicts,
                warnings=tuple(warnings),
                output_root=directory,
                project_name=wire_name,
            )

        reviewed = OutputPlan(
            project_slug=slug_wire,
            output_root=directory,
            overwrite_policy=chosen_policy,
            path_policy=path_choice,
            entries=(PlanEntry(file_path, action, payload, exists),),
            resources=resources,
            conflicts=(),
            warnings=tuple(warnings),
        )
        return GenerationPlan(
            ok=True,
            entries=(
                ConfigurationPlan(
                    BASE_PLAN_KEY,
                    file_path,
                    action,
                    reviewed.entries[0].payload_fingerprint,
                ),
            ),
            conflicts=(),
            warnings=tuple(warnings),
            format_version=result.version,
            project_name=wire_name,
            output_root=directory,
            reviewed=reviewed,
        )

    def execute(self, generation_plan: GenerationPlan) -> PlanOutput:
        """Write what was reviewed. Nothing here re-derives content: the
        payloads travel inside the plan object ``plan()`` returned, so
        executing one plan can never write another one's bytes (BUG-011)."""
        if generation_plan is None or not generation_plan.ok:
            return PlanOutput(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="execute needs a successful plan; run plan() first",
            )
        planned = generation_plan.reviewed
        if planned is None:
            return PlanOutput(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="no reviewed plan is held; run plan() first",
            )
        if planned.conflicts:
            return PlanOutput(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="the plan has conflicts; nothing was written",
                errors=tuple(planned.conflicts),
            )
        result = execute_plan(planned)
        written = tuple(
            outcome.path for outcome in result.outcomes if outcome.written
        )
        skipped = tuple(
            outcome.path for outcome in result.outcomes if not outcome.written
        )
        return PlanOutput(
            ok=not result.errors,
            written=written,
            skipped=skipped,
            copied_resources=tuple(result.copied_resources),
            errors=tuple(result.errors),
        )


# -- module helpers ------------------------------------------------------------------


def _named_policy(policies, policy_class, name, label):
    """``(policy, None)`` for a picker name, or ``(None, refusal message)``.

    The policy sets are closed; matching by name keeps the front end's
    vocabulary in sync with the manifest's (policies are recorded by name).
    ``None`` means "use the project's setting", the same default ``plan``
    and ``plan_base`` already apply.
    """
    if name is None:
        return None, None
    for policy in policies:
        if policy.name == name:
            return policy, None
    return None, (
        "%r is not a supported %s policy; choose one of: %s"
        % (name, label, ", ".join(policy.name for policy in policies))
    )


def _policy_argument(policies, policy_class, value, label):
    """A policy *object* or a picker *name* → ``(policy, None)``.

    ``None`` means "use the project's own setting", the same default every
    planning route applies. Front ends send names (``output_defaults``
    returns names); a caller that already resolved one of the closed set may
    pass the policy itself without round-tripping through its name.
    """
    if value is not None and isinstance(value, policy_class):
        return value, None
    return _named_policy(policies, policy_class, value, label)


def _entry_by_file_name(planned, file_name: str):
    """The planned entry whose file name matches ``file_name`` (paths are
    platform-joined, so compare the basename)."""
    for entry in planned.entries:
        if os.path.basename(entry.path) == file_name:
            return entry
    return None


def _manifest_decision(payload: bytes, overwrite_policy, filesystem, path):
    """The manifest follows the same §13.3 action table as any planned
    file — delegated to ``output.plan.decide_action``, the single home of
    that decision."""
    from configbuilder.output.plan import decide_action

    if filesystem is None:
        from configbuilder.output.plan import OsFileView

        filesystem = OsFileView()
    return decide_action(path, payload, overwrite_policy, filesystem)


def _plan_with_manifest(planned, manifest_entry):
    """The plan with the manifest entry appended (manifest last: it
    summarises the run, so it sorts after the variant directories)."""
    from configbuilder.output.plan import OutputPlan

    return OutputPlan(
        project_slug=planned.project_slug,
        output_root=planned.output_root,
        overwrite_policy=planned.overwrite_policy,
        path_policy=planned.path_policy,
        entries=tuple(planned.entries) + (manifest_entry,),
        resources=planned.resources,
        conflicts=planned.conflicts,
        warnings=planned.warnings,
    )


def _base_paths(output_root, project_name):
    """The base job's own three path pieces: ``(slug, folder, file)``.

    ``<output_root>/<slug>/<slug>.json`` — the file's name and the wire
    ``name`` agree because both come from this slug. Kept in one place so
    ``plan_base`` and ``base_file_path`` cannot disagree about it.
    """
    slug = slug_name(project_name)
    directory = os.path.join(output_root, slug)
    return slug, directory, os.path.join(directory, slug + ".json")
