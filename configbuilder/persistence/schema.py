"""The project-file container and its schema version (IMPLEMENTATION_PLAN.md
§14, §6.8).

A ``Project`` is what persistence saves and loads: the base configuration,
the variant specs, and the output settings. It is deliberately *not* the
generated input file — variant specs, declared factors, presence states,
and project-side labels exist only here (plan §14: round-tripping through
the generated file would lose user intent).

``schema_version`` is the project file's own axis, never conflated with
the external format version (spec §18's two-axis warning).
"""

from __future__ import annotations

from typing import Tuple

__all__ = [
    "SCHEMA_VERSION",
    "Project",
    "OutputSettings",
    "LoadResult",
    "PersistenceError",
    "FutureVersionError",
    "UPGRADES",
    "upgrade",
]


class PersistenceError(Exception):
    """A project file could not be loaded (corrupt content, invalid model
    data). This is a refusal, never a partially loaded state."""


class FutureVersionError(PersistenceError):
    """The file's ``schema_version`` is newer than this builder knows.
    Guessing is not attempted (plan §14); the message names the versions."""


SCHEMA_VERSION = 1


class OutputSettings:
    """The project's generation settings (plan §14: project = metadata +
    base configuration + variant specs + output settings)."""

    __slots__ = ("_overwrite_policy", "_path_policy")

    def __init__(self, overwrite_policy: str = "Fail", path_policy: str = "CopyIntoAssets") -> None:
        object.__setattr__(self, "_overwrite_policy", overwrite_policy)
        object.__setattr__(self, "_path_policy", path_policy)

    def __setattr__(self, name, value):
        raise PersistenceError("OutputSettings is immutable")

    @property
    def overwrite_policy(self) -> str:
        return self._overwrite_policy

    @property
    def path_policy(self) -> str:
        return self._path_policy

    def __eq__(self, other: object) -> bool:
        if isinstance(other, OutputSettings):
            return (
                self._overwrite_policy == other._overwrite_policy
                and self._path_policy == other._path_policy
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("OutputSettings", self._overwrite_policy, self._path_policy))

    def __repr__(self) -> str:
        return "OutputSettings(%r, %r)" % (self._overwrite_policy, self._path_policy)


class Project:
    """Base configuration + variant specs + output settings (plan §6.8)."""

    __slots__ = ("_configuration", "_specs", "_settings")

    def __init__(self, configuration, specs: Tuple = (), settings: OutputSettings = None) -> None:
        object.__setattr__(self, "_configuration", configuration)
        object.__setattr__(self, "_specs", tuple(specs))
        object.__setattr__(self, "_settings", settings if settings is not None else OutputSettings())

    def __setattr__(self, name, value):
        raise PersistenceError("Project is immutable")

    @property
    def configuration(self):
        return self._configuration

    @property
    def specs(self) -> Tuple:
        return self._specs

    @property
    def settings(self) -> OutputSettings:
        return self._settings

    def with_configuration(self, configuration) -> "Project":
        return Project(configuration, self._specs, self._settings)

    def with_specs(self, specs) -> "Project":
        return Project(self._configuration, tuple(specs), self._settings)

    def with_settings(self, settings: OutputSettings) -> "Project":
        return Project(self._configuration, self._specs, settings)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Project):
            return (
                self._configuration == other._configuration
                and self._specs == other._specs
                and self._settings == other._settings
            )
        return NotImplemented

    def __repr__(self) -> str:
        return "Project(%r, %d specs)" % (self._configuration.metadata.name, len(self._specs))


class LoadResult:
    """The outcome of ``load``: a project (on success), the schema version
    it was stored under, whether an upgrade step ran, and the validation
    findings for immediate presentation (plan §14: findings surface now,
    not after the first user action)."""

    __slots__ = ("project", "schema_version", "upgraded_from", "report")

    def __init__(self, project, schema_version: int, upgraded_from, report=None) -> None:
        self.project = project
        self.schema_version = schema_version
        self.upgraded_from = upgraded_from
        self.report = report

    def __repr__(self) -> str:
        return "LoadResult(v%d%s)" % (self.schema_version, ", upgraded" if self.upgraded_from else "")# -- upgrade machinery -----------------------------------------------------------
#
# Each entry maps an older stored version to a callable taking the file's
# data dict and returning the data dict in the *next* version's shape. The
# load path applies them in order (v0 -> v1 -> ...) until the data reaches
# SCHEMA_VERSION. Adding schema v2 later means appending one named, tested
# step here — never editing history.

# v0 spellings -> v1 spellings. A schema-migration map necessarily quotes
# the *retired* spellings — that is its subject matter, like a validation
# finding naming the field it points at. The wire-confinement scanner
# knows this single anchor by name.
_LEGACY_KEY_MAP = {
    "name": "job_name",
    "version": "pinned_version",
    "dialect": "target_dialect",
    "modifications": "modification_set",
}


def _upgrade_0_to_1(data: dict) -> dict:
    """v0 -> v1: project-file key spellings were reworded so the project
    file never borrows generated-file vocabulary (plan §14: the project
    file is deliberately *not* the generated external input file — the
    same discipline the wire-confinement architecture test enforces for
    ``transform`` now extends to persistence).

    The renames (applied recursively, since edits and records carry these
    at several depths) are ``_LEGACY_KEY_MAP``. Identity ``groups`` are
    absent in v0 payloads and are synthesized as singleton copy-groups by
    ``IdentityRegistry.from_data`` on load — the registry owns that
    legacy tolerance, not this step.
    """
    renamed = _LEGACY_KEY_MAP

    def walk(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                result[renamed.get(key, key)] = walk(item)
            return result
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    return walk(data)


UPGRADES = {
    0: _upgrade_0_to_1,
}


def upgrade(data: dict, from_version: int) -> dict:
    """Run the named upgrade steps from ``from_version`` up to
    ``SCHEMA_VERSION``, returning the upgraded data. A gap (no step for a
    version) is a refusal, not a guess."""
    current = dict(data)
    version = from_version
    while version < SCHEMA_VERSION:
        step = UPGRADES.get(version)
        if step is None:
            raise PersistenceError(
                "no upgrade step from project-file schema version %d" % version
            )
        current = step(current)
        version += 1
        current["schema_version"] = version
    return current
