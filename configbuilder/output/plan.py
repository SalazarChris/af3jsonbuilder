"""The output planner (IMPLEMENTATION_PLAN.md §13.1, §13.3, §13.5).

``plan`` is pure: no writes, no clock, no randomness — the same inputs
yield the same plan. It turns (name payloads, resource requirements,
policies, a read-only view of the filesystem) into the full list of
intended paths with their actions and payload fingerprints. The review
step shows this plan before anything is written; nothing is ever written
without a plan.

Actions (§13.3): ``create`` (target absent), ``overwrite`` (target exists;
same bytes, or policy Overwrite), ``skip`` (policy Skip), ``conflict``
(policy Fail and target holds different bytes). ``Versioned`` is resolved
at plan time to the actual suffixed path (deterministic numeric suffix),
so the plan always shows the real final layout.

This layer has no contract logic and no validation (plan §5.3 rule 4):
inputs are plain data — byte payloads, name strings, raw resource paths —
and the filesystem is reached only through the read-only ``FileView`` port
so planning is testable without a disk. Cross-machine hazards (absolute
resource paths) are collected as warnings, which the caller surfaces
through the normal validation/preflight reporting — planning reports,
it does not validate.
"""

from __future__ import annotations

import hashlib
import os
import re

from configbuilder.output.naming import (
    NameError,
    slug,
    variant_directory_name,
    variant_file_name,
)
from configbuilder.output.policies import OverwritePolicy, PathPolicy

__all__ = ["PlanEntry", "ResourceEntry", "OutputPlan", "FileView", "OsFileView", "conflict_message", "fingerprint", "plan", "resolve_resources_into"]


def fingerprint(data: bytes) -> str:
    """SHA-256 of a payload, hex — the plan's content address."""
    return hashlib.sha256(data).hexdigest()


def conflict_message(path: str) -> str:
    """The one wording for a refused write (policy ``Fail`` and the target
    holds different bytes). It names the file and both ways out, so the
    refusal is actionable where the user reads it, and both planning routes
    (the base's own file and a variant run) say the same thing."""
    return (
        "%s already exists with different content; delete or rename that file, "
        "or write the job to a different output folder" % path
    )


class PlanEntry:
    """One input file that will exist after execution, with its action."""

    __slots__ = ("path", "action", "payload", "payload_fingerprint", "exists")

    def __init__(self, path, action: str, payload: bytes, exists: bool) -> None:
        self.path = path
        self.action = action
        self.payload = payload
        self.payload_fingerprint = fingerprint(payload)
        self.exists = exists

    def __repr__(self) -> str:
        return "PlanEntry(%s, %s, %d bytes)" % (self.path, self.action, len(self.payload))


class ResourceEntry:
    """One external resource: where it comes from, where it will be, and
    what string the generated file will carry (§13.5)."""

    __slots__ = ("raw_path", "wire_field", "planned_path", "emitted_path", "copied")

    def __init__(self, raw_path: str, wire_field: str, planned_path, emitted_path: str, copied: bool) -> None:
        self.raw_path = raw_path
        self.wire_field = wire_field
        self.planned_path = planned_path  # absolute destination when copied, else None
        self.emitted_path = emitted_path  # the string written into the wire document
        self.copied = copied

    def __repr__(self) -> str:
        return "ResourceEntry(%r -> %r)" % (self.raw_path, self.emitted_path)


class OutputPlan:
    """The complete, reviewable intent of one generation run."""

    __slots__ = (
        "project_slug",
        "output_root",
        "overwrite_policy",
        "path_policy",
        "entries",
        "resources",
        "conflicts",
        "warnings",
    )

    def __init__(self, project_slug, output_root, overwrite_policy, path_policy, entries, resources, conflicts, warnings) -> None:
        self.project_slug = project_slug
        self.output_root = output_root
        self.overwrite_policy = overwrite_policy
        self.path_policy = path_policy
        self.entries = tuple(entries)
        self.resources = tuple(resources)
        self.conflicts = tuple(conflicts)
        self.warnings = tuple(warnings)

    def __repr__(self) -> str:
        return "OutputPlan(%s, %d files, %d conflicts)" % (self.project_slug, len(self.entries), len(self.conflicts))


class FileView:
    """Read-only filesystem questions for planning (§5.3 rule 8 confines
    filesystem access to this layer; reads are injectable for tests)."""

    def exists(self, path) -> bool:  # pragma: no cover - trivial interface
        raise NotImplementedError

    def read(self, path) -> bytes:  # pragma: no cover - trivial interface
        raise NotImplementedError


