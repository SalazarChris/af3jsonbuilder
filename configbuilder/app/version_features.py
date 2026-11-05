"""Format-version requirements a front end can *explain* but never enforce.

The numbers come from the evidenced mapping layer
(``transform.mappings``), the single authority for which JSON input version
introduced which wire field. They are re-exported here, not re-typed: a
front end asks this module so it never imports a pipeline stage itself
(plan §5.3 rule 6 keeps ``ui`` on ``app`` and ``model``), and enforcement
stays exactly where it already is — ``transform``'s version-feature check
and the generation gate built on it.

Nothing here decides anything. A front end uses these values to warn before
a user is surprised (for example: a per-entity description is kept in the
model but is only *written* from the version below), and the real refusal,
when there is one, still comes from the service.
"""

from __future__ import annotations

from configbuilder.transform.mappings import (
    DESCRIPTION_MIN_VERSION,
    MSA_PATH_MIN_VERSION,
    TEMPLATE_PATH_MIN_VERSION,
    USER_CCD_PATH_MIN_VERSION,
)

__all__ = [
    "DESCRIPTION_MIN_VERSION",
    "MSA_PATH_MIN_VERSION",
    "TEMPLATE_PATH_MIN_VERSION",
    "USER_CCD_PATH_MIN_VERSION",
]
