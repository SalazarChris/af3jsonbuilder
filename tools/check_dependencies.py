"""Check the local AF3 JSON Builder environment.

The project metadata in ``pyproject.toml`` is the source of truth. The Windows
setup script installs ``.[gui,templates]`` into ``.venv``; this checker verifies
those runtime features, records optional Gemmi fallback behavior separately,
and is read-only unless ``--ensure-venv`` is requested. In that mode it selects
a compatible interpreter and may build a replacement ``.venv``, always keeping
the previous environment as a timestamped backup until the replacement passes
the QtWidgets and application import checks.

This is the local JSON builder only. AF3 inference, model weights, GPU drivers
and the university Linux server are deliberately outside this environment.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

__all__ = [
    "Check",
    "Report",
    "check_dependency",
    "check_python_version",
    "choose_interpreter",
    "discover_interpreters",
    "ensure_venv",
    "interpreter_distribution",
    "main",
    "parse_project_metadata",
    "project_root",
    "run_diagnostics",
]

# These are optional features of the core application, not duplicated package
# requirements: the distribution names and version constraints always come
# from the corresponding pyproject optional-dependency groups.
_INSTALL_EXTRAS = ("gui", "templates")

# A fully resolved six-residue (ACDEFG) one-chain protein template. The checker
# used to read this structure from manual_test_data/, which is development
# material and is not part of the application; it is generated here instead, so
# the check is self-contained and needs no committed fixture.
_TEMPLATE_RESIDUES = (
    ("ALA", 0.000, 0.000, 0.000),
    ("CYS", 3.800, 0.100, 0.200),
    ("ASP", 7.400, -0.300, 0.900),
    ("GLU", 10.900, 0.400, 1.700),
    ("PHE", 14.600, 0.000, 2.300),
    ("GLY", 18.100, -0.500, 3.100),
)


@dataclass(frozen=True)
class Check:
    status: str
    subject: str
    detail: str
    required: bool = True

    @property
    def failed(self) -> bool:
        return self.required and self.status in {"MISSING", "INCOMPATIBLE"}


@dataclass
class Report:
    checks: list

    @property
    def exit_code(self) -> int:
        return 1 if any(check.failed for check in self.checks) else 0

    def render(self) -> str:
        lines = ["AF3 JSON Builder — local dependency check", "=" * 47]
        for check in self.checks:
            lines.append("%-12s %-31s %s" % (check.status, check.subject, check.detail))
        lines.extend(
            [
                "",
                "This checks the local JSON builder only. AF3 inference, model weights,",
                "GPU drivers and the university Linux environment are not installed here.",
                "Result: %s" % ("NOT READY" if self.exit_code else "READY"),
            ]
        )
        return "\n".join(lines)


def project_root(script_path: Optional[Path] = None) -> Path:
    """Return the checkout root from this script's location, not the cwd."""
    path = Path(script_path or __file__).resolve()
    return path.parent.parent if path.name == "check_dependencies.py" else path.resolve()


def _toml_reader():
    try:
        import tomllib
    except ImportError:  # Python 3.9/3.10; pip ships tomli in its own vendor tree.
        try:
            from pip._vendor import tomli as tomllib
        except Exception as error:
            raise RuntimeError(
                "TOML support is unavailable; repair Python/pip, then rerun this check"
            ) from error
    return tomllib


def parse_project_metadata(root: Path) -> dict:
    """Read the project name, Python constraint, core requirements and extras."""
    path = Path(root) / "pyproject.toml"
    with path.open("rb") as handle:
        document = _toml_reader().load(handle)
    project = document.get("project", {})
    return {
        "name": project.get("name", "unknown project"),
        "requires_python": project.get("requires-python", ""),
        "dependencies": tuple(project.get("dependencies", ())),
        "optional_dependencies": {
            name: tuple(requirements)
            for name, requirements in project.get("optional-dependencies", {}).items()
        },
    }


def _requirement_tools():
    try:
        from pip._vendor.packaging.requirements import Requirement
        from pip._vendor.packaging.utils import canonicalize_name
    except Exception:
        try:
            from packaging.requirements import Requirement
            from packaging.utils import canonicalize_name
        except Exception as error:
            raise RuntimeError(
                "pip's requirement parser is unavailable; upgrade pip in this environment"
            ) from error
    return Requirement, canonicalize_name