class OsFileView(FileView):
    """The real filesystem, read-only. The default: a plan that ignores
    what already exists would mislabel overwrites as creates."""

    def exists(self, path) -> bool:
        return os.path.exists(path)

    def read(self, path) -> bytes:
        with open(path, "rb") as handle:
            return handle.read()


def _forward_slashes(path: str) -> str:
    """Emitted paths always use forward slashes (plan §13.5)."""
    return path.replace("\\", "/")


def _cannot_travel(raw: str) -> bool:
    """Drive-letter or UNC absolute paths are valid where they were typed
    and meaningless on the (Linux) execution system — the §13.5 warning
    case. Detected by form, not by ``os.path.isabs``, so the planner's
    advice is identical on every host platform."""
    return bool(re.match(r"^[A-Za-z]:/", raw)) or raw.startswith("//")


def _asset_name(raw_path: str) -> str:
    """Filesystem-safe name for a copied asset: slugged stem, preserved
    extension. Asset names are not component-style names (spec §9.6's
    underscore rule targets job names), and the external system keys on
    the extension — so it survives."""
    basename = os.path.basename(raw_path.replace("\\", "/"))
    stem, ext = os.path.splitext(basename)
    if not stem:
        stem = ext.lstrip(".")
        ext = ""
    safe_ext = ext.lower() if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", ext) else ""
    return slug(stem) + safe_ext


def _versioned_path(directory_path, file_name: str, payload: bytes, filesystem: FileView):
    """First free ``<stem>-<n><ext>`` — deterministic, plan-resolved (§13.3)."""
    stem, ext = os.path.splitext(file_name)
    counter = 1
    while True:
        candidate = os.path.join(directory_path, "%s-%d%s" % (stem, counter, ext))
        if not filesystem.exists(candidate):
            return candidate
        if filesystem.read(candidate) == payload:
            return candidate  # an earlier run already wrote these exact bytes
        counter += 1


def decide_action(file_path, payload: bytes, overwrite_policy: OverwritePolicy, filesystem: FileView):
    """The §13.3 action table for one planned file — the single home of
    the policy decision, shared by ``plan`` and by callers planning files
    outside the per-variant layout (the §13.1 manifest).

    Returns ``(path, action, exists)``; under ``Versioned`` the path is
    the resolved suffixed destination.
    """
    exists = filesystem.exists(file_path)
    if not exists:
        return file_path, "create", exists
    if filesystem.read(file_path) == payload:
        return file_path, "overwrite", exists  # identical bytes; visible in the plan, harmless
    if overwrite_policy == OverwritePolicy("Fail"):
        return file_path, "conflict", exists
    if overwrite_policy == OverwritePolicy("Skip"):
        return file_path, "skip", exists
    if overwrite_policy == OverwritePolicy("Overwrite"):
        return file_path, "overwrite", exists
    # Versioned: the plan resolves the real suffixed destination
    return (
        _versioned_path(os.path.dirname(file_path), os.path.basename(file_path), payload, filesystem),
        "create",
        exists,
    )


def _resolve_resources(requirements, output_root, project_slug: str, variant_key: str, path_policy: PathPolicy, filesystem: FileView):
    """Per §13.5: resolve each requirement under the path policy, into
    the per-variant layout's directory. Returns ``(resource_entries,
    warnings)``. Warnings carry the cross-machine hazard messages
    (absolute paths that cannot travel), as data for the caller to
    surface — this layer reports, it does not validate.
    """
    variant_dir = os.path.join(output_root, project_slug, variant_directory_name(project_slug, variant_key))
    return resolve_resources_into(requirements, output_root, variant_dir, path_policy, filesystem)


