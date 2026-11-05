"""Advanced-entity forms: modifications, alignment/MSA, templates, bonds.

Every dialog here follows the Stage 3 discipline: it collects values, shows a
service refusal on its own message line and keeps itself open so the value can
be corrected. Nothing here validates a domain rule, allocates anything, reads
a file or decides whether a mode is legal — the *page* supplies the choices
(from the model) and the `apply` callable, and the service answers.

The shared `_FormDialog` base owns the accept/cancel pair, the error line and
the submit path, so the forms below contain only their own fields.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from configbuilder.app.version_features import MSA_PATH_MIN_VERSION
from configbuilder.model import d_code_for
from configbuilder.ui.present.sequence import residue_at
from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.qt.models import fixed_font

__all__ = [
    "AlignmentFormDialog",
    "BondFormDialog",
    "MAX_POSITION",
    "ModificationFormDialog",
    "TemplateEditorDialog",
]

#: The largest residue/atom position any form offers. The model's own rule is
#: "a positive integer, 1-based"; this is a bounded spin box, not a domain
#: limit, and the service/validation layer stays the authority.
MAX_POSITION = 9999

# The MSA source routes, as ``(registry key, kind)`` — the same two routes the
# console offers (``menu.msa_paste_inline`` / ``menu.msa_use_file``).
_SOURCE_OPTIONS = (
    ("menu.msa_paste_inline", "inline"),
    ("menu.msa_use_file", "file"),
)

# The paired side of a ``both`` alignment: optionally its own source, or the
# unpaired one reused (the service's own single-source behaviour).
_PAIRED_SOURCE_OPTIONS = (
    ("gui.alignment_paired_same", "same"),
) + _SOURCE_OPTIONS

# The three template routes, as ``(registry key, route word)``.
_TEMPLATE_ROUTES = (
    ("menu.templates_search", "search"),
    ("menu.templates_none", "none"),
    ("menu.templates_list", "list"),
)


class _FormDialog(QDialog):
    """Accept only on a successful apply; show the service's own refusal."""

    def __init__(self, parent, title: str, accept_text: str, apply) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self._apply = apply
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self._buttons = QDialogButtonBox()
        self.accept_button = self._buttons.addButton(
            accept_text, QDialogButtonBox.AcceptRole
        )
        self.cancel_button = self._buttons.addButton(
            _text("gui.form_cancel"), QDialogButtonBox.RejectRole
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout = QVBoxLayout(self)
        self._form = QFormLayout()

    def error_text(self) -> str:
        """The last refusal as displayed (empty when nothing was refused)."""
        return self.error_label.text()

    def finish_layout(self) -> None:
        """Add the form, the error line and the buttons (call last)."""
        self._layout.addLayout(self._form)
        self._layout.addWidget(self.error_label)
        self._layout.addWidget(self._buttons)

    def _collect(self):
        raise NotImplementedError

    def accept(self) -> None:
        outcome = self._apply(*self._collect())
        if getattr(outcome, "ok", False):
            super().accept()
            return
        self.error_label.setText(getattr(outcome, "message", "") or "")
        self.error_label.setVisible(True)


class ModificationFormDialog(_FormDialog):
    """Add or edit one modification: a code and a 1-based residue position.

    A protein chain also offers its residue's stereochemical form. ``L`` is
    the default and keeps the ordinary modification editor (a PTM code typed
    or imported). ``D`` is a *residue replacement*: the CCD code is resolved
    from the canonical residue at the chosen 1-based position, the code field
    becomes read-only, and the form shows what was resolved. Glycine (achiral)
    and positions outside the chain cannot select a D-form; the option is
    disabled and the reason is stated.

    Codes resolve from the central registry only; this dialog never validates
    a domain rule or builds a record. The page sends the answer to the service,
    which is the authority on positions, conflicts and mapping.
    """

    def __init__(
        self,
        parent,
        title,
        accept_text,
        apply,
        code="",
        position=1,
        sequence="",
        hint="",
        residue_form="L",
        offer_forms=False,
    ) -> None:
        super().__init__(parent, title, accept_text, apply)
        self._sequence = sequence or ""
        self._forms_offered = bool(offer_forms)
        self._initial_form = (
            "D"
            if self._forms_offered and str(residue_form).strip().upper() == "D"
            else "L"
        )
        self._manual_code = "" if self._initial_form == "D" else (code or "")
        self._selected_form = self._initial_form
        self.code_edit = QLineEdit(code)
        self.code_edit.setPlaceholderText(_text("gui.mod_code_placeholder"))
        self.position_spin = QSpinBox()
        self.position_spin.setRange(1, MAX_POSITION)
        self.position_spin.setValue(max(1, min(int(position), MAX_POSITION)))
        self._form.addRow(_text("gui.mod_form_code"), self.code_edit)
        self._form.addRow(_text("gui.mod_form_position"), self.position_spin)
        self.residue_label = QLabel()
        self.residue_label.setWordWrap(True)
        self._form.addRow("", self.residue_label)

        # The stereochemical form: only a protein chain has chiral residues.
        self.form_row = QWidget()
        form_layout = QHBoxLayout(self.form_row)
        form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_group = QButtonGroup(self)
        self.l_form_radio = QRadioButton(_text("gui.mod_form_l"))
        self.d_form_radio = QRadioButton(_text("gui.mod_form_d"))
        self.form_group.addButton(self.l_form_radio)
        self.form_group.addButton(self.d_form_radio)
        form_layout.addWidget(self.l_form_radio)
        form_layout.addWidget(self.d_form_radio)
        form_layout.addStretch(1)
        self._form.addRow(_text("gui.mod_form_form"), self.form_row)
        self.form_hint_label = QLabel(_text("gui.mod_form_d_hint"))
        self.form_hint_label.setWordWrap(True)
        self._form.addRow("", self.form_hint_label)
        self.form_row.setVisible(self._forms_offered)
        self.form_hint_label.setVisible(self._forms_offered)
        self.l_form_radio.setChecked(self._selected_form == "L")
        self.d_form_radio.setChecked(self._selected_form == "D")

        if hint:
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            self._layout.addWidget(hint_label)
        self.finish_layout()
        self.position_spin.valueChanged.connect(self._refresh)
        self.form_group.buttonClicked.connect(lambda _button: self._refresh_form())
        self._refresh()

    def _refresh(self) -> None:
        self._refresh_residue()
        self._refresh_form()

    def _refresh_residue(self) -> None:
        """Echo the residue at the chosen position (the console's own echo)."""
        position = self.position_spin.value()
        residue = residue_at(self._sequence, position)
        if residue is None:
            self.residue_label.setText(
                _text("gui.mod_residue_out_of_range")
                % (position, len(self._sequence))
            )
            return
        self.residue_label.setText(_text("gui.mod_residue_echo") % residue)

    def _unavailable_hint(self, residue) -> str:
        """Why the D-form is not offered at the chosen position."""
        if residue is None:
            return _text("gui.mod_form_d_needs_position")
        if residue == "G":
            return _text("gui.mod_form_d_glycine")
        return _text("gui.mod_form_d_no_mapping") % residue

    def _refresh_form(self) -> None:
        """Resolve the D-form's CCD code, or explain why there is none."""
        if not self._forms_offered:
            self.code_edit.setReadOnly(False)
            return
        residue = residue_at(self._sequence, self.position_spin.value())
        code = d_code_for(residue) if residue is not None else None
        available = code is not None
        self.d_form_radio.setEnabled(available)
        if available:
            self.form_hint_label.setText(_text("gui.mod_form_resolved") % code)
        else:
            self.form_hint_label.setText(self._unavailable_hint(residue))
        if not available and self.d_form_radio.isChecked():
            self.l_form_radio.setChecked(True)
        if self.d_form_radio.isChecked():
            if self._selected_form != "D":
                self._manual_code = self.code_edit.text().strip()
            self._selected_form = "D"
            self.code_edit.setText(code)
            self.code_edit.setReadOnly(True)
            return
        if self._selected_form == "D":
            self._selected_form = "L"
            self.code_edit.setText(self._manual_code)
        self.code_edit.setReadOnly(False)

    def selected_form(self) -> str:
        """The form the dialog will submit: ``"L"`` or ``"D"``."""
        if self._forms_offered and self.d_form_radio.isChecked():
            return "D"
        return "L"

    def select_form(self, form: str) -> bool:
        """Select ``"L"`` or ``"D"``; ``False`` when it is not available."""
        word = str(form).strip().upper()
        if not self._forms_offered or word not in ("L", "D"):
            return False
        if word == "D" and not self.d_form_radio.isEnabled():
            return False
        (self.d_form_radio if word == "D" else self.l_form_radio).setChecked(True)
        self._refresh_form()
        return True

    def resolved_code(self) -> str:
        """The CCD code the D-form resolves to (empty for an L-form)."""
        if self.selected_form() != "D":
            return ""
        return self.code_edit.text().strip()

    def _collect(self):
        return (
            self.selected_form(),
            self.code_edit.text().strip(),
            self.position_spin.value(),
        )


class AlignmentFormDialog(_FormDialog):
    """Choose one alignment mode and, when it needs one, its single source.

    ``modes`` is a sequence of ``(registry label key, service mode word)``
    pairs supplied by the page — the family's legal modes, never a list this
    dialog invented. Source controls appear only for modes that carry a
    source, exactly as the service defines them (``automatic`` and ``free``
    take no source and refuse one).

    ``both`` is the one mode with two sides: the unpaired source and, when it
    differs, an independent paired source. The paired controls appear only for
    that mode, and their default is to reuse the unpaired source — the
    service's documented single-source behaviour — so a user who wants one
    file for both sides changes nothing.
    """

    def __init__(
        self,
        parent,
        title,
        accept_text,
        apply,
        modes,
        mode="",
        source_kind="",
        source_text="",
        hint="",
        paired_kind="",
        paired_text="",
    ) -> None:
        super().__init__(parent, title, accept_text, apply)
        self.mode_combo = QComboBox()
        self._mode_words = []
        selected = 0
        for index, (label_key, word) in enumerate(modes):
            self.mode_combo.addItem(_text(label_key))
            self._mode_words.append(word)
            if word == mode:
                selected = index
        self.mode_combo.setCurrentIndex(selected)
        self._form.addRow(_text("gui.alignment_mode"), self.mode_combo)

        self.source_group = QButtonGroup(self)
        self.source_radios = []
        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        for label_key, kind in _SOURCE_OPTIONS:
            radio = QRadioButton(_text(label_key))
            self.source_group.addButton(radio)
            self.source_radios.append((kind, radio))
            source_layout.addWidget(radio)
        self._form.addRow(_text("gui.alignment_source"), source_row)
        self.source_row = source_row

        self.inline_edit = QPlainTextEdit(source_text if source_kind == "inline" else "")
        self.inline_edit.setFont(fixed_font())
        self.inline_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.inline_edit.setMinimumHeight(120)
        self._inline_label = QLabel(_text("gui.alignment_inline"))
        self._form.addRow(self._inline_label, self.inline_edit)

        self.path_edit = QLineEdit(source_text if source_kind == "file" else "")
        self.browse_button = QPushButton(_text("gui.alignment_browse"))
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(self.browse_button)
        self._path_label = QLabel(_text("gui.alignment_path"))
        self._form.addRow(self._path_label, path_row)
        self.path_row = path_row

        # The paired side's own controls (``both`` mode only). A radio group
        # of its own, so "reuse the unpaired source" is a real, visible
        # choice rather than an inferred one.
        self.paired_block = QWidget()
        paired_form = QFormLayout(self.paired_block)
        self._paired_form = paired_form
        paired_form.setContentsMargins(0, 0, 0, 0)
        self.paired_group = QButtonGroup(self)
        self.paired_radios = []
        paired_row = QWidget()
        paired_row_layout = QHBoxLayout(paired_row)
        paired_row_layout.setContentsMargins(0, 0, 0, 0)
        for label_key, kind in _PAIRED_SOURCE_OPTIONS:
            radio = QRadioButton(_text(label_key))
            self.paired_group.addButton(radio)
            self.paired_radios.append((kind, radio))
            paired_row_layout.addWidget(radio)
        paired_form.addRow(_text("gui.alignment_paired_source"), paired_row)
        self.paired_row = paired_row

        self.paired_inline_edit = QPlainTextEdit(
            paired_text if paired_kind == "inline" else ""
        )
        self.paired_inline_edit.setFont(fixed_font())
        self.paired_inline_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.paired_inline_edit.setMinimumHeight(110)
        self._paired_inline_label = QLabel(_text("gui.alignment_paired_inline"))
        paired_form.addRow(self._paired_inline_label, self.paired_inline_edit)

        self.paired_path_edit = QLineEdit(
            paired_text if paired_kind == "file" else ""
        )
        self.paired_browse_button = QPushButton(_text("gui.alignment_browse"))
        paired_path_row = QWidget()
        paired_path_layout = QHBoxLayout(paired_path_row)
        paired_path_layout.setContentsMargins(0, 0, 0, 0)
        paired_path_layout.addWidget(self.paired_path_edit, 1)
        paired_path_layout.addWidget(self.paired_browse_button)
        self._paired_path_label = QLabel(_text("gui.alignment_paired_path"))
        paired_form.addRow(self._paired_path_label, paired_path_row)
        self.paired_path_row = paired_path_row
        self._layout.addWidget(self.paired_block)

        self.hint_label = QLabel(hint or _text("gui.alignment_hint"))
        self.hint_label.setWordWrap(True)
        self.version_label = QLabel(
            _text("gui.alignment_path_version") % MSA_PATH_MIN_VERSION
        )
        self.version_label.setWordWrap(True)
        self._layout.addWidget(self.hint_label)
        self._layout.addWidget(self.version_label)
        self.finish_layout()

        default_kind = source_kind or "inline"
        for kind, radio in self.source_radios:
            radio.setChecked(kind == default_kind)
        default_paired_kind = paired_kind or "same"
        for kind, radio in self.paired_radios:
            radio.setChecked(kind == default_paired_kind)
        self.browse_button.clicked.connect(self.browse)
        self.paired_browse_button.clicked.connect(self.browse_paired)
        self.mode_combo.currentIndexChanged.connect(self._refresh_source_controls)
        self.source_group.buttonClicked.connect(
            lambda _button: self._refresh_source_controls()
        )
        self.paired_group.buttonClicked.connect(
            lambda _button: self._refresh_source_controls()
        )
        self._refresh_source_controls()

    def browse(self) -> None:
        """Put a chosen alignment file in the path field (nothing is read)."""
        path, _selected = QFileDialog.getOpenFileName(
            self, _text("gui.alignment_file_dialog"), "", _text("gui.file_filter")
        )
        if path:
            self.path_edit.setText(path)

    def current_mode(self) -> str:
        """The service's mode word for the current selection."""
        return self._mode_words[self.mode_combo.currentIndex()]

    def select_mode(self, word: str) -> bool:
        """Select a mode by the service's own word; ``False`` if unknown."""
        if word not in self._mode_words:
            return False
        self.mode_combo.setCurrentIndex(self._mode_words.index(word))
        return True

    def browse_paired(self) -> None:
        """Put a chosen paired-side alignment file in its path field."""
        path, _selected = QFileDialog.getOpenFileName(
            self, _text("gui.alignment_file_dialog"), "", _text("gui.file_filter")
        )
        if path:
            self.paired_path_edit.setText(path)

    def current_source_kind(self) -> str:
        for kind, radio in self.source_radios:
            if radio.isChecked():
                return kind
        return "inline"

    def current_paired_kind(self) -> str:
        """The paired side's chosen route: ``same``, ``inline`` or ``file``."""
        for kind, radio in self.paired_radios:
            if radio.isChecked():
                return kind
        return "same"

    def _source_needed(self) -> bool:
        return self.current_mode() not in ("automatic", "free")

    def _paired_needed(self) -> bool:
        return self.current_mode() == "both"

    def _refresh_source_controls(self) -> None:
        """Show only the controls the chosen mode actually uses."""
        needed = self._source_needed()
        for _kind, radio in self.source_radios:
            radio.setEnabled(needed)
        show_inline = needed and self.current_source_kind() == "inline"
        show_path = needed and self.current_source_kind() == "file"
        self._form.setRowVisible(self._inline_label, show_inline)
        self._form.setRowVisible(self._path_label, show_path)
        self.browse_button.setEnabled(show_path)
        self.version_label.setVisible(show_path)
        # The paired side exists only for ``both``, and within it only the
        # chosen route's control is shown.
        paired_needed = self._paired_needed()
        self.paired_block.setVisible(paired_needed)
        for _kind, radio in self.paired_radios:
            radio.setEnabled(paired_needed)
        paired_kind = self.current_paired_kind()
        self._paired_form.setRowVisible(
            self._paired_inline_label, paired_needed and paired_kind == "inline"
        )
        self._paired_form.setRowVisible(
            self._paired_path_label, paired_needed and paired_kind == "file"
        )
        self.paired_browse_button.setEnabled(paired_needed and paired_kind == "file")
        # The mode explains what it will do, in the console's own words.
        self.hint_label.setText(_text(self._hint_key()))

    def _hint_key(self) -> str:
        mode = self.current_mode()
        if mode == "automatic":
            return "gui.alignment_hint_automatic"
        if mode == "free":
            return "gui.alignment_hint_free"
        return "gui.alignment_hint_source"

    def _collect(self):
        """``(mode, kind, text, paired_kind, paired_text)``.

        The paired pair is ``("", "")`` unless the mode is ``both`` and a
        paired source of its own was chosen; ``"same"`` means "reuse the
        unpaired source", which the service does when no paired side is sent.
        """
        mode = self.current_mode()
        if not self._source_needed():
            return (mode, "", "", "", "")
        kind = self.current_source_kind()
        text = (
            self.path_edit.text().strip()
            if kind == "file"
            else self.inline_edit.toPlainText()
        )
        if not self._paired_needed():
            return (mode, kind, text, "", "")
        paired_kind = self.current_paired_kind()
        if paired_kind == "same":
            return (mode, kind, text, "", "")
        paired_text = (
            self.paired_path_edit.text().strip()
            if paired_kind == "file"
            else self.paired_inline_edit.toPlainText()
        )
        return (mode, kind, text, paired_kind, paired_text)


class _Accepted:
    """The trivial success a text-only dialog's ``apply`` returns.

    ``_FormDialog.accept`` closes only when the apply outcome is ``ok``; a
    dialog that merely collects text has nothing to refuse, so it returns
    this instead of a service result.
    """

    ok = True


class InlineTextDialog(_FormDialog):
    """A multiline mmCIF editor, used to author one inline template.

    Inline templates are a first-class AF3 representation (``mmcif``), not a
    degraded file: a user who imported one can edit it, and a user with no
    file can paste one. The dialog only collects text — the service validates
    and stores it.
    """

    def __init__(self, parent, title, accept_text, apply, content="") -> None:
        super().__init__(parent, title, accept_text, apply)
        self.text_edit = QPlainTextEdit(content)
        self.text_edit.setFont(fixed_font())
        self.text_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.text_edit.setMinimumHeight(240)
        self._form.addRow(_text("gui.templates_inline_content"), self.text_edit)
        self.finish_layout()

    def _collect(self):
        return (self.text_edit.toPlainText(),)


class TemplateEditorDialog(_FormDialog):
    """The protein template states: search allowed, none, or a reference list.

    The three routes are the console's own (``menu.templates_search`` /
    ``menu.templates_none`` / ``menu.templates_list``). In list mode each row
    is one reference: either an mmCIF file chosen with a file picker or inline
    mmCIF text authored in :class:`InlineTextDialog`, plus its optional
    0-based index pairs in the form the console asks for (``query:template``,
    comma separated). A row's own kind is preserved — an imported inline
    template stays inline when the dialog is accepted.
    """

    def __init__(
        self, parent, title, accept_text, apply, mode="search", entries=(), hint=""
    ) -> None:
        super().__init__(parent, title, accept_text, apply)
        self.route_group = QButtonGroup(self)
        self.route_radios = []
        route_row = QWidget()
        route_layout = QVBoxLayout(route_row)
        route_layout.setContentsMargins(0, 0, 0, 0)
        for label_key, route in _TEMPLATE_ROUTES:
            radio = QRadioButton(_text(label_key))
            self.route_group.addButton(radio)
            self.route_radios.append((route, radio))
            route_layout.addWidget(radio)
            if route == mode:
                radio.setChecked(True)
        self._form.addRow(_text("gui.templates_mode"), route_row)
        self.route_row = route_row

        self.pairs_note = QLabel(_text("gui.templates_pairs_note"))
        self.pairs_note.setWordWrap(True)
        self._form.addRow("", self.pairs_note)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(
            [_text("gui.templates_col_file"), _text("gui.templates_col_pairs")]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(140)
        for entry in entries:
            self._append_row(*entry)
        self.add_file_button = QPushButton(_text("gui.templates_add_file"))
        self.add_inline_button = QPushButton(_text("gui.templates_add_inline"))
        self.edit_source_button = QPushButton(_text("gui.templates_edit_source"))
        self.remove_file_button = QPushButton(_text("gui.templates_remove_file"))
        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addWidget(self.add_file_button)
        buttons_layout.addWidget(self.add_inline_button)
        buttons_layout.addWidget(self.edit_source_button)
        buttons_layout.addWidget(self.remove_file_button)
        buttons_layout.addStretch(1)
        self.buttons_row = buttons_row
        self._form.addRow(self.table)
        self._form.addRow(buttons_row)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            self._layout.addWidget(hint_label)
        self.finish_layout()

        self.add_file_button.clicked.connect(self.add_file)
        self.add_inline_button.clicked.connect(self.add_inline)
        self.edit_source_button.clicked.connect(self.edit_selected_source)
        self.remove_file_button.clicked.connect(self.remove_selected)
        self.route_group.buttonClicked.connect(lambda _button: self._refresh_controls())
        self._refresh_controls()

    #: Where a row keeps its source kind and, for inline rows, its text. Kept
    #: on the row's own item so a row removal takes the content with it.
    _KIND_ROLE = Qt.UserRole
    _TEXT_ROLE = Qt.UserRole + 1

    def _append_row(self, kind="file", value="", pairs="") -> None:
        """Append one reference row: ``kind`` is ``file`` or ``inline``."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        inline = kind == "inline"
        label = (
            _text("gui.templates_inline_row") % (len(value.splitlines()) or 1)
            if inline
            else value
        )
        item = QTableWidgetItem(label)
        item.setData(self._KIND_ROLE, "inline" if inline else "file")
        if inline:
            item.setData(self._TEXT_ROLE, value)
        # A path is never typed: it comes from the file picker, so the cell
        # is read-only while the pairs cell stays editable in place.
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, item)
        self.table.setItem(row, 1, QTableWidgetItem(pairs))

    def add_file(self) -> None:
        """Add a reference row for a file the user picks."""
        path, _selected = QFileDialog.getOpenFileName(
            self,
            _text("gui.templates_file_dialog"),
            "",
            _text("gui.templates_file_filter"),
        )
        if path:
            self._append_row("file", path, "")

    def add_inline(self, content=None) -> None:
        """Add a reference row holding pasted mmCIF text.

        ``content`` is supplied by a test; a real click opens the editor and
        stores whatever it returns. Cancelling adds nothing.
        """
        if content is None:
            content = self._ask_inline_text("")
            if content is None:
                return
        if not content.strip():
            return
        self._append_row("inline", content, "")

    def edit_selected_source(self) -> bool:
        """Re-open the editor for the selected inline row (no-op for a file)."""
        row = self._selected_row()
        if row is None:
            return False
        item = self.table.item(row, 0)
        if item is None or item.data(self._KIND_ROLE) != "inline":
            return False
        content = self._ask_inline_text(item.data(self._TEXT_ROLE) or "")
        if content is None or not content.strip():
            return False
        item.setData(self._TEXT_ROLE, content)
        item.setText(
            _text("gui.templates_inline_row") % (len(content.splitlines()) or 1)
        )
        return True

    def _ask_inline_text(self, content):
        """The editor's answer, or ``None`` when it was cancelled."""
        dialog = InlineTextDialog(
            self,
            title=_text("gui.templates_inline_dialog"),
            accept_text=_text("gui.form_save"),
            apply=lambda text: _Accepted(),
            content=content,
        )
        if dialog.exec() != InlineTextDialog.Accepted:
            return None
        return dialog.text_edit.toPlainText()

    def _selected_row(self):
        rows = {index.row() for index in self.table.selectedIndexes()}
        if rows:
            return min(rows)
        return None

    def remove_selected(self) -> None:
        """Remove the selected rows (the last one when nothing is selected)."""
        rows = sorted(
            {index.row() for index in self.table.selectedIndexes()}, reverse=True
        )
        if not rows and self.table.rowCount():
            rows = [self.table.rowCount() - 1]
        for row in rows:
            self.table.removeRow(row)

    def current_route(self) -> str:
        for route, radio in self.route_radios:
            if radio.isChecked():
                return route
        return "search"

    def select_route(self, route: str) -> bool:
        """Choose one template route; ``False`` when it is not a route."""
        for candidate, radio in self.route_radios:
            if candidate == route:
                radio.setChecked(True)
                self._refresh_controls()
                return True
        return False

    def _refresh_controls(self) -> None:
        listed = self.current_route() == "list"
        for row_widget in (self.pairs_note, self.table, self.buttons_row):
            row_widget.setVisible(listed)
        self.remove_file_button.setEnabled(self.table.rowCount() > 0)

    def entries(self):
        """The rows as ``(kind, value, pairs_text)`` triples, in display order.

        ``kind`` is ``file`` (``value`` is the path) or ``inline`` (``value``
        is the mmCIF text). The kind travels with the row, so accepting the
        dialog never converts an inline template into a path reference.
        """
        rows = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            pairs = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            if item is None:
                rows.append(("file", "", pairs))
                continue
            kind = item.data(self._KIND_ROLE) or "file"
            value = (
                item.data(self._TEXT_ROLE) or ""
                if kind == "inline"
                else item.text()
            )
            rows.append((kind, value, pairs))
        return tuple(rows)

    def _collect(self):
        route = self.current_route()
        if route != "list":
            return (route, ())
        return (route, self.entries())


class BondFormDialog(_FormDialog):
    """One covalent bond: two endpoints, each entity/residue/atom.

    ``choices`` is the page's own ``(entity key, display label)`` list built
    from the current records, so the user picks an entity by a real
    identifier and never types an internal key.
    """

    def __init__(
        self,
        parent,
        title,
        accept_text,
        apply,
        choices,
        left=None,
        right=None,
        hint="",
    ) -> None:
        super().__init__(parent, title, accept_text, apply)
        self.left_key, self.left_residue, self.left_atom = self._endpoint(
            _text("gui.bond_endpoint_a"), choices, left
        )
        self.right_key, self.right_residue, self.right_atom = self._endpoint(
            _text("gui.bond_endpoint_b"), choices, right
        )
        if hint:
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            self._layout.addWidget(hint_label)
        self.finish_layout()

    def _endpoint(self, label, choices, preselected):
        """One endpoint's three controls, added to the form."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        key_combo = QComboBox()
        for key, display in choices:
            key_combo.addItem(display, key)
        if preselected is not None:
            index = key_combo.findData(preselected)
            if index >= 0:
                key_combo.setCurrentIndex(index)
        residue_spin = QSpinBox()
        residue_spin.setRange(1, MAX_POSITION)
        atom_edit = QLineEdit()
        atom_edit.setPlaceholderText(_text("gui.bond_atom_placeholder"))
        layout.addWidget(key_combo, 2)
        layout.addWidget(residue_spin)
        layout.addWidget(atom_edit, 1)
        self._form.addRow(label, row)
        self._form.addRow("", QLabel(_text("gui.bond_columns_note")))
        return key_combo, residue_spin, atom_edit

    def _endpoint_values(self, key_combo, residue_spin, atom_edit):
        return (
            key_combo.currentData() or "",
            int(residue_spin.value()),
            atom_edit.text().strip(),
        )

    def _collect(self):
        left = self._endpoint_values(self.left_key, self.left_residue, self.left_atom)
        right = self._endpoint_values(
            self.right_key, self.right_residue, self.right_atom
        )
        return left + right
