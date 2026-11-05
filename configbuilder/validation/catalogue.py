"""Validation rule catalogue — the specification's validation matrix as data.

IMPLEMENTATION_PLAN.md §9.1 / §21 Phase 1: the catalogue is transcribed from
AUTHORITATIVE_SPEC.md §19 **before** any checking code exists, so coverage is
measurable from the start. ``check`` implementations arrive in Phase 4.

Every row carries:

- ``rule_id``      stable identifier (R-<TIER>-NNN)
- ``tier``         STRUCTURAL | RELATIONAL | CONTRACT | VARIANT | PREFLIGHT (§9.2)
- ``severity``     default severity policy (§9.3)
- ``spec_ref``     heading of AUTHORITATIVE_SPEC.md the rule transcribes
- ``evidence``     the spec's evidence-status vocabulary (spec §1)
- ``mapping_ids``  DOMAIN_MAPPING.md MAP-### cross-references
- ``summary``      the rule in one sentence (the future finding's basis)

Evidence drives severity (plan §2 rule 3 / §9.3):

- CONFIRMED / DOCUMENTED contract rules -> ERROR, not downgradable;
- INFERRED and project-policy rules     -> WARNING default, adjustable;
- UNRESOLVED subjects                   -> INFO only, never an error.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Tier(enum.Enum):
    """Execution tiers, in engine order (plan §9.2)."""

    STRUCTURAL = "STRUCTURAL"
    RELATIONAL = "RELATIONAL"
    CONTRACT = "CONTRACT"
    VARIANT = "VARIANT"
    PREFLIGHT = "PREFLIGHT"


TIER_ORDER = (
    Tier.STRUCTURAL,
    Tier.RELATIONAL,
    Tier.CONTRACT,
    Tier.VARIANT,
    Tier.PREFLIGHT,
)


class Severity(enum.Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class Evidence(enum.Enum):
    """The spec's evidence-status vocabulary (AUTHORITATIVE_SPEC.md §1)."""

    CONFIRMED = "CONFIRMED"
    DOCUMENTED = "DOCUMENTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    PROJECT_POLICY = "PROJECT_POLICY"
    PROJECT_SPECIFIC = "PROJECT_SPECIFIC"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    tier: Tier
    severity: Severity
    spec_ref: str  # section heading text in AUTHORITATIVE_SPEC.md
    evidence: Evidence
    summary: str
    mapping_ids: tuple = field(default=())


# ---------------------------------------------------------------------------
# Root-level validation (spec §19 "Root-level validation")
# ---------------------------------------------------------------------------

ROOT_RULES = (
    Rule(
        rule_id="R-ROOT-001",
        tier=Tier.CONTRACT,
        severity=Severity.ERROR,
        spec_ref="4. Top-Level AF3 Contract",
        evidence=Evidence.CONFIRMED,
        summary="JSON dialect is 'alphafold3'; no other dialect is ever emitted.",
        mapping_ids=("MAP-107",),
    ),
    Rule(
        rule_id="R-ROOT-002",
        tier=Tier.CONTRACT,
        severity=Severity.ERROR,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.CONFIRMED,
        summary=(
            "The selected JSON version is one of the supported input versions "
            "(1-4); availability only, never inferred and never a deployment "
            "observation."
        ),
        mapping_ids=("MAP-108",),
    ),
    Rule(
        rule_id="R-ROOT-003",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="4. Top-Level AF3 Contract",
        evidence=Evidence.CONFIRMED,
        summary="Job name is non-empty and yields a valid sanitized name.",
        mapping_ids=("MAP-101",),
    ),
    Rule(
        rule_id="R-ROOT-004",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="14. Reproducibility / Model Seeds",
        evidence=Evidence.CONFIRMED,
        summary="At least one model seed is present.",
        mapping_ids=("MAP-102", "MAP-003"),
    ),
    Rule(
        rule_id="R-ROOT-005",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="14. Reproducibility / Model Seeds",
        evidence=Evidence.CONFIRMED,
        summary="Every seed is an integer within the unsigned 32-bit range 0..2^32-1.",
        mapping_ids=("MAP-907",),
    ),
    Rule(
        rule_id="R-ROOT-006",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="4. Top-Level AF3 Contract",
        evidence=Evidence.CONFIRMED,
        summary="'sequences' is the entity container and holds the record objects.",
        mapping_ids=("MAP-103", "MAP-1201"),
    ),
    Rule(
        rule_id="R-ROOT-007",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="9. Components / Ligands / Ions",
        evidence=Evidence.CONFIRMED,
        summary="userCCD and userCCDPath are mutually exclusive (inline xor external).",
        mapping_ids=("MAP-105", "MAP-106", "MAP-1203"),
    ),
)

