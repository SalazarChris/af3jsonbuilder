"""The one place that shapes the desktop front end's look.

The approved mockup is a dark scientific workbench: a calm charcoal surface, a
slightly darker sidebar, one muted-turquoise accent and generous but even
spacing. This module holds that design system — the colour tokens, the sheet
that applies them, and the small label helpers the pages share — so no page
carries a colour or a metric of its own.

Three rules the sheet follows deliberately:

- **No state is signalled by colour alone.** The accent marks the primary
  action and the current destination; every status that matters ("Ready",
  "Not ready", "Conflict", "Unsaved changes") is also a *word* on screen.
- **Nothing is decorative.** No gradients, no animation, no shadow, no icon
  that replaces a label. Contrast and spacing do the work.
- **The operating system still owns the native bits.** A dark ``Fusion``
  palette (``apply_application``) covers menus, combo pop-ups, tooltips and
  message boxes; the sheet covers the application's own widgets. Both are
  built from the same tokens, so light and dark Windows themes cannot make the
  window unreadable.

A widget asks for a role by property (``role="hint"``, ``role="heading"``,
``role="title"``) or by object name (``sidebar``, ``appHeader``, ``appTitle``).
"""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel

__all__ = [
    "COLORS",
    "SPACING",
    "apply_application",
    "apply_style",
    "breadcrumb_label",
    "caption_label",
    "field_label",
    "heading_label",
    "hint_label",
    "page_title_label",
    "style_sheet",
]

#: The mockup's palette. Names describe purpose, not hue, so a future theme
#: change is a token edit rather than a hunt through QSS strings.
COLORS = {
    "background": "#171B22",
    "surface": "#222A34",
    "surface_alt": "#1E252E",
    "sidebar": "#1C222B",
    "accent": "#75D6D0",
    "accent_text": "#10231F",
    "text": "#D7E0EA",
    "muted": "#9AA8B8",
    "border": "#394351",
    "header": "#1F262F",
    # A restrained amber, used only beside the word "blocking".
    "warning": "#E0B27A",
}

#: The spacing scale (px). Every margin and gap in the sheet is one of these.
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}

_TEMPLATE = Template("""
QMainWindow, QDialog {
    background-color: $background;
}
QWidget {
    color: $text;
    font-size: 9.5pt;
}
QFrame#appHeader {
    background-color: $header;
    border-bottom: 1px solid $border;
    padding: 0;
}
QLabel#appBadge {
    background-color: #152926;
    border: 1px solid #2B4E4A;
    border-radius: 8px;
}
QLabel#appTitle {
    font-size: 12pt;
    font-weight: 600;
    color: $text;
}
QLabel#appSubtitle {
    color: $muted;
    font-size: 8.5pt;
}
QLabel#headerJob {
    color: $muted;
    padding-right: 12px;
}
QLabel#statePill {
    color: $muted;
    border: 1px solid $border;
    border-radius: 9px;
    padding: 2px 10px;
    font-size: 8.5pt;
}
QLabel#statePill[state="dirty"] {
    color: $accent;
    border-color: $accent;
}
QWidget#sidebarPanel {
    background-color: $sidebar;
    border-right: 1px solid $border;
}
QLabel#sidebarCaption {
    color: $muted;
    font-size: 7.5pt;
    letter-spacing: 1.4px;
    padding: 12px 14px 4px 14px;
}
QListWidget#sidebar {
    background-color: transparent;
    border: none;
    outline: none;
    padding: 0 8px 4px 8px;
}
QListWidget#sidebar::item {
    color: $text;
    padding: 8px 8px;
    border-radius: 6px;
    margin: 1px 0;
}
QListWidget#sidebar::item:hover {
    background-color: $surface_alt;
}
QListWidget#sidebar::item:selected {
    background-color: $surface;
    color: $accent;
}
QListWidget#sidebar::item:focus {
    border: 1px solid rgba(117, 214, 208, 90);
}
QGroupBox {
    font-weight: 600;
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 1.05em;
    padding: $padding;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: $text;
}
QLabel[role="title"] {
    font-size: 15pt;
    font-weight: 600;
}
QLabel[role="heading"] {
    font-weight: 600;
}
QLabel[role="hint"] {
    color: $muted;
}
QLabel[role="breadcrumb"] {
    color: $muted;
    font-size: 7.5pt;
    letter-spacing: 1.4px;
}
QLabel[role="fieldLabel"] {
    color: $muted;
    font-size: 7.5pt;
    letter-spacing: 1.1px;
}
QLabel[role="caption"] {
    color: $muted;
    font-size: 8.5pt;
}
QLabel[role="warning"] {
    color: $warning;
    font-size: 8.5pt;
}
QLabel#nextStepIcon {
    color: $muted;
    border: 1px solid $muted;
    border-radius: 10px;
    font-weight: 600;
}
QLabel[role="statValue"] {
    font-size: 17pt;
    font-weight: 600;
}
QLabel[role="statState"] {
    font-size: 11.5pt;
    font-weight: 600;
}
QFrame#card, QFrame#statCard, QFrame#nextStepCard {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 8px;
}
QPushButton[role="quiet"] {
    background: transparent;
    border: none;
    color: $muted;
    padding: 2px 4px;
}
QPushButton[role="choice"] {
    background-color: $surface_alt;
    text-align: left;
    padding: 9px 14px;
    font-weight: 600;
}
QPushButton[role="choice"]:hover {
    color: $accent;
    border-color: $accent;
}
QPushButton[role="quiet"]:hover {
    color: $accent;
}
QPushButton[role="quiet"]:disabled {
    color: $border;
}
QPushButton {
    background-color: $surface_alt;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 20px;
}
QPushButton:hover {
    border-color: $accent;
}
QPushButton:default, QPushButton[role="primary"] {
    background-color: $accent;
    color: $accent_text;
    border-color: $accent;
    font-weight: 600;
}
QPushButton:disabled {
    color: $muted;
    border-color: $border;
    background-color: $surface;
}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background-color: $surface_alt;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 9px;
    min-height: 20px;
    selection-background-color: $accent;
    selection-color: $accent_text;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-color: $accent;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox QAbstractItemView {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    selection-background-color: $surface_alt;
    selection-color: $accent;
}
QTableView, QTableWidget {
    background-color: $surface_alt;
    alternate-background-color: $surface;
    gridline-color: $border;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
}
QTableView::item:selected, QTableWidget::item:selected {
    background-color: $surface;
    color: $accent;
}
QHeaderView::section {
    background-color: $surface;
    color: $muted;
    padding: 6px 8px;
    font-weight: 600;
    border: none;
    border-right: 1px solid $border;
    border-bottom: 1px solid $border;
}
QTabWidget::pane {
    border: 1px solid $border;
    border-radius: 6px;
    top: -1px;
    background-color: $surface;
}
QTabBar::tab {
    background: transparent;
    color: $muted;
    padding: 7px 14px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    color: $accent;
    border-color: $border;
    background-color: $surface;
}
QTabBar::tab:hover {
    color: $text;
}
QSplitter::handle {
    background-color: $border;
}
QSplitter::handle:hover {
    background-color: $accent;
}
QToolBar#commandBar {
    background-color: $header;
    border-bottom: 1px solid $border;
    padding: 6px 18px;
    spacing: 6px;
}
QFrame#emptyState {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 8px;
}
QLabel#emptyTitle {
    font-size: 15pt;
    font-weight: 600;
}
QLabel#emptyBody {
    color: $muted;
}
QToolBar {
    background-color: $header;
    border-bottom: 1px solid $border;
    padding: 4px 8px;
    spacing: 6px;
}
QToolButton {
    background-color: $surface_alt;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 5px 12px;
}
QToolButton:hover {
    border-color: $accent;
}
QMenuBar, QMenu {
    background-color: $header;
    color: $text;
}
QMenu::item:selected {
    background-color: $surface;
    color: $accent;
}
QStatusBar {
    background-color: $header;
    color: $muted;
    border-top: 1px solid $border;
}
QScrollArea {
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: $border;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: $muted;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: $border;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: $muted;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
QToolTip {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
}
""")

