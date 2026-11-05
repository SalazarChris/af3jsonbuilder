"""Qt table models over the existing configuration, findings and status.

Three projections, all read-only, all built from data an existing service
already produced:

- :class:`EntityTableModel` — one row per ``configuration.records`` entry, in
  the configuration's own order. Rows carry display strings and the record
  they came from; the record itself is never copied, reordered or mutated.
  **Order is the contract's order**: the underlying tuple is only ever read,
  so no sorting or view interaction can change it.
- :class:`FindingsTableModel` — the validation findings as the present layer
  already formats them (``ui.present.findings.format_findings``), so the
  wording, numbering and severity tokens are the ones the console shows.
- :class:`StatusTableModel` — the readiness rows of a ``ConfigurationStatus``
  the validation service built. Nothing here decides readiness: the state
  word comes from the service's own row, and ``ConfigurationStatus.ready``
  is what the page displays as the verdict.

Family, MSA, template, version and import wording all resolve through the
existing string registry, so the desktop window and the console cannot drift
apart. No domain rule is evaluated here — a projection that needed one would
belong in ``app``.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFontDatabase

from configbuilder.app.status import FieldState
from configbuilder.model import (
    ComponentRecord,
    Explicit,
    ExplicitEmpty,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    Present,
    SearchAllowed,
    Unset,
    duplex_partner,
    fold_representation,
    fold_version_selection,
)
from configbuilder.ui.present.alignment import alignment_label
from configbuilder.ui.present.findings import format_findings
from configbuilder.ui.present.strings import text as _text

__all__ = [
    "EntityRow",
    "EntityTableModel",
    "FindingsTableModel",
    "StatusTableModel",
    "counts_text",
    "describe_entity",
    "family_label",
    "version_text",
]


# -- entity projection --------------------------------------------------------------

_FAMILY_LABEL_KEYS = {
    FamilyARecord: "menu.family_protein",
    FamilyBRecord: "menu.family_rna",
    FamilyCRecord: "menu.family_dna",
    ComponentRecord: "menu.family_ligand",
}

_ABSENT = "menu.status_absent"


def _presence_text(value) -> str:
    """A presence value as text: unset, explicitly empty, or its content."""
    if isinstance(value, Unset):
        return _text("gui.value_unset")
    if isinstance(value, ExplicitEmpty):
        return _text("gui.value_empty")
    if isinstance(value, Present):
        return value.value
    return _text("gui.value_unset")


def _representation_text(record) -> str:
    """A ligand's representation, through the model's own fold."""
    return fold_representation(
        record.representation,
        lambda codes: _text("gui.representation_ccd")
        % ", ".join(code.value for code in codes),
        lambda text: _text("gui.representation_smiles") % text,
    )


def _alignment_text(record) -> str:
    """A chain's MSA state, or ``-`` when the family has no alignment field."""
    label = alignment_label(getattr(record, "alignment", None))
    return label if label else _text(_ABSENT)


def _templates_text(record) -> str:
    """A chain's template state, or ``-`` when the family has none."""
    references = getattr(record, "references", None)
    if references is None:
        return _text(_ABSENT)
    if isinstance(references, SearchAllowed):
        return _text("menu.templates_search")
    if isinstance(references, Explicit):
        count = len(references.items)
        return _text("gui.templates_provided") % count if count else _text("menu.templates_none")
    return _text(_ABSENT)


class EntityRow(object):
    """One entity, projected to display strings plus its record handle.

    ``record_key`` is the registry's own primary identifier for the record —
    never a list position — which is what a finding's ``FieldPath`` carries
    and what the page uses to select a row.
    """

    __slots__ = (
        "record_key",
        "ids",
        "family",
        "summary",
        "description",
        "modifications",
        "msa",
        "templates",
        "record",
        "partner_key",
        "is_sequence",
        "is_dna",
    )

    def __init__(
        self,
        record_key,
        ids,
        family,
        summary,
        description,
        modifications,
        msa,
        templates,
        record,
        partner_key=None,
        is_sequence=True,
        is_dna=False,
    ) -> None:
        self.record_key = record_key
        self.ids = ids
        self.family = family
        self.summary = summary
        self.description = description
        self.modifications = modifications
        self.msa = msa
        self.templates = templates
        self.record = record
        self.partner_key = partner_key
        self.is_sequence = is_sequence
        self.is_dna = is_dna

    def __repr__(self) -> str:
        return "EntityRow(%r, %s)" % (self.record_key, self.family)


