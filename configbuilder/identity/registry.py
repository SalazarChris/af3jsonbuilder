"""Identifier and reference authority (IMPLEMENTATION_PLAN.md §6.2, §8).

One module answers every identifier question: allocation, uniqueness,
collision handling, rename rewriting, resolution. Allocation is a pure
function of the ordered set of already-assigned identifiers — no randomness,
no clock, no hash-order dependence (§8.1). Identifier order carries no
meaning beyond reproducibility (§8.1.1).

This module imports nothing from other project modules (plan §5.3 rule 1).
"""

from __future__ import annotations

import string
from typing import Dict, FrozenSet, Optional, Tuple

from configbuilder.identity.identifiers import EntityId, Multiplicity

__all__ = [
    "Assignment",
    "DuplicateIdError",
    "IdAllocator",
    "IdentityError",
    "IdentityRegistry",
    "RegistrySnapshot",
    "RenameMap",
]

_LETTERS = string.ascii_uppercase


class IdentityError(Exception):
    """Base class for identity-authority errors."""


class DuplicateIdError(IdentityError):
    """An identifier was explicitly assigned that the registry already holds.

    Plan §8.1: explicit user assignment of a taken identifier is refused,
    never silently renamed. The registry keeps this raise-based contract;
    the Phase 4 validation engine converts it to an R-ENT-002 finding at
    the engine boundary (see CHECKLIST.md Phase 4) so user-caused errors
    reach the UI as findings, not exceptions.
    """


def _progression():
    """Deterministic monotonic progression past the single-character range.

    Spec §7.6: the contract imposes no 26-identifier ceiling. The shape of
    the progression is an implementation detail of the allocator (plan §8.1);
    the registry enforces only format and uniqueness.
    """
    for letter in _LETTERS:
        yield letter
    for first in _LETTERS:
        for second in _LETTERS:
            yield first + second
    for first in _LETTERS:
        for second in _LETTERS:
            for third in _LETTERS:
                yield first + second + third


class IdAllocator:
    """Hands out the next unused identifier in the fixed progression."""

    def next(self, assigned: FrozenSet[str]) -> str:
        """The first value of the progression not in ``assigned``.

        Pure: same assigned set, same result. Raises when the progression is
        exhausted rather than wrapping into ambiguity.
        """
        for candidate in _progression():
            if candidate not in assigned:
                return candidate
        raise IdentityError("identifier space exhausted (plan §8.1 progression)")


class RegistrySnapshot:
    """An immutable view of the registry's identifier set and assignments."""

    __slots__ = ("_ids", "_assignments")

    def __init__(self, ids: Tuple[EntityId, ...], assignments: Dict[EntityId, FrozenSet[str]]) -> None:
        object.__setattr__(self, "_ids", tuple(ids))
        object.__setattr__(self, "_assignments", dict(assignments))

    @property
    def ids(self) -> Tuple[EntityId, ...]:
        return self._ids

    @property
    def assignments(self) -> Dict[EntityId, FrozenSet[str]]:
        return dict(self._assignments)

    def values(self) -> FrozenSet[str]:
        return frozenset(entity.value for entity in self._ids)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RegistrySnapshot):
            return self._ids == other._ids and self._assignments == other._assignments
        return NotImplemented

    def __repr__(self) -> str:
        return "RegistrySnapshot(ids=%r)" % ([e.value for e in self._ids],)


class RenameMap:
    """The result of a registry rename: old -> new, for reference rewriting.

    Plan §8: ``rename`` returns a rewrite map; ``app`` applies it to the
    configuration in one operation. A rename never happens outside this path.
    """

    __slots__ = ("_mapping",)

    def __init__(self, mapping: Dict[EntityId, EntityId]) -> None:
        object.__setattr__(self, "_mapping", dict(mapping))

    @property
    def mapping(self) -> Dict[EntityId, EntityId]:
        return dict(self._mapping)

    def rewrite(self, entity_id: EntityId) -> EntityId:
        """The identifier a reference should now point at."""
        return self._mapping.get(entity_id, entity_id)

    def __len__(self) -> int:
        return len(self._mapping)

    def __repr__(self) -> str:
        inner = {old.value: new.value for old, new in self._mapping.items()}
        return "RenameMap(%r)" % (inner,)


