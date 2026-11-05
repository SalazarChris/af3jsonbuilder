"""The settings page, composed in one of three scopes.

The Entities workspace hosts three instances, each with its own visible work
area, so job-wide configuration is never mixed into the selected entity's
settings:

- ``scope="entity"`` — alignment/MSA first, then templates, then PTMs. The
  page always shows the entity selected in the Entities picker; the window
  keeps the two in step. A family that has no such setting hides the section
  instead of showing a control that would be refused.
- ``scope="ccd"`` — the root custom CCD definition (inline ``userCCD`` or an
  external ``userCCDPath``, never both).
- ``scope="bonds"`` — the root covalent linkages between entity endpoints.

``scope="all"`` composes all three in one page; the window no longer uses it,
but the composition remains available to callers that host the page directly.

Every mutation is a pass-through to an existing service method
(``ConfigurationService`` via ``GuiState``). Nothing here builds a record,
allocates an identifier, assembles a bond triple for the wire, decides whether
a mode is legal, or serializes anything: the page collects values, asks its
one confirmation question, calls the service and refreshes. A refusal is shown
in the form that produced it — or through the window's problem path for an
action with no form — and never as a traceback.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from configbuilder.app.configuration_service import ReferenceInput
from configbuilder.app.version_features import (
    TEMPLATE_PATH_MIN_VERSION,
    USER_CCD_PATH_MIN_VERSION,
)
from configbuilder.model import (
    AlignmentAutomatic,
    AlignmentBoth,
    AlignmentFree,
    AlignmentPairedOnly,
    AlignmentUnpairedOnly,
    Explicit,
    External,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    Inline,
    SearchAllowed,
    SingleAutomatic,
    SingleFree,
    SingleProvided,
    is_d_code,
)
from configbuilder.ui.present.modifications import modification_code_text
from configbuilder.ui.present.sequence import residue_at
from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.qt.dialogs import (
    AlignmentFormDialog,
    BondFormDialog,
    ModificationFormDialog,
    TemplateEditorDialog,
    confirm_bond_removal,
    confirm_modification_removal,
)
from configbuilder.ui.render.qt.models import fixed_font, family_label
from configbuilder.ui.render.qt.style import heading_label, hint_label

__all__ = ["AdvancedPage"]

# The alignment modes each family accepts, in the console's own words and
# order (``MenuApp._collect_msa_mode``). Only the mode *word* is sent to the
# service, which remains the authority on what a family accepts.
_PROTEIN_MODES = (
    ("menu.msa_mode_auto", "automatic"),
    ("menu.msa_mode_unpaired", "unpaired"),
    ("menu.msa_mode_paired", "paired"),
    ("menu.msa_mode_both", "both"),
    ("menu.msa_mode_free", "free"),
)
_RNA_MODES = (
    ("menu.msa_mode_auto", "automatic"),
    ("menu.msa_mode_provided", "provided"),
    ("menu.msa_mode_free", "free"),
)

#: Families whose records carry a modification list (the model's polymer
#: families; a ligand has none).
_POLYMER_FAMILIES = (FamilyARecord, FamilyBRecord, FamilyCRecord)


def alignment_state(record):
    """One record's alignment as ``(mode, kind, text, paired_kind, paired_text)``.

    Purely a projection of the model's own alignment value: ``""`` for a mode
    word means the family has no alignment setting (DNA, ligands). Nothing is
    interpreted — every value comes from the model object. The paired pair is
    ``("", "")`` unless the mode is ``both`` and the paired side has a source
    of its own, which is what lets the form reopen with both sources intact.
    """
    alignment = getattr(record, "alignment", None)
    if isinstance(alignment, AlignmentAutomatic):
        return ("automatic", "", "", "", "")
    if isinstance(alignment, (AlignmentFree, SingleFree)):
        return ("free", "", "", "", "")
    if isinstance(alignment, AlignmentUnpairedOnly):
        return _padded(_alignment_with_source("unpaired", alignment.source))
    if isinstance(alignment, AlignmentPairedOnly):
        return _padded(_alignment_with_source("paired", alignment.source))
    if isinstance(alignment, AlignmentBoth):
        mode, kind, text = _alignment_with_source("both", alignment.source)
        paired = alignment.paired_source
        if paired == alignment.source:
            return (mode, kind, text, "", "")
        _mode, paired_kind, paired_text = _alignment_with_source("both", paired)
        return (mode, kind, text, paired_kind, paired_text)
    if isinstance(alignment, SingleAutomatic):
        return ("automatic", "", "", "", "")
    if isinstance(alignment, SingleProvided):
        return _padded(_alignment_with_source("provided", alignment.source))
    return ("", "", "", "", "")


def _alignment_with_source(mode, source):
    if isinstance(source, Inline):
        return (mode, "inline", source.text)
    if isinstance(source, External):
        return (mode, "file", source.path.raw)
    return (mode, "", "")


def _padded(triple):
    """A single-source state widened to the five-field shape (no paired side)."""
    return tuple(triple) + ("", "")


def reference_state(record):
    """One protein's references as ``(route, ((kind, value, pairs), ...))``.

    ``search`` is the model's search-allowed state, ``none`` its explicitly
    template-free state and ``list`` an explicit reference list — the three
    routes the console offers, read back from the model. ``kind`` is ``file``
    or ``inline``, so an imported inline template is shown, and re-sent, as
    what it is.
    """
    references = getattr(record, "references", None)
    if isinstance(references, Explicit):
        entries = []
        for item in references.items:
            entries.append(_reference_row(item))
        return ("list" if entries else "none", tuple(entries))
    if isinstance(references, SearchAllowed):
        return ("search", ())
    return ("", ())


def _reference_row(item):
    """One reference as ``(kind, value, pairs text)``, read from the model."""
    source = item.source
    if isinstance(source, External):
        kind, value = "file", source.path.raw
    else:
        kind, value = "inline", source.text
    pairs = ", ".join(
        "%d:%d" % (pair.query, pair.template) for pair in item.index_map
    )
    return (kind, value, pairs)


def parse_pairs(text: str):
    """The console's own index-pair syntax as ``((query, template), ...)``.

    ``query:template`` tokens separated by commas (a semicolon is accepted as
    a separator too), both indices 0-based. The service validates the values;
    this only splits the text the same way the console does.
    """
    pairs = []
    for token in (text or "").replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        left, _, right = token.partition(":")
        pairs.append((left.strip(), right.strip()))
    return tuple(pairs)


class AdvancedPage(QWidget):
    """The Stage 4 settings for the selected entity, plus the job-level ones."""

    def __init__(
        self,
        state,
        notify=None,
        problems=None,
        parent=None,
        embedded=False,
        scope="all",
    ) -> None:
        super().__init__(parent)
        self._state = state
        # Embedded: the Entities workspace owns the scroll and the title.
        self._embedded = embedded
        # Which sections this instance builds: the entity's own settings, the
        # job-wide custom-CCD tools, the job-wide bond tools, or all three.
        # The Entities workspace hosts one instance per work area so that the
        # job-wide tools are not mixed into the selected entity's settings.
        if scope not in ("all", "entity", "ccd", "bonds"):
            raise ValueError("unknown advanced-page scope %r" % (scope,))
        self._scope = scope
        self._notify = notify if notify is not None else (lambda message: None)
        self._problems = problems if problems is not None else (lambda message: None)
        self._record_key = ""
        # The one seam the tests replace: a modal confirmation nobody could
        # click offscreen. Both questions are asked through these callables.
        self.modification_confirmer = confirm_modification_removal
        self.bond_confirmer = confirm_bond_removal
        # The definition last shown by the CCD controls, so an unrelated
        # refresh does not overwrite what the user is editing there.
        self._ccd_synced_definition = None
        self._build()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel(_text("gui.adv_no_selection"))
        self._title.setWordWrap(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        # The entity's own controls, in the order the workspace reads top to
        # bottom: alignment/MSA first, then templates, then PTMs. The job-wide
        # tools are separate instances (``scope``) hosted in their own areas.
        self._family_note = hint_label("")
        self._family_note.setVisible(False)
        if self._scope in ("all", "entity"):
            # Embedded in Entities, the workspace already says this is the
            # selected entity's settings; only the standalone composition
            # needs the extra scope heading.
            if self._scope == "all":
                layout.addWidget(heading_label(_text("gui.adv_scope_entity")))
            layout.addWidget(self._family_note)
            self.alignment_group = self._build_alignment()
            self.templates_group = self._build_templates()
            self.modifications_group = self._build_modifications()
            layout.addWidget(self.alignment_group)
            layout.addWidget(self.templates_group)
            layout.addWidget(self.modifications_group)
        if self._scope == "all":
            layout.addSpacing(6)
            layout.addWidget(heading_label(_text("gui.adv_scope_job")))
            layout.addWidget(hint_label(_text("gui.adv_scope_job_hint")))
        if self._scope in ("all", "ccd"):
            self.ccd_group = self._build_ccd()
            layout.addWidget(self.ccd_group)
        if self._scope in ("all", "bonds"):
            self.bonds_group = self._build_bonds()
            layout.addWidget(self.bonds_group)
        layout.addStretch(1)
        if self._embedded:
            # The host already provides the page title and the one scroll
            # surface; nesting another would trap the wheel and clip menus.
            outer.addWidget(body)
            return
        outer.addWidget(self._title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    def _group(self, title_key):
        group = QGroupBox(_text(title_key))
        layout = QVBoxLayout(group)
        return group, layout

    def _build_modifications(self):
        group, layout = self._group("gui.section_modifications")
        self._mod_notice = QLabel()
        self._mod_notice.setWordWrap(True)
        layout.addWidget(self._mod_notice)
        self.modification_table = QTableWidget(0, 3)
        self.modification_table.setHorizontalHeaderLabels(
            [
                _text("gui.mod_form_code"),
                _text("gui.mod_form_position"),
                _text("gui.mod_col_residue"),
            ]
        )
        self.modification_table.verticalHeader().setVisible(False)
        header = self.modification_table.horizontalHeader()
        # The three columns share the width. Content-sized columns let a long
        # header wording force a horizontal scrollbar onto a narrow workspace.
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumSectionSize(60)
        self.modification_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.modification_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.modification_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.modification_table.setMinimumHeight(120)
        layout.addWidget(self.modification_table)
        self.add_modification_button = QPushButton(_text("gui.mod_add"))
        self.edit_modification_button = QPushButton(_text("gui.mod_edit"))
        self.remove_modification_button = QPushButton(_text("gui.mod_remove"))
        self.add_modification_button.clicked.connect(self.add_modification)
        self.edit_modification_button.clicked.connect(self.edit_selected_modification)
        self.remove_modification_button.clicked.connect(self.remove_selected_modification)
        row = QHBoxLayout()
        for button in (
            self.add_modification_button,
            self.edit_modification_button,
            self.remove_modification_button,
        ):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    def _build_alignment(self):
        group, layout = self._group("gui.section_alignment")
        self._alignment_notice = QLabel()
        self._alignment_notice.setWordWrap(True)
        self.alignment_label = QLabel()
        self.alignment_label.setWordWrap(True)
        self.alignment_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.alignment_button = QPushButton(_text("gui.alignment_button"))
        self.alignment_button.clicked.connect(self.change_alignment)
        layout.addWidget(self._alignment_notice)
        layout.addWidget(self.alignment_label)
        row = QHBoxLayout()
        row.addWidget(self.alignment_button)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    def _build_templates(self):
        group, layout = self._group("gui.section_templates")
        self._templates_notice = QLabel()
        self._templates_notice.setWordWrap(True)
        self.templates_label = QLabel()
        self.templates_label.setWordWrap(True)
        self.templates_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.templates_button = QPushButton(_text("gui.templates_button"))
        self.templates_button.clicked.connect(self.edit_templates)
        self.templates_version_label = QLabel(
            _text("gui.templates_path_version") % TEMPLATE_PATH_MIN_VERSION
        )
        self.templates_version_label.setWordWrap(True)
        layout.addWidget(self._templates_notice)
        layout.addWidget(self.templates_label)
        layout.addWidget(self.templates_version_label)
        row = QHBoxLayout()
        row.addWidget(self.templates_button)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    def _build_ccd(self):
        group, layout = self._group("gui.section_ccd")
        note = QLabel(_text("gui.ccd_note"))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.ccd_group = QButtonGroup(self)
        self.ccd_none_radio = QRadioButton(_text("gui.ccd_option_none"))
        self.ccd_inline_radio = QRadioButton(_text("gui.ccd_option_inline"))
        self.ccd_file_radio = QRadioButton(_text("gui.ccd_option_file"))
        self.ccd_radios = (
            ("none", self.ccd_none_radio),
            ("inline", self.ccd_inline_radio),
            ("file", self.ccd_file_radio),
        )
        for _mode, radio in self.ccd_radios:
            self.ccd_group.addButton(radio)
        self.ccd_none_radio.setChecked(True)
        self.ccd_group.buttonClicked.connect(lambda _button: self._refresh_ccd_controls())
        for _mode, radio in self.ccd_radios:
            layout.addWidget(radio)

        self.ccd_inline_edit = QPlainTextEdit()
        self.ccd_inline_edit.setFont(fixed_font())
        self.ccd_inline_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.ccd_inline_edit.setMinimumHeight(110)
        self.ccd_inline_label = QLabel(_text("gui.ccd_inline_label"))
        layout.addWidget(self.ccd_inline_label)
        layout.addWidget(self.ccd_inline_edit)

        self.ccd_path_edit = QLineEdit()
        self.ccd_browse_button = QPushButton(_text("gui.ccd_browse"))
        self.ccd_browse_button.clicked.connect(self.browse_ccd_file)
        self.ccd_path_row = QWidget()
        path_layout = QHBoxLayout(self.ccd_path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(self.ccd_path_edit, 1)
        path_layout.addWidget(self.ccd_browse_button)
        self.ccd_path_label = QLabel(_text("gui.ccd_path_label"))
        layout.addWidget(self.ccd_path_label)
        layout.addWidget(self.ccd_path_row)

        self.ccd_version_label = QLabel(
            _text("gui.ccd_path_version") % USER_CCD_PATH_MIN_VERSION
        )
        self.ccd_version_label.setWordWrap(True)
        layout.addWidget(self.ccd_version_label)
        self.ccd_current_label = QLabel()
        self.ccd_current_label.setWordWrap(True)
        layout.addWidget(self.ccd_current_label)
        self.ccd_apply_button = QPushButton(_text("gui.ccd_apply"))
        self.ccd_clear_button = QPushButton(_text("gui.ccd_clear"))
        self.ccd_apply_button.clicked.connect(self.apply_ccd)
        self.ccd_clear_button.clicked.connect(self.clear_ccd)
        row = QHBoxLayout()
        row.addWidget(self.ccd_apply_button)
        row.addWidget(self.ccd_clear_button)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    def _build_bonds(self):
        group, layout = self._group("gui.section_bonds")
        note = QLabel(_text("gui.bond_note"))
        note.setWordWrap(True)
        layout.addWidget(note)
        self._bond_notice = QLabel()
        self._bond_notice.setWordWrap(True)
        layout.addWidget(self._bond_notice)
        self.bond_table = QTableWidget(0, 2)
        self.bond_table.setHorizontalHeaderLabels(
            [_text("gui.bond_columns"), _text("gui.bond_atom")]
        )
        self.bond_table.verticalHeader().setVisible(False)
        self.bond_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.bond_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.bond_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.bond_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.bond_table.setMinimumHeight(120)
        layout.addWidget(self.bond_table)
        self.add_bond_button = QPushButton(_text("gui.bond_add"))
        self.remove_bond_button = QPushButton(_text("gui.bond_remove"))
        self.add_bond_button.clicked.connect(self.add_bond)
        self.remove_bond_button.clicked.connect(self.remove_selected_bond)
        row = QHBoxLayout()
        row.addWidget(self.add_bond_button)
        row.addWidget(self.remove_bond_button)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    # -- reading the page back ---------------------------------------------

    @property
    def state(self):
        """The session state every action routes through."""
        return self._state

    def record_key(self) -> str:
        """The entity the entity-scoped sections currently show."""
        return self._record_key

    def selected_record(self):
        """The record object behind the current key, or ``None``."""
        configuration = self._state.configuration
        if configuration is None or not self._record_key:
            return None
        for record in configuration.records:
            if record.ids.primary.value == self._record_key:
                return record
        return None

    def family_note_text(self) -> str:
        """The sentence shown when a family has no entity-scoped settings."""
        return self._family_note.text()

    def ccd_mode(self) -> str:
        """Which custom-CCD route the controls currently offer."""
        for mode, radio in self.ccd_radios:
            if radio.isChecked():
                return mode
        return "none"

    def choose_ccd_mode(self, mode: str) -> bool:
        """Select a custom-CCD route; ``False`` when it is not one."""
        for candidate, radio in self.ccd_radios:
            if candidate == mode:
                radio.setChecked(True)
                self._refresh_ccd_controls()
                return True
        return False

    def modification_rows(self):
        """The modification table as ``(code, position, residue)`` rows."""
        rows = []
        for row in range(self.modification_table.rowCount()):
            cells = [
                self.modification_table.item(row, column)
                for column in range(self.modification_table.columnCount())
            ]
            rows.append(tuple(cell.text() if cell else "" for cell in cells))
        return tuple(rows)

    def selected_modification_index(self):
        """The index (within the record's own list) of the selected row."""
        rows = {index.row() for index in self.modification_table.selectedIndexes()}
        if len(rows) != 1:
            return None
        return rows.pop()

    def bond_rows(self):
        """The bond table's display rows."""
        rows = []
        for row in range(self.bond_table.rowCount()):
            rows.append(
                tuple(
                    self.bond_table.item(row, column).text()
                    if self.bond_table.item(row, column)
                    else ""
                    for column in range(self.bond_table.columnCount())
                )
            )
        return tuple(rows)

    def selected_bond_index(self):
        rows = {index.row() for index in self.bond_table.selectedIndexes()}
        if len(rows) != 1:
            return None
        return rows.pop()

    # -- selection and refresh ---------------------------------------------

    def show_record(self, record_key) -> bool:
        """Show one entity's advanced settings; ``False`` when it is gone."""
        self._record_key = record_key or ""
        self.refresh()
        return self.selected_record() is not None

    def refresh(self) -> None:
        """Re-read the sections this instance owns from the services."""
        if self._scope in ("all", "entity"):
            record = self.selected_record()
            if record is None:
                self._record_key = ""
            self._refresh_title(record)
            self._refresh_alignment(record)
            self._refresh_templates(record)
            self._refresh_modifications(record)
        if self._scope in ("all", "ccd"):
            self._refresh_ccd()
        if self._scope in ("all", "bonds"):
            self._refresh_bonds()

    def _refresh_title(self, record) -> None:
        self._refresh_family_note(record)
        if record is None:
            self._title.setText(_text("gui.adv_no_selection"))
            return
        self._title.setText(
            _text("gui.adv_selected")
            % ("%s  ·  %s" % (record.ids.primary.value, family_label(record)))
        )

    def _refresh_family_note(self, record) -> None:
        """Explain why a ligand has no entity-scoped sections at all.

        DNA and RNA keep at least one section (modifications, or modifications
        and MSA), so the hidden groups need no sentence; a ligand would
        otherwise see an empty column.
        """
        ligand = record is not None and not isinstance(record, _POLYMER_FAMILIES)
        self._family_note.setText(
            _text("gui.entity_ligand_no_settings") if ligand else ""
        )
        self._family_note.setVisible(ligand)

    def _refresh_modifications(self, record) -> None:
        supported = isinstance(record, _POLYMER_FAMILIES)
        self.modification_table.setRowCount(0)
        self.modification_table.setEnabled(supported)
        self.modifications_group.setVisible(record is None or supported)
        for button in (
            self.add_modification_button,
            self.edit_modification_button,
            self.remove_modification_button,
        ):
            button.setEnabled(supported)
        if record is None:
            self._mod_notice.setText(_text("gui.adv_no_selection"))
            return
        if not supported:
            self._mod_notice.setText(_text("gui.mod_needs_polymer"))
            return
        self._mod_notice.setText(_text("gui.mod_note"))
        sequence = record.sequence.text
        for modification in record.modifications or ():
            position = modification.position.value
            residue = residue_at(sequence, position) or "-"
            row = self.modification_table.rowCount()
            self.modification_table.insertRow(row)
            for column, text in enumerate(
                (
                    modification_code_text(modification.code.value),
                    str(position),
                    residue,
                )
            ):
                self.modification_table.setItem(row, column, QTableWidgetItem(text))

    def _refresh_alignment(self, record) -> None:
        mode, source_kind, source_text, _paired_kind, _paired_text = (
            alignment_state(record) if record is not None else ("", "", "", "", "")
        )
        applicable = bool(mode)
        self.alignment_button.setEnabled(applicable)
        self.alignment_group.setVisible(record is None or applicable)
        if record is None:
            self._alignment_notice.setText(_text("gui.adv_no_selection"))
            self.alignment_label.setText("")
            return
        if not applicable:
            self._alignment_notice.setText(
                _text("gui.alignment_not_applicable") % family_label(record)
            )
            self.alignment_label.setText("")
            return
        self._alignment_notice.setText(_text("gui.alignment_hint"))
        self.alignment_label.setText(
            _text("gui.alignment_current") % self._alignment_text(mode, source_kind, source_text)
        )

    def _alignment_text(self, mode, source_kind, source_text) -> str:
        if mode == "automatic":
            return _text("gui.alignment_state_automatic")
        if mode == "free":
            return _text("gui.alignment_state_free")
        kind_key = (
            "gui.alignment_source_file"
            if source_kind == "file"
            else "gui.alignment_source_inline"
        )
        return _text("gui.alignment_state_provided") % _text(kind_key)

    def _refresh_templates(self, record) -> None:
        route, entries = (
            reference_state(record) if record is not None else ("", ())
        )
        applicable = bool(route)
        self.templates_button.setEnabled(applicable)
        self.templates_group.setVisible(record is None or applicable)
        if record is None:
            self._templates_notice.setText(_text("gui.adv_no_selection"))
            self.templates_label.setText("")
            return
        if not applicable:
            self._templates_notice.setText(_text("gui.templates_not_applicable"))
            self.templates_label.setText("")
            return
        self._templates_notice.setText(_text("gui.templates_hint_search"))
        if route == "search":
            current = _text("gui.templates_state_search")
        elif route == "none":
            current = _text("gui.templates_state_none")
        else:
            current = _text("gui.templates_provided") % len(entries)
        self.templates_label.setText(_text("gui.templates_current") % current)

    def _refresh_ccd(self) -> None:
        definition = None
        configuration = self._state.configuration
        if configuration is not None:
            definition = configuration.component_definition
        if definition is None:
            self._ccd_definition_mode = "none"
            self.ccd_current_label.setText(
                _text("gui.ccd_active") % _text("gui.ccd_active_none")
            )
        elif isinstance(definition, External):
            self._ccd_definition_mode = "file"
            self.ccd_current_label.setText(
                _text("gui.ccd_active")
                % (_text("gui.ccd_active_file") % definition.path.raw)
            )
        else:
            self._ccd_definition_mode = "inline"
            lines = len(definition.text.splitlines())
            self.ccd_current_label.setText(
                _text("gui.ccd_active")
                % (_text("gui.ccd_active_inline") % lines)
            )
        # The controls follow the definition that is actually set — but only
        # when it *changed*: a refresh caused by an unrelated edit must not
        # throw away a definition the user is in the middle of typing.
        signature = (self._ccd_definition_mode, definition)
        if signature != self._ccd_synced_definition:
            for mode, radio in self.ccd_radios:
                radio.setChecked(mode == self._ccd_definition_mode)
            self._ccd_synced_definition = signature
        self.ccd_clear_button.setEnabled(definition is not None)
        self._refresh_ccd_controls()

    def definition_mode(self) -> str:
        """Which custom-CCD route the job actually carries."""
        return getattr(self, "_ccd_definition_mode", "none")

    def _refresh_ccd_controls(self) -> None:
        mode = self.ccd_mode()
        for widget in (self.ccd_inline_label, self.ccd_inline_edit):
            widget.setVisible(mode == "inline")
        for widget in (self.ccd_path_label, self.ccd_path_row):
            widget.setVisible(mode == "file")
        self.ccd_version_label.setVisible(mode == "file")

    def _refresh_bonds(self) -> None:
        self.bond_table.setRowCount(0)
        configuration = self._state.configuration
        linkages = configuration.linkages if configuration is not None else ()
        words = self._entity_words()
        can_add = bool(configuration is not None and len(words) >= 2)
        self.add_bond_button.setEnabled(can_add)
        # The note above already explains what a bond is; this line is only
        # for a prerequisite the job does not meet yet.
        self._bond_notice.setText("" if can_add else _text("gui.bond_needs_entities"))
        self.remove_bond_button.setEnabled(bool(linkages))
        for linkage in linkages:
            row = self.bond_table.rowCount()
            self.bond_table.insertRow(row)
            for column, endpoint in enumerate((linkage.a, linkage.b)):
                self.bond_table.setItem(
                    row, column, QTableWidgetItem(self._endpoint_text(endpoint))
                )

    def _entity_words(self):
        """Every record as ``(key, display label)``, in configuration order."""
        configuration = self._state.configuration
        if configuration is None:
            return ()
        return tuple(
            (
                record.ids.primary.value,
                "%s  ·  %s" % (record.ids.primary.value, family_label(record)),
            )
            for record in configuration.records
        )

    def _endpoint_text(self, endpoint) -> str:
        """One endpoint as ``id (family), residue N, atom X``, for display."""
        label = endpoint.entity.value
        configuration = self._state.configuration
        if configuration is not None:
            for candidate in configuration.records:
                if candidate.ids.contains(endpoint.entity):
                    label = "%s (%s)" % (
                        endpoint.entity.value,
                        family_label(candidate),
                    )
                    break
        return _text("gui.bond_endpoint_text") % (
            label,
            endpoint.residue.value,
            endpoint.atom,
        )

    # -- modifications ------------------------------------------------------

    def _apply_modification(self, form, code, position, index=None):
        """One service call for the form the modification dialog collected.

        ``D`` is a residue replacement: the service resolves the CCD code from
        the canonical residue and refuses conflicts. ``L`` keeps the ordinary
        modification path (a PTM code), exactly as before.
        """
        if form == "D":
            if index is None:
                return self._state.set_amino_acid_form(
                    self._record_key, position, "D"
                )
            return self._state.update_modification(
                self._record_key, index, code=code, position=position
            )
        if index is None:
            return self._state.add_modification(self._record_key, code, position)
        return self._state.update_modification(
            self._record_key, index, code=code, position=position
        )

    def add_modification(self) -> bool:
        """Add a modification to the shown entity, through the service."""
        record = self.selected_record()
        if not isinstance(record, _POLYMER_FAMILIES):
            return False
        dialog = ModificationFormDialog(
            self,
            title=_text("gui.mod_dialog_add") % record.ids.primary.value,
            accept_text=_text("gui.form_add"),
            apply=lambda form, code, position: self._apply_modification(
                form, code, position
            ),
            sequence=record.sequence.text,
            hint=_text("gui.mod_note"),
            offer_forms=isinstance(record, FamilyARecord),
        )
        if dialog.exec() == ModificationFormDialog.Accepted:
            self._notify(_text("menu.modification_added"))
            return True
        return False

    def edit_selected_modification(self) -> bool:
        """Edit the selected modification (its own index in the record)."""
        record = self.selected_record()
        index = self.selected_modification_index()
        if not isinstance(record, _POLYMER_FAMILIES) or index is None:
            self._problems(_text("gui.mod_select_first"))
            return False
        modification = tuple(record.modifications or ())[index]
        dialog = ModificationFormDialog(
            self,
            title=_text("gui.mod_dialog_edit") % record.ids.primary.value,
            accept_text=_text("gui.form_save"),
            apply=lambda form, code, position: self._apply_modification(
                form, code, position, index=index
            ),
            code=modification.code.value,
            position=modification.position.value,
            sequence=record.sequence.text,
            hint=_text("gui.mod_note"),
            residue_form=(
                "D" if is_d_code(modification.code.value) else "L"
            ),
            offer_forms=isinstance(record, FamilyARecord),
        )
        if dialog.exec() == ModificationFormDialog.Accepted:
            self._notify(_text("menu.ptm_updated"))
            return True
        return False

    def remove_selected_modification(self) -> bool:
        """Remove the selected modification after confirmation."""
        record = self.selected_record()
        index = self.selected_modification_index()
        if not isinstance(record, _POLYMER_FAMILIES) or index is None:
            self._problems(_text("gui.mod_select_first"))
            return False
        modification = tuple(record.modifications or ())[index]
        question = _text("gui.mod_delete_question") % (
            modification.code.value,
            modification.position.value,
            record.ids.primary.value,
        )
        if not self.modification_confirmer(self, question):
            return False
        outcome = self._state.remove_modification(self._record_key, index)
        if not outcome.ok:
            self._problems(outcome.message or "")
            return False
        self._notify(_text("menu.modification_removed"))
        return True

    # -- alignment / MSA ----------------------------------------------------

    def change_alignment(self) -> bool:
        """Change the shown entity's alignment through the service."""
        record = self.selected_record()
        modes = self._modes_for(record)
        if not modes:
            return False
        mode, source_kind, source_text, paired_kind, paired_text = alignment_state(
            record
        )
        dialog = AlignmentFormDialog(
            self,
            title=_text("gui.alignment_dialog") % record.ids.primary.value,
            accept_text=_text("gui.form_save"),
            apply=lambda new_mode, kind, text, second_kind, second_text: (
                self._apply_alignment(
                    new_mode, kind, text, second_kind, second_text
                )
            ),
            modes=modes,
            mode=mode,
            source_kind=source_kind,
            source_text=source_text,
            paired_kind=paired_kind,
            paired_text=paired_text,
            hint=_text("gui.alignment_hint"),
        )
        if dialog.exec() == AlignmentFormDialog.Accepted:
            self._notify(_text("gui.alignment_applied"))
            return True
        return False

    def _modes_for(self, record):
        if isinstance(record, FamilyARecord):
            return _PROTEIN_MODES
        if isinstance(record, FamilyBRecord):
            return _RNA_MODES
        return ()

    def _apply_alignment(
        self, mode, source_kind, source_text, paired_kind="", paired_text=""
    ):
        """Send the chosen sources to the service, as it requires them.

        ``automatic``/``free`` are sent with no source at all — the service
        refuses a source for them — and a source-carrying mode gets exactly
        one of inline text or an external path. A ``both`` mode may also carry
        an independent paired side; no paired side means the unpaired one
        feeds both, which is the service's documented single-source rule.
        """
        keywords = {}
        if source_kind == "inline":
            keywords["inline_text"] = source_text
        elif source_kind == "file":
            keywords["external_path"] = source_text
        if paired_kind == "inline":
            keywords["paired_inline_text"] = paired_text
        elif paired_kind == "file":
            keywords["paired_external_path"] = paired_text
        return self._state.set_alignment(self._record_key, mode, **keywords)

    # -- templates ----------------------------------------------------------

    def edit_templates(self) -> bool:
        """Edit the shown protein's templates through the service."""
        record = self.selected_record()
        if not isinstance(record, FamilyARecord):
            return False
        route, entries = reference_state(record)
        dialog = TemplateEditorDialog(
            self,
            title=_text("gui.templates_dialog") % record.ids.primary.value,
            accept_text=_text("gui.form_save"),
            apply=lambda new_route, rows: self._apply_templates(new_route, rows),
            mode=route,
            entries=entries,
            hint=_text("gui.templates_hint_list"),
        )
        if dialog.exec() == TemplateEditorDialog.Accepted:
            self._notify(_text("gui.templates_applied"))
            return True
        return False

    def _apply_templates(self, route, rows):
        """Send the chosen reference state to the service.

        ``search`` and ``none`` map to the service's own two explicit calls;
        ``list`` becomes one ``ReferenceInput`` per row, with the pairs parsed
        exactly as the console parses them and the row's own kind deciding
        which of the mutually exclusive source fields is sent. Nothing here
        builds a wire value: ``ReferenceInput`` is the service's own typed
        input.
        """
        if route == "search":
            return self._state.set_references(self._record_key)
        if route == "none":
            return self._state.set_references(self._record_key, references=())
        references = tuple(
            ReferenceInput(
                external_path=(value or None) if kind == "file" else None,
                inline_text=(value or None) if kind == "inline" else None,
                pairs=parse_pairs(pairs_text),
            )
            for kind, value, pairs_text in rows
        )
        return self._state.set_references(self._record_key, references=references)

    # -- custom CCD definition ---------------------------------------------

    def browse_ccd_file(self):
        """Put a chosen CIF path in the file field (nothing is read here)."""
        path, _selected = QFileDialog.getOpenFileName(
            self,
            _text("gui.ccd_file_dialog"),
            "",
            _text("gui.ccd_file_filter"),
        )
        if path:
            self.ccd_path_edit.setText(path)
        return path

    def apply_ccd(self) -> bool:
        """Set the job's custom component definition, one representation only."""
        mode = self.ccd_mode()
        if mode == "none":
            return self.clear_ccd()
        if mode == "inline":
            outcome = self._state.set_component_definition(
                inline_text=self.ccd_inline_edit.toPlainText()
            )
        else:
            outcome = self._state.set_component_definition(
                external_path=self.ccd_path_edit.text().strip()
            )
        if not outcome.ok:
            self._problems(outcome.message or "")
            return False
        self._notify(_text("gui.ccd_applied"))
        return True

    def clear_ccd(self) -> bool:
        """Remove the job's custom component definition."""
        outcome = self._state.clear_component_definition()
        if not outcome.ok:
            self._problems(outcome.message or "")
            return False
        self._notify(_text("gui.ccd_cleared"))
        return True

    # -- covalent bonds -----------------------------------------------------

    def add_bond(self) -> bool:
        """Add one covalent linkage through the service."""
        choices = self._entity_words()
        if len(choices) < 2:
            self._problems(_text("gui.bond_needs_entities"))
            return False
        dialog = BondFormDialog(
            self,
            title=_text("gui.bond_dialog"),
            accept_text=_text("gui.form_add"),
            apply=lambda a_key, a_residue, a_atom, b_key, b_residue, b_atom: (
                self._state.add_linkage(
                    a_key, a_residue, a_atom, b_key, b_residue, b_atom
                )
            ),
            choices=choices,
            left=choices[0][0],
            right=choices[1][0],
            hint=_text("gui.bond_note"),
        )
        if dialog.exec() == BondFormDialog.Accepted:
            self._notify(_text("gui.bond_added"))
            return True
        return False

    def remove_selected_bond(self) -> bool:
        """Remove the selected linkage after confirmation."""
        index = self.selected_bond_index()
        configuration = self._state.configuration
        if index is None or configuration is None:
            self._problems(_text("gui.bond_select_first"))
            return False
        linkage = tuple(configuration.linkages)[index]
        question = _text("gui.bond_delete_question") % (
            self._endpoint_text(linkage.a),
            self._endpoint_text(linkage.b),
        )
        if not self.bond_confirmer(self, question):
            return False
        outcome = self._state.remove_linkage(index)
        if not outcome.ok:
            self._problems(outcome.message or "")
            return False
        self._notify(_text("gui.bond_removed"))
        return True

    def bond_pair_texts(self):
        """The stored linkages as display pairs, in configuration order."""
        configuration = self._state.configuration
        if configuration is None:
            return ()
        return tuple(
            _text("gui.bond_pair_text")
            % (self._endpoint_text(linkage.a), self._endpoint_text(linkage.b))
            for linkage in configuration.linkages
        )
