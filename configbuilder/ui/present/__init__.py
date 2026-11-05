"""Presentation layer (plan §5.1, §5.3 rule 9, §18.8 formatting tier).

Pure formatting over fixed widths: label resolution through the
traceability registry, width-aware layout with the documented 80/60
degradation ladder, the sequence ruler with human numbering, and
finding formatting with no internal names. No terminal library, no
stream access, no environment consultation — ``ui/render`` does that
(plan §5.3 rule 9).
"""

from configbuilder.ui.present.findings import FindingCard, format_findings, group_findings
from configbuilder.ui.present.labels import (
    SEVERITY_SYMBOLS,
    finding_context_label,
    finding_reference_label,
    label,
    labels,
    mapping_ids,
    severity_label,
    with_record_label,
)
from configbuilder.ui.present.layout import (
    DEGRADED_WIDTH,
    MINIMUM_WIDTH,
    columns_available,
    reflow,
    single_column,
    wrap_to_width,
)
from configbuilder.ui.present.sequence import (
    DEFAULT_BLOCK,
    position_range_line,
    render_sequence_ruler,
    residue_at,
)

__all__ = [
    "DEGRADED_WIDTH",
    "DEFAULT_BLOCK",
    "FindingCard",
    "MINIMUM_WIDTH",
    "SEVERITY_SYMBOLS",
    "columns_available",
    "finding_context_label",
    "finding_reference_label",
    "format_findings",
    "group_findings",
    "label",
    "labels",
    "mapping_ids",
    "position_range_line",
    "reflow",
    "render_sequence_ruler",
    "residue_at",
    "severity_label",
    "single_column",
    "with_record_label",
    "wrap_to_width",
]
