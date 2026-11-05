"""The Stage 2 modal dialogs: problem, discard, overwrite and the save chooser.

Like the import dialog, these are deliberately **dumb**: they render wording
and return the user's answer. They never call a service, never touch a file
and never decide anything — the window owns the sequence, so the only way a
job is saved is the window calling ``GenerationService`` after these return.

Each function is assigned to a window attribute at construction time
(``problem_reporter``, ``discard_confirmer``, ``overwrite_confirmer``,
``save_path_chooser``), which is how the offscreen tests replace a modal that
nobody could click.

The overwrite question reuses the console's own wording
(``menu.overwrite_confirm`` / ``menu.overwrite_yes`` / ``menu.overwrite_no``),
so both front ends ask the same question the same way. The save chooser asks
Qt for a file name with ``DontConfirmOverwrite``: the explicit confirmation
below is the one overwrite decision this window makes, so the platform dialog
does not ask a second time.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox

from configbuilder.ui.present.strings import text as _text

__all__ = [
    "ask_save_path",
    "confirm_bond_removal",
    "confirm_discard",
    "confirm_entity_delete",
    "confirm_modification_removal",
    "confirm_overwrite",
    "show_problem",
]


def show_problem(parent, message: str) -> None:
    """Report a refused action in the user's terms, never a traceback."""
    QMessageBox.critical(parent, _text("gui.problem_title"), message)


def confirm_discard(parent) -> bool:
    """Ask before throwing away unsaved changes. Cancel is the default.

    Returns True only when the user explicitly chose to discard; closing the
    box keeps the job (the safe answer is the one a stray Return picks).
    """
    box = QMessageBox(parent)
    box.setWindowTitle(_text("gui.discard_title"))
    box.setText(_text("gui.discard_question"))
    discard = box.addButton(_text("gui.discard_accept"), QMessageBox.AcceptRole)
    keep = box.addButton(_text("gui.discard_cancel"), QMessageBox.RejectRole)
    box.setDefaultButton(keep)
    box.exec()
    return box.clickedButton() is discard


def confirm_overwrite(parent, path: str) -> bool:
    """Ask before replacing an existing file, with the console's own wording."""
    box = QMessageBox(parent)
    box.setWindowTitle(_text("gui.overwrite_title"))
    box.setText(_text("menu.overwrite_confirm") % path)
    replace = box.addButton(_text("menu.overwrite_yes"), QMessageBox.YesRole)
    cancel = box.addButton(_text("menu.overwrite_no"), QMessageBox.NoRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is replace


def confirm_entity_delete(parent, message: str) -> bool:
    """Ask before removing an entity. Cancel is the default button.

    ``message`` is the page's own sentence (it names the identifiers and,
    for a DNA duplex or a multi-copy ligand, what else goes with the
    record); this function only asks and returns the answer.
    """
    box = QMessageBox(parent)
    box.setWindowTitle(_text("gui.delete_title"))
    box.setText(message)
    delete = box.addButton(_text("gui.delete_accept"), QMessageBox.DestructiveRole)
    cancel = box.addButton(_text("gui.form_cancel"), QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is delete


def _confirm_removal(parent, title: str, message: str) -> bool:
    """Ask a destructive question with Cancel as the default button.

    One shape for every removal (a modification, a covalent bond): the page
    supplies the sentence, this function only asks and answers.
    """
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    remove = box.addButton(_text("gui.delete_accept"), QMessageBox.DestructiveRole)
    cancel = box.addButton(_text("gui.form_cancel"), QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is remove


def confirm_modification_removal(parent, message: str) -> bool:
    """Ask before removing a post-translational modification."""
    return _confirm_removal(parent, _text("gui.mod_delete_title"), message)


def confirm_bond_removal(parent, message: str) -> bool:
    """Ask before removing a covalent bond."""
    return _confirm_removal(parent, _text("gui.bond_delete_title"), message)


def ask_save_path(parent, default: str):
    """The native save dialog. Returns ``(path, accepted)``.

    ``DontConfirmOverwrite`` suppresses the platform's own replace prompt:
    the window asks explicitly (``confirm_overwrite``), so the user answers
    the question once.
    """
    path, _selected_filter = QFileDialog.getSaveFileName(
        parent,
        _text("gui.save_dialog_title"),
        default,
        _text("gui.file_filter"),
        options=QFileDialog.DontConfirmOverwrite,
    )
    return path, bool(path)
