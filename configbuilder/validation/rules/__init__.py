"""Rule check functions (IMPLEMENTATION_PLAN.md §9, Phase 4).

One ``check_<rule_id_lowercased>`` function per catalogue rule; the engine
resolves them by convention. A missing function is reported as a skipped
rule — never silently green.
"""

from configbuilder.validation.rules import (
    bond_rules,
    entity_rules,
    msa_rules,
    policy_rules,
    root_rules,
    template_rules,
    variant_rules,
)

__all__ = [
    "bond_rules",
    "entity_rules",
    "msa_rules",
    "policy_rules",
    "root_rules",
    "template_rules",
    "variant_rules",
]
