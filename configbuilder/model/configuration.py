"""The Configuration root aggregate (IMPLEMENTATION_PLAN.md §7.5, §7.6).

Every model type is frozen; editing produces a new object through ``with_*``
helpers. Defaults never invent contract behaviour: optional contract fields
default to ``Unset`` (omitted), alignment to ``Automatic``, references to
``SearchAllowed``, and version selection to ``Unverified`` — which blocks
generation until a format has been observed to be accepted by the
deployment (plan §10.3).
"""

from __future__ import annotations

from typing import Tuple

from configbuilder.identity import IdentityRegistry
from configbuilder.model.presence import is_presence, Present, Unset
from configbuilder.model.errors import ModelError
from configbuilder.model.records import (
    ComponentRecord,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    Linkage,
)
from configbuilder.model.values import External, Inline, Seed

__all__ = [
    "Configuration",
    "ConfigurationError",
    "ConfigurationMetadata",
    "DEFAULT_INPUT_VERSION",
    "Dialect",
    "FormatTarget",
    "SUPPORTED_INPUT_VERSIONS",
    "SeedSet",
    "VersionSelection",
    "fold_version_selection",
]

UINT32_MAX = 2 ** 32 - 1

# The input-format versions this builder knows how to emit (spec §18). The
# set is the single authority: the console's version prompt, the GUI's version
# picker and the R-ROOT-002 availability rule all read it from here, so a
# version can never be offered by one surface and refused by another.
SUPPORTED_INPUT_VERSIONS = (1, 2, 3, 4)

#: The version a new job starts on — an explicit, supported choice, never
#: inferred from the environment.
DEFAULT_INPUT_VERSION = 3


class ConfigurationError(ModelError):
    """Raised for invalid configuration construction."""


class _FrozenBase:
    __slots__ = ()

    def __setattr__(self, name, value):
        raise ConfigurationError("%s is immutable" % type(self).__name__)


class ConfigurationMetadata(_FrozenBase):
    """Root metadata: the job name and the optional job-level description
    (MAP-002, MAP-101).

    The job description is the variant-relevant "descriptions" factor of
    spec §15 ("job name and descriptions — metadata/naming rather than
    molecular chemistry"). It is project-side naming, never emitted to the
    wire; a variant may set it without touching molecular content.
    """

    __slots__ = ("_name", "_description")

    def __init__(self, name: str, description=None) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError("name must be a non-empty string")
        object.__setattr__(self, "_name", name)
        # The description is a Presence value by contract; a bare string is
        # accepted as shorthand and normalised to ``Present`` so the state
        # algebra holds everywhere (persistence round-trips depend on it).
        if description is None:
            description = Unset()
        elif isinstance(description, str):
            description = Present(description)
        if not is_presence(description):
            raise ConfigurationError("description must be a Presence value (Unset/ExplicitEmpty/Present)")
        object.__setattr__(self, "_description", description)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self):
        """Job-level description as a Presence value (spec §15 naming factor)."""
        return self._description

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ConfigurationMetadata):
            return self._name == other._name and self._description == other._description
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("ConfigurationMetadata", self._name, self._description))

    def __repr__(self) -> str:
        return "ConfigurationMetadata(%r)" % self._name


class SeedSet(_FrozenBase):
    """The reproducibility seed set (MAP-003, MAP-102): non-empty, uint32.

    Order is preserved as given and carries no requirement (spec §14:
    neither uniqueness nor sorting is an AF3 requirement).
    """

    __slots__ = ("_seeds",)

    def __init__(self, seeds) -> None:
        if isinstance(seeds, (int, Seed)):
            seeds = (seeds,)
        if not isinstance(seeds, tuple):
            seeds = tuple(seeds)
        if not seeds:
            raise ConfigurationError("at least one model seed is required (spec §14)")
        converted = []
        for seed in seeds:
            if not isinstance(seed, Seed):
                seed = Seed(seed)
            converted.append(seed)
        object.__setattr__(self, "_seeds", tuple(converted))

    @property
    def seeds(self) -> Tuple[Seed, ...]:
        return self._seeds

    @property
    def values(self) -> Tuple[int, ...]:
        return tuple(seed.value for seed in self._seeds)

    def __len__(self) -> int:
        return len(self._seeds)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SeedSet):
            return self._seeds == other._seeds
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("SeedSet", self._seeds))

    def __repr__(self) -> str:
        return "SeedSet(%r)" % (self.values,)


class Dialect(_FrozenBase):
    """A single-member-style enumeration of the one supported dialect
    (MAP-107; spec §4, §17).

    It is an enumeration rather than a literal so the second, incompatible
    external dialect can never be produced by accident (plan §7.7)."""

    __slots__ = ("_value",)

    STANDALONE_AF3 = "alphafold3"

    _instances = {}

    def __new__(cls, value: str):
        if value != cls.STANDALONE_AF3:
            raise ConfigurationError(
                "unsupported dialect %r; the builder emits exactly one dialect" % (value,)
            )
        if value not in cls._instances:
            instance = super().__new__(cls)
            object.__setattr__(instance, "_value", value)
            cls._instances[value] = instance
        return cls._instances[value]

    @property
    def value(self) -> str:
        return self._value

    def __reduce__(self):
        return (Dialect, (self._value,))

    def __repr__(self) -> str:
        return "Dialect(%r)" % self._value


