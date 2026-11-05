"""Record, seed, and linkage editing (IMPLEMENTATION_PLAN.md §15):
``ConfigurationService``.

Every mutation returns a ``MutationOutput``; user-caused problems come
back as failure reasons and findings, never exceptions. Records are
identified by their primary ``EntityId`` resolved through the
configuration's registry — never list position (plan §8.1.1, §12.1).
"""

from __future__ import annotations

from configbuilder.app.reference_validation import validate_reference
from configbuilder.app.results import FailureReason, MutationOutput
from configbuilder.identity import (
    EntityId,
    IdentityError,
    IdentityRegistry,
    Multiplicity,
)
from configbuilder.model import (
    D_AMINO_ACIDS,
    AlignmentAutomatic,
    AlignmentBoth,
    AlignmentFree,
    AlignmentPairedOnly,
    AlignmentUnpairedOnly,
    ByCode,
    ByNotation,
    ComponentCode,
    ComponentRecord,
    ConfigurationError,
    Dialect,
    Explicit,
    External,
    FamilyARecord,
    FamilyBRecord,
    FamilyCRecord,
    FormatTarget,
    Inline,
    LinkEndpoint,
    Linkage,
    ModelError,
    ModificationRecord,
    PathSpec,
    Pinned,
    Position,
    ReferenceRecord,
    ResidueRef,
    SearchAllowed,
    SequenceText,
    SingleAutomatic,
    SingleFree,
    SingleProvided,
    d_code_for,
    duplex_partner,
    is_d_code,
    residue_for_d_code,
    reverse_complement,
    split_component_codes,
)

__all__ = ["ConfigurationService", "ReferenceInput"]

_FAMILY_TYPES = (FamilyARecord, FamilyBRecord, FamilyCRecord, ComponentRecord)

# The family word for a record that carries no sequence, so a refusal names
# what the user actually picked (a ligand) instead of "record".
_FAMILY_WORD = {
    FamilyARecord: "protein",
    FamilyBRecord: "rna",
    FamilyCRecord: "dna",
    ComponentRecord: "ligand",
}


class ReferenceInput:
    """One structural-template reference, as a front end supplies it:
    a source (inline text or an external path) and 0-based query/template
    index pairs (or the raw comma-separated pair text a console collected).

    Pair text stays text until the application's reference rules parse it,
    so the console never owns the format rule."""

    __slots__ = ("inline_text", "external_path", "pairs")

    def __init__(self, inline_text=None, external_path=None, pairs=()) -> None:
        self.inline_text = inline_text
        self.external_path = external_path
        self.pairs = pairs if isinstance(pairs, str) else tuple(pairs)


class ConfigurationService:
    """Mutates the open project's configuration through validated
    constructors and identity-owned identifiers."""

    def __init__(self, projects, validate=None) -> None:
        self._projects = projects
        self._validate = validate

    # -- helpers ---------------------------------------------------------------

    def _project(self):
        return self._projects._require_project()

    def _configuration(self):
        project = self._project()
        return project.configuration if project is not None else None

    def _commit(self, configuration) -> MutationOutput:
        self._projects._replace_project(self._project().with_configuration(configuration))
        return self._findings_output()

    def _findings_output(self) -> MutationOutput:
        project = self._project()
        if self._validate is None or project is None:
            return MutationOutput(ok=True)
        return MutationOutput(ok=True, findings=self._validate(project.configuration).findings)

    def _not_open(self) -> MutationOutput:
        return MutationOutput(
            ok=False,
            failure_reason=FailureReason.NOT_OPEN,
            message="no project is open",
        )

    def _unknown_record(self, record_key) -> MutationOutput:
        return MutationOutput(
            ok=False,
            failure_reason=FailureReason.UNKNOWN_RECORD,
            message="no record is identified by %r; pick a record the registry knows" % (record_key,),
        )

    def _refused(self, message: str) -> MutationOutput:
        return MutationOutput(ok=False, failure_reason=FailureReason.NO_PATH, message=message)

    def _record_for(self, configuration, primary: EntityId):
        """The record that carries ``primary``, or None.

        Resolution is by **membership**: the registry is the authority on
        whether an identifier is assigned, and the record that carries it is
        found by asking each record's own multiplicity. Comparing the
        registry's multiplicity for ``primary`` against the record's
        multiplicity looks equivalent but is not — a record holding several
        copies (``['A', 'B', 'C']``) is indexed per identifier, so
        ``multiplicity_of('A')`` answers with the singleton ``['A']`` and the
        equality never held. Every record with more than one copy was then
        invisible to ``update_record``, ``remove_record``, ``add_modification``
        and the alignment/reference setters (BUG-004).
        """
        try:
            configuration.identity.multiplicity_of(primary)
        except IdentityError:
            return None
        for record in configuration.records:
            if record.ids.contains(primary):
                return record
        return None

    def _key(self, record_key):
        try:
            return EntityId(record_key), None
        except ValueError as error:
            return None, self._refused(str(error))

    # -- job details (§15 set_name; spec §15 job descriptions) -------------------

    def set_name(self, name: str) -> MutationOutput:
        """Rename the job.

        A blank name is a **user condition**, not a crash: the model refuses
        an empty name, so the refusal is converted to a ``MutationOutput``
        here — every service operation answers with a result object, and no
        front end can die on a bare Enter (plan §15).
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        metadata = configuration.metadata
        try:
            renamed = metadata.__class__(name, metadata.description)
        except (ModelError, ValueError, TypeError) as error:
            return self._refused("a job name cannot be empty — %s" % (error,))
        return self._commit(configuration.with_metadata(renamed))

    # A job-level description is **not** part of the AF3 wire format (only the
    # per-entity ``description`` is), and no front end ever offered it, so
    # ``set_job_description`` was removed rather than documented: an operation
    # whose result cannot reach an output file is a trap for the next caller.
    # The model keeps ``ConfigurationMetadata.description`` because the
    # configuration value carries it; only the unreachable setter is gone.

    def set_seeds(self, seeds) -> MutationOutput:
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        # A front-end field arrives as raw text ("1 2 3"); lists/tuples are
        # the programmatic form. Parse text here so the caller's answer
        # shape is the service's problem, not the user's (plan §16).
        if isinstance(seeds, str):
            parts = seeds.replace(",", " ").split()
            try:
                seeds = [int(part) for part in parts]
            except ValueError:
                return self._refused(
                    "seeds must be whole numbers separated by spaces or commas"
                )
        if isinstance(seeds, (int, tuple)):
            seeds = list(seeds) if isinstance(seeds, tuple) else [seeds]
        try:
            seed_set = configuration.seeds.__class__(list(seeds))
        except (ValueError, TypeError, ModelError) as error:
            return self._refused(str(error))
        return self._commit(configuration.with_seeds(seed_set))

    # -- records -----------------------------------------------------------------

    def add_record(self, family: str, sequence: str = "", representation="", copies: int = 1, description=None, representation_kind="", duplex: bool = True):
        """Add a record; identity allocates its identifiers (plan §8.1).

        ``family`` is ``"protein"`` / ``"rna"`` / ``"dna"`` / ``"ligand"``.
        ``copies`` > 1 reserves an ordered copy multiplicity (plan §8.2).

        A ``dna`` entry is a duplex by default (DNA duplex feature): the
        caller supplies one 5'-to-3' strand and this service commits **two**
        records — the given strand and its reverse complement — each with
        its own registry-allocated identifier. The complement is built here
        at the domain boundary, never in a front end.

        ``duplex=False`` commits only the supplied strand, the same lone
        record an imported single-chain DNA entity produces. It is a
        deliberate choice of the caller (the console's complement question);
        the default remains the duplex so no existing caller changes.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        if family == "ligand":
            if not representation:
                return self._refused(
                    "a ligand record needs a representation: CCD code(s) or a SMILES notation"
                )
        elif family not in ("protein", "rna", "dna"):
            return self._refused("unknown family %r; use protein, rna, dna, or ligand" % (family,))
        elif not sequence:
            return self._refused("a %s record needs a sequence" % family)
        if isinstance(copies, str):  # a front-end field arrives as text
            try:
                copies = int(copies.strip() or "1")
            except ValueError:
                return self._refused("copies must be a whole number of at least 1")
        if not isinstance(copies, int) or copies < 1:
            return self._refused("copies must be a whole number of at least 1")

        if family == "dna" and copies != 1:
            return self._refused(
            "a DNA record is a duplex: the complementary strand is constructed "
            "automatically, so copies does not apply"
            )
        registry = configuration.identity.clone()
        records, failure = self._build_records(
            family, sequence, representation, copies, registry,
            representation_kind=representation_kind, duplex=duplex,
        )
        if failure is not None:
            return failure
        if description is not None:
            records = tuple(record.with_description(self._presence(description)) for record in records)
        return self._commit(
            configuration.with_records(configuration.records + records).with_identity(registry)
        )

    def _build_records(self, family, sequence, representation, copies, registry: IdentityRegistry, representation_kind="", duplex=True):
        """Build the record(s) with registry-allocated identifiers.

        Returns ``(records, None)`` or ``((), MutationOutput)``. Every
        family yields one record except DNA, which yields the duplex: the
        supplied strand plus its reverse complement, two distinct
        identifiers allocated back-to-back so the complement always sorts
        immediately after its partner. Both strands are conventional
        5'-to-3' sequences (DNA duplex feature); the direction lives in
        ``FamilyCRecord.complement`` / ``reverse_complement``, not here.
        """
        owner = "record"
        try:
            strands = 2 if family == "dna" and duplex else copies
            allocated = [registry.allocate(owner=owner) for _ in range(strands)]
            if family == "ligand":
                representation_value = self._ligand_representation(representation, kind=representation_kind)
                if isinstance(representation_value, MutationOutput):
                    return (), representation_value
                ids = Multiplicity([entity.value for entity in allocated])
                return (ComponentRecord(ids=ids, representation=representation_value),), None
            text = SequenceText(sequence, family)
            if family == "protein":
                ids = Multiplicity([allocated[0].value])
                return (FamilyARecord(ids=ids, sequence=text),), None
            if family == "rna":
                ids = Multiplicity([allocated[0].value])
                return (FamilyBRecord(ids=ids, sequence=text),), None
            given = FamilyCRecord(ids=Multiplicity([allocated[0].value]), sequence=text)
            if not duplex:
                return (given,), None
            partner = given.complement()
            partner = FamilyCRecord(
                ids=Multiplicity([allocated[1].value]),
                sequence=partner.sequence,
                modifications=partner.modifications,
                description=partner.description,
            )
            return (given, partner), None
        except (ModelError, IdentityError, ValueError) as error:
            return (), self._refused(str(error))

    def _presence(self, description):
        """Normalize text into the description's Presence vocabulary —
        the same discipline as ``set_job_description``: empty text is
        *explicitly empty*, non-empty is *present*, non-strings pass
        through as an already-built Presence value."""
        if isinstance(description, str):
            from configbuilder.model import ExplicitEmpty, Present

            return Present(description) if description else ExplicitEmpty()
        return description

    def _ligand_representation(self, representation: str, kind=""):
        """The ligand representation for a raw representation string.

        ``kind`` (``"ccd"`` / ``"smiles"``) is the UI's explicit submenu
        choice: ``ccd`` classifies as codes, ``smiles`` as a notation,
        and the empty default keeps the established classification (a
        multi-token string is codes, otherwise a code when it parses as
        one and a notation only when the caller asks for one).
        """
        text = representation.strip()
        if not text:
            return self._refused("a ligand representation cannot be empty")
        if kind == "smiles":
            try:
                return ByNotation(text)
            except ValueError as error:
                return self._refused(str(error))
        # ``ccd``, or no explicit kind: one or more CCD codes. Every token is
        # a component of the same ligand -- the contract's multi-component
        # representation (a glycan, an ion/water group) -- so both routes must
        # read the text the same way.
        return self._ccds(text)

    def _ccds(self, text: str):
        """One or more CCD component codes: whitespace, commas and semicolons
        separate the components of a single ligand.

        The ligand submenu promises "CCD code(s) - e.g. ATP, or several
        separated by spaces", and the contract's multi-component ligand (a
        glycan, an ion mix) depends on it. Treating the whole text as one code
        made that promise false through the submenu's explicit CCD route: the
        five-code glycan ``NAG NAG BMA MAN MAN`` became a single component of
        that name, which no CCD contains.

        The splitting itself is ``model.split_component_codes``, shared with
        the batch reader so one line of a code file and one form entry can
        never disagree about what a component boundary is.
        """
        tokens = split_component_codes(text)
        if not tokens:
            return self._refused("a ligand representation cannot be empty")
        try:
            codes = tuple(ComponentCode(token) for token in tokens)
        except ValueError:
            return self._refused(
                "%r is not a CCD component code; choose SMILES in the submenu for notation input" % text
            )
        return ByCode(codes)

    def update_record(self, record_key: str, sequence=None, description=None) -> MutationOutput:
        """Change a record's sequence and/or description, identified
        through the registry — never list position.

        A DNA strand is one half of a duplex the service itself built, so
        changing its sequence changes its partner's too: leaving the partner
        behind produced a "duplex" whose strands were no longer
        complementary, with nothing reporting it (DNA duplex feature). The
        partner is found by ``duplex_partner``; a lone strand (an imported
        single DNA chain) has none and is edited on its own.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not isinstance(record, _FAMILY_TYPES):
            return self._unknown_record(record_key)
        updated = record
        partner = duplex_partner(configuration, record)
        partner_update = None
        if sequence is not None:
            # Only the three polymer families have a sequence. A ligand never
            # does, so a sequence change aimed at one is a user condition to
            # report — requesting it used to reach ``with_sequence`` on a
            # ``ComponentRecord`` and escape as an ``AttributeError``
            # (BUG-020), the same shape as the already-guarded modification
            # and alignment setters below.
            if not isinstance(record, (FamilyARecord, FamilyBRecord, FamilyCRecord)):
                return self._refused(
                    "a %s record has no sequence to change; its representation is "
                    "changed instead" % _FAMILY_WORD.get(type(record), "this")
                )
            family = "protein"
            if isinstance(record, FamilyBRecord):
                family = "rna"
            elif isinstance(record, FamilyCRecord):
                family = "dna"
            try:
                replacement = SequenceText(sequence, family)
                updated = updated.with_sequence(replacement)
                if partner is not None:
                    partner_update = partner.with_sequence(reverse_complement(replacement))
            except ModelError as error:
                return self._refused(str(error))
        if description is not None:
            updated = updated.with_description(self._presence(description))

        def _replacement(existing):
            if existing is record:
                return updated
            if partner_update is not None and existing is partner:
                return partner_update
            return existing

        outcome = self._commit(
            configuration.with_records(
                tuple(_replacement(existing) for existing in configuration.records)
            )
        )
        if outcome.ok and partner_update is not None:
            return MutationOutput(
                ok=True, message="both strands of the DNA duplex were updated"
            )
        return outcome

    def remove_record(self, record_key: str) -> MutationOutput:
        """Remove a record and release its identifiers (identity-owned,
        plan §8.3). Linkages referencing the removed copies go with it.

        Removing one strand of a DNA duplex removes the duplex: the two
        records are one biological entity the user added in one action, so
        deleting half of it would leave a state no input path can produce
        (DNA duplex feature). A lone strand — an imported single DNA chain —
        is removed on its own.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None:
            return self._unknown_record(record_key)
        partner = duplex_partner(configuration, record)
        doomed = (record,) if partner is None else (record, partner)
        released = []
        for target in doomed:
            # Release the record's *own* multiplicity, not the registry's
            # answer for its primary: a multi-copy record is indexed per
            # identifier, so ``multiplicity_of(primary)`` returns the
            # singleton and left the sibling copies reserved forever — the
            # same root cause as BUG-004, on the release side.
            released.extend(target.ids.ids)
        released_values = {entity.value for entity in released}
        records = tuple(r for r in configuration.records if r not in doomed)
        linkages = tuple(
            linkage
            for linkage in configuration.linkages
            if linkage.a.entity.value not in released_values
            and linkage.b.entity.value not in released_values
        )
        registry = configuration.identity.clone()
        for entity in released:
            registry.release(entity)
        outcome = self._commit(
            configuration.with_records(records).with_linkages(linkages).with_identity(registry)
        )
        if outcome.ok and partner is not None:
            return MutationOutput(
                ok=True, message="the DNA duplex and its partner strand were removed"
            )
        return outcome

    # -- modifications (§15 add_modification) --------------------------------------

    # -- amino-acid forms (D-amino acids) ----------------------------------

    @staticmethod
    def _family_word(record) -> str:
        """The everyday family word for a record, for a refusal message."""
        return _FAMILY_WORD.get(type(record), "record")

    @staticmethod
    def _d_code_problem(record, code, position):
        """Why ``code`` cannot replace the residue at ``position``, or ``None``.

        Only known D-form codes are checked here; any other modification code
        keeps its existing (unconstrained) behaviour. An out-of-range position
        is left to R-ENT-007 so the user sees that finding once.
        """
        expected_residue = residue_for_d_code(code)
        if expected_residue is None:
            return None
        if not isinstance(record, FamilyARecord):
            return (
                "%s is a protein D-amino-acid component; it cannot replace a "
                "residue on a %s chain"
                % (code, ConfigurationService._family_word(record))
            )
        text = record.sequence.text
        if position < 1 or position > len(text):
            return None
        residue = text[position - 1]
        if residue == "G":
            return (
                "%s cannot replace glycine at position %d of chain %s: glycine "
                "is achiral and has no D-form"
                % (code, position, record.ids.primary.value)
            )
        if D_AMINO_ACIDS.get(residue) != code:
            matching = D_AMINO_ACIDS.get(residue)
            if matching is None:
                return (
                    "residue %s at position %d of chain %s has no D-form"
                    % (residue, position, record.ids.primary.value)
                )
            return (
                "%s is the D-form of %s; position %d of chain %s is %s (use %s)"
                % (
                    code,
                    expected_residue,
                    position,
                    record.ids.primary.value,
                    residue,
                    matching,
                )
            )
        return None

    @staticmethod
    def _duplicate_position_problem(record, code, position, ignore_index=None):
        """A D-form cannot share its position with any other modification."""
        if not is_d_code(code):
            return None
        for index, existing in enumerate(record.modifications):
            if index == ignore_index:
                continue
            if existing.position.value == position:
                return (
                    "position %d of chain %s already carries %s; remove it "
                    "before assigning the D-form %s"
                    % (
                        position,
                        record.ids.primary.value,
                        existing.code.value,
                        code,
                    )
                )
        return None

    def set_amino_acid_form(
        self, record_key: str, position: int, form: str
    ) -> MutationOutput:
        """Set a protein residue's stereochemical form: ``"L"`` or ``"D"``.

        ``"D"`` adds the residue replacement its canonical residue resolves
        to, through the ordinary protein modification field (no new JSON
        shape). ``"L"`` removes a D-form replacement at that position,
        returning the residue to standard.

        Conflicts are refused, never resolved silently: a position that
        already carries any modification is not overwritten, and glycine (or a
        residue with no D-form) is refused with the reason.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not hasattr(record, "modifications"):
            return self._unknown_record(record_key)
        if not isinstance(record, FamilyARecord):
            return self._refused(
                "an amino-acid form applies to a protein chain; %s is a %s "
                "chain" % (record_key, self._family_word(record))
            )
        try:
            position_value = Position(int(position))
        except (ModelError, ValueError, TypeError) as error:
            return self._refused(str(error))
        text = record.sequence.text
        if position_value.value > len(text):
            return self._refused(
                "position %d is past the end of chain %s (%d residues)"
                % (position_value.value, record_key, len(text))
            )
        word = str(form).strip().upper()
        if word not in ("L", "D"):
            return self._refused("the form must be 'L' or 'D', not %r" % (form,))
        modifications = tuple(record.modifications)
        replacements = [
            (index, modification)
            for index, modification in enumerate(modifications)
            if modification.position == position_value
            and is_d_code(modification.code.value)
        ]
        if word == "L":
            if not replacements:
                at_position = [
                    modification
                    for modification in modifications
                    if modification.position == position_value
                ]
                if at_position:
                    return self._refused(
                        "position %d of chain %s carries %s; change or remove "
                        "it in the modification editor instead"
                        % (
                            position_value.value,
                            record_key,
                            at_position[0].code.value,
                        )
                    )
                return self._refused(
                    "position %d of chain %s is already the standard L-form "
                    "(%s); there is nothing to change"
                    % (
                        position_value.value,
                        record_key,
                        text[position_value.value - 1],
                    )
                )
            removed = {index for index, _modification in replacements}
            updated = record.with_modifications(
                tuple(
                    modification
                    for index, modification in enumerate(modifications)
                    if index not in removed
                )
            )
        else:
            residue = text[position_value.value - 1]
            code = d_code_for(residue)
            if code is None:
                if residue == "G":
                    return self._refused(
                        "glycine at position %d of chain %s is achiral: it has "
                        "no D-form" % (position_value.value, record_key)
                    )
                return self._refused(
                    "residue %s at position %d of chain %s has no D-form"
                    % (residue, position_value.value, record_key)
                )
            conflict = self._duplicate_position_problem(
                record, code, position_value.value
            )
            if conflict is not None:
                return self._refused(conflict)
            updated = record.with_modifications(
                modifications
                + (ModificationRecord(ComponentCode(code), position_value),)
            )
        records = tuple(
            updated if existing is record else existing
            for existing in configuration.records
        )
        return self._commit(configuration.with_records(records))

    def add_modification(self, record_key: str, code: str, position: int) -> MutationOutput:
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not hasattr(record, "modifications"):
            return self._unknown_record(record_key)
        try:
            modification = ModificationRecord(ComponentCode(code), Position(int(position)))
        except (ModelError, ValueError, TypeError) as error:
            # ``ModelError`` is the model's own base for a refused value
            # (``ValueTypeError``); it does **not** derive from ``ValueError``,
            # so catching only ``ValueError`` let a blank code escape as a
            # traceback (BUG-001).
            return self._refused(str(error))
        problem = self._d_code_problem(
            record, modification.code.value, modification.position.value
        )
        if problem is not None:
            return self._refused(problem)
        problem = self._duplicate_position_problem(
            record, modification.code.value, modification.position.value
        )
        if problem is not None:
            return self._refused(problem)
        updated = record.with_modifications(record.modifications + (modification,))
        records = tuple(updated if existing is record else existing for existing in configuration.records)
        return self._commit(configuration.with_records(records))

    def remove_modification(self, record_key: str, index: int) -> MutationOutput:
        """Remove one modification from a record by its position in the
        record's modification list; confirmation naming what is removed
        is the caller's job (plan §16.3: delete always confirms)."""
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not hasattr(record, "modifications"):
            return self._unknown_record(record_key)
        modifications = tuple(record.modifications)
        if index < 0 or index >= len(modifications):
            return self._refused("no modification numbered %d on record %s" % (index + 1, record_key))
        updated = record.with_modifications(
            modifications[:index] + modifications[index + 1 :]
        )
        records = tuple(updated if existing is record else existing for existing in configuration.records)
        return self._commit(configuration.with_records(records))

    def update_modification(self, record_key: str, index: int, code=None, position=None) -> MutationOutput:
        """Replace one modification in place, keeping its list position.

        Removing and re-adding would move the modification to the end of the
        record's list (and would half-apply if the re-add were refused); the
        PTM editor changes the code and/or the position atomically instead.
        Either argument left as ``None`` keeps the existing value.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not hasattr(record, "modifications"):
            return self._unknown_record(record_key)
        modifications = tuple(record.modifications)
        if index < 0 or index >= len(modifications):
            return self._refused("no modification numbered %d on record %s" % (index + 1, record_key))
        current = modifications[index]
        new_code = current.code.value if code is None else code
        new_position = current.position.value if position is None else position
        try:
            replacement = ModificationRecord(ComponentCode(new_code), Position(int(new_position)))
        except (ModelError, ValueError, TypeError) as error:
            return self._refused(str(error))
        problem = self._d_code_problem(
            record, replacement.code.value, replacement.position.value
        )
        if problem is not None:
            return self._refused(problem)
        problem = self._duplicate_position_problem(
            record,
            replacement.code.value,
            replacement.position.value,
            ignore_index=index,
        )
        if problem is not None:
            return self._refused(problem)
        updated = record.with_modifications(
            modifications[:index] + (replacement,) + modifications[index + 1 :]
        )
        records = tuple(updated if existing is record else existing for existing in configuration.records)
        return self._commit(configuration.with_records(records))

    def _representation_from(self, codes, notation):
        """The representation value for ``codes`` XOR ``notation``.

        Returns ``(representation, None)`` or ``(None, MutationOutput)``; the
        single place the CCD/SMILES choice and the component-code validation
        live, shared by ``set_representation`` and
        ``update_component_record``.
        """
        try:
            if codes is not None and notation is not None:
                return None, self._refused("choose codes or a notation, not both")
            if codes is not None:
                if isinstance(codes, str):
                    return ByCode((ComponentCode(codes),)), None
                return ByCode(tuple(ComponentCode(code) for code in codes)), None
            if notation is not None:
                return ByNotation(notation), None
        except (ModelError, ValueError, TypeError) as error:
            # Same guard as ``add_modification``: an empty code raises the
            # model's ``ValueTypeError``, which is not a ``ValueError`` (BUG-010).
            return None, self._refused(str(error))
        return None, self._refused("a representation needs codes or a notation")

    def set_representation(self, record_key: str, codes=None, notation=None) -> MutationOutput:
        """Set a component record's representation: CCD code(s) or a SMILES
        notation — exactly one, as vocabulary-level data (plan §16.4)."""
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not hasattr(record, "representation"):
            return self._unknown_record(record_key)
        representation, failure = self._representation_from(codes, notation)
        if failure is not None:
            return failure
        updated = record.with_representation(representation)
        records = tuple(updated if existing is record else existing for existing in configuration.records)
        return self._commit(configuration.with_records(records))

    def update_component_record(self, record_key: str, codes=None, notation=None, description=None) -> MutationOutput:
        """Change a ligand's representation and/or description as one edit.

        A ligand's editable fields are built and validated **before** anything
        is committed, and the single ``_commit`` at the end is the only
        mutation — so a refusal of any part leaves the configuration exactly
        as it was. The two-call route a front end would otherwise need
        (``set_representation`` then ``update_record``) could apply the first
        change and then fail the second.

        Identifiers are never touched: no allocation, no rename, and a copy
        multiplicity stays exactly as the registry holds it. Passing neither a
        representation nor a description is refused rather than silently
        committing an unchanged record.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not hasattr(record, "representation"):
            return self._unknown_record(record_key)
        updated = record
        if codes is not None or notation is not None:
            representation, failure = self._representation_from(codes, notation)
            if failure is not None:
                return failure
            updated = updated.with_representation(representation)
        if description is not None:
            updated = updated.with_description(self._presence(description))
        if updated is record:
            return self._refused(
                "nothing was supplied to change: give a representation (codes or a "
                "notation) and/or a description"
            )
        records = tuple(updated if existing is record else existing for existing in configuration.records)
        return self._commit(configuration.with_records(records))

    # -- alignments and references (§15 set_alignment / set_references) ---------------

    def set_alignment(
        self,
        record_key: str,
        mode: str,
        inline_text=None,
        external_path=None,
        paired_inline_text=None,
        paired_external_path=None,
    ) -> MutationOutput:
        """Set a polymer record's alignment mode.

        Protein records accept ``automatic`` / ``free`` / ``unpaired`` /
        ``paired`` / ``both``; RNA records accept ``automatic`` / ``free`` /
        ``provided``. Source-carrying modes need exactly one of
        ``inline_text`` / ``external_path``.

        ``both`` accepts an independent paired source through
        ``paired_inline_text`` / ``paired_external_path``. When it is not
        supplied, the unpaired source feeds both sides (the historical
        one-file behaviour).
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not isinstance(record, (FamilyARecord, FamilyBRecord)):
            return self._unknown_record(record_key)
        paired_supplied = any(
            value not in (None, "")
            for value in (paired_inline_text, paired_external_path)
        )
        # automatic/free leave alignment to the deployment or to sequence
        # search: they carry no source, and demanding one would refuse
        # exactly the modes users most commonly want. Source-carrying
        # modes validate theirs below.
        if mode in ("automatic", "free"):
            if inline_text or external_path or paired_supplied:
                return self._refused("alignment mode %r takes no source" % mode)
            source = None
            paired_source = None
        else:
            source, failure = self._source(inline_text, external_path)
            if failure is not None:
                return failure
            paired_source = source
            if paired_supplied and mode != "both":
                return self._refused(
                    "a paired-side source is only accepted by the 'both' mode"
                )
            if paired_supplied:
                paired_source, failure = self._source(
                    paired_inline_text, paired_external_path
                )
                if failure is not None:
                    return failure
        try:
            if isinstance(record, FamilyARecord):
                alignment = self._protein_alignment(mode, source, paired_source)
            else:
                alignment = self._rna_alignment(mode, source)
        except ValueError as error:
            return self._refused(str(error))
        if alignment is None:
            return self._refused(
                "unknown alignment mode %r for a %s record"
                % (mode, "protein" if isinstance(record, FamilyARecord) else "RNA")
            )
        updated = record.with_alignment(alignment)
        records = tuple(updated if existing is record else existing for existing in configuration.records)
        return self._commit(configuration.with_records(records))

    def _protein_alignment(self, mode: str, source, paired_source=None):
        if mode == "automatic":
            return AlignmentAutomatic()
        if mode == "free":
            return AlignmentFree()
        if mode in ("unpaired", "unpaired_only"):
            return AlignmentUnpairedOnly(self._need(source, mode))
        if mode in ("paired", "paired_only"):
            return AlignmentPairedOnly(self._need(source, mode))
        if mode == "both":
            return AlignmentBoth(
                self._need(source, mode),
                paired_source=paired_source,
            )
        return None

    def _rna_alignment(self, mode: str, source):
        if mode == "automatic":
            return SingleAutomatic()
        if mode == "free":
            return SingleFree()
        if mode == "provided":
            return SingleProvided(self._need(source, mode))
        return None

    def _need(self, source, mode: str):
        if source is None:
            raise ValueError("alignment mode %r needs a source (inline text or an external path)" % mode)
        return source

    def _source(self, inline_text, external_path):
        if bool(inline_text) == bool(external_path):
            message = (
                "choose exactly one of inline text or an external path"
                if inline_text
                else "this choice needs exactly one of inline text or an external path"
            )
            return None, self._refused(message)
        if inline_text:
            return Inline(inline_text), None
        return External(PathSpec(external_path)), None

    def set_references(self, record_key: str, references=None) -> MutationOutput:
        """Set a protein record's structural references.

        No argument: template search stays allowed (templates omitted).
        ``references=()``: explicitly template-free. A sequence of
        ``ReferenceInput``: an explicit reference list.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        primary, failure = self._key(record_key)
        if failure is not None:
            return failure
        record = self._record_for(configuration, primary)
        if record is None or not isinstance(record, FamilyARecord):
            return self._unknown_record(record_key)
        if references is None:
            reference_set = SearchAllowed()
        else:
            sequence_length = len(record.sequence)
            built = []
            for entry in references:
                source, failure = self._source(
                    getattr(entry, "inline_text", None), getattr(entry, "external_path", None)
                )
                if failure is not None:
                    return failure
                pairs, issue = validate_reference(entry, sequence_length)
                if issue is not None:
                    return self._refused(issue.message)
                try:
                    built.append(ReferenceRecord(source, pairs))
                except (ModelError, ValueError, TypeError) as error:
                    return self._refused(str(error))
            reference_set = Explicit(tuple(built))
        updated = record.with_references(reference_set)
        records = tuple(updated if existing is record else existing for existing in configuration.records)
        return self._commit(configuration.with_records(records))

    # -- components (§15 set_component_definition) ----------------------------------

    def set_component_definition(self, inline_text=None, external_path=None) -> MutationOutput:
        """Define the component chemistry inline or as an external file."""
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        source, failure = self._source(inline_text, external_path)
        if failure is not None:
            return failure
        return self._commit(configuration.with_component_definition(source))

    def clear_component_definition(self) -> MutationOutput:
        """Remove the job's custom component (userCCD) definition entirely.

        The definition is one resource (inline text or an external path);
        clearing it returns the job to having none, which is the state a new
        job starts in — never an empty inline string, which would emit a
        bogus ``userCCD`` field.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        return self._commit(configuration.with_component_definition(None))

    # -- linkages (§15 add_linkage / remove_linkage) ---------------------------------

    def add_linkage(self, a_key: str, a_residue: int, a_atom: str, b_key: str, b_residue: int, b_atom: str) -> MutationOutput:
        """Bond two addressable endpoints; both record keys must resolve
        through the registry (identity is the sole resolution authority)."""
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        registry = configuration.identity
        try:
            endpoint_a = LinkEndpoint(registry.resolve_strict(EntityId(a_key)), ResidueRef(int(a_residue)), a_atom)
            endpoint_b = LinkEndpoint(registry.resolve_strict(EntityId(b_key)), ResidueRef(int(b_residue)), b_atom)
            linkage = Linkage(endpoint_a, endpoint_b)
        except (ModelError, IdentityError, ValueError, TypeError) as error:
            return MutationOutput(ok=False, failure_reason=FailureReason.UNKNOWN_RECORD, message=str(error))
        return self._commit(configuration.with_linkages(configuration.linkages + (linkage,)))

    def remove_linkage(self, index: int) -> MutationOutput:
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        if not isinstance(index, int) or not 0 <= index < len(configuration.linkages):
            return self._refused(
                "linkage index %r does not exist (%d linkages present)"
                % (index, len(configuration.linkages))
            )
        linkages = tuple(
            existing
            for position, existing in enumerate(configuration.linkages)
            if position != index
        )
        return self._commit(configuration.with_linkages(linkages))

    # -- format target (§15 set_format_target) ----------------------------------------

    def set_format_target(self, version=None, dialect="STANDALONE_AF3", evidence=None) -> MutationOutput:
        """Pin a format version, optionally recording provenance.

        ``evidence`` optionally cites the observation behind the pin (e.g.
        a ``PIN-nnn`` record the operator verified in the deployment log).
        The citation travels in the model; no runtime code reads any
        document to obtain it, and nothing requires one — the pin itself
        is the explicit choice. ``version=None`` keeps the selection
        Unverified, which validation still refuses as an explicit state.
        """
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        try:
            selection = (
                Pinned(int(version), evidence=evidence or "")
                if version is not None
                else None
            )
            # ``dialect`` arrives as the member name ("STANDALONE_AF3");
            # ``Dialect``'s constructor takes the member *value*.
            member_value = getattr(Dialect, dialect, None) if isinstance(dialect, str) else None
            resolved = Dialect(member_value if member_value is not None else dialect)
            target = FormatTarget(version_selection=selection, dialect=resolved)
        except (ValueError, TypeError, ConfigurationError) as error:
            return self._refused(str(error))
        return self._commit(configuration.with_format_target(target))

    def unset_format_target(self) -> MutationOutput:
        configuration = self._configuration()
        if configuration is None:
            return self._not_open()
        return self._commit(configuration.with_format_target(FormatTarget()))
