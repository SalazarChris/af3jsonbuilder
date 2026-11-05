"""The front end's string registry (plan §18.7, §18.8; CHECKLIST 11a).

Every user-visible *chrome* string — action wording, fixed notices — is
data here, keyed, unique, and non-empty. Domain labels are NOT here: they
resolve through the model's traceability registry (plan §3), and finding
wording comes from the rule messages. The meta-test asserts the split: any
user-visible string in ``ui`` is either a registry label, a rule message, or
a member of this registry.

The registry is the meta-test's oracle in both directions: a string used by
``ui`` that is missing from here (and from the two domain sources) fails the
suite, and an entry nothing uses is dead vocabulary.
"""

from __future__ import annotations

__all__ = [
    "STRINGS",
    "batch_preview_note",
    "batch_summary",
    "blocking_verdict",
    "text",
]


STRINGS = {
    # The §16.3 action grammar's wording (keys 'n', 'p', 'e', 'd', 'v',
    # 's', 'q' are keystroke tokens, not display text).
    "action.next_step": "next step",
    "action.previous_step": "previous step",
    "action.edit_item": "edit an item",
    "action.delete_item": "delete an item",
    "action.validate_now": "validate now",
    "action.quit": "quit",
    # Fixed notices
    "sequence.empty": "(empty sequence)",
    # Fallback grouping context for findings whose rule emitted no locator.
    "finding.context.general": "General",
    # Console wording.
    "console.eof": "input stream closed",
    # The findings list's numbering template (shared by every screen).
    "jump.reference": "%d. %s — %s",

    # -- the builder's shared chrome -------------------------------------
    "menu.select_prompt": "Select: ",
    "menu.banner_title": "JSON CONFIGURATION BUILDER",
    "menu.back": "0. Back",
    "menu.exit": "0. Exit",
    "menu.invalid": "Not a valid choice: %r",
    "menu.interrupted": "Interrupted — returning to the menu.",
    "menu.choice_line": "%d. %s",
    "menu.applied": "Applied.",
    "menu.not_applied": "Not applied: %s",
    "menu.no_project": "No project is open.",
    "menu.need_whole_number": "%r is not a whole number — enter digits only (for example 12).",

    # -- the main menu: new job / open a JSON file ------------------------
    "menu.main_actions": (
        "1. New job\n"
        "2. Open a JSON file"
    ),
    "menu.ask_experiment": "Job name (blank generates one): ",
    "menu.job_created": "Started job %s.",

    # -- the job menu ----------------------------------------------------
    "menu.job_title": "JOB MENU",
    # The header block under the banner: the job's identity (name, seed set,
    # model target), its state (modifications, custom CCD, unsaved changes)
    # and the chains recorded so far — the work in progress, visible every
    # time the menu is drawn. One row template, so the colons line up.
    "menu.job_header_row": "%-13s : %s",
    "menu.job_header_label_name": "Name",
    "menu.job_header_label_seed": "Seed",
    "menu.job_header_label_model": "Model",
    "menu.job_header_label_modifications": "Modifications",
    "menu.job_header_label_ccd": "Custom CCD",
    "menu.job_header_label_changes": "Changes",
    "menu.job_header_model_value": "%s (JSON %s)",
    "menu.job_header_ccd_inline": "inline CIF, %d lines",
    # The one value the state rows share when there is nothing to report.
    "menu.job_header_none": "none",
    "menu.job_header_changes_unsaved": "unsaved",
    "menu.model_name": "AlphaFold 3",
    "menu.job_header_entities": "Entities (%d):",
    "menu.job_chain_line": "  Chain %s  %s",
    "menu.job_chain_mods": "  (modifications: %d)",
    "menu.job_actions": (
        "1. Edit job configurations\n"
        "2. Add entity\n"
        "3. Edit entity\n"
        "4. Custom CCD management\n"
        "5. Post-translational modification management\n"
        "6. Save and show summary\n"
        "7. Generate configurations from a file (sequences or ligands)\n"
        "8. Covalent bond management"
    ),
    "menu.job_back": "0. Return to main menu",
    "menu.leave_title": "Save before leaving?",
    "menu.leave_dirty": (
        "This job has changes that have not been saved to a JSON file."
    ),
    "menu.leave_save": "Save and leave",
    "menu.leave_discard": "Leave without saving",
    "menu.leave_cancel": "Cancel",

    # -- edit job configurations -----------------------------------------
    "menu.builder_title": "EDIT JOB CONFIGURATIONS",
    "menu.current_settings": "Current name: %s",
    "menu.current_version": "Version: %s",
    "menu.current_seeds": "Model seeds: %s",
    "menu.config_actions": (
        "1. Job name\n"
        "2. Model seeds\n"
        "3. JSON version"
    ),
    "menu.ask_name": "New name: ",
    "menu.ask_seeds": "Seeds (space- or comma-separated integers): ",
    "menu.seeds_method_title": "How do you want to set the model seeds?",
    "menu.seeds_method_menu": "Choose a method:",
    "menu.seeds_method_specific": "Enter specific seed values",
    "menu.seeds_method_generate": "Generate a number of seeds automatically",
    "menu.ask_seed_count": "How many model seeds do you want? ",
    "menu.ask_version": "JSON version to use: ",
    "menu.version_unsupported": "Unsupported JSON version — choose one of %s.",

    # -- the configuration-status view (defaults + what is still required) --
    "menu.status_title": "Configuration status",
    "menu.status_line": "  %-14s %s",
    "menu.status_name": "Name",
    "menu.status_seeds": "Model seeds",
    "menu.status_version": "JSON version",
    "menu.status_components": "Entities",
    "menu.status_modifications": "Modifications",
    "menu.status_msa": "MSA",
    "menu.status_templates": "Templates",
    "menu.status_other": "Other",
    "menu.status_ok": "OK",
    "menu.status_missing": "MISSING",
    "menu.status_invalid": "INVALID",
    "menu.status_absent": "-",
    "menu.status_automatic": "(automatic)",
    "menu.status_provided": "(you provided this)",
    "menu.status_none": "none",
    "menu.status_ready": "  STATUS: READY",
    "menu.status_incomplete": "  STATUS: INCOMPLETE",
    "menu.version_unverified": "not set",
    "menu.version_pinned": "v%d",
    "menu.version_auto": "auto",

    # -- add entity ------------------------------------------------------
    "menu.add_entity_title": "ADD ENTITY",
    "menu.family_protein": "Protein",
    "menu.family_rna": "RNA",
    "menu.family_dna": "DNA",
    "menu.family_ligand": "Ligand",
    "menu.add_protein_prompt": "Protein sequence: ",
    "menu.add_rna_prompt": "RNA sequence: ",
    "menu.add_dna_prompt": "DNA sequence (5' to 3'): ",
    "menu.dna_complement_question": "Do you want to add the complementary reverse-complement DNA strand?",
    "menu.dna_complement_menu": "Choose:",
    "menu.dna_complement_yes": "Yes - add the complementary strand (double-stranded DNA)",
    "menu.dna_complement_no": "No - use only the supplied strand (single-stranded DNA)",
    "menu.dna_complement_will_add": "The complementary strand will be added.",
    "menu.dna_complement_will_not_add": "Only the supplied strand will be used.",
    "menu.add_ligand_value_prompt": "Ligand value: ",
    "menu.ligand_kind_menu": "Is this ligand given as a CCD code or a SMILES string?",
    "menu.ligand_kind_ccd": "CCD code(s) — e.g. ATP, or several separated by spaces",
    "menu.ligand_kind_smiles": "SMILES string — e.g. C(C)O",
    "menu.quantity_direct_prompt": "How many copies of this ligand do you want? ",
    "menu.quantity_bad_value": "Enter a whole number of copies, at least 1.",
    "menu.add_cancelled": "Cancelled — nothing was added.",
    "menu.entity_added": "Entity added.",
    "menu.ask_templates_yn": "Use structural templates for this record? [y/N]: ",
    "menu.msa_skip": "No MSA will be used - edit the entity to change this later.",
    "menu.templates_skip_new": "No templates will be used - edit the entity to change this later.",
    "menu.templates_skip_edit": "No change - the template setting is unchanged.",
    "menu.msa_choice_title": "MSA (multiple sequence alignment) configuration:",
    "menu.msa_choice_current": "%s (current setting)",
    "menu.msa_choice_files": "Provide existing MSA file(s)",
    "menu.msa_choice_none": "No MSA - run without alignment data",
    "menu.msa_keep_new": "Automatic MSA: AlphaFold searches for the MSA at inference time; this builder writes no MSA fields.",
    "menu.msa_keep_edit": "The current MSA setting is kept unchanged.",
    "menu.msa_none_explained": "No MSA: AlphaFold will run MSA-free; the MSA fields will be explicit empty strings.",
    "menu.msa_files_explained": "Paired and unpaired are separate files; leave one blank only when that side must be the empty string.",
    "menu.msa_files_explained_rna": "RNA uses a single MSA file in A3M format; it has no paired side. Enter one file path.",
    "menu.ask_paired_msa_file": "Paired MSA file (blank = empty paired side): ",
    "menu.ask_unpaired_msa_file": "Unpaired MSA file (blank = empty unpaired side): ",
    "menu.ask_rna_msa_file": "RNA MSA file: ",
    "menu.msa_files_need_one": "Enter at least one MSA file (paired, unpaired, or both), or choose the no-MSA option.",
    "menu.msa_file_required": "An MSA file path is required here. Enter a path or 0 to cancel.",
    "menu.msa_file_invalid": "The MSA file %r cannot be used: %s. Enter another path or 0 to cancel.",
    "menu.msa_file_missing": "the file does not exist",
    "menu.msa_file_not_regular": "the path is not a regular file",
    "menu.msa_file_unreadable": "the file cannot be read",
    "menu.msa_file_empty": "the file is empty",
    "menu.msa_mode_auto": "Let AlphaFold search for MSAs automatically",
    "menu.msa_mode_unpaired": "Unpaired only",
    "menu.msa_mode_paired": "Paired only",
    "menu.msa_mode_both": "Both",
    "menu.msa_mode_free": "No MSA - proceed without alignment data",
    "menu.msa_mode_provided": "Provided (paste or file)",
    "menu.msa_paste_inline": "Paste inline text",
    "menu.msa_use_file": "Use a file",
    "menu.msa_source_title_paired": "Paired side",
    "menu.msa_source_title_unpaired": "Unpaired side",
    "menu.msa_source_title_rna": "Alignment source",
    "menu.msa_side_empty": "Leave this side empty",
    "menu.paste_msa": "Paste the alignment, finish with a blank line:",
    "menu.msa_inline_empty": "Nothing was pasted - the alignment setting is unchanged.",
    "menu.ask_msa_side_file": "Alignment file: ",
    "menu.templates_menu": "Templates:",
    "menu.templates_search": "Let AlphaFold search for templates",
    "menu.templates_none": "No templates - proceed without template structures",
    "menu.templates_list": "Provide template mmCIF files and residue index pairs",
    "menu.ref_templates_explained": (
        "For each template, give its own mmCIF content (a file, or pasted "
        "inline) and its own query:template residue index pairs (both 0-based)."
    ),
    "menu.templates_source_title": "Template %d mmCIF source:",
    "menu.paste_template": "Paste the mmCIF content, finish with a blank line:",
    "menu.templates_inline_empty": "Nothing was pasted - the template setting is unchanged.",
    "menu.ask_ref_path": "Template %d mmCIF file (0 cancels): ",
    "menu.ask_ref_pairs": "Template %d residue index pairs (query:template, 0-based, comma-separated; e.g. 0:5,1:6,2:7): ",
    "menu.ask_ref_another": "Add another template? [y/N]: ",
    "menu.ref_templates_cancelled": "Template collection cancelled - the template setting is unchanged.",

    "menu.no_entities": "This job has no entities, so there is nothing to vary.",

    # -- edit entity -----------------------------------------------------
    "menu.entity_editor_title": "EDIT ENTITY",
    "menu.entity_list_empty": "  (no entities)",
    "menu.no_entities_edit": "There are no entities to edit — add one first.",
    "menu.select_entity": "Select entity:",
    "menu.entity_action_title": "SELECTED ENTITY",
    "menu.selected_entity": "Entity: %s",
    "menu.entity_actions": "1. Edit\n2. Delete",
    "menu.entity_actions_polymer": (
        "1. Edit\n"
        "2. Delete\n"
        "3. Modifications"
    ),
    "menu.delete_confirm": "Delete \"%s\"?",
    "menu.delete_yes": "Yes, delete",
    "menu.delete_no": "No, go back",
    "menu.removed_detail": "Removed %r: %s.",
    "menu.ask_entity_description": (
        "Description for this entity (optional, blank leaves it unset): "
    ),
    "menu.edit_sequence_prompt": "New sequence (blank keeps the current one): ",
    "menu.edit_desc_prompt": "New description (blank keeps the current one): ",
    "menu.removed": "Removed %r.",
    "menu.entity_list_header": "  %s  %s  %d residues",
    "menu.entity_list_ligand": "  %s  ligand  %s",
    "menu.entity_list_ligand_counted": "  %s  ligand  %s  x%d",
    "menu.entity_mod_row": "      %s at residue %s%s",
    "menu.ligand_by_code": "CCD %s",
    "menu.ligand_by_notation": "SMILES notation",

    # -- custom CCD management -------------------------------------------
    "menu.ccd_title": "CUSTOM CCD MANAGEMENT",
    "menu.ccd_actions": (
        "1. View the custom CCD definition\n"
        "2. Set or replace the custom CCD definition\n"
        "3. Remove the custom CCD definition"
    ),
    "menu.ccd_none": "No custom CCD definition is set for this job.",
    "menu.ccd_current": "Current custom CCD definition:",
    "menu.ccd_path": "File: %s",
    "menu.ccd_inline": "Inline CIF definition: %s",
    "menu.ccd_inline_lines": "Total lines: %d",
    "menu.ccd_source_menu": "How is the definition supplied?",
    "menu.ccd_set": "Custom CCD definition set.",
    "menu.ccd_removed": "Custom CCD definition removed.",
    "menu.ccd_confirm": "Remove the custom CCD definition?",
    "menu.paste_definition": "Paste the CIF definition, finish with a blank line:",
    "menu.ask_ccd_path": "Path to the CIF definition file: ",

    # -- covalent bonds --------------------------------------------------
    "menu.bond_title": "COVALENT BOND MANAGEMENT",
    "menu.bond_note": (
        "A covalent bond links two entity endpoints; each endpoint is an "
        "entity, a 1-based residue number and an atom name (e.g. SG)."
    ),
    "menu.bond_none": "No covalent bonds are set for this job.",
    "menu.bond_actions": (
        "1. View the bonds\n"
        "2. Add a bond\n"
        "3. Remove a bond"
    ),
    "menu.bond_row": "%d. %s",
    "menu.bond_pair": "%s  <->  %s",
    "menu.bond_endpoint": "%s, residue %d, atom %s",
    "menu.bond_endpoint_a": "First endpoint:",
    "menu.bond_endpoint_b": "Second endpoint:",
    "menu.bond_entity": "Which entity is this endpoint?",
    "menu.bond_residue_prompt": "Residue number (1-based, 0 cancels): ",
    "menu.bond_residue_bad": "Enter a whole residue number of at least 1.",
    "menu.bond_atom_prompt": "Atom name (e.g. SG, blank cancels): ",
    "menu.bond_needs_entities": "Add at least two entities before defining a bond.",
    "menu.bond_added": "Covalent bond added.",
    "menu.bond_removed": "Covalent bond removed.",
    "menu.bond_remove_prompt": "Remove which covalent bond?",

    # -- PTM management --------------------------------------------------
    "menu.ptm_title": "POST-TRANSLATIONAL MODIFICATION MANAGEMENT",
    "menu.ptm_actions": (
        "1. View modifications\n"
        "2. Add a modification\n"
        "3. Edit a modification\n"
        "4. Remove a modification\n"
        "5. Show the supported D-amino-acid forms\n"
        "6. Set a protein residue's form (L or D)"
    ),
    "menu.ptm_none": "No post-translational modifications are set on any entity yet.",
    "menu.ptm_record": "%s",
    "menu.mod_target_entity": "Which entity holds the post-translational modification:",
    "menu.no_modification_target": (
        "No protein, RNA, or DNA chain to modify yet — add one first "
        "(ligands carry no post-translational modifications)."
    ),
    "menu.ask_code": "Post-translational modification code (e.g. SEP): ",
    "menu.ask_position": "Position (1-based residue number): ",
    "menu.mod_cancelled": "Cancelled — nothing was added to this record.",
    "menu.modification_added": "Post-translational modification added.",
    "menu.modification_removed": "Post-translational modification removed.",
    "menu.ptm_updated": "Post-translational modification updated.",
    "menu.ptm_edit_code_prompt": "New modification code (blank keeps the current one): ",
    "menu.ptm_edit_position_prompt": "New position (blank keeps the current one): ",
    "menu.mod_remove_prompt": "Remove which post-translational modification?",
    "menu.no_mods_on_record": "This record carries no post-translational modifications.",
    "menu.mod_menu_title": "POST-TRANSLATIONAL MODIFICATIONS ON THIS RECORD",
    "menu.mod_actions": (
        "1. Add a post-translational modification\n"
        "2. Edit a post-translational modification\n"
        "3. Remove a post-translational modification"
    ),
    "menu.mod_actions_protein": (
        "1. Add a post-translational modification\n"
        "2. Edit a post-translational modification\n"
        "3. Remove a post-translational modification\n"
        "4. Show the supported D-amino-acid forms\n"
        "5. Set this chain's residue form (L or D)"
    ),

    # -- D-amino-acid forms (the console's route to set_amino_acid_form) --
    "menu.d_form_title": "SUPPORTED D-AMINO-ACID FORMS",
    "menu.d_form_intro": (
        "Each of these CCD codes replaces one residue of a protein chain. "
        "Glycine is achiral, so it has none."
    ),
    "menu.d_form_row": "  %s  %-4s %s",
    "menu.d_form_note": (
        "Ordinary PTMs are still added by code; a D-form is set by residue "
        "position, and the service resolves its code."
    ),
    "menu.ptm_form_entity": "Which protein chain holds the residue:",
    "menu.no_protein_for_form": (
        "No protein chain to set a form on yet — add one first."
    ),
    "menu.ptm_form_position_prompt": (
        "Residue position for the form (1-based, 0 cancels): "
    ),
    "menu.ptm_form_position_out": (
        "Position %d is past the end of chain %s (%d residues)."
    ),
    "menu.ptm_form_residue": (
        "Position %d of chain %s is %s; its D-form is %s."
    ),
    "menu.ptm_form_residue_none": (
        "Position %d of chain %s is %s, which has no D-form."
    ),
    "menu.ptm_form_prompt": "Form — L (standard) or D (replacement): ",
    "menu.ptm_form_bad": "Enter L or D, not %r.",
    "menu.ptm_form_set": (
        "Position %d of chain %s is now the %s-form."
    ),

    # -- save and show summary -------------------------------------------
    "menu.summary_title": "JOB SUMMARY",
    "menu.summary_name": "Name: %s",
    "menu.summary_seeds": "Model seeds: %s",
    "menu.summary_version": "Version: %s",
    "menu.summary_entities": "Number of entities: %d",
    "menu.summary_breakdown": "Entity breakdown:",
    "menu.summary_protein": "- Proteins: %d",
    "menu.summary_dna": "- DNA:      %d",
    "menu.summary_rna": "- RNA:      %d",
    "menu.summary_ligand": "- Ligands:  %d",
    "menu.summary_other": "- Other supported types: %d",
    "menu.ask_save_path": "Save the JSON to (blank = %s): ",
    "menu.overwrite_confirm": "%s already exists. Overwrite it?",
    "menu.overwrite_yes": "Yes, overwrite",
    "menu.overwrite_no": "No, cancel",
    "menu.save_cancelled": "Cancelled — nothing was written.",
    "menu.save_job_blocked": "This job cannot be saved yet:",
    "menu.save_job_wrote": "Saved to %s",
    "menu.export_skipped": "Skipped (exists): %s",
    "menu.export_conflict": "Conflict: %s",
    "menu.card_line": "%d. %s — %s",
    "menu.finding_indent": "    ",

    # -- open a JSON file ------------------------------------------------
    "menu.ask_import_path": "AF3 JSON file to open: ",
    "menu.unknown_error": "unknown error",
    "menu.import_file_line": "File: %s",
    "menu.import_entities": "Entities: %d",
    "menu.job_family_header": "%s:",
    "menu.preview_seeds": "Seeds: %s",
    "menu.import_notes": "Fields this builder does not support for editing:",
    "menu.import_note_line": "  ! %s",
    "menu.import_confirm": "Open this JSON as the current job?",
    "menu.import_yes": "Open",
    "menu.import_no": "Cancel",
    "menu.import_failed": "Could not open this JSON.",
    "menu.import_reason": "Reason: %s",
    "menu.import_untouched": "The original file has not been modified.",
    "menu.import_loaded": "JSON opened. It is now a normal, editable job.",

    # -- file picking ----------------------------------------------------
    "menu.files_in": "Files in %s:",
    "menu.pick_hint": "Type a number to open or choose, a full path, or '..' to go up. 0 cancels.",
    "menu.pick_cannot_list": "Cannot list this directory.",

    # -- configuration generation from a file ------------------------------
    "menu.file_title": "CONFIGURATION GENERATION FROM A FILE",
    "menu.file_description": (
        "Choose what the file holds, then load it. Each valid entry becomes "
        "one independent AF3 JSON configuration: this base job plus that "
        "entity."
    ),
    "menu.file_base_job": "Base job: %s",
    "menu.file_base_entities": "Base entities: %d",
    "menu.file_actions": "1. Load an input file and generate configurations",
    "menu.file_kinds_title": "What does the file contain?",
    "menu.file_target_title": "What each entry changes",
    "menu.file_target_add": "Add a new entity to each configuration",
    "menu.file_target_row": "Replace entity %s (%s)",
    "menu.file_kind_protein": "Protein sequences, one per line",
    "menu.file_kind_dna": "DNA sequences, one per line",
    "menu.file_kind_rna": "RNA sequences, one per line",
    "menu.file_kind_ligand_smiles": (
        "Ligands by SMILES, one per line, with an optional name first"
    ),
    "menu.file_kind_ligand_ccd": (
        "Ligands by CCD code, one ligand per line (several codes make one "
        "multi-component ligand)"
    ),
    "menu.file_prompt_sequence": "Sequence file (.txt, one sequence per line): ",
    "menu.file_prompt_ligand_smiles": "Ligand file (.smiles or .txt): ",
    "menu.file_prompt_ligand_ccd": "CCD code file (.txt, one ligand per line): ",
    "menu.file_preview_title": "%d entries read from %s:",
    "menu.file_preview_entry": "  - %s",
    "menu.file_output_root": "Output folder for the configurations [%s]: ",
    # Where the offered default came from, and anything wrong with the
    # configured one. The sentence itself is the path service's (it knows
    # which source failed); this entry only frames it.
    "menu.output_root_note": "Output folder: %s",
    "menu.output_root_problem": "%s",
    "menu.file_generating": "Generating configurations...",
    "menu.file_written": "Wrote %s",
    "menu.file_summary_location": "Written under %s",
    "menu.file_refused": "Nothing was written: %s",
    "menu.file_blocked": "Nothing was written; %d blocking finding(s):",
    "menu.file_nothing_written": (
        "Nothing was written: the overwrite policy skipped every planned file."
    ),


    # -- the Qt desktop front end (Stage 1: review & preview) -------------
    # The desktop shell's own chrome. Domain wording is never repeated
    # here: family, status, version, MSA/template and import wording all
    # come from the entries above, so the two front ends cannot drift.
    "gui.window_title": "AF3 JSON Builder",
    "gui.window_title_job": "%s - AF3 JSON Builder",
    "gui.window_title_dirty": "%s* - AF3 JSON Builder",
    "gui.tab_overview": "Overview",
    "gui.tab_entities": "Entities",
    "gui.action_open": "Open AF3 JSON…",
    "gui.section_job": "Job details",
    "gui.readiness_ok": "Ready — nothing blocks generation.",
    "gui.readiness_blocked": "Not ready: %d blocking findings.",
    "gui.readiness_blocked_one": "Not ready: 1 blocking finding.",
    "gui.readiness_ready": "Ready",
    "gui.readiness_attention": "Needs attention",
    "gui.findings_detail": "Technical detail: %s",
    "gui.col_number": "#",
    "gui.col_severity": "Severity",
    "gui.col_where": "Where",
    "gui.col_message": "Message",
    "gui.col_ids": "Entity ID(s)",
    "gui.col_family": "Family",
    "gui.col_summary": "Length / representation",
    "gui.col_description": "Description",
    "gui.dialect_label": "Dialect",
    "gui.counts_value": "Protein %d · RNA %d · DNA %d · Ligand %d",
    "gui.notice_no_job": (
        "Create a job or open an AF3 JSON to begin. Nothing leaves this computer."
    ),
    "gui.notice_job": (
        "Edits stay in memory until you save JSON or generate output. Nothing "
        "is uploaded."
    ),
    "gui.notice_dirty": (
        "Unsaved changes - save JSON or generate output to write them."
    ),
    "gui.source_file": "Source file: %s",
    "gui.source_none": "No file open.",
    "gui.demo_notice": "Sample data (demo mode) — no file is open and nothing is written.",
    "gui.open_dialog_title": "Open an AF3 JSON file",
    "gui.file_filter": (
        "AF3 JSON files (*.json *.txt);;All files (*)"
    ),
    "gui.import_title": "Review the file before opening it",
    "gui.import_summary_title": "What this file contains",
    "gui.import_ids": "Entity IDs: %s",
    "gui.import_accept": "Import",
    "gui.entities_none": "This job has no entities.",
    "gui.entity_hint": (
        "Select an entity to see its details and its own settings beside the "
        "list. Add, edit or remove a record with the buttons above."
    ),
    "gui.entity_selector": "Entity",
    "gui.entity_selector_empty": "No entities yet",
    "gui.entity_choice_sequence": "%s · %s · %d residues",
    "gui.entity_choice_ligand": "%s · %s · %s",
    "gui.entity_tab_settings": "Entity settings",
    "gui.entity_tab_ccd": "Custom CCDs",
    "gui.entity_tab_bonds": "Covalent bonds",
    "gui.entity_job_wide": (
        "This applies to the whole job, not to one selected entity."
    ),
    "gui.entity_length": "Length",
    "gui.entity_length_value": "%d residues",
    "gui.entity_representation": "Representation",
    "gui.entity_partner": "Reverse-complement partner: %s",
    "gui.entity_no_partner": "No partner strand accompanies this DNA strand.",
    "gui.entity_modification_row": "%s at %d",
    "gui.templates_provided": "%d provided",
    "gui.preview_title": "Generated JSON (read-only)",
    "gui.preview_note": "This is the builder's generated JSON for the open job. It is normalized, so its layout may differ from the file you opened.",
    "gui.preview_unavailable": "No JSON can be shown yet.",
    "gui.preview_refresh": "Refresh",
    "gui.entity_details": "Selected entity",
    "gui.entity_details_hint": (
        "A compact summary. Use Edit to change the sequence or representation; "
        "the settings below apply to this entity alone."
    ),
    "gui.entity_settings": "Settings for this entity",
    "gui.entity_ligand_no_settings": (
        "A ligand has no PTMs, MSA or templates. Edit its representation with "
        "the Edit button above."
    ),
    "gui.entity_partner_label": "Reverse-complement partner",
    # Generation from a file: an action on Entities, the input-type question,
    # two path pickers, the review before writing, and the report of what was
    # written. Entity-neutral, because every supported kind goes through it.
    "gui.action_file_generation": "Generate configurations from file...",
    "gui.action_file_generation_hint": (
        "Load a file of protein, DNA or RNA sequences, or of ligands, and "
        "write one AF3 JSON per entry. This job is the base and is not "
        "modified."
    ),
    "gui.entity_file_note": (
        "One file in, one configuration per entry out; existing files are "
        "never replaced."
    ),
    "gui.batch_kind_title": "Input type",
    "gui.batch_kind_prompt": "What does the file contain?",
    "gui.batch_target_title": "Base entity",
    "gui.batch_target_prompt": (
        "Each entry can add a new entity or replace one this job already "
        "holds. What should this file do?"
    ),
    "gui.batch_target_add": "Add a new entity",
    "gui.batch_target_row": "Replace %s - %s",
    "gui.batch_file_dialog": "Choose an input file",
    "gui.batch_file_filter_sequences": "Sequence lists (*.txt);;All files (*)",
    "gui.batch_file_filter_ligands": "Ligand lists (*.smiles *.txt);;All files (*)",
    "gui.batch_folder_dialog": (
        "Choose the folder for the generated configurations"
    ),
    "gui.batch_preview_title": "Review the input file",
    "gui.batch_preview_entries": "%d entries read:",
    "gui.batch_preview_kind": "Input type: %s",
    "gui.batch_preview_row": "  - %s",
    "gui.batch_preview_more": "...and %d more",
    "gui.batch_preview_destination": "Output folder: %s",
    "gui.batch_preview_files": (
        "%d configuration file(s) plus a manifest will be written."
    ),
    "batch.preview_lead_protein": (
        "Each entry adds one new protein entity to the base job."
    ),
    "batch.preview_lead_dna": (
        "Each DNA entry adds one new DNA entity to the base job: the strand "
        "you supplied plus its reverse-complement strand, in one "
        "configuration."
    ),
    "batch.preview_lead_rna": "Each entry adds one new RNA entity to the base job.",
    "batch.preview_lead_ligand": (
        "Each entry adds one new ligand entity to the base job."
    ),
    "batch.preview_lead_replace": (
        "Each entry replaces entity %s in its own configuration. Every other "
        "entity is copied unchanged, and this job itself is not modified."
    ),
    "batch.preview_tail": (
        "The base job itself is not modified, and existing files are never "
        "replaced: if one already exists with different content the whole "
        "batch is refused, so choose another output folder instead."
    ),
    "batch.preview_assets": (
        "External files (MSA, templates, custom CCD) follow this job's path "
        "policy; with the default, CopyIntoAssets, each configuration gets "
        "its own assets folder and can be moved on its own."
    ),
    "batch.summary_configurations": "Generated %d AF3 configurations.",
    "batch.summary_one_configuration": "Generated 1 AF3 configuration.",
    "batch.summary_manifests": "Wrote %d manifest files.",
    "batch.summary_one_manifest": "Wrote 1 manifest.",
    "batch.summary_assets": "Copied %d asset files.",
    "batch.summary_one_asset": "Copied 1 asset file.",
    "batch.summary_total": "Total output files: %d.",
    "gui.batch_preview_accept": "Generate",
    "gui.batch_result_title": "Generated configurations",
    "gui.batch_result_written": "%d file(s) written:",
    "gui.batch_result_errors": "These could not be written:",
    "gui.batch_result_skipped": (
        "%d planned file(s) were left alone by the overwrite policy "
        "(Skip); they were not rewritten."
    ),
    "gui.batch_result_refused": "Nothing was written: %s",
    "gui.batch_result_nothing": "Nothing was written.",
    "gui.action_quit": "Quit",
    "gui.value_unset": "not set",
    "gui.value_empty": "(empty)",
    "gui.representation_ccd": "CCD: %s",
    "gui.representation_smiles": "SMILES: %s",
    "gui.cli_description": "Open an AF3 JSON file in the desktop builder window.",
    "gui.cli_help_path": "An AF3 JSON file to review; the window still asks you to confirm it.",
    "gui.cli_help_demo": "Start with built-in sample data instead of a file; nothing is written.",

    # -- the Qt desktop front end (Stage 2: the job lifecycle) ------------
    # New Job / Save JSON / the job-settings panel and their questions.
    # Saving reuses the console's own save, overwrite and cancellation
    # wording above, so both front ends say the same thing.
    "gui.action_new_job": "New Job…",
    "gui.action_save": "Save JSON…",
    # Save feedback: the status line says what is happening, and a refusal
    # names the file and the reason rather than a traceback.
    "gui.save_started": "Saving…",
    "gui.save_busy": "A save is already in progress.",
    "gui.save_done": "Configuration saved successfully.",
    "gui.open_succeeded": "Job opened successfully.",
    "gui.save_permission_denied": (
        "Cannot write to %s: access was denied. Choose another folder, or "
        "close the file if it is open in another program."
    ),
    "gui.save_filesystem_failed": "Cannot write to %s: %s",
    # The first-run panel and the always-visible command bar.
    "gui.toolbar_job": "Job",
    "gui.empty_title": "Start a job",
    "gui.empty_body": (
        "Create a new AF3 job, or open an existing AF3 JSON file to review and "
        "edit it. Save JSON writes the current job at any time."
    ),
    "gui.empty_new": "New job",
    "gui.empty_open": "Open AF3 JSON…",
    "gui.section_settings": "Job settings",
    "gui.settings_apply": "Apply",
    "gui.settings_default": "Application default",
    "gui.settings_custom": "Changed — not the default",
    "gui.settings_name_applied": "Job name updated to %s.",
    "gui.settings_seeds_applied": "Model seeds updated.",
    "gui.settings_version_applied": "JSON version pinned to %d.",
    "gui.save_dialog_title": "Save the job as an AF3 JSON file",
    "gui.overwrite_title": "Replace an existing file",
    "gui.discard_title": "Unsaved changes",
    "gui.discard_question": "This job has unsaved changes. Discard them?",
    "gui.discard_accept": "Discard changes",
    "gui.discard_cancel": "Keep the job",
    "gui.problem_title": "The action could not be completed",

    # -- the Qt desktop front end (Stage 3: entity management) ------------
    # Add/edit/delete actions, their forms and their questions. Family,
    # sequence-alphabet and representation rules stay in the services; the
    # wording below explains, it never decides.
    "gui.action_add_protein": "Add Protein",
    "gui.action_add_rna": "Add RNA",
    "gui.action_add_dna": "Add DNA",
    "gui.action_add_ligand": "Add Ligand",
    "gui.action_edit_record": "Edit entity",
    "gui.action_delete_record": "Delete entity",
    "gui.dialog_add_protein": "Add a protein",
    "gui.dialog_add_rna": "Add an RNA chain",
    "gui.dialog_add_dna": "Add a DNA duplex",
    "gui.dialog_add_ligand": "Add a ligand",
    "gui.dialog_edit_protein": "Edit the selected protein",
    "gui.dialog_edit_rna": "Edit the selected RNA chain",
    "gui.dialog_edit_dna": "Edit the selected DNA strand",
    "gui.dialog_edit_ligand": "Edit the selected ligand",
    "gui.form_sequence": "Sequence",
    "gui.form_description": "Description (optional)",
    "gui.form_add": "Add",
    "gui.form_save": "Apply changes",
    "gui.form_cancel": "Cancel",
    "gui.sequence_add_hint": "Paste is fine; the sequence must contain only this family's letters — no FASTA header and no line breaks.",
    "gui.sequence_edit_hint": "The sequence is changed through the builder's own update operation; the record's other settings are preserved. Paste a plain sequence — no FASTA header and no line breaks.",
    "gui.dna_add_hint": "The sequence you enter becomes one strand; choose below whether the builder also creates its reverse-complement partner.",
    "gui.dna_duplex_choice": "DNA strands",
    "gui.dna_duplex_pair": "Double-stranded — also add the reverse-complement partner strand",
    "gui.dna_duplex_single": "Single-stranded — use only the strand entered here",
    "gui.dna_edit_hint": "This strand belongs to a DNA duplex: changing its sequence updates its reverse-complement partner through the builder.",
    "gui.ligand_kind": "Representation",
    "gui.ligand_ccd_option": "CCD code(s)",
    "gui.ligand_smiles_option": "SMILES",
    "gui.ligand_value": "Codes or SMILES",
    "gui.ligand_copies": "Copies",
    "gui.ligand_copies_fixed": "The copy count is set when the ligand is created and cannot be changed afterwards.",
    "gui.ligand_form_hint": "An ion is a ligand represented by its CCD code (for example ZN).",
    "gui.description_version_warning": "This job is pinned to JSON version %d; per-entity descriptions are written from version %d. The description is kept, not discarded — raise the job's JSON version to include it.",
    "gui.delete_title": "Delete entity",
    "gui.delete_single": "Remove entity %s from the job?",
    "gui.delete_duplex": "Entity %s is one strand of a DNA duplex; removing it removes its partner %s as well.",
    "gui.delete_copies": "Entity %s is a multi-copy ligand with %d identifiers; removing it removes all of them.",
    "gui.delete_accept": "Delete",

    # -- the Qt desktop front end (Stage 4: advanced entity settings) -----
    # Modifications, alignment/MSA, templates, the job-level custom CCD
    # definition and covalent bonds. Mode words stay the service's own
    # ('automatic', 'free', ...); only the labels and explanations live here,
    # and the explanations describe the model, they never decide.
    "gui.adv_no_selection": (
        "Select an entity in the table above to edit its modifications, MSA "
        "and templates."
    ),
    "gui.adv_selected": "Selected entity: %s",
    "gui.adv_scope_entity": "This entity",
    "gui.adv_scope_job": "Whole job (all entities)",
    "gui.adv_scope_job_hint": (
        "A custom CCD definition and covalent bonds belong to the job, not to "
        "the selected entity; they apply to the generated file as a whole."
    ),

    "gui.section_modifications": "Modifications / PTMs",
    "gui.mod_columns": "Code · Position (1-based) · Residue",
    "gui.mod_note": "Modification positions are 1-based residue numbers counted from the chain's first residue.",
    "gui.mod_needs_polymer": "A ligand carries no modifications; select a protein, RNA or DNA chain.",
    "gui.mod_none": "No modifications on this entity.",
    "gui.mod_add": "Add…",
    "gui.mod_edit": "Edit…",
    "gui.mod_remove": "Remove…",
    "gui.mod_dialog_add": "Add a modification to entity %s",
    "gui.mod_dialog_edit": "Edit the selected modification on entity %s",
    "gui.mod_form_code": "Modification code",
    "gui.mod_form_position": "Position (1-based)",
    "gui.mod_col_residue": "Residue",
    "gui.mod_code_placeholder": "e.g. SEP",
    "gui.mod_residue_echo": "Residue at that position: %s",
    "gui.mod_residue_out_of_range": "Position %d is past the end of this chain (%d residues).",
    "gui.mod_form_form": "Residue form",
    "gui.mod_form_l": "L-form (standard residue)",
    "gui.mod_form_d": "D-form",
    "gui.mod_form_d_hint": (
        "A D-form replaces the residue at this position. Only one modification "
        "can occupy a position, so remove any existing PTM there first."
    ),
    "gui.mod_form_resolved": "Resolved CCD code: %s",
    "gui.mod_form_d_glycine": (
        "Glycine is achiral: it has no D-form, so only the L-form is available here."
    ),
    "gui.mod_form_d_no_mapping": (
        "Residue %s has no D-form in this build, so only the L-form is available here."
    ),
    "gui.mod_form_d_needs_position": (
        "Choose a position inside the chain to resolve a D-form."
    ),
    "gui.mod_delete_title": "Remove a modification",
    "gui.mod_delete_question": "Remove %s at residue %d from entity %s?",
    "gui.mod_select_first": "Select a modification in the list first.",

    "gui.section_alignment": "Alignment / MSA",
    "gui.alignment_current": "Current alignment: %s",
    "gui.alignment_button": "Change alignment…",
    "gui.alignment_dialog": "Alignment for entity %s",
    "gui.alignment_mode": "Mode",
    "gui.alignment_source": "Alignment source",
    "gui.alignment_inline": "Alignment text",
    "gui.alignment_path": "Alignment file",
    "gui.alignment_browse": "Choose file…",
    "gui.alignment_file_dialog": "Choose an alignment file",
    "gui.alignment_hint": (
        "Choose how this entity's multiple sequence alignment (MSA) is supplied."
    ),
    "gui.alignment_hint_automatic": "AlphaFold searches for the alignment itself; the job stores none.",
    "gui.alignment_hint_free": "No alignment data: prediction runs without an MSA.",
    "gui.alignment_hint_source": "The alignment comes from what you provide here — paste text or choose a file, not both.",
    "gui.alignment_paired_source": "Paired side source",
    "gui.alignment_paired_same": "Same as the unpaired source",
    "gui.alignment_paired_inline": "Paired alignment text",
    "gui.alignment_paired_path": "Paired alignment file",
    "gui.alignment_path_version": "An external alignment file is written as a path field, which needs input version %d or later.",
    "gui.alignment_state_automatic": "automatic (AlphaFold searches)",
    "gui.alignment_state_free": "no alignment",
    "gui.alignment_state_provided": "provided (%s)",
    "gui.alignment_source_inline": "inline text",
    "gui.alignment_source_file": "external file",
    "gui.alignment_not_applicable": "A %s entity has no alignment setting.",
    "gui.alignment_applied": "Alignment updated.",

    "gui.section_templates": "Templates",
    "gui.templates_current": "Current templates: %s",
    "gui.templates_button": "Edit templates…",
    "gui.templates_dialog": "Templates for entity %s",
    "gui.templates_mode": "Templates",
    "gui.templates_col_file": "mmCIF source",
    "gui.templates_col_pairs": "Index pairs (query:template, 0-based)",
    "gui.templates_pairs_note": "Index pairs map query residues to template residues and are 0-based; leave a cell blank for none.",
    "gui.templates_add_file": "Add file…",
    "gui.templates_add_inline": "Add inline mmCIF…",
    "gui.templates_edit_source": "Edit source…",
    "gui.templates_inline_row": "Inline mmCIF (%d lines)",
    "gui.templates_inline_dialog": "Inline template mmCIF",
    "gui.templates_inline_content": "mmCIF content",
    "gui.templates_remove_file": "Remove file…",
    "gui.templates_file_dialog": "Choose a template structure file",
    "gui.templates_file_filter": "mmCIF files (*.cif *.mmcif);;All files (*)",
    "gui.templates_hint_search": "AlphaFold searches for templates itself.",
    "gui.templates_hint_none": "No templates: AlphaFold will not search for any.",
    "gui.templates_hint_list": (
        "One row per template — a file you choose or inline mmCIF you paste; "
        "pairs are query:template, 0-based."
    ),
    "gui.templates_path_version": "An external template file is written as a path field, which needs input version %d or later.",
    "gui.templates_state_search": "search allowed (AlphaFold finds them)",
    "gui.templates_state_none": "none (explicitly template-free)",
    "gui.templates_not_applicable": "Only a protein can carry templates.",
    "gui.templates_applied": "Templates updated.",

    "gui.section_ccd": "Custom CCD definition",
    "gui.ccd_note": "One custom component definition applies to the whole job: paste CIF text, or point at a CIF file — never both.",
    "gui.ccd_option_none": "No custom definition",
    "gui.ccd_option_inline": "Paste a CIF definition",
    "gui.ccd_option_file": "Load from a CIF file",
    "gui.ccd_inline_label": "CIF definition text",
    "gui.ccd_path_label": "CIF definition file",
    "gui.ccd_browse": "Choose file…",
    "gui.ccd_file_dialog": "Choose a CIF definition file",
    "gui.ccd_file_filter": "CIF files (*.cif *.mmcif);;All files (*)",
    "gui.ccd_apply": "Apply",
    "gui.ccd_clear": "Clear",
    "gui.ccd_active": "Active definition: %s",
    "gui.ccd_active_none": "none",
    "gui.ccd_active_inline": "inline CIF text (%d lines)",
    "gui.ccd_active_file": "external file %s",
    "gui.ccd_path_version": "An external definition is written as a path field, which needs input version %d or later.",
    "gui.ccd_applied": "Custom CCD definition updated.",
    "gui.ccd_cleared": "Custom CCD definition cleared.",

    "gui.section_bonds": "Covalent bonds",
    "gui.bond_note": "Each bond names two endpoints as an entity, a 1-based residue and an atom name.",
    "gui.bond_none": "No covalent bonds are defined.",
    "gui.bond_columns": "First endpoint · Second endpoint",
    "gui.bond_add": "Add bond…",
    "gui.bond_remove": "Remove bond…",
    "gui.bond_dialog": "Add a covalent bond",
    "gui.bond_endpoint_a": "First endpoint",
    "gui.bond_endpoint_b": "Second endpoint",
    "gui.bond_entity": "Entity",
    "gui.bond_residue": "Residue (1-based)",
    "gui.bond_atom": "Atom name",
    "gui.bond_columns_note": "Entity · Residue (1-based) · Atom name",
    "gui.bond_atom_placeholder": "e.g. SG",
    "gui.bond_endpoint_text": "%s, residue %d, atom %s",
    "gui.bond_pair_text": "%s  <->  %s",
    "gui.bond_added": "Covalent bond added.",
    "gui.bond_removed": "Covalent bond removed.",
    "gui.bond_delete_title": "Remove a covalent bond",
    "gui.bond_delete_question": "Remove the bond between %s and %s?",
    "gui.bond_select_first": "Select a bond in the list first.",
    "gui.bond_needs_entities": "Add entities before defining a bond.",

    # -- the mockup shell (sidebar, header, page titles) ------------------
    # The approved mockup's chrome. The five destination names reuse the
    # tab_* entries above, so the sidebar and the window speak one vocabulary.
    "gui.app_name": "AF3 Builder",
    "gui.app_subtitle": "Molecular input workspace",
    "gui.header_job": "Job: %s",
    "gui.header_no_job": "No job open",
    "gui.header_unsaved": "Unsaved",
    "gui.header_saved": "Saved",
    "gui.nav_section_workspace": "WORKSPACE",
    "gui.breadcrumb_overview": "WORKSPACE / OVERVIEW",
    "gui.overview_title": "Prepare your AF3 job",
    "gui.overview_intro": (
        "Configure the input, check readiness and review what will be generated."
    ),
    "gui.field_job_name": "JOB NAME",
    "gui.field_seeds": "MODEL SEEDS",
    "gui.field_version": "JSON VERSION",
    "gui.stat_entities": "ENTITIES",
    "gui.stat_readiness": "READINESS",
    "gui.stat_entities_none": "No entities yet",
    "gui.stat_no_job": "No job open",
    "gui.family_protein": "protein",
    "gui.family_proteins": "proteins",
    "gui.family_rna": "RNA",
    "gui.family_dna": "DNA strand",
    "gui.family_dna_plural": "DNA strands",
    "gui.family_ligand": "ligand",
    "gui.family_ligands": "ligands",
    "gui.dialect_caption": "Dialect: %s",
    "gui.overview_next_entities": "Add at least one entity",
    "gui.overview_next_entities_detail": (
        "The current job cannot be generated without at least one entity."
    ),
    "gui.overview_next_findings": "Review the blocking issues",
    "gui.overview_next_findings_detail": (
        "Save and Generate explain what blocks the job when you attempt them."
    ),
    "gui.overview_next_generate": "Review the output plan",
    "gui.overview_next_generate_detail": (
        "Nothing blocks generation - review the planned files and write them."
    ),
    "gui.overview_next_nojob_detail": (
        "Create a job or open an AF3 JSON file to begin."
    ),
    "gui.overview_go_entities": "Manage entities",
    "gui.overview_go_generate": "Open Generate",
    "gui.overview_validate": "Validate job",
    "gui.validate_ok": "Validation passed: no findings.",
    "gui.validate_findings": (
        "Validation found %d blocking issues; save and generate are blocked."
    ),
    "gui.overview_no_job": (
        "No job is open. Use New or Open in the FILE footer to begin."
    ),
    "gui.entity_summary_manage": "Manage entities",
    "gui.entity_summary_hint": (
        "Open the entity workspace to add, edit or remove entities."
    ),
    "gui.blocked_header": "%d blocking issues stop this action; nothing was written:",
    "gui.blocked_header_one": "1 blocking issue stops this action; nothing was written:",
    "gui.blocked_line": "• %s",
    "gui.blocked_fix": "  %s",
    "gui.blocked_more": "…and %d more.",
    "gui.preview_copy": "Copy JSON",
    "gui.preview_copied": "The JSON was copied to the clipboard.",
    "gui.preview_title_note": "Read-only",
}