def resolve_resources_into(requirements, output_root, directory_path: str, path_policy: PathPolicy, filesystem: FileView):
    """§13.5 resolution into an explicit directory — the one home of the
    path-policy decision, shared by the per-variant layout and by the
    base configuration's own run (whose file sits directly under the
    project directory, so there is no variant subdirectory).

    Returns ``(resource_entries, warnings)``; see ``_resolve_resources``.
    """
    entries = []
    warnings = []
    variant_dir = directory_path
    assets_dir = os.path.join(variant_dir, "assets")
    seen = set()
    for requirement in requirements:
        raw = _forward_slashes(requirement.raw_path)
        key = (requirement.kind, raw)
        if key in seen:
            continue
        seen.add(key)
        if path_policy == PathPolicy("AsGiven"):
            emitted = raw
            planned = None
            copied = False
            if _cannot_travel(raw):
                warnings.append(
                    "resource %r is a drive-letter or UNC path and will not resolve on the execution "
                    "system; choose CopyIntoAssets or RelativeToOutput so the file travels" % raw
                )
        elif path_policy == PathPolicy("RelativeToOutput"):
            emitted = raw
            planned = None
            copied = False
            if _cannot_travel(raw):
                warnings.append(
                    "resource %r is a drive-letter or UNC path; RelativeToOutput cannot make it "
                    "relative — it resolves only on machines where that path exists" % raw
                )
        else:  # CopyIntoAssets — the default; the only travelling form (§13.5)
            emitted = None
            planned = None
            copied = False
            name = _asset_name(raw)
            planned = os.path.join(assets_dir, name)
            if filesystem.exists(planned):
                same_bytes = filesystem.read(planned) == (filesystem.read(raw) if filesystem.exists(raw) else None)
                if not same_bytes:
                    stem, ext = os.path.splitext(name)
                    counter = 1
                    while filesystem.exists(os.path.join(assets_dir, "%s-%d%s" % (stem, counter, ext))):
                        counter += 1
                    planned = os.path.join(assets_dir, "%s-%d%s" % (stem, counter, ext))
                    copied = True
            elif filesystem.exists(raw):
                copied = True
            else:
                copied = True  # the copy step will surface the missing source
                warnings.append(
                    "resource %r does not exist; the copy step will fail — check the path" % raw
                )
            emitted = _forward_slashes(os.path.relpath(planned, variant_dir))
        entries.append(ResourceEntry(requirement.raw_path, requirement.kind, planned, emitted, copied))
    return entries, warnings


def plan(
    name_payloads,
    output_root,
    project_name: str,
    overwrite_policy: OverwritePolicy = None,
    path_policy: PathPolicy = None,
    resources_by_variant=None,
    filesystem: FileView = None,
) -> OutputPlan:
    """Build the run's plan: one directory and input file per variant.

    ``name_payloads`` is an ordered mapping ``variant_key -> bytes`` (the
    encoded input file). ``resources_by_variant`` maps ``variant_key ->
    tuple of objects with ``.kind`` and ``.raw_path``. Collision detection
    is case-insensitive across the whole run (§13.2). Pure: nothing here
    touches the filesystem for writing.
    """
    overwrite_policy = overwrite_policy if overwrite_policy is not None else OverwritePolicy("Fail")
    path_policy = path_policy if path_policy is not None else PathPolicy("CopyIntoAssets")
    filesystem = filesystem if filesystem is not None else OsFileView()
    resources_by_variant = resources_by_variant or {}
    project_slug = slug(project_name)

    conflicts = []
    # Cross-run path collision detection (§13.2). The slug lower-cases, so
    # two keys differing only in case plan the *same* directory — as do two
    # keys whose difference lies beyond the slug's length cap. Any two
    # distinct keys mapping onto one path is a conflict everywhere (the
    # same project must lay out identically on Windows and Linux). A key
    # that cannot be slugged at all is reported, never crashed on.
    directories_by_key = {}
    seen_directories = {}
    for key in name_payloads:
        try:
            directory = variant_directory_name(project_slug, key)
        except NameError:
            conflicts.append(
                "variant key %r cannot be turned into a filesystem name; rename it" % (key,)
            )
            continue
        if directory in seen_directories:
            conflicts.append(
                "variant keys %r and %r plan the same directory %r; rename one"
                % (seen_directories[directory], key, directory)
            )
        seen_directories[directory] = key
        directories_by_key[key] = directory

    entries = []
    resources = []
    warnings = []
    for key, payload in name_payloads.items():
        if key not in directories_by_key:
            continue  # already reported as unnamable / colliding
        directory = directories_by_key[key]
        file_name = variant_file_name(project_slug, key)
        directory_path = os.path.join(output_root, project_slug, directory)
        file_path = os.path.join(directory_path, file_name)

        file_path, action, exists = decide_action(file_path, payload, overwrite_policy, filesystem)
        entries.append(PlanEntry(file_path, action, payload, exists))

        resource_entries, resource_warnings = _resolve_resources(
            resources_by_variant.get(key, ()), output_root, project_slug, key, path_policy, filesystem
        )
        resources.extend(resource_entries)
        warnings.extend(resource_warnings)

    if any(entry.action == "conflict" for entry in entries):
        for entry in entries:
            if entry.action == "conflict":
                conflicts.append(conflict_message(entry.path))

    return OutputPlan(
        project_slug=project_slug,
        output_root=output_root,
        overwrite_policy=overwrite_policy,
        path_policy=path_policy,
        entries=entries,
        resources=resources,
        conflicts=conflicts,
        warnings=warnings,
    )
