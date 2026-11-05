"""The executor (IMPLEMENTATION_PLAN.md §13.3, §13.4).

``execute(plan)`` performs the writes the plan lists — nothing more. All
writes are atomic per file (temporary file in the destination directory,
flush, then ``os.replace``), directories are created only as the plan
requires, and the run is all-or-nothing: any plan-level conflict, or any
resource whose source cannot be read, aborts before the first byte is
written. ``execute`` raises nothing for user-caused conditions; it returns
an ``OutputResult`` describing what happened (errors included).

Atomicity across the *whole* run (what a failed run leaves behind):

- files the plan would ``create`` are **removed again** if a later write
  fails, and the directories this run created are removed when empty — so a
  refusal does not leave a half-written batch behind;
- a file the plan would ``overwrite`` already existed before the run. Its old
  bytes are replaced by design, and cannot be restored; it is kept and the
  error says how many such files were left as rewritten. Nothing here ever
  deletes a file that existed before the run;
- per-file atomicity holds throughout: a failed file is its old content or
  absent, never a partial write.
"""

from __future__ import annotations

import os

from configbuilder.output.plan import OutputPlan

__all__ = ["OutputResult", "WriteOutcome", "execute"]


class WriteOutcome:
    """What happened to one planned file."""

    __slots__ = ("path", "action", "written", "bytes_written")

    def __init__(self, path, action: str, written: bool, bytes_written: int) -> None:
        self.path = path
        self.action = action
        self.written = written
        self.bytes_written = bytes_written

    def __repr__(self) -> str:
        return "WriteOutcome(%s, %s, written=%s)" % (self.path, self.action, self.written)


class OutputResult:
    """The executor's report: per-file outcomes, copied resources,
    directories created by this run, and pre-write errors (empty on
    success)."""

    __slots__ = ("outcomes", "copied_resources", "directories_created", "errors")

    def __init__(self, outcomes, copied_resources, directories_created, errors=()) -> None:
        self.outcomes = tuple(outcomes)
        self.copied_resources = tuple(copied_resources)
        self.directories_created = tuple(directories_created)
        self.errors = tuple(errors)

    def __repr__(self) -> str:
        return "OutputResult(%d files, %d resources, %d errors)" % (
            len(self.outcomes),
            len(self.copied_resources),
            len(self.errors),
        )


def _atomic_write(path, payload: bytes) -> int:
    """Write ``payload`` to ``path`` atomically: temp file in the same
    directory, flush + fsync, then ``os.replace`` (§13.4). A failure at
    any point removes the temporary file — the destination is either the
    complete old content or the complete new content, never a partial
    write."""
    temporary = os.path.join(os.path.dirname(path), ".%s.tmp" % os.path.basename(path))
    handle = open(temporary, "wb")
    try:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(temporary, path)
    except Exception:
        handle.close()
        if os.path.exists(temporary):
            os.remove(temporary)
        raise
    return len(payload)


def _copy_atomic(source, destination) -> None:
    """Copy a resource file atomically (same temp-then-replace pattern)."""
    with open(source, "rb") as handle:
        payload = handle.read()
    _atomic_write(destination, payload)


def _roll_back(
    unwritten_outcomes, created_directories, copied_resources, output_root
) -> tuple:
    """Undo the part of a failed run that can be undone safely.

    Only paths this run **created** are removed: an entry whose action was
    ``create`` and an asset copied into a directory this run made. A file the
    plan overwrote existed before the run and is never deleted here — the old
    bytes are gone, so removing it would destroy the user's file instead of
    restoring it.

    Returns ``(removed_paths, kept_pre_existing_paths)`` for the error
    message. Failures to remove are tolerated: a rollback is a courtesy after
    a filesystem error, and a second error must not hide the first.
    """
    created = set(created_directories)
    removed = []
    kept = []
    for outcome in unwritten_outcomes:
        if not outcome.written:
            continue
        if outcome.action != "create":
            kept.append(outcome.path)
            continue
        try:
            os.remove(outcome.path)
        except OSError:
            kept.append(outcome.path)
        else:
            removed.append(outcome.path)
    for source, destination in copied_resources:
        if os.path.dirname(destination) not in created:
            continue  # its directory pre-existed; the asset may have too
        try:
            os.remove(destination)
        except OSError:
            continue
        else:
            removed.append(destination)
    def _remove_tree_of_empty_directories(directory) -> None:
        """Remove ``directory`` and its now-empty ancestors, never elsewhere.

            ``makedirs`` created the planned directories *and* every parent
            that did not exist yet (``<root>/P``, not just ``<root>/P/P__k``),
            so the rollback walks up as long as the directory is empty and
            still under the run's own output root. It stops at the first
            non-empty ancestor: that is where something not ours lives.
        """
        root = os.path.abspath(str(output_root)) if output_root else None
        current = os.path.abspath(directory)
        while root is not None and (
            current == root or current.startswith(root + os.sep)
        ):
            if current == root:
                return  # the output root itself is the user's, not ours
            try:
                os.rmdir(current)
            except OSError:
                return  # still holds something that was not ours to delete
            current = os.path.dirname(current)

    for directory in sorted(created, key=len, reverse=True):
        _remove_tree_of_empty_directories(directory)
    return tuple(removed), tuple(kept)