class Unverified(_FrozenBase):
    """No format has been verified against the deployment yet; blocks
    generation (plan §10.3)."""

    __slots__ = ()

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __reduce__(self):
        return (Unverified,)


class Pinned(_FrozenBase):
    """Emit version ``n``, with the human-supplied provenance of ``evidence``.

    The evidence reference records *why* this version was chosen — a
    deployment observation's ``PIN-nnn`` identifier is the usual one, but
    it is a string the operator supplies; no runtime code ever reads a
    document to construct it, and an empty string is accepted: citing an
    observation is provenance, not a condition for generating output. The
    version itself is one of ``SUPPORTED_INPUT_VERSIONS`` (R-ROOT-002); no
    version is ever inferred.
    """

    __slots__ = ("_version", "_evidence")

    def __init__(self, version: int, evidence="") -> None:
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ConfigurationError("Pinned version must be a positive integer")
        if not isinstance(evidence, str):
            raise ConfigurationError("Pinned evidence must be a string")
        evidence = evidence.strip()
        if not evidence or evidence.lower() == "none":
            evidence = ""
        object.__setattr__(self, "_version", version)
        object.__setattr__(self, "_evidence", evidence)

    @property
    def version(self) -> int:
        return self._version

    @property
    def evidence(self) -> str:
        """The operator-supplied provenance reference (e.g. ``PIN-001``);
        empty when none was cited yet."""
        return self._evidence

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Pinned):
            return self._version == other._version and self._evidence == other._evidence
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Pinned", self._version, self._evidence))

    def __repr__(self) -> str:
        if not self._evidence:
            return "Pinned(%d)" % self._version
        return "Pinned(%d, evidence=%r)" % (self._version, self._evidence)


class Auto(_FrozenBase):
    """Minimum version covering the features used, within an evidenced set
    (plan §10.3). It never extrapolates beyond the evidenced versions."""

    __slots__ = ("_evidenced",)

    def __init__(self, evidenced: Tuple[int, ...]) -> None:
        if not isinstance(evidenced, tuple):
            evidenced = tuple(evidenced)
        if not evidenced:
            raise ConfigurationError(
                "Auto requires at least one evidenced version"
            )
        for version in evidenced:
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise ConfigurationError("evidenced versions must be positive integers")
        object.__setattr__(self, "_evidenced", tuple(sorted(set(evidenced))))

    @property
    def evidenced(self) -> Tuple[int, ...]:
        return self._evidenced

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Auto):
            return self._evidenced == other._evidenced
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Auto", self._evidenced))

    def __repr__(self) -> str:
        return "Auto(evidenced=%r)" % (self._evidenced,)


VersionSelection = (Unverified, Pinned, Auto)


def fold_version_selection(value, on_unverified, on_pinned, on_auto):
    """The only dispatch over ``VersionSelection`` (plan §7.3)."""
    if isinstance(value, Unverified):
        return on_unverified()
    if isinstance(value, Pinned):
        return on_pinned(value.version)
    if isinstance(value, Auto):
        return on_auto(value.evidenced)
    raise ConfigurationError(
        "fold_version_selection: unknown version selection %r" % (value,)
    )


class FormatTarget(_FrozenBase):
    """Dialect plus version selection (MAP-107/108)."""

    __slots__ = ("_dialect", "_version_selection")

    def __init__(self, version_selection=None, dialect: Dialect = None) -> None:
        object.__setattr__(self, "_dialect", Dialect(Dialect.STANDALONE_AF3) if dialect is None else dialect)
        object.__setattr__(self, "_version_selection", Unverified() if version_selection is None else version_selection)

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    @property
    def version_selection(self):
        return self._version_selection

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FormatTarget):
            return (
                self._dialect == other._dialect
                and self._version_selection == other._version_selection
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("FormatTarget", self._dialect, self._version_selection))

    def __repr__(self) -> str:
        return "FormatTarget(%r, %r)" % (self._dialect.value, self._version_selection)


