"""The job-wide settings editor: the job's name, model seeds and JSON version.

One widget, one placement (Stage 8): the Overview page, so the values a
reviewer wants most are editable where the readiness verdict is read. The
separate Job Settings tab was removed rather than kept as a second route to
the same values — the panel talks to the service and re-reads it on every
refresh, so there is one source of truth and never a second copy of the state
in a widget.

Every change goes through ``ConfigurationService``: this widget parses nothing
and decides nothing. A refused value — a blank name, seeds that are not whole
numbers, an unsupported version — comes back as the service's own message,
which the window reports; the page then re-reads the service's current values
instead of keeping the refused text on screen.

The fields always show the values **in use**, and each row says whether that
value is still the application's default (``gui.settings_default``) or has
been changed (``gui.settings_custom``). The defaults themselves are the
service's (``app.status``): nothing here replaces them silently, and a change
happens only when the user presses Apply on that row.

The version list is the console's own ``SUPPORTED_VERSIONS`` — imported, not
re-typed, so the two front ends cannot disagree about which versions may be
pinned. The version rules themselves stay in the service and the model; this
page only offers the choice.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from configbuilder.app.status import DEFAULT_VERSION, is_automatic_name, is_default_seeds
from configbuilder.model import Pinned
from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.menus import SUPPORTED_VERSIONS
from configbuilder.ui.render.qt.models import version_text
from configbuilder.ui.render.qt.style import (
    caption_label,
    field_label,
    heading_label,
)

__all__ = ["JobSettingsPanel"]


class JobSettingsPanel(QWidget):
    """The open job's name, seeds and version pin, applied through services.

    ``notify`` receives a success line and ``problems`` a refusal's own
    message; both default to doing nothing so the panel can be constructed in
    a test without a window. ``title_key`` names the group for its context
    without a second copy of the form.
    """

    def __init__(
        self,
        state,
        notify=None,
        problems=None,
        title_key="gui.section_settings",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._notify = notify if notify is not None else (lambda message: None)
        self._problems = problems if problems is not None else (lambda message: None)
        self._title_key = title_key
        self._build()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        """The mockup's settings card: labels above fields, one quiet Apply
        per value, and the default/changed marker as a caption underneath.

        The card is the page's own width, so the fields read as a form rather
        than as a table of label/editor pairs. Apply stays visible and
        labelled on every value: nothing is committed while typing, and a
        refused value still restores the service's own text.
        """
        layout = QVBoxLayout(self)
        group = QFrame()
        group.setObjectName("card")
        inner = QVBoxLayout(group)
        inner.setContentsMargins(16, 14, 16, 14)
        inner.setSpacing(6)
        inner.addWidget(heading_label(_text(self._title_key)))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)

        self.name_edit = QLineEdit()
        # A QGridLayout label is not a buddy, so the screen reader needs the
        # field's own name; it is the same wording the visible label carries.
        self.name_edit.setAccessibleName(_text("gui.field_job_name"))
        self.name_apply = QPushButton(_text("gui.settings_apply"))
        self.name_state = caption_label()
        self.name_edit.returnPressed.connect(self.apply_name)
        self.name_apply.clicked.connect(self.apply_name)

        self.seeds_edit = QLineEdit()
        self.seeds_edit.setAccessibleName(_text("gui.field_seeds"))
        self.seeds_apply = QPushButton(_text("gui.settings_apply"))
        self.seeds_state = caption_label()
        self.seeds_edit.returnPressed.connect(self.apply_seeds)
        self.seeds_apply.clicked.connect(self.apply_seeds)

        self.version_combo = QComboBox()
        self.version_combo.setAccessibleName(_text("gui.field_version"))
        for version in SUPPORTED_VERSIONS:
            self.version_combo.addItem(str(version), version)
        self.version_apply = QPushButton(_text("gui.settings_apply"))
        self.version_state = caption_label()
        self.version_apply.clicked.connect(self.apply_version)

        for button in (self.name_apply, self.seeds_apply, self.version_apply):
            button.setProperty("role", "quiet")

        grid.addWidget(field_label(_text("gui.field_job_name")), 0, 0, 1, 4)
        grid.addWidget(self.name_edit, 1, 0, 1, 3)
        grid.addWidget(self.name_apply, 1, 3, Qt.AlignVCenter)
        grid.addWidget(self.name_state, 2, 0, 1, 4)

        grid.addWidget(field_label(_text("gui.field_seeds")), 3, 0, 1, 2)
        grid.addWidget(field_label(_text("gui.field_version")), 3, 2, 1, 2)
        grid.addWidget(self.seeds_edit, 4, 0)
        grid.addWidget(self.seeds_apply, 4, 1, Qt.AlignVCenter)
        grid.addWidget(self.version_combo, 4, 2)
        grid.addWidget(self.version_apply, 4, 3, Qt.AlignVCenter)
        grid.addWidget(self.seeds_state, 5, 0, 1, 2)
        grid.addWidget(self.version_state, 5, 2, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        inner.addLayout(grid)

        layout.addWidget(group)
        layout.setContentsMargins(0, 0, 0, 0)

    # -- refresh -----------------------------------------------------------

    def refresh(self) -> None:
        """Re-read the service's current values (never a cached copy)."""
        configuration = self._state.configuration
        enabled = configuration is not None
        for widget in (
            self.name_edit,
            self.name_apply,
            self.seeds_edit,
            self.seeds_apply,
            self.version_combo,
            self.version_apply,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self.name_edit.clear()
            self.seeds_edit.clear()
            self.name_state.setText(_text("menu.status_absent"))
            self.seeds_state.setText(_text("menu.status_absent"))
            self.version_state.setText(_text("menu.status_absent"))
            return

        name = configuration.metadata.name
        self.name_edit.setText(name)
        self.name_state.setText(
            _text("gui.settings_default") if is_automatic_name(name) else _text("gui.settings_custom")
        )

        self.seeds_edit.setText(", ".join(str(value) for value in configuration.seeds.values))
        self.seeds_state.setText(
            _text("gui.settings_default")
            if is_default_seeds(configuration.seeds.values)
            else _text("gui.settings_custom")
        )

        selection = configuration.format_target.version_selection
        pinned = selection.version if isinstance(selection, Pinned) else None
        chosen = pinned if pinned in SUPPORTED_VERSIONS else DEFAULT_VERSION
        index = self.version_combo.findData(chosen)
        self.version_combo.setCurrentIndex(index if index >= 0 else 0)
        if pinned is None:
            self.version_state.setText(version_text(selection))
        else:
            marker = (
                _text("gui.settings_default")
                if pinned == DEFAULT_VERSION
                else _text("gui.settings_custom")
            )
            self.version_state.setText(
                "%s · %s" % (version_text(selection), marker)
            )

    # -- applying (one row at a time, on request) --------------------------

    def apply_name(self) -> bool:
        """Send the typed name to ``ConfigurationService.set_name``."""
        outcome = self._state.set_job_name(self.name_edit.text().strip())
        return self._applied(
            outcome,
            lambda: self._notify(
                _text("gui.settings_name_applied") % self._state.configuration.metadata.name
            ),
        )

    def apply_seeds(self) -> bool:
        """Send the typed seeds; blank text is no change (console parity)."""
        text = self.seeds_edit.text().strip()
        if not text:
            self.refresh()
            return False
        outcome = self._state.set_seeds(text)
        return self._applied(outcome, lambda: self._notify(_text("gui.settings_seeds_applied")))

    def apply_version(self) -> bool:
        """Pin the chosen version through ``set_format_target``."""
        version = self.version_combo.currentData()
        outcome = self._state.set_json_version(version)
        return self._applied(
            outcome,
            lambda: self._notify(_text("gui.settings_version_applied") % int(version)),
        )

    def _applied(self, outcome, success) -> bool:
        """Report a service outcome; a refusal restores the current values."""
        if outcome.ok:
            success()
            return True
        self._problems(outcome.message)
        self.refresh()
        return False
