"""Result objects (IMPLEMENTATION_PLAN.md §15).

``app`` exposes the only API a front end needs, and every operation
returns a result object: user-caused problems are findings, not
exceptions. These types are plain data holders — the menu reads them;
nothing here raises for conditions the user can fix.

The types are deliberately app-owned (plan §5.3 rule 6: ``ui`` imports
``app`` and ``model.traceability`` only, so layer types must not leak
into the result surface).
"""

from __future__ import annotations


__all__ = [
    "FailureReason",
    "ConfigurationOutput",
    "ExpandOutput",
    "FilePreview",
    "BatchCounts",
    "GenerationPlan",
    "LigandBatchOutput",
    "LoadOutput",
    "MutationOutput",
    "PlanOutput",
    "VariantValidationOutput",
    "batch_counts",
]


BASE_PLAN_KEY = "base"
"""The label the base configuration's own plan entry carries.

Base generation is a first-class operation — the base job is a complete
job — and its file is named after the project itself; this key only
marks the plan entry, it is not part of the file name.
"""


class FailureReason:
    """Stable, matchable reasons a service operation returned no value.

    A front end switches on these instead of parsing messages. The
    companion ``message`` is human-readable; ``rule_id`` names the
    blocking catalogue rule where the failure came from validation.
    """

    NOT_OPEN = "not_open"
    VALIDATION_BLOCKED = "validation_blocked"
    EXPANSION_FAILED = "expansion_failed"
    TRANSFORM_FAILED = "transform_failed"
    EMPTY_EXPANSION = "empty_expansion"
    IO_ERROR = "io_error"
    CORRUPT_FILE = "corrupt_file"
    FUTURE_VERSION = "future_version"
    UNKNOWN_RECORD = "unknown_record"
    NO_PATH = "no_path"
    INVALID_CHOICE = "invalid_choice"


class MutationOutput:
    """Outcome of a mutation (``ConfigurationService`` operations).

    ``findings`` carries what validation reports about the project after
    the change (empty when the service was built with validation
    disabled); ``unknown_record`` reports an edit aimed at a record key
    identity does not know — the user must pick a real record.
    """

    __slots__ = ("ok", "failure_reason", "message", "findings")

    def __init__(self, ok, failure_reason=None, message="", findings=()) -> None:
        self.ok = bool(ok)
        self.failure_reason = failure_reason
        self.message = message or ""
        self.findings = tuple(findings)

    def __repr__(self) -> str:
        if self.ok:
            return "MutationOutput(ok=True, findings=%d)" % len(self.findings)
        return "MutationOutput(ok=False, reason=%r, message=%r)" % (
            self.failure_reason,
            self.message,
        )


class LoadOutput:
    """Outcome of ``ProjectService.open``.

    ``warnings`` carries schema-upgrade notices; ``findings`` the
    validation report computed at load (when a validator is installed);
    ``upgraded_from`` the schema version the file was migrated from.
    """

    __slots__ = ("ok", "failure_reason", "message", "project", "warnings", "findings", "upgraded_from")

    def __init__(self, ok, project=None, failure_reason=None, message="", warnings=(), findings=None, upgraded_from=None) -> None:
        self.ok = bool(ok)
        self.project = project
        self.failure_reason = failure_reason
        self.message = message or ""
        self.warnings = tuple(warnings)
        self.findings = findings
        self.upgraded_from = upgraded_from

    def __repr__(self) -> str:
        return "LoadOutput(ok=%r, warnings=%d)" % (self.ok, len(self.warnings))


class ConfigurationOutput:
    """Outcome of ``ValidationService.validate_base``."""

    __slots__ = ("ok", "failure_reason", "message", "report")

    def __init__(self, ok, report=None, failure_reason=None, message="") -> None:
        self.ok = bool(ok)
        self.report = report
        self.failure_reason = failure_reason
        self.message = message or ""

    def __repr__(self) -> str:
        return "ConfigurationOutput(ok=%r)" % self.ok


class VariantValidationOutput:
    """Outcome of ``ValidationService.validate_all``: base report, the
    per-variant reports, and the combined documents the checks ran on.

    ``failure_reason`` is set when a committed variant could not even be
    expanded, so no report exists for it: the base report is still carried
    (it was computed first) and the variant half is empty — the UI says why
    instead of dying on an exception (BUG-022).
    """

    __slots__ = (
        "base_report",
        "variant_reports",
        "variant_documents",
        "base_document",
        "failure_reason",
        "message",
    )

    def __init__(
        self,
        base_report,
        variant_reports=None,
        variant_documents=None,
        base_document=None,
        failure_reason=None,
        message="",
    ) -> None:
        self.base_report = base_report
        self.variant_reports = dict(variant_reports or {})
        self.variant_documents = dict(variant_documents or {})
        self.base_document = base_document
        self.failure_reason = failure_reason
        self.message = message or ""

    def __repr__(self) -> str:
        if self.failure_reason is not None:
            return "VariantValidationOutput(reason=%r)" % (self.failure_reason,)
        return "VariantValidationOutput(variants=%d)" % len(self.variant_reports)


