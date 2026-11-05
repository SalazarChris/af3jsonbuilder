"""Persistence (IMPLEMENTATION_PLAN.md §14, §6.8): project file save/load
with its own schema version axis.

Depends on ``model``, ``identity``, and ``variants`` (edit types) only
(plan §5.3 rule 8); validation is injected into ``load`` by ``app`` so
findings surface at load time without a layering violation.
"""

from configbuilder.persistence.schema import (
    SCHEMA_VERSION,
    FutureVersionError,
    LoadResult,
    OutputSettings,
    PersistenceError,
    Project,
    upgrade,
)
from configbuilder.persistence.sequences import (
    parse_code_text,
    parse_sequence_text,
    parse_smiles_text,
    read_code_file,
    read_sequence_file,
    read_smiles_file,
)
from configbuilder.persistence.store import PROJECT_EXTENSION, load, save

__all__ = [
    "SCHEMA_VERSION",
    "FutureVersionError",
    "LoadResult",
    "OutputSettings",
    "PersistenceError",
    "PROJECT_EXTENSION",
    "Project",
    "load",
    "parse_code_text",
    "parse_sequence_text",
    "parse_smiles_text",
    "read_code_file",
    "read_sequence_file",
    "read_smiles_file",
    "save",
    "upgrade",
]
