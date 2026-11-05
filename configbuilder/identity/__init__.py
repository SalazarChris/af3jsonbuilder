"""Identity package: identifier allocation, uniqueness, reference resolution.

The sole authority for identifiers (IMPLEMENTATION_PLAN.md §6.2, §8).
Imports nothing from other project modules (plan §5.3 rule 1).
"""

from configbuilder.identity.identifiers import EntityId, Multiplicity
from configbuilder.identity.registry import (
    Assignment,
    DuplicateIdError,
    IdAllocator,
    IdentityError,
    IdentityRegistry,
    RegistrySnapshot,
    RenameMap,
)

__all__ = [
    "EntityId",
    "Multiplicity",
    "Assignment",
    "DuplicateIdError",
    "IdAllocator",
    "IdentityError",
    "IdentityRegistry",
    "RegistrySnapshot",
    "RenameMap",
]
