"""Configuration defaults and the status view (one place for both).

Two responsibilities, both plain data.

**The default policy.** The values a new job is created with: its name, its
model seeds, and the format-version pin. ``ProjectService.new`` builds jobs
from these constants, so the policy is written down once, and the status
view can report a value as *automatic* by comparing a field against it.

**The status view.** One row per piece of information the user should be
able to see, each labelled:

- ``DEFAULTED`` — the application supplied the standard value;
- ``PROVIDED`` — the user supplied it;
- ``NONE`` — optional and absent (never a problem, never an error);
- ``MISSING`` — genuinely required and not supplied;
- ``INVALID`` — supplied, but the validation catalogue refuses it.

The **verdict** is not decided here. ``blocking`` is the validation
catalogue's own result (``ValidationService.validate_base``), and a row
reads MISSING/INVALID only because a blocking finding names that field:
``R-ROOT-006`` (no entities) points at ``Configuration``, ``R-VER-001`` /
``R-ROOT-002`` (no verified version) at ``Unverified``, and so on. Nothing
here re-decides whether a configuration is acceptable — this module maps
the catalogue's decision onto the rows a front end shows, so a refusal can
say *which* information is missing instead of leaving the user with a bare
"blocking findings".

No user-visible sentence lives here (``app`` returns data, ``ui`` renders
wording): rows carry a key, a state, and plain values.
"""

from __future__ import annotations

from configbuilder.model import (
    DEFAULT_INPUT_VERSION,
    AlignmentAutomatic,
    AlignmentFree,
    ComponentRecord,
    Explicit,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    Pinned,
    Unverified,
)

__all__ = [
    "AUTO_NAME_PREFIX",
    "DEFAULT_SEED_VALUES",
    "DEFAULT_VERSION",
    "ConfigurationStatus",
    "FieldState",
    "StatusField",
    "build_status",
    "default_job_name",
    "is_automatic_name",
]


# -- the default policy -------------------------------------------------------------

AUTO_NAME_PREFIX = "Untitled job "
"""Automatic job names are ``Untitled job N`` (``default_job_name``).

The prefix doubles as the marker the status view uses to report a name as
*automatic* rather than user-supplied.
"""

DEFAULT_SEED_VALUES = (1,)
"""The seed set a new job starts with (spec §14 requires at least one seed).

Deliberately the project's established default: one seed is a valid AF3
input, and the deployment's wider comparison policy (ten seeds) is a
project choice the user can opt into — never a requirement to get started.
"""

DEFAULT_VERSION = DEFAULT_INPUT_VERSION
"""The format version a new job pins: the model's ``DEFAULT_INPUT_VERSION``.

A new job therefore starts on an explicit, supported choice and an export
never needs a version/evidence ritual first (spec §18).

Deliberately AlphaFold 3 input version 3: the reference implementation
carries ``JSON_VERSIONS = (1, 2, 3, 4)`` — the same set as
``SUPPORTED_INPUT_VERSIONS``. Version 3 is the minimum version that covers
the builder's core fields — v2 added the external MSA and template file
fields, v3 the external user-CCD field — while version 4 adds only the
per-chain textual ``description`` fields. A job that uses a description must
raise the pin to 4 in the job-configuration menu; the transform engine names
that requirement rather than silently upgrading.
"""


def default_job_name(index: int) -> str:
    """The automatic job name for sequence position ``index`` (1-based)."""
    return "%s%d" % (AUTO_NAME_PREFIX, index)


def is_automatic_name(name: str) -> bool:
    """True when ``name`` looks like an automatically generated job name.

    Value-based rather than provenance-tracked: the model carries no
    "who typed this" flag, and adding one would change the project file for
    a display detail. A user who deliberately types ``Untitled job 7`` sees
    it reported as automatic — harmless, and the opposite error (calling a
    generated name user-supplied) never happens.
    """
    text = (name or "").strip()
    if not text.startswith(AUTO_NAME_PREFIX):
        return False
    rest = text[len(AUTO_NAME_PREFIX):]
    return rest.isdigit() or (rest and rest[0].isdigit() and rest[1:].isdigit())


