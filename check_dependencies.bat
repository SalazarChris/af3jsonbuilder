@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto :root_failed
set "ROOT=%CD%"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
set "GUI_PY=%ROOT%\.venv-gui\Scripts\python.exe"

echo ============================================================
echo AF3 JSON Builder - dependency and environment check
echo ============================================================
if exist "%VENV_PY%" goto :check_project_venv
if exist "%GUI_PY%" goto :check_gui_venv

echo MISSING: project virtual environment was not found.
echo Double-click setup_windows.bat to create and install it.
goto :failed

:check_project_venv
echo Checking project-local .venv; no packages will be installed or changed.
"%VENV_PY%" tools\check_dependencies.py --root "%ROOT%"
if errorlevel 1 goto :failed
goto :success

:check_gui_venv
echo .venv is absent; checking the existing GUI environment for compatibility.
echo The standard setup creates .venv; this fallback does not install packages.
"%GUI_PY%" tools\check_dependencies.py --gui --root "%ROOT%"
if errorlevel 1 goto :failed
goto :success

:root_failed
echo ERROR: Could not change to the checker script's project directory: %~dp0
goto :failed

:success
echo.
echo Dependency check completed successfully.
set "RESULT=0"
goto :pause_end

:failed
echo.
echo Dependency check found a problem. No packages were modified.
set "RESULT=1"
:pause_end
echo.
pause
exit /b %RESULT%
