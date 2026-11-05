"""Finding formatting (plan §16.6, §18.8 formatting tier).

Findings are grouped by severity, then by the record a ``FieldPath``
points to, each carrying a stable reference number the user can type to
jump straight to that field's prompt. Severity is a word and a symbol;
technical details are held behind a per-finding key rather than printed
inline. Finding text comes from the rule messages — no internal names,
no wire field names (plan §18.8: the meta-test enforces it).
"""

from __future__ import annotations

from configbuilder.ui.present.labels import (
    finding_context_label,
    general_finding_context,
    severity_label,
)
from configbuilder.ui.present.layout import reflow

__all__ = [
    "FindingCard",
    "format_findings",
    "group_findings",
]


class FindingCard:
    """One displayable finding: its reference number, grouped context,
    the user-facing lines, and the technical detail kept behind ``t``."""

    __slots__ = ("number", "severity_line", "context", "lines", "detail", "finding")

    def __init__(self, number, severity_line, context, lines, detail, finding) -> None:
        self.number = number
        self.severity_line = severity_line
        self.context = context
        self.lines = tuple(lines)
        self.detail = tuple(detail)
        self.finding = finding

    def __repr__(self) -> str:
        return "FindingCard(%d, %s)" % (self.number, self.severity_line)


def group_findings(findings):
    """Findings grouped by severity, then by record context, in stable
    order. Returns ``((severity_name, (finding, ...)), ...)`` with
    severities in ERROR, WARNING, INFO order."""
    order = ["ERROR", "WARNING", "INFO"]
    by_severity = {}
    for finding in findings:
        name = finding.severity.name if hasattr(finding.severity, "name") else str(finding.severity)
        by_severity.setdefault(name, []).append(finding)
    groups = []
    for name in order:
        bucket = by_severity.get(name, ())
        if not bucket:
            continue
        by_context = {}
        for finding in bucket:
            context = _context_key(finding)
            by_context.setdefault(context, []).append(finding)
        groups.append((name, tuple(by_context.items())))
    return tuple(groups)


def format_findings(findings, width: int = 80) -> tuple:
    """The findings list as numbered cards, ready to print.

    Every card's number is the jump-to-field token (plan §16.6); the
    lines fit ``width``; the technical detail is carried separately so
    the renderer can put it behind ``t``.
    """
    cards = []
    number = 0
    for severity_name, contexts in group_findings(findings):
        for _context_key, context_findings in contexts:
            for finding in context_findings:
                number += 1
                paths = tuple(getattr(finding, "paths", ()) or ())
                context = (
                    finding_context_label(paths[0])
                    if paths
                    else _fallback_context(finding)
                )
                cards.append(
                    FindingCard(
                        number=number,
                        severity_line=severity_label(finding.severity),
                        context=context,
                        lines=reflow([finding.user_message], width),
                        detail=_detail_lines(finding, width),
                        finding=finding,
                    )
                )
    return tuple(cards)


def _detail_lines(finding, width: int) -> tuple:
    """The technical detail block: the rule id, the diagnostic, and the
    suggestion — what ``t`` reveals (plan §16.6)."""
    parts = []
    rule_id = getattr(finding, "rule_id", "")
    if rule_id:
        parts.append("rule %s" % rule_id)
    diagnostic = getattr(finding, "diagnostic", "")
    if diagnostic:
        parts.append(diagnostic)
    suggestion = getattr(finding, "suggestion", "")
    if suggestion:
        parts.append("suggestion: %s" % suggestion)
    return reflow(parts, width) if parts else ()


def _context_key(finding) -> str:
    paths = tuple(getattr(finding, "paths", ()) or ())
    if paths:
        return finding_context_label(paths[0])
    return _fallback_context(finding)


def _fallback_context(finding) -> str:
    """A finding whose rule emitted no locator still needs a grouping
    context; the header comes from the string registry."""
    return general_finding_context()
