"""The JSON Preview page: the builder's generated JSON, read-only.

The text comes from ``GenerationService.show_json`` — the same ``to_wire`` →
``encode`` path a save would use, so what the window shows is exactly what the
builder would write. This page has no save, overwrite, generate or execute
button, and writes nothing: Stage 1 is a review window.

When the service refuses to produce a document (a job that is not ready, or a
feature above the pinned version) it returns a reason instead of raising; the
reason is displayed verbatim rather than being swallowed or crashing.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.qt.models import fixed_font
from configbuilder.ui.render.qt.style import page_title_label

__all__ = ["PreviewPage"]


class PreviewPage(QWidget):
    """Read-only view of the generated JSON for the open job."""

    def __init__(self, state, notify=None, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._notify = notify if notify is not None else (lambda message: None)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(page_title_label(_text("gui.preview_title")))
        readonly = QLabel(_text("gui.preview_title_note"))
        readonly.setProperty("role", "hint")
        header.addWidget(readonly)
        header.addStretch(1)
        # Copy and Refresh are labelled buttons beside the text they act on;
        # Copy is disabled while there is nothing to copy.
        self._copy_button = QPushButton(_text("gui.preview_copy"))
        self._copy_button.clicked.connect(self.copy_text)
        self._copy_button.setEnabled(False)
        self._refresh_button = QPushButton(_text("gui.preview_refresh"))
        self._refresh_button.clicked.connect(self.refresh)
        header.addWidget(self._copy_button)
        header.addWidget(self._refresh_button)
        note = QLabel(_text("gui.preview_note"))
        note.setWordWrap(True)
        self._reason = QLabel()
        self._reason.setWordWrap(True)
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setFont(fixed_font())
        self._editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addLayout(header)
        layout.addWidget(note)
        layout.addWidget(self._reason)
        layout.addWidget(self._editor, 1)

    def copy_text(self) -> str:
        """Copy exactly the text on screen; nothing is regenerated for it."""
        text = self._editor.toPlainText()
        if not text:
            return ""
        QGuiApplication.clipboard().setText(text)
        self._notify(_text("gui.preview_copied"))
        return text

    def refresh(self) -> None:
        """Ask the service for the current text; display it or its reason."""
        text, reason = self._state.preview_json(None)
        self._copy_button.setEnabled(text is not None and bool(text))
        if text is not None:
            self._editor.setPlainText(text)
            self._reason.setText("")
            self._reason.setVisible(False)
            return
        self._editor.setPlainText("")
        self._reason.setText(
            "%s\n%s" % (_text("gui.preview_unavailable"), _text("menu.import_reason") % reason)
        )
        self._reason.setVisible(True)

    @property
    def editor(self):
        """The read-only editor, for tests to read back what is displayed."""
        return self._editor

    def reason_text(self) -> str:
        """The refusal the service gave, as displayed (empty when it worked)."""
        return self._reason.text()
