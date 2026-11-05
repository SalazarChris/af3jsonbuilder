"""Variant spec editing (IMPLEMENTATION_PLAN.md §15): ``VariantService``.

``add_spec`` / ``update_spec`` / ``remove_spec`` / ``duplicate_spec``
maintain the project's spec list; ``preview`` expands a single spec
without committing it; ``expand`` materialises the whole set. Edit
failures (unknown record keys, identifier conflicts) come back as
failure reasons — never exceptions.
"""

from __future__ import annotations

from configbuilder.app.results import (
    ExpandOutput,
    FailureReason,
    FilePreview,
    MutationOutput,
)
from configbuilder.identity import EntityId
from configbuilder.model import ByCode, ByNotation, ModelError, SequenceText
from configbuilder.model.records import (
    ComponentRecord,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
)
from configbuilder.variants import (
    EditError,
    VariantSpec,
    VariantSpecError,
    describe_edit,
    expand,
)

__all__ = [
    "ChoiceError",
    "EntityRow",
    "TargetPlan",
    "TargetPlanRow",
    "TARGET_STRATEGIES",
    "VariantChoice",
    "VariantService",
]

#: The input kind each entity family reads through, for callers that still speak
#: in families. The kinds themselves are ``batch_variants.INPUT_KINDS``; this is
#: a translation, not a second vocabulary.
_KIND_FOR_FAMILY = {
    "protein": "protein-sequence",
    "dna": "dna-sequence",
    "rna": "rna-sequence",
    "ligand": "ligand-smiles",
}


#: The entity family each input kind can *replace*: the inverse of
#: ``_KIND_FOR_FAMILY`` plus the two ligand kinds, which both act on a
#: component record. A file of one kind may only replace an entity of its own
#: family — a protein list cannot re-sequence a ligand.
_REPLACE_FAMILY = {
    "protein-sequence": "protein",
    "dna-sequence": "dna",
    "rna-sequence": "rna",
    "ligand-smiles": "ligand",
    "ligand-ccd": "ligand",
}


class ChoiceError(Exception):
    """A UI-facing choice payload is unusable (bad table shape, unknown
    template route). User-caused, so it surfaces as a refusal — never an
    exception escaping into a front end."""


class VariantChoice:
    """One numbered choice in a UI table: label (human wording, may
    carry the record key for orientation), ``kind`` discriminator, and
    the value the front end passes back. Plain data — no behaviour."""

    __slots__ = ("label", "kind", "value", "detail")

    def __init__(self, label, kind, value=None, detail=None):
        self.label = label
        self.kind = kind
        self.value = value
        self.detail = detail


#: The strategies that vary *one entity at a time*, and the families each can
#: act on — the multi-ligand / small-protein workflow's whole vocabulary.
#:
#: This table is the single authority for two things: the "can vary" column the
#: target picker shows (``entity_table``) and the early refusal a wrong-family
#: target gets (``_family_target_failure``). A strategy therefore cannot be
#: offered for a family that expansion would reject, and a front end never has
#: to keep its own copy of the rule.
TARGET_STRATEGIES = (
    ("sequence", "Sequence change", ("protein", "rna", "dna")),
    ("component_representation", "Ligand representation (SMILES)", ("ligand",)),
    ("component_count", "Component copy count", ("ligand",)),
    ("add_modification", "Add a modification", ("protein", "rna", "dna")),
    ("remove_modification", "Remove a modification", ("protein", "rna", "dna")),
    ("alignment", "MSA (alignment)", ("protein", "rna")),
    ("references", "Structural templates", ("protein",)),
    ("remove_entity", "Remove the entity", ("protein", "rna", "dna", "ligand")),
)

_STRATEGY_BY_KIND = {
    kind: (label, families) for kind, label, families in TARGET_STRATEGIES
}

#: What a reader needs to know about a family *before* choosing a strategy.
#: Empty for the protein case: nothing about it limits the vocabulary.
_FAMILY_NOTES = {
    "protein": "",
    "rna": "RNA carries one MSA field; it has no paired side.",
    "dna": "A DNA record has no MSA field in the input format.",
    "ligand": "A ligand has no sequence or MSA; vary its representation or copies.",
}


class EntityRow:
    """One base entity as the target picker shows it (`plan §15`).

    One row per *record*: ``copies`` is the record's multiplicity, so a ligand
    present twice is one entity with two copies — an entity definition, not a
    chain instance. ``kinds`` is the target strategies this family supports,
    from :data:`TARGET_STRATEGIES`.
    """

    __slots__ = ("key", "family", "copies", "summary", "kinds", "note")

    def __init__(self, key, family, copies, summary, kinds, note="") -> None:
        self.key = key
        self.family = family
        self.copies = copies
        self.summary = summary
        self.kinds = tuple(kinds)
        self.note = note

    def can(self, kind: str) -> bool:
        """Whether this entity supports ``kind``."""
        return kind in self.kinds

    def __repr__(self) -> str:
        return "EntityRow(%r, %s, copies=%d)" % (self.key, self.family, self.copies)


class TargetPlanRow:
    """One planned variant: the entity, its key, and the edits to apply."""

    __slots__ = ("key", "family", "label", "spec_key", "edits", "described")

    def __init__(self, key, family, label, spec_key, edits, described) -> None:
        self.key = key
        self.family = family
        self.label = label
        self.spec_key = spec_key
        self.edits = tuple(edits)
        self.described = tuple(described)

    def __repr__(self) -> str:
        return "TargetPlanRow(%r -> %r)" % (self.key, self.spec_key)


class TargetPlan:
    """What selecting a set of entities and one strategy would create.

    ``ok`` is False when *any* selected entity cannot take the change, because
    the commit is all-or-nothing: a partial batch would leave the user with
    variants they did not ask for. ``message`` then names every target and its
    reason. ``count`` is the number of variants a commit would add — the
    number a user must see before pressing the button.
    """

    __slots__ = ("ok", "rows", "failures", "message", "unchanged_keys")

    def __init__(self, ok, rows=(), failures=(), message="", unchanged_keys=()) -> None:
        self.ok = bool(ok)
        self.rows = tuple(rows)
        self.failures = tuple(failures)
        self.message = message or ""
        self.unchanged_keys = tuple(unchanged_keys)

    @property
    def count(self) -> int:
        return len(self.rows)

    @property
    def spec_keys(self) -> tuple:
        return tuple(row.spec_key for row in self.rows)

    def __repr__(self) -> str:
        return "TargetPlan(ok=%r, count=%d, failures=%d)" % (
            self.ok,
            self.count,
            len(self.failures),
        )


