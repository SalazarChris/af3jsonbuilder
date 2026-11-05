"""The file-generation workflow's dialogs: kind, file, folder, review, result.

Five dumb steps, in the order the workflow asks them:

- :func:`choose_batch_kind` — what the file holds (protein, DNA, RNA, SMILES
  ligands, CCD-coded ligands), the one question content cannot answer;
- :func:`choose_batch_file` — the native open dialog for the input list, with
  the filter of the kind already chosen;
- :func:`choose_output_folder` — the native folder dialog for the outputs;
- :func:`confirm_batch_preview` — one box listing what was read, that kind, and
  where it will be written, before anything is planned or written;
- :func:`report_batch_run` — the outcome: the files that were written, or the
  service's own refusal.

Like every other dialog here they render wording and return an answer. None of
them reads a molecule, calls a service, decides a file name or writes anything:
the page owns that sequence, and the service owns every decision behind it.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox

from configbuilder.app.results import batch_counts
from configbuilder.ui.present.strings import (
    batch_preview_note,
    batch_summary,
    text as _text,
)

__all__ = [
    "choose_batch_file",
    "choose_batch_kind",
    "choose_batch_target",
    "choose_output_folder",
    "confirm_batch_preview",
    "report_batch_run",
]

#: How many entries the review box lists before it summarises the rest. The
#: count is always exact; only the enumeration is capped, so a file of two
#: hundred molecules does not open a wall of text.
_PREVIEW_ROWS = 12

#: The kinds the dialog offers, with the registry key of each label. The
#: application's own tuple is ``batch_variants.INPUT_KINDS``; a test compares
#: the two, so this list cannot offer a kind no service builds.
KIND_LABELS = (
    ("menu.file_kind_protein", "protein-sequence"),
    ("menu.file_kind_dna", "dna-sequence"),
    ("menu.file_kind_rna", "rna-sequence"),
    ("menu.file_kind_ligand_smiles", "ligand-smiles"),
    ("menu.file_kind_ligand_ccd", "ligand-ccd"),
)


def choose_batch_kind(parent) -> str:
    """Ask what the input file holds; ``""`` means the user cancelled.

    The question is asked **before** the file, because the answer is what
    makes the file readable: a ``.txt`` of ``MVT``/``TEST`` lines is a protein
    batch only because someone said so, and inferring it from the text would
    silently reinterpret a user's data. One button per kind, so the choice is
    one click and the labels are the shipped ones.
    """
    box = QMessageBox(parent)
    box.setWindowTitle(_text("gui.batch_kind_title"))
    box.setText(_text("gui.batch_kind_prompt"))
    buttons = {}
    for label_key, token in KIND_LABELS:
        buttons[box.addButton(_text(label_key), QMessageBox.AcceptRole)] = token
    cancel = box.addButton(_text("gui.form_cancel"), QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    return buttons.get(clicked, "")


def choose_batch_target(parent, rows, kind: str = ""):
    """Ask whether each entry adds an entity or replaces one; ``None`` cancels.

    Returns ``("add", "")`` or ``("replace", <record key>)``. ``rows`` are the
    service's own ``entity_table`` rows filtered to the kind's family, so this
    dialog cannot propose a target the service would refuse. **Add** is listed
    first and preselected: growing the job is what the workflow originally
    meant, and replacing is the deliberate second choice.
    """
    if not rows:
        # Nothing of this family to replace: one answer would be a question.
        return ("add", "")
    box = QMessageBox(parent)
    box.setWindowTitle(_text("gui.batch_target_title"))
    box.setText(_text("gui.batch_target_prompt"))
    buttons = {}
    add = box.addButton(_text("gui.batch_target_add"), QMessageBox.AcceptRole)
    buttons[add] = ""
    for row in rows:
        label = _text("gui.batch_target_row") % (row.key, row.summary)
        buttons[box.addButton(label, QMessageBox.AcceptRole)] = row.key
    cancel = box.addButton(_text("gui.form_cancel"), QMessageBox.RejectRole)
    box.setDefaultButton(add)
    box.exec()
    clicked = box.clickedButton()
    if clicked is None or clicked is cancel or clicked not in buttons:
        return None
    key = buttons[clicked]
    return ("replace", key) if key else ("add", "")


def choose_batch_file(parent, kind: str = "ligand-smiles", start: str = "") -> str:
    """Ask for the input file of ``kind``; ``""`` means the user cancelled."""
    filter_key = (
        "gui.batch_file_filter_sequences"
        if kind.endswith("-sequence")
        else "gui.batch_file_filter_ligands"
    )
    path, _selected_filter = QFileDialog.getOpenFileName(
        parent,
        _text("gui.batch_file_dialog"),
        start,
        _text(filter_key),
    )
    return path or ""


def choose_output_folder(parent, start: str = "") -> str:
    """Ask for the output folder; ``""`` means the user cancelled."""
    return QFileDialog.getExistingDirectory(
        parent, _text("gui.batch_folder_dialog"), start
    ) or ""


def confirm_batch_preview(
    parent, preview, output_root: str, kind: str = "", replaced: str = ""
) -> bool:
    """Show what was read, that kind, and where it goes; True to continue.

    Cancel is the default button: the safe answer is the one a stray Return
    picks, and nothing has been planned or written at this point.
    """
    entries = list(preview.entries)
    shown = entries[:_PREVIEW_ROWS]
    lines = [_text("gui.batch_preview_entries") % len(entries)]
    if kind:
        lines.append(_text("gui.batch_preview_kind") % _kind_label(kind))
    lines.extend([""] + [_text("gui.batch_preview_row") % entry for entry in shown])
    if len(entries) > len(shown):
        lines.append(_text("gui.batch_preview_more") % (len(entries) - len(shown)))
    lines.extend(
        [
            "",
            _text("gui.batch_preview_destination") % output_root,
            _text("gui.batch_preview_files") % len(entries),
            # The console's own note, so the two front ends explain the
            # entries, the base and the overwrite policy in one voice (and
            # say what a DNA entry becomes in the same words).
            batch_preview_note(kind, replaced) if kind else "",
        ]
    )
    box = QMessageBox(parent)
    box.setWindowTitle(_text("gui.batch_preview_title"))
    box.setText("\n".join(lines))
    proceed = box.addButton(
        _text("gui.batch_preview_accept"), QMessageBox.AcceptRole
    )
    cancel = box.addButton(_text("gui.form_cancel"), QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is proceed


def _kind_label(kind: str) -> str:
    """The shipped label of ``kind`` (the kind table's own wording)."""
    for label_key, token in KIND_LABELS:
        if token == kind:
            return _text(label_key)
    return kind


def report_batch_run(parent, output) -> None:
    """Report the run: files written, or the refusal's own message.

    ``output`` is the service's ``LigandBatchOutput`` — the outcome type every
    batch uses — so this function only lays out what it says: a success message
    is never shown for a batch that wrote nothing, and the refusal names the
    file or finding that stopped it.
    """
    plan = output.plan
    lines = []
    if plan is not None and not plan.ok:
        lines.append(_text("gui.batch_result_refused") % (plan.message or ""))
        lines.extend(plan.conflicts)
        for finding in plan.findings:
            lines.append("  - %s" % finding.user_message)
    elif output.written:
        # Roles, not rows: configurations and the manifest are counted
        # apart here exactly as the console counts them, and copied assets
        # are named rather than folded into the file total.
        lines.append(batch_summary(batch_counts(output)))
        lines.append("")
        lines.append(_text("gui.batch_result_written") % len(output.written))
        lines.extend(output.written)
        if output.errors:
            lines.append("")
            lines.append(_text("gui.batch_result_errors"))
            lines.extend(output.errors)
        skipped = len(output.skipped)
        if skipped > 0:
            lines.append("")
            lines.append(_text("gui.batch_result_skipped") % skipped)
    else:
        lines.append(_text("gui.batch_result_nothing"))
    box = QMessageBox(parent)
    box.setWindowTitle(_text("gui.batch_result_title"))
    box.setText("\n".join(lines))
    box.exec()