# ---------------------------------------------------------------------------
# Entity validation (spec §19 "Entity validation")
# ---------------------------------------------------------------------------

ENTITY_RULES = (
    Rule(
        rule_id="R-ENT-001",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="5. Data Families / Entity Types",
        evidence=Evidence.CONFIRMED,
        summary="Entity families are exactly protein/RNA/DNA/ligand.",
        mapping_ids=("MAP-005", "MAP-006", "MAP-007", "MAP-008", "MAP-1201"),
    ),
    Rule(
        rule_id="R-ENT-002",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="7. Identifiers and Indexing",
        evidence=Evidence.CONFIRMED,
        summary="Entity IDs are unique across the input, including copy multiplicity.",
        # Wiring note (CHECKLIST.md Phase 4): the engine converts
        # identity.DuplicateIdError to this rule's finding at the engine
        # boundary — the registry raises, the engine translates.
        mapping_ids=("MAP-901", "MAP-902"),
    ),
    Rule(
        rule_id="R-ENT-003",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="7. Identifiers and Indexing",
        evidence=Evidence.CONFIRMED,
        summary="Entity IDs are uppercase alphabetic.",
        mapping_ids=("MAP-901",),
    ),
    Rule(
        rule_id="R-ENT-004",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="5. Data Families / Entity Types",
        evidence=Evidence.CONFIRMED,
        summary="Protein sequence is alphabetic (one-letter amino-acid codes).",
        mapping_ids=("MAP-202",),
    ),
    Rule(
        rule_id="R-ENT-005",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="5. Data Families / Entity Types",
        evidence=Evidence.CONFIRMED,
        summary="RNA sequence uses the documented alphabet A, C, G, U.",
        mapping_ids=("MAP-302",),
    ),
    Rule(
        rule_id="R-ENT-006",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="5. Data Families / Entity Types",
        evidence=Evidence.CONFIRMED,
        summary="DNA sequence uses the documented alphabet A, C, G, T.",
        mapping_ids=("MAP-352",),
    ),
    Rule(
        rule_id="R-ENT-007",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="7. Identifiers and Indexing",
        evidence=Evidence.CONFIRMED,
        summary="Modification positions lie within the parent sequence length (1-based).",
        mapping_ids=("MAP-903", "MAP-503", "MAP-1204", "MAP-1205", "MAP-1206"),
    ),
    Rule(
        rule_id="R-ENT-008",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="8. Modifications / Special Objects",
        evidence=Evidence.CONFIRMED,
        summary="Polymer modification codes must not start with the 'CCD_' prefix.",
        mapping_ids=("MAP-204", "MAP-304", "MAP-354", "MAP-506"),
    ),
    Rule(
        rule_id="R-ENT-009",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="5. Data Families / Entity Types",
        evidence=Evidence.CONFIRMED,
        summary="A ligand has exactly one of CCD codes or SMILES.",
        mapping_ids=("MAP-402", "MAP-403", "MAP-406", "MAP-1209"),
    ),
    Rule(
        rule_id="R-ENT-010",
        tier=Tier.PREFLIGHT,
        severity=Severity.ERROR,
        spec_ref="5. Data Families / Entity Types",
        evidence=Evidence.CONFIRMED,
        summary=(
            "SMILES notation parses; when no local chemistry probe is available the "
            "check reports 'not checked' as a WARNING instead (plan §9.6)."
        ),
        mapping_ids=("MAP-403",),
    ),
    Rule(
        rule_id="R-ENT-011",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="8. Modifications / Special Objects",
        evidence=Evidence.CONFIRMED,
        summary=(
            "A D-amino-acid modification uses the CCD component of the canonical "
            "residue it replaces, on a protein chain; glycine has no D-form."
        ),
        mapping_ids=("MAP-009", "MAP-204", "MAP-205"),
    ),
    Rule(
        rule_id="R-ENT-012",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="8. Modifications / Special Objects",
        evidence=Evidence.CONFIRMED,
        summary=(
            "A polymer position carries at most one modification: a residue "
            "replacement and a PTM cannot share a position."
        ),
        mapping_ids=("MAP-009", "MAP-204", "MAP-205"),
    ),
)

