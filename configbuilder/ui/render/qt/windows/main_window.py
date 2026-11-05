"""The application window: one shell over the pages, plus the job lifecycle.

What this window owns is navigation and the order of operations, never
domain work. The open job lives in ``ProjectService``; the pages re-read it
through :class:`~configbuilder.ui.render.qt.state.GuiState` whenever the
state says it changed.

The job lifecycle has exactly one visible home, the command bar:

- **New Job** starts a fresh job through ``ProjectService.new`` — the
  service's own default policy supplies the name, seeds and version pin.
- **Open AF3 JSON…** previews an existing document and imports it.
- **Save JSON…** is the one save/export action. It asks for a destination and
  then runs the *generation service's* two-step workflow: ``plan_save``
  (validate, transform, encode, decide the overwrite action) and then
  ``execute`` (write exactly the reviewed bytes, copying referenced assets
  beside them). This window never assembles a wire document, never serializes
  JSON, never allocates an identifier and never writes a file itself.

There used to be a second, folder-based write route (the sidebar's FILE footer
with a one-click "Save to folder", and a Generate destination that wrote the
same job into a prefilled folder and then printed its plan and result). Both
only repeated what **Save JSON…** already does, so they are gone: the sidebar
now carries the working destinations only, and one dialog decides where the
document goes.

Feedback is the status bar's, plus a modal only when something is refused.
The technical detail behind a refusal (the service's reason, the blocking
findings, the exception) goes to this module's logger rather than onto the
screen: the window shows the sentence a user can act on.

Unsaved changes are never discarded silently: New Job, opening another file
and closing the window all ask first (``confirm_discard``), and Cancel keeps
the job. Every modal is an assignable attribute, which is how the offscreen
tests answer it without a click.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from configbuilder.app.results import FailureReason
from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.qt.dialogs import (
    ImportPreviewDialog,
    ask_save_path,
    confirm_discard,
    confirm_overwrite,
    show_failure,
    show_problem,
)
from configbuilder.ui.render.qt.pages import (
    AdvancedPage,
    EntitiesPage,
    OverviewPage,
    PreviewPage,
)
from configbuilder.ui.render.qt.style import apply_style
from configbuilder.ui.render.qt.widgets import app_mark_pixmap, navigation_icon

__all__ = ["MainWindow"]

#: Where a refusal's technical detail goes. The user sees the sentence that
#: tells them what to do; the service's reason, the findings, the conflicts and
#: the exception stay here for whoever has to diagnose it.
_log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """The review, settings and save window over the current job."""

    def __init__(self, state, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self.setWindowTitle(_text("gui.window_title"))
        self.setMinimumSize(940, 640)
        # How a refusal reaches the user. The defaults are the modal boxes;
        # the tests replace them with recorders, because a modal waits for a
        # click that an offscreen test can never give. Whatever reports, the
        # refusal is also kept and shown on the status line.
        self.failure_reporter = show_failure
        self.problem_reporter = show_problem
        self.discard_confirmer = confirm_discard
        self.overwrite_confirmer = confirm_overwrite
        self.save_path_chooser = ask_save_path
        self._last_failure = ""
        self._last_problem = ""
        # One save at a time: a second click must not plan, ask and write over
        # the first operation's half-finished state.
        self._saving = False
        self._build()
        apply_style(self)
        self._state.project_changed.connect(self.refresh)
        self._state.source_changed.connect(self._refresh_source)
        self.refresh()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        self._new_action = QAction(_text("gui.action_new_job"), self)
        self._new_action.setShortcut(QKeySequence.New)
        self._new_action.triggered.connect(self.new_job)
        self._open_action = QAction(_text("gui.action_open"), self)
        self._open_action.setShortcut(QKeySequence.Open)
        self._open_action.triggered.connect(self.open_json)
        self._save_action = QAction(_text("gui.action_save"), self)
        self._save_action.setShortcut(QKeySequence.Save)
        self._save_action.triggered.connect(self.save_json)
        self._quit_action = QAction(_text("gui.action_quit"), self)
        self._quit_action.setShortcut(QKeySequence.Quit)
        self._quit_action.triggered.connect(self.close)
        # There is no menu strip any more: the command bar is the visible home
        # of the lifecycle, and the shortcuts have to belong to the window
        # itself rather than to a menu nobody can see.
        for action in (
            self._new_action,
            self._open_action,
            self._save_action,
            self._quit_action,
        ):
            self.addAction(action)

        self._overview = OverviewPage(
            self._state,
            notify=self._notify,
            problems=self.report_problem,
            parent=self,
        )
        self._advanced = AdvancedPage(
            self._state,
            notify=self._notify,
            problems=self.report_problem,
            parent=self,
            embedded=True,
            scope="entity",
        )
        # The job-wide tools are their own instances and their own work areas:
        # a custom CCD or a bond belongs to the job, not to the selected entity.
        self._ccd = AdvancedPage(
            self._state,
            notify=self._notify,
            problems=self.report_problem,
            parent=self,
            embedded=True,
            scope="ccd",
        )
        self._bonds = AdvancedPage(
            self._state,
            notify=self._notify,
            problems=self.report_problem,
            parent=self,
            embedded=True,
            scope="bonds",
        )
        # The entity workspace hosts a compact picker and three work areas:
        # the selected entity's settings, Custom CCDs and Covalent bonds.
        self._entities = EntitiesPage(
            self._state,
            notify=self._notify,
            problems=self.report_problem,
            advanced=self._advanced,
            ccd=self._ccd,
            bonds=self._bonds,
            parent=self,
        )
        # The serialized document view is internal only: it is not a
        # destination, not in the sidebar and not reachable from any button.
        # Save JSON… is the user-facing route to the file itself.
        self._preview = PreviewPage(self._state, notify=self._notify, parent=self)
        # It is not in the workspace stack and has no destination any more, so
        # it must not be an unmanaged visible child: hiding it keeps its
        # controls out of the tab order as well as off the screen.
        self._preview.hide()
        self._build_shell()
        # The Overview's entity summary changes destination; nothing else
        # about it is special.
        self._overview.entities_requested.connect(
            lambda: self.show_page(self._entities)
        )

        # The Advanced tab always speaks about the entity selected on the
        # Entities tab: one selection, two views of it.
        self._entities.selection_changed.connect(self._advanced.show_record)

        self._notice = QLabel()
        self.statusBar().addWidget(self._notice, 1)
        self._source = QLabel()
        self.statusBar().addPermanentWidget(self._source)
        self._refresh_source()

    # -- the shell: sidebar, header, one stacked workspace ---------------

    #: The working destinations, in the order the sidebar shows them. The
    #: labels are the registry's page names, so the sidebar, the window and
    #: any test agree by construction. The file-driven ligand workflow is an
    #: action on the Entities page, not a destination of its own; saving the
    #: job is the window's Save JSON… action, not a page.
    _DESTINATIONS = (
        ("gui.tab_overview", "_overview", "overview"),
        ("gui.tab_entities", "_entities", "entities"),
    )

    def _build_shell(self) -> None:
        """The frame: captioned sidebar, product header, one pane.

        The sidebar carries WORKSPACE over the working destinations and
        nothing else: New/Open/Save live once, in the command bar above, so
        there is no second copy to clip or duplicate. One destination is
        visible at a time; the header always says which job is open and
        whether it has unsaved changes.
        """
        panel = QWidget()
        panel.setObjectName("sidebarPanel")
        panel.setFixedWidth(200)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        panel_layout.addWidget(self._sidebar_caption("gui.nav_section_workspace"))

        self._sidebar = QListWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setSelectionMode(QListWidget.SingleSelection)
        self._sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sidebar.setIconSize(QSize(16, 16))
        self._sidebar.setFocusPolicy(Qt.StrongFocus)
        self._stack = QStackedWidget()
        for label_key, attribute, icon_name in self._DESTINATIONS:
            page = getattr(self, attribute)
            item = QListWidgetItem(navigation_icon(icon_name), _text(label_key))
            self._sidebar.addItem(item)
            self._stack.addWidget(page)
        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sidebar.setCurrentRow(0)
        # The list takes the remaining height; with the FILE row gone there is
        # no footer to leave a gap behind, and the items stay under the caption.
        panel_layout.addWidget(self._sidebar, 1)

        # One inset for every destination, so switching page does not shift the
        # content edge; the pages themselves carry no outer margin.
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 16, 20, 16)
        content_layout.setSpacing(0)
        self._empty_state = self._build_empty_state()
        content_layout.addWidget(self._empty_state)
        content_layout.addWidget(self._stack)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(panel)
        body_layout.addWidget(content, 1)

        # The header spans the whole window, as in the mockup: the product mark
        # sits at the window's top-left, above the sidebar's WORKSPACE caption.
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._build_header())
        central_layout.addWidget(self._build_toolbar())
        central_layout.addWidget(body, 1)
        self.setCentralWidget(central)

    @staticmethod
    def _sidebar_caption(key: str) -> QLabel:
        """A sidebar section caption (WORKSPACE, FILE)."""
        caption = QLabel(_text(key))
        caption.setObjectName("sidebarCaption")
        return caption

    def _build_toolbar(self):
        """The command bar: the job actions, in view from the first second.

        These are the one visible home of the lifecycle. New/Open/Save are the
        same ``QAction`` objects the shortcuts trigger, so text, shortcut,
        enablement and handler cannot drift between the bar and the keyboard,
        and every button carries its words rather than an icon alone.
        """
        bar = QToolBar(_text("gui.toolbar_job"), self)
        bar.setObjectName("commandBar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for action in (
            self._new_action,
            self._open_action,
            self._save_action,
        ):
            bar.addAction(action)
            # The footer's buttons used to be in the Tab order; the bar is now
            # the only visible home of these actions, so its buttons must be
            # reachable by keyboard too (Ctrl+S alone is not discoverable).
            button = bar.widgetForAction(action)
            if button is not None:
                button.setFocusPolicy(Qt.StrongFocus)
        # Qt adds an overflow button to every toolbar. It has no text, so it
        # would be the one unlabelled control in the window: name it for a
        # screen reader and keep it out of sight while the bar fits.
        extension = bar.findChild(QToolButton, "qt_toolbar_ext_button")
        if extension is not None:
            extension.setAccessibleName(_text("gui.toolbar_job"))
            extension.hide()
        self._toolbar = bar
        return bar

    def command_bar_actions(self):
        """The command bar's actions, in the order the bar shows them."""
        return tuple(self._toolbar.actions())

    def _build_empty_state(self):
        """The first-run panel: the two ways to start, where the job would be.

        Without a job the workspace is empty, so this card names the next step
        in that space instead of leaving it blank. It creates nothing itself:
        both buttons call the same lifecycle methods as the toolbar.
        """
        card = QFrame()
        card.setObjectName("emptyState")
        card.setVisible(False)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        title = QLabel(_text("gui.empty_title"))
        title.setObjectName("emptyTitle")
        layout.addWidget(title)
        body = QLabel(_text("gui.empty_body"))
        body.setObjectName("emptyBody")
        body.setWordWrap(True)
        layout.addWidget(body)
        row = QHBoxLayout()
        self._empty_new_button = QPushButton(_text("gui.empty_new"))
        self._empty_new_button.setProperty("role", "primary")
        self._empty_new_button.clicked.connect(self.new_job)
        self._empty_open_button = QPushButton(_text("gui.empty_open"))
        self._empty_open_button.clicked.connect(self.open_json)
        row.addWidget(self._empty_new_button)
        row.addWidget(self._empty_open_button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return card

    def _build_header(self):
        """The mockup's header: mark, product name, job line, state pill."""
        header = QFrame()
        header.setObjectName("appHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)
        badge = QLabel()
        badge.setObjectName("appBadge")
        badge.setFixedSize(38, 38)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(app_mark_pixmap(22))
        layout.addWidget(badge)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        product = QLabel(_text("gui.app_name"))
        product.setObjectName("appTitle")
        subtitle = QLabel(_text("gui.app_subtitle"))
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(product)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)
        self._header_job = QLabel()
        self._header_job.setObjectName("headerJob")
        self._header_job.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._header_state = QLabel()
        self._header_state.setObjectName("statePill")
        self._header_state.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._header_job)
        layout.addWidget(self._header_state)
        return header

    def _refresh_header(self) -> None:
        """The header's job line and unsaved marker, in words, not colour.

        The marker is the mockup's pill: "Unsaved" while ``GuiState.is_dirty``
        says the job differs from the last open/save, "Saved" otherwise. The
        word carries the meaning; the accent only reinforces it.
        """
        project = self._state.project
        if project is None:
            self._header_job.setText(_text("gui.header_no_job"))
            self._header_state.setText("")
            self._header_state.setVisible(False)
            return
        self._header_state.setVisible(True)
        self._header_job.setText(
            _text("gui.header_job") % project.configuration.metadata.name
        )
        if project is not None and self._state.is_dirty:
            self._header_state.setText(_text("gui.header_unsaved"))
            self._header_state.setProperty("state", "dirty")
        else:
            self._header_state.setText(_text("gui.header_saved"))
            self._header_state.setProperty("state", "clean")
        # A dynamic property drives the sheet, so it must be re-polished.
        self._header_state.style().unpolish(self._header_state)
        self._header_state.style().polish(self._header_state)

    # -- the job lifecycle (Stage 2) ---------------------------------------

    def new_job(self) -> bool:
        """Start a fresh job; unsaved changes are never discarded silently."""
        if not self.confirm_discard_changes():
            return False
        project = self._state.new_job()
        self.statusBar().showMessage(
            _text("menu.job_created") % project.configuration.metadata.name, 8000
        )
        return True

    def confirm_discard_changes(self) -> bool:
        """Ask before throwing away unsaved edits.

        Returns True when it is safe to proceed (nothing is unsaved, or the
        user chose to discard) and False when the user kept the job.
        """
        if not self._state.has_project() or not self._state.is_dirty:
            return True
        return bool(self.discard_confirmer(self))

    def save_json(self) -> bool:
        """Save the open job as AF3 JSON through the generation service.

        The sequence mirrors the console's own save: choose a destination,
        confirm an existing file, plan, then execute. A refusal is reported
        with the service's reason (and its findings when validation blocked
        it) and nothing is marked saved; success updates the current path and
        the saved state only after ``execute`` reports it wrote the plan.
        """
        if not self._state.has_project():
            self.report_problem(_text("menu.no_project"))
            return False
        if self._saving:
            self._notify(_text("gui.save_busy"))
            return False
        # The file the job came from first (re-saving over it is the normal
        # case); otherwise a full path inside ``saved_jobs``, so accepting the
        # dialog unchanged cannot write a job into the program folder. When no
        # output folder on this machine is writable, the dialog opens with no
        # suggestion at all and the reason is said in words — a prefilled path
        # there could only fail.
        default, warning = self._default_save_path()
        destination, accepted = self.save_path_chooser(self, default)
        if not accepted or not destination:
            # A cancel normally says so; when there was no writable folder to
            # offer, the reason for that outlives the cancelled dialog.
            self.statusBar().showMessage(
                warning or _text("menu.save_cancelled"), 8000
            )
            return False
        overwrite = os.path.exists(destination)
        if overwrite and not self.overwrite_confirmer(self, destination):
            self.statusBar().showMessage(_text("menu.save_cancelled"), 8000)
            return False

        self._saving = True
        self._set_saving(True)
        self.statusBar().showMessage(_text("gui.save_started"))
        try:
            plan = self._state.plan_save(destination, overwrite=overwrite)
            if not plan.ok:
                return self._report_save_refusal(plan)
            result = self._state.execute(plan)
            if not result.ok:
                message = "\n\n".join(
                    str(error) for error in result.errors
                ) or result.message
                _log.error(
                    "write to %s failed: %s (errors=%r, message=%r)",
                    destination,
                    message,
                    tuple(result.errors),
                    result.message,
                )
                self.report_problem(message)
                self._show_status_for_problem(message)
                return False
            for path in result.written:
                _log.info("saved %s", path)
                # One sentence, no plan dump: the source line beside it names
                # the file that was written, and the detail is in the log.
                self.statusBar().showMessage(_text("gui.save_done"), 8000)
            for path in result.skipped:
                self.statusBar().showMessage(
                    _text("menu.export_skipped") % path, 8000
                )
            self._state.record_save(destination)
            # The saved snapshot changed, so every view of it must re-read:
            # the header pill and the title otherwise keep saying "Unsaved"
            # until the next unrelated edit.
            self.refresh()
            # Remembered only after a successful write: a refused or cancelled
            # save must not move the next default. Kept off the success path's
            # critical section — a preferences write can never hang or fail a
            # save that already wrote its file.
            self._remember_save_directory(destination)
            return True
        except OSError as error:
            return self._report_save_oserror(destination, error)
        finally:
            self._saving = False
            self._set_saving(False)

    def _default_save_path(self):
        """``(destination, warning)`` for the save dialog.

        A job that came from a file offers that file again; otherwise the
        shared output service names the path, never the working directory.
        The root's ``usable`` flag is what keeps an unwritable folder out of
        the dialog: a suggestion there could only produce a failed write, so
        the destination is empty and ``warning`` carries the reason the user
        needs to act on (an empty string when there is nothing to say).
        """
        if self._state.source_path:
            return self._state.source_path, ""
        resolved = self._state.paths.resolve_root()
        if not resolved.usable:
            message = " ".join(resolved.diagnostics)
            _log.warning("no writable output folder: %s", message)
            return "", message
        return (
            self._state.paths.default_save_path(
                self._state.suggested_file_name()
            ),
            "",
        )

    def _remember_save_directory(self, destination: str) -> None:
        """Remember where the job was written; never part of the save's verdict.

        The preference file lives in the user profile, which a policy or a
        security product may refuse to write. ``app.paths`` bounds that write
        (see ``_atomic_write``), and this method also tolerates the refusal: a
        job that has been written is saved whether or not the next dialog opens
        in the same folder.
        """
        try:
            self._state.paths.remember_save_directory(
                os.path.dirname(os.path.abspath(destination))
            )
        except OSError:
            pass

    def _report_save_oserror(self, destination: str, error: OSError) -> bool:
        """Turn a filesystem refusal into words and keep the job editable.

        ``PermissionError`` is the Windows shape of the reported failure (a
        protected folder, or a file open in another program); everything else
        is reported with its own explanation rather than a traceback. Nothing
        here changes the saved snapshot, so the unsaved changes stay, and the
        exception itself goes to the log rather than the screen.
        """
        _log.error("cannot write %s: %r", destination, error, exc_info=error)
        if isinstance(error, PermissionError):
            message = _text("gui.save_permission_denied") % destination
        else:
            message = _text("gui.save_filesystem_failed") % (destination, error)
        self.report_problem(message)
        self._show_status_for_problem(message)
        return False

    def _set_saving(self, saving: bool) -> None:
        """Enable the one write action only when a save can actually start."""
        self._save_action.setEnabled(self._state.has_project() and not saving)

    def _report_save_refusal(self, plan) -> bool:
        """Show why nothing was written, including the blocking findings.

        Readiness is a compact line now, so the reasons come to the user here,
        on the save attempt, instead of living in a permanent list on Overview.
        """
        if plan.failure_reason == FailureReason.VALIDATION_BLOCKED:
            message = self._blocking_message(plan)
        else:
            message = plan.message or ""
        for conflict in plan.conflicts:
            line = _text("menu.export_conflict") % conflict
            message = "%s\n\n%s" % (message, line) if message else line
        _log.warning(
            "save refused: reason=%s message=%r conflicts=%r findings=%r",
            plan.failure_reason,
            plan.message,
            tuple(plan.conflicts),
            tuple(
                (
                    getattr(finding, "rule_id", ""),
                    finding.user_message,
                    finding.suggestion,
                )
                for finding in tuple(getattr(plan, "findings", ()) or ())
            ),
        )
        self.report_problem(message)
        self._show_status_for_problem(message)
        return False

    @staticmethod
    def _blocking_message(plan) -> str:
        """The blocking findings as a short, actionable explanation."""
        findings = tuple(getattr(plan, "findings", ()) or ())
        blocking = tuple(
            finding
            for finding in findings
            if getattr(getattr(finding, "severity", None), "name", "") == "ERROR"
        ) or findings
        if not blocking:
            return plan.message or ""
        header = (
            _text("gui.blocked_header_one")
            if len(blocking) == 1
            else _text("gui.blocked_header") % len(blocking)
        )
        lines = [header]
        for finding in blocking[:4]:
            lines.append(_text("gui.blocked_line") % finding.user_message)
            if finding.suggestion:
                lines.append(_text("gui.blocked_fix") % finding.suggestion)
        if len(blocking) > 4:
            lines.append(_text("gui.blocked_more") % (len(blocking) - 4))
        return "\n".join(lines)

    # -- the import path: preview, confirm, then commit --------------------

    def open_json(self) -> None:
        """Ask for a file, preview it, and commit only if the user imports."""
        from PySide6.QtWidgets import QFileDialog

        path, _selected = QFileDialog.getOpenFileName(
            self,
            _text("gui.open_dialog_title"),
            "",
            _text("gui.file_filter"),
        )
        if not path:
            return
        self.offer_import(path)

    def offer_import(self, path: str) -> bool:
        """Run the preview → confirm → commit sequence for ``path``.

        The unsaved-changes question comes **after** the preview is accepted
        and **before** the commit, so a Cancel keeps the open job exactly as
        it is, and a user who abandons the preview is never asked about a
        replacement that was not going to happen.

        Returns True when the file became the open job.
        """
        preview = self._state.preview_import(path)
        if not preview.ok:
            self.report_failure(preview.message)
            return False
        dialog = ImportPreviewDialog(self, path, preview)
        if dialog.exec() != ImportPreviewDialog.Accepted:
            return False
        if not self.confirm_discard_changes():
            return False
        outcome = self._state.commit_import(path)
        if not outcome.ok:
            self.report_failure(outcome.message)
            return False
        _log.info("opened %s", path)
        self.statusBar().showMessage(_text("gui.open_succeeded"), 8000)
        return True

    # -- reporting ---------------------------------------------------------

    def report_failure(self, message: str) -> str:
        """Tell the user why a file was refused, in their terms.

        The service's own message is shown verbatim (never a traceback), the
        status line keeps it visible after the box is dismissed, and it stays
        readable through :meth:`last_failure_text` so a test can assert on it.
        """
        self._last_failure = message
        _log.warning("import refused: %s", message)
        self.statusBar().showMessage(_text("menu.import_failed"), 8000)
        self.failure_reporter(self, message)
        return message

    def report_problem(self, message: str) -> str:
        """Tell the user why an action was refused, with the service's reason.

        The same contract as :meth:`report_failure` for everything that is
        not an import; the message is kept verbatim and readable through
        :meth:`last_problem_text`.
        """
        self._last_problem = message
        _log.warning("action refused: %s", message)
        self.problem_reporter(self, message)
        return message

    def _notify(self, message: str) -> None:
        """A success line on the status bar (never a modal box)."""
        self.statusBar().showMessage(message, 8000)

    def _show_status_for_problem(self, message: str) -> None:
        first_line = (message or "").splitlines()[0] if message else ""
        self.statusBar().showMessage(_text("menu.not_applied") % first_line, 8000)

    # -- refresh and navigation -------------------------------------------

    def refresh(self) -> None:
        """Re-read every page from the services. Writes nothing."""
        self._set_saving(self._saving)
        self._refresh_empty_state()
        self._overview.refresh()
        self._entities.refresh()
        self._advanced.refresh()
        self._ccd.refresh()
        self._bonds.refresh()
        self._preview.refresh()
        self._refresh_source()
        self._refresh_title()
        self._refresh_notice()
        self._refresh_header()

    def _refresh_empty_state(self) -> None:
        """Show the start panel exactly while there is no job to edit."""
        self._empty_state.setVisible(not self._state.has_project())

    def _refresh_title(self) -> None:
        """Name the open job in the title bar and mark unsaved changes.

        The marker is text, not colour: the title reads "name* - AF3 JSON
        Builder" exactly while ``GuiState.is_dirty`` says the live
        configuration differs from the last save or open. Only an operation
        that actually recorded a save clears it.
        """
        project = self._state.project
        if project is None:
            self.setWindowTitle(_text("gui.window_title"))
            return
        name = project.configuration.metadata.name
        template = (
            "gui.window_title_dirty" if self._state.is_dirty else "gui.window_title_job"
        )
        self.setWindowTitle(_text(template) % name)

    def _refresh_notice(self) -> None:
        """The status bar's one standing hint, matched to the current state."""
        if not self._state.has_project():
            key = "gui.notice_no_job"
        elif self._state.is_dirty:
            key = "gui.notice_dirty"
        else:
            key = "gui.notice_job"
        self._notice.setText(_text(key))

    def _refresh_source(self) -> None:
        if self._state.is_demo:
            self._source.setText(_text("gui.demo_notice"))
        elif self._state.source_path:
            self._source.setText(_text("gui.source_file") % self._state.source_path)
        else:
            self._source.setText(_text("gui.source_none"))


    def show_page(self, page) -> None:
        """Bring one destination forward (the sidebar follows the workspace)."""
        index = self._stack.indexOf(page)
        if index >= 0:
            self._sidebar.setCurrentRow(index)

    def current_page(self):
        """The destination currently displayed."""
        return self._stack.currentWidget()

    def destination_pages(self):
        """The pages the sidebar can reach, in its own order."""
        return tuple(
            self._stack.widget(index) for index in range(self._stack.count())
        )

    def sidebar_labels(self):
        """The destination labels, in the sidebar's own order."""
        return [
            self._sidebar.item(row).text() for row in range(self._sidebar.count())
        ]

    # -- close -------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """Closing is the third place unsaved changes must not vanish."""
        if self.confirm_discard_changes():
            event.accept()
        else:
            event.ignore()

    # -- page accessors (used by the window's own tests and callers) -------

    def source_text(self) -> str:
        """The status bar's source line as displayed."""
        return self._source.text()

    def notice_text(self) -> str:
        """The status bar's read-only notice as displayed."""
        return self._notice.text()

    def header_job_text(self) -> str:
        """The header's job line as displayed."""
        return self._header_job.text()

    def header_state_text(self) -> str:
        """The header's saved/unsaved marker as displayed."""
        return self._header_state.text()

    def empty_state_visible(self) -> bool:
        """Whether the first-run start panel is on screen."""
        return not self._empty_state.isHidden()

    def last_failure_text(self) -> str:
        """The last refusal's own message, as reported to the user."""
        return self._last_failure

    def last_problem_text(self) -> str:
        """The last non-import refusal's own message, as reported."""
        return self._last_problem

    @property
    def state(self):
        return self._state

    @property
    def overview_page(self):
        return self._overview

    @property
    def entities_page(self):
        return self._entities

    @property
    def settings_page(self):
        """The one job-wide settings editor: the panel Overview hosts.

        Stage 8 removed the separate Job Settings tab, so this accessor names
        the single remaining placement rather than a page of its own. A
        caller that used to read the tab now reads the same widget, backed by
        the same ``ConfigurationService``.
        """
        return self._overview.job_settings

    @property
    def ccd_page(self):
        """The job-wide Custom CCD work area hosted inside Entities."""
        return self._ccd

    @property
    def bonds_page(self):
        """The job-wide Covalent bonds work area hosted inside Entities."""
        return self._bonds

    @property
    def advanced_page(self):
        return self._advanced

    @property
    def preview_page(self):
        """The internal read-only JSON view (not a destination since Stage 9).

        It shows exactly what ``GenerationService.show_json`` returns and is
        refreshed with the window, but no sidebar item, Overview action or
        other route displays it: the user reads the document by saving it.
        The tests still read it back as the window's copy of the service text.
        """
        return self._preview
