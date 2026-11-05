"""Finding and report vocabulary (IMPLEMENTATION_PLAN.md §9.4).

A ``Finding`` is the only way a rule reports; rules never raise for a
condition the *user* can fix — exceptions are reserved for programmer or
environment errors. ``FieldPath`` is the canonical locator for everything
a front end can jump to (plan §11: "jump-to-field from every FieldPath
variant"), and it carries a traceability-registered type name so the UI can
label the target without ever seeing a raw internal class name (plan §3.1).
"""

from __future__ import annotations

from configbuilder.validation.catalogue import Rule, Severity

__all__ = ["FieldPath", "Finding", "Report"]


class FieldPath:
    """A canonical, hashable locator: the type whose UI label names the
    context, the record key it belongs to (or ``None``), and the wire/model
    field within it. Equality and hashing are by value so findings can be
    deduplicated and jumped to.

    The ``type_name`` must be registered in the traceability registry
    (``label_for``); a locator with a label-less type is a programming
    error and is rejected here rather than producing a broken UI link.
    """

    __slots__ = ("type_name", "record_key", "field")

    def __init__(self, type_name: str, record_key=None, field: str = "") -> None:
        if not isinstance(type_name, str) or not type_name:
            raise ValueError("FieldPath requires a type name")
        from configbuilder.model.traceability import label_for

        label_for(type_name)  # raises KeyError for unregistered types
        object.__setattr__(self, "type_name", type_name)
        object.__setattr__(self, "record_key", record_key)
        object.__setattr__(self, "field", field)

    def __setattr__(self, name, value):
        raise AttributeError("FieldPath is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FieldPath):
            return (
                self.type_name == other.type_name
                and self.record_key == other.record_key
                and self.field == other.field
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("FieldPath", self.type_name, self.record_key, self.field))

    def __repr__(self) -> str:
        return "FieldPath(%r, record_key=%r, field=%r)" % (
            self.type_name,
            self.record_key,
            self.field,
        )


class Finding:
    """One rule outcome: what the user sees, what the machine knows."""

    __slots__ = ("rule_id", "severity", "user_message", "diagnostic", "suggestion", "paths")

    def __init__(
        self,
        rule_id: str,
        severity: Severity,
        user_message: str,
        diagnostic: str,
        paths: tuple = (),
        suggestion: str = "",
    ) -> None:
        from configbuilder.validation.catalogue import get_rule

        rule = get_rule(rule_id)
        if rule is None:
            raise ValueError("finding references unknown rule %r" % rule_id)
        if not isinstance(severity, Severity):
            raise ValueError("finding severity must be a Severity")
        if not user_message or not user_message.strip():
            raise ValueError("a finding requires a user-facing message")
        self.rule_id = rule_id
        self.severity = severity
        self.user_message = user_message
        self.diagnostic = diagnostic
        self.suggestion = suggestion
        self.paths = tuple(paths)

    def __repr__(self) -> str:
        return "Finding(%r, %s, %r)" % (self.rule_id, self.severity.value, self.user_message)


class Report:
    """An ordered, deduplicated set of findings with tier bookkeeping."""

    def __init__(self) -> None:
        self._findings: list = []
        self._seen: set = set()
        self._skipped: list = []

    def add(self, finding: Finding) -> None:
        key = (finding.rule_id, finding.user_message, finding.paths)
        if key not in self._seen:
            self._seen.add(key)
            self._findings.append(finding)

    def add_all(self, findings) -> None:
        for finding in findings:
            self.add(finding)

    def mark_skipped(self, rule: Rule, reason: str) -> None:
        """A rule that could not run is recorded — never silently green
        (plan §9.2)."""
        self._skipped.append((rule.rule_id, reason))

    @property
    def findings(self) -> tuple:
        return tuple(self._findings)

    @property
    def skipped(self) -> tuple:
        return tuple(self._skipped)

    def errors(self) -> tuple:
        return tuple(f for f in self._findings if f.severity is Severity.ERROR)

    def warnings(self) -> tuple:
        return tuple(f for f in self._findings if f.severity is Severity.WARNING)

    def blocking(self) -> tuple:
        """Findings that stop generation: every ERROR."""
        return self.errors()

    def __len__(self) -> int:
        return len(self._findings)

    def __iter__(self):
        return iter(self._findings)

    def __bool__(self) -> bool:
        return bool(self._findings)
