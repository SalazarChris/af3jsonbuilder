"""The project file store (IMPLEMENTATION_PLAN.md §14, §6.8).

``save(project, path)`` writes the project file atomically (§13.4's write
semantics apply here too). ``load(path)`` reads it back: refusing unknown
future versions with a clear message, running the named upgrade steps for
known older ones, and reconstructing the model through the validated
constructors — a corrupted file is a ``PersistenceError``, never an
invalid model. Filesystem access lives in this module only (plan §5.3
rule 8); it imports model, identity, and variants (edit types) — never
validation or transform.
"""

from __future__ import annotations

import json
import os

from configbuilder.persistence.decode_model import decode_configuration, decode_spec
from configbuilder.persistence.encode_model import encode_configuration, encode_spec
from configbuilder.persistence.schema import (
    SCHEMA_VERSION,
    FutureVersionError,
    LoadResult,
    OutputSettings,
    PersistenceError,
    Project,
    upgrade,
)

__all__ = ["save", "load", "PROJECT_EXTENSION"]


PROJECT_EXTENSION = ".cbproj"


def _atomic_write_bytes(path, payload: bytes) -> None:
    """Atomic per-file write (temp in destination dir, then replace)."""
    temporary = os.path.join(os.path.dirname(path), ".%s.tmp" % os.path.basename(path))
    handle = open(temporary, "wb")
    try:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(temporary, path)
    except Exception:
        handle.close()
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def _deterministic_bytes(data: dict) -> bytes:
    """The file's byte form: UTF-8, LF, one trailing newline, fixed
    separators. Deterministic so byte-identical projects produce
    byte-identical files (the same policy the serializer uses)."""
    return (json.dumps(data, ensure_ascii=False, indent=2, separators=(",", ": ")) + "\n").encode("utf-8")


def save(project: Project, path: str) -> None:
    """Write ``project`` to ``path`` atomically.

    Deterministic: no timestamps, no host data, input order only —
    ``load(save(p))`` and a second ``save`` of the same project are
    byte-identical.
    """
    data = {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "configuration": encode_configuration(project.configuration),
            "variant_specs": [encode_spec(spec) for spec in project.specs],
            "output_settings": {
                "overwrite_policy": project.settings.overwrite_policy,
                "path_policy": project.settings.path_policy,
            },
        },
    }
    _atomic_write_bytes(path, _deterministic_bytes(data))


def _read(path: str) -> dict:
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
    except OSError as error:
        raise PersistenceError("project file cannot be read: %s" % error) from error
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise PersistenceError("project file is not valid JSON: %s" % error) from error
    if not isinstance(data, dict):
        raise PersistenceError("project file must contain a JSON object")
    return data


def load(path: str, validate=None) -> LoadResult:
    """Load the project file at ``path``.

    ``validate`` is the validation callable (injected from ``app`` to keep
    this module free of a validation import, plan §5.3 rule 8's layering);
    when given, the loaded configuration is validated immediately and the
    report travels on the result (plan §14: findings surface now).

    Lower stored versions run the named upgrade steps; higher versions are
    refused with a message naming both versions. Every model object is
    rebuilt through the same validated constructors a UI-built project
    passes through.
    """
    data = _read(path)
    stored_version = data.get("schema_version")
    if not isinstance(stored_version, int):
        raise PersistenceError(
            "project file has no integer 'schema_version'; it is not a project file "
            "this builder can read"
        )
    if stored_version > SCHEMA_VERSION:
        raise FutureVersionError(
            "project file schema version %d is newer than this builder's version %d; "
            "upgrade the builder to open it (no guessing is attempted)"
            % (stored_version, SCHEMA_VERSION)
        )
    upgraded_from = None
    if stored_version < SCHEMA_VERSION:
        data = upgrade(data, stored_version)
        upgraded_from = stored_version

    project_data = data.get("project")
    if not isinstance(project_data, dict):
        raise PersistenceError("project file is missing its 'project' object")

    configuration = decode_configuration(project_data.get("configuration"))
    specs = [
        decode_spec(spec_data, index)
        for index, spec_data in enumerate(project_data.get("variant_specs", ()))
    ]
    settings_data = project_data.get("output_settings", {})
    settings = OutputSettings(
        overwrite_policy=settings_data.get("overwrite_policy", "Fail"),
        path_policy=settings_data.get("path_policy", "CopyIntoAssets"),
    )

    project = Project(configuration=configuration, specs=tuple(specs), settings=settings)

    report = None
    if validate is not None:
        report = validate(configuration)

    return LoadResult(
        project=project,
        schema_version=SCHEMA_VERSION,
        upgraded_from=upgraded_from,
        report=report,
    )