def fixed_font():
    """The platform's fixed-width font, for sequences and JSON text.

    Asked of Qt rather than named, so the same code reads well on Windows
    (where the GUI runs) and on the Linux machines the generated files go to.
    """
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)


def family_label(record) -> str:
    """The registry label for a record's family (one source for both pages)."""
    return _text(_FAMILY_LABEL_KEYS.get(type(record), "menu.status_other"))


def describe_entity(configuration, record) -> EntityRow:
    """Project one record into a row, reading only what the model holds.

    Every family gets exactly the facts its model type actually has: a DNA
    strand and a ligand show ``-`` for MSA and templates rather than a
    plausible-looking guess, and a DNA strand carries the identifier of the
    strand paired with it (``duplex_partner``) so the two halves of a duplex
    can be recognised without splitting or reordering anything. The list
    displays identity, family and summary; the remaining facts belong to the
    selected entity's details card.
    """
    is_ligand = isinstance(record, ComponentRecord)
    if is_ligand:
        summary = _representation_text(record)
        modifications = _text(_ABSENT)
    else:
        summary = str(len(record.sequence.text))
        count = len(getattr(record, "modifications", ()) or ())
        modifications = str(count) if count else _text("menu.status_none")
    partner = duplex_partner(configuration, record)
    return EntityRow(
        record_key=record.ids.primary.value,
        ids=", ".join(entity.value for entity in record.ids.ids),
        family=family_label(record),
        summary=summary,
        description=_presence_text(record.description),
        modifications=modifications,
        msa=_alignment_text(record),
        templates=_templates_text(record),
        record=record,
        partner_key=partner.ids.primary.value if partner is not None else None,
        is_sequence=not is_ligand,
        is_dna=isinstance(record, FamilyCRecord),
    )


class EntityTableModel(QAbstractTableModel):
    """The entity table. Rows follow ``configuration.records`` exactly."""

    #: The compact list: identity, family and one useful summary. The rest of
    #: a record's facts (description, PTMs, MSA, templates, partner) belong to
    #: the selected entity's details card, so repeating them as table columns
    #: only crowds the list and forces horizontal scrolling.
    COLUMN_KEYS = (
        "gui.col_ids",
        "gui.col_family",
        "gui.col_summary",
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows = []
        self._records = ()

    # -- population -------------------------------------------------------

    def set_configuration(self, configuration) -> None:
        """Project ``configuration`` (or clear when it is ``None``).

        Reads ``configuration.records`` in order and stores the tuple it saw;
        it never writes to the configuration.
        """
        self.beginResetModel()
        if configuration is None:
            self._rows = []
            self._records = ()
        else:
            self._records = configuration.records
            self._rows = [
                describe_entity(configuration, record) for record in configuration.records
            ]
        self.endResetModel()

    @property
    def rows(self):
        return tuple(self._rows)

    @property
    def records(self):
        """The record tuple this model projected, for order assertions."""
        return self._records

    def row_at(self, index: int):
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

    def row_for_record_key(self, record_key):
        """The row whose primary identifier (or any of its ids) is ``key``."""
        if not record_key:
            return -1
        for position, row in enumerate(self._rows):
            if row.record_key == record_key:
                return position
        for position, row in enumerate(self._rows):
            if record_key in row.ids.split(", "):
                return position
        return -1

    # -- QAbstractTableModel ---------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMN_KEYS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == Qt.DisplayRole:
            return (
                row.ids,
                row.family,
                row.summary,
            )[column]
        if role == Qt.UserRole:
            return row.record_key
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _text(self.COLUMN_KEYS[section])
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return str(section + 1)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


# -- findings projection ------------------------------------------------------------


def _finding_record_key(finding):
    """The entity a finding names, or ``None`` when it names no record."""
    for path in getattr(finding, "paths", ()) or ():
        key = getattr(path, "record_key", None)
        if key:
            return key
    return None


class FindingsTableModel(QAbstractTableModel):
    """Validation findings, formatted by the shared presentation layer.

    The rows are ``FindingCard`` values from ``format_findings``: the same
    numbering, severity tokens and wrapping the console prints, so a jump
    reference means the same thing in both front ends.
    """

    COLUMN_KEYS = ("gui.col_number", "gui.col_severity", "gui.col_where", "gui.col_message")

    def __init__(self, parent=None, width=80) -> None:
        super().__init__(parent)
        self._cards = ()
        self._width = width

    def set_findings(self, findings) -> None:
        """Format and show ``findings`` (a service report's own collection)."""
        self.beginResetModel()
        self._cards = format_findings(tuple(findings or ()), width=self._width)
        self.endResetModel()

    @property
    def cards(self):
        return tuple(self._cards)

    def finding_at(self, index: int):
        if 0 <= index < len(self._cards):
            return self._cards[index].finding
        return None

    def record_key_at(self, index: int):
        card = self._cards[index] if 0 <= index < len(self._cards) else None
        return _finding_record_key(card.finding) if card is not None else None

    def detail_at(self, index: int) -> str:
        card = self._cards[index] if 0 <= index < len(self._cards) else None
        if card is None or not card.detail:
            return ""
        return _text("gui.findings_detail") % " ".join(card.detail)

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._cards)

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMN_KEYS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        card = self._cards[index.row()]
        if role == Qt.DisplayRole:
            return (
                str(card.number),
                card.severity_line,
                card.context,
                " ".join(card.lines),
            )[index.column()]
        if role == Qt.ToolTipRole:
            detail = self.detail_at(index.row())
            return detail or None
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _text(self.COLUMN_KEYS[section])
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


