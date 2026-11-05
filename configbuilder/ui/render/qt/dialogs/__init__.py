"""Modal dialogs of the Qt front end (Stages 1-4).

Every dialog here renders wording and returns the user's answer: the import
preview renders a service result, the lifecycle dialogs (problem, discard,
overwrite, save chooser, removal confirmations) ask their one question, the
entity/advanced forms collect values for the page to submit, and the batch
input dialogs ask their kind and two paths and report the run. None performs a
service call or a file access of its own.
"""

from __future__ import annotations

from configbuilder.ui.render.qt.dialogs.advanced_forms import (
    AlignmentFormDialog,
    BondFormDialog,
    ModificationFormDialog,
    TemplateEditorDialog,
)
from configbuilder.ui.render.qt.dialogs.entity_forms import (
    LigandFormDialog,
    SequenceFormDialog,
)
from configbuilder.ui.render.qt.dialogs.import_preview import (
    ImportPreviewDialog,
    show_failure,
)
from configbuilder.ui.render.qt.dialogs.batch_input import (
    KIND_LABELS,
    choose_batch_file,
    choose_batch_kind,
    choose_batch_target,
    choose_output_folder,
    confirm_batch_preview,
    report_batch_run,
)
from configbuilder.ui.render.qt.dialogs.messages import (
    ask_save_path,
    confirm_bond_removal,
    confirm_discard,
    confirm_entity_delete,
    confirm_modification_removal,
    confirm_overwrite,
    show_problem,
)

__all__ = [
    "AlignmentFormDialog",
    "BondFormDialog",
    "ImportPreviewDialog",
    "LigandFormDialog",
    "ModificationFormDialog",
    "SequenceFormDialog",
    "TemplateEditorDialog",
    "KIND_LABELS",
    "ask_save_path",
    "choose_batch_file",
    "choose_batch_kind",
    "choose_batch_target",
    "choose_output_folder",
    "confirm_batch_preview",
    "confirm_bond_removal",
    "confirm_discard",
    "confirm_entity_delete",
    "confirm_modification_removal",
    "confirm_overwrite",
    "report_batch_run",
    "show_failure",
    "show_problem",
]
