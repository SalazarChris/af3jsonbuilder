"""Direct module execution: ``python -m configbuilder``.

A thin delegation to the one console entry point (``app.cli.main``) — no
second orchestration exists here. Under ``python -m`` the package's own
``__main__`` module runs, so ``configbuilder.app.cli`` would import as
``__main__`` and execute twice without this indirection.
"""

from configbuilder.app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
