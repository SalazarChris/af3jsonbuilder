"""Entity forms: add/edit for sequence chains and for ligands.

Both dialogs are deliberately **dumb**, exactly like the import dialog: they
collect text and choices and hand them to an ``apply`` callable the page
supplied. They never call a service, never build a record, allocate an
identifier or compute anything biological. A refusal comes back as the
service's own result object, is shown on the dialog's message line, and
leaves the dialog open so the value can be corrected — no traceback, no
silent discard.

The sequence form covers protein, RNA and DNA (the same three fields the
service accepts); the ligand form covers the mutually exclusive CCD/SMILES
representation, the copy count and the optional description. The warning
line is worded by the page (which knows the pinned JSON version) and is shown
only while a description is actually supplied; it explains, and never
upgrades or discards anything.

A DNA add also asks the one question the service cannot answer for the user:
whether the entered strand is half of a duplex (the default, matching every
existing caller) or a lone single strand. The choice is a *dialog control*
whose answer is passed straight to ``add_record(duplex=…)``; the complement
itself is still built by the service, never here.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.qt.models import fixed_font

__all__ = ["LigandFormDialog", "SequenceFormDialog"]

#: The most copies the ligand form offers. The service's own rule is only
#: "a whole number of at least 1" and the identifier progression runs far
#: past this; 99 is a deliberately conservative bound for a spin box, and
#: the service remains the authority on what is accepted.
MAX_LIGAND_COPIES = 99


class _ResultDialog(QDialog):
    """Shared behaviour: an error line, and Accept only on a successful apply."""

    def __init__(self, parent, title: str, accept_text: str, apply, warning: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self._apply = apply
        self._warning_text = warning or ""
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self._buttons = QDialogButtonBox()
        self.accept_button = self._buttons.addButton(accept_text, QDialogButtonBox.AcceptRole)
        self.cancel_button = self._buttons.addButton(
            _text("gui.form_cancel"), QDialogButtonBox.RejectRole
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self.warning_label = QLabel(self._warning_text)
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)

    def error_text(self) -> str:
        """The last refusal as displayed (empty when nothing was refused)."""
        return self.error_label.text()

    def warning_text(self) -> str:
        """The version explanation as displayed (empty when none applies).

        ``isVisibleTo`` rather than ``isVisible``: the latter is False for
        every child of a dialog that is not itself on screen, which would
        report "hidden" for a warning the user is looking at.
        """
        if not self.warning_label.isVisibleTo(self):
            return ""
        return self.warning_label.text()

    def _refresh_warning(self) -> None:
        """Show the version explanation only while a description is supplied."""
        self.warning_label.setVisible(bool(self._warning_text) and self._description_supplied())

    def _description_supplied(self) -> bool:
        raise NotImplementedError

    def _collect(self):
        """The apply arguments; subclasses decide the shape."""
        raise NotImplementedError

    def accept(self) -> None:
        """Submit through ``apply``; keep the dialog open on a refusal."""
        outcome = self._apply(*self._collect())
        if getattr(outcome, "ok", False):
            super().accept()
            return
        self.error_label.setText(getattr(outcome, "message", "") or "")
        self.error_label.setVisible(True)


class SequenceFormDialog(_ResultDialog):
    """Add or edit a protein, RNA or DNA chain."""

    def __init__(
        self,
        parent,
        title,
        accept_text,
        apply,
        sequence="",
        description="",
        hint="",
        warning="",
        duplex=None,
    ) -> None:
        """``duplex`` is ``None`` for a family that has no such choice
        (protein, RNA, and every edit form); for a DNA add it is the initial
        answer — ``True`` (duplex, the service default) or ``False``."""
        super().__init__(parent, title, accept_text, apply, warning)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.sequence_edit = QPlainTextEdit(sequence)
        self.sequence_edit.setFont(fixed_font())
        self.sequence_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.sequence_edit.setMinimumHeight(110)
        form.addRow(_text("gui.form_sequence"), self.sequence_edit)
        self.description_edit = QLineEdit(description)
        form.addRow(_text("gui.form_description"), self.description_edit)
        # The DNA-only duplex question. Two radios in one group, so exactly
        # one answer is ever collected; the service still builds the
        # complement when the duplex answer is chosen.
        self.paired_radio = None
        self.single_radio = None
        self.duplex_group = None
        if duplex is not None:
            self.paired_radio = QRadioButton(_text("gui.dna_duplex_pair"))
            self.single_radio = QRadioButton(_text("gui.dna_duplex_single"))
            self.duplex_group = QButtonGroup(self)
            self.duplex_group.addButton(self.paired_radio)
            self.duplex_group.addButton(self.single_radio)
            self.paired_radio.setChecked(bool(duplex))
            self.single_radio.setChecked(not duplex)
            form.addRow(_text("gui.dna_duplex_choice"), self.paired_radio)
            form.addRow("", self.single_radio)
        layout.addLayout(form)
        # The hint is kept as an attribute so a caller (and a test) can read
        # back the guidance the user is actually being given.
        self.hint_label = QLabel(hint)
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(self.hint_label)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.error_label)
        layout.addWidget(self._buttons)
        self.description_edit.textChanged.connect(self._refresh_warning)
        self._refresh_warning()

    def _description_supplied(self) -> bool:
        return bool(self.description_edit.text().strip())

    def duplex_selected(self) -> bool:
        """Whether the entered DNA strand should get its complement.

        Always ``True`` for a form without the control (protein, RNA, edit),
        which is the service's own default.
        """
        if self.duplex_group is None:
            return True
        return self.paired_radio.isChecked()

    def _collect(self):
        return (
            self.sequence_edit.toPlainText().strip(),
            self.description_edit.text(),
            self.duplex_selected(),
        )


class LigandFormDialog(_ResultDialog):
    """Add or edit a ligand: CCD code(s) XOR SMILES, copies, description.

    The two representation radios share one ``QButtonGroup``, so exactly one
    of them is ever checked — the service's mutually exclusive constraint is
    enforced by construction here, not by asking the user nicely.
    """

    def __init__(
        self,
        parent,
        title,
        accept_text,
        apply,
        kind="ccd",
        value="",
        copies=1,
        copies_editable=True,
        description="",
        hint="",
        warning="",
    ) -> None:
        super().__init__(parent, title, accept_text, apply, warning)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ccd_radio = QRadioButton(_text("gui.ligand_ccd_option"))
        self.smiles_radio = QRadioButton(_text("gui.ligand_smiles_option"))
        self.representation_group = QButtonGroup(self)
        self.representation_group.addButton(self.ccd_radio)
        self.representation_group.addButton(self.smiles_radio)
        self.ccd_radio.setChecked(kind != "smiles")
        self.smiles_radio.setChecked(kind == "smiles")
        form.addRow(_text("gui.ligand_kind"), self.ccd_radio)
        form.addRow("", self.smiles_radio)

        self.value_edit = QLineEdit(value)
        form.addRow(_text("gui.ligand_value"), self.value_edit)

        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, MAX_LIGAND_COPIES)
        self.copies_spin.setValue(max(1, min(int(copies), MAX_LIGAND_COPIES)))
        self.copies_spin.setEnabled(bool(copies_editable))
        form.addRow(_text("gui.ligand_copies"), self.copies_spin)

        self.description_edit = QLineEdit(description)
        form.addRow(_text("gui.form_description"), self.description_edit)
        layout.addLayout(form)

        self.hint_label = QLabel(hint)
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(self.hint_label)
        self.copies_note = QLabel(_text("gui.ligand_copies_fixed"))
        self.copies_note.setWordWrap(True)
        self.copies_note.setVisible(not copies_editable)
        layout.addWidget(self.copies_note)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.error_label)
        layout.addWidget(self._buttons)
        self.description_edit.textChanged.connect(self._refresh_warning)
        self._refresh_warning()

    def _description_supplied(self) -> bool:
        return bool(self.description_edit.text().strip())

    def _collect(self):
        kind = "smiles" if self.smiles_radio.isChecked() else "ccd"
        return (
            kind,
            self.value_edit.text(),
            self.copies_spin.value(),
            self.description_edit.text(),
        )