class Assignment:
    """One allocated-or-assigned identifier and what it is reserved for."""

    __slots__ = ("entity_id", "owner")

    def __init__(self, entity_id: EntityId, owner: Optional[str]) -> None:
        self.entity_id = entity_id
        self.owner = owner

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Assignment):
            return self.entity_id == other.entity_id and self.owner == other.owner
        return NotImplemented

    def __repr__(self) -> str:
        return "Assignment(%r, owner=%r)" % (self.entity_id.value, self.owner)


class IdentityRegistry:
    """The registry held by the Configuration (plan §7.5).

    Responsibilities (plan §6.2): allocation, uniqueness, collision
    detection, format compliance, reference resolution, deterministic
    ordering, cloning. Every identifier it hands out is reserved across copy
    multiplicity (plan §8.2).
    """

    def __init__(self, records=None) -> None:
        # records: iterable of (Multiplicity, owner) preserving registry order.
        object.__setattr__(self, "_ordered", [])
        object.__setattr__(self, "_assigned", {})
        # Every value this registry generation has ever reserved. Allocation
        # draws from this set, not from current reservations, so a released
        # identifier is not handed out again (plan §8.3). Released values are
        # simply ever-assigned values no longer in ``_assigned``.
        object.__setattr__(self, "_ever_assigned", set())
        # Group membership per reserved identifier (plan §8.2): which
        # multiplicity each identifier was reserved as part of.
        object.__setattr__(self, "_multiplicity_index", {})
        object.__setattr__(self, "_allocator", IdAllocator())
        for multiplicity, owner in records or ():
            for entity_id in multiplicity:
                self._reserve(entity_id, owner, multiplicity)
                self._ordered.append(entity_id)

    # -- internal reservation ------------------------------------------------

    def _reserve(self, entity_id: EntityId, owner: Optional[str], group: Optional[Multiplicity] = None) -> None:
        if entity_id in self._assigned:
            raise DuplicateIdError(
                "identifier %r is already assigned in this registry" % (entity_id.value,)
            )
        if group is None:
            group = Multiplicity([entity_id])
        self._assigned[entity_id] = owner
        self._ever_assigned.add(entity_id.value)
        self._multiplicity_index[entity_id] = group

    # -- allocation ----------------------------------------------------------

    def allocate(self, owner: Optional[str] = None) -> EntityId:
        """Reserve and return the next unused identifier.

        Deterministic: the same starting state always yields the same
        identifier. Taken identifiers are skipped (plan §8.1).
        """
        assigned = self._ever_assigned
        value = self._allocator.next(frozenset(assigned))
        entity_id = EntityId(value)
        self._reserve(entity_id, owner)
        self._ordered.append(entity_id)
        return entity_id

    def assign(self, requested: str, owner: Optional[str] = None) -> EntityId:
        """Reserve a user-chosen identifier, refusing taken ones explicitly."""
        entity_id = EntityId(requested)
        if entity_id in self._assigned:
            raise DuplicateIdError(
                "identifier %r is already assigned; it must be changed, not silently renamed"
                % (entity_id.value,)
            )
        self._reserve(entity_id, owner)
        self._ordered.append(entity_id)
        return entity_id

    def reserve_multiplicity(self, multiplicity: Multiplicity, owner: Optional[str] = None) -> Multiplicity:
        """Reserve every identifier of a copy multiplicity (plan §8.2)."""
        for entity_id in multiplicity:
            self._reserve(entity_id, owner, multiplicity)
            self._ordered.append(entity_id)
        return multiplicity

    # -- queries ---------------------------------------------------------------

    def multiplicity_of(self, entity_id: EntityId) -> Multiplicity:
        """The reserved multiplicity containing ``entity_id`` (plan §8.2).

        Group membership is remembered in reservation order, so variants can
        remove or re-key a whole copy group through identity rather than by
        list position (plan §12.1). Raises for an identifier this registry
        does not hold.
        """
        if entity_id not in self._assigned:
            raise IdentityError("unassigned identifier %r" % (entity_id.value,))
        return self._multiplicity_index[entity_id]

    def assigned_values(self) -> FrozenSet[str]:
        return frozenset(entity.value for entity in self._assigned)

    def is_taken(self, value: str) -> bool:
        return EntityId(value) in self._assigned

    def order(self) -> Tuple[EntityId, ...]:
        """Allocation order. Deterministic; carries no meaning (plan §8.1.1)."""
        return tuple(self._ordered)

    def owner_of(self, entity_id: EntityId) -> Optional[str]:
        return self._assigned.get(entity_id)

    def assignments(self) -> Tuple[Assignment, ...]:
        return tuple(
            Assignment(entity, self._assigned[entity]) for entity in self._ordered
        )

    def snapshot(self) -> RegistrySnapshot:
        return RegistrySnapshot(self.order(), dict(self._assigned))

    # -- reference integrity ----------------------------------------------------

    def resolve(self, entity_id: EntityId) -> bool:
        """True when the identifier is held by this registry (plan §8).

        Linkage endpoints and any future reference resolve only through this
        operation.
        """
        return entity_id in self._assigned

    def resolve_strict(self, entity_id: EntityId) -> EntityId:
        if not self.resolve(entity_id):
            raise IdentityError("unresolved reference: %r" % (entity_id.value,))
        return entity_id

    # -- mutation ---------------------------------------------------------------

    def _release_registered(self, entity_id: EntityId, owner: Optional[str]) -> None:
        del self._assigned[entity_id]
        del self._multiplicity_index[entity_id]
        self._ordered.remove(entity_id)

    def release(self, entity_id: EntityId) -> None:
        """Release an identifier (plan §8.3: removals release per variant).

        The caller decides reuse policy; the registry forgets the
        reservation. Released identifiers are not automatically handed out
        again by ``allocate`` in this registry generation.
        """
        if entity_id not in self._assigned:
            raise IdentityError("cannot release unassigned identifier %r" % (entity_id.value,))
        self._release_registered(entity_id, self._assigned[entity_id])

    def release_multiplicity(self, multiplicity: Multiplicity, missing_ok: bool = False) -> None:
        """Release every identifier of a copy multiplicity (plan §8.2, §8.3).

        Atomic: if any member is not currently reserved, nothing is released
        — the call raises, or skips silently under ``missing_ok``. Released
        identifiers stay in the ever-assigned set, so ``allocate`` does not
        hand them back out within this registry generation.
        """
        entity_ids = tuple(multiplicity)
        missing = [e for e in entity_ids if e not in self._assigned]
        if missing and not missing_ok:
            raise IdentityError(
                "cannot release multiplicity %r: unreserved members %s"
                % (multiplicity, ", ".join(repr(e.value) for e in missing))
            )
        for entity_id in entity_ids:
            if entity_id in self._assigned:
                self._release_registered(entity_id, self._assigned[entity_id])

    def rename(self, old: EntityId, new_value: str) -> RenameMap:
        """Rename an identifier, returning the rewrite map for references.

        The new identifier must be valid and free. The mapping covers the
        renamed identifier only; multi-identifier multiplicities keep their
        other members.
        """
        if old not in self._assigned:
            raise IdentityError("cannot rename unassigned identifier %r" % (old.value,))
        new = EntityId(new_value)
        if new == old:
            return RenameMap({})
        if new in self._assigned:
            raise DuplicateIdError(
                "cannot rename %r to taken identifier %r" % (old.value, new.value)
            )
        owner = self._assigned.pop(old)
        self._assigned[new] = owner
        self._ever_assigned.add(new.value)
        # Rewrite the group membership: every member of the old group now
        # shares a group carrying the new identifier (plan §12.1: edits
        # resolve through identity, so a rename must not orphan a copy
        # group's shape).
        group = self._multiplicity_index.pop(old)
        new_group = Multiplicity([new if entity == old else entity for entity in group])
        for entity in new_group:
            if entity in self._assigned:
                self._multiplicity_index[entity] = new_group
        self._ordered[self._ordered.index(old)] = new
        return RenameMap({old: new})

    def clone(self) -> "IdentityRegistry":
        """A registry holding the same identifiers (plan §8.3: copies are
        preserved, not reallocated; plan §12.4: cloned per variant)."""
        return IdentityRegistry.from_data(self.to_data())

    # -- persistence data (plan §21 Phase 9) -----------------------------------

    def to_data(self) -> Dict[str, object]:
        """Export this registry as plain persistence data.

        The ordered identifier list, the owner map, the ever-assigned set,
        and the copy-group shapes (plan §8.2). Identifiers are stored as
        their string values, so the payload survives JSON round-trips
        unchanged. Persisting ``ever_assigned`` keeps released identifiers
        retired after a project is reopened (plan Phase 9: reopening never
        reassigns); persisting ``groups`` keeps copy multiplicity editable
        through identity afterwards.
        """
        seen_group_ids = set()
        groups = []
        for entity in self._ordered:
            group = self._multiplicity_index[entity]
            if id(group) not in seen_group_ids:
                seen_group_ids.add(id(group))
                groups.append([member.value for member in group])
        return {
            "order": [entity.value for entity in self._ordered],
            "owners": {
                entity.value: self._assigned.get(entity)
                for entity in self._ordered
            },
            "ever_assigned": sorted(self._ever_assigned),
            "groups": groups,
        }

    @classmethod
    def from_data(cls, data: Dict[str, object]) -> "IdentityRegistry":
        """Rebuild a registry from :meth:`to_data` data.

        Every value is re-validated through the model constructors (plan
        Phase 9: persisted data cannot inject invalid models). The rebuilt
        registry holds every identifier of the saved order, keeps retired
        values in the ever-assigned set, and its allocator continues past
        them (plan §8.1, §8.3).
        """
        if not isinstance(data, dict):
            raise IdentityError("registry data must be an object")
        order = data.get("order")
        owners = data.get("owners")
        ever = data.get("ever_assigned")
        if not isinstance(order, list) or not all(isinstance(v, str) for v in order):
            raise IdentityError("registry data 'order' must be a list of identifier strings")
        if not isinstance(owners, dict):
            raise IdentityError("registry data 'owners' must be an object")
        if ever is None:
            ever = list(order)
        if not isinstance(ever, list) or not all(isinstance(v, str) for v in ever):
            raise IdentityError("registry data 'ever_assigned' must be a list of identifier strings")
        ever_values = set(ever)
        for value in order:
            if value not in ever_values:
                raise IdentityError(
                    "registry data: identifier %r is in 'order' but missing from 'ever_assigned'" % value
                )
        groups = data.get("groups")
        if groups is None:
            # Legacy payload from before group persistence: every identifier
            # was its own reservation.
            groups = [[value] for value in order]
        if not isinstance(groups, list) or not all(
            isinstance(group, list) and all(isinstance(v, str) for v in group)
            for group in groups
        ):
            raise IdentityError("registry data 'groups' must be a list of identifier lists")
        try:
            parsed_groups = [Multiplicity(group) for group in groups]
        except ValueError as error:
            raise IdentityError("registry data 'groups' holds an invalid multiplicity: %s" % error)
        flattened = [value for group in groups for value in group]
        if len(flattened) != len(set(flattened)):
            raise IdentityError(
                "registry data 'groups' must not repeat an identifier across groups"
            )
        flattened_set = set(flattened)
        uncovered = [value for value in order if value not in flattened_set]
        if uncovered:
            raise IdentityError(
                "registry data 'groups' must cover every identifier in 'order' (missing: %s)"
                % ", ".join(uncovered)
            )
        orphans = sorted(flattened_set - set(order) - ever_values)
        if orphans:
            raise IdentityError(
                "registry data 'groups' names unknown identifiers: %s" % ", ".join(orphans)
            )

        registry = cls()
        order_values = set(order)
        for group in parsed_groups:
            for member in group:
                if member.value not in order_values:
                    continue  # a released member of the group's shape
                raw_owner = owners.get(member.value)
                if raw_owner is not None and not isinstance(raw_owner, str):
                    raise IdentityError(
                        "registry data owner for %r must be a string or null" % member.value
                    )
                registry._reserve(member, raw_owner, group)
                registry._ordered.append(member)
        registry._ever_assigned = set(ever_values)
        return registry