# -- status projection --------------------------------------------------------------

# Which registry label each status row carries: ``(row key, registry key)``
# pairs, assembled once — the same shape the console uses
# (``ui/render/menus.py::_STATUS_LABEL_ROWS``). The row keys are the
# *service's* own vocabulary; they are compared, never used to build a
# structure, which is what keeps this clear of the wire-confinement rule
# (plan §10.1). Neither front end decides what "ready" means.
_STATUS_LABEL_ROWS = (
    ("name", "menu.status_name"),
    ("seeds", "menu.status_seeds"),
    ("version", "menu.status_version"),
    ("components", "menu.status_components"),
    ("modifications", "menu.status_modifications"),
    ("msa", "menu.status_msa"),
    ("templates", "menu.status_templates"),
)
_STATUS_LABEL_KEYS = dict(_STATUS_LABEL_ROWS)

_STATE_KEYS = {
    FieldState.DEFAULTED: "menu.status_ok",
    FieldState.PROVIDED: "menu.status_ok",
    FieldState.NONE: "menu.status_absent",
    FieldState.MISSING: "menu.status_missing",
    FieldState.INVALID: "menu.status_invalid",
}

_OPTIONAL_KEYS = ("modifications", "msa", "templates")


def version_text(selection) -> str:
    """A version selection through the model's own fold."""
    return fold_version_selection(
        selection,
        lambda: _text("menu.version_unverified"),
        lambda version: _text("menu.version_pinned") % version,
        lambda evidenced: _text("menu.version_auto"),
    )


def counts_text(counts) -> str:
    counts = counts if isinstance(counts, dict) else {}
    return _text("gui.counts_value") % (
        counts.get("protein", 0),
        counts.get("rna", 0),
        counts.get("dna", 0),
        counts.get("ligand", 0),
    )


def _status_detail(field) -> str:
    """A status row's detail, from the row's own state and value."""
    if field.state in (FieldState.INVALID, FieldState.MISSING):
        return field.message
    if field.key == "components":
        return counts_text(field.value)
    if field.key == "version":
        return version_text(field.value)
    if field.key == "seeds":
        values = field.value if field.value is not None else ()
        return "[%s]" % ", ".join(str(value) for value in values)
    if field.key in _OPTIONAL_KEYS and field.state == FieldState.NONE:
        return _text("menu.status_none")
    if field.value is None:
        return _text("menu.status_none")
    return str(field.value)


class StatusTableModel(QAbstractTableModel):
    """The readiness rows a ``ConfigurationStatus`` already carries."""

    COLUMN_KEYS = ("gui.col_where", "gui.col_severity", "gui.col_message")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fields = ()

    def set_status(self, status) -> None:
        self.beginResetModel()
        self._fields = tuple(status.fields) if status is not None else ()
        self.endResetModel()

    @property
    def fields(self):
        return self._fields

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._fields)

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMN_KEYS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        field = self._fields[index.row()]
        if index.column() == 0:
            return _text(_STATUS_LABEL_KEYS.get(field.key, "menu.status_other"))
        if index.column() == 1:
            state = _text(_STATE_KEYS.get(field.state, "menu.status_absent"))
            if field.state == FieldState.DEFAULTED:
                return "%s %s" % (state, _text("menu.status_automatic"))
            if field.state == FieldState.PROVIDED:
                return "%s %s" % (state, _text("menu.status_provided"))
            return state
        return _status_detail(field)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _text(self.COLUMN_KEYS[section])
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable
