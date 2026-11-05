"""Application services (IMPLEMENTATION_PLAN.md §15).

The only layer allowed to join every stage (plan §5.3 rule 5): it composes
``validation``, ``variants``, ``transform``, ``serialize``, ``output``,
``persistence``, and the model itself into the workflows a UI or CLI
drives. Services never raise for user-caused problems — they return
result values (``results.py``) whose ``ok`` flag is the contract.

The layer owns no domain logic: every stage's invariants live in the
stage's own package; this package only sequences them.
"""

from configbuilder.app.configuration_service import ConfigurationService
from configbuilder.app.generation_service import GenerationService
from configbuilder.app.project_service import ProjectService
from configbuilder.app.results import (
    BatchCounts,
    FailureReason,
    GenerationPlan,
    LoadOutput,
    PlanOutput,
    batch_counts,
)
from configbuilder.app.validation_service import ValidationService
from configbuilder.app.variant_service import VariantService

__all__ = [
    "BatchCounts",
    "ConfigurationService",
    "FailureReason",
    "GenerationPlan",
    "GenerationService",
    "LoadOutput",
    "PlanOutput",
    "ProjectService",
    "ValidationService",
    "VariantService",
    "batch_counts",
]
