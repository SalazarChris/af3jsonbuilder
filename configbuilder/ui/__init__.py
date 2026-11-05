"""Terminal presentation (plan §5.1, §16).

``ui/render`` is the one front end — ``menus.py`` drives the application
over a ``Console`` — and it is the only family that reads or writes a
stream. ``ui/present`` is formatting and label resolution, with no I/O.
The re-exports below exist so an out-of-tree consumer can reach the
presentation API without naming submodules; the application itself
imports the submodules directly.

The company kept by ``ui``: ``app`` and ``model.traceability`` only
(plan §5.3 rule 6).
"""

from configbuilder.ui.present import (
    FindingCard,
    MINIMUM_WIDTH,
    format_findings,
    label,
    render_sequence_ruler,
    residue_at,
    severity_label,
)
__all__ = [
    "FindingCard",
    "MINIMUM_WIDTH",
    "format_findings",
    "label",
    "render_sequence_ruler",
    "residue_at",
    "severity_label",
]
