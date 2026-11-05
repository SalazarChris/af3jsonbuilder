"""Sequence rendering with human numbering (plan §16.4, §18.8).

The modification-position prompt shows the sequence with a position
ruler: width-sized blocks, 1-based human numbering at both ends of each
line, exactly the format the plan shows. Positions are the domain's own
1-based residue numbers — the user types the number and sees the residue
echoed; no arithmetic is ever shown or requested (plan §16.4).
"""

from __future__ import annotations

from configbuilder.ui.present.layout import MINIMUM_WIDTH
from configbuilder.ui.present.strings import text

__all__ = [
    "DEFAULT_BLOCK",
    "render_sequence_ruler",
    "residue_at",
    "position_range_line",
]


# Block width inside a line at the 80-column minimum, matching the
# plan's example (4 blocks of 10).
DEFAULT_BLOCK = 10


def render_sequence_ruler(sequence: str, width: int = MINIMUM_WIDTH, block: int = DEFAULT_BLOCK) -> tuple:
    """The sequence as ruler lines: ``  <start>  <blocks>  <end>``.

    Line length adapts to ``width`` (blocks per line = whatever fits);
    numbering is 1-based and human (position, not index) at both ends
    of every line. Below the degraded width fewer residues fit per
    line; nothing is ever cut.
    """
    if not sequence:
        return (text("sequence.empty"),)
    gutter = 8  # room for both number columns
    per_line = max(1, ((width - gutter) // (block + 1)) * block) if width > gutter else block
    lines = []
    total = len(sequence)
    start = 0
    while start < total:
        chunk = sequence[start : start + per_line]
        first = start + 1
        last = start + len(chunk)
        body = _blocked(chunk, block)
        lines.append("%6d  %s  %d" % (first, body, last))
        start = last
    return tuple(lines)


def residue_at(sequence: str, position: int):
    """The 1-based residue at ``position``, or ``None`` when out of
    range. This is the echo the position prompt shows (plan §16.4)."""
    if position < 1 or position > len(sequence):
        return None
    return sequence[position - 1]


def position_range_line(sequence: str) -> str:
    """The valid-range hint for a position prompt: ``[1-128]``."""
    return "[1-%d]" % len(sequence)


def _blocked(chunk: str, block: int) -> str:
    return " ".join(chunk[i : i + block] for i in range(0, len(chunk), block))
