@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto :fail_root
set "ROOT=%CD%"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

rem Optional interpreter override, for a machine with several Python builds:
rem   setup_windows.bat "C:\path\to\python.exe"
rem   or:  set PYTHON=C:\path\to\python.exe   before running this script
set "PY_EXE="
if not "%~1"=="" if exist "%~1" set "PY_EXE=%~1"
if not defined PY_EXE if defined PYTHON if exist "%PYTHON%" set "PY_EXE=%PYTHON%"

rem The checker itself may run on any Python 3.9+; the environment it creates
rem is always built from a separately selected, compatible interpreter.
set "TOOL_PY="
where py >nul 2>nul
if not errorlevel 1 set "TOOL_PY=py -3"
if not defined TOOL_PY (
    where python >nul 2>nul
    if not errorlevel 1 set "TOOL_PY=python"
)
if not defined TOOL_PY goto :no_python_launcher

echo ============================================================
echo AF3 JSON Builder - local Windows setup
echo ============================================================
echo Project: %ROOT%
echo This installs the local JSON builder only. It does not install AF3
echo inference, model weights, GPU drivers, or university server software.
echo.
if defined PY_EXE echo Interpreter override requested: %PY_EXE%
echo Checking the Python environment and the GUI's native Qt imports...
echo A broken .venv is preserved as .venv.backup-^<timestamp^>; it is never
echo deleted before the replacement has passed its checks.
echo.

if defined PY_EXE (
    %TOOL_PY% "tools\check_dependencies.py" --ensure-venv --root "%ROOT%" --interpreter "%PY_EXE%"
) else (
    %TOOL_PY% "tools\check_dependencies.py" --ensure-venv --root "%ROOT%"
)
set "ENSURE=%ERRORLEVEL%"
if "%ENSURE%"=="0" goto :verify
if "%ENSURE%"=="2" goto :no_compatible_python
goto :recovery_failed

:verify
echo.
echo Running the full read-only dependency and application checks...
"%VENV_PY%" "tools\check_dependencies.py" --root "%ROOT%"
if errorlevel 1 goto :diagnostic_failed
echo.
echo SETUP SUCCEEDED. Use check_dependencies.bat to check this environment later.
echo The gui.py launcher uses this .venv and retains .venv-gui compatibility.
goto :finish

:no_python_launcher
echo ERROR: no Python interpreter was found to run the installer.
echo Install 64-bit Python 3.12 from:
echo   https://www.python.org/downloads/windows/
echo During installation, enable "Add python.exe to PATH" and the Python Launcher.
goto :failed

:no_compatible_python
echo.
echo ERROR: no compatible 64-bit CPython 3.9+ interpreter was found.
echo Anaconda/Miniconda is never selected automatically: its
echo bundled MSVC/Qt runtime can prevent the official PySide6 wheels from loading.
echo.
echo Install 64-bit Python 3.12 from:
echo   https://www.python.org/downloads/windows/
echo During installation, enable "Add python.exe to PATH" and the Python Launcher.
echo Or, if winget is available:
echo   winget install -e --id Python.Python.3.12
echo Then run setup_windows.bat again.
goto :failed

:recovery_failed
echo.
echo ERROR: the virtual environment could not be created or verified.
echo Any previous .venv was restored unchanged. A successful rebuild also
echo keeps the old environment as .venv.backup-^<timestamp^>, never deleted.
echo.
echo Check the pip output above for network or disk errors, then rerun
echo setup_windows.bat. If Qt still fails to load, install the 64-bit
echo Microsoft Visual C++ 2015-2022 Redistributable and a 64-bit python.org
echo CPython, then rerun setup_windows.bat.
goto :failed

:diagnostic_failed
echo ERROR: installation finished, but dependency verification failed.
echo Run check_dependencies.bat and follow each MISSING or INCOMPATIBLE line.
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
