@echo off
rem ---------------------------------------------------------------------------
rem  Double-click launcher for the AF3 JSON Builder text interface.
rem
rem  Same rules as run_gui.cmd: the application folder comes from this file's
rem  own directory, arguments are forwarded, and the working directory is set
rem  only so imports resolve. Saved jobs and generated configurations still go
rem  to the application's own output folders, not into this directory.
rem ---------------------------------------------------------------------------
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto :no_directory
set "ROOT=%CD%"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%ROOT%\af3builder.py" goto :no_application
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
"%VENV_PY%" "%ROOT%\af3builder.py" %*
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" exit /b 0
echo.
echo The builder exited with status %RESULT%.
echo Run check_dependencies.bat for a diagnosis, or setup_windows.bat to
echo repair the environment.
echo.
pause
exit /b %RESULT%

:no_application
echo af3builder.py was not found next to this launcher:
echo   %ROOT%
echo Put run_console.cmd inside the AF3Builder application folder.
pause
exit /b 1

:no_directory
echo Could not change to this launcher's own folder: %~dp0
pause
exit /b 1