def execute(plan: OutputPlan) -> OutputResult:
    """Perform the plan's writes. All-or-nothing.

    Identical plans over identical filesystem states produce identical
    results; a plan with conflicts, or referencing unreadable resources,
    writes nothing and reports why.
    """
    if plan.conflicts:
        return OutputResult(
            (),
            (),
            (),
            errors=("plan has conflicts; nothing was written (overwrite policy %s)" % plan.overwrite_policy,),
        )

    directories_needed = set()
    for entry in plan.entries:
        directories_needed.add(os.path.dirname(entry.path))
    for resource in plan.resources:
        if resource.planned_path is not None and resource.copied:
            directories_needed.add(os.path.dirname(resource.planned_path))

    # Pre-write verification: a resource whose source cannot be read would
    # otherwise tear the run mid-write (§13.4 all-or-nothing).
    errors = []
    for resource in plan.resources:
        if resource.planned_path is None or not resource.copied:
            continue
        if not os.path.isfile(resource.raw_path):
            errors.append("resource source %r is missing; nothing was written" % resource.raw_path)
    if errors:
        return OutputResult((), (), (), errors=errors)

    pre_existing = {path for path in directories_needed if os.path.isdir(path)}
    outcomes = []
    copied_resources = []
    created = tuple(sorted(directories_needed - pre_existing))
    target = None
    creating = False
    try:
        for directory in sorted(directories_needed - pre_existing):
            target = directory
            creating = True
            os.makedirs(directory, exist_ok=True)
        creating = False
        for entry in plan.entries:
            if entry.action == "skip":
                outcomes.append(WriteOutcome(entry.path, "skip", False, 0))
                continue
            target = entry.path
            outcomes.append(WriteOutcome(entry.path, entry.action, True, _atomic_write(entry.path, entry.payload)))
        for resource in plan.resources:
            if resource.planned_path is None or not resource.copied:
                continue
            target = resource.planned_path
            _copy_atomic(resource.raw_path, resource.planned_path)
            copied_resources.append((resource.raw_path, resource.planned_path))
    except OSError as error:
        # A filesystem refusal is a user-caused condition like every other
        # one this function reports: the destination may be a name the
        # platform reserves (Windows devices such as ``nul``), a path whose
        # parent is an existing *file*, or a directory the user cannot write.
        # Raising sent a traceback to a beginner who had merely typed a name;
        # the caller prints ``errors`` and can offer another path. Only
        # ``OSError`` is caught -- a genuine defect in this code must still
        # fail loudly. Per-file atomicity is unchanged: each file is its old
        # content or its new content, never a partial write.
        reason = error.strerror or error
        if creating:
            # Name what actually failed: the user typed an output directory
            # whose parent is a file, or a name the platform reserves.
            detail = "could not create the directory %r: %s" % (target, reason)
            if os.path.isfile(plan.output_root):
                detail += "; the output directory %r is a file" % plan.output_root
        else:
            detail = "could not write %r: %s" % (target, reason)
        written = [outcome for outcome in outcomes if outcome.written]
        if written or copied_resources:
            # Only reachable when a later write fails after earlier ones
            # succeeded. Files this run created are removed again; files it
            # replaced existed before and stay. Say which happened, so the
            # user is never left to guess what a failed run left behind.
            removed, kept = _roll_back(
                written, created, copied_resources, plan.output_root
            )
            if removed:
                detail += "; %d file(s) created by this run were removed again" % len(removed)
            if kept:
                detail += (
                    "; %d file(s) that already existed were left as rewritten "
                    "(their previous content cannot be restored)" % len(kept)
                )
            outcomes = [
                WriteOutcome(outcome.path, outcome.action, False, 0)
                if outcome.written and outcome.path in removed
                else outcome
                for outcome in outcomes
            ]
            copied_resources = [
                pair for pair in copied_resources if pair[1] not in removed
            ]
            # A directory the rollback removed is no longer a directory this
            # run created-for-you.
            created = tuple(
                directory for directory in created if os.path.isdir(directory)
            )
        return OutputResult(outcomes, copied_resources, created, errors=(detail,))
    return OutputResult(outcomes, copied_resources, created)