# ---------------------------------------------------------------------------
# MSA validation (spec §19 "MSA validation")
# ---------------------------------------------------------------------------

MSA_RULES = (
    Rule(
        rule_id="R-MSA-001",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="11. MSA Contract",
        evidence=Evidence.CONFIRMED,
        summary="Protein unpaired/paired MSA fields are both set or both unset.",
        mapping_ids=("MAP-601", "MAP-602", "MAP-603", "MAP-604", "MAP-605"),
    ),
    Rule(
        rule_id="R-MSA-002",
        tier=Tier.CONTRACT,
        severity=Severity.ERROR,
        spec_ref="6. Representations",
        evidence=Evidence.CONFIRMED,
        summary="Inline and path representations are mutually exclusive per MSA field.",
        mapping_ids=("MAP-207", "MAP-208", "MAP-209", "MAP-210", "MAP-307", "MAP-308"),
    ),
    Rule(
        rule_id="R-MSA-003",
        tier=Tier.PREFLIGHT,
        severity=Severity.WARNING,
        spec_ref="11. MSA Contract",
        evidence=Evidence.DOCUMENTED,
        summary=(
            "Custom MSA content is required to be A3M; shallow local check only — "
            "the external system owns deep interpretation (plan §9.2)."
        ),
        mapping_ids=("MAP-602", "MAP-604", "MAP-605", "MAP-606"),
    ),
    Rule(
        rule_id="R-MSA-004",
        tier=Tier.PREFLIGHT,
        severity=Severity.WARNING,
        spec_ref="11. MSA Contract",
        evidence=Evidence.DOCUMENTED,
        summary=(
            "The first sequence of a custom MSA should equal the query sequence; "
            "shallow check, advisory."
        ),
        mapping_ids=("MAP-602", "MAP-605"),
    ),
    Rule(
        rule_id="R-MSA-005",
        tier=Tier.PREFLIGHT,
        severity=Severity.WARNING,
        spec_ref="11. MSA Contract",
        evidence=Evidence.DOCUMENTED,
        summary=(
            "After removing lowercase insertions a custom MSA should form a "
            "rectangular alignment; shallow check, advisory."
        ),
        mapping_ids=("MAP-602", "MAP-604", "MAP-605"),
    ),
    Rule(
        rule_id="R-MSA-006",
        tier=Tier.PREFLIGHT,
        severity=Severity.ERROR,
        spec_ref="11. MSA Contract",
        evidence=Evidence.CONFIRMED,
        summary=(
            "A configured external MSA file is an existing, readable, non-empty "
            "regular file; automatic search and no-MSA states configure none and "
            "are never reported here. A missing filesystem port reports 'not "
            "checked' rather than a false error (plan §9.6)."
        ),
        mapping_ids=("MAP-602", "MAP-603", "MAP-604", "MAP-605", "MAP-606"),
    ),
)

# ---------------------------------------------------------------------------
# Template validation (spec §19 "Template validation")
# ---------------------------------------------------------------------------

TEMPLATE_RULES = (
    Rule(
        rule_id="R-TPL-001",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="12. Structural Templates",
        evidence=Evidence.CONFIRMED,
        summary="Templates are supported only on protein chains.",
        mapping_ids=("MAP-705", "MAP-1207"),
    ),
    Rule(
        rule_id="R-TPL-002",
        tier=Tier.CONTRACT,
        severity=Severity.ERROR,
        spec_ref="12. Structural Templates",
        evidence=Evidence.CONFIRMED,
        summary="mmcif and mmcifPath are mutually exclusive per template.",
        mapping_ids=("MAP-701", "MAP-702"),
    ),
    Rule(
        rule_id="R-TPL-003",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="7. Identifiers and Indexing",
        evidence=Evidence.CONFIRMED,
        summary="Query/template indices are 0-based and are never arithmetic-adjusted.",
        mapping_ids=("MAP-705", "MAP-704", "MAP-905", "MAP-906"),
    ),
    Rule(
        rule_id="R-TPL-004",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="12. Structural Templates",
        evidence=Evidence.CONFIRMED,
        summary="Query and template index arrays form a parallel mapping of equal length.",
        mapping_ids=("MAP-703", "MAP-704"),
    ),
    Rule(
        rule_id="R-TPL-005",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="12. Structural Templates",
        evidence=Evidence.CONFIRMED,
        summary="Up to 20 templates per protein chain (current source docstring).",
        mapping_ids=("MAP-705", "MAP-1207"),
    ),
)