def text(key: str) -> str:
    """The registered wording for ``key``. Unknown keys raise: a missing
    entry is a programming error, never a silent fallback (the same
    discipline the traceability registry applies to labels)."""
    try:
        return STRINGS[key]
    except KeyError:
        raise KeyError(
            "no string registered for %r; add it to ui/present/strings.py" % key
        )


#: What one entry of each kind becomes, in the note shown before writing.
#: A whole sentence per family rather than a noun slot: "one new DNA" is not
#: English, and the DNA construction needs more than a noun to explain it.
_PREVIEW_LEAD_KEYS = {
    "protein-sequence": "batch.preview_lead_protein",
    "dna-sequence": "batch.preview_lead_dna",
    "rna-sequence": "batch.preview_lead_rna",
    "ligand-smiles": "batch.preview_lead_ligand",
    "ligand-ccd": "batch.preview_lead_ligand",
}


def batch_preview_note(kind: str, replaced: str = "") -> str:
    """The note shown before a batch is written, for both front ends.

    Three things the audit found under-explained live here rather than in one
    front end: what an entry becomes (and that the base is untouched), the
    overwrite policy's real consequence (one different existing file refuses
    the whole batch), and — for DNA only — that one record becomes a duplex.
    The DNA sentence states the established construction; it does not change
    it. A run that replaces an entity says so instead of calling every entry a
    new entity, because "one new protein per entry" is false in that mode.
    """
    lead = (
        text("batch.preview_lead_replace") % replaced
        if replaced
        else text(_PREVIEW_LEAD_KEYS.get(kind, "batch.preview_lead_protein"))
    )
    return "\n".join(
        [
            lead,
            text("batch.preview_tail"),
            text("batch.preview_assets"),
        ]
    )


