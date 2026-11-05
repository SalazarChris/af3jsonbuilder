"""Where output goes, and where the user's choices are remembered.

This module is the single answer to "what folder should the save/generate
default be?". Both front ends ask it, so the console and the window cannot
disagree, and nothing here reads the current working directory: the defaults
are the same whether the application was started from Explorer, a shortcut,
a terminal in the application folder, or a terminal in ``C:\\Windows``.

Resolution order for the **output root** (``resolve_root``):

1. ``AF3BUILDER_OUTPUT_ROOT`` — an explicit configuration. A value that
   cannot be created or written is reported as a diagnostic and the next
   source is used; it is never silently accepted *or* silently dropped.
2. a remembered root from the preferences file, when it is still usable;
3. ``<Documents>/AF3Builder``;
4. ``%LOCALAPPDATA%\\AF3Builder`` when Documents is unavailable.

Two subdirectories keep the operations apart, because they are different
things: ``generated_configurations`` for batch output (one configuration per
input entry plus ``manifest.json`` and asset copies) and ``saved_jobs`` for a
single saved job and its ``assets/``. Each also remembers its own last-used
directory, so a user who exports to a network share is not dragged back to
Documents on the next save.

Preferences live in ``%APPDATA%\\AF3Builder\\preferences.json`` — user-writable,
outside the installation folder, and safe to lose: every read tolerates a
missing, malformed or partially valid file and falls back to the defaults.
Nothing in this module raises for a user-caused problem, and nothing imports
the UI layer (plan §5.3: ``app`` never imports ``ui``).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

__all__ = [
    "ENV_OUTPUT_ROOT",
    "GENERATED_DIRECTORY_NAME",
    "SAVED_JOBS_DIRECTORY_NAME",
    "PREFERENCE_OUTPUT_ROOT",
    "PREFERENCE_LAST_SAVE_DIRECTORY",
    "PREFERENCE_LAST_BATCH_DIRECTORY",
    "OutputRoot",
    "Preferences",
    "OutputPaths",
    "preferences_path",
]

#: The environment variable a user (or a deployment script) can set to pin the
#: output tree somewhere else entirely.
ENV_OUTPUT_ROOT = "AF3BUILDER_OUTPUT_ROOT"

GENERATED_DIRECTORY_NAME = "generated_configurations"
SAVED_JOBS_DIRECTORY_NAME = "saved_jobs"

PREFERENCE_OUTPUT_ROOT = "output_root"
PREFERENCE_LAST_SAVE_DIRECTORY = "last_save_directory"
PREFERENCE_LAST_BATCH_DIRECTORY = "last_batch_directory"

_APPLICATION_DIRECTORY_NAME = "AF3Builder"
_PREFERENCES_FILE_NAME = "preferences.json"

#: ``os.open`` is read once so a test can prove how many times a refused
#: create is attempted without patching the ``os`` module for the whole run.
_os_open = os.open

#: How many names a write tries before giving up. Only a name collision — a
#: create that fails because *that* file exists — consumes another attempt. A
#: permission failure ends the write immediately: ``tempfile.mkstemp`` treats
#: a denied create on Windows as a collision and can search 10,000 names,
#: which froze the window after a save that had already written its JSON.
_WRITE_ATTEMPTS = 3


def _atomic_write(path: Path, payload: str) -> bool:
    """Replace ``path`` with ``payload``, atomically and in bounded time.

    The temporary name is generated here rather than by ``tempfile``: one
    refused create must end the attempt, not start a long search. ``os.replace``
    is atomic within a volume, so a reader never sees a half-written file, and
    a failure leaves the previous preferences untouched. Returns ``False`` for
    every filesystem refusal; remembering a folder is never a condition of
    saving a job.
    """
    for _attempt in range(_WRITE_ATTEMPTS):
        temporary = path.parent / (".preferences-%s.json" % uuid.uuid4().hex)
        try:
            handle = _os_open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError:
            continue
        except OSError:
            return False
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
            os.replace(temporary, path)
            return True
        except OSError:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            return False
    return False


def preferences_path(env=None, home=None) -> Path:
    """The preferences file, outside the application folder.

    ``%APPDATA%`` is the roaming per-user directory on Windows; elsewhere
    (and on a Windows box where ``APPDATA`` is unset) ``~/.config`` is the
    conventional equivalent. Both are writable by the user, which the
    installation folder may not be.
    """
    environment = os.environ if env is None else env
    roaming = environment.get("APPDATA")
    if roaming:
        base = Path(roaming)
    else:
        base = Path(home) if home is not None else Path.home()
        base = base / ".config"
    return base / _APPLICATION_DIRECTORY_NAME / _PREFERENCES_FILE_NAME


class Preferences:
    """A tiny JSON store for the few choices worth remembering.

    Deliberately dumb: no schema version, no locks, no merge machinery. A
    read returns a ``dict`` (empty when the file is missing or unusable), and
    a write merges the given keys into what is already there, so one
    preference changing cannot erase another. A write that cannot happen
    (read-only profile, disk full) returns ``False`` and changes nothing —
    remembering a folder is a convenience, never a condition of saving a job.
    """

    __slots__ = ("_path",)

    def __init__(self, path=None, env=None, home=None) -> None:
        self._path = Path(path) if path is not None else preferences_path(env, home)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> dict:
        """The stored values, or ``{}`` when there is nothing usable."""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return {}
        try:
            loaded = json.loads(raw)
        except (ValueError, TypeError):
            # A corrupt file is not a reason to fail a save; the defaults are
            # perfectly usable. The next successful write replaces it.
            return {}
        if not isinstance(loaded, dict):
            return {}
        return loaded

    def get(self, key: str, default=None):
        """One stored string value (``None`` when absent or not a string)."""
        value = self.read().get(key)
        return value if isinstance(value, str) and value.strip() else default

    def update(self, **values) -> bool:
        """Merge ``values`` into the file; True when it was written.

        Unchanged values are not rewritten: an existing preferences file is
        left alone when the user picks the same folder again, which keeps the
        file's timestamp meaningful and avoids pointless disk writes.
        """
        current = self.read()
        changed = {key: value for key, value in values.items() if current.get(key) != value}
        if not changed:
            return True
        merged = dict(current)
        merged.update(changed)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(merged, indent=2, sort_keys=True) + "\n"
        except (OSError, ValueError):
            return False
        return _atomic_write(self._path, payload)


class OutputRoot:
    """The resolved root, why it was chosen, and anything worth saying.

    ``diagnostics`` holds sentences for the user: an unusable
    ``AF3BUILDER_OUTPUT_ROOT``, or Documents being unavailable. A front end
    shows them and carries on with the fallback; an empty tuple means the
    default was used exactly as documented.
    """

    __slots__ = ("path", "source", "diagnostics", "usable")

    def __init__(self, path, source: str, diagnostics=(), usable: bool = True) -> None:
        self.path = Path(path)
        self.source = source
        self.diagnostics = tuple(diagnostics)
        #: ``False`` only when no candidate on this machine could be created or
        #: written. The path is still returned so a front end can name what it
        #: tried, but nothing should be written there without the user choosing
        #: a folder.
        self.usable = usable

    def __repr__(self) -> str:
        return "OutputRoot(path=%r, source=%r)" % (str(self.path), self.source)


def _environment(env):
    return os.environ if env is None else env


def _directory_is_usable(path: Path) -> bool:
    """True when ``path`` is (or can become) a writable directory.

    Creates the directory when it is missing: an output tree the user has
    never touched is the normal first run, not an error. A path that exists
    as a *file*, or whose creation fails (permissions, read-only media), is
    not usable and the caller moves on to the next source.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError):
        return False
    return path.is_dir() and os.access(str(path), os.W_OK)