# ---------------------------------------------------------------------------
# Ligand / bond validation (spec §19 "Ligand / bond validation")
# ---------------------------------------------------------------------------

BOND_RULES = (
    Rule(
        rule_id="R-BND-001",
        tier=Tier.CONTRACT,
        severity=Severity.ERROR,
        spec_ref="5. Data Families / Entity Types",
        evidence=Evidence.CONFIRMED,
        summary="Ions are represented as ligands with a CCD code; there is no ion entity.",
        mapping_ids=("MAP-405", "MAP-008"),
    ),
    Rule(
        rule_id="R-BND-002",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="13. Covalent Bonds",
        evidence=Evidence.CONFIRMED,
        summary="A SMILES-only ligand cannot be an endpoint of an explicit bond.",
        mapping_ids=("MAP-403", "MAP-807"),
    ),
    Rule(
        rule_id="R-BND-003",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="13. Covalent Bonds",
        evidence=Evidence.CONFIRMED,
        summary="Bond endpoints resolve to entity/residue/atom triples (chain, 1-based residue, atom name).",
        mapping_ids=("MAP-801", "MAP-802", "MAP-803", "MAP-804", "MAP-805", "MAP-806"),
    ),
    Rule(
        rule_id="R-BND-004",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="7. Identifiers and Indexing",
        evidence=Evidence.CONFIRMED,
        summary="Bond residue IDs are 1-based (a single-residue ligand uses residue 1).",
        mapping_ids=("MAP-904", "MAP-802", "MAP-805"),
    ),
    Rule(
        rule_id="R-BND-005",
        tier=Tier.STRUCTURAL,
        severity=Severity.ERROR,
        spec_ref="13. Covalent Bonds",
        evidence=Evidence.CONFIRMED,
        summary="All explicit bonds are covalent; no other bond type exists in the model.",
        mapping_ids=("MAP-807",),
    ),
    Rule(
        rule_id="R-BND-006",
        tier=Tier.RELATIONAL,
        severity=Severity.ERROR,
        spec_ref="13. Covalent Bonds",
        evidence=Evidence.DOCUMENTED,
        summary="Polymer-polymer covalent bonds through this field are unsupported and rejected.",
        mapping_ids=("MAP-807",),
    ),
)

# ---------------------------------------------------------------------------
# Version selection (plan §10.3, resting on spec §3/§18)
# ---------------------------------------------------------------------------

VERSION_RULES = (
    Rule(
        rule_id="R-VER-001",
        tier=Tier.CONTRACT,
        severity=Severity.ERROR,
        spec_ref="18. Versioning",
        evidence=Evidence.CONFIRMED,
        summary=(
            "Save and generation need an explicit JSON format version; Unverified "
            "is the blocking state. No deployment evidence or prior run is required."
        ),
        mapping_ids=("MAP-108",),
    ),
    Rule(
        rule_id="R-VER-002",
        tier=Tier.CONTRACT,
        severity=Severity.ERROR,
        spec_ref="18. Versioning",
        evidence=Evidence.CONFIRMED,
        summary=(
            "A feature requiring a version above the evidenced pin is an error naming "
            "the feature; the version is never silently raised."
        ),
        mapping_ids=("MAP-108",),
    ),
)

# ---------------------------------------------------------------------------
# VARIANT-tier rules (plan §12.5, §9.2 tier table).
#
# These compare a variant against its base. Because plan §5.3 rule 2 keeps
# ``variants``, ``validation``, and ``transform`` mutually independent, the
# facts they consume (wire documents, declared-change descriptors) arrive
# through ``ValidationContext`` as plain data; ``app`` performs the joining.
# Without those facts in the context, the rules report "not checked" as a
# WARNING rather than pretending the variant is clean (plan §9.6).
# ---------------------------------------------------------------------------