def is_default_seeds(values) -> bool:
    """True when a seed sequence is the project's standard starting set."""
    return tuple(values) == tuple(DEFAULT_SEED_VALUES)


# -- the status view ----------------------------------------------------------------


class FieldState:
    """How one field stands (the vocabulary a front end switches on)."""

    DEFAULTED = "defaulted"
    PROVIDED = "provided"
    NONE = "none"
    MISSING = "missing"
    INVALID = "invalid"


class StatusField:
    """One row of the status view: a key, its state, and plain values."""

    __slots__ = ("key", "state", "value", "message")

    def __init__(self, key, state, value=None, message="") -> None:
        self.key = key
        self.state = state
        self.value = value
        self.message = message or ""

    @property
    def needs_attention(self) -> bool:
        """True when this row is genuinely incomplete or refused."""
        return self.state in (FieldState.MISSING, FieldState.INVALID)

    def __repr__(self) -> str:
        return "StatusField(%r, %r)" % (self.key, self.state)


class ConfigurationStatus:
    """The configuration as the user needs to see it: field rows plus the
    catalogue's verdict.

    ``blocking`` is the base report's blocking findings from
    ``ValidationService.GATE_TIERS`` — the same rule set save, preview and
    generation gate on, so ``ready`` and "this job can be written" can never
    disagree. Variant-tier and full-catalogue reviews stay on the Variants
    page, which has its own verdict.
    """

    __slots__ = ("fields", "blocking")

    def __init__(self, fields, blocking=()) -> None:
        self.fields = tuple(fields)
        self.blocking = tuple(blocking)

    @property
    def ready(self) -> bool:
        """True when nothing blocks generation (the catalogue's verdict)."""
        return not self.blocking

    def field(self, key):
        """The row for ``key``, or ``None``."""
        for field in self.fields:
            if field.key == key:
                return field
        return None

    def attention(self):
        """The rows that need the user's attention (missing or refused)."""
        return tuple(field for field in self.fields if field.needs_attention)

    def __repr__(self) -> str:
        return "ConfigurationStatus(ready=%r, fields=%d)" % (
            self.ready,
            len(self.fields),
        )


# -- building the view --------------------------------------------------------------

# Which status row a blocking finding speaks about. The mapping is by the
# finding's *field path type name* — the catalogue's own locator vocabulary
# (``FieldPath``) — so this table is presentation routing, not a second
# opinion about what is required.
_FIELD_BY_PATH_TYPE = {
    "ConfigurationMetadata": "name",
    "SeedSet": "seeds",
    "Seed": "seeds",
    "Unverified": "version",
    "Auto": "version",
    "Dialect": "version",
    "FormatTarget": "version",
    "Configuration": "components",
    "Record": "components",
    "FamilyARecord": "components",
    "FamilyBRecord": "components",
    "FamilyCRecord": "components",
    "ComponentRecord": "components",
    "ComponentCode": "components",
    "ComponentRepresentation": "components",
    "SequenceText": "components",
    "EntityId": "components",
    "ByNotation": "components",
    "LinkEndpoint": "components",
    "ResidueRef": "components",
    "Linkage": "components",
    "ReferenceRecord": "templates",
    "ReferenceSet": "templates",
    "IndexPair": "templates",
}

_REQUIRED_KEYS = ("name", "seeds", "version", "components")


def _attention_by_field(blocking_findings) -> dict:
    """``{row key: finding}`` for the blocking findings that name a row."""
    attention = {}
    for finding in blocking_findings:
        for path in getattr(finding, "paths", ()) or ():
            key = _FIELD_BY_PATH_TYPE.get(getattr(path, "type_name", ""))
            if key is not None:
                attention.setdefault(key, finding)
                break
    return attention


def _record_counts(records) -> dict:
    """Record counts per family, in the model's own family order."""
    counts = {"protein": 0, "rna": 0, "dna": 0, "ligand": 0}
    for record in records:
        if isinstance(record, FamilyARecord):
            counts["protein"] += 1
        elif isinstance(record, FamilyBRecord):
            counts["rna"] += 1
        elif isinstance(record, FamilyCRecord):
            counts["dna"] += 1
        elif isinstance(record, ComponentRecord):
            counts["ligand"] += 1
    return counts


