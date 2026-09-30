@echo off
setlocal
cd /d "%~dp0"
set "SNAPSHOT_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%SNAPSHOT_PYTHON%" goto bundled
where py >nul 2>nul
if not errorlevel 1 goto python_launcher
where python >nul 2>nul
if not errorlevel 1 goto system_python
echo Python was not found. See README.md for setup on another computer.
pause
exit /b 1
:bundled
"%SNAPSHOT_PYTHON%" "%~dp0pdf_snapshot.py" --gui %*
goto finished
:python_launcher
py -3 "%~dp0pdf_snapshot.py" --gui %*
goto finished
:system_python
python "%~dp0pdf_snapshot.py" --gui %*
:finished
if not errorlevel 1 exit /b 0
echo.
echo Could not start PDF Snapshot. See the error above and README.md for setup.
pause
exit /b 1
