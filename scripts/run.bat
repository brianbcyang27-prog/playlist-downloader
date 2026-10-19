@echo off
REM Launch Playlist Downloader on Windows.
REM
REM Uses (or creates) a project-local virtual environment so nothing pollutes
REM your system Python. Safe to run repeatedly; installs only on the first run.
REM
REM   scripts\run.bat                 normal start (auto-opens your browser)
REM   scripts\run.bat --port 9000     extra flags pass through to the app
setlocal EnableExtensions
cd /d "%~dp0.."

set "PY=%CD%\.venv\Scripts\python.exe"
if exist "%PY%" goto deps

echo First run: creating a virtual environment ...
set "BASE=python"
where py >nul 2>nul
if not errorlevel 1 set "BASE=py -3"
%BASE% -m venv .venv
if errorlevel 1 (
  echo Could not create the virtual environment. Is Python 3 installed?
  echo Get it from https://www.python.org/downloads/
  pause
  exit /b 1
)
"%PY%" -m pip install --upgrade pip

:deps
"%PY%" -c "import yt_dlp, mutagen" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies ^(one time^) ...
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency install failed. Check your internet connection and retry.
    pause
    exit /b 1
  )
)

"%PY%" -m app.server %*
if errorlevel 1 pause
endlocal
