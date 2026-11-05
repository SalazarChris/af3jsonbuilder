"""The import preview dialog, and the import-failure message.

The dialog is deliberately **dumb**: it renders the ``ImportPreview`` the
service already produced (its summary rows and its notes) and returns
accepted or rejected. It never calls a service and never touches a file, so
the only way an import is installed is the window calling
``ProjectService.import_json_commit`` after the user pressed Import.

Every sentence shown here is registered wording — the same wording the
console's own import screen uses — so the two front ends describe a file the
same way.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from configbuilder.ui.present.strings import text as _text

__all__ = ["ImportPreviewDialog", "show_failure"]


def _row(form, label_key, text) -> None:
    label = QLabel(text)
    label.setWordWrap(True)
    form.addRow(_text(label_key), label)


class ImportPreviewDialog(QDialog):
    """Show what a file contains, then ask for an explicit Import."""

    def __init__(self, parent, path, preview) -> None:
        super().__init__(parent)
        self.setWindowTitle(_text("gui.import_title"))
        self.setMinimumWidth(560)
        summary = preview.summary or {}
        layout = QVBoxLayout(self)

        summary_group = QGroupBox(_text("gui.import_summary_title"))
        form = QFormLayout(summary_group)
        _row(form, "menu.import_file_line", path)
        _row(form, "menu.summary_name", str(summary.get("job_name", "")))
        seeds = summary.get("seed_values") or ()
        _row(form, "menu.summary_seeds", ", ".join(str(value) for value in seeds))
        _row(form, "menu.import_entities", str(summary.get("entity_count", 0)))
        counts = summary.get("family_counts") or {}
        for family_key, family in (
            ("menu.summary_protein", "protein"),
            ("menu.summary_dna", "dna"),
            ("menu.summary_rna", "rna"),
            ("menu.summary_ligand", "ligand"),
        ):
            _row(form, family_key, str(counts.get(family, 0)))
        record_ids = summary.get("record_ids") or ()
        _row(form, "gui.import_ids", ", ".join(str(value) for value in record_ids))
        layout.addWidget(summary_group)

        if preview.notes:
            notes_group = QGroupBox(_text("menu.import_notes"))
            notes_layout = QVBoxLayout(notes_group)
            for note in preview.notes:
                note_label = QLabel(_text("menu.import_note_line") % note.detail)
                note_label.setWordWrap(True)
                notes_layout.addWidget(note_label)
            layout.addWidget(notes_group)

        untouched = QLabel(_text("menu.import_untouched"))
        untouched.setWordWrap(True)
        layout.addWidget(untouched)

        question = QLabel(_text("menu.import_confirm"))
        question.setWordWrap(True)
        layout.addWidget(question)

        buttons = QDialogButtonBox()
        buttons.addButton(_text("gui.import_accept"), QDialogButtonBox.AcceptRole)
        buttons.addButton(_text("menu.import_no"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def show_failure(parent, message: str) -> None:
    """Report a refused import/read in the user's terms, never a traceback."""
    QMessageBox.critical(
        parent,
        _text("menu.import_failed"),
        _text("menu.import_reason") % message,
    )
