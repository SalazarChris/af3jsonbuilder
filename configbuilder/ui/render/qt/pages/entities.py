"""The Entities workspace: one compact picker and three work areas.

The large entity table is gone. A single drop-down at the top lists every
record the job holds — identity, family and a short summary, so both strands
of a DNA duplex and every identifier of a multi-copy ligand are visible — and
the actions (Add Protein/RNA/DNA/Ligand, Edit, Delete) sit beside it.

Below the picker, the page is split into three labelled work areas:

- **Entity settings** — the selected entity's compact facts (length or
  representation, description, DNA partner) and its own settings, with
  Alignment/MSA first, then templates, then PTMs;
- **Custom CCDs** — the job-wide ``userCCD``/``userCCDPath`` definition;
- **Covalent bonds** — the job-wide endpoints that connect entities.

The last two are job-wide configuration, so they are not mixed into the
selected entity's settings: each has its own visible area and says so. The
entity-scoped ``AdvancedPage`` instance the window exposes still owns those
settings; this page only hosts it.

The picker remains a read-only projection: :class:`EntityTableModel` lists
``configuration.records`` in the order the configuration holds them.
Everything the action buttons do routes through
:class:`~configbuilder.ui.render.qt.state.GuiState` → ``ConfigurationService``:
the page collects values, asks its one confirmation question and refreshes.
It never builds a record, allocates or renames an identifier, computes a DNA
complement, parses a ligand representation beyond the service's own documented
separators, or writes anything.

Identity is the registry's own primary identifier (a row's ``record_key``);
no action addresses a record by row number.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from configbuilder.app.version_features import DESCRIPTION_MIN_VERSION
from configbuilder.model import (
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    Pinned,
    Present,
    fold_representation,
)
from configbuilder.ui.present.notices import removal_notice
from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.qt.dialogs import (
    LigandFormDialog,
    SequenceFormDialog,
    choose_batch_file,
    choose_batch_kind,
    choose_batch_target,
    choose_output_folder,
    confirm_batch_preview,
    confirm_entity_delete,
    report_batch_run,
)
from configbuilder.app.results import batch_counts
from configbuilder.ui.present.strings import batch_summary
from configbuilder.ui.render.qt.models import EntityTableModel
from configbuilder.ui.render.qt.style import (
    heading_label,
    hint_label,
    page_title_label,
)

__all__ = ["EntitiesPage"]


# The compact fact rows. A chain shows its length, a ligand its
# representation; description is common, and only DNA has a partner. The
# full sequence is never rendered here — it is edited in the Add/Edit dialog.
_DETAIL_ROW_LABELS = (
    "gui.entity_length",
    "gui.entity_representation",
    "gui.col_description",
    "gui.entity_partner_label",
)
(
    _LENGTH,
    _REPRESENTATION,
    _DESCRIPTION,
    _PARTNER,
) = range(len(_DETAIL_ROW_LABELS))

# The add/edit dialog titles, per family. Literal keys (a front end may not
# build registry keys dynamically: the meta-test requires each entry to be
# referenced where it is used).
_ADD_TITLE_KEYS = {
    "protein": "gui.dialog_add_protein",
    "rna": "gui.dialog_add_rna",
    "dna": "gui.dialog_add_dna",
}
_EDIT_TITLE_KEYS = {
    FamilyARecord: "gui.dialog_edit_protein",
    FamilyBRecord: "gui.dialog_edit_rna",
    FamilyCRecord: "gui.dialog_edit_dna",
}

_SEQUENCE_HINT_KEYS = {
    "protein": "gui.sequence_add_hint",
    "rna": "gui.sequence_add_hint",
    "dna": "gui.dna_add_hint",
}


def _presence_text(value) -> str:
    """A description presence as the edit field's text (empty for unset)."""
    if isinstance(value, Present):
        return value.value
    return ""


def _ccd_tokens(text: str):
    """The component codes in ``text``, split the way the service documents.

    ``ConfigurationService._ccds`` accepts whitespace, commas and semicolons
    as separators for one multi-component ligand; the same separators are
    applied here because the *edit* route (``set_representation``) takes an
    already-separated sequence of codes. Every token is still validated by
    the service.
    """
    return text.replace(",", " ").replace(";", " ").split()


