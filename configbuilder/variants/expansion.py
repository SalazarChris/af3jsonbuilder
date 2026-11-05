"""Variant expansion (IMPLEMENTATION_PLAN.md §12.2, §12.3, §12.4).

``expand(base, specs, base_fingerprint) -> tuple[Variant, ...]`` is a pure
function: same base, same specs, same fingerprint — same variants, same
order. The fingerprint of the base's wire document arrives as *data*
(plan §5.3 rule 2 keeps ``variants`` and ``transform`` independent; ``app``
computes it and passes it in), and travels on every ``Lineage`` so a
manifest can prove which base a variant came from.

Isolation is structural (plan §12.4): model objects are frozen, so
sub-objects are shared between base and variants safely; edits return new
configurations; and any edit that would mutate the registry
(``AddRecord``/``RemoveRecord``) clones the registry first, so the base's
registry is never drained and siblings never see each other's
identifier changes. Released identifiers stay retired within each
variant's own registry generation (plan §8.3).
"""

from __future__ import annotations

from typing import Tuple

from configbuilder.variants.edits import EditError, apply_edit
from configbuilder.variants.spec import Lineage, Variant, VariantSpec, VariantSpecError

__all__ = ["Variant", "expand"]


def _check_unique_keys(specs: Tuple[VariantSpec, ...]) -> None:
    seen = set()
    for spec in specs:
        if spec.key in seen:
            raise VariantSpecError("duplicate variant key %r" % spec.key)
        seen.add(spec.key)


def expand(
    base,
    specs: Tuple[VariantSpec, ...],
    base_fingerprint: str = "",
) -> Tuple[Variant, ...]:
    """Expand ``specs`` over ``base`` in declared order.

    Raises for malformed specs (duplicate keys) and for edits that cannot
    apply (unknown record key, identifier conflict). Validation findings —
    including variant drift — are a separate, later stage.
    """
    specs = tuple(specs)
    _check_unique_keys(specs)
    variants = []
    for spec in specs:
        configuration = base
        for edit in spec.edits:
            try:
                configuration = apply_edit(edit, configuration)
            except EditError as error:
                raise EditError(
                    "variant %r: %s" % (spec.key, error)
                ) from error
        lineage = Lineage(
            base_fingerprint=base_fingerprint,
            applied_edits=spec.edits,
            declared_factors=spec.declared_factors,
        )
        variants.append(Variant(spec.key, spec.label, configuration, lineage))
    return tuple(variants)