def check_python_version(requires_python: str, version: Sequence[int]) -> Check:
    """Compare an interpreter tuple against pyproject's PEP 440 constraint."""
    try:
        from pip._vendor.packaging.specifiers import SpecifierSet
        from pip._vendor.packaging.version import Version
    except Exception:
        try:
            from packaging.specifiers import SpecifierSet
            from packaging.version import Version
        except Exception as error:
            return Check("WARNING", "Python version", "cannot parse requires-python: %s" % error)
    rendered = ".".join(str(part) for part in version[:3])
    try:
        compatible = Version(rendered) in SpecifierSet(requires_python)
    except Exception as error:
        return Check("INCOMPATIBLE", "pyproject Python constraint", str(error))
    if compatible:
        return Check("PASS", "Python version", "%s satisfies requires-python %s" % (rendered, requires_python))
    return Check(
        "INCOMPATIBLE",
        "Python version",
        "%s does not satisfy requires-python %s; install a compatible Python and rerun setup_windows.bat"
        % (rendered, requires_python),
    )


def _packages_distributions() -> dict:
    """Map import roots to distributions across Python 3.9+ metadata APIs."""
    mapper = getattr(metadata, "packages_distributions", None)
    if mapper is not None:
        return mapper()
    mapping = {}
    try:
        distributions = metadata.distributions()
    except Exception:
        distributions = ()
    for distribution in distributions:
        name = distribution.metadata.get("Name")
        if not name:
            continue
        top_level = distribution.read_text("top_level.txt") or ""
        for module in top_level.splitlines():
            module = module.strip()
            if module:
                mapping.setdefault(module, []).append(name)
    return mapping


def _is_import_root(name: str) -> bool:
    """A probed import root must be a dotted identifier, never a file path."""
    return bool(name) and all(part.isidentifier() for part in name.split("."))


def _module_names_for_distribution(distribution: str, package_map: dict) -> Tuple[str, ...]:
    """Resolve distribution names to import roots using installed metadata.

    ``packages_distributions()`` also reports record paths such as
    ``PySide6/QtCore`` or ``googleapiclient/discovery_cache``. Those are file
    locations, not importable module names, so they are filtered out before
    anything is passed to ``importlib``.
    """
    Requirement, canonicalize_name = _requirement_tools()
    wanted = canonicalize_name(distribution)
    found = []
    for module, distributions in package_map.items():
        if not _is_import_root(module):
            continue
        if any(canonicalize_name(name) == wanted for name in distributions):
            found.append(module)
    if not found:
        # Most distributions use a normalized import root; packages_distributions
        # supplies the authoritative mapping for exceptions (Pillow/PIL, etc.).
        found.append(re.sub(r"[-.]+", "_", distribution))
    return tuple(dict.fromkeys(found))


def check_dependency(
    requirement_text: str,
    module_names: Sequence[str],
    *,
    get_version: Callable[[str], str],
    import_module: Callable[[str], object],
    required: bool = True,
    fallback_available: bool = False,
) -> Check:
    """Check distribution presence/version and that an import root loads."""
    Requirement, _canonicalize_name = _requirement_tools()
    requirement = Requirement(requirement_text)
    label = requirement.name
    try:
        installed = get_version(label)
    except metadata.PackageNotFoundError:
        if not required and fallback_available:
            return Check("OPTIONAL", label, "not installed; the supported fallback is available", False)
        return Check("MISSING", label, "install the project extras with setup_windows.bat", required)
    except Exception as error:
        return Check("WARNING", label, "distribution version could not be read: %s" % error, required)

    if requirement.specifier and installed not in requirement.specifier:
        detail = "installed %s does not satisfy %s" % (installed, requirement.specifier)
        if not required and fallback_available:
            return Check("OPTIONAL", label, detail + "; fallback is available", False)
        return Check("INCOMPATIBLE", label, detail, required)

    errors = []
    for module_name in module_names:
        try:
            import_module(module_name)
        except Exception as error:
            errors.append("%s: %s" % (module_name, error))
    if errors:
        detail = "distribution %s is installed but its import failed (%s)" % (installed, "; ".join(errors))
        if not required and fallback_available:
            return Check("OPTIONAL", label, detail + "; fallback is available", False)
        return Check("MISSING", label, detail, required)
    return Check("PASS", label, "version %s satisfies %s; import verified" % (installed, requirement_text), required)


def _venv_python(root: Path, name: str = ".venv") -> Path:
    if os.name == "nt":
        return root / name / "Scripts" / "python.exe"
    return root / name / "bin" / "python"


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.realpath(str(left))) == os.path.normcase(os.path.realpath(str(right)))


_PROBE_SCRIPT = (
    "import json, platform, sys\n"
    "print(json.dumps({\n"
    "    'executable': sys.executable,\n"
    "    'version': list(sys.version_info[:3]),\n"
    "    'base_prefix': sys.base_prefix,\n"
    "    'prefix': sys.prefix,\n"
    "    'architecture': platform.architecture()[0],\n"
    "    'implementation': platform.python_implementation(),\n"
    "    'version_string': sys.version,\n"
    "}))\n"
)


