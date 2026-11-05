"""Direct module execution: ``python -m configbuilder.ui.render.qt``.

Delegates to the one launcher in ``application``; the console's own
``__main__`` keeps its separate delegation to ``app.cli``, so neither front
end gains a second orchestration path.
"""

from configbuilder.ui.render.qt.application import main

if __name__ == "__main__":
    raise SystemExit(main())