def _name_field(configuration, attention) -> StatusField:
    name = configuration.metadata.name
    finding = attention.get("name")
    if finding is not None:
        return StatusField("name", FieldState.INVALID, name, finding.user_message)
    state = (
        FieldState.DEFAULTED if is_automatic_name(name) else FieldState.PROVIDED
    )
    return StatusField("name", state, name)


def _seeds_field(configuration, attention) -> StatusField:
    values = tuple(configuration.seeds.values)
    finding = attention.get("seeds")
    if finding is not None:
        return StatusField("seeds", FieldState.INVALID, values, finding.user_message)
    state = (
        FieldState.DEFAULTED if is_default_seeds(values) else FieldState.PROVIDED
    )
    return StatusField("seeds", state, values)


def _version_field(configuration, attention) -> StatusField:
    selection = configuration.format_target.version_selection
    if isinstance(selection, Unverified):
        finding = attention.get("version")
        message = finding.user_message if finding is not None else ""
        return StatusField("version", FieldState.MISSING, None, message)
    finding = attention.get("version")
    if finding is not None:
        return StatusField("version", FieldState.INVALID, selection, finding.user_message)
    state = FieldState.DEFAULTED
    if isinstance(selection, Pinned) and selection.version != DEFAULT_VERSION:
        state = FieldState.PROVIDED
    return StatusField("version", state, selection)


def _components_field(configuration, attention) -> StatusField:
    counts = _record_counts(configuration.records)
    if not configuration.records:
        finding = attention.get("components")
        message = finding.user_message if finding is not None else ""
        return StatusField("components", FieldState.MISSING, counts, message)
    finding = attention.get("components")
    if finding is not None:
        return StatusField("components", FieldState.INVALID, counts, finding.user_message)
    return StatusField("components", FieldState.PROVIDED, counts)


def _optional_field(key, count) -> StatusField:
    """An optional row: absent is ``NONE``, never a problem."""
    return StatusField(key, FieldState.PROVIDED if count else FieldState.NONE, count)


def _modifications_field(configuration) -> StatusField:
    total = 0
    for record in configuration.records:
        if isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord)):
            total += len(record.modifications or ())
    return _optional_field("modifications", total)


def _msa_field(configuration) -> StatusField:
    """MSA is optional; a record still on the automatic MSA is not "no MSA".

    Three states matter here: the contract's automatic MSA (the standard
    default — reported ``DEFAULTED``, never as user input), the explicit
    "no MSA" state, and a user-supplied alignment (``PROVIDED``).
    """
    custom = 0
    automatic = 0
    for record in configuration.records:
        if isinstance(record, (FamilyARecord, FamilyBRecord)):
            alignment = record.alignment
            if isinstance(alignment, AlignmentAutomatic):
                automatic += 1
            elif isinstance(alignment, AlignmentFree) or alignment is None:
                continue
            else:
                custom += 1
    if custom:
        return StatusField("msa", FieldState.PROVIDED, custom)
    if automatic:
        return StatusField("msa", FieldState.DEFAULTED, automatic)
    return StatusField("msa", FieldState.NONE, 0)


def _templates_field(configuration) -> StatusField:
    total = 0
    for record in configuration.records:
        if isinstance(record, FamilyARecord):
            references = record.references
            if isinstance(references, Explicit) and references.items:
                total += 1
    return _optional_field("templates", total)


def build_status(configuration, blocking_findings=()) -> ConfigurationStatus:
    """The status view over ``configuration``.

    ``blocking_findings`` is the base report's blocking findings (the
    catalogue's verdict); pass it so refused or missing fields can be named.
    Pass *only* what blocks: a non-blocking finding that happens to name a
    field must not make a row read INVALID (an optional-absent field is
    never an error), which is why the caller filters on severity rather
    than handing over the whole report.
    """
    attention = _attention_by_field(blocking_findings)
    fields = (
        _name_field(configuration, attention),
        _seeds_field(configuration, attention),
        _version_field(configuration, attention),
        _components_field(configuration, attention),
        _modifications_field(configuration),
        _msa_field(configuration),
        _templates_field(configuration),
    )
    return ConfigurationStatus(fields, blocking_findings)