VARIANT_RULES = (
    Rule(
        rule_id="R-VAR-001",
        tier=Tier.VARIANT,
        severity=Severity.ERROR,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.PROJECT_SPECIFIC,
        summary=(
            "Undrifted comparison: any difference between a variant's wire document "
            "and the base's must be attributable to a declared edit; anything else "
            "is drift and blocks generation (plan §12.5)."
        ),
        mapping_ids=("MAP-014", "MAP-103"),
    ),
    Rule(
        rule_id="R-VAR-002",
        tier=Tier.VARIANT,
        severity=Severity.ERROR,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.PROJECT_SPECIFIC,
        summary=(
            "Identity stability: record identifiers survive expansion unchanged, and "
            "released identifiers are not reused within an expansion run (plan §8.3, §12.4)."
        ),
        mapping_ids=("MAP-014", "MAP-901"),
    ),
)

# ---------------------------------------------------------------------------
# Rules deliberately NOT promoted to confirmed AF3 requirements
# (spec §19 final section; plan §9.3: INFO-only so no future change can
# silently turn a non-rule into a gate)
# ---------------------------------------------------------------------------

NON_PROMOTED_RULES = (
    Rule(
        rule_id="R-POL-001",
        tier=Tier.VARIANT,
        severity=Severity.INFO,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.PROJECT_POLICY,
        summary="Seed-list uniqueness is a project policy, not an AF3 requirement (spec §14).",
        mapping_ids=("MAP-907",),
    ),
    Rule(
        rule_id="R-POL-002",
        tier=Tier.VARIANT,
        severity=Severity.INFO,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.PROJECT_POLICY,
        summary="Seed sorting/ordering is not an AF3 requirement; ordered list is preserved as given.",
        mapping_ids=("MAP-907",),
    ),
    Rule(
        rule_id="R-POL-003",
        tier=Tier.RELATIONAL,
        severity=Severity.INFO,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.PROJECT_POLICY,
        summary="The chain-ID allocation algorithm is a project choice (plan §8.1), not a contract rule.",
        mapping_ids=("MAP-901",),
    ),
    Rule(
        rule_id="R-POL-004",
        tier=Tier.VARIANT,
        severity=Severity.INFO,
        spec_ref="14. Reproducibility / Model Seeds",
        evidence=Evidence.PROJECT_POLICY,
        summary="The project's fixed set of 10 seeds is a comparison policy, not an AF3 schema rule.",
        mapping_ids=("MAP-102",),
    ),
    Rule(
        rule_id="R-POL-005",
        tier=Tier.RELATIONAL,
        severity=Severity.INFO,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.UNRESOLVED,
        summary="Biological validity of a requested PTM/site is out of scope (spec §21 non-goals).",
        mapping_ids=("MAP-009",),
    ),
    Rule(
        rule_id="R-POL-006",
        tier=Tier.RELATIONAL,
        severity=Severity.INFO,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.UNRESOLVED,
        summary="Scientific plausibility of any modification is out of scope (spec §21 non-goals).",
        mapping_ids=("MAP-009",),
    ),
    Rule(
        rule_id="R-POL-007",
        tier=Tier.VARIANT,
        severity=Severity.INFO,
        spec_ref="19. Validation Matrix",
        evidence=Evidence.PROJECT_POLICY,
        summary="Seed-set stability across variants is a project policy reported as a finding (plan §12.5).",
        mapping_ids=("MAP-102", "MAP-014"),
    ),
)

RULES = (
    ROOT_RULES
    + ENTITY_RULES
    + MSA_RULES
    + TEMPLATE_RULES
    + BOND_RULES
    + VERSION_RULES
    + VARIANT_RULES
    + NON_PROMOTED_RULES
)


def rules_by_tier():
    """Catalogue grouped in engine execution order (plan §9.2)."""
    return {tier: tuple(r for r in RULES if r.tier is tier) for tier in TIER_ORDER}


def get_rule(rule_id: str) -> Rule:
    for rule in RULES:
        if rule.rule_id == rule_id:
            return rule
    raise KeyError(rule_id)
