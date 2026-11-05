"""Output generation (IMPLEMENTATION_PLAN.md §13): naming, policies,
planning, execution, manifest.

Depends on ``serialize``'s payload bytes and naming inputs only (plan
§5.3 rule 4): no contract logic, no validation. The filesystem is
touched only in ``execute``; planning reads through an injectable
``FileView``.
"""

from configbuilder.output.naming import (
    MAX_SLUG_LENGTH,
    NameError,
    casefold_conflicts,
    slug,
    variant_directory_name,
    variant_file_name,
)
from configbuilder.output.policies import (
    OVERWRITE_POLICIES,
    PATH_POLICIES,
    Action,
    OverwritePolicy,
    PathPolicy,
)
from configbuilder.output.plan import (
    FileView,
    OutputPlan,
    PlanEntry,
    ResourceEntry,
    fingerprint,
    plan,
)
from configbuilder.output.execute import OutputResult, WriteOutcome, execute
from configbuilder.output.manifest import (
    MANIFEST_SCHEMA_VERSION,
    ManifestData,
    build_manifest,
    run_info,
)

__all__ = [
    "MAX_SLUG_LENGTH",
    "MANIFEST_SCHEMA_VERSION",
    "Action",
    "FileView",
    "ManifestData",
    "NameError",
    "OutputPlan",
    "OutputResult",
    "OVERWRITE_POLICIES",
    "OverwritePolicy",
    "PATH_POLICIES",
    "PathPolicy",
    "PlanEntry",
    "ResourceEntry",
    "WriteOutcome",
    "build_manifest",
    "casefold_conflicts",
    "execute",
    "fingerprint",
    "plan",
    "run_info",
    "slug",
    "variant_directory_name",
    "variant_file_name",
]
