@echo off
rem ---------------------------------------------------------------------------
rem  Double-click launcher for the AF3 JSON Builder window.
rem
rem  Works from any location: the application folder is found from this file's
rem  own directory, never from the terminal's current directory. Each argument
rem  is forwarded to gui.py (a JSON path, or --demo).
rem
rem  The working directory is the application root so imports and internal
rem  resources resolve; output locations come from the application's own
rem  output-folder service (AF3BUILDER_OUTPUT_ROOT, then preferences, then
rem  Documents\AF3Builder), never from this directory.
rem ---------------------------------------------------------------------------
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto :no_directory
set "ROOT=%CD%"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%ROOT%\gui.py" goto :no_application
if exist "%VENV_PY%" goto :launch

echo ============================================================
echo AF3 JSON Builder - the local Python environment is missing
echo ============================================================
echo Looked for: %VENV_PY%
echo.
echo Double-click setup_windows.bat in this folder first; it creates the
echo environment and installs the application's dependencies.
echo.
pause
exit /b 1

:launch
rem python.exe, not pythonw.exe: a startup failure must be readable in this
rem window instead of disappearing with no console at all.
"%VENV_PY%" "%ROOT%\gui.py" %*
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" exit /b 0
echo.
echo The window could not start (exit status %RESULT%).
echo Run check_dependencies.bat for a diagnosis, or setup_windows.bat to
echo repair the environment. The message above says what failed.
echo.
pause
exit /b %RESULT%

:no_application
echo gui.py was not found next to this launcher:
echo   %ROOT%
echo Put run_gui.cmd inside the AF3Builder application folder.
pause
exit /b 1

:no_directory
echo Could not change to this launcher's own folder: %~dp0
pause
exit /b 1