class ImportPreview:
    """A read-only look at an AF3 JSON file (nothing installed yet).

    ``summary`` carries the display rows for the confirm screen (the
    job picture data, keyed like ``SummaryService``'s output);
    ``notes`` are the ImportNotes for unsupported-but-tolerated fields.
    The current project is untouched until ``commit`` is called.
    """

    __slots__ = ("ok", "failure_reason", "message", "summary", "notes")

    def __init__(self, ok, summary=None, notes=(), failure_reason=None, message="") -> None:
        self.ok = bool(ok)
        self.failure_reason = failure_reason
        self.message = message or ""
        self.summary = summary or {}
        self.notes = tuple(notes)

    def __repr__(self) -> str:
        return "ImportPreview(ok=%r, notes=%d)" % (self.ok, len(self.notes))


class FilePreview:
    """A read-only look at a batch input file (no variants created).

    ``entries`` carries the detected sequence texts in file order; the
    committed batch re-reads the file through the same persistence
    reader, so what is confirmed is exactly what would be created.

    ``planned`` is how many variants the commit would create (Stage 8),
    computed by building the very specs ``generate_from_file`` builds —
    against a throwaway registry clone — so the count and any refusal are
    known *before* the user commits. ``None`` means "not determined" (no
    project is open, or the file itself was refused).
    """

    __slots__ = ("ok", "message", "entries", "planned")

    def __init__(self, ok, message="", entries=(), planned=None) -> None:
        self.ok = bool(ok)
        self.message = message or ""
        self.entries = tuple(entries)
        self.planned = planned

    def __repr__(self) -> str:
        return "FilePreview(ok=%r, entries=%d)" % (self.ok, len(self.entries))


class ExpandOutput:
    """Outcome of ``VariantService.expand`` / ``preview``."""

    __slots__ = ("ok", "failure_reason", "message", "variants")

    def __init__(self, ok, variants=(), failure_reason=None, message="") -> None:
        self.ok = bool(ok)
        self.variants = tuple(variants)
        self.failure_reason = failure_reason
        self.message = message or ""

    def __repr__(self) -> str:
        return "ExpandOutput(ok=%r, variants=%d)" % (self.ok, len(self.variants))


class ConfigurationPlan:
    """One planned input file, as plain data for review.

    ``payload_fingerprint`` is the SHA-256 of the exact bytes that will
    be written; ``action`` is ``create`` / ``overwrite`` / ``skip`` /
    ``conflict`` (plan §13.3).

    ``different_content`` is True only when the file exists, will be
    written over, and the bytes on disk are *not* the bytes about to be
    written. An identical file is also labelled ``overwrite`` (it is
    rewritten with the same bytes, which changes nothing), so a front end
    that wants to ask before replacing needs this distinction rather than
    the action word.
    """

    __slots__ = (
        "variant_key",
        "path",
        "action",
        "payload_fingerprint",
        "different_content",
    )

    def __init__(
        self,
        variant_key,
        path,
        action,
        payload_fingerprint,
        different_content=False,
    ) -> None:
        self.variant_key = variant_key
        self.path = path
        self.action = action
        self.payload_fingerprint = payload_fingerprint
        self.different_content = different_content

    def __repr__(self) -> str:
        return "ConfigurationPlan(%r, %s, %s)" % (self.variant_key, self.path, self.action)


class GenerationPlan:
    """Outcome of ``GenerationService.plan``.

    ``conflicts`` non-empty means nothing may be written; ``warnings``
    carries path-hazard notices for the user; ``manifest_data`` is the
    manifest's deterministic payload — the bytes that are written, with no
    per-run timestamp, so a regenerated manifest is byte-identical (its
    ``run_info`` companion is available in ``output`` for diagnostics and is
    deliberately left out of the file).
    """

    __slots__ = (
        "ok",
        "failure_reason",
        "message",
        "entries",
        "conflicts",
        "warnings",
        "manifest_data",
        "format_version",
        "project_name",
        "output_root",
        "findings",
        "reviewed",
        "refused_scope",
    )

    def __init__(
        self,
        ok,
        entries=(),
        conflicts=(),
        warnings=(),
        manifest_data=None,
        format_version=None,
        project_name="",
        output_root="",
        failure_reason=None,
        message="",
        findings=(),
        reviewed=None,
        refused_scope="",
    ) -> None:
        self.ok = bool(ok)
        self.entries = tuple(entries)
        self.conflicts = tuple(conflicts)
        self.warnings = tuple(warnings)
        self.manifest_data = manifest_data
        self.format_version = format_version
        self.project_name = project_name
        self.output_root = output_root
        self.failure_reason = failure_reason
        self.message = message or ""
        # Blocking findings attached when a refusal was caused by validation
        # (VALIDATION_BLOCKED): the UI renders these instead of leaving the
        # user with a message that names no cause. Empty otherwise.
        self.findings = tuple(findings)
        # The reviewed ``output.OutputPlan`` this result describes. It travels
        # *inside* the result so ``execute`` writes the plan it was handed
        # rather than whatever was planned last — a service-held "last plan"
        # made two plans in a row ambiguous (BUG-011).
        self.reviewed = reviewed
        # Which half a VALIDATION_BLOCKED refusal came from: "base" or
        # "variant". The page labels its findings accordingly.
        self.refused_scope = refused_scope

    def __repr__(self) -> str:
        return "GenerationPlan(ok=%r, entries=%d, conflicts=%d)" % (
            self.ok,
            len(self.entries),
            len(self.conflicts),
        )


