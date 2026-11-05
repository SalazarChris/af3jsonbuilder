"""Terminal rendering (plan §5.1, §5.3 rule 9, §16.7).

The only ``ui`` family that may read or write a stream, consult the
environment, or branch on the host platform. One front end drives the
menu over one console abstraction: the real terminal (``Console``) and
the scripted one the tests and snapshots use (``ScriptedConsole``).
"""

from configbuilder.ui.render.console import Console, ScriptedConsole, make_console

__all__ = [
    "Console",
    "ScriptedConsole",
    "make_console",
]
