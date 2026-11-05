@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto :fail_root
set "ROOT=%CD%"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

rem Optional interpreter override, for machines whose default Python cannot run
rem the GUI (see the Qt DLL note below):
rem   setup_windows.bat "C:\path\to\python.exe"
rem   or:  set PYTHON=C:\path\to\python.exe   before running this script
set "PY_EXE="
if not "%~1"=="" if exist "%~1" set "PY_EXE=%~1"
if not defined PY_EXE if defined PYTHON if exist "%PYTHON%" set "PY_EXE=%PYTHON%"

echo ============================================================
echo AF3 JSON Builder - local Windows setup
echo ============================================================
echo Project: %ROOT%
echo This installs the local JSON builder only. It does not install AF3
echo inference, model weights, GPU drivers, or university server software.
echo.
if defined PY_EXE echo Interpreter override in use: %PY_EXE%

if defined PY_EXE if exist "%VENV_PY%" goto :override_with_existing_venv
if exist "%VENV_PY%" goto :reuse_venv
if exist "%ROOT%\.venv" goto :broken_venv

if defined PY_EXE goto :create_with_exe
where py >nul 2>nul
if not errorlevel 1 goto :create_with_py
where python >nul 2>nul
if errorlevel 1 goto :no_python
python tools\check_dependencies.py --python-only --root "%ROOT%"
if errorlevel 1 goto :python_incompatible
python -m venv .venv
if errorlevel 1 goto :venv_failed
goto :install

:create_with_py
py -3 tools\check_dependencies.py --python-only --root "%ROOT%"
if errorlevel 1 goto :python_incompatible
py -3 -m venv .venv
if errorlevel 1 goto :venv_failed
goto :install

:create_with_exe
"%PY_EXE%" tools\check_dependencies.py --python-only --root "%ROOT%"
if errorlevel 1 goto :python_incompatible
"%PY_EXE%" -m venv .venv
if errorlevel 1 goto :venv_failed
goto :install

:override_with_existing_venv
echo NOTE: .venv already exists, so the interpreter override was not used.
echo The existing environment is left exactly as it is. If it was built with an
echo interpreter that cannot load PySide6, rename .venv to .venv.backup yourself
echo and then rerun this script with the override.
goto :reuse_venv

:reuse_venv
echo Found existing .venv. Checking it without deleting or recreating it...
"%VENV_PY%" -c "import sys; print(sys.version); print(sys.executable)"
if errorlevel 1 goto :broken_venv
"%VENV_PY%" tools\check_dependencies.py --python-only --root "%ROOT%"
if errorlevel 1 goto :python_incompatible
goto :install

:install
echo.
echo Upgrading pip in the project-local environment...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :install_failed
echo.
echo Installing the project plus its declared GUI and template extras...
"%VENV_PY%" -m pip install -e ".[gui,templates]"
if errorlevel 1 goto :install_failed
echo.
echo Running the read-only dependency and application checks...
"%VENV_PY%" tools\check_dependencies.py --root "%ROOT%"
if errorlevel 1 goto :diagnostic_failed
echo.
echo SETUP SUCCEEDED. Use check_dependencies.bat to check this environment later.
echo The existing gui.py launcher will prefer .venv and retains .venv-gui compatibility.
goto :finish

:no_python
echo ERROR: Python 3.9 or newer was not found on PATH, and the Windows py launcher is absent.
echo Install a supported Python from https://www.python.org/downloads/windows/
echo During installation, enable the Python Launcher and/or Add Python to PATH.
goto :failed

:python_incompatible
echo ERROR: The selected Python does not satisfy pyproject.toml requires-python.
echo Install a compatible Python 3 release, then double-click setup_windows.bat again.
goto :failed

:broken_venv
echo ERROR: An existing .venv is incomplete or cannot execute Python.
echo It was left untouched. If you do not need its contents, rename .venv to .venv.backup
echo yourself, then rerun setup_windows.bat. Do not delete it until you have checked it.
goto :failed

:venv_failed
echo ERROR: Python could not create .venv. Check the message above and available disk space.
goto :failed

:install_failed
echo ERROR: Installation failed. The existing .venv was not deleted or recreated.
echo Review the pip error above, fix network or permissions issues, then rerun setup_windows.bat.
goto :failed

:diagnostic_failed
echo ERROR: Installation finished, but dependency verification failed.
echo Run check_dependencies.bat and follow each MISSING or INCOMPATIBLE instruction.
echo.
echo If the failure is "DLL load failed" while importing PySide6/Qt, this Python
echo distribution bundles a C runtime that conflicts with Qt ^(common with
echo Anaconda/Miniconda builds^). Recover by rebuilding with a python.org build:
echo     rename .venv .venv.backup
echo     setup_windows.bat "C:\path\to\python.exe"
goto :failed

:fail_root
echo ERROR: Could not change to the setup script's project directory: %~dp0
goto :failed

:failed
echo.
echo Setup did not complete successfully.
set "RESULT=1"
goto :pause_end

:finish
set "RESULT=0"
:pause_end
echo.
pause
exit /b %RESULT%