class Configuration(_FrozenBase):
    """The canonical internal model root (MAP-001).

    No validation flag travels with the data (plan §7.6): validation state
    is a separate ``ValidationReport`` held by ``app``.
    """

    __slots__ = (
        "_metadata",
        "_seeds",
        "_records",
        "_linkages",
        "_component_definition",
        "_identity",
        "_format_target",
    )

    def __init__(
        self,
        metadata: ConfigurationMetadata,
        seeds: SeedSet,
        records: Tuple[object, ...],
        identity: IdentityRegistry,
        linkages: Tuple[Linkage, ...] = (),
        component_definition=None,
        format_target: FormatTarget = None,
    ) -> None:
        if not isinstance(metadata, ConfigurationMetadata):
            raise ConfigurationError("metadata must be ConfigurationMetadata")
        if not isinstance(seeds, SeedSet):
            raise ConfigurationError("seeds must be a SeedSet")
        if not isinstance(records, tuple):
            records = tuple(records)
        for record in records:
            if not isinstance(
                record, (FamilyARecord, FamilyBRecord, FamilyCRecord, ComponentRecord)
            ):
                raise ConfigurationError("records must be record-family instances")
        if not isinstance(linkages, tuple):
            linkages = tuple(linkages)
        for linkage in linkages:
            if not isinstance(linkage, Linkage):
                raise ConfigurationError("linkages must be Linkage values")
        if not isinstance(identity, IdentityRegistry):
            raise ConfigurationError("identity must be an IdentityRegistry")
        from configbuilder.model.values import External, Inline

        if component_definition is not None and not isinstance(
            component_definition, (Inline, External)
        ):
            raise ConfigurationError("component_definition must be Inline or External")
        object.__setattr__(self, "_metadata", metadata)
        object.__setattr__(self, "_seeds", seeds)
        object.__setattr__(self, "_records", records)
        object.__setattr__(self, "_linkages", linkages)
        object.__setattr__(self, "_component_definition", component_definition)
        object.__setattr__(self, "_identity", identity)
        object.__setattr__(
            self,
            "_format_target",
            FormatTarget() if format_target is None else format_target,
        )

    @property
    def metadata(self) -> ConfigurationMetadata:
        return self._metadata

    @property
    def seeds(self) -> SeedSet:
        return self._seeds

    @property
    def records(self) -> Tuple[object, ...]:
        return self._records

    @property
    def linkages(self) -> Tuple[Linkage, ...]:
        return self._linkages

    @property
    def component_definition(self):
        """``None`` means the root user-CCD source is absent (MAP-1203)."""
        return self._component_definition

    @property
    def identity(self) -> IdentityRegistry:
        return self._identity

    @property
    def format_target(self) -> FormatTarget:
        return self._format_target

    # -- with_* derivation helpers (plan §7.6) --------------------------------

    def with_metadata(self, metadata: ConfigurationMetadata) -> "Configuration":
        return Configuration(
            metadata,
            self._seeds,
            self._records,
            self._identity,
            self._linkages,
            self._component_definition,
            self._format_target,
        )

    def with_seeds(self, seeds: SeedSet) -> "Configuration":
        return Configuration(
            self._metadata,
            seeds,
            self._records,
            self._identity,
            self._linkages,
            self._component_definition,
            self._format_target,
        )

    def with_records(self, records) -> "Configuration":
        return Configuration(
            self._metadata,
            self._seeds,
            tuple(records),
            self._identity,
            self._linkages,
            self._component_definition,
            self._format_target,
        )

    def with_linkages(self, linkages) -> "Configuration":
        return Configuration(
            self._metadata,
            self._seeds,
            self._records,
            self._identity,
            tuple(linkages),
            self._component_definition,
            self._format_target,
        )

    def with_component_definition(self, component_definition) -> "Configuration":
        if component_definition is not None and not isinstance(
            component_definition, (Inline, External)
        ):
            raise ConfigurationError("component_definition must be Inline or External")
        return Configuration(
            self._metadata,
            self._seeds,
            self._records,
            self._identity,
            self._linkages,
            component_definition,
            self._format_target,
        )

    def with_format_target(self, format_target: FormatTarget) -> "Configuration":
        return Configuration(
            self._metadata,
            self._seeds,
            self._records,
            self._identity,
            self._linkages,
            self._component_definition,
            format_target,
        )

    def with_identity(self, identity: IdentityRegistry) -> "Configuration":
        """Replace the registry (variant expansion clones it per variant —
        plan §12.4: the registry is the one mutable-feeling object, so each
        variant holds its own)."""
        if not isinstance(identity, IdentityRegistry):
            raise ConfigurationError("identity must be an IdentityRegistry")
        return Configuration(
            self._metadata,
            self._seeds,
            self._records,
            identity,
            self._linkages,
            self._component_definition,
            self._format_target,
        )

    def with_named(self, name: str) -> "Configuration":
        """Same configuration under a different job name (variant SetName)."""
        return self.with_metadata(ConfigurationMetadata(name, self._metadata.description))

    def with_job_description(self, description) -> "Configuration":
        """Same configuration with a new job-level description Presence
        (variant SetDescription; spec §15 naming factor)."""
        if not is_presence(description):
            raise ConfigurationError("job description must be a Presence value")
        return self.with_metadata(ConfigurationMetadata(self._metadata.name, description))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Configuration):
            return (
                self._metadata == other._metadata
                and self._seeds == other._seeds
                and self._records == other._records
                and self._linkages == other._linkages
                and self._component_definition == other._component_definition
                and self._format_target == other._format_target
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash(
            (
                "Configuration",
                self._metadata,
                self._seeds,
                self._records,
                self._linkages,
                self._component_definition,
                self._format_target,
            )
        )

    def __repr__(self) -> str:
        return "Configuration(name=%r, records=%d, linkages=%d)" % (
            self._metadata.name,
            len(self._records),
            len(self._linkages),
        )
