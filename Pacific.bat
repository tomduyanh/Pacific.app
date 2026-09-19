@echo off
setlocal
title Pacific
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if defined PY goto :haspy
where python >nul 2>nul && set "PY=python"
if defined PY goto :haspy
where py >nul 2>nul && set "PY=py"

:haspy
if not defined PY goto :nopy

"%PY%" run.py %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo   Pacific exited with code %RC%.
  pause
)
exit /b %RC%

:nopy
echo.
echo   [!] Python was not found on this machine.
echo.
echo       Install Python 3.9 or newer from https://www.python.org/downloads/
echo       and tick "Add python.exe to PATH" during setup, then run this again.
echo.
pause
exit /b 1
