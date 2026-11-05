"""Root-level launcher for the optional PySide6 desktop front end.

PySide6 is deliberately *not* a dependency of the core package, so the
desktop front end lives in its own environment (``.venv-gui``, created from
the ``gui`` extra). This launcher is the one-line bridge between the plain
project interpreter and that environment::

    python gui.py                       # empty window -> "Open AF3 JSON..."
    python gui.py --demo                # built-in sample job
    python gui.py "C:\\path\\to\\job with spaces.json"
    python gui.py --help

It runs the existing module ``configbuilder.ui.render.qt`` (never a
re-implementation of it) as::

    <repo-root>\\.venv-gui\\Scripts\\python.exe -m configbuilder.ui.render.qt <your args...>

Every argument is forwarded unchanged, as its own list element, with no
shell involved, so a JSON path containing spaces stays a single argument.
The child starts with the repository root as its working directory, so the
command behaves identically whether it is typed here or run by full path
from somewhere else.

If ``.venv-gui`` has not been created yet the launcher prints copyable setup
commands and exits non-zero *without* trying to start anything. It never
falls back to another interpreter, never installs anything, and never edits
the GUI itself -- a missing dependency is reported with the child's own
diagnostic and its exit code.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__ = [
    "GUI_MODULE",
    "VENV_DIRECTORY",
    "build_command",
    "gui_python",
    "main",
    "missing_environment_message",
    "repository_root",
    "setup_commands",
]

#: The existing GUI module -- launched, never duplicated.
GUI_MODULE = "configbuilder.ui.render.qt"

#: Canonical complete local-builder environment created by setup_windows.bat.
VENV_DIRECTORY = ".venv"

#: Older checkouts may still have the GUI-only environment; keep it as fallback.
LEGACY_VENV_DIRECTORY = ".venv-gui"

_IS_WINDOWS = os.name == "nt"

#: The child could not even be started, so there is nothing to propagate.
EXIT_NO_ENVIRONMENT = 1


def repository_root() -> Path:
    """Discover the checkout this launcher lives in.

    The root is the directory holding this file, resolved to an absolute
    path so it is correct even when ``gui.py`` is invoked by its full path
    from another working directory. Nothing is hard-coded to a user's
    machine.
    """
    return Path(__file__).resolve().parent


def gui_python(root=None) -> Path:
    """The interpreter of the isolated GUI environment.

    ``<root>/.venv-gui/Scripts/python.exe`` on Windows,
    ``<root>/.venv-gui/bin/python`` elsewhere.
    """
    base = Path(root) if root is not None else repository_root()
    executable = "python.exe" if _IS_WINDOWS else "python"
    scripts_name = "Scripts" if _IS_WINDOWS else "bin"
    canonical = base / VENV_DIRECTORY / scripts_name / executable
    if canonical.is_file():
        return canonical
    legacy = base / LEGACY_VENV_DIRECTORY / scripts_name / executable
    return legacy


def build_command(args=(), python=None):
    """Build the exact child argv, one list element per argument.

    No string concatenation, no quoting and no ``shell=True``: a caller's
    argument (a path with spaces, an option) is passed through verbatim.
    """
    interpreter = Path(python) if python is not None else gui_python()
    return [str(interpreter), "-m", GUI_MODULE, *(str(argument) for argument in args)]


def setup_commands(root=None) -> list:
    """The copyable commands that create the complete local-builder environment."""
    if _IS_WINDOWS:
        create = "py -3 -m venv %s" % VENV_DIRECTORY
        interpreter = Path(VENV_DIRECTORY) / "Scripts" / "python.exe"
    else:
        create = "python3 -m venv %s" % VENV_DIRECTORY
        interpreter = Path(VENV_DIRECTORY) / "bin" / "python"
    install = '%s -m pip install -e ".[gui,templates]"' % interpreter
    return [create, install]


def missing_environment_message(root=None, python=None) -> str:
    """Actionable, copyable instructions for a checkout with no ``.venv-gui``."""
    base = Path(root) if root is not None else repository_root()
    interpreter = Path(python) if python is not None else gui_python(base)
    create, install = setup_commands(base)
    return "\n".join(
        [
            "gui.py: the GUI environment was not found -- the desktop front end",
            "is optional and lives in its own environment.",
            "",
            "Expected interpreter:",
            "  %s" % interpreter,
            "",
            "Create it and install the local GUI and structural-template extras from the repository root:",
            "",
            "  %s" % create,
            "  %s" % install,
            "",
            "Then run:  python gui.py",
        ]
    )


def main(argv=None, runner=None) -> int:
    """Start the GUI in ``.venv-gui`` and return its exit code.

    ``argv`` defaults to this process's own arguments (``sys.argv[1:]``) and
    is forwarded unchanged. ``runner`` is the subprocess callable and exists
    so the unit tests can observe the command, its working directory and its
    exit status without ever opening a window; production uses
    :func:`subprocess.run`.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = repository_root()
    interpreter = gui_python(root)

    if not interpreter.exists():
        print(missing_environment_message(root, interpreter), file=sys.stderr)
        return EXIT_NO_ENVIRONMENT

    if runner is None:
        runner = subprocess.run

    completed = runner(build_command(arguments, interpreter), cwd=str(root))
    status = getattr(completed, "returncode", 1)

    if status:
        create, install = setup_commands(root)
        print(
            "gui.py: the GUI process exited with status %s. If a dependency is "
            "missing, install the complete local builder into %s:\n\n  %s\n  %s"
            % (status, VENV_DIRECTORY, create, install),
            file=sys.stderr,
        )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
