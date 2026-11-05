"""Check the local AF3 JSON Builder environment without installing anything.

The project metadata in ``pyproject.toml`` is the source of truth. The Windows
setup script installs ``.[gui,templates]`` into ``.venv``; this checker verifies
those runtime features, records optional Gemmi fallback behavior separately,
and never installs or changes packages.

This is the local JSON builder only. AF3 inference, model weights, GPU drivers
and the university Linux server are deliberately outside this environment.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

__all__ = [
    "Check",
    "Report",
    "check_dependency",
    "check_python_version",
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
        # Seen with conda-style builds: their base directory ships its own
        # ucrtbase/msvcp140/vcruntime140 DLLs, which shadow the Windows runtime
        # Qt needs. pip and the rest of the environment are unaffected.
        message += (
            " | this Python distribution bundles a C runtime that conflicts with "
            "Qt (Anaconda/Miniconda builds are known to do this). Rebuild .venv "
            "with a python.org build: rename .venv .venv.backup, then run "
            "setup_windows.bat \"C:\\path\\to\\python.exe\""
        )
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
        help="check only the current interpreter against pyproject requires-python (used by setup)",
    )
    parser.add_argument(
        "--gui", action="store_true",
        help="verify the existing .venv-gui environment used by gui.py",
    )
    arguments = parser.parse_args(argv)
    root = Path(arguments.root).resolve() if arguments.root else project_root()
    try:
        project = parse_project_metadata(root)
    except Exception as error:
        print("INCOMPATIBLE pyproject.toml: %s" % error)
        return 1
    if arguments.python_only:
        check = check_python_version(project["requires_python"], sys.version_info)
        print("%s — %s: %s" % (check.status, check.subject, check.detail))
        return 0 if not check.failed else 1
    report = run_diagnostics(root, environment_name=".venv-gui" if arguments.gui else ".venv")
    print(report.render())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
