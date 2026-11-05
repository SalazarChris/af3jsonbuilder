"""Launching the desktop front end (Stage 1: review & preview).

This is the Qt analogue of ``app/cli.py``: a composition root that builds the
standard service wiring, hands it to the window, and returns the session
status. It sits inside ``ui`` because it is a front end, exactly as the console
entry point does — and it never imports a pipeline stage directly, so the
§5.3 dependency rules hold unchanged.

Launch it with any of:

    python -m configbuilder.ui.render.qt
    python -m configbuilder.ui.render.qt --demo
    python -m configbuilder.ui.render.qt path\\to\\job.json
    af3-json-builder            (installed with the ``gui`` extra)

A path given on the command line is **not** opened silently: the same preview
dialog the window shows is presented first, so the file is committed only
after the user confirms, exactly as when the file is chosen from the toolbar.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from configbuilder.app.paths import preferences_path
from configbuilder.ui.present.strings import text as _text
from configbuilder.ui.render.qt.state import GuiState, build_demo_state
from configbuilder.ui.render.qt.style import apply_application
from configbuilder.ui.render.qt.windows import MainWindow

__all__ = ["build_parser", "configure_logging", "main"]

#: The application logger every module (``configbuilder.*``) reports under.
_LOGGER_NAME = "configbuilder"


def configure_logging(path=None):
    """Send diagnostics to ``%APPDATA%\\AF3Builder\\gui.log``; best effort.

    The window shows the sentence a user can act on; the service's reason, the
    blocking findings and any exception belong in a log file, where a developer
    (or the user sending a report) can read them after the window is closed.
    Lives beside the preferences file, which is user-writable by construction.
    Returns the path written to, or ``None`` when no file could be opened — a
    refused log file must never stop the application from starting.
    """
    if path is None:
        try:
            log_path = Path(preferences_path()).parent / "gui.log"
        except (OSError, ValueError):  # pragma: no cover - defensive
            return None
    else:
        log_path = Path(path)

    logger = logging.getLogger(_LOGGER_NAME)
    for existing in list(logger.handlers):
        if getattr(existing, "af3builder_gui", False):
            logger.removeHandler(existing)
            existing.close()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError:
        return None
    handler.af3builder_gui = True
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return log_path


def build_parser():
    """The launcher's own arguments.

    Qt's own switches are not forwarded: they arrive through the environment
    (``QT_QPA_PLATFORM`` and friends), which is also how the offscreen tests
    run, so the two never fight over the same argv.
    """
    parser = argparse.ArgumentParser(
        prog="af3-json-builder",
        description=_text("gui.cli_description"),
    )
    parser.add_argument("path", nargs="?", default="", help=_text("gui.cli_help_path"))
    parser.add_argument("--demo", action="store_true", help=_text("gui.cli_help_demo"))
    return parser


def main(argv=None) -> int:
    """Compose the application and run the window loop."""
    arguments = build_parser().parse_args(argv)
    # Before anything can refuse: a diagnostic is worth keeping even if the
    # window never appears.
    configure_logging()
    existing = QApplication.instance()
    application = existing if existing is not None else QApplication([sys.argv[0]])
    application.setApplicationName(_text("gui.window_title"))
    # The approved dark workbench, applied to the whole application: a Fusion
    # palette for the native pieces (menus, combo pop-ups, tooltips, message
    # boxes) plus the sheet for the application's own widgets. The window
    # applies the sheet to itself too, so a window built without this call
    # still looks the same.
    apply_application(application)
    state = build_demo_state() if arguments.demo else GuiState()
    window = MainWindow(state)
    window.show()
    if arguments.path and not arguments.demo:
        window.offer_import(arguments.path)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
