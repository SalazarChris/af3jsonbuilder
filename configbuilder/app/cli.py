"""The console entry point (plan §5 architecture map: one console entry point;
packaging declared in ``pyproject.toml`` as ``configbuilder.app.cli:main``).

This module is the **composition root** of the console application, not an
application-domain module: it builds the standard service wiring once, hands
it to the menu (``ui.render.menus.MenuApp``), and returns the session
status. There is one front end: the menu's six goal-oriented actions
(edit, review, variants, generate, open saved work, import).

Importing ``ui`` from here is the single, designated exception to plan §5.3
rule 6: an entry point is a composition root, not an ordinary ``app`` module.
``tests/architecture/test_dependency_rules.py`` names this module explicitly
as the only such exception and guards what it may import.
"""

from __future__ import annotations

from configbuilder.ui.render.console import Console
from configbuilder.ui.render.menus import MenuApp
from configbuilder.ui.services import build_services

__all__ = ["main"]


def main() -> int:
    """Compose the application and run the interactive builder.

    Returns 0 for every deliberate end (exit choice, quit word, Ctrl+C,
    EOF) — the builder reports per-operation outcomes itself, so no
    second status system is invented here.
    """
    services = build_services()
    return MenuApp(services, Console()).run()


if __name__ == "__main__":
    raise SystemExit(main())