_STYLE_SHEET = _TEMPLATE.substitute(padding="14px 16px 14px 16px", **COLORS)


def style_sheet() -> str:
    """The application's style sheet (a string; nothing is applied here)."""
    return _STYLE_SHEET


def apply_style(widget) -> None:
    """Apply the sheet to ``widget``'s subtree (and its child dialogs)."""
    widget.setStyleSheet(style_sheet())


def _palette() -> QPalette:
    """A dark palette built from the same tokens, for the native widgets."""
    palette = QPalette()
    background = QColor(COLORS["background"])
    surface = QColor(COLORS["surface"])
    text = QColor(COLORS["text"])
    muted = QColor(COLORS["muted"])
    accent = QColor(COLORS["accent"])
    accent_text = QColor(COLORS["accent_text"])
    palette.setColor(QPalette.Window, background)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, surface)
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["surface_alt"]))
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, surface)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, accent)
    palette.setColor(QPalette.ToolTipBase, surface)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Highlight, accent)
    palette.setColor(QPalette.HighlightedText, accent_text)
    palette.setColor(QPalette.Link, accent)
    palette.setColor(QPalette.PlaceholderText, muted)
    palette.setColor(QPalette.Disabled, QPalette.Text, muted)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, muted)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, muted)
    return palette


def apply_application(application) -> None:
    """Give the whole application the dark workbench look.

    ``Fusion`` is used because it renders the palette consistently on every
    Windows version; the sheet then styles the application's own widgets. The
    window applies the sheet to itself as well, so a window built in a test
    (with no ``apply_application`` call) still looks the same.
    """
    try:
        application.setStyle("Fusion")
    except (AttributeError, RuntimeError):  # pragma: no cover - platform guard
        pass
    application.setPalette(_palette())
    application.setStyleSheet(style_sheet())


def _role_label(text: str, role: str, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", role)
    if wrap:
        label.setWordWrap(True)
    return label


def page_title_label(text: str) -> QLabel:
    """A page's own title: the largest text inside a destination."""
    return _role_label(text, "title")


def heading_label(text: str) -> QLabel:
    """A small bold section label inside a workspace."""
    return _role_label(text, "heading")


def breadcrumb_label(text: str) -> QLabel:
    """The small uppercase trail above a page title (mockup: WORKSPACE / …)."""
    return _role_label(text, "breadcrumb")


def field_label(text: str) -> QLabel:
    """A form field's small uppercase label."""
    return _role_label(text, "fieldLabel")


def caption_label(text: str = "", wrap: bool = False) -> QLabel:
    """A quiet line under a value: default/changed markers, counts, detail."""
    return _role_label(text, "caption", wrap=wrap)


def hint_label(text: str) -> QLabel:
    """A wrapped explanatory label in the muted secondary style.

    The role is a *property*, not a colour on the widget, so the wording stays
    readable in either Windows theme; the label is never the only signal for a
    state.
    """
    return _role_label(text, "hint", wrap=True)