class EntitiesPage(QWidget):
    """The entity table, the selected record's details, and the actions."""

    #: The identifier of the row the user has selected (``""`` for none).
    #: The Advanced page follows it, so both tabs always speak about the same
    #: entity without either page owning the other's state.
    selection_changed = Signal(str)

    def __init__(
        self,
        state,
        notify=None,
        problems=None,
        advanced=None,
        ccd=None,
        bonds=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._notify = notify if notify is not None else (lambda message: None)
        self._problems = problems if problems is not None else (lambda message: None)
        # The entity-scoped Stage 4 settings, hosted here when the window
        # supplies the page; ``None`` keeps this page usable on its own.
        self._advanced = advanced
        # The job-wide work areas: their own AdvancedPage instances, so they
        # never appear among the selected entity's settings.
        self._ccd = ccd
        self._bonds = bonds
        self._model = EntityTableModel(self)
        # The compact fact rows, keyed by the registry label they display —
        # what ``detail_text`` reads back without depending on widget order.
        self._detail_labels = {}
        # Both halves of a detail row, so a family can hide facts that do not
        # apply to it instead of showing "-" for every irrelevant one.
        self._detail_rows = {}
        # The last selection announced through ``selection_changed``, so a
        # refresh that rebuilds the same selection does not re-announce it.
        self._announced_key = None
        # Seams the tests replace: the delete confirmation is a modal box by
        # default, and the forms are real dialogs whose modal loop the tests
        # stand in for.
        self.delete_confirmer = confirm_entity_delete
        # The file-generation workflow's six modal seams: the input-type
        # question, the add-or-replace question, the two path pickers, the
        # review box and the result report.
        self.batch_kind_chooser = choose_batch_kind
        self.batch_target_chooser = choose_batch_target
        self.batch_file_chooser = choose_batch_file
        self.batch_folder_chooser = choose_output_folder
        self.batch_previewer = confirm_batch_preview
        self.batch_reporter = report_batch_run
        self._build()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        """A compact picker above three labelled work areas.

        The picker replaces the table: choosing an entry selects that record
        and shows its facts and settings. Custom CCDs and Covalent bonds have
        their own tabs, because they belong to the whole job.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(page_title_label(_text("gui.tab_entities")))
        layout.addWidget(self._build_selector())
        self.tabs = QTabWidget()
        self.workspace = self._build_workspace()
        self.tabs.addTab(self.workspace, _text("gui.entity_tab_settings"))
        self.ccd_tab = self._build_job_area(self._ccd)
        self.tabs.addTab(self.ccd_tab, _text("gui.entity_tab_ccd"))
        self.bonds_tab = self._build_job_area(self._bonds)
        self.tabs.addTab(self.bonds_tab, _text("gui.entity_tab_bonds"))
        layout.addWidget(self.tabs, 1)

    def _build_selector(self):
        """One compact picker and the actions that manage the selection.

        The drop-down's entries carry identity, family and a short summary, so
        both DNA strands and every identifier of a multi-copy ligand are
        distinguishable without a wide table.
        """
        row = QWidget()
        outer = QVBoxLayout(row)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(QLabel(_text("gui.entity_selector")))
        self.selector = QComboBox()
        self.selector.setAccessibleName(_text("gui.entity_selector"))
        self.selector.setMinimumContentsLength(34)
        self.selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.selector.currentIndexChanged.connect(self._on_selector_changed)
        layout.addWidget(self.selector, 1)
        self.edit_button = QPushButton(_text("gui.action_edit_record"))
        self.delete_button = QPushButton(_text("gui.action_delete_record"))
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        layout.addWidget(self.edit_button)
        layout.addWidget(self.delete_button)
        outer.addLayout(layout)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(6)
        self.add_protein_button = QPushButton(_text("gui.action_add_protein"))
        self.add_rna_button = QPushButton(_text("gui.action_add_rna"))
        self.add_dna_button = QPushButton(_text("gui.action_add_dna"))
        self.add_ligand_button = QPushButton(_text("gui.action_add_ligand"))
        self.add_protein_button.clicked.connect(self.add_protein)
        self.add_rna_button.clicked.connect(self.add_rna)
        self.add_dna_button.clicked.connect(self.add_dna)
        self.add_ligand_button.clicked.connect(self.add_ligand)
        for button in (
            self.add_protein_button,
            self.add_rna_button,
            self.add_dna_button,
            self.add_ligand_button,
        ):
            add_row.addWidget(button)
        add_row.addStretch(1)
        outer.addLayout(add_row)

        # The file-driven workflow lives with the entity actions because that
        # is exactly what it extends: one entity per input entry — protein, DNA
        # or RNA sequence, or a ligand — added to this job as the base. It reads
        # the job and writes files; it never changes the job on screen.
        file_row = QHBoxLayout()
        file_row.setContentsMargins(0, 0, 0, 0)
        file_row.setSpacing(8)
        self.batch_file_button = QPushButton(_text("gui.action_file_generation"))
        self.batch_file_button.setToolTip(_text("gui.action_file_generation_hint"))
        self.batch_file_button.setAccessibleName(self.batch_file_button.text())
        self.batch_file_button.clicked.connect(self.generate_from_file)
        file_row.addWidget(self.batch_file_button)
        file_row.addWidget(hint_label(_text("gui.entity_file_note")), 1)
        outer.addLayout(file_row)

        self._notice = hint_label("")
        outer.addWidget(self._notice)
        return row

    def _build_workspace(self):
        """The selected entity: compact facts, then its own settings."""
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(self._build_details())
        if self._advanced is not None:
            layout.addWidget(heading_label(_text("gui.entity_settings")))
            layout.addWidget(self._advanced, 1)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("entityWorkspace")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        return scroll

    def _build_job_area(self, page):
        """A job-wide work area: the scope note, then its controls.

        The tab already names the area, so the note is the only heading the
        content needs.
        """
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(hint_label(_text("gui.entity_job_wide")))
        if page is not None:
            layout.addWidget(page)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        return scroll

    def _build_details(self):
        """A compact facts card; the full editor stays behind the Edit action.

        No sequence is rendered: a chain reports its length and a ligand its
        representation. The exact sequence remains in the Add/Edit form.
        """
        card = QFrame()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(6)
        outer.addWidget(heading_label(_text("gui.entity_details")))
        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self._title)
        outer.addWidget(hint_label(_text("gui.entity_details_hint")))

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(6)
        for label_key in _DETAIL_ROW_LABELS:
            row_label = QLabel(_text(label_key))
            row_label.setWordWrap(True)
            label = QLabel()
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(row_label, label)
            self._detail_labels[label_key] = label
            self._detail_rows[label_key] = (row_label, label)
        outer.addLayout(form)
        return card

    # -- the file-generation workflow ---------------------------------------

    def generate_from_file(self) -> None:
        """One input file in, one configuration per entry out.

        Six steps, no detour: what the file holds, which file, whether the
        entries are new entities or new content for one the job already holds,
        show what was read, which folder, write. The kind comes first because the answer is
        what makes the file readable — a ``.txt`` of amino-acid codes is a
        protein batch only because the user said so, and guessing from the
        content would silently reinterpret their data. After that the preview
        is the service's own read-only check (so an empty file, a duplicate
        entry or an unreadable path refuses here, before a folder is chosen),
        the write is one service call that plans and validates before touching
        a file, and the report lists what was actually written. Nothing about
        the open job changes.
        """
        kind = self.batch_kind_chooser(self)
        if not kind:
            return
        path = self.batch_file_chooser(self, kind)
        if not path:
            return
        # Add or replace: the entries can become new entities, or new content
        # for one entity this job already holds. The rows offered are the
        # service's own, filtered to the family the chosen kind builds, so the
        # page never proposes a target the service would refuse.
        targets = self._state.batch_target_rows(kind)
        answer = self.batch_target_chooser(self, targets, kind)
        if answer is None:
            return
        replace_key = answer[1]
        replaced = next(
            (
                "%s (%s)" % (row.key, row.summary)
                for row in targets
                if row.key == replace_key
            ),
            "",
        )
        preview = self._state.inspect_input_file(path, kind, replace_key or None)
        if not preview.ok:
            self._problems(preview.message)
            return
        # The folder is offered already chosen: ``generated_configurations``
        # under the shared output root (or the last batch's folder), not an
        # empty dialog remembering some unrelated directory. The preview below
        # names the same folder, so what is shown is what is written.
        root = self.batch_folder_chooser(self, self._default_batch_root())
        if not root:
            return
        if not self.batch_previewer(self, preview, root, kind, replaced=replaced):
            return
        outcome = self._state.generate_input_configurations(
            path, root, kind, replace_key or None
        )
        self.batch_reporter(self, outcome)
        if outcome.ok:
            # Only a run that wrote something moves the next default.
            self._state.paths.remember_batch_directory(root)
            # The same sentence the console prints and the report box shows,
            # so the status line cannot disagree with the dialog.
            self._notify(batch_summary(batch_counts(outcome)))

    def _default_batch_root(self) -> str:
        """The batch destination to offer first, or an empty string."""
        try:
            return self._state.paths.default_batch_root()
        except (OSError, ValueError):
            return ""

    # -- reading the details pane back --------------------------------------

    def detail_title(self) -> str:
        """The details pane's title line as displayed."""
        return self._title.text()

    def detail_text(self, label_key: str) -> str:
        """What the details pane shows for ``label_key``, as displayed."""
        label = self._detail_labels.get(label_key)
        return label.text() if label is not None else ""

    # -- refresh -----------------------------------------------------------

    def refresh(self) -> None:
        """Re-project the picker from the configuration the service holds.

        The previous selection is kept when its record is still there, so a
        mutation elsewhere on the page does not yank the user to another entry.
        """
        selected = self.selected_record_key()
        self._model.set_configuration(self._state.configuration)
        has_project = self._state.configuration is not None
        for button in (
            self.add_protein_button,
            self.add_rna_button,
            self.add_dna_button,
            self.add_ligand_button,
        ):
            button.setEnabled(has_project)
        rows = self._model.rows
        self.selector.blockSignals(True)
        self.selector.clear()
        for row in rows:
            self.selector.addItem(self._choice_text(row), row.record_key)
        self.selector.setEnabled(bool(rows))
        index = self._model.row_for_record_key(selected) if selected else -1
        if index < 0 and rows:
            index = 0
        self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)
        self._notice.setText(
            _text("gui.entities_none")
            if has_project and not rows
            else ""
        )
        self._apply_selection(self._model.row_at(index) if index >= 0 else None)

    def _choice_text(self, row) -> str:
        """One picker entry: identity, family and a short, family-own summary."""
        if row.is_sequence:
            return _text("gui.entity_choice_sequence") % (
                row.ids,
                row.family,
                len(row.record.sequence.text),
            )
        return _text("gui.entity_choice_ligand") % (
            row.ids,
            row.family,
            row.summary,
        )

    @property
    def state(self):
        """The session state every action routes through."""
        return self._state

    @property
    def model(self):
        """The entity table model (read back by callers and tests)."""
        return self._model

    def select_record(self, record_key) -> bool:
        """Select the entry whose identifier is ``record_key``."""
        position = self._model.row_for_record_key(record_key)
        if position < 0:
            return False
        self.selector.setCurrentIndex(position)
        return True

    def selected_record_key(self) -> str:
        """The selected entry's registry identifier, or ``""``."""
        row = self._selected_row()
        return row.record_key if row is not None else ""

    def _selected_row(self):
        key = self.selector.currentData()
        position = self._model.row_for_record_key(key) if key else -1
        return self._model.row_at(position) if position >= 0 else None

    def _update_action_state(self) -> None:
        has_selection = self._selected_row() is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    # -- add (Stage 3) -----------------------------------------------------

    def add_protein(self) -> bool:
        return self._add_sequence("protein")

    def add_rna(self) -> bool:
        return self._add_sequence("rna")

    def add_dna(self) -> bool:
        """Add DNA, asking whether the entered strand is half of a duplex.

        The question is the console's own (``menu.dna_complement_menu``); the
        answer is passed to the service, which builds the complement. A
        single-stranded answer is a supported model state — the lone record an
        imported single DNA chain produces — not a degraded duplex.
        """
        return self._add_sequence("dna")

    def add_ligand(self) -> bool:
        """Add a ligand: exactly one representation, plus copies and description."""
        dialog = LigandFormDialog(
            self,
            title=_text("gui.dialog_add_ligand"),
            accept_text=_text("gui.form_add"),
            apply=lambda kind, value, copies, description: self._add_with_selection(
                lambda: self._state.add_record(
                    "ligand",
                    representation=value,
                    representation_kind=kind,
                    copies=copies,
                    description=(description.strip() or None),
                )
            ),
            hint=_text("gui.ligand_form_hint"),
            warning=self._description_warning(),
        )
        if dialog.exec() == LigandFormDialog.Accepted:
            self._notify(_text("menu.entity_added"))
            return True
        return False

    def _add_sequence(self, family: str) -> bool:
        """Add a protein/RNA/DNA chain through the service's own add.

        Only DNA gets the duplex control; the other families pass the
        service's own default through unchanged.
        """
        dialog = SequenceFormDialog(
            self,
            title=_text(_ADD_TITLE_KEYS[family]),
            accept_text=_text("gui.form_add"),
            apply=lambda sequence, description, duplex: self._add_with_selection(
                lambda: self._state.add_record(
                    family,
                    sequence=sequence,
                    description=(description.strip() or None),
                    duplex=duplex,
                )
            ),
            hint=_text(_SEQUENCE_HINT_KEYS[family]),
            warning=self._description_warning(),
            duplex=(True if family == "dna" else None),
        )
        if dialog.exec() == SequenceFormDialog.Accepted:
            self._notify(_text("menu.entity_added"))
            return True
        return False

    def _add_with_selection(self, add):
        """Run an add, then select the record(s) the service just created.

        The new keys are found by comparing the model's rows before and after
        — the identifiers themselves are the service's, never computed here.
        """
        before = {row.record_key for row in self._model.rows}
        outcome = add()
        if outcome.ok:
            for row in self._model.rows:
                if row.record_key not in before:
                    self.select_record(row.record_key)
                    break
        return outcome

    # -- edit (Stage 3) ----------------------------------------------------

    def edit_selected(self) -> bool:
        """Edit the selected record's basic fields, by record type."""
        row = self._selected_row()
        if row is None:
            return False
        if row.is_sequence:
            return self._edit_sequence(row)
        return self._edit_ligand(row)

    def _edit_sequence(self, row) -> bool:
        original = _presence_text(row.record.description)
        dialog = SequenceFormDialog(
            self,
            title=_text(_EDIT_TITLE_KEYS[type(row.record)]),
            accept_text=_text("gui.form_save"),
            apply=lambda sequence, description, _duplex: self._apply_sequence_edit(
                row, original, sequence, description
            ),
            sequence=row.record.sequence.text,
            description=original,
            hint=_text("gui.dna_edit_hint" if row.is_dna else "gui.sequence_edit_hint"),
            warning=self._description_warning(),
        )
        if dialog.exec() == SequenceFormDialog.Accepted:
            self._notify(_text("menu.applied"))
            return True
        return False

    def _apply_sequence_edit(self, row, original, sequence, description):
        """Send the edit to the service; unchanged text is passed as ``None``.

        Passing ``None`` for an unchanged description preserves the record's
        exact presence (unset stays unset, explicitly empty stays explicitly
        empty) instead of rewriting it.
        """
        return self._state.update_record(
            row.record_key,
            sequence=sequence,
            description=(description if description != original else None),
        )

    def _edit_ligand(self, row) -> bool:
        original = _presence_text(row.record.description)
        # The model's own fold is the only dispatch over a representation
        # (plan §7.3): the form gets the component codes or the notation, and
        # never both.
        kind, value = fold_representation(
            row.record.representation,
            lambda codes: ("ccd", " ".join(code.value for code in codes)),
            lambda text: ("smiles", text),
        )
        dialog = LigandFormDialog(
            self,
            title=_text("gui.dialog_edit_ligand"),
            accept_text=_text("gui.form_save"),
            apply=lambda new_kind, new_value, copies, description: self._apply_ligand_edit(
                row, original, new_kind, new_value, description
            ),
            kind=kind,
            value=value,
            copies=len(row.record.ids),
            copies_editable=False,
            description=original,
            hint=_text("gui.ligand_form_hint"),
            warning=self._description_warning(),
        )
        if dialog.exec() == LigandFormDialog.Accepted:
            self._notify(_text("menu.applied"))
            return True
        return False

    def _apply_ligand_edit(self, row, original, kind, value, description):
        """Send the whole ligand edit as **one** service call.

        ``update_component_record`` validates the representation before it
        commits anything, so a refused code cannot leave a description
        half-applied — which is exactly what the two-call route
        (``set_representation`` then ``update_record``) allowed. The
        description is passed only when it actually changed, so the record's
        exact presence (unset vs explicitly empty) is preserved otherwise.
        """
        if kind == "smiles":
            return self._state.update_component_record(
                row.record_key,
                notation=value,
                description=(description if description != original else None),
            )
        return self._state.update_component_record(
            row.record_key,
            codes=_ccd_tokens(value),
            description=(description if description != original else None),
        )

    # -- delete (Stage 3) --------------------------------------------------

    def delete_selected(self) -> bool:
        """Remove the selected record, with a consequence-naming confirmation."""
        row = self._selected_row()
        if row is None:
            return False
        if not self.delete_confirmer(self, self._delete_message(row)):
            return False
        outcome = self._state.remove_record(row.record_key)
        if not outcome.ok:
            self._problems(outcome.message or "")
            return False
        self._notify(_text("menu.removed") % row.ids)
        return True

    def _delete_message(self, row) -> str:
        """What the confirmation says, from the record's own shape.

        The wording is shared with the console (``present.notices``), so the
        same deletion is described identically in both front ends.
        """
        return removal_notice(row.ids, row.partner_key, len(row.record.ids))

    # -- the description/version explanation -------------------------------

    def _description_warning(self) -> str:
        """The version explanation a supplied description needs, or ``""``.

        The minimum version is the mapping layer's (via ``app``); this method
        only compares it with the job's current pin and words the result.
        Nothing is upgraded or refused here.
        """
        configuration = self._state.configuration
        if configuration is None:
            return ""
        selection = configuration.format_target.version_selection
        if not isinstance(selection, Pinned) or selection.version >= DESCRIPTION_MIN_VERSION:
            return ""
        return _text("gui.description_version_warning") % (
            selection.version,
            DESCRIPTION_MIN_VERSION,
        )

    # -- details -----------------------------------------------------------

    def _clear_details(self) -> None:
        self._title.setText("")
        for label in self._detail_labels.values():
            label.setText("")
        self._show_detail_rows(None)

    def _on_selector_changed(self, index) -> None:
        self._apply_selection(self._model.row_at(index))

    def _apply_selection(self, row) -> None:
        """Show one record's compact facts; never renders the full sequence."""
        self._update_action_state()
        key = row.record_key if row is not None else ""
        if key != getattr(self, "_announced_key", None):
            self._announced_key = key
            self.selection_changed.emit(key)
        if row is None:
            self._clear_details()
            return
        self._title.setText("%s  ·  %s" % (row.ids, row.family))
        self._detail_labels[_DETAIL_ROW_LABELS[_LENGTH]].setText(
            _text("gui.entity_length_value") % len(row.record.sequence.text)
            if row.is_sequence
            else ""
        )
        self._detail_labels[_DETAIL_ROW_LABELS[_REPRESENTATION]].setText(
            "" if row.is_sequence else row.summary
        )
        self._detail_labels[_DETAIL_ROW_LABELS[_DESCRIPTION]].setText(row.description)
        if row.partner_key:
            self._detail_labels[_DETAIL_ROW_LABELS[_PARTNER]].setText(
                _text("gui.entity_partner") % row.partner_key
            )
        elif row.is_dna:
            self._detail_labels[_DETAIL_ROW_LABELS[_PARTNER]].setText(
                _text("gui.entity_no_partner")
            )
        else:
            self._detail_labels[_DETAIL_ROW_LABELS[_PARTNER]].setText("")
        self._show_detail_rows(row)

    def _show_detail_rows(self, row) -> None:
        """Hide the facts a record's family does not have."""
        if row is None:
            for label, value in self._detail_rows.values():
                label.setVisible(False)
                value.setVisible(False)
            return
        visible = {
            "gui.entity_length": row.is_sequence,
            "gui.entity_representation": not row.is_sequence,
            "gui.col_description": True,
            "gui.entity_partner_label": row.is_dna,
        }
        for key, (label, value) in self._detail_rows.items():
            shown = visible.get(key, True)
            label.setVisible(shown)
            value.setVisible(shown)