def batch_summary(counts) -> str:
    """One sentence describing a finished batch run's outputs.

    Both front ends print this, so the console and the desktop cannot
    describe the same run with different totals. ``counts`` is
    ``app.results.BatchCounts`` — roles, not plan rows: the manifest is
    never called a configuration, and copied assets are reported as copies
    rather than folded silently into the file count.

    The assets sentence appears only when something was copied, so the
    ordinary case stays the short "Generated N … Wrote 1 manifest. Total …".
    """
    if counts.configurations == 1:
        parts = [text("batch.summary_one_configuration")]
    else:
        parts = [
            text("batch.summary_configurations") % counts.configurations
        ]
    if counts.manifests == 1:
        parts.append(text("batch.summary_one_manifest"))
    elif counts.manifests:
        parts.append(text("batch.summary_manifests") % counts.manifests)
    if counts.assets == 1:
        parts.append(text("batch.summary_one_asset"))
    elif counts.assets:
        parts.append(text("batch.summary_assets") % counts.assets)
    parts.append(text("batch.summary_total") % counts.total)
    return " ".join(parts)


def blocking_verdict(count: int) -> str:
    """The readiness verdict for ``count`` blocking findings.

    One place decides the singular/plural wording, so the card, the status
    line and the tests cannot drift into "1 blocking finding(s)".
    """
    if count == 1:
        return text("gui.readiness_blocked_one")
    return text("gui.readiness_blocked") % count
