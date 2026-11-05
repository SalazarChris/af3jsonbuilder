"""Project lifecycle (IMPLEMENTATION_PLAN.md §15): ``new``, ``open``,
``import_json_preview`` / ``import_json_commit``, ``is_dirty``.

The workflow is JSON-first and in-memory: the job in hand lives in memory
and the only save target is an ordinary AF3 JSON file written on request.
The former ``.cbproj`` working-copy autosave, its internal store and its
``load_saved_work`` recovery entry point were removed with the menu rework
(2026-10): the only supported way to resume a saved job is to open its
JSON. ``open`` remains as the general project-file reader used by the
tests, and ``is_dirty`` as the edit-tracking flag a front end reads.

Every operation returns a result object; user-caused problems are
findings or failure reasons, never exceptions.
"""

from __future__ import annotations

import os

from configbuilder.app.results import FailureReason, ImportPreview, LoadOutput
from configbuilder.model import ModelError
from configbuilder.persistence import (
    FutureVersionError,
    OutputSettings,
    PersistenceError,
    Project,
    load as _load,
)

__all__ = ["ProjectService"]


class ProjectService:
    """Owns the currently open project and loads JSON into it.

    Persistence discipline: the job is edited in memory, and the
    user-visible save action writes **AF3 JSON** through the generation
    pipeline. Nothing is autosaved behind the user's back.
    """

    def __init__(self, validate=None) -> None:
        self._project = None  # type: Optional[Project]
        self._dirty = False
        self._validate = validate
        self._automatic_names = 0  # how many automatic job names this session minted
        # The parse result of the most recent successful preview, waiting to
        # be confirmed: ``(path, configuration, notes)``. It is what the
        # confirm installs, so the file cannot change under the user between
        # the screen and the answer.
        self._prepared_import = None

    # -- state ---------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._project is not None

    @property
    def is_dirty(self) -> bool:
        """True when the in-memory project differs from the last save."""
        return self._dirty

    @property
    def project(self):
        """The open project, or ``None``. Read-only for front ends."""
        return self._project

    # -- operations (§15) ------------------------------------------------------

    def new(self, name: str = None) -> Project:
        """Start a fresh project. Never fails: nothing exists to corrupt.

        The job arrives with the standard defaults already applied (the
        policy in ``app/status.py``): a job name when the caller supplies
        one and an automatic ``config-NNN`` name otherwise, the project's
        default seed set, and the default format-version pin — so an
        export never needs a naming/seeding/version ritual first. Only the
        entities are genuinely the user's to supply; nothing here invents
        biological data. Every default stays editable: the job settings
        menu can change the name, the seeds, and the pin at any time, and
        ``Unverified`` remains the explicit refusal-to-pin state.
        """
        from configbuilder.model import Configuration, ConfigurationMetadata, FormatTarget, SeedSet
        from configbuilder.model.configuration import Pinned
        from configbuilder.identity import IdentityRegistry
        from configbuilder.app.status import (
            DEFAULT_SEED_VALUES,
            DEFAULT_VERSION,
            default_job_name,
        )

        job_name = (name or "").strip()
        if not job_name:
            self._automatic_names += 1
            job_name = default_job_name(self._automatic_names)
        configuration = Configuration(
            metadata=ConfigurationMetadata(job_name),
            seeds=SeedSet(list(DEFAULT_SEED_VALUES)),
            records=(),
            identity=IdentityRegistry(),
            format_target=FormatTarget(version_selection=Pinned(DEFAULT_VERSION)),
        )
        self._project = Project(
            configuration=configuration,
            specs=(),
            settings=OutputSettings(),
        )
        self._dirty = True
        return self._project

    # -- AF3 JSON import (§7 of the import feature; the same canonical model) --

    def _directory_refusal(self, path: str) -> str:
        """The reason a directory cannot be imported, or ``""``.

        Pointing the picker at a folder is an ordinary mistake — the file
        listing shows directories too. Windows reports *reading* one as
        ``Permission denied``, which sends the user looking for a
        permissions problem they do not have; say what is actually wrong.
        """
        if os.path.isdir(path):
            return "that path is a directory, not an AF3 JSON file"
        return ""

    def _prepare_import(self, path: str):
        """Parse an AF3 JSON file for import.

        Returns ``(configuration, notes, refusal)``: on success ``refusal``
        is ``None``, and on any user-caused failure it is a
        ``(FailureReason, message)`` pair instead of an exception. The
        preview and a commit that has no preview to reuse both go through
        this one function because they must parse *identically* — the two
        copies had already drifted once, over what a directory path should
        say (BUG-018).
        """
        import os

        from configbuilder.transform import (
            WireImportError,
            from_wire,
            rebase_resource_paths,
        )

        refusal = self._directory_refusal(path)
        if refusal:
            return None, (), (FailureReason.IO_ERROR, refusal)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                import json as _json

                document = _json.load(handle)
        except OSError as error:
            return None, (), (FailureReason.IO_ERROR, str(error))
        except ValueError as error:
            return None, (), (
                FailureReason.CORRUPT_FILE,
                "the file is not valid JSON: %s" % (error,),
            )
        # An AF3 file's relative paths mean "relative to this file"; resolve
        # them before the model is built, so a self-contained job (assets
        # copied beside it) can be reopened and re-saved without its files
        # appearing to have vanished.
        rebase_resource_paths(document, os.path.dirname(os.path.abspath(path)))
        try:
            configuration, notes = from_wire(document)
        except WireImportError as error:
            return None, (), (FailureReason.CORRUPT_FILE, str(error))
        except (ModelError, ValueError, TypeError) as error:
            return None, (), (FailureReason.CORRUPT_FILE, str(error))
        return configuration, notes, None

    def import_json_preview(self, path: str) -> ImportPreview:
        """Parse and validate an AF3 JSON file **without installing it**.

        Returns the summary rows and any ImportNotes for the confirm
        screen; the current project is untouched whatever happens here.

        A successful preview is also kept as the *pending* import, so the
        confirm that follows installs exactly the content this screen
        described. A failed preview, or a preview of another path, replaces
        or clears whatever was pending.
        """
        self._prepared_import = None
        configuration, notes, refusal = self._prepare_import(path)
        if refusal is not None:
            return ImportPreview(
                ok=False, failure_reason=refusal[0], message=refusal[1]
            )
        self._prepared_import = (path, configuration, notes)
        return ImportPreview(
            ok=True, summary=self._import_summary(configuration), notes=notes
        )

    def import_json_commit(self, path: str) -> LoadOutput:
        """Install the previously previewed file as the current project.

        What gets installed is the document that was **previewed**: the
        parse result travels from ``import_json_preview`` as the pending
        import, so what the confirm screen described is exactly what lands,
        whatever happens to the file in between (these used to be two
        independent reads of the file). The pending import is consumed — a
        second commit, and any commit with no matching preview, reads and
        parses the file itself, exactly as before.

        The file becomes the base configuration — a normal job, editable
        through every existing service, variant-able, and generatable;
        no "imported" special state exists. The original file is never
        modified (the import output goes through the normal generation
        naming, which derives its own path from the project name).
        """
        prepared = self._prepared_import
        self._prepared_import = None
        if prepared is not None and prepared[0] == path:
            configuration, notes = prepared[1], prepared[2]
        else:
            configuration, notes, refusal = self._prepare_import(path)
            if refusal is not None:
                return LoadOutput(
                    ok=False, failure_reason=refusal[0], message=refusal[1]
                )
        report = None
        if self._validate is not None:
            report = self._validate(configuration)
        self._project = Project(
            configuration=configuration,
            specs=(),
            settings=OutputSettings(),
        )
        self._dirty = True
        return LoadOutput(
            ok=True,
            project=self._project,
            warnings=tuple(note.detail for note in notes),
            findings=report,
        )

    def _import_summary(self, configuration) -> dict:
        """Summary data for the confirm screen — plain data from the
        model; the UI renders wording ("app returns data, ui renders",
        plan §5.3 rule 6)."""
        from configbuilder.model.records import FamilyARecord, FamilyBRecord, FamilyCRecord, ComponentRecord

        records = configuration.records
        family_names = {
            FamilyARecord: "protein",
            FamilyBRecord: "rna",
            FamilyCRecord: "dna",
            ComponentRecord: "ligand",
        }
        families = {}
        for record in records:
            name = family_names.get(type(record), type(record).__name__)
            families.setdefault(name, []).append(record)
        return {
            "job_name": configuration.metadata.name,
            "seed_values": [seed.value for seed in configuration.seeds.seeds],
            "entity_count": len(records),
            "family_counts": {name: len(rows) for name, rows in sorted(families.items())},
            "record_ids": [record.ids.primary.value for record in records],
        }

    def open(self, path: str) -> LoadOutput:
        """Load a project file. Corruption, future versions, and IO
        problems are reported, never raised."""
        try:
            result = _load(path, validate=self._validate)
        except FutureVersionError as error:
            return LoadOutput(
                ok=False,
                failure_reason=FailureReason.FUTURE_VERSION,
                message=str(error),
            )
        except PersistenceError as error:
            return LoadOutput(
                ok=False,
                failure_reason=FailureReason.CORRUPT_FILE,
                message=str(error),
            )
        except OSError as error:
            return LoadOutput(
                ok=False,
                failure_reason=FailureReason.IO_ERROR,
                message=str(error),
            )
        self._project = result.project
        self._dirty = False
        return LoadOutput(
            ok=True,
            project=result.project,
            warnings=tuple(result.warnings()) if callable(getattr(result, "warnings", None)) else (),
            findings=result.report,
            upgraded_from=result.upgraded_from,
        )

    # -- internal hooks used by the sibling services ---------------------------

    def _require_project(self):
        if self._project is None:
            return None
        return self._project

    def _replace_project(self, project: Project) -> None:
        self._project = project
        self._dirty = True

    def _specs(self):
        project = self._require_project()
        return project.specs if project is not None else ()

    def _with_specs(self, specs):
        project = self._require_project()
        if project is None:
            return None
        self._replace_project(project.with_specs(tuple(specs)))
        return project
