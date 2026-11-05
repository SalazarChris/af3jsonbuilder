"""Root-level convenience launcher for the interactive console builder.

Run the builder straight from a checkout with the plain project
interpreter::

    python af3builder.py

This is a deliberate two-line delegation to the **one** existing entry
point, ``configbuilder.app.cli.main`` (also published as the
``configbuilder`` console script and reachable as
``python -m configbuilder``). No menu wording, builder logic, validation or
service wiring lives here -- the launcher exists only so the application
starts from a memorable command in the repository root, and it returns
whatever exit status the application itself returns.

The core application has no runtime dependencies, so this launcher needs
neither PySide6 nor the optional ``gui`` extra. Importing this module is
side-effect free: the interactive menu starts only under the ``__main__``
guard below, never on import.
"""

from __future__ import annotations

from configbuilder.app import cli

__all__ = ["main"]


def main() -> int:
    """Start the interactive builder through the existing composition root.

    Delegates to ``configbuilder.app.cli.main`` exactly once and passes its
    result straight back, so the launcher never invents a second status
    system of its own.
    """
    return cli.main()


if __name__ == "__main__":
    raise SystemExit(main())
