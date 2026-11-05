"""The Overview page: job settings, entities at a glance, and readiness.

The job's name, model seeds and JSON version are **editable here**, and this is
the only place they are edited: the separate Job Settings destination was
removed, so the page embeds the single :class:`JobSettingsPanel` and it reads
and writes through ``ConfigurationService``.

What remains on the page is deliberately small:

1. **Job details** — the job-wide settings with their Apply semantics and
   default/changed markers;
2. **Entities** — the record count, the service's own per-family breakdown and
   one :class:`Entities` action that opens the Entities workspace;
3. **Readiness** — the validation service's verdict as one short line, with a
   quiet *Validate job* action that re-reads it and says so.

There is no persistent findings table and no readiness row-table here. The
service still validates exactly as before; Save and Generate explain a
blocking refusal through their own focused message when the user attempts
them. Removing the list changed nothing about the gate.

No JSON preview action is on this page either: the document is written through
**Save JSON** in the FILE footer, which is the one visible save route.

Everything shown here comes from a service call:

- the counts are the status service's own ``components`` row;
- the readiness verdict is ``ValidationService.status()`` — this page displays
  it and never recomputes it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from configbuilder.ui.present.strings import blocking_verdict
from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.qt.pages.settings import JobSettingsPanel
from configbuilder.ui.render.qt.style import (
    breadcrumb_label,
    caption_label,
    field_label,
    hint_label,
    page_title_label,
)

__all__ = ["OverviewPage"]


class OverviewPage(QWidget):
    """Job settings, an entity summary and one compact readiness line."""

    #: The summary action the window answers by changing destination.
    entities_requested = Signal()

    def __init__(self, state, notify=None, problems=None, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._notify = notify if notify is not None else (lambda message: None)
        self.job_settings = JobSettingsPanel(
            state, notify=notify, problems=problems, parent=self
        )
        # The last service answer, kept so the validate action reports the same
        # verdict the line shows rather than re-deriving one.
        self._last_status = None
        self._build()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(breadcrumb_label(_text("gui.breadcrumb_overview")))
        layout.addWidget(page_title_label(_text("gui.overview_title")))
        layout.addWidget(hint_label(_text("gui.overview_intro")))
        layout.addSpacing(2)
        layout.addWidget(self.job_settings)
        self._no_job_note = hint_label(_text("gui.overview_no_job"))
        self._no_job_note.setVisible(False)
        layout.addWidget(self._no_job_note)
        self._summary_card = self._build_entity_summary()
        layout.addWidget(self._summary_card)
        self._readiness_card = self._build_readiness()
        layout.addWidget(self._readiness_card)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    def _build_entity_summary(self):
        """A compact card: how many entities, which families, and where to go."""
        card = QFrame()
        card.setObjectName("statCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        layout.addWidget(field_label(_text("gui.stat_entities")))
        self._entities_value = QLabel(_text("menu.status_absent"))
        self._entities_value.setProperty("role", "statValue")
        self._entities_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._entities_value)
        self._entities_detail = caption_label(wrap=True)
        layout.addWidget(self._entities_detail)
        self._dialect_label = caption_label()
        self._dialect_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._dialect_label)
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(10)
        self.entities_button = QPushButton(_text("gui.overview_go_entities"))
        self.entities_button.setProperty("role", "quiet")
        self.entities_button.clicked.connect(self.entities_requested.emit)
        row.addWidget(self.entities_button)
        # Wrap: the hint's full sentence is wider than the content area at the
        # window's 940 px minimum, and an unwrapped label forced the whole
        # Overview into a horizontal scrollbar there.
        row.addWidget(
            caption_label(_text("gui.entity_summary_hint"), wrap=True), 1
        )
        layout.addLayout(row)
        return card

    def _build_readiness(self):
        """One compact line: the service's verdict and a quiet re-read."""
        card = QFrame()
        card.setObjectName("statCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)
        layout.addWidget(field_label(_text("gui.stat_readiness")))
        self._readiness_state = QLabel()
        self._readiness_state.setProperty("role", "statState")
        layout.addWidget(self._readiness_state)
        self._verdict = caption_label(wrap=True)
        layout.addWidget(self._verdict, 1)
        self.validate_button = QPushButton(_text("gui.overview_validate"))
        self.validate_button.setProperty("role", "quiet")
        self.validate_button.clicked.connect(self.validate_job)
        layout.addWidget(self.validate_button)
        return card

    # -- refresh -----------------------------------------------------------

    def refresh(self) -> None:
        """Re-read the model and the readiness service. Never writes anything."""
        configuration = self._state.configuration
        project = self._state.project
        if configuration is None or project is None:
            self._clear()
            return
        self.job_settings.refresh()
        self.job_settings.setVisible(True)
        self._no_job_note.setVisible(False)
        self._summary_card.setVisible(True)
        self._readiness_card.setVisible(True)

        status = self._state.status()
        self._last_status = status
        total = len(configuration.records)
        self._entities_value.setText(str(total))
        self._entities_detail.setText(
            _family_summary(_components_counts(status))
            if total
            else _text("gui.stat_entities_none")
        )
        self._dialect_label.setText(
            _text("gui.dialect_caption") % configuration.format_target.dialect.value
        )
        if status is None:
            self._readiness_state.setText(_text("gui.stat_no_job"))
            self._verdict.setText("")
        elif status.ready:
            self._readiness_state.setText(_text("gui.readiness_ready"))
            self._verdict.setText(_text("gui.readiness_ok"))
        else:
            self._readiness_state.setText(_text("gui.readiness_attention"))
            self._verdict.setText(blocking_verdict(len(status.blocking)))

    def _clear(self) -> None:
        """No job: keep the page neutral and leave New/Open to the footer."""
        self.job_settings.refresh()
        self.job_settings.setVisible(False)
        self._last_status = None
        self._entities_value.setText("0")
        self._entities_detail.setText("")
        self._dialect_label.setText("")
        self._readiness_state.setText(_text("gui.stat_no_job"))
        self._verdict.setText("")
        self._summary_card.setVisible(False)
        self._readiness_card.setVisible(False)
        self._no_job_note.setVisible(True)

    def validate_job(self) -> bool:
        """Re-read readiness from the service, then report the same answer."""
        self.refresh()
        status = self._last_status
        if status is None:
            self._notify(_text("menu.no_project"))
            return False
        if status.ready:
            self._notify(_text("gui.validate_ok"))
        else:
            self._notify(
                _text("gui.validate_findings") % len(status.blocking)
            )
        return True

    # -- reading the page back (used by the window's tests) ----------------

    def verdict_text(self) -> str:
        """The readiness detail as displayed, straight from the service."""
        return self._verdict.text()

    def readiness_state_text(self) -> str:
        """The short readiness state (\"Ready\"/\"Needs attention\")."""
        return self._readiness_state.text()

    def entities_value_text(self) -> str:
        """The entity count the summary card shows."""
        return self._entities_value.text()

    def summary_text(self, label_key: str) -> str:
        """The summary value displayed for one label key (``""`` if none)."""
        if label_key == "menu.status_components":
            return self._entities_detail.text()
        if label_key == "gui.dialect_label":
            return self._dialect_label.text()
        return ""


#: Per-family wording for the entity summary, in the mockup's order.
_FAMILY_WORDS = (
    ("protein", "gui.family_protein", "gui.family_proteins"),
    ("rna", "gui.family_rna", "gui.family_rna"),
    ("dna", "gui.family_dna", "gui.family_dna_plural"),
    ("ligand", "gui.family_ligand", "gui.family_ligands"),
)


def _family_summary(counts) -> str:
    """Only the families present, in plain words.

    The numbers are the status service's own ``components`` value; this only
    chooses wording and skips empty families, so a three-ligand job reads
    "3 ligands" rather than listing zeros for protein, RNA and DNA. DNA is
    counted as chain records, so a duplex the builder added is two strands.
    """
    counts = counts if isinstance(counts, dict) else {}
    parts = []
    for key, singular, plural in _FAMILY_WORDS:
        amount = counts.get(key, 0) or 0
        if amount == 1:
            parts.append("%d %s" % (amount, _text(singular)))
        elif amount > 1:
            parts.append("%d %s" % (amount, _text(plural)))
    return " · ".join(parts)


def _components_counts(status):
    """The per-family record counts, from the status service's own row."""
    if status is None:
        return None
    field = status.field("components")
    return field.value if field is not None else None
