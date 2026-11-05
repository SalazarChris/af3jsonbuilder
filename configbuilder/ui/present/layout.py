"""Width-aware layout (plan §16.9, §18.8 formatting tier).

All layout is computed for a measured width with a documented minimum
of 80 columns; between 60 and 80 the layout degrades to single-column
without losing content; below 60 content is wrapped harder but nothing
is cut. Every function here is pure: text in, text out — the renderers
decide what happens to the lines.
"""

from __future__ import annotations

import textwrap

__all__ = [
    "MINIMUM_WIDTH",
    "DEGRADED_WIDTH",
    "wrap_to_width",
    "reflow",
    "single_column",
    "columns_available",
]


MINIMUM_WIDTH = 80  # the documented supported minimum (plan §16.9)
DEGRADED_WIDTH = 60  # below this the layout degrades further


def wrap_to_width(text: str, width: int, subsequent_indent: str = "") -> tuple:
    """Wrap ``text`` to ``width``, returning lines. Pure.

    Degradation, never failure: below the 80-column minimum the text is
    wrapped harder; nothing is cut or truncated.
    """
    if width < 1:
        width = 1
    return tuple(
        textwrap.wrap(
            text,
            width=width,
            initial_indent="",
            subsequent_indent=subsequent_indent,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=True,
        )
        or [""]
    )


def reflow(paragraphs, width: int) -> tuple:
    """Wrap each paragraph separately; blank paragraphs are separators.

    Used for finding text and help text so the renderer receives
    ready-to-print lines regardless of terminal width.
    """
    lines = []
    for index, paragraph in enumerate(paragraphs):
        if not paragraph:
            lines.append("")
            continue
        if index:
            lines.append("")
        lines.extend(wrap_to_width(paragraph, width))
    return tuple(lines)


def single_column(width: int) -> bool:
    """True when the width permits only the degraded single-column
    layout (plan §16.9: between 60 and 80)."""
    return width < MINIMUM_WIDTH


def columns_available(width: int, count: int, gutter: int = 2) -> int:
    """Width available to each of ``count`` columns, or 0 when the
    width cannot usefully hold them (the caller degrades to one
    column). The gutter between columns is accounted for."""
    if count < 1:
        return width
    usable = width - gutter * (count - 1)
    if usable < count:  # not even one character per column
        return 0
    return usable // count