class VariantService:
    """Maintains the open project's variant specs."""

    def __init__(self, projects, configuration=None) -> None:
        self._projects = projects
        self._configuration = configuration

    # -- helpers ---------------------------------------------------------------

    def _specs(self):
        return self._projects._specs()

    def _not_open(self):
        return MutationOutput(ok=False, failure_reason=FailureReason.NOT_OPEN, message="no project is open")

    def _find(self, key: str):
        for spec in self._specs():
            if spec.key == key:
                return spec
        return None

    @staticmethod
    def _validate_spec_value(key: str, label: str, edits):
        try:
            return VariantSpec(key=key, label=label, edits=tuple(edits)), None
        except (VariantSpecError, EditError) as error:
            return None, MutationOutput(
                ok=False, failure_reason=FailureReason.NO_PATH, message=str(error)
            )

    # -- spec CRUD (§15) ----------------------------------------------------------

    def add_spec(self, key: str, label: str, edits=()) -> MutationOutput:
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        if self._find(key) is not None:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="a variant keyed %r already exists; keys are unique" % (key,),
            )
        spec, failure = self._validate_spec_value(key, label, edits)
        if failure is not None:
            return failure
        self._projects._with_specs(self._specs() + (spec,))
        return MutationOutput(ok=True)

    def update_spec(self, key: str, label=None, edits=None) -> MutationOutput:
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        existing = self._find(key)
        if existing is None:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.UNKNOWN_RECORD,
                message="no variant keyed %r exists" % (key,),
            )
        new_label = existing.label if label is None else label
        new_edits = existing.edits if edits is None else tuple(edits)
        spec, failure = self._validate_spec_value(key, new_label, new_edits)
        if failure is not None:
            return failure
        self._projects._with_specs(
            tuple(spec if s.key == key else s for s in self._specs())
        )
        return MutationOutput(ok=True)

    def remove_spec(self, key: str) -> MutationOutput:
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        if self._find(key) is None:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.UNKNOWN_RECORD,
                message="no variant keyed %r exists" % (key,),
            )
        self._projects._with_specs(tuple(s for s in self._specs() if s.key != key))
        return MutationOutput(ok=True)

    def add_spec_from_factor(
        self, key: str, factor: str, value, label: str = "", record_key=None
    ) -> MutationOutput:
        """The guided factor picker (plan §16.4): the user picks
        a factor and supplies a value; the builder writes the edits.

        Factors are the declared-change vocabulary of spec §15
        (``_FACTOR_BY_EDIT``'s targets). The edit objects are built here
        in ``app`` — ``ui`` never constructs variant vocabulary."""
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        try:
            edit, failure = self._factor_edit(project, factor, value, record_key)
            if failure is not None:
                return self._refuse(failure)
        except (EditError, VariantSpecError, ValueError, TypeError) as error:
            return self._refuse(str(error))
        return self.add_spec(key, label or key, (edit,))

    @staticmethod
    def _edit_class(name: str):
        from configbuilder import variants as _v

        return getattr(_v, name)

    @staticmethod
    def _sole_polymer_key(project):
        polymers = [
            record.ids.primary.value
            for record in project.configuration.records
            if hasattr(record, "sequence")
        ]
        return polymers[0] if len(polymers) == 1 else None

    @staticmethod
    def _family_of_key(project, key: str) -> str:
        """The family alphabet of the record identified by ``key``
        (protein/rna/dna), from the record's own type — the picker never
        guesses an alphabet from the text.

        A key the registry holds but that names a record with no sequence
        (a ligand) is refused in those terms: the record *does* exist, so
        "no record is identified by 'A'" sent the user looking for a
        mistake that was not there.
        """
        for record in project.configuration.records:
            if record.ids.primary.value == key:
                family = {
                    "FamilyARecord": "protein",
                    "FamilyBRecord": "rna",
                    "FamilyCRecord": "dna",
                }.get(type(record).__name__)
                if family:
                    return family
                raise EditError(
                    "record %r is a ligand; only a protein, RNA or DNA chain "
                    "carries a sequence or an MSA" % key
                )
        raise EditError("no record is identified by %r" % key)

    @staticmethod
    def _modification_target_failure(project, record_key):
        """Why ``record_key`` cannot carry a modification, or ``None``.

        The modification vocabulary applies to the polymer families only;
        a variant edit aimed at a ligand can never expand, so it is refused
        where the user composes it instead of surfacing later as an
        expansion failure (the variant-side twin of
        ``ConfigurationService.add_modification``'s own guard).
        """
        for record in project.configuration.records:
            if record.ids.primary.value == record_key:
                if isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord)):
                    return None
                return (
                    "record %r is a ligand; modifications belong to a protein, "
                    "RNA or DNA chain" % (record_key,)
                )
        return "no record is identified by %r" % (record_key,)

    def _refuse(self, message: str) -> MutationOutput:
        return MutationOutput(ok=False, failure_reason=FailureReason.NO_PATH, message=message)

    def duplicate_spec(self, key: str, new_key: str, new_label: str = "") -> MutationOutput:
        """Copy an existing spec under a fresh key."""
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        existing = self._find(key)
        if existing is None:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.UNKNOWN_RECORD,
                message="no variant keyed %r exists" % (key,),
            )
        if self._find(new_key) is not None:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="a variant keyed %r already exists; keys are unique" % (new_key,),
            )
        label = new_label or ("%s (copy)" % existing.label)
        spec, failure = self._validate_spec_value(new_key, label, existing.edits)
        if failure is not None:
            return failure
        self._projects._with_specs(self._specs() + (spec,))
        return MutationOutput(ok=True)

    # -- expansion (§15 preview / expand) ---------------------------------------------

    def preview(self, key: str):
        """Expand one spec against the open base without committing.

        Returns an ``ExpandOutput``; the variant's configuration is fully
        materialised and the project's committed spec list is untouched.
        """
        project = self._projects._require_project()
        if project is None:
            return ExpandOutput(ok=False, failure_reason=FailureReason.NOT_OPEN, message="no project is open")
        spec = self._find(key)
        if spec is None:
            return ExpandOutput(
                ok=False,
                failure_reason=FailureReason.UNKNOWN_RECORD,
                message="no variant keyed %r exists" % (key,),
            )
        return self._expand_specs((spec,))

    def expand(self, only=None):
        """Expand every committed spec, in declared order (§12.2).

        ``only`` (an iterable of keys) restricts the expansion to those
        specs — the subset-export route. Unknown keys refuse; an empty
        ``only`` means "no keys selected", not "everything".
        """
        project = self._projects._require_project()
        if project is None:
            return ExpandOutput(ok=False, failure_reason=FailureReason.NOT_OPEN, message="no project is open")
        specs = self._specs()
        if only is None:
            return self._expand_specs(specs)
        keys = tuple(only)
        known = {spec.key for spec in specs}
        unknown = [key for key in keys if key not in known]
        if unknown:
            return ExpandOutput(
                ok=False,
                failure_reason=FailureReason.UNKNOWN_RECORD,
                message="no variant keyed %r exists" % (unknown[0],),
            )
        selected = tuple(spec for key in keys for spec in specs if spec.key == key)
        return self._expand_specs(selected)

    def _factor_edit(self, project, factor: str, value, record_key=None):
        """The picker's factor → edit conversion (plan §16.4).

        Factors are the declared-change vocabulary of spec §15
        (``_FACTOR_BY_EDIT``'s targets). Returns ``(edit, None)`` on
        success and ``(None, message)`` on refusal — the edit objects are
        built here in ``app``: ``ui`` never constructs variant vocabulary.
        """
        try:
            if factor == "sequence":
                target = record_key or self._sole_polymer_key(project)
                if target is None:
                    return None, "choose the record the sequence change applies to"
                # The alphabet is the *target record's family*, known from
                # the configuration — never guessed from the text.
                alphabet = self._family_of_key(project, target)
                text = SequenceText(value, alphabet)
                return self._edit_class("SetSequence")(EntityId(target), text), None
            elif factor == "job_name":
                return self._edit_class("SetName")(value), None
            elif factor == "job_description":
                # The edit vocabulary stores the job description as a
                # Presence value (the presence algebra, plan §7.4): a
                # picker string means "present with this text".
                from configbuilder.model.presence import Present

                return self._edit_class("SetJobDescription")(Present(value)), None
            elif factor == "seeds":
                return self._edit_class("SetSeeds")(
                    [int(part) for part in str(value).replace(",", " ").split()]
                ), None
            else:
                return None, (
                    "the factor %r is not offered by the picker yet; "
                    "extend add_spec_from_factor" % (factor,)
                )
        except (EditError, VariantSpecError, ModelError, ValueError, TypeError) as error:
            # ``ModelError`` is the model's own base for a refused value
            # (``SequenceTextError`` for an alphabet violation) and does
            # **not** derive from ``ValueError``, so catching only
            # ``ValueError`` let a wrong-alphabet sequence escape as a
            # traceback out of ``apply_variant_edit`` (BUG-021).
            return None, str(error)

    def append_factor(self, key: str, factor: str, value, record_key=None):
        """Add one factor edit to an existing spec, keeping its others.

        The variant-editing route behind "edit a variant" in a free-
        navigation UI: the conversion is the picker's (``_factor_edit``
        builds the edit) and ``update_spec`` commits the extended tuple,
        so a variant is grown without ever rebuilding it.
        """
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        existing = self._find(key)
        if existing is None:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.UNKNOWN_RECORD,
                message="no variant keyed %r exists" % (key,),
            )
        edit, failure = self._factor_edit(project, factor, value, record_key)
        if failure is not None:
            return self._refuse(failure)
        return self.update_spec(key, edits=existing.edits + (edit,))

    # -- UI choice tables (§15 vocabulary as numbered menus; the UI never
    #    constructs edits itself — every table answers "what can this
    #    variant change" from the same authority the edits come from) -----

    def edit_options(self) -> "tuple[VariantChoice, ...]":
        """The change kinds a variant can make, as UI choices.

        Every option here maps onto ``_factor_edit`` or
        ``apply_variant_edit`` — nothing is offered that the service
        cannot perform.
        """
        return (
            VariantChoice("Sequence change", "sequence"),
            VariantChoice("Add a modification", "add_modification"),
            VariantChoice("Remove a modification", "remove_modification"),
            VariantChoice("MSA (alignment)", "alignment"),
            VariantChoice("Structural templates", "references"),
            VariantChoice("Job name", "job_name"),
            VariantChoice("Job description", "job_description"),
            VariantChoice("Model seeds", "seeds"),
            VariantChoice("Component copy count", "component_count"),
            VariantChoice("Ligand representation (SMILES)", "component_representation"),
            VariantChoice("Add a new entity", "add_entity"),
            VariantChoice("Remove an entity", "remove_entity"),
        )

    def entity_choices(self, family: str) -> "tuple[VariantChoice, ...]":
        """The base's records of one family, as choice rows.

        ``label`` is deliberately **data, not wording** (``app`` cannot
        import the UI's string registry): the front end renders the row
        through its own registered templates. ``value`` is the internal
        key — resolved here, never typed.
        """
        project = self._projects._require_project()
        if project is None:
            return ()
        type_by_family = {
            "protein": FamilyARecord,
            "rna": FamilyBRecord,
            "dna": FamilyCRecord,
            "ligand": ComponentRecord,
        }
        type_ = type_by_family.get(family)
        if type_ is None:
            return ()
        choices = []
        for record in project.configuration.records:
            if not isinstance(record, type_):
                continue
            key = record.ids.primary.value
            choices.append(VariantChoice(key, family, key))
        return tuple(choices)

    def all_entity_choices(self) -> "tuple[VariantChoice, ...]":
        """Every base record across families, as choice rows (the
        sequence-change target picker)."""
        project = self._projects._require_project()
        if project is None:
            return ()
        return tuple(
            VariantChoice(record.ids.primary.value, "entity", record.ids.primary.value)
            for record in project.configuration.records
        )

    def build_add_records(self, family: str, sequence: str, representation="", representation_kind=""):
        """The record(s) one add-entity edit adds: ``(records, None)`` or
        ``((), message)``.

        Construction is delegated to the configuration service's own
        ``_build_records`` — the same validated constructors, the same
        DNA-duplex rule, allocation from a **throwaway clone** of the
        base registry (the base never claims the ids; ``AddRecord``
        reserves them again inside each expansion). A DNA family add
        therefore yields the two-strand duplex, exactly like the base
        entity path.
        """
        project = self._projects._require_project()
        if project is None:
            return (), "no project is open"
        if self._configuration is None:
            return (), "entity adds need the configuration service"
        registry = project.configuration.identity.clone()
        records, failure = self._configuration._build_records(
            family, sequence, representation, 1, registry,
            representation_kind=representation_kind,
        )
        if failure is not None:
            return (), failure.message or "refused"
        return tuple(records), None

    def modification_summary(self, key: str):
        """The variant's modification rows, as the remove picker shows them.

        Each row is ``(index, "<record> @ <position> (<code>)")`` where
        ``index`` is the modification's place in the **expanded** record's
        own modification list — the list ``RemoveModification`` indexes
        when the edit applies.

        Reading the indices from the expansion (rather than counting this
        spec's own ``AddModification`` rows) is the whole point: the two
        numberings differ as soon as the base record already carries a
        modification, and the mismatched index deleted the *base's*
        modification while keeping the one the user had picked (BUG-025).
        ``[]`` means the variant cannot expand, or its records carry no
        modifications to offer.
        """
        if self._find(key) is None:
            return []
        expanded = self.preview(key)
        if not expanded.ok:
            return []
        summary = []
        for record in expanded.variants[0].configuration.records:
            record_key = record.ids.primary.value
            for index, modification in enumerate(
                getattr(record, "modifications", ()) or ()
            ):
                summary.append(
                    (
                        index,
                        "%s @ %s (%s)"
                        % (
                            record_key,
                            modification.position.value,
                            modification.code.value,
                        ),
                    )
                )
        return summary

    def _edits_for_kind(self, project, kind, value, record_key=None):
        """The edit(s) one change kind builds: ``(edits, None)`` or
        ``((), message)``.

        The single place the UI vocabulary is turned into variant edits, so
        ``apply_variant_edit`` (an existing spec) and
        ``add_spec_with_edit`` (a new one) cannot diverge. Every kind here is
        one ``edit_options`` offers; anything else refuses.
        """
        if kind in ("sequence", "job_name", "job_description", "seeds"):
            edit, failure = self._factor_edit(project, kind, value, record_key)
            if failure is not None:
                return (), failure
            return (edit,), None
        if kind == "add_modification":
            code, position = value
            failure = self._modification_target_failure(project, record_key)
            if failure is not None:
                return (), failure
            try:
                code_value, position_value = self._modification_values(code, int(position))
                edit = self._edit_class("AddModification")(
                    EntityId(record_key), code_value, position_value
                )
            except (EditError, ModelError, ValueError, TypeError) as error:
                return (), str(error)
            return (edit,), None
        if kind == "remove_modification":
            failure = self._modification_target_failure(project, record_key)
            if failure is not None:
                return (), failure
            try:
                edit = self._edit_class("RemoveModification")(
                    EntityId(record_key), int(value)
                )
            except (EditError, ValueError, TypeError) as error:
                return (), str(error)
            return (edit,), None
        if kind == "alignment":
            # The alignment case is the target's own: a protein carries the
            # paired/unpaired cases (``SetAlignment``), an RNA the single one
            # (``SetSingleAlignment``). Any other family has no MSA field in
            # the input format at all.
            try:
                family = self._family_of_key(project, record_key)
                if family == "rna":
                    edit = self._edit_class("SetSingleAlignment")(
                        EntityId(record_key), self._single_alignment_case(value)
                    )
                elif family == "protein":
                    edit = self._edit_class("SetAlignment")(
                        EntityId(record_key), self._alignment_case(value)
                    )
                else:
                    return (), (
                        "record %r is a %s chain; an alignment belongs to a "
                        "protein or an RNA chain" % (record_key, family)
                    )
            except (EditError, ChoiceError, ValueError, TypeError) as error:
                return (), str(error)
            return (edit,), None
        if kind == "references":
            try:
                reference_set = self._reference_set_case(value)
            except ChoiceError as error:
                return (), str(error)
            try:
                edit = self._edit_class("SetReferences")(
                    EntityId(record_key), reference_set
                )
            except (EditError, ValueError, TypeError) as error:
                return (), str(error)
            return (edit,), None
        if kind == "add_entity":
            try:
                edits = tuple(
                    self._edit_class("AddRecord")(record) for record in value
                )
            except (EditError, ValueError, TypeError) as error:
                return (), str(error)
            return edits, None
        if kind == "component_count":
            failure = self._family_target_failure(project, kind, record_key)
            if failure is not None:
                return (), failure
            try:
                count = int(str(value).strip())
            except (TypeError, ValueError):
                # A front end's text field is not an integer; say so in the
                # user's terms rather than letting int() word the refusal.
                return (), "the copy count must be a whole number (got %r)" % (value,)
            try:
                edit = self._edit_class("SetComponentCount")(
                    EntityId(record_key), count
                )
            except (EditError, ValueError, TypeError) as error:
                return (), str(error)
            return (edit,), None
        if kind == "component_representation":
            # A ligand's representation is CCD codes or SMILES and nothing
            # else; this kind writes the SMILES case, which is the one a user
            # can type. Replacing a CCD representation with SMILES is the
            # documented meaning of the change (spec §15).
            failure = self._family_target_failure(project, kind, record_key)
            if failure is not None:
                return (), failure
            try:
                edit = self._edit_class("SetComponentRepresentation")(
                    EntityId(record_key), ByNotation(str(value).strip())
                )
            except (EditError, ModelError, ValueError, TypeError) as error:
                return (), str(error)
            return (edit,), None
        if kind == "remove_entity":
            try:
                edit = self._edit_class("RemoveRecord")(EntityId(record_key))
            except (EditError, ValueError, TypeError) as error:
                return (), str(error)
            return (edit,), None
        return (), "unknown change kind %r" % (kind,)

    def modification_choices(self, key: str):
        """The variant's modification rows with the record each belongs to.

        ``modification_summary`` keeps the console's two-column shape; a
        free-navigation UI must target the record as well as the index, so
        this returns ``(index, record_key, display)`` rows from the same
        expansion. ``[]`` means the variant cannot expand or has none.
        """
        if self._find(key) is None:
            return []
        expanded = self.preview(key)
        if not expanded.ok:
            return []
        rows = []
        for record in expanded.variants[0].configuration.records:
            record_key = record.ids.primary.value
            for index, modification in enumerate(
                getattr(record, "modifications", ()) or ()
            ):
                rows.append(
                    (
                        index,
                        record_key,
                        "%s @ %s (%s)"
                        % (
                            record_key,
                            modification.position.value,
                            modification.code.value,
                        ),
                    )
                )
        return rows

    def apply_variant_edit(self, key: str, kind: str, value, record_key=None) -> MutationOutput:
        """Apply one menu-selected change kind to an existing spec.

        The menu passes the ``kind`` from ``edit_options``; the edit
        construction stays here, in ``app``. Kinds outside the table
        refuse — the UI can never invent an edit the vocabulary lacks.
        """
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        existing = self._find(key)
        if existing is None:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.UNKNOWN_RECORD,
                message="no variant keyed %r exists" % (key,),
            )
        edits, failure = self._edits_for_kind(project, kind, value, record_key)
        if failure is not None:
            return self._refuse(failure)
        return self.update_spec(key, edits=existing.edits + edits)

    def describe_change(self, kind: str, value, record_key=None):
        """Describe the change a UI is about to add, without committing it.

        ``(descriptions, None)`` or ``([], message)``: the edit(s) are built
        by the same ``_edits_for_kind`` path ``apply_variant_edit`` uses and
        run through ``describe_edit``, so a preview cannot show a change the
        service would refuse or describe it differently.
        """
        project = self._projects._require_project()
        if project is None:
            return [], "no project is open"
        edits, failure = self._edits_for_kind(project, kind, value, record_key)
        if failure is not None:
            return [], failure
        return [describe_edit(edit) for edit in edits], None

    def add_spec_with_edit(self, key: str, label: str, kind: str, value, record_key=None) -> MutationOutput:
        """Create a spec and its first declared change as one commit.

        Creating the spec first and appending the edit afterwards would
        leave an empty variant behind when the edit is refused. Both parts
        are therefore built and validated before ``add_spec`` commits — the
        same construction ``apply_variant_edit`` uses, never a second one.
        """
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        if self._find(key) is not None:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message="a variant keyed %r already exists; keys are unique" % (key,),
            )
        edits, failure = self._edits_for_kind(project, kind, value, record_key)
        if failure is not None:
            return self._refuse(failure)
        return self.add_spec(key, label, edits)

    @staticmethod
    def _modification_values(code: str, position: int):
        from configbuilder.model import ComponentCode, Position

        return ComponentCode(code), Position(position)

    @staticmethod
    def _alignment_case(value):
        from configbuilder.model import (
    AlignmentAutomatic,
            AlignmentBoth,
            AlignmentFree,
            AlignmentPairedOnly,
            AlignmentUnpairedOnly,
            External,
            Inline,
            PathSpec,
        )

        mode, source = value
        if mode == "automatic":
            return AlignmentAutomatic()
        if mode == "free":
            return AlignmentFree()
        if source is None:
            raise ChoiceError("mode %r carries an MSA source; none was given" % (mode,))
        if source[0] == "inline":
            payload = Inline(source[1])
        else:
            payload = External(PathSpec(source[1]))
        if mode == "unpaired":
            return AlignmentUnpairedOnly(payload)
        if mode == "paired":
            return AlignmentPairedOnly(payload)
        if mode == "both":
            return AlignmentBoth(payload)
        raise ChoiceError("unknown alignment mode %r" % (mode,))

    @staticmethod
    def _single_alignment_case(value):
        """The RNA alignment case for the collected mode/source: automatic
        (search), free (MSA-free), provided (a source is required)."""
        from configbuilder.model import (
            External,
            Inline,
            PathSpec,
            SingleAutomatic,
            SingleFree,
            SingleProvided,
        )

        mode, source = value
        if mode == "automatic":
            return SingleAutomatic()
        if mode == "free":
            return SingleFree()
        if source is None:
            raise ChoiceError("mode %r carries an MSA source; none was given" % (mode,))
        payload = Inline(source[1]) if source[0] == "inline" else External(PathSpec(source[1]))
        if mode == "provided":
            return SingleProvided(payload)
        raise ChoiceError("unknown RNA alignment mode %r" % (mode,))

    @staticmethod
    def _reference_set_case(value):
        from configbuilder.model import (
            Explicit,
            External,
            IndexPair,
            Inline,
            PathSpec,
            ReferenceRecord,
            SearchAllowed,
        )

        route, payload = value
        if route == "search":
            return SearchAllowed()
        if route == "none":
            return Explicit(())
        # payload is a list of (source_kind, text, pairs) rows
        records = []
        for source_kind, text, pairs in payload:
            if source_kind == "inline":
                source = Inline(text)
            else:
                source = External(PathSpec(text))
            index_map = tuple(IndexPair(int(q), int(t)) for q, t in pairs)
            records.append(ReferenceRecord(source, index_map))
        return Explicit(tuple(records))

    def describe_spec_edits(self, key: str):
        """Every edit of one spec as described data (``describe_edit``),
        in order — the preview's change list as plain data; the front end
        renders it through its own registered wording."""
        project = self._projects._require_project()
        if project is None:
            return []
        spec = self._find(key)
        if spec is None:
            return []
        return [describe_edit(edit) for edit in spec.edits]

    def spec_change_descriptions(self, key: str):
        """The variant list's change summaries as plain ``(kind,
        described, record)`` rows — no wording (``app`` cannot import
        the UI's string registry); the front end renders each row
        through its registered templates."""
        rows = []
        for described in self.describe_spec_edits(key):
            kind = described.get("kind", "")
            record = described.get("record_key", "") or ""
            rows.append((kind, described, record))
        return rows

    def component_count_choices(self) -> "tuple[VariantChoice, ...]":
        """The base's ligand/component records — the only records whose
        copy count is a variable dimension — as choice rows. ``value``
        is the primary key; ``label`` carries the family word (data, not
        wording); ``detail`` is the row's current copy count."""
        project = self._projects._require_project()
        if project is None:
            return ()
        return tuple(
            VariantChoice(
                record.ids.primary.value, "component",
                record.ids.primary.value, len(record.ids.ids),
            )
            for record in project.configuration.records
            if isinstance(record, ComponentRecord)
        )

    def quantity_series_plan(self, keys, start: int, factor: int, levels: int):
        """The concentration/quantity series as reviewable data —
        **no variant is created here** (§7: preview before creation).

        ``keys`` are ligand primary keys; ``levels`` variants are planned
        at multipliers ``start * factor**(level-1)``. Each level is one
        spec of independent ``base + SetComponentCount(key, count)``
        edits — derived from the base, never from a sibling variant.
        Returns ``(plan_rows, None)`` or ``(None, message)`` where
        ``plan_rows`` is a list of ``(key, {component_key: count})``
        pairs in variant order.
        """
        project = self._projects._require_project()
        if project is None:
            return None, "no project is open"
        known = {record.ids.primary.value for record in project.configuration.records
                 if isinstance(record, ComponentRecord)}
        requested = tuple(keys)
        if not requested:
            return None, "select at least one component to vary"
        unknown = [key for key in requested if key not in known]
        if unknown:
            return None, "no component identified by %r" % (unknown[0],)
        for name, value in (("start", start), ("factor", factor), ("levels", levels)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                return None, (
                    "the series %s must be a whole number of at least 1" % name
                )
        rows = []
        for level in range(1, levels + 1):
            multiplier = start * factor ** (level - 1)
            counts = {key: len(self._find_component(key).ids.ids) * multiplier
                      for key in requested}
            rows.append((multiplier, counts))
        return rows, None

    def create_quantity_series(self, keys, start: int, factor: int, levels: int) -> MutationOutput:
        """Commit the series the picker previewed: one spec per level,
        named ``series_<multiplier>x`` (deterministic keys, regenerable
        on any machine). Commitment is ``add_spec``'s — the standard
        route's guarantees; the base configuration is never touched."""
        rows, failure = self.quantity_series_plan(keys, start, factor, levels)
        if failure is not None:
            return self._refuse(failure)
        created = 0

        def _rollback():
            for done in rows[:created]:
                self.remove_spec("series_%dx" % done[0])

        for multiplier, counts in rows:
            edits = tuple(
                self._edit_class("SetComponentCount")(EntityId(key), count)
                for key, count in sorted(counts.items())
            )
            key = "series_%dx" % multiplier
            if self._find(key) is not None:
                _rollback()
                return self._refuse(
                    "a variant keyed %r already exists; rename or remove it first" % key
                )
            outcome = self.add_spec(key, "series x%d" % multiplier, edits)
            if not outcome.ok:
                _rollback()
                return self._refuse(
                    "variant %r could not be created: %s" % (key, outcome.message)
                )
            created += 1
        return MutationOutput(ok=True, message="%d series variants created" % created)

    def _find_component(self, key: str):
        for record in self._projects._require_project().configuration.records:
            if isinstance(record, ComponentRecord) and record.ids.primary.value == key:
                return record
        raise EditError("no component identified by %r" % key)

    def inspect_sequence_file(self, path: str):
        """Read a sequence file for preview **only** — no variant is
        created. The same persistence reader the committed batch uses,
        so what the user confirms is exactly what would be created."""
        from configbuilder.persistence import PersistenceError, read_sequence_file

        try:
            entries = read_sequence_file(path)
        except PersistenceError as error:
            return FilePreview(ok=False, message=str(error))
        if not entries:
            return FilePreview(
                ok=False, message="the sequence file contains no sequences (only blank lines)"
            )
        return FilePreview(ok=True, entries=[text for _, text in entries])

    def ligand_file_specs(self, path: str, replace_key=None):
        """Read a ligand file and build its independent specs, uncommitted.

        Returns ``(entries, specs, None)`` or ``(entries, (), message)``:
        ``entries`` are the ``(line_number, name, smiles)`` rows exactly as
        ``persistence.read_smiles_file`` read them, so a front end can show
        what would be processed even when the file is refused. The specs are
        ``base + AddRecord`` pairs built against a **throwaway clone** of the
        base registry — the project never claims an identifier, and the base
        configuration is not touched.

        This is the single construction the preview, the legacy committing
        path and the one-step generation share; a change to the ``name
        SMILES`` reading can therefore never make one of them disagree with
        another.
        """
        from configbuilder.persistence import PersistenceError, read_smiles_file

        project = self._projects._require_project()
        if project is None:
            return (), (), "no project is open"
        from configbuilder.app.batch_variants import (
            BatchError,
            ligand_specs_for_entries,
        )
        from configbuilder.model import SequenceTextError

        try:
            entries = read_smiles_file(path)
        except PersistenceError as error:
            return (), (), str(error)
        if not entries:
            return (
                (),
                (),
                "the ligand file contains no entries (only blank lines or comments)",
            )
        try:
            specs = ligand_specs_for_entries(
                entries,
                project.configuration.identity.clone(),
                replace_key=replace_key,
            )
        except (BatchError, SequenceTextError) as error:
            return entries, (), str(error)
        return entries, specs, None

    #: How each input kind is described when its file is empty. One sentence per
    #: reader, because "no entries" and "no sequences" are the user's own words
    #: for what they thought they wrote.
    _EMPTY_MESSAGES = {
        "protein-sequence": "the sequence file contains no sequences (only blank lines)",
        "dna-sequence": "the sequence file contains no sequences (only blank lines)",
        "rna-sequence": "the sequence file contains no sequences (only blank lines)",
        "ligand-smiles": (
            "the ligand file contains no entries (only blank lines or comments)"
        ),
        "ligand-ccd": (
            "the CCD code file contains no entries (only blank lines or comments)"
        ),
    }

    def input_file_specs(
        self, path: str, kind: str = "ligand-smiles", replace_key=None
    ):
        """Read one batch input file of ``kind`` and build its specs, uncommitted.

        Returns ``(entries, specs, None)`` or ``(entries, (), message)``, with
        ``entries`` exactly as the kind's reader read them (so a front end can
        show what would be processed even when the file is refused). The specs
        are ``base + AddRecord`` pairs built against a **throwaway clone** of
        the base registry: the project never claims an identifier, the base
        configuration is not touched, and a refused file leaves both as they
        were.

        ``kind`` is the user's explicit choice (``batch_variants.INPUT_KINDS``),
        never a guess from the file's extension or contents: a ``.txt`` of
        amino-acid codes is a protein batch only because someone said so.

        ``replace_key`` selects the mode. Without it every entry is a **new**
        entity (``AddRecord``). With it every entry edits that existing base
        entity instead (``SetSequence`` for a chain, which rewrites a DNA
        partner strand too, ``SetComponentRepresentation`` for a ligand), so a
        file can re-sequence or re-represent a placeholder, a wild type or a
        lead compound without the job growing a second copy of it. The key must
        name a record of the kind's own family: the check happens here, before
        any entry is built, so the refusal names the mismatch rather than an
        alphabet error on line 1.
        """
        from configbuilder.app.batch_variants import (
            BatchError,
            INPUT_KINDS,
            specs_for_entries,
        )
        from configbuilder.model import SequenceTextError
        from configbuilder.persistence import (
            PersistenceError,
            read_code_file,
            read_sequence_file,
        )

        if kind not in INPUT_KINDS:
            return (), (), "%r is not an input type this builder reads" % (kind,)
        project = self._projects._require_project()
        if project is None:
            return (), (), "no project is open"
        if replace_key is not None:
            problem = self._replace_target_failure(project, kind, replace_key)
            if problem is not None:
                return (), (), problem
        if kind == "ligand-smiles":
            # The SMILES reading is unchanged and shared: one implementation of
            # ``name SMILES`` for the preview, the console and the page.
            return self.ligand_file_specs(path, replace_key=replace_key)
        try:
            if kind == "ligand-ccd":
                entries = read_code_file(path)
            else:
                entries = read_sequence_file(path)
        except PersistenceError as error:
            return (), (), str(error)
        if not entries:
            return (), (), self._EMPTY_MESSAGES.get(kind, "the file contains no entries")
        try:
            # Preserve direct VariantService callers that were constructed
            # without ConfigurationService; this legacy API uses the original
            # pure record builders. UI wiring supplies the normal constructor,
            # including the DNA duplex behavior, for file-based generation.
            if self._configuration is None:
                specs = specs_for_entries(
                    entries,
                    project.configuration.identity.clone(),
                    kind,
                    replace_key=replace_key,
                )
            else:
                family = {
                    "protein-sequence": "protein",
                    "dna-sequence": "dna",
                    "rna-sequence": "rna",
                }.get(kind)
                sequence_record_factory = (
                    self._batch_records_for_family(family)
                    if family is not None
                    else None
                )
                specs = specs_for_entries(
                    entries,
                    project.configuration.identity.clone(),
                    kind,
                    sequence_record_factory=sequence_record_factory,
                    replace_key=replace_key,
                )
        except (BatchError, SequenceTextError) as error:
            return entries, (), str(error)
        return entries, specs, None

    def _replace_target_failure(self, project, kind: str, replace_key):
        """Why ``replace_key`` cannot be the entity a ``kind`` file replaces.

        One refusal for the two mistakes a user can actually make: the key is
        not in this job at all, or it names an entity of another family (a
        protein list asked to re-sequence a ligand). ``_REPLACE_FAMILY`` is the
        authority, so the check here and the picker a front end shows read the
        same table.
        """
        wanted = _REPLACE_FAMILY.get(kind)
        if wanted is None:
            return "%r is not an input type this builder reads" % (kind,)
        record = self._record_of(project, replace_key)
        if record is None:
            return "no entity is identified by %r" % (replace_key,)
        family = self._family_of_record(record)
        if family != wanted:
            return (
                "entity %r is a %s record; a %s file replaces %s records"
                % (replace_key, family, kind, wanted)
            )
        return None

    def entity_rows_for_kind(self, kind: str):
        """The base entities a file of ``kind`` can replace, in record order.

        Empty for an unknown kind and for a job that holds nothing of that
        family. A front end offers exactly these rows, so it cannot propose a
        target ``input_file_specs`` would refuse.
        """
        family = _REPLACE_FAMILY.get(kind)
        if family is None:
            return ()
        return tuple(row for row in self.entity_table() if row.family == family)

    def _batch_records_for_family(self, family):
        """Build one line's records through normal entity construction.

        Protein and RNA each add one record. DNA follows the same default
        duplex/reverse-complement behavior as ConfigurationService.add_record;
        one file line remains one independent batch specification, with both
        strands grouped in that specification.
        """
        def build(registry, sequence):
            records, failure = self._configuration._build_records(
                family, sequence, "", 1, registry
            )
            if failure is not None:
                raise BatchError(failure.message or "invalid %s sequence" % family)
            return records

        from configbuilder.app.batch_variants import BatchError

        return build

    def inspect_input_file(
        self, path: str, kind: str = "ligand-smiles", replace_key=None
    ):
        """Preview one batch input file of ``kind`` without creating anything.

        The preview is the service's own read-only check against the same spec
        construction the write uses, so the count, the entries and any refusal
        (a bad line, a duplicate, an unreadable path, an unknown kind) are known
        before a folder is chosen. Nothing is added to the project and no
        identifier is reserved in the base: the clone is discarded.
        """
        entries, specs, problem = self.input_file_specs(path, kind, replace_key)
        if kind == "ligand-smiles":
            shown = ["%s  %s" % (name, smiles) for _line, name, smiles in entries]
        else:
            shown = [text for _line, text in entries]
        if problem is not None:
            return FilePreview(ok=False, message=problem, entries=shown)
        return FilePreview(ok=True, entries=shown, planned=len(specs))

    # -- legacy batch surface (specs, not files) ------------------------------
    #
    # ``inspect_batch_file`` / ``generate_from_file`` are the *commit-based*
    # batch API: they add one variant spec per entry to the open project, where
    # they stay visible in the variants list. No front end uses them — the
    # user-facing workflow is ``GenerationService.plan_input_batch`` /
    # ``generate_input_batch``, which writes independent AF3 JSON files and
    # commits nothing. They remain because the manual-test suite and the
    # fixture generator drive that older shape, and deleting them would mean
    # rewriting those callers for no user-visible gain.
    #
    # The two surfaces are not interchangeable, and they are not meant to be:
    # one builds files, the other builds specs. A change to the reading or the
    # record construction belongs in ``app.batch_variants``, which both use, so
    # a sequence can never be read one way here and another way there.

    def inspect_batch_file(self, path: str, family: str = "protein"):
        """Preview a batch input file by **entity family**, commit-accurate.

        **Legacy surface** (see the section note above): it previews the
        committing path, not the file-writing workflow. Kept for callers that
        think in families (the older service surface and its tests): the family
        is translated to the input kind the front ends offer, and the same
        read-only check runs. Unlike
        :meth:`inspect_input_file`, this preview also reports a key the project
        already holds, because its caller is the **committing** path
        (``generate_from_file``) where such a key would be refused at commit
        time. The one-step file workflow commits nothing, so its preview has no
        collision question — reporting one there would refuse a rerun that is
        perfectly writable.
        """
        kind = _KIND_FOR_FAMILY.get(family)
        if kind is None:
            return FilePreview(
                ok=False,
                message="a batch file can contain protein, DNA, RNA or ligand "
                "entries; %r is not supported" % (family,),
            )
        entries, specs, problem = self.input_file_specs(path, kind)
        if kind == "ligand-smiles":
            shown = ["%s  %s" % (name, smiles) for _line, name, smiles in entries]
        else:
            shown = [text for _line, text in entries]
        if problem is not None:
            return FilePreview(ok=False, message=problem, entries=shown)
        collisions = [spec.key for spec in specs if self._find(spec.key) is not None]
        if collisions:
            return FilePreview(
                ok=False,
                message="a variant keyed %r already exists; rename or remove it first"
                % collisions[0],
                entries=shown,
            )
        return FilePreview(ok=True, entries=shown, planned=len(specs))

    def generate_from_file(self, path: str, family: str = "protein") -> MutationOutput:
        """Batch-generate one independent variant per entry in a file.

        **LEGACY / DEPRECATED — not the user-facing workflow, do not add
        callers.** This commits a ``base + AddRecord`` spec per entry into the
        open project, which mutates the job the user is editing. The console
        and the desktop instead write one independent configuration per entry
        through ``GenerationService`` (``generate_input_batch``), which never
        touches the base. Neither front end calls this method; the only
        remaining callers are test/fixture tooling, and the migration plan for
        them is ``docs/LEGACY_GENERATION_API_MIGRATION.md``.

        Keep this until those callers are migrated and verified — deleting it
        first would break fixture generation. Use ``generate_input_batch`` for
        any user-facing behaviour, or this one only when the result you want
        *is* a set of variants committed into the job.

        ``path`` is a file containing multiple entries:
        - For protein/dna families: a sequence file (.txt) with one sequence per line
        - For ligand family: a SMILES file (.smiles or .txt) with one SMILES per line

        The reading is persistence's (plan §5.3 rule 8: file IO is confined
        there); the spec construction is the batch module's; the commitment
        is ``add_spec``'s — so every generated variant is a plain
        ``base + AddRecord`` spec, identical in kind to a hand-created one,
        visible in the Variants menu, exportable, and editable afterwards.
        All-or-nothing: any invalid line or duplicate refuses the whole
        batch and commits nothing.
        """
        project = self._projects._require_project()
        if project is None:
            return self._not_open()
        from configbuilder.persistence import PersistenceError, read_sequence_file
        from configbuilder.app.batch_variants import BatchError, batch_specs_for_sequences
        from configbuilder.model import SequenceTextError

        # Choose the appropriate reader based on family
        if family == "ligand":
            # The documented ``name SMILES`` names are kept: they become the
            # variant keys (and so the output filenames). The discarded-name
            # behaviour this replaces was the audit's defect D-4.
            _entries, specs, problem = self.ligand_file_specs(path)
            if problem is not None:
                return self._refuse(problem)
        else:
            try:
                entries = read_sequence_file(path)
            except PersistenceError as error:
                return self._refuse(str(error))
            if not entries:
                return self._refuse("the sequence file contains no sequences (only blank lines)")
            try:
                registry = project.configuration.identity.clone()
                specs = batch_specs_for_sequences(entries, registry, family=family)
            except (BatchError, SequenceTextError) as error:
                return self._refuse(str(error))
        # Commit through add_spec so every guarantee (unique keys,
        # persistence shape) is the standard route's.
        for spec in specs:
            outcome = self.add_spec(spec.key, spec.label, spec.edits)
            if not outcome.ok:
                # Roll back any already-added specs of this batch.
                for done in specs:
                    if done.key == spec.key:
                        break
                    self.remove_spec(done.key)
                return self._refuse(
                    "variant %r could not be created: %s" % (spec.key, outcome.message)
                )
        return MutationOutput(ok=True, message="%d variants generated" % len(specs))

    # -- the per-entity workflow (multi-ligand / small-protein inputs) ---------

    def target_strategy_choices(self) -> "tuple[VariantChoice, ...]":
        """The strategies that vary *one* entity, restricted to the families
        this base actually contains, as choice rows.

        ``label`` is wording-free data: a front end renders it through its
        own templates. Offering only strategies some entity can carry is the
        point of the table below — a picker that offers "Sequence change" to
        a job of ligands is the problem this workflow removes.
        """
        families_present = {row.family for row in self.entity_table()}
        return tuple(
            VariantChoice(label, kind, detail=", ".join(families))
            for kind, label, families in TARGET_STRATEGIES
            if families_present.intersection(families)
        )

    def entity_table(self) -> "tuple[EntityRow, ...]":
        """Every base entity as the target picker shows it (plan §15).

        One row per *record* — an entity definition — never one per chain:
        ``copies`` is the record's multiplicity, so a ligand present twice is
        one entity with two copies, which is exactly what a variant targets.
        ``kinds`` comes from ``TARGET_STRATEGIES``, the same table the service
        refuses with, so the table cannot advertise a strategy expansion would
        reject.
        """
        project = self._projects._require_project()
        if project is None:
            return ()
        rows = []
        for record in project.configuration.records:
            family = self._family_of_record(record)
            rows.append(
                EntityRow(
                    key=record.ids.primary.value,
                    family=family,
                    copies=record.ids.count,
                    summary=self._record_summary(record),
                    kinds=tuple(
                        kind
                        for kind, _label, families in TARGET_STRATEGIES
                        if family in families
                    ),
                    note=_FAMILY_NOTES.get(family, ""),
                )
            )
        return tuple(rows)

    def plan_target_variants(self, keys, kind: str, value) -> "TargetPlan":
        """What varying ``keys`` with one strategy *would* create; no commit.

        One independent spec per target — ``variant 1 = base + edit(target A)``
        and ``variant 2 = base + edit(target B)``, both from the same base, so
        two selected ligands never become one variant holding both changes.
        Combining changes is a different, explicit action (add the second
        change to the variant), which is why the count here is simply the
        number of eligible targets.

        The edits are built by ``_edits_for_kind`` — the same call
        ``add_spec_with_edit`` commits — so the preview cannot describe a
        change the service would refuse.
        """
        project = self._projects._require_project()
        if project is None:
            return TargetPlan(ok=False, message="no project is open")
        if kind not in _STRATEGY_BY_KIND:
            return TargetPlan(
                ok=False,
                message="%r is not a per-entity strategy; choose one of %s"
                % (kind, ", ".join(sorted(_STRATEGY_BY_KIND))),
            )
        ordered = tuple(dict.fromkeys(str(key) for key in keys))
        if not ordered:
            return TargetPlan(ok=False, message="select at least one entity to vary")
        table = {row.key: row for row in self.entity_table()}
        rows = []
        failures = []
        for key in ordered:
            row = table.get(key)
            if row is None:
                failures.append((key, "no entity is identified by %r" % (key,)))
                continue
            edits, failure = self._edits_for_kind(project, kind, value, key)
            if failure is not None:
                failures.append((key, failure))
                continue
            rows.append(
                TargetPlanRow(
                    key=key,
                    family=row.family,
                    label="%s: %s" % (key, _STRATEGY_BY_KIND[kind][0]),
                    spec_key="%s_%s" % (key, kind),
                    edits=tuple(edits),
                    described=tuple(describe_edit(edit) for edit in edits),
                )
            )
        unchanged = tuple(
            row.key for row in table.values() if row.key not in set(ordered)
        )
        plan = TargetPlan(
            ok=not failures,
            rows=tuple(rows),
            failures=tuple(failures),
            unchanged_keys=unchanged,
        )
        if failures:
            plan.message = "%d of %d selected entities cannot take this change:\n  %s" % (
                len(failures),
                len(ordered),
                "\n  ".join("%s: %s" % (key, reason) for key, reason in failures),
            )
        return plan

    def create_target_variants(self, keys, kind: str, value) -> MutationOutput:
        """Commit the plan: one independent variant spec per selected entity.

        All-or-nothing: every edit is planned first and the spec list is
        written once, so a refused target leaves no half-built variant behind
        (the same rule ``add_spec_with_edit`` follows for one variant). A key
        that already exists is refused rather than renamed — the user's list
        stays theirs.
        """
        plan = self.plan_target_variants(keys, kind, value)
        if not plan.ok:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message=plan.message or "the selection cannot be varied",
            )
        existing = {spec.key for spec in self._specs()}
        clashes = [row.spec_key for row in plan.rows if row.spec_key in existing]
        if clashes:
            return MutationOutput(
                ok=False,
                failure_reason=FailureReason.NO_PATH,
                message=(
                    "a variant is already named %s; rename or remove it first"
                    % ", ".join(clashes)
                ),
            )
        specs = tuple(
            VariantSpec(key=row.spec_key, label=row.label, edits=row.edits)
            for row in plan.rows
        )
        self._projects._with_specs(self._specs() + specs)
        return MutationOutput(
            ok=True,
            message="%d variant%s created: %s"
            % (
                len(specs),
                "" if len(specs) == 1 else "s",
                ", ".join(spec.label for spec in specs),
            ),
        )

    @staticmethod
    def _record_of(project, key):
        if not key:
            return None
        for record in project.configuration.records:
            if record.ids.primary.value == key:
                return record
        return None

    @staticmethod
    def _family_of_record(record) -> str:
        if isinstance(record, FamilyARecord):
            return "protein"
        if isinstance(record, FamilyBRecord):
            return "rna"
        if isinstance(record, FamilyCRecord):
            return "dna"
        return "ligand"

    @staticmethod
    def _record_summary(record) -> str:
        """The entity's own content, short enough for a table cell."""
        if isinstance(record, ComponentRecord):
            representation = record.representation
            if isinstance(representation, ByCode):
                return "CCD %s" % ", ".join(
                    code.value for code in representation.codes
                )
            return "SMILES %s" % representation.text
        return record.sequence.text

    def _family_target_failure(self, project, kind: str, record_key):
        """Why ``record_key`` cannot carry ``kind``, or ``None``.

        ``TARGET_STRATEGIES`` is the authority: the entity table's ``kinds``
        and this refusal read the same row, so a strategy is never offered for
        a family that expansion would reject.
        """
        families = _STRATEGY_BY_KIND.get(kind)
        if families is None:
            return None
        if not record_key:
            return "choose the entity this change applies to"
        record = self._record_of(project, record_key)
        if record is None:
            return "no entity is identified by %r" % (record_key,)
        family = self._family_of_record(record)
        if family in families[1]:
            return None
        return (
            "%s cannot be applied to %s entity %r; it supports %s"
            % (families[0], family, record_key, ", ".join(families[1]))
        )

    def _expand_specs(self, specs):
        project = self._projects._require_project()
        try:
            variants = expand(project.configuration, tuple(specs))
        except (EditError, VariantSpecError) as error:
            return ExpandOutput(
                ok=False,
                failure_reason=FailureReason.EXPANSION_FAILED,
                message=str(error),
            )
        return ExpandOutput(ok=True, variants=variants)

    def specs(self):
        """Return the list of all variant specs."""
        return list(self._specs())

    def spec_count(self):
        """Return the number of variant specs."""
        return len(self._specs())