class OutputPaths:
    """The resolved output tree plus the two remembered last-used folders.

    Construct one per front end (or per test) and pass it around: two
    instances with the same preferences file agree, and nothing is cached
    across calls, so a folder the user deletes is noticed the next time.
    """

    __slots__ = ("_preferences", "_env", "_home", "_local_appdata")

    def __init__(self, preferences=None, env=None, home=None, local_appdata=None) -> None:
        self._env = _environment(env)
        self._preferences = Preferences(env=self._env, home=home) if preferences is None else preferences
        self._home = Path(home) if home is not None else Path.home()
        self._local_appdata = (
            Path(local_appdata)
            if local_appdata is not None
            else Path(self._env.get("LOCALAPPDATA") or (self._home / ".local" / "share"))
        )

    # -- resolution --------------------------------------------------------

    def _documents_root(self) -> Path:
        return self._home / "Documents" / _APPLICATION_DIRECTORY_NAME

    def _local_appdata_root(self) -> Path:
        return self._local_appdata / _APPLICATION_DIRECTORY_NAME

    def _as_path(self, text: str) -> Path:
        """A stored path, never resolved against the working directory.

        An absolute path is used as written. ``~`` and a relative value are
        resolved under this instance's home directory, so a hand-edited
        preference or a relative override cannot make the output folder depend
        on where the application was launched from.
        """
        raw = str(text).strip()
        if raw == "~" or raw.startswith(("~/", "~\\")):
            raw = raw[1:].lstrip("/\\")
            return self._home / raw if raw else self._home
        candidate = Path(raw)
        return candidate if candidate.is_absolute() else self._home / candidate

    def resolve_root(self) -> OutputRoot:
        """The output root, with the reason it was chosen and any diagnostics."""
        diagnostics = []

        configured = (self._env.get(ENV_OUTPUT_ROOT) or "").strip()
        if configured:
            candidate = self._as_path(configured)
            if _directory_is_usable(candidate):
                return OutputRoot(candidate, ENV_OUTPUT_ROOT)
            diagnostics.append(
                "The folder named by %s could not be created or written: %s. "
                "Using the standard output folder instead; fix or unset the "
                "variable to remove this message." % (ENV_OUTPUT_ROOT, candidate)
            )

        remembered = self._preferences.get(PREFERENCE_OUTPUT_ROOT)
        if remembered:
            candidate = self._as_path(remembered)
            if _directory_is_usable(candidate):
                return OutputRoot(candidate, "preferences", diagnostics)

        documents = self._documents_root()
        if _directory_is_usable(documents):
            return OutputRoot(documents, "documents", diagnostics)

        fallback = self._local_appdata_root()
        diagnostics.append(
            "The Documents folder could not be used for output (%s), so the "
            "application folder under LOCALAPPDATA is used instead: %s"
            % (documents, fallback)
        )
        if _directory_is_usable(fallback):
            return OutputRoot(fallback, "localappdata", diagnostics)
        # Nothing on this machine is writable. The path is returned so a front
        # end can name what it tried, but it is marked unusable: a caller must
        # ask the user for a folder instead of offering a write that will fail.
        diagnostics.append(
            "No writable output folder could be created. Tried %s and %s; "
            "choose another folder for output." % (documents, fallback)
        )
        return OutputRoot(fallback, "unavailable", diagnostics, usable=False)

    def root(self) -> Path:
        """Just the resolved root path."""
        return self.resolve_root().path

    def generated_configurations(self) -> Path:
        """Where batch output goes (created on demand)."""
        return self.root() / GENERATED_DIRECTORY_NAME

    def saved_jobs(self) -> Path:
        """Where a single saved job goes (created on demand)."""
        return self.root() / SAVED_JOBS_DIRECTORY_NAME

    # -- per-operation defaults -------------------------------------------

    def _usable_remembered(self, key: str):
        remembered = self._preferences.get(key)
        if not remembered:
            return None
        candidate = self._as_path(remembered)
        # A remembered folder is not created here: if the user removed it, the
        # documented default is the better answer than resurrecting it.
        if candidate.is_dir() and os.access(str(candidate), os.W_OK):
            return candidate
        return None

    def save_directory(self) -> Path:
        """The folder the save dialog should offer.

        The remembered save folder first, then ``saved_jobs`` under the
        resolved root. Created when missing, because the next click writes
        into it.
        """
        remembered = self._usable_remembered(PREFERENCE_LAST_SAVE_DIRECTORY)
        if remembered is not None:
            return remembered
        directory = self.saved_jobs()
        _directory_is_usable(directory)
        return directory

    def batch_directory(self) -> Path:
        """The folder the batch/generate destination should offer."""
        remembered = self._usable_remembered(PREFERENCE_LAST_BATCH_DIRECTORY)
        if remembered is not None:
            return remembered
        directory = self.generated_configurations()
        _directory_is_usable(directory)
        return directory

    def default_save_path(self, file_name: str) -> str:
        """``<save directory>/<file_name>`` as a displayable path string."""
        return str(self.save_directory() / file_name)

    def default_batch_root(self) -> str:
        """The batch output root as a displayable path string."""
        return str(self.batch_directory())

    # -- remembering -------------------------------------------------------

    def remember_save_directory(self, directory) -> bool:
        """Remember where a job was just written (after it succeeded)."""
        return self._remember_directory(PREFERENCE_LAST_SAVE_DIRECTORY, directory)

    def remember_batch_directory(self, directory) -> bool:
        """Remember where a batch was just written (after it succeeded)."""
        return self._remember_directory(PREFERENCE_LAST_BATCH_DIRECTORY, directory)

    def _remember_directory(self, key: str, directory) -> bool:
        text = str(directory or "").strip()
        if not text:
            return False
        return self._preferences.update(**{key: str(self._as_path(text))})