def probe_interpreter(python) -> Optional[dict]:
    """Facts about one interpreter, or ``None`` when it cannot run Python."""
    try:
        result = subprocess.run(
            [str(python), "-c", _PROBE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        facts = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    if not isinstance(facts, dict) or "version" not in facts:
        return None
    facts["version"] = tuple(facts["version"])
    return facts


def interpreter_distribution(facts: dict) -> str:
    """Name the distribution that owns an interpreter's base prefix.

    Conda's base prefix carries ``conda-meta`` and its own ``Library/bin``
    copies of the MSVC runtime and Qt libraries. Those DLLs can shadow the
    ones the PySide6 wheel expects, so conda is identified explicitly rather
    than guessed from an import error later.
    """
    base = Path(facts.get("base_prefix") or "")
    version_text = str(facts.get("version_string", "")).lower()
    executable = str(facts.get("executable", "")).replace("\\", "/").lower()
    base_text = str(base).replace("\\", "/").lower()
    if (base / "conda-meta").is_dir() or "anaconda" in version_text or "miniconda" in version_text:
        return "Anaconda/Miniconda"
    if "windowsapps" in executable:
        return "Microsoft Store"
    parts = [part for part in base_text.split("/") if part]
    if "uv" in parts and "python" in parts:
        return "uv-managed CPython"
    if base.name.lower().startswith("python"):
        return "python.org CPython"
    return "CPython"


def _interpreter_problem(facts: dict) -> Optional[str]:
    """Why an interpreter cannot host the application, or ``None``."""
    implementation = facts.get("implementation")
    if implementation != "CPython":
        return "%s is not CPython" % implementation
    if "64" not in str(facts.get("architecture", "")):
        return "%s is not 64-bit" % facts.get("architecture")
    if tuple(facts.get("version", ()))[:2] < (3, 9):
        return "Python %s is older than 3.9" % ".".join(str(part) for part in facts.get("version", ()))
    if interpreter_distribution(facts) == "Microsoft Store":
        return "the Microsoft Store Python alias is not a real interpreter"
    return None


def _candidate_rank(facts: dict) -> int:
    """Lower is better; conda is usable only when nothing else exists."""
    distribution = interpreter_distribution(facts)
    return {
        "python.org CPython": 0,
        "CPython": 10,
        "uv-managed CPython": 20,
        "Anaconda/Miniconda": 80,
        "Microsoft Store": 90,
    }.get(distribution, 30)


def _py_launcher_paths() -> list:
    """Interpreters registered with the Windows ``py`` launcher."""
    try:
        result = subprocess.run(["py", "-0p"], capture_output=True, text=True, timeout=20)
    except Exception:
        return []
    paths = []
    for line in (result.stdout or "").splitlines():
        match = re.match(r"^\s*-V:\S+\s+(?:\*\s+)?(.+?)\s*$", line)
        if match:
            candidate = match.group(1).strip().strip('"')
            if candidate.lower().endswith("python.exe"):
                paths.append(candidate)
    return paths


def _known_python_installations() -> list:
    """Standard per-user and machine-wide CPython locations."""
    roots = []
    for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        value = os.environ.get(variable)
        if not value:
            continue
        if variable == "LOCALAPPDATA":
            roots.append(Path(value) / "Programs" / "Python")
        else:
            roots.append(Path(value))
    paths = []
    for root in roots:
        if root.is_dir():
            paths.extend(str(item) for item in root.glob("Python3*/python.exe"))
    uv_root = os.environ.get("APPDATA")
    if uv_root:
        uv_python = Path(uv_root) / "uv" / "python"
        if uv_python.is_dir():
            paths.extend(str(item) for item in uv_python.glob("*/python.exe"))
    return paths


def discover_interpreters() -> list:
    """Every distinct Python candidate, with facts and a preference rank."""
    candidates = []
    candidates.extend(_py_launcher_paths())
    for name in ("python", "python3"):
        located = shutil.which(name)
        if located:
            candidates.append(located)
    candidates.extend(_known_python_installations())

    seen = set()
    found = []
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        identity = os.path.normcase(os.path.realpath(str(path)))
        if identity in seen:
            continue
        seen.add(identity)
        facts = probe_interpreter(path)
        if facts is None:
            continue
        # A venv is not a base interpreter: creating a venv from one inherits
        # another project's environment. Only base installations are offered.
        if os.path.normcase(os.path.realpath(str(facts.get("prefix", facts.get("base_prefix", ""))))) != os.path.normcase(
            os.path.realpath(str(facts.get("base_prefix", "")))
        ):
            continue
        facts = dict(facts)
        facts["distribution"] = interpreter_distribution(facts)
        facts["problem"] = _interpreter_problem(facts)
        facts["rank"] = _candidate_rank(facts)
        found.append(facts)
    return found


def choose_interpreter(infos=None) -> Optional[dict]:
    """The most suitable interpreter, preferring python.org over conda."""
    if infos is None:
        infos = discover_interpreters()
    usable = [facts for facts in infos if not facts.get("problem")]
    if not usable:
        return None
    # A conda environment is never selected automatically: its DLL directory
    # can make the official PySide6 wheels unloadable. An explicit override is
    # still honoured by ensure_venv().
    usable = [facts for facts in usable if facts.get("distribution") != "Anaconda/Miniconda"]
    if not usable:
        return None

    def version_rank(facts):
        major, minor = tuple(facts["version"])[:2]
        if (major, minor) in ((3, 11), (3, 12)):
            return 0  # the verified range for the PySide6 wheels
        if (major, minor) in ((3, 9), (3, 10)):
            return 1
        return 2

    usable.sort(key=lambda facts: (
        facts["rank"],
        version_rank(facts),
        tuple(-part for part in facts["version"]),
        facts["executable"],
    ))
    return usable[0]


_QT_PROBE_SCRIPT = """
import json
result = {}
try:
    from PySide6.QtCore import qVersion
    result["QtCore"] = {"ok": True, "detail": qVersion()}
except BaseException as error:
    result["QtCore"] = {"ok": False, "detail": "%s: %s" % (type(error).__name__, error)}
try:
    from PySide6.QtGui import QGuiApplication
    result["QtGui"] = {"ok": True, "detail": "QGuiApplication imported"}
except BaseException as error:
    result["QtGui"] = {"ok": False, "detail": "%s: %s" % (type(error).__name__, error)}
try:
    from PySide6.QtWidgets import QApplication
    result["QtWidgets"] = {"ok": True, "detail": "QApplication imported"}
except BaseException as error:
    result["QtWidgets"] = {"ok": False, "detail": "%s: %s" % (type(error).__name__, error)}
try:
    import configbuilder
    result["application"] = {"ok": True, "detail": configbuilder.__file__}
except BaseException as error:
    result["application"] = {"ok": False, "detail": "%s: %s" % (type(error).__name__, error)}
versions = {}
try:
    import importlib.metadata as metadata
    for name in ("PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
except BaseException:
    pass
result["versions"] = versions
print(json.dumps(result))
"""


def probe_qt(python, root: Path) -> dict:
    """Import the three Qt layers in a child process and report each stage."""
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    try:
        result = subprocess.run(
            [str(python), "-c", _QT_PROBE_SCRIPT],
            cwd=str(root),
            env=environment,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except Exception as error:
        failure = {"ok": False, "detail": "could not run the Qt probe: %s" % error}
        return {"QtCore": failure, "QtGui": failure, "QtWidgets": failure, "application": failure, "versions": {}}
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        failure = {"ok": False, "detail": (result.stderr or result.stdout or "Qt probe produced no result").strip()}
        return {"QtCore": failure, "QtGui": failure, "QtWidgets": failure, "application": failure, "versions": {}}


def qt_failure_detail(stage: str, detail: str, distribution: str) -> str:
    """Explain a Qt import failure without blaming conda for every DLL error."""
    if "DLL load failed" in detail:
        if distribution == "Anaconda/Miniconda":
            return (
                "%s failed to load its native Qt DLLs under an Anaconda/Miniconda base "
                "interpreter (%s). Conda's Library/bin ships its own MSVC/Qt runtime, "
                "which conflicts with the official PySide6 wheels. setup_windows.bat "
                "will now build .venv from a non-conda CPython automatically." % (stage, detail)
            )
        return (
            "%s failed to load its native Qt DLLs (%s). The PySide6 wheel, the 64-bit "
            "CPython runtime and the Microsoft Visual C++ 2015-2022 x64 Redistributable "
            "do not agree; reinstalling the gui extra into a fresh .venv is the "
            "supported repair." % (stage, detail)
        )
    if "specified procedure could not be found" in detail:
        return (
            "%s could not resolve a required Windows procedure (%s). This is a native "
            "runtime mismatch, not a missing Python package; use the 64-bit CPython "
            "and VC++ runtime required by PySide6." % (stage, detail)
        )
    if "ModuleNotFoundError" in detail or "No module named" in detail:
        return "%s is not installed: %s" % (stage, detail)
    return "%s failed: %s" % (stage, detail)


def check_qt_imports(python=None, root: Optional[Path] = None) -> list:
    """QtCore, QtGui and QtWidgets checks for the running environment."""
    executable = Path(python) if python is not None else Path(sys.executable)
    root = Path(root or project_root()).resolve()
    facts = probe_interpreter(executable) or {"base_prefix": sys.base_prefix, "version_string": sys.version, "executable": str(executable)}
    distribution = interpreter_distribution(facts)
    stages = probe_qt(executable, root)
    checks = []
    for stage in ("QtCore", "QtGui", "QtWidgets"):
        outcome = stages.get(stage, {"ok": False, "detail": "probe returned no result"})
        if outcome.get("ok"):
            checks.append(Check("PASS", "%s import" % stage, str(outcome.get("detail", "imported"))))
        else:
            checks.append(Check(
                "INCOMPATIBLE",
                "%s import" % stage,
                qt_failure_detail(stage, str(outcome.get("detail", "failed")), distribution),
            ))
    versions = stages.get("versions") or {}
    present = {name: value for name, value in versions.items() if value}
    if len(present) >= 2:
        minors = {tuple(str(value).split(".")[:2]) for value in present.values()}
        if len(minors) > 1:
            checks.append(Check(
                "INCOMPATIBLE",
                "PySide6 version set",
                "inconsistent versions: %s" % ", ".join("%s %s" % item for item in sorted(present.items())),
            ))
        else:
            checks.append(Check(
                "PASS",
                "PySide6 version set",
                "consistent: %s" % ", ".join("%s %s" % item for item in sorted(present.items())),
            ))
    return checks


def _distribution_check() -> Check:
    facts = {
        "executable": sys.executable,
        "version": tuple(sys.version_info[:3]),
        "base_prefix": sys.base_prefix,
        "version_string": sys.version,
        "architecture": "64bit" if sys.maxsize > 2 ** 32 else "32bit",
        "implementation": sys.implementation.name,
    }
    distribution = interpreter_distribution(facts)
    if distribution == "Anaconda/Miniconda":
        return Check(
            "WARNING",
            "Python distribution",
            "Anaconda/Miniconda base (%s); Qt native imports may fail because conda's "
            "DLL directory shadows the official PySide6 runtime" % sys.base_prefix,
        )
    if distribution == "Microsoft Store":
        return Check("INCOMPATIBLE", "Python distribution", "the Microsoft Store Python alias is not a real interpreter")
    return Check("PASS", "Python distribution", distribution)


def _unique_backup(root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = root / (".venv.backup-" + stamp)
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = root / (".venv.backup-%s-%d" % (stamp, suffix))
    return candidate


def _install_extras(venv_python: Path, root: Path) -> bool:
    """Upgrade pip, then install the editable application with its extras."""
    try:
        upgrade = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], cwd=str(root)
        )
        if upgrade.returncode:
            return False
        install = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-e", ".[gui,templates]"], cwd=str(root)
        )
    except Exception as error:
        print("ERROR: could not run pip: %s" % error)
        return False
    return install.returncode == 0


def _environment_probe(venv_python: Path, root: Path) -> dict:
    facts = probe_interpreter(venv_python)
    if facts is None:
        return {"runs": False, "QtWidgets": {"ok": False, "detail": "interpreter cannot run"}}
    stages = probe_qt(venv_python, root)
    stages["runs"] = True
    stages["facts"] = facts
    stages["distribution"] = interpreter_distribution(facts)
    return stages


def ensure_venv(root, interpreter=None, *, discover=discover_interpreters, probe=_environment_probe, install=_install_extras, runner=subprocess.run) -> int:
    """Create or repair ``.venv`` without ever discarding the previous one."""
    root = Path(root).resolve()
    venv_dir = root / ".venv"
    venv_python = _venv_python(root)
    backup = None

    if venv_dir.exists():
        health = probe(venv_python, root) if venv_python.is_file() else {"runs": False}
        if health.get("runs") and health.get("QtWidgets", {}).get("ok") and health.get("application", {}).get("ok"):
            print("PASS existing .venv passes the QtWidgets and application import checks")
            return 0
        print("INCOMPATIBLE existing .venv cannot load the GUI; it will be preserved as a backup")
        backup = _unique_backup(root)
        try:
            os.replace(str(venv_dir), str(backup))
            print("Backup: %s" % backup)
        except OSError as error:
            print("ERROR: could not preserve the existing .venv (%s); nothing was changed" % error)
            return 1

    selected = None
    if interpreter is not None:
        facts = probe_interpreter(interpreter)
        if facts is None or _interpreter_problem(facts):
            print("ERROR: the requested interpreter is not usable: %s" % interpreter)
            if facts:
                print("       %s" % (_interpreter_problem(facts) or interpreter_distribution(facts)))
        else:
            facts = dict(facts)
            facts["distribution"] = interpreter_distribution(facts)
            selected = facts
            if facts["distribution"] == "Anaconda/Miniconda":
                print("WARNING: the requested interpreter is Anaconda/Miniconda; Qt may still fail")
    else:
        selected = choose_interpreter(discover())

    if selected is None:
        print("ERROR: no compatible 64-bit CPython 3.9+ interpreter was found")
        if backup is not None:
            os.replace(str(backup), str(venv_dir))
            print("The previous .venv was restored unchanged")
        return 2

    print("Selected interpreter: %s (%s, Python %s, %s)" % (
        selected["executable"], selected["distribution"],
        ".".join(str(part) for part in selected["version"]), selected.get("architecture", "unknown"),
    ))
    try:
        created = runner([selected["executable"], "-m", "venv", str(venv_dir)])
    except Exception as error:
        print("ERROR: could not create .venv: %s" % error)
        created = None
    if created is None or getattr(created, "returncode", 1) != 0:
        shutil.rmtree(str(venv_dir), ignore_errors=True)
        if backup is not None:
            os.replace(str(backup), str(venv_dir))
            print("The previous .venv was restored unchanged")
        return 1

    if not install(venv_python, root):
        print("ERROR: installing .[gui,templates] failed")
        shutil.rmtree(str(venv_dir), ignore_errors=True)
        if backup is not None:
            os.replace(str(backup), str(venv_dir))
            print("The previous .venv was restored unchanged")
        return 1

    health = probe(venv_python, root)
    if not (health.get("runs") and health.get("QtWidgets", {}).get("ok") and health.get("application", {}).get("ok")):
        detail = health.get("QtWidgets", {}).get("detail", "GUI verification failed")
        print("ERROR: the new environment still cannot load the GUI: %s" % detail)
        shutil.rmtree(str(venv_dir), ignore_errors=True)
        if backup is not None:
            os.replace(str(backup), str(venv_dir))
            print("The previous .venv was restored unchanged")
        return 1

    print("PASS new .venv passes QtCore, QtGui, QtWidgets and application import checks")
    if backup is not None:
        print("Previous environment retained at: %s" % backup)
    return 0


def _pip_check() -> Check:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as error:
        return Check("WARNING", "pip check", "could not run: %s" % error)
    output = (result.stdout or result.stderr).strip()
    if result.returncode == 0:
        return Check("PASS", "pip check", output or "no broken requirements")
    return Check("INCOMPATIBLE", "pip check", output or "pip reported dependency conflicts")


def _run_cli_smoke(root: Path) -> Check:
    launcher = root / "af3builder.py"
    try:
        result = subprocess.run(
            [sys.executable, str(launcher)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as error:
        return Check("INCOMPATIBLE", "CLI startup", "could not start the actual launcher: %s" % error)
    if result.returncode == 0 and "JSON CONFIGURATION BUILDER" in result.stdout:
        return Check("PASS", "CLI startup", "af3builder.py opened the console menu and exited cleanly on EOF")
    detail = (result.stderr or result.stdout).strip().splitlines()
    return Check("INCOMPATIBLE", "CLI startup", detail[-1] if detail else "launcher did not start cleanly")


def _template_fixture_text() -> str:
    """A minimal mmCIF template that both parser tiers accept."""
    lines = [
        "data_AF3_TEMPLATE_A",
        "#",
        "_entry.id AF3_TEMPLATE_A",
        "#",
        "_struct.title 'AF3 builder fixture A: six-residue protein template, fully resolved'",
        "#",
        "_entity_poly.entity_id 1",
        "_entity_poly.type 'polypeptide(L)'",
        "_entity_poly.pdbx_strand_id A",
        "_entity_poly.pdbx_seq_one_letter_code ACDEFG",
        "#",
        "loop_",
        "_entity_poly_seq.entity_id",
        "_entity_poly_seq.num",
        "_entity_poly_seq.mon_id",
    ]
    for index, residue in enumerate(_TEMPLATE_RESIDUES, start=1):
        lines.append("1 %d %s" % (index, residue[0]))
    lines.extend(
        [
            "#",
            "loop_",
            "_struct_asym.id",
            "_struct_asym.entity_id",
            "A 1",
            "#",
            "loop_",
            "_atom_site.group_PDB",
            "_atom_site.id",
            "_atom_site.type_symbol",
            "_atom_site.label_atom_id",
            "_atom_site.label_asym_id",
            "_atom_site.label_comp_id",
            "_atom_site.label_seq_id",
            "_atom_site.auth_asym_id",
            "_atom_site.auth_seq_id",
            "_atom_site.Cartn_x",
            "_atom_site.Cartn_y",
            "_atom_site.Cartn_z",
            "_atom_site.occupancy",
            "_atom_site.B_iso_or_equiv",
        ]
    )
    for index, residue in enumerate(_TEMPLATE_RESIDUES, start=1):
        lines.append(
            "ATOM %d C CA A %s %d A %d %.3f %.3f %.3f 1.00 20.00"
            % (index, residue[0], index, index, residue[1], residue[2], residue[3])
        )
    lines.append("#")
    return "\n".join(lines) + "\n"


def _run_gui_smoke(root: Path) -> Check:
    with tempfile.TemporaryDirectory(prefix="af3-template-") as directory:
        fixture = Path(directory) / "template_fully_resolved.cif"
        fixture.write_text(_template_fixture_text(), encoding="utf-8")
        return _run_gui_smoke_with_fixture(root, fixture)


def _run_gui_smoke_with_fixture(root: Path, fixture: Path) -> Check:
    script = """\nfrom PySide6.QtWidgets import QApplication
from configbuilder.app.reference_validation import file_issue
from configbuilder.ui.render.qt.state import GuiState
from configbuilder.ui.render.qt.windows import MainWindow
from configbuilder.ui.services import build_services
app = QApplication.instance() or QApplication([])
services = build_services()
assert services.projects is not None and services.configuration is not None
assert services.generation is not None and services.validation is not None
window = MainWindow(GuiState())
window.close()
fixture = %r
assert file_issue(fixture) is None, file_issue(fixture)
app.quit()
print('Qt window, application services and template validation initialized')
""" % str(fixture)
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"

    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(root),
            env=environment,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except Exception as error:
        return Check("INCOMPATIBLE", "GUI/service smoke", "could not start smoke test: %s" % error)
    if result.returncode == 0:
        return Check("PASS", "GUI/service smoke", result.stdout.strip() or "Qt and services initialized")
    detail = (result.stderr or result.stdout).strip().splitlines()
    message = detail[-1] if detail else "GUI smoke test failed"
    if "DLL load failed" in (result.stderr or ""):
        facts = probe_interpreter(Path(sys.executable)) or {
            "base_prefix": sys.base_prefix, "version_string": sys.version, "executable": sys.executable,
        }
        message = qt_failure_detail("GUI startup", message, interpreter_distribution(facts))
        message += " Run setup_windows.bat again; it preserves the old .venv and rebuilds it automatically."
    return Check("INCOMPATIBLE", "GUI/service smoke", message)


def run_diagnostics(
    root: Optional[Path] = None,
    *,
    include_smokes: bool = True,
    environment_name: str = ".venv",
) -> Report:
    """Collect dependency, venv, pip and safe application smoke results."""
    root = Path(root or project_root()).resolve()
    checks = []
    try:
        project = parse_project_metadata(root)
    except Exception as error:
        return Report([Check("INCOMPATIBLE", "pyproject.toml", str(error))])

    checks.append(check_python_version(project["requires_python"], sys.version_info))
    checks.append(_distribution_check())
    expected_python = _venv_python(root, environment_name)
    environment_label = "Project %s" % environment_name
    if not expected_python.is_file():
        checks.append(Check(
            "MISSING", environment_label, "not found; double-click setup_windows.bat first"
        ))
    else:
        try:
            probe = subprocess.run(
                [str(expected_python), "-c", "import sys; print(sys.prefix); print(sys.base_prefix)"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as error:
            probe = None
            checks.append(Check("INCOMPATIBLE", ".venv interpreter", "cannot execute: %s" % error))
        if probe is not None:
            if probe.returncode:
                checks.append(Check("INCOMPATIBLE", ".venv interpreter", (probe.stderr or "failed").strip()))
            else:
                checks.append(Check("PASS", ".venv interpreter", "project virtual environment executes Python"))
        if _same_path(Path(sys.executable), expected_python):
            checks.append(Check("PASS", "Active interpreter", "running from %s" % environment_name))
        else:
            checks.append(Check(
                "INCOMPATIBLE", "Active interpreter",
                "checker is using %s, not %s; launch check_dependencies.bat" % (sys.executable, expected_python),
            ))

    try:
        Requirement, _canonicalize_name = _requirement_tools()
        package_map = _packages_distributions()
        for item in project["dependencies"]:
            requirement = Requirement(item)
            modules = _module_names_for_distribution(requirement.name, package_map)
            checks.append(check_dependency(
                item,
                modules,
                get_version=metadata.version,
                import_module=importlib.import_module,
            ))
        for extra in _INSTALL_EXTRAS:
            is_optional = extra == "templates"
            for item in project["optional_dependencies"].get(extra, ()):
                if is_optional and _requirement_name(item) == "gemmi":
                    continue  # checked once below, together with its fallback
                requirement = Requirement(item)
                modules = _module_names_for_distribution(requirement.name, package_map)
                checks.append(check_dependency(
                    item,
                    modules,
                    get_version=metadata.version,
                    import_module=importlib.import_module,
                    required=not is_optional,
                    fallback_available=False,
                ))
        if not project["dependencies"]:
            checks.append(Check("PASS", "Core runtime", "pyproject declares no third-party core dependencies"))
    except Exception as error:
        checks.append(Check("WARNING", "Dependency metadata", "could not verify requirements: %s" % error))

    if "templates" not in project["optional_dependencies"]:
        checks.append(Check("WARNING", "Template extra", "pyproject has no templates extra; fallback is still checked", False))
    else:
        gemmi_reqs = [item for item in project["optional_dependencies"]["templates"] if _requirement_name(item) == "gemmi"]
        if gemmi_reqs:
            fallback_ok = _template_fallback_available()
            try:
                gemmi_check = check_dependency(
                    gemmi_reqs[0], _module_names_for_distribution("gemmi", _packages_distributions()),
                    get_version=metadata.version, import_module=importlib.import_module,
                    required=False, fallback_available=fallback_ok,
                )
            except Exception as error:
                gemmi_check = Check("WARNING", "Gemmi", "dependency check failed: %s" % error, False)
            checks.append(gemmi_check)
            checks.append(Check(
                "PASS" if fallback_ok else "WARNING",
                "Template fallback",
                "bundled mmCIF structural check works" if fallback_ok else "bundled mmCIF fallback could not be verified",
                False,
            ))
        else:
            checks.append(Check("WARNING", "Template extra", "no Gemmi requirement is declared by the templates extra", False))

    checks.append(_pip_check())
    if include_smokes:
        checks.append(_run_cli_smoke(root))
        gui_requirement_present = any(
            _requirement_name(item) == "pyside6"
            for item in project["optional_dependencies"].get("gui", ())
        )
        if gui_requirement_present:
            checks.extend(check_qt_imports(root=root))
            checks.append(_run_gui_smoke(root))
        else:
            checks.append(Check("INCOMPATIBLE", "GUI metadata", "PySide6 is not declared in the gui extra"))
    return Report(checks)


def _requirement_name(requirement_text: str) -> str:
    Requirement, canonicalize_name = _requirement_tools()
    return canonicalize_name(Requirement(requirement_text).name)


def _template_fallback_available() -> bool:
    """Exercise the bundled lexical parser with the optional parser disabled."""
    try:
        from configbuilder.persistence import mmcif
        return mmcif._lexical_problem(_template_fixture_text()) is None
    except Exception:
        return False


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--python-only", action="store_true",
        help="check only the current interpreter's version and distribution",
    )
    parser.add_argument(
        "--choose-python", action="store_true",
        help="print the best compatible interpreter path (used by setup_windows.bat)",
    )
    parser.add_argument(
        "--ensure-venv", action="store_true",
        help="create or repair .venv, preserving any existing environment until the new one passes",
    )
    parser.add_argument(
        "--interpreter", type=Path,
        help="interpreter requested for --ensure-venv",
    )
    parser.add_argument(
        "--venv-only", action="store_true",
        help="check only whether the existing .venv can import the Qt application layer",
    )
    parser.add_argument(
        "--gui", action="store_true",
        help="verify the existing .venv-gui environment used by gui.py",
    )
    arguments = parser.parse_args(argv)
    root = Path(arguments.root).resolve() if arguments.root else project_root()

    if arguments.choose_python:
        for facts in discover_interpreters():
            print(
                "%s\t%s\tPython %s\t%s"
                % (facts["executable"], facts["distribution"],
                   ".".join(str(part) for part in facts["version"]),
                   facts.get("problem") or "usable"),
                file=sys.stderr,
            )
        best = choose_interpreter()
        if best is None:
            return 2
        print(best["executable"])
        return 0

    if arguments.ensure_venv:
        return ensure_venv(root, interpreter=arguments.interpreter)

    if arguments.venv_only:
        venv_python = _venv_python(root)
        if not venv_python.is_file():
            print("MISSING .venv interpreter: %s" % venv_python)
            return 2
        health = _environment_probe(venv_python, root)
        if health.get("runs") and health.get("QtWidgets", {}).get("ok") and health.get("application", {}).get("ok"):
            print("PASS .venv imports QtWidgets and the application")
            return 0
        detail = health.get("QtWidgets", {}).get("detail", "the interpreter did not run")
        print("INCOMPATIBLE .venv: %s" % detail)
        return 1

    try:
        project = parse_project_metadata(root)
    except Exception as error:
        print("INCOMPATIBLE pyproject.toml: %s" % error)
        return 1
    if arguments.python_only:
        checks = [
            check_python_version(project["requires_python"], sys.version_info),
            _distribution_check(),
        ]
        for check in checks:
            print("%s — %s: %s" % (check.status, check.subject, check.detail))
        return 0 if not any(check.failed for check in checks) else 1
    report = run_diagnostics(root, environment_name=".venv-gui" if arguments.gui else ".venv")
    print(report.render())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
