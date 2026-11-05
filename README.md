# AF3 JSON Builder

A local desktop and console application for building **AlphaFold 3 input JSON**
files. Create a job, add protein, DNA, RNA, ion, ligand and modification
entries, attach MSAs or structural templates, then save one configuration or
generate one configuration per line of a batch file.

This repository contains the builder only. It does **not** run AlphaFold 3,
download model weights, or need a GPU. The generated JSON files are copied to a
separate AF3 installation.

## Requirements

- Windows 10 or 11 (the launchers and setup scripts are Windows-specific).
- Python 3.9 or newer from [python.org](https://www.python.org/downloads/windows/).
  Python 3.10 or newer is recommended for the desktop window.
- An internet connection for the first installation (PySide6 and gemmi are
  downloaded from PyPI).

The core builder uses only the Python standard library. PySide6 is the optional
desktop front end; gemmi strengthens structural-template checking.

## Install on Windows

1. Download or clone this repository into a folder under your user profile, for
   example `C:\Users\<you>\AF3Builder`. Do not use `C:\Program Files`: setup
   creates a `.venv` inside the folder and a normal user cannot write there.
2. Double-click **`setup_windows.bat`**. It locates Python, creates `.venv`,
   installs the project with the `gui` and `templates` extras, and runs the
   dependency check. Read the final lines of the window.
3. To re-check the environment at any time, double-click
   **`check_dependencies.bat`**. It is read-only and reports PASS, MISSING,
   INCOMPATIBLE or OPTIONAL for each requirement.

If Windows blocks the scripts, right-click the file, choose **Properties**, and
clear the **Unblock** checkbox before running it.

### Manual installation (any platform)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[gui,templates]"
```

`pip install .` alone installs the console application without PySide6.

## Launch

| Command | What it opens |
| --- | --- |
| `run_gui.cmd` (double-click) | The desktop window |
| `run_console.cmd` (double-click) | The text menu |
| `python gui.py` | The desktop window from an activated environment |
| `python af3builder.py` | The text menu from an activated environment |
| `python -m configbuilder` | The text menu (equivalent) |
| `configbuilder` | The installed console entry point |
| `af3-json-builder` | The installed desktop entry point |

The launchers find the application folder from their own location, so shortcuts
work from the desktop or Start menu. A console window stays open behind the GUI
because startup errors are printed there.

## Create and save an AF3 JSON file

1. Start the GUI and choose **New Job**.
2. Give the job a name, then add entities on the **Entities** page: proteins,
   DNA, RNA, ions or ligands. Sequence, MSA and template settings are edited per
   entity; PTMs and D-amino-acid forms are set from the protein's
   **Modifications / PTMs** action.
3. Use **Preview** to review the generated AF3 document and the validation
   findings. Errors block generation; warnings do not.
4. Choose **Save JSON…** and pick a destination. The builder writes the JSON
   plus an `assets\` folder when the job references external files.

To produce many configurations at once, open the batch input file from the
window. The builder reads one entry per line and writes one independent
configuration per entry, each in its own folder with its own `assets\`, plus a
`manifest.json` run report. A batch entry can add a new entity or replace one
entity the current job already holds; the open job itself is not modified.

## Where output goes

By default everything is written outside the application folder:

```text
%USERPROFILE%\Documents\AF3Builder\
    saved_jobs\                  one saved job JSON and its assets
    generated_configurations\    one folder per generated configuration
```

The output root is resolved in this order:

1. `AF3BUILDER_OUTPUT_ROOT` environment variable, when set and writable;
2. the last output folder you chose, remembered in
   `%APPDATA%\AF3Builder\preferences.json`;
3. `Documents\AF3Builder`;
4. `%LOCALAPPDATA%\AF3Builder` when Documents is unavailable.

You can pick a different destination in the save or generate dialog once; the
application remembers it. A relative `AF3BUILDER_OUTPUT_ROOT` is resolved
against the current working directory.

## Use the generated files with AlphaFold 3

Copy each configuration **together with its `assets\` folder**, preserving the
layout:

```text
my-job__entry-1\
    my-job__entry-1.json
    assets\               MSAs, templates, custom CCD files
```

References inside the JSON are relative to the JSON file, so the folder can be
copied on its own. Do not copy a JSON that still points outside its folder
unless you copy those files with the same relative layout. `manifest.json` is a
builder-side report; AF3 does not read it.

Run the copied JSON with the AlphaFold 3 installation and model parameters
provided by your AF3 environment. The builder does not submit jobs, run
inference, or validate an installation's CCD snapshot.

## Known limitations

- AlphaFold 3 itself, its weights, GPU drivers and the Linux runtime are not
  included and are not installed by this project.
- The desktop window requires PySide6, which has no wheel for every Python
  version on every platform. Python 3.10 or newer from python.org is the tested
  combination.
- D-amino-acid and PTM codes come from the CCD snapshot of the target AF3
  installation. If that snapshot lacks a component, AF3 will reject the input;
  the builder does not fabricate custom CCD definitions.
- Moving the application folder invalidates the editable install's recorded
  path. Run `setup_windows.bat` again from the new location.

## License

MIT. See [LICENSE](LICENSE).