class BatchCounts:
    """What one file-driven run produced, counted by role rather than by row.

    The audit found the two front ends describing the same run with
    different totals: the console counted every plan entry, so the manifest
    was reported as one more "file", while the desktop could not mention
    copied assets at all because the batch outcome did not carry them. A
    front end that counts plan rows cannot tell a configuration from a
    manifest; this type counts only the roles.

    ``records`` is the number of input records that produced a planned
    configuration. For DNA one record is one configuration even though the
    entity is the supplied strand plus its reverse complement, so the count
    matches the file the user gets, not the number of chains inside it.
    """

    __slots__ = ("records", "configurations", "manifests", "assets", "total")

    def __init__(self, records=0, configurations=0, manifests=0, assets=0) -> None:
        self.records = int(records)
        self.configurations = int(configurations)
        self.manifests = int(manifests)
        self.assets = int(assets)
        self.total = self.configurations + self.manifests + self.assets

    def __repr__(self) -> str:
        return "BatchCounts(records=%d, configurations=%d, manifests=%d, assets=%d)" % (
            self.records,
            self.configurations,
            self.manifests,
            self.assets,
        )


def batch_counts(output) -> "BatchCounts":
    """Count a finished batch run's outputs by role.

    Configurations and manifests are told apart by the plan entry's
    ``variant_key`` (None is the manifest), and only files ``execute``
    reports as written are counted — a skipped or refused file was not
    written and must not appear in a total. Assets come from the executor's
    own copy report, which is why the batch outcome carries them.
    """
    plan = getattr(output, "plan", None)
    if plan is None or not plan.ok:
        return BatchCounts()
    entries = tuple(getattr(plan, "entries", ()))
    configuration_paths = {
        entry.path for entry in entries if getattr(entry, "variant_key", None) is not None
    }
    manifest_paths = {
        entry.path for entry in entries if getattr(entry, "variant_key", None) is None
    }
    written = tuple(getattr(output, "written", ()))
    configurations = sum(1 for path in written if path in configuration_paths)
    manifests = sum(1 for path in written if path in manifest_paths)
    assets = len(tuple(getattr(output, "copied_resources", ())))
    return BatchCounts(
        records=len(configuration_paths),
        configurations=configurations,
        manifests=manifests,
        assets=assets,
    )


class LigandBatchOutput:
    """Outcome of the one-step ligand file workflow.

    ``plan`` is the reviewed ``GenerationPlan`` (it carries the files, their
    actions, conflicts and warnings); ``written`` / ``skipped`` /
    ``copied_resources`` / ``errors`` come from ``execute``, so a front end
    reports what actually landed on disk rather than what was planned.
    ``ok`` is True only when planning succeeded and nothing failed to write:
    the flow never claims success for a batch it did not write in full.

    ``copied_resources`` (``(source, destination)`` pairs) is what makes an
    accurate total possible: copied assets are output files that are not
    plan entries, so a summary built only from ``written`` under-reports the
    run.
    """

    __slots__ = (
        "ok",
        "plan",
        "written",
        "skipped",
        "copied_resources",
        "errors",
        "message",
    )

    def __init__(
        self,
        plan=None,
        written=(),
        skipped=(),
        copied_resources=(),
        errors=(),
        ok=False,
        message="",
    ) -> None:
        self.plan = plan
        self.written = tuple(written)
        self.skipped = tuple(skipped)
        self.copied_resources = tuple(copied_resources)
        self.errors = tuple(errors)
        self.ok = bool(ok)
        self.message = message or ""

    def __repr__(self) -> str:
        return "LigandBatchOutput(ok=%r, written=%d, errors=%d)" % (
            self.ok,
            len(self.written),
            len(self.errors),
        )


class PlanOutput:
    """Outcome of ``GenerationService.execute``."""

    __slots__ = ("ok", "failure_reason", "message", "written", "skipped", "copied_resources", "errors")

    def __init__(self, ok, written=(), skipped=(), copied_resources=(), errors=(), failure_reason=None, message="") -> None:
        self.ok = bool(ok)
        self.written = tuple(written)
        self.skipped = tuple(skipped)
        # Copied resource paths, like every other collection here, as a tuple.
        self.copied_resources = tuple(copied_resources)
        self.errors = tuple(errors)
        self.failure_reason = failure_reason
        self.message = message or ""

    def __repr__(self) -> str:
        return "PlanOutput(ok=%r, written=%d, errors=%d)" % (
            self.ok,
            len(self.written),
            len(self.errors),
        )
