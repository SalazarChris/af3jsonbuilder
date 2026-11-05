"""The console abstraction (plan §5.3 rule 9: only ``ui/render`` may
read or write a stream).

The menu speaks to a ``Console``, never to ``sys`` directly, so
scripted-stdin tests drive the whole workflow and snapshot the
transcript without a terminal (plan §18.8). Generated files are
unaffected by any of this — their bytes are fixed by ``serialize``
(plan §16.10).
"""

from __future__ import annotations

import io
import sys

from configbuilder.ui.present.strings import text as _text

__all__ = ["Console", "ScriptedConsole", "make_console"]


def _survive_the_streams_codec(stream, errors: str) -> None:
    """Stop a code page from ending the session.

    A terminal's or a pipe's encoding is not the application's business.
    Writing a glyph the code page lacks (``\u2192`` on cp1252, any emoji on a
    legacy console) used to raise ``UnicodeEncodeError`` out of
    ``write_line`` and kill the session, and a byte the *input* codec cannot
    decode did the same on the way in. Redirected output takes the ANSI code
    page on Windows, so this is ordinary, not exotic.

    Output becomes ``replace``: an unprintable glyph shows as ``?`` rather
    than aborting. Input becomes ``surrogateescape`` (the platform's own
    choice for redirected input): undecodable bytes survive as themselves
    instead of raising, and the app's echo of them encodes back to the same
    bytes.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return  # StringIO, a mock, a closed stream: nothing to configure
    try:
        reconfigure(errors=errors)
    except (ValueError, OSError, AttributeError, TypeError):
        pass


class Console:
    """Real-stream console. The only class in the codebase that talks
    to a terminal's stdin/stdout."""

    def __init__(self, stdin=None, stdout=None) -> None:
        # Only the *default* streams are reconfigured: a caller that hands
        # in its own stream keeps full control of it (the scripted console
        # and the tests rely on that).
        if stdin is None:
            _survive_the_streams_codec(sys.stdin, "surrogateescape")
        if stdout is None:
            _survive_the_streams_codec(sys.stdout, "replace")
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout

    def write_line(self, text: str = "") -> None:
        self.stdout.write(text + "\n")

    def ask(self, prompt_text: str, field=None) -> str:
        """Field-aware ask: this console has no input extras, so
        ``field`` (the asking field, when there is one) is accepted and
        ignored — path completion lives in the menu's own picker."""
        return self.prompt(prompt_text)

    def prompt(self, text: str) -> str:
        """One line of input; the prompt text is shown first."""
        self.stdout.write(text)
        self.stdout.flush()
        line = self.stdin.readline()
        if line == "":  # EOF: never loop forever on a closed stream
            raise EOFError(_text("console.eof"))
        return line.rstrip("\n")

    def read_multiline(self, instructions: str, terminator: str = "") -> bytes:
        """Multi-line input until a blank line (the documented finish
        for the paste route when bracketed paste is unavailable). The
        bytes between the lines are preserved exactly."""
        self.stdout.write(instructions)
        self.stdout.flush()
        collected = []
        while True:
            line = self.stdin.readline()
            if line == "":
                break  # EOF terminates a paste too — never hangs
            if line.rstrip("\r\n") == terminator:
                break
            collected.append(line)
        return "".join(collected).encode("utf-8")


class ScriptedConsole(Console):
    """A console fed by a script of input lines, capturing all output —
    the §18.8 snapshot harness, no terminal needed.

    The input side is a chunk queue, not a shared cursor: ``feed_multiline``
    appends a paste after the scripted lines, so a test can script the
    menu choice and then feed the pasted content.
    """

    def __init__(self, script) -> None:
        self._chunks = ["".join(line + "\n" for line in script)]
        self._output = io.StringIO()
        super().__init__(self, self._output)

    # -- the read side (passed to Console as ``stdin``) -----------------

    def readline(self) -> str:
        while len(self._chunks) > 1 and self._chunks[0] == "":
            self._chunks.pop(0)  # a consumed remainder is not a line
        if not self._chunks or self._chunks[0] == "":
            return ""  # script exhausted: EOF, and never a hang
        return self._read_from(0)

    def _read_from(self, _chunk_index: int) -> str:
        chunk = self._chunks[0]
        newline = chunk.find("\n")
        if newline == -1:
            self._chunks.pop(0)  # a chunk with no newline is a final line
            return chunk
        self._chunks[0] = chunk[newline + 1 :]
        return chunk[: newline + 1]

    # -- the write side -------------------------------------------------

    @property
    def transcript(self) -> str:
        return self._output.getvalue()

    def feed_multiline(self, text: str) -> None:
        """Push multi-line content into the input queue (a paste)."""
        self._chunks.append(text)


def make_console(scripted=None):
    """A real console, or a scripted one for tests."""
    if scripted is None:
        return Console()
    return ScriptedConsole(scripted)
